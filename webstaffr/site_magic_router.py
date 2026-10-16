"""Authenticated control plane for the external Site Magic worker."""

from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .customer_auth import CustomerAuthorizer
from .db import DB_ERRORS, get_connection
from .site_magic import (
    ArtifactStorage,
    InvalidStateTransitionError,
    NullArtifactStorage,
    NullSiteMagicQueue,
    PREVIEWABLE_STATUSES,
    SiteMagicNotConfiguredError,
    SiteMagicQueue,
    SiteMagicRepository,
)
from .site_magic_security import UnsafeSiteSourceError, normalize_public_url
from .workers.angel.api_auth import SharedSecretVerifier, internal_api_verifier_from_env

logger = logging.getLogger("webstaffr.site_magic_router")


class IntakeSource(BaseModel):
    type: Literal["intake"]
    intake_id: str = Field(min_length=1, max_length=128)


class URLSource(BaseModel):
    type: Literal["url"]
    url: str = Field(min_length=1, max_length=2048)
    ownership_attested: Literal[True]


class RepositorySource(BaseModel):
    type: Literal["repository"]
    surface: str = Field(min_length=1, max_length=128)


class CreateJobRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    source: dict[str, Any]


class PublishJobRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)


class TransitionJobRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=32)
    # Optional: when present, the transition is idempotent -- a retry with
    # the same event_id replays the cached result (200, was_replay=true)
    # instead of re-applying or 409ing. Omit for the plain, non-idempotent
    # path (existing callers/tests keep working unchanged).
    event_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    # Keep in sync with MAX_REMEDIATION_ROUNDS (site_maker_engine.ts) -- the
    # worker posts remediation_rounds up to that constant on every
    # evaluating->remediating transition, and a lower ceiling here 422s the
    # transition rather than remediating (found 2026-08-14: worker bumped to
    # 4, this stayed at 2, third round failed the job instead of quarantining).
    remediation_rounds: Optional[int] = Field(default=None, ge=0, le=4)
    rebuild_count: Optional[int] = Field(default=None, ge=0, le=1)
    quality_summary: Optional[dict[str, Any]] = None
    failure_code: Optional[str] = Field(default=None, max_length=64)
    # Present only on the transition into ready_for_review, immediately
    # after ArtifactStore.sealPrivateImmutable() (site_maker_engine.ts).
    # All three required together -- see internal_transition_job().
    build_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    artifact_manifest: Optional[dict[str, Any]] = None
    preview_locator: Optional[str] = Field(default=None, min_length=1, max_length=512)


def _public_job(job, final_url: Optional[str] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "source_type": job.source_type,
        "status": job.status,
        "remediation_rounds": job.remediation_rounds,
        "rebuild_count": job.rebuild_count,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }
    if job.status in PREVIEWABLE_STATUSES and final_url:
        payload["final_url"] = final_url
    return payload


