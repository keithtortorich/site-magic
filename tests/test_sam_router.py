"""Tests for Sam's HTTP surface and full quote generation flow."""

import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.db import connect, migrate
from webstaffr.tenant import Tenant
from webstaffr.workers.angel.api_auth import NullSharedSecretVerifier, StaticSecretVerifier
from webstaffr.workers.sam.protocol import NullGHLQuoteClient
from webstaffr.workers.sam.quote_repository import QuoteRepository


class SamRouterTestCase(unittest.TestCase):
    """Base test case for Sam router tests.

    Uses a real temp-file SQLite DB rather than ':memory:' -- each
    sqlite3.connect(':memory:') call opens an independent, empty database,
    so an app built with db_path=':memory:' never shares a schema with a
    separately-migrated test connection. A temp file behaves like the real
    deployment (one file, many connections) and lets the repository-level
    assertions below read what the HTTP layer wrote.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(
            db_path=self.db_path,
            internal_api_verifier=NullSharedSecretVerifier(),
        )
        # Enter the TestClient as a context manager so the app's ASGI
        # lifespan (startup -> migrate()) actually fires; TestClient(app)
        # without __enter__ does not reliably run lifespan events.
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        # Second connection on the SAME file, for direct repository reads.
        self._ctx = connect(self.db_path)
        self.conn = self._ctx.__enter__()
        migrate(self.conn)  # idempotent -- no-op once lifespan has run
        # Tables here FK to tenants(tenant_id); seed the tenants these
        # tests exercise, same shortcut other repository tests use.
        for tenant_id in ("test_tenant", "tenant_a", "tenant_b"):
            self.conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", (tenant_id,)
            )
        self.conn.commit()
        self.tenant = Tenant(tenant_id="test_tenant")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestSamAuthentication(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

    def tearDown(self):
        os.remove(self.db_path)

    @staticmethod
    def _quote_payload():
        return {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "service_scope": "AC repair service",
            "industry": "HVAC",
            "auto_send": False,
        }

    def test_unconfigured_sam_routes_deny_access(self):
        with TestClient(create_app(db_path=self.db_path)) as client:
            self.assertEqual(client.post("/quotes/generate", json=self._quote_payload()).status_code, 401)
            self.assertEqual(client.get("/quotes/q_1", params={"tenant_id": "test_tenant"}).status_code, 401)
            self.assertEqual(
                client.post("/quotes/q_1/accept", json={"tenant_id": "test_tenant"}).status_code,
                401,
            )

    def test_wrong_internal_key_is_rejected(self):
        app = create_app(
            db_path=self.db_path,
            internal_api_verifier=StaticSecretVerifier("correct-key"),
        )
        with TestClient(app) as client:
            response = client.post(
                "/quotes/generate",
                json=self._quote_payload(),
                headers={"X-API-Key": "wrong-key"},
            )
        self.assertEqual(response.status_code, 401)

    def test_valid_internal_key_is_accepted(self):
        app = create_app(
            db_path=self.db_path,
            internal_api_verifier=StaticSecretVerifier("correct-key"),
        )
        with TestClient(app) as client:
            with connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)",
                    ("test_tenant",),
                )
            response = client.post(
                "/quotes/generate",
                json=self._quote_payload(),
                headers={"X-API-Key": "correct-key"},
            )
        self.assertEqual(response.status_code, 200)


class TestGenerateQuote(SamRouterTestCase):
    def test_generate_quote_basic(self):
        """POST /quotes/generate returns a quote with pricing."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "service_scope": "AC Repair on my split system, it's not cooling",
            "industry": "HVAC",
            "urgency": "routine",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Check structure
        self.assertIn("quote_id", data)
        self.assertIn("estimated_range_low", data)
        self.assertIn("estimated_range_high", data)
        self.assertIn("caveat", data)
        self.assertEqual(data["status"], "pending")
        self.assertFalse(data["email_sent"])

        # Check pricing: AC Repair HVAC range is $200-600
        self.assertGreaterEqual(data["estimated_range_low"], 200)
        self.assertLessEqual(data["estimated_range_high"], 600)

        # Caveat must be present
        self.assertIn("site inspection", data["caveat"].lower())

    def test_generate_quote_invalid_tenant(self):
        """POST /quotes/generate with invalid tenant returns 400."""
        req = {
            "tenant_id": "!!!invalid!!!",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "service_scope": "AC Repair",
            "industry": "HVAC",
        }
        resp = self.client.post("/quotes/generate", json=req)
        self.assertEqual(resp.status_code, 400)

    def test_generate_quote_missing_service_scope(self):
        """POST /quotes/generate with empty scope returns 422 from Pydantic validation."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "service_scope": "",
            "industry": "HVAC",
        }
        resp = self.client.post("/quotes/generate", json=req)
        # Empty string fails GenerateQuoteRequest's min_length=5 before the
        # route handler runs; FastAPI/Pydantic returns 422 for validation errors.
        self.assertEqual(resp.status_code, 422)

    def test_generate_quote_unknown_service_defaults_to_contact(self):
        """POST /quotes/generate with unknown service returns contact-for-quote."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "service_scope": "I need some weird service that doesn't exist",
            "industry": "HVAC",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Should return 0-0 range and "Contact for quote" caveat
        self.assertEqual(data["estimated_range_low"], 0)
        self.assertEqual(data["estimated_range_high"], 0)
        self.assertIn("contact", data["caveat"].lower())

    def test_generate_quote_urgency_multiplier(self):
        """POST /quotes/generate applies urgency multiplier to estimate."""
        # Routine scope
        req_routine = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "urgency": "routine",
            "auto_send": False,
        }
        resp_routine = self.client.post("/quotes/generate", json=req_routine)
        data_routine = resp_routine.json()

        # Emergency scope
        req_emergency = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_124",
            "contact_name": "Jane",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "urgency": "emergency",
            "auto_send": False,
        }
        resp_emergency = self.client.post("/quotes/generate", json=req_emergency)
        data_emergency = resp_emergency.json()

        # Emergency should be higher
        self.assertGreater(
            data_emergency["estimated_range_high"],
            data_routine["estimated_range_high"],
        )
        # Emergency caveat should mention surcharge
        self.assertIn("surcharge", data_emergency["caveat"].lower())

    def test_generate_quote_industry_fallback(self):
        """POST /quotes/generate with unknown industry falls back to Other."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John",
            "service_scope": "Some service",
            "industry": "UnknownIndustry123",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        # Should fall back gracefully
        self.assertIn("quote_id", data)

    def test_generate_quote_persisted_to_db(self):
        """POST /quotes/generate persists quote to database."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req)
        data = resp.json()
        quote_id = data["quote_id"]

        # Fetch from DB directly
        quote = QuoteRepository.get_quote(self.conn, quote_id, "test_tenant")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.tenant_id, "test_tenant")
        self.assertEqual(quote.contact_id, "ghl_123")
        self.assertEqual(quote.status, "pending")


