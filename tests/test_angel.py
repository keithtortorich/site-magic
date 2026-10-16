import os
import unittest

import httpx

from webstaffr.db import connect, migrate
from webstaffr.tenant import Tenant
from webstaffr.workers.angel.angel import Angel, load_prompt_template
from webstaffr.workers.angel.booking import AppointmentRepository, _normalize_starts_at
from webstaffr.workers.angel.ghl import (
    GHLNotConfiguredError,
    GoHighLevelClient,
    NullGHLClient,
)
from webstaffr.workers.angel.voice import (
    GrokVoiceBackend,
    NullVoiceBackend,
    VoiceBackendNotConfiguredError,
)


class _FakeHTTPResponse:
    """Minimal stand-in for an httpx.Response, used to test
    GrokVoiceBackend.respond() without a real network call."""

    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("simulated error status", request=None, response=self)

    def json(self):
        return self._json


class AngelTestCase(unittest.TestCase):
    def setUp(self):
        self._ctx = connect(":memory:")
        self.conn = self._ctx.__enter__()
        migrate(self.conn)
        self.tenant = Tenant(tenant_id="acme")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)


class TestPromptTemplate(unittest.TestCase):
    def test_prompt_template_loads_real_founder_prompt(self):
        text = load_prompt_template()
        # The founder's real prompt, synced from Drive -- no longer a
        # placeholder. Check for content specific to the real text so this
        # test actually fails if the file regresses to something else.
        self.assertIn("AI receptionist for local home service businesses", text)
        self.assertIn("Always get explicit confirmation before booking", text)
        self.assertNotIn("DRAFT PLACEHOLDER", text)


class TestRenderPrompt(AngelTestCase):
    def test_render_prompt_includes_core_prompt_and_dynamic_context(self):
        angel = Angel(tenant=self.tenant, conn=self.conn, business_name="Joe's Plumbing")
        context = angel.build_context({"caller_name": "Pat"})
        rendered = angel.render_prompt(context)

        self.assertIn("You are Angel", rendered)
        self.assertIn("Dynamic context for this session:", rendered)
        self.assertIn("business_name: Joe's Plumbing", rendered)
        self.assertIn("caller_name: Pat", rendered)

    def test_respond_attaches_rendered_system_prompt_to_context(self):
        captured = {}

        class CapturingBackend:
            def respond(self, message, context):
                captured.update(context)
                return "ok"

        angel = Angel(tenant=self.tenant, conn=self.conn, voice_backend=CapturingBackend())
        angel.respond("hello")
        self.assertIn("system_prompt", captured)
        self.assertIn("You are Angel", captured["system_prompt"])


class TestAngelRespond(AngelTestCase):
    def test_respond_uses_null_backend_by_default(self):
        angel = Angel(tenant=self.tenant, conn=self.conn)
        reply = angel.respond("Hi, can I book an appointment?")
        self.assertIsInstance(reply, str)
        self.assertTrue(len(reply) > 0)


class TestAngelBooking(AngelTestCase):
    def test_book_appointment_persists_locally(self):
        angel = Angel(tenant=self.tenant, conn=self.conn)
        appt = angel.book_appointment(
            contact_name="Jane Doe",
            starts_at="2026-08-01T15:00:00Z",
            contact_phone="555-1234",
            sync_to_ghl=False,
        )
        self.assertIsNotNone(appt.appointment_id)
        self.assertFalse(appt.ghl_synced)

        stored_ids = AppointmentRepository(self.conn).list_for_tenant("acme")
        self.assertEqual(stored_ids, [appt.appointment_id])

    def test_book_appointment_syncs_to_ghl_when_requested(self):
        ghl = NullGHLClient()
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        appt = angel.book_appointment(
            contact_name="Jane Doe",
            starts_at="2026-08-01T15:00:00Z",
            sync_to_ghl=True,
            ghl_contact_id="ghl_contact_123",
        )
        self.assertTrue(appt.ghl_synced)
        self.assertEqual(len(ghl.created_appointments), 1)

    def test_ghl_sync_failure_does_not_break_local_booking(self):
        class BoomGHLClient:
            def __init__(self):
                self.create_appointment_calls = 0

            def log_note(self, contact_id, note):
                raise RuntimeError("simulated GHL outage")

            def create_appointment(self, contact_id, starts_at, notes):
                self.create_appointment_calls += 1
                raise RuntimeError("simulated GHL outage")

        ghl = BoomGHLClient()
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        appt = angel.book_appointment(
            contact_name="Jane Doe",
            starts_at="2026-08-01T15:00:00Z",
            sync_to_ghl=True,
            ghl_contact_id="ghl_contact_123",
        )
        # Local booking must still have succeeded despite the GHL failure.
        self.assertIsNotNone(appt.appointment_id)
        self.assertFalse(appt.ghl_synced)
        # Default ghl_max_attempts=3 -- confirms retry actually happened,
        # not just a single failed attempt.
        self.assertEqual(ghl.create_appointment_calls, 3)

    def test_book_appointment_retries_and_succeeds_after_transient_ghl_failures(self):
        class FlakyGHLClient:
            def __init__(self, fail_times):
                self.fail_times = fail_times
                self.calls = 0

            def create_appointment(self, contact_id, starts_at, notes):
                self.calls += 1
                if self.calls <= self.fail_times:
                    raise RuntimeError("simulated transient GHL outage")
                return {"contact_id": contact_id, "ghl_id": "ghl_1"}

            def log_note(self, contact_id, note):
                raise AssertionError("not exercised by this test")

        ghl = FlakyGHLClient(fail_times=2)
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        appt = angel.book_appointment(
            contact_name="Jane Doe",
            starts_at="2026-08-01T15:00:00Z",
            sync_to_ghl=True,
            ghl_contact_id="ghl_contact_123",
        )
        self.assertTrue(appt.ghl_synced)
        self.assertEqual(ghl.calls, 3)


class TestAngelGHLNotes(AngelTestCase):
    def test_log_note_to_ghl_returns_true_on_success(self):
        ghl = NullGHLClient()
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        ok = angel.log_note_to_ghl("ghl_contact_123", "Called about pricing.")
        self.assertTrue(ok)
        self.assertEqual(len(ghl.logged_notes), 1)

    def test_log_note_to_ghl_returns_false_on_failure_without_raising(self):
        class BoomGHLClient:
            def __init__(self):
                self.log_note_calls = 0

            def log_note(self, contact_id, note):
                self.log_note_calls += 1
                raise RuntimeError("simulated GHL outage")

            def create_appointment(self, contact_id, starts_at, notes):
                raise AssertionError("not exercised by this test")

        ghl = BoomGHLClient()
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        ok = angel.log_note_to_ghl("ghl_contact_123", "Called about pricing.")
        self.assertFalse(ok)
        self.assertEqual(ghl.log_note_calls, 3)

    def test_log_note_to_ghl_retries_and_succeeds_after_transient_failures(self):
        class FlakyGHLClient:
            def __init__(self, fail_times):
                self.fail_times = fail_times
                self.calls = 0

            def log_note(self, contact_id, note):
                self.calls += 1
                if self.calls <= self.fail_times:
                    raise RuntimeError("simulated transient GHL outage")

            def create_appointment(self, contact_id, starts_at, notes):
                raise AssertionError("not exercised by this test")

        ghl = FlakyGHLClient(fail_times=1)
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl)
        ok = angel.log_note_to_ghl("ghl_contact_123", "Called about pricing.")
        self.assertTrue(ok)
        self.assertEqual(ghl.calls, 2)

    def test_ghl_max_attempts_is_configurable_and_validated(self):
        with self.assertRaises(ValueError):
            Angel(tenant=self.tenant, conn=self.conn, ghl_max_attempts=0)

        class AlwaysFailsGHLClient:
            def __init__(self):
                self.calls = 0

            def log_note(self, contact_id, note):
                self.calls += 1
                raise RuntimeError("simulated GHL outage")

            def create_appointment(self, contact_id, starts_at, notes):
                raise AssertionError("not exercised by this test")

        ghl = AlwaysFailsGHLClient()
        angel = Angel(tenant=self.tenant, conn=self.conn, ghl_client=ghl, ghl_max_attempts=1)
        ok = angel.log_note_to_ghl("ghl_contact_123", "note")
        self.assertFalse(ok)
        self.assertEqual(ghl.calls, 1)


