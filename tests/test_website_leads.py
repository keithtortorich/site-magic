from __future__ import annotations

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.rate_limit import RateLimitExceeded
from webstaffr.workers.angel.ghl import GHLSyncError, NullGHLClient


def _intake_payload(**overrides):
    payload = {
        "biz_name": "Desert Pro Plumbing",
        "phone": "602-555-0100",
        "email": "owner@example.com",
        "industry": "Plumber",
        "service_area": "Phoenix, AZ",
        "tagline": "Local plumbing service",
        "differentiator": "Family operated",
        "services": ["Leak Repair", "Drain Cleaning"],
        "license_number": "N/A",
        "plan": "office_staff",
        "lead_routing": "office",
        "approver": "owner",
    }
    payload.update(overrides)
    return payload


def _lead_payload(**overrides):
    payload = {
        "name": "Jordan Customer",
        "phone": "602-555-0199",
        "email": "jordan@example.com",
        "message": "The kitchen sink is leaking.",
        "source_path": "/contact",
    }
    payload.update(overrides)
    return payload


class WebsiteLeadTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "app.db")
        app = create_app(db_path=self.db_path)
        self._client_context = TestClient(app)
        self.client = self._client_context.__enter__()
        response = self.client.post("/intake", json=_intake_payload())
        self.assertEqual(response.status_code, 200, response.text)
        self.tenant_id = response.json()["tenant_id"]

    def tearDown(self):
        self._client_context.__exit__(None, None, None)
        self._tmp.cleanup()

    def _rows(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM website_leads ORDER BY created_at, lead_id"
            ).fetchall()
        finally:
            conn.close()


class TestWebsiteLeadPersistence(WebsiteLeadTestCase):
    def test_json_submission_returns_201_and_persists_under_url_tenant(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "received")
        uuid.UUID(response.json()["lead_id"])

        rows = self._rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["lead_id"], response.json()["lead_id"])
        self.assertEqual(row["tenant_id"], self.tenant_id)
        self.assertEqual(row["name"], "Jordan Customer")
        self.assertEqual(row["phone"], "602-555-0199")
        self.assertEqual(row["email"], "jordan@example.com")
        self.assertEqual(row["message"], "The kitchen sink is leaking.")
        self.assertEqual(row["source_path"], "/contact")
        self.assertEqual(row["status"], "received")
        self.assertEqual(row["forward_attempts"], 0)

    def test_urlencoded_no_javascript_submission_returns_confirmation_html(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            data=_lead_payload(email="", source_path="/"),
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Request received", response.text)
        self.assertIn(f"/sites/{self.tenant_id}/web", response.text)
        self.assertEqual(len(self._rows()), 1)

    def test_service_page_source_derives_published_service(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(
                service=None,
                source_path="/services/leak-repair",
            ),
        )

        self.assertEqual(response.status_code, 201)
        row = self._rows()[0]
        self.assertEqual(row["service"], "Leak Repair")
        self.assertEqual(row["source_path"], "/services/leak-repair")

    def test_unpublished_service_and_source_are_not_stored(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(
                service="Other Tenant Premium Service",
                source_path="/services/other-tenant-premium-service",
            ),
        )

        self.assertEqual(response.status_code, 201)
        row = self._rows()[0]
        self.assertIsNone(row["service"])
        self.assertIsNone(row["source_path"])

    def test_honeypot_is_indistinguishable_but_writes_nothing(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(website="https://spam.example"),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "received")
        uuid.UUID(response.json()["lead_id"])
        self.assertEqual(self._rows(), [])

    def test_second_tenant_payload_cannot_override_url_tenant(self):
        other = self.client.post(
            "/intake",
            json=_intake_payload(biz_name="Other Electric", services=["Panel Upgrade"]),
        ).json()["tenant_id"]
        payload = _lead_payload(service="Panel Upgrade")
        payload["tenant_id"] = other

        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=payload,
        )

        self.assertEqual(response.status_code, 201)
        row = self._rows()[0]
        self.assertEqual(row["tenant_id"], self.tenant_id)
        self.assertIsNone(row["service"])