class TestGetQuote(SamRouterTestCase):
    def test_get_quote_found(self):
        """GET /quotes/{id} returns quote data."""
        # First, create a quote
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        create_resp = self.client.post("/quotes/generate", json=req)
        quote_id = create_resp.json()["quote_id"]

        # Fetch it
        resp = self.client.get(f"/quotes/{quote_id}?tenant_id=test_tenant")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["quote_id"], quote_id)
        self.assertEqual(data["contact_id"], "ghl_123")
        self.assertIn("estimated_range_low", data)

    def test_get_quote_not_found(self):
        """GET /quotes/{id} with non-existent ID returns 404."""
        resp = self.client.get("/quotes/nonexistent?tenant_id=test_tenant")
        self.assertEqual(resp.status_code, 404)

    def test_get_quote_tenant_isolation(self):
        """GET /quotes/{id} respects tenant scoping."""
        # Create quote for one tenant
        req = {
            "tenant_id": "tenant_a",
            "contact_id": "ghl_123",
            "contact_name": "John",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        create_resp = self.client.post("/quotes/generate", json=req)
        quote_id = create_resp.json()["quote_id"]

        # Try to fetch with different tenant
        resp = self.client.get(f"/quotes/{quote_id}?tenant_id=tenant_b")
        self.assertEqual(resp.status_code, 404)

        # Fetch with correct tenant works
        resp = self.client.get(f"/quotes/{quote_id}?tenant_id=tenant_a")
        self.assertEqual(resp.status_code, 200)


class TestAcceptQuote(SamRouterTestCase):
    def test_accept_quote_creates_appointment(self):
        """POST /quotes/{id}/accept creates an appointment."""
        # Create quote
        create_req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        create_resp = self.client.post("/quotes/generate", json=create_req)
        quote_id = create_resp.json()["quote_id"]

        # Accept quote
        accept_req = {
            "tenant_id": "test_tenant",
            "preferred_time": "2026-08-10T14:00:00Z",
        }
        resp = self.client.post(f"/quotes/{quote_id}/accept", json=accept_req)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertEqual(data["quote_id"], quote_id)
        self.assertEqual(data["status"], "accepted")
        self.assertIsNotNone(data["appointment_id"])
        self.assertTrue(data["appointment_scheduled"])

    def test_accept_quote_updates_status(self):
        """POST /quotes/{id}/accept updates quote status to accepted."""
        # Create and accept quote
        create_req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John Smith",
            "contact_email": "john@example.com",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        create_resp = self.client.post("/quotes/generate", json=create_req)
        quote_id = create_resp.json()["quote_id"]

        accept_req = {"tenant_id": "test_tenant"}
        self.client.post(f"/quotes/{quote_id}/accept", json=accept_req)

        # Fetch quote and verify status
        get_resp = self.client.get(f"/quotes/{quote_id}?tenant_id=test_tenant")
        quote_data = get_resp.json()

        self.assertEqual(quote_data["status"], "accepted")
        self.assertIsNotNone(quote_data["accepted_at"])

    def test_accept_nonexistent_quote_returns_404(self):
        """POST /quotes/{id}/accept with non-existent ID returns 404."""
        req = {"tenant_id": "test_tenant"}
        resp = self.client.post("/quotes/nonexistent/accept", json=req)
        self.assertEqual(resp.status_code, 404)


class TestQuoteNoFabrication(SamRouterTestCase):
    """Tests ensuring quotes never fabricate pricing data."""

    def test_quote_always_shows_caveat(self):
        """Every quote includes caveat text."""
        req = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John",
            "service_scope": "AC Repair",
            "industry": "HVAC",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req)
        data = resp.json()

        self.assertGreater(len(data["caveat"]), 0)
        # Should reference site inspection or be a contact-for-quote message
        caveat_lower = data["caveat"].lower()
        self.assertTrue(
            "site inspection" in caveat_lower or "contact" in caveat_lower or "surcharge" in caveat_lower
        )

    def test_quote_ranges_are_plausible(self):
        """Quote ranges are never zero unless service is unknown."""
        # Known service
        req_known = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_123",
            "contact_name": "John",
            "service_scope": "Water Heater Replacement",
            "industry": "Plumber",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req_known)
        data = resp.json()

        # Known service should have non-zero range
        if "water heater" in data["caveat"].lower():
            self.assertGreater(data["estimated_range_low"], 0)
            self.assertGreater(data["estimated_range_high"], 0)

        # Unknown service returns 0-0 (contact for quote)
        req_unknown = {
            "tenant_id": "test_tenant",
            "contact_id": "ghl_124",
            "contact_name": "Jane",
            "service_scope": "xyz_unknown_service_123",
            "industry": "HVAC",
            "auto_send": False,
        }
        resp = self.client.post("/quotes/generate", json=req_unknown)
        data = resp.json()

        self.assertEqual(data["estimated_range_low"], 0)
        self.assertEqual(data["estimated_range_high"], 0)


if __name__ == "__main__":
    unittest.main()