class TestVoiceBackends(unittest.TestCase):
    def test_null_backend_responds_without_external_calls(self):
        backend = NullVoiceBackend()
        reply = backend.respond("hello", {})
        self.assertIsInstance(reply, str)

    def test_grok_backend_requires_api_key(self):
        old = os.environ.pop("GROK_API_KEY", None)
        try:
            with self.assertRaises(VoiceBackendNotConfiguredError):
                GrokVoiceBackend()
        finally:
            if old is not None:
                os.environ["GROK_API_KEY"] = old

    def test_grok_backend_returns_content_from_successful_api_call(self):
        """GrokVoiceBackend.respond() now makes a real xAI API call --
        mocked here rather than hitting the network. No live xAI account
        is available in this environment, and this test suite never makes
        real network calls anywhere else (NullVoiceBackend/NullGHLClient
        follow the same offline-by-default rule)."""
        backend = GrokVoiceBackend(api_key="test-key")
        backend.client.post = lambda *a, **k: _FakeHTTPResponse(
            {"choices": [{"message": {"content": "Hello from Grok"}}]}
        )
        reply = backend.respond("hi", {"system_prompt": "You are Angel."})
        self.assertEqual(reply, "Hello from Grok")

    def test_grok_backend_degrades_gracefully_on_transport_failure(self):
        backend = GrokVoiceBackend(api_key="test-key")

        def _boom(*args, **kwargs):
            raise httpx.RequestError("simulated network failure")

        backend.client.post = _boom
        reply = backend.respond("hi", {})
        self.assertIsInstance(reply, str)
        self.assertNotEqual(reply, "")

    def test_grok_backend_degrades_gracefully_on_malformed_response(self):
        """An unexpected response shape (e.g. xAI changing their API) must
        still degrade to the fallback reply, not raise into the caller --
        but see test_router.py/health_check.py for the logging distinction
        this case gets versus a transport failure."""
        backend = GrokVoiceBackend(api_key="test-key")
        backend.client.post = lambda *a, **k: _FakeHTTPResponse({"unexpected": "shape"})
        reply = backend.respond("hi", {})
        self.assertIsInstance(reply, str)
        self.assertNotEqual(reply, "")


class TestGHLClients(unittest.TestCase):
    def test_null_client_records_calls(self):
        client = NullGHLClient()
        client.log_note("c1", "note text")
        client.create_appointment("c1", "2026-08-01T15:00:00Z", "notes")
        client.update_appointment("appt_1", "2026-08-02T15:00:00Z", "updated notes")
        client.cancel_appointment("appt_1")
        self.assertEqual(len(client.logged_notes), 1)
        self.assertEqual(len(client.created_appointments), 1)
        self.assertEqual(len(client.updated_appointments), 1)
        self.assertEqual(len(client.cancelled_appointments), 1)

    def test_real_client_requires_credentials(self):
        old_key = os.environ.pop("GHL_API_KEY", None)
        old_loc = os.environ.pop("GHL_LOCATION_ID", None)
        try:
            with self.assertRaises(GHLNotConfiguredError):
                GoHighLevelClient()
        finally:
            if old_key is not None:
                os.environ["GHL_API_KEY"] = old_key
            if old_loc is not None:
                os.environ["GHL_LOCATION_ID"] = old_loc

    def test_upsert_contact_calls_documented_endpoint_and_payload(self):
        client = GoHighLevelClient(api_key="k", location_id="loc")
        captured = {}

        def _fake_request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return {"contact": {"id": "contact_1"}}

        client._request = _fake_request
        result = client.upsert_contact(
            "Jordan Customer",
            "602-555-0199",
            "jordan@example.com",
            "NetBuild.Pro website",
        )

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/contacts/upsert")
        self.assertEqual(
            captured["payload"],
            {
                "name": "Jordan Customer",
                "phone": "602-555-0199",
                "email": "jordan@example.com",
                "locationId": "loc",
                "source": "NetBuild.Pro website",
                "createNewIfDuplicateAllowed": False,
            },
        )
        self.assertEqual(result["contact"]["id"], "contact_1")

    def test_update_appointment_calls_expected_endpoint(self):
        """Verifies GoHighLevelClient.update_appointment() calls _request
        with the right method/path -- mocked, no live GHL account to hit."""
        client = GoHighLevelClient(api_key="k", location_id="loc")
        captured = {}

        def _fake_request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return {"ok": True}

        client._request = _fake_request
        result = client.update_appointment("appt_1", "2026-08-02T15:00:00Z", "updated notes")
        self.assertEqual(captured["method"], "PUT")
        self.assertIn("appt_1", captured["path"])
        self.assertEqual(result, {"ok": True})

    def test_cancel_appointment_calls_expected_endpoint(self):
        client = GoHighLevelClient(api_key="k", location_id="loc")
        captured = {}

        def _fake_request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return {"ok": True}

        client._request = _fake_request
        result = client.cancel_appointment("appt_1")
        self.assertEqual(captured["method"], "DELETE")
        self.assertIn("appt_1", captured["path"])
        self.assertEqual(result, {"ok": True})


if __name__ == "__main__":
    unittest.main()
