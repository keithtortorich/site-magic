import os
import base64
import json
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.customer_auth import (
    DenyAllIdentityVerifier,
    SupabaseIdentityVerifier,
    VerifiedIdentity,
    identity_verifier_from_env,
)
from webstaffr.db import connect


class StaticIdentityVerifier:
    def __init__(self, identity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "valid-token" else None


def _unsigned_token(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


class TestSupabaseIdentityVerifier:
    def test_accepts_only_matching_unexpired_verified_identity(self):
        user_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        token = _unsigned_token({
            "sub": user_id,
            "session_id": session_id,
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        })
        response = Mock(status_code=200)
        response.json.return_value = {"id": user_id}
        with patch("webstaffr.customer_auth.httpx.get", return_value=response) as get:
            identity = SupabaseIdentityVerifier("https://project.supabase.co", "publishable").verify(token)
        assert identity.user_id == user_id
        assert identity.session_id == session_id
        assert get.call_args.kwargs["headers"]["Authorization"] == f"Bearer {token}"

    def test_rejects_identity_mismatch_after_provider_success(self):
        token = _unsigned_token({
            "sub": str(uuid.uuid4()),
            "session_id": str(uuid.uuid4()),
            "exp": int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()),
        })
        response = Mock(status_code=200)
        response.json.return_value = {"id": str(uuid.uuid4())}
        with patch("webstaffr.customer_auth.httpx.get", return_value=response):
            assert SupabaseIdentityVerifier("https://project.supabase.co", "publishable").verify(token) is None

    def test_rejects_expired_token_and_provider_rejection(self):
        user_id = str(uuid.uuid4())
        expired = _unsigned_token({
            "sub": user_id,
            "session_id": str(uuid.uuid4()),
            "exp": int((datetime.now(timezone.utc) - timedelta(seconds=1)).timestamp()),
        })
        response = Mock(status_code=200)
        response.json.return_value = {"id": user_id}
        with patch("webstaffr.customer_auth.httpx.get", return_value=response):
            assert SupabaseIdentityVerifier("https://project.supabase.co", "publishable").verify(expired) is None
        with patch("webstaffr.customer_auth.httpx.get", return_value=Mock(status_code=401)):
            assert SupabaseIdentityVerifier("https://project.supabase.co", "publishable").verify(expired) is None

    def test_missing_environment_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            assert isinstance(identity_verifier_from_env(), DenyAllIdentityVerifier)

    def test_private_cors_wildcard_configuration_is_rejected(self):
        with patch.dict(os.environ, {"CUSTOMER_ALLOWED_ORIGINS": "*"}):
            with pytest.raises(ValueError, match="exact http\\(s\\) origins"):
                create_app()


class TestCustomerAuthorization:
    def setup_method(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.user_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.identity = VerifiedIdentity(
            user_id=self.user_id,
            session_id=self.session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        app = create_app(
            db_path=self.db_path,
            customer_identity_verifier=StaticIdentityVerifier(self.identity),
            customer_allowed_origins={"https://dashboard.example"},
        )
        self.client = TestClient(app)
        self.client.__enter__()
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('tenant_a')")
            conn.execute("INSERT INTO tenants (tenant_id) VALUES ('tenant_b')")
            conn.execute(
                "INSERT INTO customer_users (user_id) VALUES (?)", (self.user_id,)
            )

    def teardown_method(self):
        self.client.__exit__(None, None, None)
        os.remove(self.db_path)

    @staticmethod
    def headers(**extra):
        return {"Authorization": "Bearer valid-token", **extra}

    def start_session(self):
        response = self.client.post("/auth/session", headers=self.headers())
        assert response.status_code == 200

    def add_membership(self, tenant_id="tenant_a", role="viewer", status="active"):
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
                VALUES (?, ?, ?, ?)
                """,
                (tenant_id, self.user_id, role, status),
            )

    def test_missing_or_bad_bearer_token_is_401(self):
        assert self.client.get("/tenants/tenant_a/metrics").status_code == 401
        assert self.client.get(
            "/tenants/tenant_a/metrics", headers={"Authorization": "Bearer bad"}
        ).status_code == 401

    def test_verified_identity_requires_registered_session(self):
        self.add_membership()
        response = self.client.get("/tenants/tenant_a/metrics", headers=self.headers())
        assert response.status_code == 401

    def test_active_viewer_can_read_and_generates_redacted_audit(self):
        self.start_session()
        self.add_membership()
        correlation_id = str(uuid.uuid4())
        response = self.client.get(
            "/tenants/tenant_a/metrics",
            headers=self.headers(**{"X-Correlation-ID": correlation_id}),
        )
        assert response.status_code == 200
        with connect(self.db_path) as conn:
            event = conn.execute("SELECT * FROM customer_audit_events").fetchone()
        assert event["correlation_id"] == correlation_id
        assert event["tenant_id"] == "tenant_a"
        assert event["action"] == "metrics.read"
        assert "valid-token" not in str(dict(event))

    def test_membership_cannot_cross_tenants(self):
        self.start_session()
        self.add_membership("tenant_a", "owner")
        response = self.client.get("/tenants/tenant_b/metrics", headers=self.headers())
        assert response.status_code == 403
        with connect(self.db_path) as conn:
            event = conn.execute(
                "SELECT outcome, reason_code FROM customer_audit_events"
            ).fetchone()
        assert event["outcome"] == "denied"
        assert event["reason_code"] == "insufficient_membership"

    def test_suspended_membership_is_denied(self):
        self.start_session()
        self.add_membership(status="suspended")
        response = self.client.get("/tenants/tenant_a/metrics", headers=self.headers())
        assert response.status_code == 403

    def test_logout_revokes_session_immediately(self):
        self.start_session()
        self.add_membership()
        assert self.client.post("/auth/logout", headers=self.headers()).status_code == 200
        response = self.client.get("/tenants/tenant_a/metrics", headers=self.headers())
        assert response.status_code == 401

    def test_expired_local_session_is_denied(self):
        self.start_session()
        self.add_membership()
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE customer_sessions SET expires_at = ? WHERE session_id = ?",
                ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), self.session_id),
            )
        response = self.client.get("/tenants/tenant_a/metrics", headers=self.headers())
        assert response.status_code == 401

    def test_disabled_user_cannot_start_session(self):
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE customer_users SET status = 'disabled' WHERE user_id = ?",
                (self.user_id,),
            )
        response = self.client.post("/auth/session", headers=self.headers())
        assert response.status_code == 403

    def test_auth_routes_are_cors_scoped(self):
        response = self.client.options(
            "/auth/session",
            headers={"Origin": "https://dashboard.example"},
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://dashboard.example"
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_auth_routes_reject_unlisted_cross_origin(self):
        response = self.client.options(
            "/auth/session",
            headers={"Origin": "https://attacker.example"},
        )
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers
