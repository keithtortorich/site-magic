import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.rate_limit import RateLimitExceeded


def _valid_payload(**overrides):
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


class IntakeTestCase(unittest.TestCase):
    """Same temp-file-db + lifespan-context pattern as RouterTestCase in
    test_router.py -- see that file for why ':memory:' doesn't work here."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(db_path=self.db_path)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class FakeSiteMagicQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, *, job_id, tenant_id):
        self.enqueued.append((job_id, tenant_id))


class TestIntakeSubmission(IntakeTestCase):
    def test_valid_submission_returns_generated_tenant_id(self):
        resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body["submission_id"], int)
        self.assertTrue(body["tenant_id"].startswith("desert_pro_plumbing_"))
        self.assertEqual(body["biz_name"], "Desert Pro Plumbing")
        self.assertEqual(body["industry"], "Plumber")
        self.assertEqual(body["plan"], "office_staff")

    def test_storage_failure_returns_json_503_not_html_500(self):
        """A persistence error (e.g. a missing/partially-applied production
        schema) must yield a JSON 503 the browser can parse, never an
        unhandled 500 HTML page that makes response.json() throw
        'Unexpected token I, \"Internal S\"...'."""
        from webstaffr.intake import StorageError

        with patch(
            "webstaffr.intake_router.IntakeRepository.save",
            side_effect=StorageError("simulated persist failure"),
        ):
            resp = self.client.post("/intake", json=_valid_payload())

        self.assertEqual(resp.status_code, 503)
        # Content-Type must be JSON so the frontend's response handler parses it.
        self.assertIn("application/json", resp.headers.get("content-type", ""))
        self.assertEqual(
            resp.json()["detail"],
            "Intake temporarily unavailable. Please try again shortly.",
        )

    def test_submission_creates_tenant_row(self):
        resp = self.client.post("/intake", json=_valid_payload())
        tenant_id = resp.json()["tenant_id"]

        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT tenant_id FROM tenants WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)

    def test_submission_persists_full_row(self):
        resp = self.client.post("/intake", json=_valid_payload(rating_value=4.8, review_count=214))
        tenant_id = resp.json()["tenant_id"]
        submission_id = resp.json()["submission_id"]

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM intake_submissions WHERE tenant_id = ? AND submission_id = ?",
                (tenant_id, submission_id),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["biz_name"], "Desert Pro Plumbing")
        self.assertEqual(row["rating_value"], 4.8)
        self.assertEqual(row["review_count"], 214)
        self.assertIn("Leak Repair", row["services_json"])

    def test_two_businesses_with_same_name_get_different_tenant_ids(self):
        r1 = self.client.post("/intake", json=_valid_payload())
        r2 = self.client.post("/intake", json=_valid_payload())
        self.assertNotEqual(r1.json()["tenant_id"], r2.json()["tenant_id"])

    def test_submission_generates_site_artifacts(self):
        resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 200)
        tenant_id = resp.json()["tenant_id"]

        workdir = Path(self.db_path).resolve().parent / "generated_sites"
        web_dir = workdir / tenant_id / "web"
        self.assertTrue(web_dir.exists(), msg=f"expected web dir at {web_dir}")
        self.assertTrue((web_dir / "tokens.css").exists(), msg="expected tokens.css")
        for page in ("home.html", "about.html", "contact.html", "services.html"):
            self.assertTrue((web_dir / page).exists(), msg=f"expected {page}")

    def test_rate_limited_submission_creates_no_tenant_or_site(self):
        workdir = Path(self.db_path).resolve().parent / "generated_sites"
        sites_before = set(workdir.iterdir()) if workdir.exists() else set()
        with patch(
            "webstaffr.intake_router.check_dimensions",
            side_effect=RateLimitExceeded("testclient", "intake", 31, 30, 60),
        ) as check:
            resp = self.client.post("/intake", json=_valid_payload())

        self.assertEqual(resp.status_code, 429)
        self.assertEqual(
            resp.json()["detail"],
            "Too many setup requests. Please try again shortly.",
        )
        check.assert_called_once()
        dimensions = check.call_args.args[2]
        self.assertEqual(dimensions, [("ip", "testclient")])

        conn = sqlite3.connect(self.db_path)
        try:
            tenant_count = conn.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
            submission_count = conn.execute(
                "SELECT COUNT(*) FROM intake_submissions"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(tenant_count, 0)
        self.assertEqual(submission_count, 0)

        sites_after = set(workdir.iterdir()) if workdir.exists() else set()
        self.assertEqual(sites_after, sites_before)


class TestIntakeAutoEnqueuesSiteMagic(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.queue = FakeSiteMagicQueue()
        app = create_app(db_path=self.db_path, site_magic_queue=self.queue)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_successful_intake_enqueues_a_site_magic_job(self):
        resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 200)
        tenant_id = resp.json()["tenant_id"]

        self.assertEqual(len(self.queue.enqueued), 1)
        job_id, enqueued_tenant_id = self.queue.enqueued[0]
        self.assertEqual(enqueued_tenant_id, tenant_id)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT tenant_id, source_type, source_payload_json, status FROM site_magic_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["tenant_id"], tenant_id)
        self.assertEqual(row["source_type"], "intake")
        self.assertEqual(row["status"], "queued")
        source_payload = json.loads(row["source_payload_json"])
        self.assertEqual(source_payload["renderer_baseline"]["path"], f"/sites/{tenant_id}/web")
        self.assertIn("home", source_payload["renderer_baseline"]["pages"])

    def test_rate_limited_submission_does_not_enqueue(self):
        with patch(
            "webstaffr.intake_router.check_dimensions",
            side_effect=RateLimitExceeded("testclient", "intake", 31, 30, 60),
        ):
            resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(self.queue.enqueued, [])

    def test_renderer_route_is_enqueued_when_optional_disk_generation_fails(self):
        with patch(
            "webstaffr.intake_router.generate_site_for_submission",
            side_effect=OSError("read-only serverless filesystem"),
        ):
            resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 200)
        tenant_id = resp.json()["tenant_id"]
        self.assertEqual(len(self.queue.enqueued), 1)

        job_id, _ = self.queue.enqueued[0]
        conn = sqlite3.connect(self.db_path)
        try:
            raw = conn.execute(
                "SELECT source_payload_json FROM site_magic_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        source_payload = json.loads(raw)
        self.assertEqual(
            source_payload["renderer_baseline"]["path"],
            f"/sites/{tenant_id}/web",
        )
        self.assertEqual(
            source_payload["renderer_baseline"]["pages"],
            ["home", "about", "contact", "services"],
        )


class TestIntakeWithoutSiteMagicQueueConfigured(IntakeTestCase):
    """IntakeTestCase's create_app() call doesn't pass site_magic_queue, so
    the resolved queue is NullSiteMagicQueue -- intake must still succeed."""

    def test_intake_succeeds_even_though_site_magic_is_not_configured(self):
        resp = self.client.post("/intake", json=_valid_payload())
        self.assertEqual(resp.status_code, 200)

        tenant_id = resp.json()["tenant_id"]
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM site_magic_jobs WHERE tenant_id = ?", (tenant_id,)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)


class TestIntakeValidation(IntakeTestCase):
    def test_missing_required_field_is_rejected(self):
        resp = self.client.post("/intake", json={"biz_name": "Test"})
        self.assertEqual(resp.status_code, 422)

    def test_empty_services_list_is_rejected(self):
        resp = self.client.post("/intake", json=_valid_payload(services=[]))
        self.assertEqual(resp.status_code, 400)

    def test_invalid_plan_is_rejected(self):
        resp = self.client.post("/intake", json=_valid_payload(plan="enterprise"))
        self.assertEqual(resp.status_code, 400)

    def test_rating_value_out_of_range_is_rejected(self):
        resp = self.client.post("/intake", json=_valid_payload(rating_value=9.0))
        self.assertEqual(resp.status_code, 400)

    def test_no_submission_is_persisted_on_validation_failure(self):
        self.client.post("/intake", json=_valid_payload(plan="enterprise"))
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM intake_submissions").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 0)


class TestTradePresets(IntakeTestCase):
    def test_list_presets_returns_all_industries(self):
        resp = self.client.get("/intake/presets")
        self.assertEqual(resp.status_code, 200)
        industries = resp.json()["industries"]
        self.assertIn("HVAC", industries)
        self.assertIn("Plumber", industries)
        self.assertIn("Other", industries)

    def test_known_industry_returns_matching_preset(self):
        resp = self.client.get("/intake/presets/HVAC")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["industry"], "HVAC")
        self.assertIn("tagline", body["hints"])
        self.assertIn("options", body["software"])

    def test_industry_alias_resolves_to_canonical_preset(self):
        resp = self.client.get("/intake/presets/Plumbing")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["industry"], "Plumber")

    def test_unknown_industry_falls_back_to_other(self):
        resp = self.client.get("/intake/presets/Astrology")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["industry"], "Other")


class TestIntakeCORSScoping(IntakeTestCase):
    """/intake and /intake/presets are browser-facing (the intake form runs
    on an arbitrary origin, same as the /chat widget) so they need CORS --
    unlike /book and /webhooks/ghl, see test_router.py's TestCORSScoping."""

    def test_intake_has_cors_header_for_arbitrary_origin(self):
        resp = self.client.post(
            "/intake",
            json=_valid_payload(),
            headers={"Origin": "https://some-marketing-site.example.com"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")

    def test_intake_presets_has_cors_header(self):
        resp = self.client.get(
            "/intake/presets/HVAC",
            headers={"Origin": "https://some-marketing-site.example.com"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")


if __name__ == "__main__":
    unittest.main()
