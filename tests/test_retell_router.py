import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from webstaffr.workers.angel.ghl import NullGHLClient
from webstaffr.workers.angel.retell import NullRetellWebhookVerifier, RetellSignatureVerifier
from webstaffr.app import create_app
from webstaffr.workers.angel.voice import NullVoiceBackend


class RetellRouterTestCase(unittest.TestCase):
    """Same shape as RouterTestCase in test_router.py -- a real temp-file
    SQLite DB so the startup migration is visible to per-request
    connections, entered as a context manager so the ASGI lifespan
    actually fires."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.ghl = NullGHLClient()
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=self.ghl,
            retell_verifier=NullRetellWebhookVerifier(),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestRetellNoCORS(RetellRouterTestCase):
    """/retell/* is server-to-server (Retell calling this app, never a
    browser) -- must not carry CORS headers, same as /book and
    /webhooks/ghl. See ScopedCORSMiddleware in router.py."""

    def test_webhook_has_no_cors_header(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_started", "call": {"call_id": "c1", "metadata": {"tenant_id": "acme"}}},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)

    def test_function_call_has_no_cors_header(self):
        resp = self.client.post(
            "/retell/function-call",
            json={"name": "get_availability", "args": {}, "call": {"metadata": {"tenant_id": "acme"}}},
            headers={"Origin": "https://evil.example.com"},
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)


class TestCallLifecycleWebhook(RetellRouterTestCase):
    def test_call_started_is_acknowledged(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_started", "call": {"call_id": "c1", "metadata": {"tenant_id": "acme"}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "received")

    def test_missing_tenant_id_is_ignored_not_rejected(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_started", "call": {"call_id": "c1"}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")

    def test_invalid_tenant_id_is_ignored_not_rejected(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_started", "call": {"call_id": "c1", "metadata": {"tenant_id": "bad id with spaces"}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")

    def test_call_ended_logs_ghl_note_when_summary_and_contact_present(self):
        resp = self.client.post(
            "/retell/webhook",
            json={
                "event": "call_ended",
                "call": {
                    "call_id": "c1",
                    "metadata": {"tenant_id": "acme", "ghl_contact_id": "contact_1"},
                    "call_analysis": {"call_summary": "Caller wants an HVAC tune-up."},
                },
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.ghl.logged_notes), 1)
        self.assertIn("HVAC tune-up", self.ghl.logged_notes[0]["note"])

    def test_call_ended_without_summary_does_not_log_note(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_ended", "call": {"call_id": "c1", "metadata": {"tenant_id": "acme"}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.ghl.logged_notes), 0)

    def test_duplicate_call_event_is_acknowledged_without_second_effect(self):
        payload = {
            "event": "call_ended",
            "call": {
                "call_id": "duplicate-call",
                "metadata": {"tenant_id": "acme", "ghl_contact_id": "contact_1"},
                "call_analysis": {"call_summary": "One note only."},
            },
        }
        first = self.client.post("/retell/webhook", json=payload)
        second = self.client.post("/retell/webhook", json=payload)
        self.assertEqual(first.json()["status"], "received")
        self.assertEqual(second.json()["status"], "duplicate")
        self.assertEqual(len(self.ghl.logged_notes), 1)


class TestFunctionCallWebhook(RetellRouterTestCase):
    def test_book_appointment_creates_local_appointment(self):
        resp = self.client.post(
            "/retell/function-call",
            json={
                "name": "book_appointment",
                "args": {
                    "customer_name": "Jane Doe",
                    "phone": "555-1234",
                    "preferred_time": "2026-08-01T15:00:00Z",
                },
                "call": {"metadata": {"tenant_id": "acme"}},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("all set", resp.json()["result"])
        # Booked locally, not synced to GHL -- a fresh caller has no
        # existing GHL contact_id yet. See _handle_book_appointment.
        self.assertEqual(len(self.ghl.created_appointments), 0)

    def test_book_appointment_without_preferred_time_asks_again(self):
        resp = self.client.post(
            "/retell/function-call",
            json={
                "name": "book_appointment",
                "args": {"customer_name": "Jane"},
                "call": {"metadata": {"tenant_id": "acme"}},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("preferred time", resp.json()["result"])

    def test_escalate_to_human(self):
        resp = self.client.post(
            "/retell/function-call",
            json={
                "name": "escalate_to_human",
                "args": {"reason": "angry customer"},
                "call": {"metadata": {"tenant_id": "acme"}},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("connect you", resp.json()["result"])

    def test_get_availability(self):
        resp = self.client.post(
            "/retell/function-call",
            json={"name": "get_availability", "args": {}, "call": {"metadata": {"tenant_id": "acme"}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("openings", resp.json()["result"])

    def test_unknown_function_returns_fallback(self):
        resp = self.client.post(
            "/retell/function-call",
            json={"name": "not_a_real_tool", "args": {}, "call": {"metadata": {"tenant_id": "acme"}}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("team member", resp.json()["result"])

    def test_missing_tenant_id_returns_fallback_not_error(self):
        resp = self.client.post(
            "/retell/function-call",
            json={"name": "book_appointment", "args": {}, "call": {}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("team member", resp.json()["result"])


class TestSignatureVerifier(unittest.TestCase):
    """RetellSignatureVerifier's HMAC logic in isolation -- no live Retell
    request involved. See retell.py's [Unverified] caveat: this tests the
    implementation as written, not that it matches Retell's real header
    format/convention."""

    def test_valid_signature_verifies(self):
        verifier = RetellSignatureVerifier("test-secret")
        body = b'{"event": "call_started"}'
        timestamp = str(int(time.time() * 1000))
        digest = hmac.new(b"test-secret", body + timestamp.encode("ascii"), hashlib.sha256).hexdigest()
        sig = f"v={timestamp},d={digest}"
        self.assertTrue(verifier.verify(body, sig))

    def test_stale_signature_rejected(self):
        verifier = RetellSignatureVerifier("test-secret")
        body = b"{}"
        timestamp = str(int((time.time() - 301) * 1000))
        digest = hmac.new(b"test-secret", body + timestamp.encode("ascii"), hashlib.sha256).hexdigest()
        self.assertFalse(verifier.verify(body, f"v={timestamp},d={digest}"))

    def test_legacy_bare_digest_rejected(self):
        verifier = RetellSignatureVerifier("test-secret")
        body = b"{}"
        digest = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        self.assertFalse(verifier.verify(body, digest))

    def test_invalid_signature_rejected(self):
        verifier = RetellSignatureVerifier("test-secret")
        self.assertFalse(verifier.verify(b'{"event": "call_started"}', "not-a-real-signature"))

    def test_missing_signature_rejected(self):
        verifier = RetellSignatureVerifier("test-secret")
        self.assertFalse(verifier.verify(b"{}", None))

    def test_empty_secret_raises(self):
        with self.assertRaises(ValueError):
            RetellSignatureVerifier("")

    def test_null_verifier_accepts_everything(self):
        verifier = NullRetellWebhookVerifier()
        self.assertTrue(verifier.verify(b"anything", None))


class TestSignatureEnforcement(unittest.TestCase):
    """End-to-end: a router built with a real verifier actually rejects
    unsigned/incorrectly-signed requests."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=NullGHLClient(),
            retell_verifier=RetellSignatureVerifier("real-secret"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_unsigned_webhook_rejected(self):
        resp = self.client.post("/retell/webhook", json={"event": "call_started", "call": {}})
        self.assertEqual(resp.status_code, 401)

    def test_incorrectly_signed_webhook_rejected(self):
        resp = self.client.post(
            "/retell/webhook",
            json={"event": "call_started", "call": {}},
            headers={"x-retell-signature": "wrong-signature"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_correctly_signed_webhook_accepted(self):
        body = json.dumps({"event": "call_started", "call": {"metadata": {"tenant_id": "acme"}}}).encode()
        timestamp = str(int(time.time() * 1000))
        digest = hmac.new(b"real-secret", body + timestamp.encode("ascii"), hashlib.sha256).hexdigest()
        sig = f"v={timestamp},d={digest}"
        resp = self.client.post(
            "/retell/webhook",
            content=body,
            headers={"content-type": "application/json", "x-retell-signature": sig},
        )
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
