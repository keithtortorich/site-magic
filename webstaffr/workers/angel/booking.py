"""Appointment booking -- tenant-scoped, persisted via SQLite or Postgres
(appointments table, migration 0002). Separate from GHL sync: an
appointment is recorded locally first (source of truth for this system),
then optionally synced to GHL -- a GHL failure never prevents the local
booking from succeeding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ...db import DB_ERRORS, StorageError


@dataclass
class Appointment:
    tenant_id: str
    contact_name: str
    starts_at: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    source: str = "angel"
    appointment_id: Optional[int] = None
    ghl_synced: bool = False


def _normalize_starts_at(raw: str) -> str:
    """Best-effort parse of common spoken time strings into ISO-8601.

    Accepts:
    - an existing ISO-8601 timestamp with or without timezone suffix
    - ``today at 3pm`` / ``today 3pm``
    - ``3pm`` / ``3:30pm``
    - ``9am`` / ``9:00am``

    Anything we cannot parse safely falls back to the raw value rather
    than inventing a date, so callers never receive a fabricated time.
    """
    raw = raw.strip()
    lower = raw.lower()

    today = datetime.now(timezone.utc).date()
    for fmt in ("%I%p", "%I:%M%p"):
        try:
            parsed = datetime.strptime(lower, fmt)
            return datetime(
                today.year,
                today.month,
                today.day,
                parsed.hour,
                parsed.minute,
                tzinfo=timezone.utc,
            ).isoformat()
        except ValueError:
            pass

    prefixes = ("today at ", "today ")
    for prefix in prefixes:
        if lower.startswith(prefix):
            remainder = lower[len(prefix):]
            for fmt in ("%I%p", "%I:%M%p"):
                try:
                    parsed = datetime.strptime(remainder, fmt)
                    return datetime(
                        today.year,
                        today.month,
                        today.day,
                        parsed.hour,
                        parsed.minute,
                        tzinfo=timezone.utc,
                    ).isoformat()
                except ValueError:
                    pass

    return raw


class AppointmentRepository:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def save(self, appt: Appointment) -> int:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", (appt.tenant_id,)
            )
            cursor = self._conn.execute(
                """
                INSERT INTO appointments
                    (tenant_id, contact_name, contact_phone, contact_email, starts_at,
                     notes, source, ghl_synced, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appt.tenant_id,
                    appt.contact_name,
                    appt.contact_phone,
                    appt.contact_email,
                    appt.starts_at,
                    appt.notes,
                    appt.source,
                    int(appt.ghl_synced),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except DB_ERRORS as exc:
            raise StorageError(
                f"Failed to save appointment for tenant {appt.tenant_id!r}: {exc}"
            ) from exc
        appt.appointment_id = cursor.lastrowid
        return appt.appointment_id

    def mark_ghl_synced(self, tenant_id: str, appointment_id: int) -> None:
        try:
            self._conn.execute(
                "UPDATE appointments SET ghl_synced = 1 WHERE tenant_id = ? AND appointment_id = ?",
                (tenant_id, appointment_id),
            )
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to mark appointment {appointment_id} synced: {exc}") from exc

    def list_for_tenant(self, tenant_id: str) -> list:
        try:
            rows = self._conn.execute(
                "SELECT appointment_id FROM appointments WHERE tenant_id = ? ORDER BY appointment_id",
                (tenant_id,),
            ).fetchall()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to list appointments for tenant {tenant_id!r}: {exc}") from exc
        return [row["appointment_id"] for row in rows]
