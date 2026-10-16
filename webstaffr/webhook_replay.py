"""Transactional webhook idempotency backed by shared application storage."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Optional

REPLAY_RETENTION_SECONDS = 7 * 24 * 60 * 60


@dataclass(frozen=True)
class DeliveryClaim:
    is_new: bool
    response_json: Optional[str] = None


def payload_digest(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def claim_delivery(
    conn: Any,
    *,
    provider: str,
    event_key: str,
    event_type: str,
    raw_body: bytes,
    tenant_id: Optional[str] = None,
) -> DeliveryClaim:
    """Atomically claim a delivery inside the caller's business transaction."""
    now_epoch = int(time.time())
    conn.execute(
        "DELETE FROM webhook_deliveries WHERE created_epoch < ?",
        (now_epoch - REPLAY_RETENTION_SECONDS,),
    )
    cursor = conn.execute(
        """
        INSERT INTO webhook_deliveries
            (provider, event_key, tenant_id, event_type, payload_sha256, status, created_epoch)
        VALUES (?, ?, ?, ?, ?, 'processing', ?)
        ON CONFLICT (provider, event_key) DO NOTHING
        """,
        (provider, event_key, tenant_id, event_type, payload_digest(raw_body), now_epoch),
    )
    inserted = getattr(cursor, "rowcount", None)
    if inserted is None:
        inserted = conn.execute("SELECT changes() AS count").fetchone()["count"]
    if inserted:
        return DeliveryClaim(is_new=True)

    row = conn.execute(
        "SELECT response_json FROM webhook_deliveries WHERE provider = ? AND event_key = ?",
        (provider, event_key),
    ).fetchone()
    return DeliveryClaim(is_new=False, response_json=row["response_json"] if row else None)


def complete_delivery(conn: Any, *, provider: str, event_key: str, response_json: str) -> None:
    conn.execute(
        """
        UPDATE webhook_deliveries
        SET status = 'processed', response_json = ?, processed_at = CURRENT_TIMESTAMP
        WHERE provider = ? AND event_key = ?
        """,
        (response_json, provider, event_key),
    )
