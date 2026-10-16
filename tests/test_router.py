import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from webstaffr.workers.angel.api_auth import NullSharedSecretVerifier, StaticSecretVerifier
from webstaffr.workers.angel.ghl import NullGHLClient
from webstaffr.app import create_app
from webstaffr.workers.angel.voice import NullVoiceBackend


class RouterTestCase(unittest.TestCase):
    """Uses a real temp-file SQLite DB rather than ':memory:' -- each
    sqlite3.connect(':memory:') call opens an independent, empty database,
    which would hide the startup migration from the router's per-request
    connections. A temp file behaves like the real deployment (one file,
    many connections)."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.ghl = NullGHLClient()
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=self.ghl,
            book_api_verifier=NullSharedSecretVerifier(),
            ghl_webhook_verifier=NullSharedSecretVerifier(),
        )
        # Enter the TestClient as a context manager so the app's ASGI
        # lifespan (startup -> migrate()) actually fires. TestClient(app)
        # without __enter__ does not reliably run lifespan events, which
        # is exactly the gap that let a "no such table" bug slip past
        # every endpoint that never happened to touch a table.
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestHealthEndpoint(RouterTestCase):
    def test_health_ok(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_health_reports_vercel_release_when_available(self):
        with patch.dict(os.environ, {"VERCEL_GIT_COMMIT_SHA": "abc123"}):
            resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok", "release": "abc123"})

    def test_health_has_no_cors_header(self):
        resp = self.client.get("/health", headers={"Origin": "https://evil.example.com"})
        self.assertNotIn("access-control-allow-origin", resp.headers)


class TestCORSScoping(RouterTestCase):
    """CORS is scoped to /chat only -- angel-widget.js is the only caller
    that needs cross-origin access from an arbitrary customer-site origin.
    /book and /webhooks/ghl must NOT carry CORS headers: see the CLAUDE.md
    session addendum (2026-07-05) documenting the app-wide wildcard this
    replaced."""

    def test_chat_has_cors_header_for_arbitrary_origin(self):
        resp = self.client.post(
            "/chat",
            json={"tenant_id": "acme", "message": "Hi"},
            headers={"Origin": "https://some-customer-site.example.com"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")

    def test_book_has_no_cors_header(self):
        resp = self.client.post(
            "/book",
            json={"tenant_id": "acme", "contact_name": "Jane", "starts_at": "2026-08-01T15:00:00Z"},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)

    def test_webhooks_ghl_has_no_cors_header(self):
        resp = self.client.post(
            "/webhooks/ghl",
            json={"tenant_id": "acme", "event_type": "missed_call"},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)


class TestChatEndpoint(RouterTestCase):
    def test_chat_returns_a_reply(self):
        resp = self.client.post("/chat", json={"tenant_id": "acme", "message": "Hi there"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("reply", resp.json())
        self.assertTrue(len(resp.json()["reply"]) > 0)

    def test_chat_rejects_invalid_tenant_id(self):
        resp = self.client.post("/chat", json={"tenant_id": "", "message": "Hi there"})
        self.assertEqual(resp.status_code, 400)

    def test_chat_rejects_oversized_message(self):
        """ChatRequest.message previously had no length limit at all -- a
        real, billed cost once GROK_API_KEY is live. Pydantic's
        Field(max_length=...) rejects this before it ever reaches
        Angel/Grok, hence 422 (validation error) rather than 400 (this
        router's own hand-rolled rejections)."""
        resp = self.client.post(
            "/chat",
            json={"tenant_id": "acme", "message": "x" * 4001},
        )
        self.assertEqual(resp.status_code, 422)

    def test_chat_accepts_message_at_the_length_limit(self):
        resp = self.client.post(
            "/chat",
            json={"tenant_id": "acme", "message": "x" * 4000},
        )
        self.assertEqual(resp.status_code, 200)

    def test_chat_is_rate_limited_per_tenant(self):
        """Confirms the rate_limit.py wiring end to end, not just the
        module in isolation (see test_rate_limit.py for the
        boundary-condition coverage) -- uses the real
        DEFAULT_MAX_REQUESTS_PER_WINDOW (30) rather than injecting a lower
        one, since create_app() doesn't expose that as a param and
        shouldn't need to for this to be testable."""
        for _ in range(30):
            resp = self.client.post("/chat", json={"tenant_id": "rate-limited-tenant", "message": "hi"})
            self.assertEqual(resp.status_code, 200)

        resp = self.client.post("/chat", json={"tenant_id": "rate-limited-tenant", "message": "hi"})
        self.assertEqual(resp.status_code, 429)

        # A different tenant is unaffected.
        resp = self.client.post("/chat", json={"tenant_id": "another-tenant", "message": "hi"})
        self.assertEqual(resp.status_code, 200)


class TestBookEndpoint(RouterTestCase):
    def test_book_creates_appointment_without_ghl_sync(self):
        resp = self.client.post(
            "/book",
            json={
                "tenant_id": "acme",
                "contact_name": "Jane Doe",
                "starts_at": "2026-08-01T15:00:00Z",
                "contact_phone": "555-1234",
                "sync_to_ghl": False,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body["appointment_id"], int)
        self.assertEqual(body["tenant_id"], "acme")
        self.assertEqual(body["contact_name"], "Jane Doe")
        self.assertFalse(body["ghl_synced"])

    def test_book_syncs_to_ghl_when_requested(self):
        resp = self.client.post(
            "/book",
            json={
                "tenant_id": "acme",
                "contact_name": "Jane Doe",
                "starts_at": "2026-08-01T15:00:00Z",
                "sync_to_ghl": True,
                "ghl_contact_id": "ghl_contact_123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ghl_synced"])
        self.assertEqual(len(self.ghl.created_appointments), 1)

    def test_book_rejects_invalid_tenant_id(self):
        resp = self.client.post(
            "/book",
            json={"tenant_id": "bad id with spaces", "contact_name": "Jane", "starts_at": "2026-08-01T15:00:00Z"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_book_rejects_empty_contact_name(self):
        resp = self.client.post(
            "/book",
            json={"tenant_id": "acme", "contact_name": "   ", "starts_at": "2026-08-01T15:00:00Z"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_book_rejects_empty_starts_at(self):
        resp = self.client.post(
            "/book",
            json={"tenant_id": "acme", "contact_name": "Jane", "starts_at": ""},
        )
        self.assertEqual(resp.status_code, 400)


class TestGHLWebhookEndpoint(RouterTestCase):
    def test_website_lead_event_is_handled(self):
        resp = self.client.post(
            "/webhooks/ghl",
            json={
                "tenant_id": "acme",
                "event_type": "website_lead",
                "contact_id": "c1",
                "contact_name": "Jane Doe",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "handled")

    def test_missed_call_event_is_handled(self):
        resp = self.client.post(
            "/webhooks/ghl",
            json={"tenant_id": "acme", "event_type": "missed_call", "contact_id": "c1"},
        )
        self.assertEqual(resp.status_code, 200)

    def test_exact_duplicate_is_acknowledged_without_reprocessing(self):
        payload = {"tenant_id": "acme", "event_type": "missed_call", "contact_id": "dup-1"}
        first = self.client.post("/webhooks/ghl", json=payload)
        second = self.client.post("/webhooks/ghl", json=payload)
        self.assertEqual(first.json()["status"], "handled")
        self.assertEqual(second.json(), {"status": "duplicate"})

    def test_unsupported_event_type_is_rejected(self):
        resp = self.client.post(
            "/webhooks/ghl",
            json={"tenant_id": "acme", "event_type": "not_a_real_event"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_tenant_id_is_rejected(self):
        resp = self.client.post(
            "/webhooks/ghl",
            json={"tenant_id": "bad id with spaces", "event_type": "website_lead"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_oversized_message_is_rejected(self):
        """Same unbounded-message finding as ChatRequest --
        GHLWebhookEvent.message was also unbounded."""
        resp = self.client.post(
            "/webhooks/ghl",
            json={"tenant_id": "acme", "event_type": "website_lead", "message": "x" * 4001},
        )
        self.assertEqual(resp.status_code, 422)

    def test_webhook_is_rate_limited_per_tenant(self):
        """Same wiring as TestChatEndpoint.test_chat_is_rate_limited_per_tenant,
        tracked separately from /chat's counter (different endpoint tag)."""
        for _ in range(30):
            resp = self.client.post(
                "/webhooks/ghl", json={"tenant_id": "rate-limited-tenant", "event_type": "missed_call"}
            )
            self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            "/webhooks/ghl", json={"tenant_id": "rate-limited-tenant", "event_type": "missed_call"}
        )
        self.assertEqual(resp.status_code, 429)


class TestBookApiKeyAuth(unittest.TestCase):
    """Separate app instance (not RouterTestCase) so a real
    StaticSecretVerifier can be injected via dependency injection -- same
    approach test_retell_router.py uses for RetellSignatureVerifier. Covers
    the fix for /book previously accepting any caller that knew a
    tenant_id."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=NullGHLClient(),
            book_api_verifier=StaticSecretVerifier("test-book-key"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _payload(self):
        return {"tenant_id": "acme", "contact_name": "Jane", "starts_at": "2026-08-01T15:00:00Z"}

    def test_rejects_missing_api_key(self):
        resp = self.client.post("/book", json=self._payload())
        self.assertEqual(resp.status_code, 401)

    def test_rejects_wrong_api_key(self):
        resp = self.client.post("/book", json=self._payload(), headers={"X-API-Key": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_accepts_correct_api_key(self):
        resp = self.client.post("/book", json=self._payload(), headers={"X-API-Key": "test-book-key"})
        self.assertEqual(resp.status_code, 200)


class TestGHLWebhookSecretAuth(unittest.TestCase):
    """Same shape as TestBookApiKeyAuth, for /webhooks/ghl -- covers the
    fix for a forgeable webhook with no shared-secret check."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=NullGHLClient(),
            ghl_webhook_verifier=StaticSecretVerifier("test-ghl-secret"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _payload(self):
        return {"tenant_id": "acme", "event_type": "missed_call"}

    def test_rejects_missing_secret(self):
        resp = self.client.post("/webhooks/ghl", json=self._payload())
        self.assertEqual(resp.status_code, 401)

    def test_rejects_wrong_secret(self):
        resp = self.client.post("/webhooks/ghl", json=self._payload(), headers={"X-Webhook-Secret": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_accepts_correct_secret(self):
        resp = self.client.post(
            "/webhooks/ghl", json=self._payload(), headers={"X-Webhook-Secret": "test-ghl-secret"}
        )
        self.assertEqual(resp.status_code, 200)


class TestBookAndWebhookAuthDefaultsToClosedWhenUnconfigured(unittest.TestCase):
    """Production construction denies access when credentials are absent."""

    def setUp(self):
        self._old_ghl_secret = os.environ.pop("GHL_WEBHOOK_SECRET", None)
        self._old_book_key = os.environ.pop("BOOK_API_KEY", None)
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._client_ctx = TestClient(create_app(db_path=self.db_path))
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)
        if self._old_ghl_secret is not None:
            os.environ["GHL_WEBHOOK_SECRET"] = self._old_ghl_secret
        if self._old_book_key is not None:
            os.environ["BOOK_API_KEY"] = self._old_book_key

    def test_book_rejects_missing_api_key_when_unconfigured(self):
        resp = self.client.post(
            "/book",
            json={"tenant_id": "acme", "contact_name": "Jane", "starts_at": "2026-08-01T15:00:00Z"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_webhook_rejects_missing_secret_when_unconfigured(self):
        resp = self.client.post("/webhooks/ghl", json={"tenant_id": "acme", "event_type": "missed_call"})
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
