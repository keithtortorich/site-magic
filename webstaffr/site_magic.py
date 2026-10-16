"""Tenant-scoped persistence and fail-closed integration contracts for Site Magic."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Protocol

from .db import DB_ERRORS
from .site_magic_quality import quality_gates_pass


def _json_column(value: Any) -> Any:
    """Read a JSON column that is TEXT under SQLite and jsonb under Postgres.

    psycopg2 parses jsonb for us, so the same column arrives as a `str` from
    SQLite and as an already-decoded `dict`/`list` from Postgres. Calling
    json.loads() on the decoded value raises TypeError -- which is neither a
    DB_ERROR nor a SiteMagicNotConfiguredError, so it escaped every handler in
    intake's enqueue path and surfaced as a bare 500 with no log line, while
    every SQLite-backed test passed. Found 2026-08-12 by the first real
    production intake.
    """
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value)


logger = logging.getLogger("webstaffr.site_magic")

JobStatus = Literal[
    "queued", "ingesting", "directing", "building", "evaluating",
    "remediating", "final_review", "ready_for_review", "published",
    "failed", "quarantined",
]

TERMINAL_STATUSES = frozenset({"published", "failed", "quarantined"})
PREVIEWABLE_STATUSES = frozenset({"ready_for_review", "published"})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"ingesting", "failed", "quarantined"}),
    "ingesting": frozenset({"directing", "failed", "quarantined"}),
    "directing": frozenset({"building", "failed", "quarantined"}),
    "building": frozenset({"evaluating", "failed", "quarantined"}),
    "evaluating": frozenset({"remediating", "final_review", "failed", "quarantined"}),
    "remediating": frozenset({"evaluating", "building", "failed", "quarantined"}),
    "final_review": frozenset({"ready_for_review", "building", "failed", "quarantined"}),
    "ready_for_review": frozenset({"published", "failed", "quarantined"}),
    "published": frozenset(),
    "failed": frozenset(),
    "quarantined": frozenset(),
}


class SiteMagicNotConfiguredError(RuntimeError):
    """Raised when an external Site Magic service is not configured."""


class InvalidStateTransitionError(ValueError):
    pass


class SiteMagicQueue(Protocol):
    def enqueue(self, *, job_id: str, tenant_id: str) -> None: ...


class ArtifactStorage(Protocol):
    def signed_preview_url(self, *, tenant_id: str, locator: str) -> str: ...

    def publish(self, *, tenant_id: str, locator: str, build_id: str) -> str: ...


class SiteCrawler(Protocol):
    def snapshot(self, *, url: str, tenant_id: str) -> dict[str, Any]: ...


class ImageGenerator(Protocol):
    def generate_directions(self, *, brief: str, count: int = 3) -> list[str]: ...


class CodexRuntime(Protocol):
    def run(self, *, job_id: str, workspace: str, instructions: str) -> dict[str, Any]: ...


class NullSiteMagicQueue:
    def enqueue(self, *, job_id: str, tenant_id: str) -> None:
        raise SiteMagicNotConfiguredError("Site Magic queue is not configured")


class NullArtifactStorage:
    def signed_preview_url(self, *, tenant_id: str, locator: str) -> str:
        raise SiteMagicNotConfiguredError("Site Magic artifact storage is not configured")

    def publish(self, *, tenant_id: str, locator: str, build_id: str) -> str:
        raise SiteMagicNotConfiguredError("Site Magic artifact storage is not configured")


class NullSiteCrawler:
    def snapshot(self, *, url: str, tenant_id: str) -> dict[str, Any]:
        raise SiteMagicNotConfiguredError("Site Magic crawler is not configured")


class NullImageGenerator:
    def generate_directions(self, *, brief: str, count: int = 3) -> list[str]:
        raise SiteMagicNotConfiguredError("Site Magic image generator is not configured")


class NullCodexRuntime:
    def run(self, *, job_id: str, workspace: str, instructions: str) -> dict[str, Any]:
        raise SiteMagicNotConfiguredError("Site Magic Codex runtime is not configured")


@dataclass(frozen=True)
class SiteMagicJob:
    job_id: str
    tenant_id: str
    source_type: str
    source_payload: dict[str, Any]
    status: str
    remediation_rounds: int
    rebuild_count: int
    quality_summary: Optional[dict[str, Any]]
    final_build_id: Optional[str]
    failure_code: Optional[str]
    current_event_sequence: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SiteMagicBuild:
    build_id: str
    job_id: str
    tenant_id: str
    artifact_manifest: dict[str, Any]
    preview_locator: str
    published_url: Optional[str]
    created_at: str


def assert_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidStateTransitionError(f"Invalid Site Magic transition: {current} -> {target}")


class SiteMagicRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def create_job(self, *, tenant_id: str, source_type: str, source_payload: dict[str, Any]) -> SiteMagicJob:
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO site_magic_jobs (
                job_id, tenant_id, source_type, source_payload_json, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, tenant_id, source_type, json.dumps(source_payload, sort_keys=True), now, now),
        )
        return self.get_job(tenant_id=tenant_id, job_id=job_id)

    def get_job(self, *, tenant_id: str, job_id: str) -> Optional[SiteMagicJob]:
        row = self._conn.execute(
            """
            SELECT job_id, tenant_id, source_type, source_payload_json, status,
                   remediation_rounds, rebuild_count, quality_summary_json,
                   final_build_id, failure_code, current_event_sequence,
                   created_at, updated_at
            FROM site_magic_jobs WHERE tenant_id = ? AND job_id = ?
            """,
            (tenant_id, job_id),
        ).fetchone()
        if row is None:
            return None
        return SiteMagicJob(
            job_id=str(row["job_id"]), tenant_id=row["tenant_id"],
            source_type=row["source_type"],
            source_payload=_json_column(row["source_payload_json"]),
            status=row["status"],
            remediation_rounds=row["remediation_rounds"], rebuild_count=row["rebuild_count"],
            quality_summary=_json_column(row["quality_summary_json"]),
            final_build_id=(str(row["final_build_id"]) if row["final_build_id"] else None),
            failure_code=row["failure_code"],
            current_event_sequence=row["current_event_sequence"],
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def transition(
        self,
        *,
        tenant_id: str,
        job_id: str,
        target: str,
        remediation_rounds: Optional[int] = None,
        rebuild_count: Optional[int] = None,
        quality_summary: Optional[dict[str, Any]] = None,
        failure_code: Optional[str] = None,
    ) -> SiteMagicJob:
        """Advance a job's status, optionally updating the round/rebuild
        counters and recording a quality report or failure reason in the
        same statement. Every optional arg left as None leaves that
        column unchanged -- the worker only passes what it actually has
        for a given transition (e.g. quality_summary at evaluating,
        failure_code at failed/quarantined)."""
        job = self.get_job(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise KeyError(job_id)
        assert_transition(job.status, target)
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE site_magic_jobs SET
                status = ?, updated_at = ?,
                remediation_rounds = COALESCE(?, remediation_rounds),
                rebuild_count = COALESCE(?, rebuild_count),
                quality_summary_json = COALESCE(?, quality_summary_json),
                failure_code = COALESCE(?, failure_code)
            WHERE tenant_id = ? AND job_id = ? AND status = ?
            """,
            (
                target, now, remediation_rounds, rebuild_count,
                (json.dumps(quality_summary, sort_keys=True) if quality_summary is not None else None),
                failure_code, tenant_id, job_id, job.status,
            ),
        )
        if cursor.rowcount != 1:
            raise InvalidStateTransitionError("Site Magic job changed concurrently")
        return self.get_job(tenant_id=tenant_id, job_id=job_id)

    def transition_idempotent(
        self,
        *,
        tenant_id: str,
        job_id: str,
        event_id: str,
        target: str,
        remediation_rounds: Optional[int] = None,
        rebuild_count: Optional[int] = None,
        quality_summary: Optional[dict[str, Any]] = None,
        failure_code: Optional[str] = None,
    ) -> tuple[SiteMagicJob, bool]:
        """Same as transition(), plus an idempotency ledger keyed on
        (job_id, event_id). Returns (job, was_replay) -- was_replay=True
        means this exact event_id was already applied and the cached
        result is being returned rather than re-applying it (a retried
        worker callback after a timed-out response, for example).

        event_sequence is allocated here, server-side, from
        site_magic_jobs.current_event_sequence -- callers never supply
        one, so there's no "client sent a stale sequence number" case to
        handle. A concurrent transition attempt (whether a genuine race
        or two different event_ids fighting over the same status change)
        still goes through the same optimistic `WHERE status = ?` guard
        transition() uses, and still raises InvalidStateTransitionError."""
        existing = self._conn.execute(
            "SELECT response_json FROM site_magic_job_events WHERE job_id = ? AND event_id = ?",
            (job_id, event_id),
        ).fetchone()
        if existing is not None:
            return self.get_job(tenant_id=tenant_id, job_id=job_id), True

        job = self.get_job(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise KeyError(job_id)
        assert_transition(job.status, target)
        next_sequence = job.current_event_sequence + 1
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._conn.execute(
            """
            UPDATE site_magic_jobs SET
                status = ?, updated_at = ?, current_event_sequence = ?,
                remediation_rounds = COALESCE(?, remediation_rounds),
                rebuild_count = COALESCE(?, rebuild_count),
                quality_summary_json = COALESCE(?, quality_summary_json),
                failure_code = COALESCE(?, failure_code)
            WHERE tenant_id = ? AND job_id = ? AND status = ? AND current_event_sequence = ?
            """,
            (
                target, now, next_sequence, remediation_rounds, rebuild_count,
                (json.dumps(quality_summary, sort_keys=True) if quality_summary is not None else None),
                failure_code, tenant_id, job_id, job.status, job.current_event_sequence,
            ),
        )
        if cursor.rowcount != 1:
            raise InvalidStateTransitionError("Site Magic job changed concurrently")

        updated = self.get_job(tenant_id=tenant_id, job_id=job_id)
        self._conn.execute(
            """
            INSERT INTO site_magic_job_events
                (event_id, job_id, tenant_id, event_sequence, prior_state, new_state,
                 payload_json, response_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, job_id, tenant_id, next_sequence, job.status, target,
                json.dumps(
                    {
                        "remediation_rounds": remediation_rounds, "rebuild_count": rebuild_count,
                        "quality_summary": quality_summary, "failure_code": failure_code,
                    },
                    sort_keys=True,
                ),
                json.dumps({"status": updated.status, "event_sequence": next_sequence}, sort_keys=True),
                now,
            ),
        )
        return updated, False

    def get_build(self, *, tenant_id: str, build_id: str) -> Optional[SiteMagicBuild]:
        row = self._conn.execute(
            """
            SELECT build_id, job_id, tenant_id, artifact_manifest_json,
                   preview_locator, published_url, created_at
            FROM site_magic_builds WHERE tenant_id = ? AND build_id = ?
            """,
            (tenant_id, build_id),
        ).fetchone()
        if row is None:
            return None
        return SiteMagicBuild(
            build_id=str(row["build_id"]), job_id=str(row["job_id"]), tenant_id=row["tenant_id"],
            artifact_manifest=_json_column(row["artifact_manifest_json"]),
            preview_locator=row["preview_locator"], published_url=row["published_url"],
            created_at=str(row["created_at"]),
        )

    def seal_build_and_advance(
        self,
        *,
        tenant_id: str,
        job_id: str,
        build_id: str,
        artifact_manifest: dict[str, Any],
        preview_locator: str,
        target: str = "ready_for_review",
        remediation_rounds: Optional[int] = None,
        rebuild_count: Optional[int] = None,
    ) -> SiteMagicJob:
        """Records the build ArtifactStore.sealPrivateImmutable() just
        produced (site_maker_engine.ts) and advances the job to
        ready_for_review in the same call -- the only place
        site_magic_builds rows and jobs.final_build_id get written from
        the actual run path (repository tests insert build rows directly
        via raw SQL as a fixture shortcut; this is the real one)."""
        job = self.get_job(tenant_id=tenant_id, job_id=job_id)
        if job is None:
            raise KeyError(job_id)
        assert_transition(job.status, target)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO site_magic_builds
                (build_id, job_id, tenant_id, artifact_manifest_json, preview_locator, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (build_id, job_id, tenant_id, json.dumps(artifact_manifest, sort_keys=True), preview_locator, now),
        )
        cursor = self._conn.execute(
            """
            UPDATE site_magic_jobs SET
                status = ?, updated_at = ?, final_build_id = ?,
                remediation_rounds = COALESCE(?, remediation_rounds),
                rebuild_count = COALESCE(?, rebuild_count)
            WHERE tenant_id = ? AND job_id = ? AND status = ?
            """,
            (target, now, build_id, remediation_rounds, rebuild_count, tenant_id, job_id, job.status),
        )
        if cursor.rowcount != 1:
            raise InvalidStateTransitionError("Site Magic job changed concurrently")
        return self.get_job(tenant_id=tenant_id, job_id=job_id)

    def publish(self, *, tenant_id: str, job_id: str, build_id: str, published_url: str) -> SiteMagicJob:
        job = self.get_job(tenant_id=tenant_id, job_id=job_id)
        if job is None or job.final_build_id != build_id:
            raise KeyError(build_id)
        assert_transition(job.status, "published")
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """UPDATE site_magic_builds SET published_url = ?
               WHERE tenant_id = ? AND build_id = ? AND job_id = ?""",
            (published_url, tenant_id, build_id, job_id),
        )
        self._conn.execute(
            """
            INSERT INTO site_magic_active_builds (tenant_id, build_id, activated_at)
            VALUES (?, ?, ?)
            ON CONFLICT (tenant_id) DO UPDATE SET
                build_id = excluded.build_id, activated_at = excluded.activated_at
            """,
            (tenant_id, build_id, now),
        )
        self._conn.execute(
            """UPDATE site_magic_jobs SET status = 'published', updated_at = ?
               WHERE tenant_id = ? AND job_id = ? AND status = 'ready_for_review'""",
            (now, tenant_id, job_id),
        )
        return self.get_job(tenant_id=tenant_id, job_id=job_id)


def log_db_failure(event: str, exc: BaseException) -> None:
    if isinstance(exc, DB_ERRORS):
        logger.error("%s error_type=%s", event, type(exc).__name__)