def create_site_magic_router(
    authorizer: CustomerAuthorizer,
    queue: Optional[SiteMagicQueue] = None,
    artifact_storage: Optional[ArtifactStorage] = None,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
) -> APIRouter:
    router = APIRouter(prefix="/site-magic", tags=["site-magic"])
    active_queue = queue or NullSiteMagicQueue()
    active_storage = artifact_storage or NullArtifactStorage()
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()

    def connection(request: Request):
        try:
            return get_connection(request.app.state.db_path)
        except DB_ERRORS as exc:
            logger.error("site_magic_db_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc

    @router.post("/jobs", status_code=202)
    def create_job(body: CreateJobRequest, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, body.tenant_id, "owner")
        source_type = body.source.get("type")
        try:
            if source_type == "intake":
                source = IntakeSource(**body.source)
                source_payload = source.model_dump() if hasattr(source, "model_dump") else source.dict()
            elif source_type == "url":
                source = URLSource(**body.source)
                source_payload = source.model_dump() if hasattr(source, "model_dump") else source.dict()
                source_payload["url"] = normalize_public_url(source.url)
            elif source_type == "repository":
                raise HTTPException(status_code=403, detail="Repository sources are internal only")
            else:
                raise ValueError("Unsupported Site Magic source")
        except UnsafeSiteSourceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="Invalid Site Magic source") from exc

        conn = connection(request)
        try:
            repo = SiteMagicRepository(conn)
            job = repo.create_job(
                tenant_id=body.tenant_id, source_type=source_type, source_payload=source_payload
            )
            active_queue.enqueue(job_id=job.job_id, tenant_id=body.tenant_id)
            conn.commit()
        except SiteMagicNotConfiguredError as exc:
            conn.rollback()
            raise HTTPException(status_code=503, detail="Site Magic is not configured") from exc
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_create_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.job.create", resource_type="site_magic_job", resource_id=job.job_id)
        return _public_job(job)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: str, request: Request, tenant_id: str = Query(...)) -> dict[str, Any]:
        authorizer.authorize(request, tenant_id, "viewer")
        conn = connection(request)
        try:
            job = SiteMagicRepository(conn).get_job(tenant_id=tenant_id, job_id=job_id)
        finally:
            conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail="Site Magic job not found")
        return _public_job(job)

    @router.get("/jobs/{job_id}/preview")
    def preview(job_id: str, request: Request, tenant_id: str = Query(...)) -> dict[str, str]:
        authorizer.authorize(request, tenant_id, "viewer")
        conn = connection(request)
        try:
            repo = SiteMagicRepository(conn)
            job = repo.get_job(tenant_id=tenant_id, job_id=job_id)
            build = repo.get_build(tenant_id=tenant_id, build_id=job.final_build_id) if job and job.final_build_id else None
        finally:
            conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail="Site Magic job not found")
        if job.status not in PREVIEWABLE_STATUSES or build is None:
            raise HTTPException(status_code=409, detail="Final preview is not ready")
        try:
            return {"final_url": active_storage.signed_preview_url(tenant_id=tenant_id, locator=build.preview_locator)}
        except SiteMagicNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail="Site Magic artifact storage is not configured") from exc

    @router.post("/jobs/{job_id}/publish")
    def publish(job_id: str, body: PublishJobRequest, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, body.tenant_id, "owner")
        conn = connection(request)
        try:
            repo = SiteMagicRepository(conn)
            job = repo.get_job(tenant_id=body.tenant_id, job_id=job_id)
            build = repo.get_build(tenant_id=body.tenant_id, build_id=job.final_build_id) if job and job.final_build_id else None
            if job is None:
                raise HTTPException(status_code=404, detail="Site Magic job not found")
            if job.status != "ready_for_review" or build is None:
                raise HTTPException(status_code=409, detail="Site Magic job is not publishable")
            published_url = active_storage.publish(
                tenant_id=body.tenant_id, locator=build.preview_locator, build_id=build.build_id
            )
            job = repo.publish(
                tenant_id=body.tenant_id, job_id=job_id, build_id=build.build_id,
                published_url=published_url,
            )
            conn.commit()
        except SiteMagicNotConfiguredError as exc:
            conn.rollback()
            raise HTTPException(status_code=503, detail="Site Magic artifact storage is not configured") from exc
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_publish_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.job.publish", resource_type="site_magic_job", resource_id=job_id)
        return _public_job(job, published_url)

    def _require_internal_caller(x_api_key: Optional[str]) -> None:
        if not active_internal_api_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    @router.get("/internal/jobs/{job_id}")
    def internal_get_job(
        job_id: str, request: Request, tenant_id: str = Query(...),
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict[str, Any]:
        """Server-to-server only: the worker fetching a job it was just
        handed by the queue. Includes source_payload -- unlike
        _public_job()'s customer-facing projection, this endpoint's caller
        IS the thing that needs to act on the source (crawl the URL, read
        the intake_id), not a tenant browsing their own job history."""
        _require_internal_caller(x_api_key)
        conn = connection(request)
        try:
            job = SiteMagicRepository(conn).get_job(tenant_id=tenant_id, job_id=job_id)
        finally:
            conn.close()
        if job is None:
            raise HTTPException(status_code=404, detail="Site Magic job not found")
        return {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "source_type": job.source_type,
            "source_payload": job.source_payload,
            "status": job.status,
            "remediation_rounds": job.remediation_rounds,
            "rebuild_count": job.rebuild_count,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    @router.post("/internal/jobs/{job_id}/transition")
    def internal_transition_job(
        job_id: str, body: TransitionJobRequest, request: Request,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> dict[str, Any]:
        """Server-to-server only: the worker reporting a state-machine
        step as it runs SiteMakerEngine.run() (site_maker_engine.ts) --
        one call per JobStateSink.transition()."""
        _require_internal_caller(x_api_key)
        build_fields_present = (
            body.build_id is not None or body.artifact_manifest is not None or body.preview_locator is not None
        )
        if build_fields_present and (
            body.build_id is None or body.artifact_manifest is None or body.preview_locator is None
        ):
            raise HTTPException(
                status_code=422,
                detail="build_id, artifact_manifest, and preview_locator must all be present together",
            )

        # event_id-based idempotent replay only covers the plain transition
        # path -- seal_build_and_advance() already has its own idempotency
        # signal (build_id's PRIMARY KEY: a retried seal for a build_id
        # that already landed 503s rather than silently re-sealing). Both
        # mechanisms are real; they just don't need to be the same one.
        was_replay = False
        conn = connection(request)
        try:
            repo = SiteMagicRepository(conn)
            if build_fields_present:
                job = repo.seal_build_and_advance(
                    tenant_id=body.tenant_id, job_id=job_id, build_id=body.build_id,
                    artifact_manifest=body.artifact_manifest, preview_locator=body.preview_locator,
                    target=body.target, remediation_rounds=body.remediation_rounds,
                    rebuild_count=body.rebuild_count,
                )
            elif body.event_id is not None:
                job, was_replay = repo.transition_idempotent(
                    tenant_id=body.tenant_id, job_id=job_id, event_id=body.event_id, target=body.target,
                    remediation_rounds=body.remediation_rounds, rebuild_count=body.rebuild_count,
                    quality_summary=body.quality_summary, failure_code=body.failure_code,
                )
            else:
                job = repo.transition(
                    tenant_id=body.tenant_id, job_id=job_id, target=body.target,
                    remediation_rounds=body.remediation_rounds, rebuild_count=body.rebuild_count,
                    quality_summary=body.quality_summary, failure_code=body.failure_code,
                )
            conn.commit()
        except KeyError as exc:
            conn.rollback()
            raise HTTPException(status_code=404, detail="Site Magic job not found") from exc
        except InvalidStateTransitionError as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_internal_transition_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        payload = _public_job(job)
        if body.event_id is not None:
            payload["was_replay"] = was_replay
            payload["event_sequence"] = job.current_event_sequence
        return payload

    return router
