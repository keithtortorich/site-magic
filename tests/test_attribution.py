"""Tests for webstaffr/attribution.py and attribution_router.py: tracking
number generation/persistence, call event logging, and the dashboard
metrics/list-calls reads. Same temp-file-db + lifespan-context pattern as
test_intake.py/test_router.py."""

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from webstaffr.attribution import (
    AttributionValidationError,
    CallEvent,
    CallEventRepository,
    TrackingNumberRepository,
    generate_tracking_number,
)
from webstaffr.db import connect, migrate
from webstaffr.app import create_app
from webstaffr.customer_auth import VerifiedIdentity


class _IdentityVerifier:
    def __init__(self, identity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "test-token" else None


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


class AttributionUnitTestCase(unittest.TestCase):
    """Direct repository tests against a real (temp-file) SQLite connection
    -- no HTTP layer, matching test_db_pg_shim.py's "test the module
    directly" posture for the parts that don't need the router."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._conn_ctx = connect(self.db_path)
        self.conn = self._conn_ctx.__enter__()
        migrate(self.conn)
        # tracking_numbers/call_events both FK to tenants(tenant_id) --
        # create one directly, same shortcut other repository tests use.
        self.conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("acme_hvac",))
        self.conn.commit()

    def tearDown(self):
        self._conn_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestTrackingNumberRepository(AttributionUnitTestCase):
    def test_get_or_create_creates_a_new_record(self):
        record = TrackingNumberRepository(self.conn).get_or_create("acme_hvac")
        self.conn.commit()
        self.assertEqual(record.tenant_id, "acme_hvac")
        self.assertTrue(record.tracking_number.startswith("trk_acme_hvac_"))
        self.assertIsNotNone(record.created_at)

    def test_get_or_create_is_idempotent(self):
        repo = TrackingNumberRepository(self.conn)
        first = repo.get_or_create("acme_hvac")
        self.conn.commit()
        second = repo.get_or_create("acme_hvac")
        self.conn.commit()
        self.assertEqual(first.tracking_number, second.tracking_number)

    def test_get_for_tenant_returns_none_when_absent(self):
        self.assertIsNone(TrackingNumberRepository(self.conn).get_for_tenant("acme_hvac"))

    def test_generate_tracking_number_is_unique_per_call(self):
        a = generate_tracking_number("acme_hvac")
        b = generate_tracking_number("acme_hvac")
        self.assertNotEqual(a, b)
        self.assertIn("acme_hvac", a)


class TestCallEventRepository(AttributionUnitTestCase):
    def test_log_event_rejects_invalid_event_type(self):
        with self.assertRaises(AttributionValidationError):
            CallEventRepository(self.conn).log_event(
                CallEvent(tenant_id="acme_hvac", event_type="not_a_real_event")
            )

    def test_log_event_persists_and_returns_event_id(self):
        event = CallEventRepository(self.conn).log_event(
            CallEvent(tenant_id="acme_hvac", event_type="call_received", call_id="call_1")
        )
        self.conn.commit()
        self.assertIsNotNone(event.event_id)
        self.assertIsNotNone(event.created_at)

    def test_metrics_for_tenant_with_no_events_is_all_zero(self):
        metrics = CallEventRepository(self.conn).metrics_for_tenant("acme_hvac")
        self.assertEqual(metrics["calls_received"], 0)
        self.assertEqual(metrics["calls_completed"], 0)
        self.assertEqual(metrics["appointments_booked"], 0)
        self.assertEqual(metrics["estimated_value_usd"], 0.0)

    def test_metrics_for_tenant_counts_by_event_type(self):
        repo = CallEventRepository(self.conn)
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_received", call_id="c1"))
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_ended", call_id="c1", duration_seconds=90))
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_received", call_id="c2"))
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_ended", call_id="c2", duration_seconds=60))
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="appointment_booked", call_id="c2"))
        self.conn.commit()

        metrics = repo.metrics_for_tenant("acme_hvac")
        self.assertEqual(metrics["calls_received"], 2)
        self.assertEqual(metrics["calls_completed"], 2)
        self.assertEqual(metrics["appointments_booked"], 1)
        self.assertEqual(metrics["estimated_value_usd"], 250.0)

    def test_metrics_are_tenant_scoped(self):
        self.conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("other_tenant",))
        repo = CallEventRepository(self.conn)
        repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="appointment_booked"))
        repo.log_event(CallEvent(tenant_id="other_tenant", event_type="appointment_booked"))
        repo.log_event(CallEvent(tenant_id="other_tenant", event_type="appointment_booked"))
        self.conn.commit()

        self.assertEqual(repo.metrics_for_tenant("acme_hvac")["appointments_booked"], 1)
        self.assertEqual(repo.metrics_for_tenant("other_tenant")["appointments_booked"], 2)

    def test_list_for_tenant_orders_most_recent_first(self):
        repo = CallEventRepository(self.conn)
        first = repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_received", call_id="c1"))
        second = repo.log_event(CallEvent(tenant_id="acme_hvac", event_type="call_received", call_id="c2"))
        self.conn.commit()

        events = repo.list_for_tenant("acme_hvac")
        self.assertEqual(events[0].event_id, second.event_id)
        self.assertEqual(events[1].event_id, first.event_id)

    def test_log_event_preserves_metadata(self):
        repo = CallEventRepository(self.conn)
        repo.log_event(
            CallEvent(
                tenant_id="acme_hvac",
                event_type="call_ended",
                metadata={"disconnection_reason": "user_hangup"},
            )
        )
        self.conn.commit()
        event = repo.list_for_tenant("acme_hvac")[0]
        self.assertEqual(event.metadata, {"disconnection_reason": "user_hangup"})


class AttributionRouterTestCase(unittest.TestCase):
    """HTTP-layer tests: intake wiring (tracking number auto-created) and
    the dashboard read endpoints, via TestClient against a real app
    instance -- same pattern as IntakeTestCase in test_intake.py."""

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
            customer_allowed_origins={"https://example-customer-site.com"},
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO customer_users (user_id) VALUES (?)", (self.user_id,)
            )
        response = self.client.post("/auth/session", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _submit_intake(self):
        resp = self.client.post("/intake", json=_valid_intake_payload())
        self.assertEqual(resp.status_code, 200)
        tenant_id = resp.json()["tenant_id"]
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO tenant_memberships (tenant_id, user_id, role)
                VALUES (?, ?, 'viewer')
                """,
                (tenant_id, self.user_id),
            )
        return tenant_id

    @staticmethod
    def _auth_headers(**extra):
        return {"Authorization": "Bearer test-token", **extra}

    def _get(self, path, **headers):
        return self.client.get(path, headers=self._auth_headers(**headers))


