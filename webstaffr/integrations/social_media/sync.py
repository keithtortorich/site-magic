"""Social media marketing sync logic.

Read-first bounded operations for mount creation and intent submission.
Follows the same pattern as the intake/attribution repositories:
repository-style helpers on an already-open connection, operating on the
SocialMediaMount/SocialMediaIntent dataclasses defined in client.py (the
canonical location -- see that module's docstring).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .client import SocialMediaMount, SocialMediaIntent


class SocialMediaSync:
    """Coordinates bounded writes for social media mounts and intents."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def mount(
        self,
        *,
        tenant_id: str,
        social_tenant_id: str,
        platforms: list[str],
        default_brand_id: Optional[str],
        mode: str,
    ) -> SocialMediaMount:
        cursor = self._conn.execute(
            """
            INSERT INTO social_media_mounts
                (tenant_id, social_tenant_id, platforms, default_brand_id, mode, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                social_tenant_id,
                json.dumps(platforms),
                default_brand_id,
                mode,
                _now_iso(),
            ),
        )
        mount_id = cursor.lastrowid
        row = self._conn.execute(
            """
            SELECT mount_id, tenant_id, social_tenant_id, platforms, default_brand_id, mode, created_at
            FROM social_media_mounts
            WHERE mount_id = ?
            """,
            (mount_id,),
        ).fetchone()
        return SocialMediaMount(
            mount_id=row["mount_id"],
            tenant_id=row["tenant_id"],
            social_tenant_id=row["social_tenant_id"],
            platforms=_parse_json_list(row["platforms"]),
            default_brand_id=row["default_brand_id"],
            mode=row["mode"],
            created_at=row["created_at"],
        )

    def create_intent(
        self,
        *,
        mount_id: int,
        campaign_intent: dict[str, Any],
        post_draft: dict[str, Any],
    ) -> SocialMediaIntent:
        cursor = self._conn.execute(
            """
            INSERT INTO social_media_intents
                (mount_id, campaign_intent, post_draft, status, workflow_instance_id, approval_url, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mount_id,
                json.dumps(campaign_intent),
                json.dumps(post_draft),
                "pending_review",
                None,
                None,
                _now_iso(),
            ),
        )
        intent_id = cursor.lastrowid
        return SocialMediaIntent(
            intent_id=intent_id,
            mount_id=mount_id,
            campaign_intent=campaign_intent,
            post_draft=post_draft,
            status="pending_review",
            workflow_instance_id=None,
            approval_url=None,
            created_at=_now_iso(),
        )

    def get_intent(self, *, intent_id: int) -> SocialMediaIntent:
        row = self._conn.execute(
            """
            SELECT intent_id, mount_id, campaign_intent, post_draft, status,
                   workflow_instance_id, approval_url, created_at
            FROM social_media_intents
            WHERE intent_id = ?
            """,
            (intent_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"social media intent {intent_id} not found")
        return SocialMediaIntent(
            intent_id=row["intent_id"],
            mount_id=row["mount_id"],
            campaign_intent=_parse_json(row["campaign_intent"]),
            post_draft=_parse_json(row["post_draft"]),
            status=row["status"],
            workflow_instance_id=row["workflow_instance_id"],
            approval_url=row["approval_url"],
            created_at=row["created_at"],
        )

    def resolve_intent(
        self,
        *,
        intent_id: int,
        status: str,
        workflow_instance_id: Optional[str],
        approval_url: Optional[str],
    ) -> SocialMediaIntent:
        self._conn.execute(
            """
            UPDATE social_media_intents
            SET status = ?, workflow_instance_id = ?, approval_url = ?
            WHERE intent_id = ?
            """,
            (status, workflow_instance_id, approval_url, intent_id),
        )
        return self.get_intent(intent_id=intent_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json(value: Optional[str]) -> Any:
    return json.loads(value) if value is not None else None


def _parse_json_list(value: Optional[str]) -> list[str]:
    parsed = _parse_json(value)
    return list(parsed) if isinstance(parsed, list) else []