class WebsiteLeadGHLTestCase(WebsiteLeadTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "app.db")
        self.ghl = NullGHLClient()
        app = create_app(db_path=self.db_path, ghl_client=self.ghl)
        self._client_context = TestClient(app)
        self.client = self._client_context.__enter__()
        response = self.client.post("/intake", json=_intake_payload())
        self.assertEqual(response.status_code, 200, response.text)
        self.tenant_id = response.json()["tenant_id"]


class TestWebsiteLeadGHLForwarding(WebsiteLeadGHLTestCase):
    def test_successful_forward_records_contact_and_tenant_attributed_note(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(service="Leak Repair", source_path="/services/leak-repair"),
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(len(self.ghl.upserted_contacts), 1)
        contact = self.ghl.upserted_contacts[0]
        self.assertEqual(contact["name"], "Jordan Customer")
        self.assertEqual(contact["phone"], "602-555-0199")
        self.assertEqual(contact["email"], "jordan@example.com")
        self.assertEqual(contact["source"], f"NetBuild.Pro website ({self.tenant_id})")
        self.assertEqual(len(self.ghl.logged_notes), 1)
        note = self.ghl.logged_notes[0]["note"]
        self.assertIn("Desert Pro Plumbing", note)
        self.assertIn(self.tenant_id, note)
        self.assertIn("Leak Repair", note)
        self.assertIn("kitchen sink is leaking", note)

        row = self._rows()[0]
        self.assertEqual(row["status"], "forwarded")
        self.assertEqual(row["forward_attempts"], 1)
        self.assertEqual(row["ghl_contact_id"], "null-contact-1")
        self.assertIsNone(row["last_forward_error_code"])

    def test_provider_failure_keeps_local_lead_and_records_safe_error_code(self):
        def fail_upsert(*args, **kwargs):
            raise GHLSyncError("secret provider response")

        self.ghl.upsert_contact = fail_upsert
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "received")
        self.assertEqual(self.ghl.logged_notes, [])
        row = self._rows()[0]
        self.assertEqual(row["status"], "forward_failed")
        self.assertEqual(row["forward_attempts"], 1)
        self.assertIsNone(row["ghl_contact_id"])
        self.assertEqual(row["last_forward_error_code"], "GHLSyncError")
        self.assertNotIn("secret provider response", row["last_forward_error_code"])

    def test_missing_contact_id_is_a_safe_forward_failure(self):
        self.ghl.upsert_contact = lambda *args, **kwargs: {"contact": {}}

        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        row = self._rows()[0]
        self.assertEqual(row["status"], "forward_failed")
        self.assertEqual(row["last_forward_error_code"], "RuntimeError")
        self.assertIsNone(row["ghl_contact_id"])

    def test_note_failure_preserves_upserted_contact_id_for_reconciliation(self):
        def fail_note(*args, **kwargs):
            raise GHLSyncError("secret note response")

        self.ghl.log_note = fail_note
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
        )

        self.assertEqual(response.status_code, 201, response.text)
        row = self._rows()[0]
        self.assertEqual(row["status"], "forward_failed")
        self.assertEqual(row["forward_attempts"], 1)
        self.assertEqual(row["ghl_contact_id"], "null-contact-1")
        self.assertEqual(row["last_forward_error_code"], "GHLSyncError")

    def test_forward_bookkeeping_failure_never_changes_accepted_response(self):
        with patch(
            "webstaffr.website_lead_router.WebsiteLeadRepository.mark_forwarded",
            side_effect=sqlite3.OperationalError("secret database detail"),
        ):
            response = self.client.post(
                f"/sites/{self.tenant_id}/leads",
                json=_lead_payload(),
            )

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["status"], "received")
        self.assertEqual(len(self.ghl.upserted_contacts), 1)
        self.assertEqual(len(self.ghl.logged_notes), 1)
        row = self._rows()[0]
        self.assertEqual(row["status"], "received")
        self.assertEqual(row["forward_attempts"], 0)

    def test_honeypot_never_calls_provider(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(website="https://spam.example"),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.ghl.upserted_contacts, [])
        self.assertEqual(self.ghl.logged_notes, [])
        self.assertEqual(self._rows(), [])


