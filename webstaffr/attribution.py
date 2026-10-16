"""Per-tenant call attribution: tracking numbers, call-lifecycle events, and
the metrics rollup a customer-facing ROI dashboard reads from.

Exists to unblock the "pays for itself" guarantee conversation -- without
a record of what actually happened on a tenant's calls, there's no way to
back that claim with anything other than a promise.

Follows the same repository pattern as intake.py/booking.py: plain
dataclasses plus a repository class operating on an already-open
connection (SQLite or Postgres -- see db.get_connection), tenant-scoped
throughout. No new persistence pattern, no ORM.

Perfect-site principle applies here too: metrics are computed only from
real logged events. There is no synthetic/placeholder call data -- a
tenant with zero calls sees zero, not a fabricated number to look
impressive.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .db import DB_ERRORS, StorageError

VALID_EVENT_TYPES = {"call_received", "call_ended", "appointment_booked"}

# [Inference] Placeholder estimated value per booked appointment, used only
# for the dashboard's "estimated value" figure until real per-tenant job
# values exist (e.g. from GHL or ServiceTitan). Deliberately conservative
# and clearly labeled in the API response as an estimate, not a measured
# figure. Tune once real per-tenant job values exist.
ESTIMATED_VALUE_PER_APPOINTMENT = 250.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_tracking_number(tenant_id: str) -> str:
    """A logical tracking identifier, not a real phone number -- no Twilio/
    Retell number-provisioning integration exists yet (see the 0006
    migration's docstring). Shaped as a short, greppable token rather than
    a fake phone-number-looking string, so it's never confused with a real
    DID once one is actually provisioned and this value is updated in
    place."""
    return f"trk_{tenant_id}_{uuid.uuid4().hex[:8]}"


@dataclass
class TrackingNumber:
    tenant_id: str
    tracking_number: str
    created_at: str


@dataclass
class CallEvent:
    tenant_id: str
    event_type: str
    tracking_number: Optional[str] = None
    call_id: Optional[str] = None
    duration_seconds: Optional[int] = None
    outcome: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[str] = None
    event_id: Optional[int] = None


class AttributionValidationError(ValueError):
    """Raised for a malformed call event (bad event_type). Router turns
    this into a 400, same pattern as IntakeValidationError."""


class TrackingNumberRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def get_or_create(self, tenant_id: str) -> TrackingNumber:
        """Idempotent: returns the existing tracking number for this tenant
        if one exists, otherwise creates one. Called from intake_router.py
        right after a tenant's first successful intake submission, so in
        practice every tenant gets one exactly once -- but this stays safe
        to call repeatedly (e.g. a retry) without creating duplicates."""
        existing = self.get_for_tenant(tenant_id)
        if existing is not None:
            return existing

        tracking_number = generate_tracking_number(tenant_id)
        created_at = _now_iso()
        try:
            self._conn.execute(
                """
                INSERT INTO tracking_numbers (tenant_id, tracking_number, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (tenant_id, tracking_number, created_at),
            )
        except DB_ERRORS as exc:
            raise StorageError(f"failed to create tracking number for {tenant_id!r}") from exc

        # Re-read rather than trust the just-built row: a concurrent call
        # for the same tenant_id may have won the INSERT ... DO NOTHING
        # race, in which case the real row differs from what this call
        # just attempted to write.
        row = self.get_for_tenant(tenant_id)
        if row is None:
            raise StorageError(f"tracking number for {tenant_id!r} not found after insert")
        return row

    def get_for_tenant(self, tenant_id: str) -> Optional[TrackingNumber]:
        row = self._conn.execute(
            "SELECT tenant_id, tracking_number, created_at FROM tracking_numbers WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        if row is None:
            return None
        return TrackingNumber(
            tenant_id=row["tenant_id"],
            tracking_number=row["tracking_number"],
            created_at=row["created_at"],
        )


class CallEventRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def log_event(self, event: CallEvent) -> CallEvent:
        if event.event_type not in VALID_EVENT_TYPES:
            raise AttributionValidationError(
                f"invalid event_type {event.event_type!r}, must be one of {sorted(VALID_EVENT_TYPES)}"
            )

        created_at = event.created_at or _now_iso()
        metadata_json = json.dumps(event.metadata) if event.metadata is not None else None

        try:
            cursor = self._conn.execute(
                """
                INSERT INTO call_events
                    (tenant_id, tracking_number, call_id, event_type, duration_seconds, outcome, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.tenant_id,
                    event.tracking_number,
                    event.call_id,
                    event.event_type,
                    event.duration_seconds,
                    event.outcome,
                    metadata_json,
                    created_at,
                ),
            )
        except DB_ERRORS as exc:
            raise StorageError(f"failed to log call event for {event.tenant_id!r}") from exc

        event.event_id = cursor.lastrowid
        event.created_at = created_at
        return event

    def list_for_tenant(self, tenant_id: str, limit: int = 50) -> list[CallEvent]:
        rows = self._conn.execute(
            """
            SELECT event_id, tenant_id, tracking_number, call_id, event_type,
                   duration_seconds, outcome, metadata_json, created_at
            FROM call_events
            WHERE tenant_id = ?
            ORDER BY created_at DESC, event_id DESC
            LIMIT ?
            """,
            (tenant_id, limit),
        ).fetchall()
        return [_row_to_event(row) for row in rows]

    def metrics_for_tenant(self, tenant_id: str) -> dict:
        """Aggregate counts driving the dashboard's headline figures.
        Deliberately simple SUM/COUNT queries, not a materialized rollup
        table -- call volume at MVP/soft-launch scale doesn't justify that
        complexity yet (same "revisit at real volume" posture as
        rate_limit.py's unpruned counters)."""
        calls_received = self._count(tenant_id, "call_received")
        calls_ended = self._count(tenant_id, "call_ended")
        appointments_booked = self._count(tenant_id, "appointment_booked")

        return {
            "tenant_id": tenant_id,
            "calls_received": calls_received,
            "calls_completed": calls_ended,
            "appointments_booked": appointments_booked,
            "estimated_value_usd": round(appointments_booked * ESTIMATED_VALUE_PER_APPOINTMENT, 2),
            "estimated_value_note": (
                f"Estimate only, at ${ESTIMATED_VALUE_PER_APPOINTMENT:.0f}/booked appointment "
                "-- not a measured figure."
            ),
        }

    def _count(self, tenant_id: str, event_type: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM call_events WHERE tenant_id = ? AND event_type = ?",
            (tenant_id, event_type),
        ).fetchone()
        return int(row["n"]) if row is not None else 0


def _row_to_event(row: Any) -> CallEvent:
    metadata_json = row["metadata_json"]
    return CallEvent(
        event_id=row["event_id"],
        tenant_id=row["tenant_id"],
        tracking_number=row["tracking_number"],
        call_id=row["call_id"],
        event_type=row["event_type"],
        duration_seconds=row["duration_seconds"],
        outcome=row["outcome"],
        metadata=json.loads(metadata_json) if metadata_json else None,
        created_at=row["created_at"],
    )
