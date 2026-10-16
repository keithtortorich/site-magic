"""Social media client mock for offline tests and local development."""
from __future__ import annotations

from typing import Any, Optional

from .client import SocialMediaHTTPError, SocialMediaMount, SocialMediaIntent


class MockSocialMediaClient:
    """Deterministic, credential-free fake social media client."""

    def __init__(self, *, mounts: Optional[dict[str, list[SocialMediaMount]]] = None, intents: Optional[dict[str, list[SocialMediaIntent]]] = None, fail: Optional[str] = None) -> None:
        self.mounts = mounts or {}
        self.intents = intents or {}
        self.fail = fail
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def mount(self, tenant_id: str, social_tenant_id: str, platforms: list[str], default_brand_id: Optional[str], mode: str) -> SocialMediaMount:
        self.calls.append(("mount", (tenant_id, social_tenant_id, tuple(platforms), default_brand_id, mode), {}))
        if self.fail == "mount":
            raise SocialMediaHTTPError("forced mount failure")
        key = tenant_id
        existing = self.mounts.get(key) or []
        mount = SocialMediaMount(
            mount_id=len(existing) + 1,
            tenant_id=tenant_id,
            social_tenant_id=social_tenant_id,
            platforms=platforms,
            default_brand_id=default_brand_id,
            mode=mode,
            created_at="2026-07-24T00:00:00+00:00",
        )
        existing.append(mount)
        self.mounts[key] = existing
        return mount

    def create_intent(self, mount_id: int, campaign_intent: dict[str, Any], post_draft: dict[str, Any]) -> SocialMediaIntent:
        self.calls.append(("create_intent", (mount_id, campaign_intent, post_draft), {}))
        if self.fail == "create_intent":
            raise SocialMediaHTTPError("forced intent failure")
        key = str(mount_id)
        existing = self.intents.get(key) or []
        intent = SocialMediaIntent(
            intent_id=len(existing) + 1,
            mount_id=mount_id,
            campaign_intent=campaign_intent,
            post_draft=post_draft,
            status="pending_review",
            workflow_instance_id=None,
            approval_url=None,
            created_at="2026-07-24T00:00:00+00:00",
        )
        existing.append(intent)
        self.intents[key] = existing
        return intent

    def get_intent(self, intent_id: int) -> SocialMediaIntent:
        self.calls.append(("get_intent", (intent_id,), {}))
        if self.fail == "get_intent":
            raise SocialMediaHTTPError("forced get intent failure")
        for intents in self.intents.values():
            for intent in intents:
                if intent.intent_id == intent_id:
                    return intent
        raise ValueError(f"social media intent {intent_id} not found")