class TestWebsiteLeadValidation(WebsiteLeadTestCase):
    def test_unknown_and_invalid_tenants_write_nothing(self):
        for tenant_id in ("valid_but_missing", "bad tenant id"):
            with self.subTest(tenant_id=tenant_id):
                response = self.client.post(
                    f"/sites/{tenant_id}/leads",
                    json=_lead_payload(),
                )
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self._rows(), [])

    def test_invalid_contact_and_content_are_rejected(self):
        invalid_payloads = (
            _lead_payload(name="   "),
            _lead_payload(message="   "),
            _lead_payload(phone="", email=""),
            _lead_payload(email="not-an-email"),
            _lead_payload(name="x" * 121),
            _lead_payload(message="x" * 2001),
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sites/{self.tenant_id}/leads",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self._rows(), [])

    def test_malformed_json_is_rejected_without_write(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            content=b'{"name":',
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._rows(), [])

    def test_rate_limit_rejection_writes_no_lead(self):
        with patch(
            "webstaffr.website_lead_router.check_dimensions",
            side_effect=RateLimitExceeded(self.tenant_id, "website_leads", 31, 30, 60),
        ) as check:
            response = self.client.post(
                f"/sites/{self.tenant_id}/leads",
                json=_lead_payload(),
            )

        self.assertEqual(response.status_code, 429)
        dimensions = check.call_args.args[2]
        self.assertIn(("account", self.tenant_id), dimensions)
        self.assertIn(("ip", "testclient"), dimensions)
        self.assertEqual(self._rows(), [])

    def test_database_failure_returns_sanitized_503(self):
        with patch(
            "webstaffr.website_lead_router.WebsiteLeadRepository.save",
            side_effect=sqlite3.OperationalError("secret database detail"),
        ):
            response = self.client.post(
                f"/sites/{self.tenant_id}/leads",
                json=_lead_payload(),
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret database detail", response.text)
        self.assertEqual(self._rows(), [])


class TestWebsiteLeadSurface(WebsiteLeadTestCase):
    def test_endpoint_has_public_cors_without_credentials(self):
        response = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
            headers={"Origin": "https://customer.example"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.headers["access-control-allow-origin"], "*")
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_rendered_forms_use_lead_endpoint_and_collect_message(self):
        for path in ("/web", "/web/contact", "/web/services/leak-repair"):
            response = self.client.get(f"/sites/{self.tenant_id}{path}")
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(
                f'action="http://testserver/sites/{self.tenant_id}/leads"',
                response.text,
            )
            self.assertIn('name="message"', response.text)
            self.assertIn('name="website"', response.text)
            self.assertIn("Request received. Reference:", response.text)
            self.assertNotIn('action="http://testserver/intake"', response.text)

    def test_no_public_read_or_mutation_routes_exist(self):
        lead_id = self.client.post(
            f"/sites/{self.tenant_id}/leads",
            json=_lead_payload(),
        ).json()["lead_id"]
        self.assertEqual(
            self.client.get(f"/sites/{self.tenant_id}/leads").status_code,
            405,
        )
        self.assertEqual(
            self.client.get(f"/sites/{self.tenant_id}/leads/{lead_id}").status_code,
            404,
        )

    def test_postgres_migration_is_default_deny(self):
        postgres_sql = Path(
            "webstaffr/migrations/postgres_manual/0018_website_leads.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ENABLE ROW LEVEL SECURITY", postgres_sql)
        self.assertIn("REVOKE ALL", postgres_sql)
        self.assertNotIn("CREATE POLICY", postgres_sql)

    def test_sqlite_and_postgres_lead_migrations_have_field_parity(self):
        sqlite_sql = Path("webstaffr/migrations/0015_website_leads.sql").read_text(
            encoding="utf-8"
        )
        postgres_sql = Path(
            "webstaffr/migrations/postgres_manual/0018_website_leads.sql"
        ).read_text(encoding="utf-8")
        expected_columns = (
            "lead_id",
            "tenant_id",
            "name",
            "phone",
            "email",
            "message",
            "service",
            "source_path",
            "ghl_contact_id",
            "status",
            "forward_attempts",
            "last_forward_error_code",
            "created_at",
            "updated_at",
        )
        for column in expected_columns:
            with self.subTest(column=column):
                self.assertIn(f"    {column} ", sqlite_sql)
                self.assertIn(f"    {column} ", postgres_sql)


if __name__ == "__main__":
    unittest.main()
