"""Tests for the client-facing NetBuild dashboard (webstaffr/dashboard.py
and webstaffr/dashboard_router.py).

Covers: tenant-scoped aggregation, no-fabrication (an empty tenant shows
zeros and nulls, never invented numbers), the read-only JSON endpoint's
auth gating (401 without a session, 403 without membership), and the
branded SPA shell rendering. Same temp-db + TestClient pattern as
test_attribution.py.
"""

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.customer_auth import VerifiedIdentity
from webstaffr.dashboard import build_dashboard_data, dashboard_data_to_dict
from webstaffr.db import connect, migrate


def _valid_intake_payload(**overrides):
    payload = {
        "biz_name": "Desert Pro Plumbing",
        "phone": "602-555-0100",
        "email": "owner@example.com",
        "industry": "Plumber",
        "service_area": "Phoenix, AZ",
        "tagline": "Fast, honest plumbing.",
        "differentiator": "We show up on time, every time.",
        "services": ["Leak Repair", "Drain Cleaning"],
        "license_number": "ROC 999999",
        "plan": "office_staff",
        "lead_routing": "Text Maria at 602-555-0101, replies within 1 hour.",
        "approver": "Maria Lopez",
    }
    payload.update(overrides)
    return payload


class _IdentityVerifier:
    def __init__(self, identity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "test-token" else None


class DashboardUnitTestCase(unittest.TestCase):
    """Direct aggregation tests against a real temp SQLite connection."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._conn_ctx = connect(self.db_path)
        self.conn = self._conn_ctx.__enter__()
        migrate(self.conn)
        self.conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("acme_hvac",))
        self.conn.commit()

    def tearDown(self):
        self._conn_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_empty_tenant_yields_zeros_and_nulls_not_fabricated(self):
        data = build_dashboard_data(self.conn, "acme_hvac")
        d = dashboard_data_to_dict(data)
        self.assertEqual(d["kpis"]["calls_received"], 0)
        self.assertEqual(d["kpis"]["appointments_booked"], 0)
        self.assertEqual(d["kpis"]["leads_received"], 0)
        self.assertEqual(d["kpis"]["reviews_received"], 0)
        self.assertIsNone(d["kpis"]["review_avg_rating"])
        self.assertIsNone(d["business"])  # no intake submission yet
        self.assertIsNone(d["site"])  # no site magic job yet
        self.assertEqual(d["activity"], [])
        self.assertEqual(d["angel"]["status"], "not_configured")
        self.assertEqual(d["roi"]["estimated_value_usd"], 0.0)

    def test_business_snapshot_comes_from_latest_submission(self):
        self.conn.execute(
            """
            INSERT INTO intake_submissions
                (tenant_id, biz_name, phone, email, industry, service_area,
                 tagline, differentiator, services_json, license_number, plan,
                 lead_routing, approver, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "acme_hvac", "Desert Pro Plumbing", "602-555-0100", "o@x.com",
                "Plumber", "Phoenix, AZ", "Fast plumbing.", "On time.",
                '["Leak Repair"]', "ROC 1", "office_staff", "x", "Maria",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        data = build_dashboard_data(self.conn, "acme_hvac")
        self.assertEqual(data.business["biz_name"], "Desert Pro Plumbing")
        self.assertEqual(data.business["industry"], "Plumber")

    def test_aggregation_counts_real_rows_only(self):
        self.conn.execute(
            "INSERT INTO tenants (tenant_id) VALUES (?)", ("other_tenant",)
        )
        ce = self.conn.execute
        ce(
            "INSERT INTO tracking_numbers (tenant_id, tracking_number, created_at) VALUES (?,?,?)",
            ("acme_hvac", "trk_acme_hvac_aa", datetime.now(timezone.utc).isoformat()),
        )
        ce(
            "INSERT INTO call_events (tenant_id, event_type, created_at) VALUES (?,?,?)",
            ("acme_hvac", "call_received", datetime.now(timezone.utc).isoformat()),
        )
        ce(
            "INSERT INTO call_events (tenant_id, event_type, created_at) VALUES (?,?,?)",
            ("acme_hvac", "appointment_booked", datetime.now(timezone.utc).isoformat()),
        )
        ce(
            "INSERT INTO website_leads (lead_id, tenant_id, name, message, status, created_at) VALUES (?,?,?,?,?,?)",
            ("l1", "acme_hvac", "Dana", "need help", "received", datetime.now(timezone.utc).isoformat()),
        )
        ce(
            "INSERT INTO call_events (tenant_id, event_type, created_at) VALUES (?,?,?)",
            ("other_tenant", "call_received", datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()

        data = build_dashboard_data(self.conn, "acme_hvac")
        self.assertEqual(data.kpis["calls_received"], 1)
        self.assertEqual(data.kpis["appointments_booked"], 1)
        self.assertEqual(data.kpis["leads_received"], 1)
        # other_tenant's single call must never leak into acme_hvac
        self.assertEqual(data.kpis["calls_received"], 1)

    def test_angel_active_only_when_calls_logged(self):
        ce = self.conn.execute
        ce(
            "INSERT INTO tracking_numbers (tenant_id, tracking_number, created_at) VALUES (?,?,?)",
            ("acme_hvac", "trk_acme_hvac_aa", datetime.now(timezone.utc).isoformat()),
        )
        self.conn.commit()
        data = build_dashboard_data(self.conn, "acme_hvac")
        # tracking present but no calls -> configured, NOT active
        self.assertEqual(data.angel["status"], "configured")
        self.assertEqual(data.angel["calls_fielded"], 0)


class DashboardRouterTestCase(unittest.TestCase):
    """HTTP-layer tests via TestClient against a real app instance."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.user_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        identity = VerifiedIdentity(
            user_id=self.user_id,
            session_id=self.session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        app = create_app(
            db_path=self.db_path,
            customer_identity_verifier=_IdentityVerifier(identity),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO customer_users (user_id) VALUES (?)", (self.user_id,)
            )
        resp = self.client.post("/auth/session", headers=self._auth_headers())
        self.assertEqual(resp.status_code, 200)

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    @staticmethod
    def _auth_headers(**extra):
        return {"Authorization": "Bearer test-token", **extra}

    def _submit_intake(self):
        resp = self.client.post("/intake", json=_valid_intake_payload())
        self.assertEqual(resp.status_code, 200)
        tenant_id = resp.json()["tenant_id"]
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (?, ?, 'viewer')",
                (tenant_id, self.user_id),
            )
        return tenant_id

    def test_dashboard_data_requires_auth(self):
        tenant_id = self._submit_intake()
        # no bearer token
        resp = self.client.get(f"/tenants/{tenant_id}/dashboard-data")
        self.assertEqual(resp.status_code, 401)

    def test_dashboard_data_requires_membership(self):
        tenant_id = self._submit_intake()
        # same member token, but for a tenant the user never joined -> 403
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("unjoined_tenant",))
        resp = self.client.get(
            "/tenants/unjoined_tenant/dashboard-data", headers=self._auth_headers()
        )
        self.assertEqual(resp.status_code, 403)

    def test_dashboard_data_returns_aggregated_payload(self):
        tenant_id = self._submit_intake()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO call_events (tenant_id, event_type, created_at) VALUES (?,?,?)",
                (tenant_id, "call_received", datetime.now(timezone.utc).isoformat()),
            )
        resp = self.client.get(
            f"/tenants/{tenant_id}/dashboard-data", headers=self._auth_headers()
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], tenant_id)
        self.assertEqual(body["kpis"]["calls_received"], 1)
        self.assertIn("generated_at", body)
        self.assertIn("activity", body)
        self.assertIn("angel", body)

    def test_dashboard_shell_renders_html(self):
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Control Center", resp.text)

    def test_tenant_dashboard_page_renders_html(self):
        resp = self.client.get("/tenants/acme_hvac/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Control Center", resp.text)

    def test_invalid_tenant_id_shape_on_data_is_404(self):
        resp = self.client.get(
            "/tenants/not valid!!/dashboard-data", headers=self._auth_headers()
        )
        self.assertIn(resp.status_code, (404, 403))

    def test_all_sql_is_tenant_scoped(self):
        """Static check: every query executed against a tenant table in
        dashboard.py carries a tenant_id predicate (no cross-tenant read
        path exists). Inspects each conn.execute(...) SQL block."""
        import pathlib
        import re

        src = (
            pathlib.Path(__file__).parent.parent / "webstaffr" / "dashboard.py"
        ).read_text()
        blocks = re.findall(r'execute\(\s*(?:f)?\("(.*?)"\s*,', src, re.DOTALL)
        tables = (
            "intake_submissions", "website_leads", "appointments",
            "review_requests", "review_responses", "quotes",
            "site_magic_jobs", "site_magic_builds", "call_events",
            "tracking_numbers",
        )
        suspicious = [b.strip() for b in blocks if any(t in b for t in tables) and "tenant_id = ?" not in b]
        self.assertEqual(
            suspicious, [], msg=f"Untenant-scoped query blocks: {suspicious}"
        )


if __name__ == "__main__":
    unittest.main()