class TestIntakeCreatesTrackingNumber(AttributionRouterTestCase):
    def test_intake_submission_creates_a_tracking_number(self):
        tenant_id = self._submit_intake()
        resp = self._get(f"/tenants/{tenant_id}/tracking-number")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], tenant_id)
        self.assertTrue(body["tracking_number"].startswith("trk_"))


class TestTrackingNumberEndpoint(AttributionRouterTestCase):
    def test_unknown_tenant_returns_404(self):
        resp = self._get("/tenants/never_submitted/tracking-number")
        self.assertEqual(resp.status_code, 403)

    def test_invalid_tenant_id_shape_returns_404_not_500(self):
        resp = self._get("/tenants/not valid!!/tracking-number")
        self.assertEqual(resp.status_code, 403)


class TestMetricsEndpoint(AttributionRouterTestCase):
    def test_metrics_for_tenant_with_no_calls_is_zeroed_not_404(self):
        tenant_id = self._submit_intake()
        resp = self._get(f"/tenants/{tenant_id}/metrics")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["calls_received"], 0)
        self.assertEqual(body["appointments_booked"], 0)
        self.assertIn("estimated_value_note", body)

    def test_invalid_tenant_id_shape_returns_404(self):
        resp = self._get("/tenants/../etc/metrics")
        self.assertIn(resp.status_code, (404, 307))  # path traversal chars get normalized/rejected either way


class TestCallsEndpoint(AttributionRouterTestCase):
    def test_calls_list_is_empty_for_new_tenant(self):
        tenant_id = self._submit_intake()
        resp = self._get(f"/tenants/{tenant_id}/calls")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["calls"], [])

    def test_limit_is_capped_at_200(self):
        tenant_id = self._submit_intake()
        resp = self._get(f"/tenants/{tenant_id}/calls?limit=99999")
        self.assertEqual(resp.status_code, 200)  # capped server-side, not rejected


class TestAttributionCORSScoping(AttributionRouterTestCase):
    def test_tenants_prefix_carries_cors_headers(self):
        tenant_id = self._submit_intake()
        resp = self.client.get(
            f"/tenants/{tenant_id}/metrics",
            headers=self._auth_headers(Origin="https://example-customer-site.com"),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.headers["access-control-allow-origin"],
            "https://example-customer-site.com",
        )
        self.assertEqual(resp.headers["access-control-allow-credentials"], "true")

    def test_tenants_prefix_rejects_unlisted_cross_origin(self):
        tenant_id = self._submit_intake()
        resp = self.client.get(
            f"/tenants/{tenant_id}/metrics",
            headers=self._auth_headers(Origin="https://attacker.example"),
        )
        self.assertEqual(resp.status_code, 403)
        self.assertNotIn("access-control-allow-origin", resp.headers)

    def test_book_endpoint_still_has_no_cors(self):
        """Regression guard: adding '/tenants/' to _CORS_SCOPED_PREFIXES
        must not accidentally widen CORS on unrelated routes."""
        resp = self.client.post(
            "/book",
            json={"tenant_id": "whoever", "contact_name": "x", "starts_at": "2026-01-01T10:00:00"},
            headers={"Origin": "https://example-customer-site.com"},
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)


if __name__ == "__main__":
    unittest.main()
