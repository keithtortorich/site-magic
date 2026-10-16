import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app

_INTERNAL_FIELDS = (
    "lead_routing",
    "approver",
    "timeline",
    "notes",
    "extra_pages",
    "assets_status",
    "has_site",
    "site_url",
    "site_platform",
    "site_issues",
    "has_logo",
    "brand_colors",
    "inspo_sites",
    "brand_words",
    "fsm_system",
    "booking_system",
    "has_gbp",
    "competitors",
    "license_number",
)


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


class SiteDataTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(db_path=self.db_path)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestSiteDataEndpoint(SiteDataTestCase):
    def test_returns_public_data_for_existing_tenant(self):
        submit = self.client.post("/intake", json=_valid_payload())
        tenant_id = submit.json()["tenant_id"]

        resp = self.client.get(f"/sites/{tenant_id}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["tenant_id"], tenant_id)
        self.assertEqual(body["biz_name"], "Desert Pro Plumbing")
        self.assertEqual(body["services"], ["Leak Repair", "Drain Cleaning"])

    def test_internal_fields_never_leak(self):
        submit = self.client.post("/intake", json=_valid_payload())
        tenant_id = submit.json()["tenant_id"]

        body = self.client.get(f"/sites/{tenant_id}").json()
        for field_name in _INTERNAL_FIELDS:
            self.assertNotIn(field_name, body, f"{field_name} must not be public")

    def test_optional_none_fields_are_omitted_not_null(self):
        """Perfect-site principle: no rating_value/review_count/testimonials
        submitted means the key is absent, not present as null -- so the
        site template's job is a presence check, not a null-check, and it
        can never render a fabricated-looking zero/empty value."""
        submit = self.client.post("/intake", json=_valid_payload())
        tenant_id = submit.json()["tenant_id"]

        body = self.client.get(f"/sites/{tenant_id}").json()
        for field_name in ("rating_value", "review_count", "testimonials", "certifications"):
            self.assertNotIn(field_name, body)

    def test_real_rating_and_testimonials_are_included(self):
        submit = self.client.post(
            "/intake",
            json=_valid_payload(rating_value=4.9, review_count=214, testimonials="Great work!"),
        )
        tenant_id = submit.json()["tenant_id"]

        body = self.client.get(f"/sites/{tenant_id}").json()
        self.assertEqual(body["rating_value"], 4.9)
        self.assertEqual(body["review_count"], 214)
        self.assertEqual(body["testimonials"], "Great work!")

    def test_unknown_tenant_returns_404(self):
        resp = self.client.get("/sites/no_such_tenant_at_all")
        self.assertEqual(resp.status_code, 404)

    def test_invalid_tenant_id_returns_404_not_400(self):
        """Same 404 as an unknown-but-valid-shaped tenant_id -- an invalid
        tenant_id shouldn't distinguish itself from "doesn't exist" and leak
        information about tenant_id validity to a public endpoint."""
        resp = self.client.get("/sites/bad id with spaces")
        self.assertEqual(resp.status_code, 404)

    def test_returns_latest_submission_when_tenant_submits_twice(self):
        first = self.client.post("/intake", json=_valid_payload())
        tenant_id = first.json()["tenant_id"]

        # Can't re-post /intake for the same tenant_id (it always generates
        # a new one), so exercise load_latest_for_tenant directly via the
        # repository instead of a second HTTP round trip.
        from webstaffr.intake import IntakeRepository, IntakeSubmission
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            repo = IntakeRepository(conn)
            updated = IntakeSubmission.from_payload(
                tenant_id, _valid_payload(tagline="Updated tagline!")
            )
            repo.save(updated)
            conn.commit()
        finally:
            conn.close()

        body = self.client.get(f"/sites/{tenant_id}").json()
        self.assertEqual(body["tagline"], "Updated tagline!")


class TestSiteDataCORSScoping(SiteDataTestCase):
    def test_sites_endpoint_has_cors_header(self):
        submit = self.client.post("/intake", json=_valid_payload())
        tenant_id = submit.json()["tenant_id"]

        resp = self.client.get(
            f"/sites/{tenant_id}",
            headers={"Origin": "https://some-client-site.lovable.app"},
        )
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "*")


if __name__ == "__main__":
    unittest.main()
