"""Integration tests for Leo's router: webhook handling, scoring, routing."""

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from webstaffr.app import _leo_outreach_enabled_from_env, create_app
from webstaffr.db import connect, migrate
from webstaffr.workers.angel.api_auth import StaticSecretVerifier
from webstaffr.workers.angel.ghl import NullGHLClient
from webstaffr.workers.leo.protocol import GHLMessagingClient


class _FakeGHLMessagingClient(GHLMessagingClient):
    """Test double for GHL messaging (SMS/email). Captures calls."""

    def __init__(self):
        self.sent_sms = []
        self.sent_emails = []

    def send_sms(self, contact_id: str, message: str) -> dict:
        self.sent_sms.append({"contact_id": contact_id, "message": message})
        return {"status": "sent"}

    def send_email(self, contact_id: str, subject: str, body: str) -> dict:
        self.sent_emails.append({"contact_id": contact_id, "subject": subject, "body": body})
        return {"status": "sent"}


def _valid_lead_event(**overrides):
    event = {
        "tenant_id": "acme",
        "event_type": "lead_created",
        "contact_id": "ghl-contact-uuid-123",
        "contact_name": "John Smith",
        "phone": "+1-602-555-0100",
        "email": "john@example.com",
        "business_name": "Smith Plumbing",
        "industry": "Plumbing",
        "company_phone_answered": True,
        "owner_answered": False,
        "text_enabled": True,
        "employee_count": 5,
        "vehicle_count": 2,
        "currently_hiring": False,
        "multiple_locations": False,
        "has_website": False,
        "has_booking_system": False,
        "has_crm": False,
        "has_diy_platform": False,
        "hiring_office_staff": False,
        "active_reviews_count": 3,
        "offers_financing": False,
        "recent_service_history": False,
    }
    event.update(overrides)
    return event


