"""Focused smoke tests for the social media integration bridge."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webstaffr.app import create_app
from webstaffr.workers.angel.api_auth import NullSharedSecretVerifier
from webstaffr.integrations.social_media.client import (
    SocialMediaConfigError,
    SocialMediaHTTPError,
)
from webstaffr.integrations.social_media.mocks import MockSocialMediaClient
from webstaffr.integrations.social_media.sync import SocialMediaSync
import sqlite3


def test_social_media_client_exports() -> None:
    assert MockSocialMediaClient is not None
    assert SocialMediaSync is not None
    assert SocialMediaHTTPError is SocialMediaConfigError is not None


def test_mock_client_round_trip() -> None:
    client = MockSocialMediaClient()
    mount = client.mount(
        tenant_id="tenant-1",
        social_tenant_id="org-1",
        platforms=["meta"],
        default_brand_id="brand-1",
        mode="agent_managed",
    )
    intent = client.create_intent(
        mount_id=mount.mount_id,
        campaign_intent={"objective": "bookings"},
        post_draft={"headline": "test"},
    )
    assert intent.status == "pending_review"
    assert intent.workflow_instance_id is None
    assert len(client.calls) == 2


def _all_route_paths(routes) -> list[str]:
    """Recursively collect every path FastAPI actually serves.

    FastAPI wraps each include_router() call in an internal
    `_IncludedRouter` object whose real routes live on
    `.original_router.routes`, not a flat `.routes`/`.path` on the wrapper
    itself (confirmed against fastapi==0.139.2, the version pinned in
    requirements.txt -- this differs across FastAPI versions, which is
    exactly why the previous version of this test silently found zero
    routes and looked like a registration bug when it was actually a
    stale assumption about FastAPI's internal route representation)."""
    found: list[str] = []
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            found.append(path)
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            found.extend(_all_route_paths(original_router.routes))
    return found


def test_social_media_routes_are_registered() -> None:
    app = create_app()
    social_paths = [p for p in _all_route_paths(app.routes) if "/integrations/social-media" in p]
    assert "/integrations/social-media/mount" in social_paths
    assert any(
        path.startswith("/integrations/social-media/mount/") and "/intent" in path
        for path in social_paths
    )


from fastapi.testclient import TestClient


def test_mount_endpoint_returns_mount() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = create_app(
            db_path=str(Path(tmp_dir) / "app.db"),
            internal_api_verifier=NullSharedSecretVerifier(),
        )
        with TestClient(app) as http:
            response = http.post(
                "/integrations/social-media/mount",
                json={
                    "tenant_id": "tenant-1",
                    "social_tenant_id": "org-1",
                    "platforms": ["meta"],
                    "default_brand_id": "brand-1",
                    "mode": "agent_managed",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["tenant_id"] == "tenant-1"
            assert data["social_tenant_id"] == "org-1"
            assert data["platforms"] == ["meta"]
            assert data["default_brand_id"] == "brand-1"
            assert data["mode"] == "agent_managed"
            assert data["mount_id"] == 1
            assert "created_at" in data


def test_intent_endpoint_returns_pending_review() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        app = create_app(
            db_path=str(Path(tmp_dir) / "app.db"),
            internal_api_verifier=NullSharedSecretVerifier(),
        )
        with TestClient(app) as http:
            mount = http.post(
                "/integrations/social-media/mount",
                json={
                    "tenant_id": "tenant-1",
                    "social_tenant_id": "org-1",
                    "platforms": ["meta"],
                    "default_brand_id": "brand-1",
                    "mode": "agent_managed",
                },
            )
            assert mount.status_code == 200
            intent = http.post(
                "/integrations/social-media/mount/1/intent",
                json={
                    "campaign_intent": {"objective": "bookings"},
                    "post_draft": {"headline": "test"},
                },
            )
            assert intent.status_code == 200
            data = intent.json()
            assert data["status"] == "pending_review"
            assert data["workflow_instance_id"] == "wf_1"
            assert data["approval_url"] == "/approvals/wf_1"


def test_social_media_routes_default_to_closed() -> None:
    app = create_app()
    with TestClient(app) as http:
        response = http.post(
            "/integrations/social-media/mount",
            json={
                "tenant_id": "tenant-1",
                "social_tenant_id": "org-1",
                "platforms": ["meta"],
            },
        )
    assert response.status_code == 401



def test_sqlite_sync_round_trip() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        (ROOT / "webstaffr" / "migrations" / "0006_social_media.sql").read_text()
    )
    conn.commit()
    sync = SocialMediaSync(conn)
    mount = sync.mount(
        tenant_id="tenant-1",
        social_tenant_id="org-1",
        platforms=["meta"],
        default_brand_id="brand-1",
        mode="agent_managed",
    )
    intent = sync.create_intent(
        mount_id=mount.mount_id,
        campaign_intent={"objective": "bookings"},
        post_draft={"headline": "test"},
    )
    assert mount.mount_id == 1
    assert intent.intent_id == 1
    assert intent.status == "pending_review"
    resolved = sync.resolve_intent(
        intent_id=intent.intent_id,
        status="approved",
        workflow_instance_id="wf_1",
        approval_url="/approvals/wf_1",
    )
    assert resolved.status == "approved"
