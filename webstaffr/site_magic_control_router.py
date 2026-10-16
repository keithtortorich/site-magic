"""Tenant-scoped HTTP boundary for the standalone Site Magic control plane."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from .customer_auth import CustomerAuthorizer
from .db import DB_ERRORS, get_connection
from .site_magic_control import (
    ControlPlaneConflictError,
    ControlPlaneNotConfiguredError,
    ControlPlaneNotFoundError,
    ControlPlaneValidationError,
    SiteMagicControlRepository,
    SiteMagicBuildDispatcher,
    SiteMagicPublisher,
    NullSiteMagicPublisher,
)
from .workers.angel.api_auth import SharedSecretVerifier, internal_api_verifier_from_env

logger = logging.getLogger("webstaffr.site_magic_control_router")


class FactRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    value: Any
    source: dict[str, Any]


class PlanRequest(BaseModel):
    fact_ids: list[str] = Field(default_factory=list, max_length=500)
    content: dict[str, Any]


class PlanProposalRequest(BaseModel):
    fact_ids: list[str] = Field(default_factory=list, max_length=500)


class PlanPatchRequest(PlanRequest):
    base_version: int = Field(ge=1)


class BuildRequest(BaseModel):
    approval_id: str = Field(min_length=1, max_length=128)
    plan_version: int = Field(ge=1)


class PreviewCallbackRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    preview_locator: str = Field(min_length=1, max_length=512)
    artifact_manifest: dict[str, Any]
    rendered_evidence: dict[str, Any]
    trace_manifest: dict[str, Any]
    quality_report: dict[str, Any]


class BuildFailureRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    failure_code: str = Field(min_length=1, max_length=128)


class RevisionRequest(BaseModel):
    scope: list[str] = Field(min_length=1, max_length=200)
    request_text: str = Field(min_length=1, max_length=4000)
    change_class: str = Field(min_length=1, max_length=32)
    expected_impact: dict[str, Any] = Field(default_factory=dict)


class RevisionApplyRequest(BaseModel):
    approval_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    plan_version: Optional[int] = Field(default=None, ge=1)


def _idempotency_key(value: Optional[str]) -> str:
    if not value or not value.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return value.strip()[:256]


def _connection(request: Request):
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        logger.error("site_magic_control_db_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc


def _handle_control_error(exc: Exception) -> None:
    if isinstance(exc, ControlPlaneNotFoundError):
        raise HTTPException(status_code=404, detail="Site Magic resource not found") from exc
    if isinstance(exc, ControlPlaneConflictError):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, ControlPlaneValidationError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


def create_site_magic_control_router(
    authorizer: CustomerAuthorizer,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
    build_dispatcher: Optional[SiteMagicBuildDispatcher] = None,
    publisher: Optional[SiteMagicPublisher] = None,
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["site-magic-control"])
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()
    active_publisher = publisher or NullSiteMagicPublisher()

    def require_internal_caller(request: Request) -> None:
        if not active_internal_api_verifier.verify(request.headers.get("X-API-Key")):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    @router.post("/tenants/{tenant_id}/facts", status_code=201)
    def create_fact(
        tenant_id: str,
        body: FactRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            fact, replay = SiteMagicControlRepository(conn).create_fact(
                tenant_id=tenant_id, kind=body.kind, value=body.value, source=body.source,
                actor_id=context.user_id, correlation_id=context.correlation_id,
                idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_fact_create_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.fact.create", resource_type="fact", resource_id=fact.fact_id)
        return {**fact.public(), "replayed": replay}

    @router.get("/tenants/{tenant_id}/facts")
    def list_facts(tenant_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            facts = SiteMagicControlRepository(conn).list_facts(tenant_id=tenant_id)
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.fact.list", resource_type="fact")
        return {"tenant_id": tenant_id, "facts": [fact.public() for fact in facts]}

    @router.post("/tenants/{tenant_id}/facts/{fact_id}/verify")
    def verify_fact(
        tenant_id: str,
        fact_id: str,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            fact, replay = SiteMagicControlRepository(conn).verify_fact(
                tenant_id=tenant_id, fact_id=fact_id, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_fact_verify_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.fact.verify", resource_type="fact", resource_id=fact_id)
        return {**fact.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/plans/propose", status_code=201)
    def propose_plan(
        tenant_id: str,
        body: PlanProposalRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            plan, replay = SiteMagicControlRepository(conn).propose_plan(
                tenant_id=tenant_id, fact_ids=body.fact_ids, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_plan_propose_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.plan.propose", resource_type="plan", resource_id=plan.plan_id)
        return {**plan.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/plans", status_code=201)
    def create_plan(
        tenant_id: str,
        body: PlanRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            plan, replay = SiteMagicControlRepository(conn).create_plan(
                tenant_id=tenant_id, fact_ids=body.fact_ids, content=body.content,
                actor_id=context.user_id, correlation_id=context.correlation_id,
                idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_plan_create_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.plan.propose", resource_type="plan", resource_id=plan.plan_id)
        return {**plan.public(), "replayed": replay}

    @router.get("/tenants/{tenant_id}/plans")
    def list_plans(tenant_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            plans = SiteMagicControlRepository(conn).list_plans(tenant_id=tenant_id)
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.plan.list", resource_type="plan")
        return {"tenant_id": tenant_id, "plans": [plan.public() for plan in plans]}

    @router.get("/tenants/{tenant_id}/plans/{plan_id}")
    def get_plan(tenant_id: str, plan_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            plan = SiteMagicControlRepository(conn).get_plan(tenant_id=tenant_id, plan_id=plan_id)
        finally:
            conn.close()
        if plan is None:
            raise HTTPException(status_code=404, detail="Site Magic resource not found")
        authorizer.audit(request, context, action="site_magic.plan.read", resource_type="plan", resource_id=plan_id)
        return plan.public()

    @router.patch("/tenants/{tenant_id}/plans/{plan_id}/draft")
    def patch_plan(
        tenant_id: str,
        plan_id: str,
        body: PlanPatchRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            plan, replay = SiteMagicControlRepository(conn).patch_plan(
                tenant_id=tenant_id, plan_id=plan_id, base_version=body.base_version,
                fact_ids=body.fact_ids, content=body.content, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_plan_patch_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.plan.edit", resource_type="plan", resource_id=plan_id)
        return {**plan.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/plans/{plan_id}/versions/{version}/approve")
    def approve_plan(
        tenant_id: str,
        plan_id: str,
        version: int,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "owner")
        conn = _connection(request)
        try:
            approval, replay = SiteMagicControlRepository(conn).approve_plan(
                tenant_id=tenant_id, plan_id=plan_id, version=version, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_plan_approve_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.plan.approve", resource_type="plan", resource_id=plan_id)
        return {**approval.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/builds", status_code=202)
    def request_build(
        tenant_id: str,
        body: BuildRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            build, replay = SiteMagicControlRepository(conn).request_build(
                tenant_id=tenant_id, approval_id=body.approval_id, plan_version=body.plan_version,
                actor_id=context.user_id, correlation_id=context.correlation_id,
                idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_build_request_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        if build_dispatcher is not None and not replay:
            try:
                build_dispatcher.dispatch(build=build)
            except Exception as exc:  # provider boundary must not leak details
                logger.error("site_magic_control_build_dispatch_failed error_type=%s", type(exc).__name__)
                raise HTTPException(status_code=503, detail="Site Magic build engine unavailable") from exc
        authorizer.audit(request, context, action="site_magic.build.request", resource_type="build", resource_id=build.build_id)
        return {**build.public(), "replayed": replay}

    @router.get("/tenants/{tenant_id}/builds/{build_id}")
    def get_build(tenant_id: str, build_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            build = SiteMagicControlRepository(conn).get_build(
                tenant_id=tenant_id, build_id=build_id
            )
        finally:
            conn.close()
        if build is None:
            raise HTTPException(status_code=404, detail="Site Magic resource not found")
        authorizer.audit(request, context, action="site_magic.build.read", resource_type="build", resource_id=build_id)
        return build.public()

    @router.post("/internal/builds/{build_id}/preview", status_code=202)
    def receive_preview(
        build_id: str,
        body: PreviewCallbackRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        require_internal_caller(request)
        conn = _connection(request)
        try:
            preview, replay = SiteMagicControlRepository(conn).create_preview(
                tenant_id=body.tenant_id, build_id=build_id, preview_locator=body.preview_locator,
                artifact_manifest=body.artifact_manifest, rendered_evidence=body.rendered_evidence,
                trace_manifest=body.trace_manifest, quality_report=body.quality_report,
                actor_type="build_engine", actor_id=None,
                correlation_id=request.headers.get("X-Correlation-ID") or str(uuid.uuid4()),
                idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_preview_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        return {**preview.public(), "replayed": replay}

    @router.post("/internal/builds/{build_id}/failed", status_code=202)
    def fail_build(
        build_id: str,
        body: BuildFailureRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        require_internal_caller(request)
        conn = _connection(request)
        try:
            build, replay = SiteMagicControlRepository(conn).fail_build(
                tenant_id=body.tenant_id,
                build_id=build_id, failure_code=body.failure_code, actor_id=None,
                correlation_id=request.headers.get("X-Correlation-ID") or str(uuid.uuid4()),
                idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_build_failure_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        return {**build.public(), "replayed": replay}

    @router.get("/internal/builds/{build_id}/source")
    def get_build_source(
        build_id: str,
        request: Request,
        tenant_id: str = Query(min_length=1, max_length=128),
    ) -> dict[str, Any]:
        require_internal_caller(request)
        conn = _connection(request)
        try:
            source = SiteMagicControlRepository(conn).get_build_source(
                tenant_id=tenant_id, build_id=build_id
            )
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            logger.error("site_magic_control_build_source_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        return source

    @router.get("/tenants/{tenant_id}/previews/{preview_id}")
    def get_preview(tenant_id: str, preview_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            preview = SiteMagicControlRepository(conn).get_preview(tenant_id=tenant_id, preview_id=preview_id)
        finally:
            conn.close()
        if preview is None:
            raise HTTPException(status_code=404, detail="Site Magic resource not found")
        authorizer.audit(request, context, action="site_magic.preview.read", resource_type="preview", resource_id=preview_id)
        return preview.public()

    @router.post("/tenants/{tenant_id}/previews/{preview_id}/revisions", status_code=201)
    def request_revision(
        tenant_id: str,
        preview_id: str,
        body: RevisionRequest,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        conn = _connection(request)
        try:
            revision, replay = SiteMagicControlRepository(conn).request_revision(
                tenant_id=tenant_id, preview_id=preview_id, scope=body.scope,
                request_text=body.request_text, change_class=body.change_class,
                expected_impact=body.expected_impact, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_revision_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.revision.request", resource_type="revision", resource_id=revision.revision_id)
        return {**revision.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/revisions/{revision_id}/apply", status_code=202)
    def apply_revision(
        tenant_id: str,
        revision_id: str,
        request: Request,
        body: Optional[RevisionApplyRequest] = None,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "manager")
        request_key = _idempotency_key(idempotency_key)
        conn = _connection(request)
        try:
            build, replay = SiteMagicControlRepository(conn).apply_revision(
                tenant_id=tenant_id, revision_id=revision_id, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=request_key,
                approval_id=body.approval_id if body else None,
                plan_version=body.plan_version if body else None,
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_revision_apply_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        if build_dispatcher is not None and not replay:
            try:
                build_dispatcher.dispatch(build=build)
            except Exception as exc:
                logger.error("site_magic_control_revision_dispatch_failed error_type=%s", type(exc).__name__)
                raise HTTPException(status_code=503, detail="Site Magic build engine unavailable") from exc
        authorizer.audit(request, context, action="site_magic.revision.apply", resource_type="revision", resource_id=revision_id)
        return {**build.public(), "replayed": replay}

    @router.post("/tenants/{tenant_id}/previews/{preview_id}/checkpoint", status_code=201)
    def accept_checkpoint(
        tenant_id: str,
        preview_id: str,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "owner")
        conn = _connection(request)
        try:
            checkpoint, replay = SiteMagicControlRepository(conn).accept_checkpoint(
                tenant_id=tenant_id, preview_id=preview_id, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=_idempotency_key(idempotency_key),
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_checkpoint_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.checkpoint.accept", resource_type="checkpoint", resource_id=checkpoint.checkpoint_id)
        return {**checkpoint.public(), "replayed": replay}

    @router.get("/tenants/{tenant_id}/checkpoints/{checkpoint_id}")
    def get_checkpoint(tenant_id: str, checkpoint_id: str, request: Request) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            checkpoint = SiteMagicControlRepository(conn).get_checkpoint(
                tenant_id=tenant_id, checkpoint_id=checkpoint_id
            )
        finally:
            conn.close()
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="Site Magic resource not found")
        authorizer.audit(request, context, action="site_magic.checkpoint.read", resource_type="checkpoint", resource_id=checkpoint_id)
        return checkpoint.public()

    @router.post("/tenants/{tenant_id}/checkpoints/{checkpoint_id}/release", status_code=202)
    def release_checkpoint(
        tenant_id: str,
        checkpoint_id: str,
        request: Request,
        idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "owner")
        request_key = _idempotency_key(idempotency_key)
        conn = _connection(request)
        try:
            repository = SiteMagicControlRepository(conn)
            release, replay = repository.request_release(
                tenant_id=tenant_id, checkpoint_id=checkpoint_id, actor_id=context.user_id,
                correlation_id=context.correlation_id, idempotency_key=request_key,
            )
            conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            conn.rollback()
            logger.error("site_magic_control_release_request_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            conn.close()

        if release.status == "published":
            authorizer.audit(request, context, action="site_magic.release.read", resource_type="release", resource_id=release.release_id)
            return {**release.public(), "replayed": replay}

        checkpoint_conn = _connection(request)
        try:
            checkpoint = SiteMagicControlRepository(checkpoint_conn).get_checkpoint(
                tenant_id=tenant_id, checkpoint_id=checkpoint_id
            )
        finally:
            checkpoint_conn.close()
        if checkpoint is None:
            raise HTTPException(status_code=404, detail="Site Magic resource not found")
        try:
            public_locator = active_publisher.publish(
                tenant_id=tenant_id, checkpoint_id=checkpoint_id,
                artifact_locator=checkpoint.artifact_manifest.get("locator", ""),
                artifact_manifest=checkpoint.artifact_manifest,
            )
        except ControlPlaneNotConfiguredError as exc:
            failure_code = "publisher_not_configured"
        except Exception as exc:  # publisher boundary must not leak provider details
            logger.error("site_magic_control_release_publish_failed error_type=%s", type(exc).__name__)
            failure_code = "publisher_failed"
        else:
            failure_code = None

        result_conn = _connection(request)
        try:
            result_repo = SiteMagicControlRepository(result_conn)
            if failure_code is None:
                release = result_repo.complete_release(
                    tenant_id=tenant_id, release_id=release.release_id, public_locator=public_locator,
                    actor_id=None, correlation_id=context.correlation_id,
                    idempotency_key=f"{request_key}:published",
                )
            else:
                release = result_repo.fail_release(
                    tenant_id=tenant_id, release_id=release.release_id, failure_code=failure_code,
                    actor_id=None, correlation_id=context.correlation_id,
                    idempotency_key=f"{request_key}:failed",
                )
            result_conn.commit()
        except (ControlPlaneNotFoundError, ControlPlaneConflictError, ControlPlaneValidationError) as exc:
            result_conn.rollback()
            _handle_control_error(exc)
        except DB_ERRORS as exc:
            result_conn.rollback()
            logger.error("site_magic_control_release_finalize_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Site Magic temporarily unavailable") from exc
        finally:
            result_conn.close()
        authorizer.audit(request, context, action="site_magic.release.publish", resource_type="release", resource_id=release.release_id)
        return {**release.public(), "replayed": replay}

    @router.get("/tenants/{tenant_id}/events")
    def list_events(tenant_id: str, request: Request, limit: int = 100) -> dict[str, Any]:
        context = authorizer.authorize(request, tenant_id, "viewer")
        conn = _connection(request)
        try:
            events = SiteMagicControlRepository(conn).list_events(tenant_id=tenant_id, limit=limit)
        finally:
            conn.close()
        authorizer.audit(request, context, action="site_magic.event.list", resource_type="event")
        return {"tenant_id": tenant_id, "events": events}

    return router