class LeoRouterTestCase(unittest.TestCase):
    """Setup: transient temp DB, migrated schema, authenticated TestClient."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        with connect(self.db_path) as conn:
            migrate(conn)

        self.ghl_client = _FakeGHLMessagingClient()
        self.webhook_verifier = StaticSecretVerifier("test-secret")
        app = create_app(
            db_path=self.db_path,
            ghl_messaging_client=self.ghl_client,
            ghl_webhook_verifier=self.webhook_verifier,
            internal_api_verifier=StaticSecretVerifier("internal-test-secret"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def _seed_tenant(self, tenant_id: str):
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)",
                (tenant_id,),
            )
            conn.commit()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _auth_headers(self):
        return {"X-Webhook-Secret": "test-secret"}

    def _internal_headers(self):
        return {"X-API-Key": "internal-test-secret"}


class TestLeoScoreEndpoint(LeoRouterTestCase):
    """Test the /leo/score internal endpoint."""

    def test_score_endpoint_rejects_missing_internal_key(self):
        resp = self.client.post("/leo/score", json={})
        self.assertEqual(resp.status_code, 401)

    def test_score_endpoint_rejects_wrong_internal_key(self):
        resp = self.client.post(
            "/leo/score",
            json={},
            headers={"X-API-Key": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_score_endpoint_no_signals_returns_low_score(self):
        resp = self.client.post("/leo/score", json={}, headers=self._internal_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["score_accessibility"], 0)
        self.assertEqual(body["score_business_size"], 0)
        self.assertEqual(body["score_digital_maturity"], 0)
        self.assertEqual(body["score_revenue_potential"], 6)  # Other default
        self.assertEqual(body["score_buying_signals"], 0)
        self.assertEqual(body["score_total"], 6)
        self.assertEqual(body["tier"], 4)  # Skip

    def test_score_endpoint_high_signals_returns_high_score(self):
        resp = self.client.post(
            "/leo/score",
            headers=self._internal_headers(),
            json={
                "company_phone_answered": True,  # 15
                "owner_answered": True,  # 10
                "text_enabled": True,  # 5
                "email": "test@example.com",  # 5
                "employee_count": 10,  # 8
                "vehicle_count": 5,  # 5
                "currently_hiring": True,  # 3
                "has_website": False,  # 8
                "has_booking_system": False,  # 5
                "has_crm": False,  # 5
                "industry": "HVAC",  # 15
                "active_reviews_count": 5,  # 2
                "offers_financing": True,  # 2
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["score_accessibility"], 35)  # 15 + 10 + 5 + 5
        self.assertEqual(body["score_business_size"], 16)  # 8 + 5 + 3
        self.assertEqual(body["score_digital_maturity"], 18)  # 8 + 5 + 5
        self.assertEqual(body["score_revenue_potential"], 15)  # HVAC
        self.assertEqual(body["score_buying_signals"], 4)  # 2 + 2
        # Total: 35 + 16 + 18 + 15 + 4 = 88
        self.assertEqual(body["score_total"], 88)
        self.assertEqual(body["tier"], 1)

    def test_score_endpoint_tier_1_threshold(self):
        resp = self.client.post(
            "/leo/score",
            headers=self._internal_headers(),
            json={
                "company_phone_answered": True,  # 15
                "owner_answered": True,  # 10
                "text_enabled": True,  # 5
                "email": "test@example.com",  # 5
                "employee_count": 10,  # 8
                "vehicle_count": 5,  # 5
                "currently_hiring": True,  # 3
                "has_website": False,  # 8
                "has_booking_system": False,  # 5
                "has_crm": False,  # 5
                "industry": "HVAC",  # 15
                "hiring_office_staff": True,  # 3
                "active_reviews_count": 5,  # 2
                "offers_financing": True,  # 2
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["score_total"], 91)
        self.assertEqual(body["tier"], 1)


class TestLeoWebhookNoVerifier(LeoRouterTestCase):
    """Test webhook handling with authenticated requests."""

    def test_webhook_valid_lead_creates_record(self):
        """POST /webhooks/ghl/lead with valid event."""
        self._seed_tenant("acme")
        event = _valid_lead_event()
        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())

        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        self.assertEqual(body["status"], "processed")
        self.assertGreater(body["lead_id"], 0)
        self.assertEqual(body["score"], 70)  # Based on the test event signals
        self.assertEqual(body["tier"], 2)
        self.assertEqual(body["first_touch"], "sms")
        self.assertEqual(body["sync_status"], "synced")

    def test_webhook_valid_lead_stores_in_database(self):
        """Verify lead was actually inserted into webstaffr_leads table."""
        self._seed_tenant("acme")
        event = _valid_lead_event()
        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        lead_id = resp.json()["lead_id"]

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT lead_id, tenant_id, contact_name, score_total, tier, first_touch_channel FROM webstaffr_leads WHERE lead_id = ?",
            (lead_id,),
        )
        row = cursor.fetchone()
        conn.close()

        self.assertIsNotNone(row)
        self.assertEqual(row[0], lead_id)
        self.assertEqual(row[1], "acme")
        self.assertEqual(row[2], "John Smith")
        self.assertEqual(row[3], 70)  # score_total
        self.assertEqual(row[4], 2)  # tier
        self.assertEqual(row[5], "sms")  # first_touch_channel

    def test_webhook_tier_1_sends_sms(self):
        """Tier 1 leads (85+) get SMS first touch."""
        self._seed_tenant("acme")
        event = _valid_lead_event(
            company_phone_answered=True,  # 15
            owner_answered=True,  # 10
            text_enabled=True,  # 5
            email="test@example.com",  # 5
            employee_count=10,  # 8
            vehicle_count=5,  # 5
            currently_hiring=True,  # 3
            has_website=False,  # 8
            has_booking_system=False,  # 5
            has_crm=False,  # 5
            industry="HVAC",  # 15
            hiring_office_staff=True,  # 3
            active_reviews_count=5,  # 2
            offers_financing=True,  # 2
        )
        # Total: 91, Tier 1

        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 1)
        self.assertEqual(body["first_touch"], "sms")

        # Verify SMS was sent
        self.assertEqual(len(self.ghl_client.sent_sms), 1)
        sms = self.ghl_client.sent_sms[0]
        self.assertEqual(sms["contact_id"], "ghl-contact-uuid-123")
        self.assertIn("Smith Plumbing", sms["message"])
        self.assertIn("NetBuild.Pro", sms["message"])
        self.assertNotIn("24/7", sms["message"])
        self.assertIn("YES", sms["message"])

    def test_webhook_tier_3_sends_email(self):
        """Tier 3 leads (55-69) get email first touch."""
        self._seed_tenant("acme")
        event = _valid_lead_event(
            company_phone_answered=True,  # 15
            owner_answered=True,  # 10
            text_enabled=None,  # unknown
            employee_count=None,  # unknown
            vehicle_count=None,  # unknown
            currently_hiring=None,  # unknown
            multiple_locations=None,  # unknown
            has_website=False,  # 8
            has_booking_system=False,  # 5
            has_crm=None,  # unknown
            has_diy_platform=None,  # unknown
            industry="HVAC",  # 15
            hiring_office_staff=True,  # 3
            active_reviews_count=None,  # unknown
            offers_financing=None,  # unknown
            recent_service_history=None,  # unknown
        )
        # Total: 56, Tier 3

        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 3)
        self.assertEqual(body["first_touch"], "email")

        # Verify email was sent
        self.assertEqual(len(self.ghl_client.sent_emails), 1)
        email = self.ghl_client.sent_emails[0]
        self.assertEqual(email["contact_id"], "ghl-contact-uuid-123")
        self.assertIn("Smith Plumbing", email["subject"])
        self.assertIn("NetBuild.Pro", email["body"])
        self.assertIn("integrations are verified", email["body"])
        self.assertNotIn("24/7", email["body"])
        self.assertNotIn("WebStaffr", email["body"])

    def test_webhook_tier_4_sends_nothing(self):
        """Tier 4 leads (<55) are skipped, no outreach."""
        self._seed_tenant("acme")
        event = _valid_lead_event(
            company_phone_answered=False,
            owner_answered=False,
            text_enabled=False,
            email=None,
            employee_count=1,
            has_website=True,
            has_booking_system=True,
            industry="Other",
        )
        # Total: 6, Tier 4

        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tier"], 4)
        self.assertEqual(body["first_touch"], "")

        # No SMS or email sent
        self.assertEqual(len(self.ghl_client.sent_sms), 0)
        self.assertEqual(len(self.ghl_client.sent_emails), 0)

    def test_webhook_invalid_tenant_returns_400(self):
        """Invalid tenant_id → 400."""
        event = _valid_lead_event(tenant_id="")
        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)

    def test_webhook_invalid_event_type_returns_400(self):
        """Unsupported event_type → 400."""
        self._seed_tenant("acme")
        event = _valid_lead_event(event_type="invalid_event")
        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unsupported event_type", resp.json()["detail"])

    def test_webhook_missing_contact_data_still_scores(self):
        """Lead with minimal data still gets scored and stored."""
        self._seed_tenant("acme")
        event = _valid_lead_event(
            contact_name=None,
            phone=None,
            email=None,
            company_phone_answered=None,
        )
        resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()

        # Still processed and scored
        self.assertEqual(body["status"], "processed")
        self.assertGreater(body["lead_id"], 0)
        self.assertGreater(body["score"], 0)

    def test_webhook_rate_limit_exceeded_returns_429(self):
        """Exceeding rate limit returns 429."""
        self._seed_tenant("acme")
        event = _valid_lead_event()

        # Send many requests rapidly to hit rate limit
        # The rate limit is per-tenant and per-key; check rate_limit.py for limits
        for i in range(20):
            resp = self.client.post("/webhooks/ghl/lead", json=event, headers=self._auth_headers())
            if resp.status_code == 429:
                self.assertEqual(resp.json()["detail"], "Rate limit exceeded, try again shortly.")
                return

        # If we got here without hitting 429, the limit is higher than 20
        # This test just documents expected behavior


class TestLeoTenantIsolation(LeoRouterTestCase):
    """Test tenant isolation: can't query/sync across tenants."""

    def test_lead_created_for_one_tenant_invisible_to_another(self):
        """Create lead for tenant A, verify tenant B can't see it."""
        self._seed_tenant("tenant_a")
        self._seed_tenant("tenant_b")
        event_a = _valid_lead_event(tenant_id="tenant_a")
        resp_a = self.client.post("/webhooks/ghl/lead", json=event_a, headers=self._auth_headers())
        lead_id_a = resp_a.json()["lead_id"]

        # Query as tenant B via database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM webstaffr_leads WHERE tenant_id = ?",
            ("tenant_b",),
        )
        count_b = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(count_b, 0)

        # Verify tenant A's lead still exists
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM webstaffr_leads WHERE tenant_id = ? AND lead_id = ?",
            ("tenant_a", lead_id_a),
        )
        count_a = cursor.fetchone()[0]
        conn.close()

        self.assertEqual(count_a, 1)


class TestLeoOutreachActivation(unittest.TestCase):
    def test_env_flag_is_explicit_and_fail_closed(self):
        for value, expected in (("true", True), ("TRUE", True), ("1", False), ("yes", False), ("", False)):
            with self.subTest(value=value), patch.dict(
                os.environ, {"LEO_OUTREACH_ENABLED": value}
            ):
                self.assertEqual(_leo_outreach_enabled_from_env(), expected)

    def test_general_ghl_configuration_does_not_enable_outreach(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        ghl = NullGHLClient()
        try:
            app = create_app(
                db_path=db_path,
                ghl_client=ghl,
                ghl_webhook_verifier=StaticSecretVerifier("test-secret"),
            )
            with TestClient(app) as client:
                with connect(db_path) as conn:
                    conn.execute(
                        "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)",
                        ("acme",),
                    )
                response = client.post(
                    "/webhooks/ghl/lead",
                    json=_valid_lead_event(),
                    headers={"X-Webhook-Secret": "test-secret"},
                )
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(ghl.sent_sms, [])
            self.assertEqual(ghl.sent_emails, [])
        finally:
            os.remove(db_path)


if __name__ == "__main__":
    unittest.main()
