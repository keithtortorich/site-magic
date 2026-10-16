"""Demo site lifecycle on top of the real Site Magic pipeline.

Per ADR-030: a demo at /demos/{slug} is a Site Magic job against a
reserved tenant_id, not a static fixture. This module owns that job's
lifecycle -- enqueue once, poll status, auto-publish once a build is
ready -- so demo_router.py stays a thin HTTP layer.

Auto-publish (skipping the customer "review then publish" step
site_magic_router.py's POST /jobs/{id}/publish exposes) is deliberate: a
demo has no human customer to click publish, and CustomerAuthorizer's
owner-role check has no meaningful subject for a reserved system tenant.
This is why DemoJobManager talks to SiteMagicRepository and
ArtifactStorage directly instead of going through the customer-facing
router -- same underlying tables and contracts, no new persistence
surface, just a different (system, not customer-authorized) caller.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .db import DB_ERRORS
from .demo_sites import DemoFixture
from .site_magic import (
    ArtifactStorage,
    NullArtifactStorage,
    NullSiteMagicQueue,
    SiteMagicNotConfiguredError,
    SiteMagicQueue,
    SiteMagicRepository,
    TERMINAL_STATUSES,
)

logger = logging.getLogger("webstaffr.demo_job_manager")

DemoStatus = Literal["not_started", "building", "ready", "failed"]


@dataclass(frozen=True)
class DemoStatusResult:
    status: DemoStatus
    job_status: Optional[str] = None
    published_url: Optional[str] = None
    failure_code: Optional[str] = None


_BUILDING_STATUSES = frozenset(
    {"queued", "ingesting", "directing", "building", "evaluating", "remediating", "final_review"}
)


class DemoJobManager:
    """Wraps SiteMagicRepository + SiteMagicQueue + ArtifactStorage for
    the demo-site flow. Constructed per-request with an already-open
    connection, same lifecycle as SiteMagicRepository itself -- no
    connection pooling or caching of its own."""

    def __init__(
        self,
        conn,
        *,
        queue: Optional[SiteMagicQueue] = None,
        artifact_storage: Optional[ArtifactStorage] = None,
    ) -> None:
        self._conn = conn
        self._repo = SiteMagicRepository(conn)
        self._queue = queue or NullSiteMagicQueue()
        self._storage = artifact_storage or NullArtifactStorage()

    def _latest_job(self, reserved_tenant_id: str) -> Optional[Any]:
        """Site Magic has no "jobs for tenant" list query today (every
        existing caller already knows its job_id) -- demos are the first
        caller that needs "do I already have a job for this tenant",
        so that lookup lives here rather than growing the general
        repository's surface for a demo-only need."""
        row = self._conn.execute(
            """
            SELECT job_id FROM site_magic_jobs
            WHERE tenant_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (reserved_tenant_id,),
        ).fetchone()
        if row is None:
            return None
        return self._repo.get_job(tenant_id=reserved_tenant_id, job_id=str(row["job_id"]))

    def enqueue_if_needed(self, fixture: DemoFixture) -> DemoStatusResult:
        """Idempotent from the caller's perspective: if a job already
        exists for this demo's reserved tenant, returns its current
        status without creating a second one. Only creates + enqueues on
        a genuine first visit."""
        existing = self._latest_job(fixture.reserved_tenant_id)
        if existing is not None:
            return self._status_for_job(existing)

        try:
            # site_magic_jobs.tenant_id has a FOREIGN KEY on tenants
            # (0016_site_magic.sql) -- a real submission gets this row via
            # IntakeRepository.save()'s own INSERT OR IGNORE (intake.py);
            # a demo has no intake submission, so it needs the same
            # insert done here instead, or create_job() below fails its
            # FK check on every demo's first-ever visit.
            self._conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)",
                (fixture.reserved_tenant_id,),
            )
            job = self._repo.create_job(
                tenant_id=fixture.reserved_tenant_id,
                source_type="intake",
                source_payload={
                    "type": "intake",
                    # No real intake_submissions row backs a demo -- the
                    # worker's resolveSource() reads verified_facts
                    # straight off this payload for the intake branch
                    # rather than re-fetching, so a stable synthetic id
                    # is sufficient here (see site_magic_worker.ts).
                    "intake_id": f"demo:{fixture.slug}",
                    "verified_facts": fixture.verified_facts,
                },
            )
            self._queue.enqueue(job_id=job.job_id, tenant_id=fixture.reserved_tenant_id)
            self._conn.commit()
        except SiteMagicNotConfiguredError:
            self._conn.rollback()
            logger.warning("demo_queue_not_configured slug=%s", fixture.slug)
            return DemoStatusResult(status="not_started")
        except DB_ERRORS as exc:
            self._conn.rollback()
            logger.error("demo_enqueue_failed slug=%s error_type=%s", fixture.slug, type(exc).__name__)
            return DemoStatusResult(status="not_started")
        return self._status_for_job(job)

    def get_status(self, reserved_tenant_id: str) -> DemoStatusResult:
        job = self._latest_job(reserved_tenant_id)
        if job is None:
            return DemoStatusResult(status="not_started")
        return self._status_for_job(job)

    def _status_for_job(self, job) -> DemoStatusResult:
        if job.status == "published":
            build = self._repo.get_build(tenant_id=job.tenant_id, build_id=job.final_build_id) if job.final_build_id else None
            return DemoStatusResult(
                status="ready", job_status=job.status,
                published_url=(build.published_url if build else None),
            )
        if job.status == "ready_for_review":
            published = self._auto_publish(job)
            if published is not None:
                return DemoStatusResult(status="ready", job_status="published", published_url=published)
            # Auto-publish failed (storage not configured, race, etc.) --
            # report the true underlying state rather than claim ready.
            return DemoStatusResult(status="building", job_status=job.status)
        if job.status in _BUILDING_STATUSES:
            return DemoStatusResult(status="building", job_status=job.status)
        if job.status in TERMINAL_STATUSES:  # failed, quarantined
            return DemoStatusResult(status="failed", job_status=job.status, failure_code=job.failure_code)
        return DemoStatusResult(status="building", job_status=job.status)

    def _auto_publish(self, job) -> Optional[str]:
        if job.final_build_id is None:
            return None
        build = self._repo.get_build(tenant_id=job.tenant_id, build_id=job.final_build_id)
        if build is None:
            return None
        try:
            published_url = self._storage.publish(
                tenant_id=job.tenant_id, locator=build.preview_locator, build_id=build.build_id,
            )
            self._repo.publish(
                tenant_id=job.tenant_id, job_id=job.job_id, build_id=build.build_id,
                published_url=published_url,
            )
            self._conn.commit()
        except SiteMagicNotConfiguredError:
            self._conn.rollback()
            logger.warning("demo_auto_publish_storage_not_configured tenant_id=%s", job.tenant_id)
            return None
        except DB_ERRORS as exc:
            self._conn.rollback()
            logger.error("demo_auto_publish_failed tenant_id=%s error_type=%s", job.tenant_id, type(exc).__name__)
            return None
        return published_url
