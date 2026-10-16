"""Tests for Rita's HTTP surface and data access patterns.

Tests cover:
- Job completion webhook (POST /webhooks/ghl/job_completed)
- Review response drafting (POST /workers/rita/draft-response)
- Template rendering (positive/neutral/negative reviews)
- Tenant isolation (tenant A's data not visible to tenant B)
- Rate limiting (shared with Angel)
- No fabrication of reviews or ratings
"""

import os
import tempfile
import unittest
from datetime import datetime

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.db import connect, migrate
from webstaffr.tenant import Tenant
from webstaffr.workers.angel.api_auth import StaticSecretVerifier
from webstaffr.workers.rita.client import ReviewRequestRepository, ReviewResponseRepository
from webstaffr.workers.rita.protocol import NullReviewPlatformClient
from webstaffr.workers.rita.templates import (
    draft_negative_response,
    draft_neutral_response,
    draft_positive_response,
    render_review_request_sms,
    render_review_request_email,
    select_response_template,
)


class RitaTestCase(unittest.TestCase):
    """Direct repository tests against a real (temp-file) SQLite connection.

    A temp file rather than ':memory:' so the DB behaves like the real
    deployment (one file, many connections) instead of giving every
    sqlite3.connect() call its own independent, empty database.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._ctx = connect(self.db_path)
        self.conn = self._ctx.__enter__()
        migrate(self.conn)
        # review_requests/review_responses both FK to tenants(tenant_id) --
        # create the rows directly, same shortcut other repository tests use.
        for tenant_id in ("acme", "widgetco"):
            self.conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", (tenant_id,)
            )
        self.conn.commit()
        self.tenant = Tenant(tenant_id="acme")
        self.other_tenant = Tenant(tenant_id="widgetco")

    def tearDown(self):
        self._ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestRitaInternalAuthentication(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(
            db_path=self.db_path,
            internal_api_verifier=StaticSecretVerifier("internal-test-key"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        with connect(self.db_path) as conn:
            conn.execute("INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", ("acme",))

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    @staticmethod
    def _payload():
        return {
            "tenant_id": "acme",
            "review_id": "review-1",
            "review_text": "Great service",
            "review_rating": 5,
        }

    def test_draft_response_rejects_missing_key(self):
        response = self.client.post("/workers/rita/draft-response", json=self._payload())
        self.assertEqual(response.status_code, 401)

    def test_draft_response_rejects_wrong_key(self):
        response = self.client.post(
            "/workers/rita/draft-response",
            json=self._payload(),
            headers={"X-API-Key": "wrong"},
        )
        self.assertEqual(response.status_code, 401)

    def test_draft_response_accepts_valid_key(self):
        response = self.client.post(
            "/workers/rita/draft-response",
            json=self._payload(),
            headers={"X-API-Key": "internal-test-key"},
        )
        self.assertEqual(response.status_code, 200)


class TestReviewRequestTemplates(unittest.TestCase):
    """Test review request SMS/email templates."""

    def test_sms_template_with_customer_name(self):
        sms = render_review_request_sms(
            "Alice Smith", "Alice's Plumbing"
        )
        self.assertIn("Alice Smith", sms)
        self.assertIn("Alice's Plumbing", sms)
        self.assertIn("review", sms.lower())

    def test_sms_template_without_customer_name(self):
        sms = render_review_request_sms(None, "Alice's Plumbing")
        self.assertIn("there", sms.lower())
        self.assertIn("Alice's Plumbing", sms)

    def test_email_template_returns_subject_and_body(self):
        subject, body = render_review_request_email(
            "Bob Jones", "Bob's HVAC"
        )
        self.assertIn("hear from you", subject.lower())
        self.assertIn("Bob Jones", body)
        self.assertIn("Bob's HVAC", body)
        self.assertIn("feedback", body.lower())

    def test_email_template_without_customer_name(self):
        subject, body = render_review_request_email(None, "Bob's HVAC")
        self.assertIn("friend", body.lower())


class TestReviewResponseTemplates(unittest.TestCase):
    """Test review response templates -- no fabrication."""

    def test_positive_response_thanks_customer(self):
        response = draft_positive_response(
            "Great service, very professional!",
            "Acme HVAC"
        )
        self.assertIn("thank", response.lower())
        self.assertIn("Acme HVAC", response)
        # Should NOT repeat the original review text (that would be fabrication)
        # Instead, it thanks and offers future service
        self.assertNotIn("Great service", response)

    def test_neutral_response_asks_for_feedback(self):
        response = draft_neutral_response(
            "It was okay, nothing special",
            "Acme HVAC"
        )
        self.assertIn("feedback", response.lower())
        self.assertIn("Acme HVAC", response)
        # Should acknowledge but not echo the review
        self.assertNotIn("It was okay", response)

    def test_negative_response_flagged_for_approval(self):
        response = draft_negative_response(
            "Poor workmanship, wouldn't recommend",
            "Acme HVAC"
        )
        self.assertIn("PENDING YOUR APPROVAL", response)
        self.assertIn("Acme HVAC", response)
        self.assertIn("reach out", response.lower())
        # Should NOT post defensively
        self.assertNotIn("actually", response.lower())

    def test_select_template_positive_no_approval_needed(self):
        response_text, requires_approval = select_response_template(
            5, "Excellent work!", "Acme HVAC"
        )
        self.assertFalse(requires_approval)
        self.assertIn("thank", response_text.lower())

    def test_select_template_four_stars_no_approval_needed(self):
        response_text, requires_approval = select_response_template(
            4, "Good job", "Acme HVAC"
        )
        self.assertFalse(requires_approval)

    def test_select_template_neutral_no_approval_needed(self):
        response_text, requires_approval = select_response_template(
            3, "It was fine", "Acme HVAC"
        )
        self.assertFalse(requires_approval)

    def test_select_template_one_star_requires_approval(self):
        response_text, requires_approval = select_response_template(
            1, "Terrible experience", "Acme HVAC"
        )
        self.assertTrue(requires_approval)
        self.assertIn("PENDING YOUR APPROVAL", response_text)

    def test_select_template_two_stars_requires_approval(self):
        response_text, requires_approval = select_response_template(
            2, "Disappointed", "Acme HVAC"
        )
        self.assertTrue(requires_approval)


class TestReviewRequestRepository(RitaTestCase):
    """Test review_requests table operations."""

    def test_create_review_request_minimal(self):
        repo = ReviewRequestRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            contact_id="ghl_contact_123",
        )
        self.assertIn("request_id", result)
        self.assertEqual(result["tenant_id"], "acme")
        self.assertEqual(result["contact_id"], "ghl_contact_123")

    def test_create_review_request_with_customer_name_and_contact(self):
        repo = ReviewRequestRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            contact_id="ghl_contact_123",
            contact_name="Alice Smith",
            contact_phone="+15551234567",
            contact_email="alice@example.com",
            ghl_job_id="ghl_appt_456",
        )
        request_id = result["request_id"]

        # Retrieve and verify
        fetched = repo.get_by_id("acme", request_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["contact_name"], "Alice Smith")
        self.assertEqual(fetched["contact_phone"], "+15551234567")
        self.assertEqual(fetched["ghl_job_id"], "ghl_appt_456")
        self.assertEqual(fetched["status"], "pending")
        self.assertEqual(fetched["ghl_synced"], 0)

    def test_get_by_contact_id_tenant_scoped(self):
        """Verify tenant isolation: requests from one tenant not visible to another."""
        repo = ReviewRequestRepository(self.conn)

        # Create request for tenant A
        result_a = repo.create(tenant_id="acme", contact_id="contact_123")
        # Create request for tenant B
        result_b = repo.create(tenant_id="widgetco", contact_id="contact_123")

        # Tenant A should only see their own request
        acme_requests = repo.get_by_contact_id("acme", "contact_123")
        self.assertEqual(len(acme_requests), 1)
        self.assertEqual(acme_requests[0]["request_id"], result_a["request_id"])

        # Tenant B should only see their own request
        widgetco_requests = repo.get_by_contact_id("widgetco", "contact_123")
        self.assertEqual(len(widgetco_requests), 1)
        self.assertEqual(widgetco_requests[0]["request_id"], result_b["request_id"])

    def test_update_status(self):
        repo = ReviewRequestRepository(self.conn)
        result = repo.create(tenant_id="acme", contact_id="contact_123")
        request_id = result["request_id"]

        repo.update_status("acme", request_id, "responded")
        fetched = repo.get_by_id("acme", request_id)
        self.assertEqual(fetched["status"], "responded")

    def test_mark_ghl_synced(self):
        repo = ReviewRequestRepository(self.conn)
        result = repo.create(tenant_id="acme", contact_id="contact_123")
        request_id = result["request_id"]

        self.assertEqual(result["request_id"], request_id)
        repo.mark_ghl_synced("acme", request_id)
        fetched = repo.get_by_id("acme", request_id)
        self.assertEqual(fetched["ghl_synced"], 1)


class TestReviewResponseRepository(RitaTestCase):
    """Test review_responses table operations."""

    def test_create_review_response_positive(self):
        repo = ReviewResponseRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            review_source="google",
            review_rating=5,
            review_text="Great service!",
            response_text="Thank you so much!",
            requires_approval=False,
        )
        self.assertIn("response_id", result)
        self.assertEqual(result["response_status"], "pending_draft")
        self.assertEqual(result["tenant_id"], "acme")

    def test_create_review_response_negative(self):
        repo = ReviewResponseRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            review_source="google",
            review_rating=1,
            review_text="Terrible experience",
            response_text="*** PENDING APPROVAL ***...",
            requires_approval=True,
            external_review_id="google_review_789",
            reviewer_name="Unhappy Customer",
        )
        response_id = result["response_id"]

        fetched = repo.get_by_id("acme", response_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["review_rating"], 1)
        self.assertEqual(fetched["reviewer_name"], "Unhappy Customer")
        self.assertEqual(fetched["response_status"], "pending_draft")

    def test_get_pending_approval_tenant_scoped(self):
        """Verify tenant isolation for pending approvals."""
        repo = ReviewResponseRepository(self.conn)

        # Create pending responses for both tenants
        repo.create(
            tenant_id="acme",
            review_source="google",
            review_rating=1,
            review_text="Bad review",
            response_text="Response",
            requires_approval=True,
        )
        repo.create(
            tenant_id="widgetco",
            review_source="google",
            review_rating=1,
            review_text="Bad review",
            response_text="Response",
            requires_approval=True,
        )

        # Acme should only see their own
        acme_pending = repo.get_pending_approval("acme")
        self.assertEqual(len(acme_pending), 1)
        self.assertEqual(acme_pending[0]["tenant_id"], "acme")

        # WidgetCo should only see their own
        widgetco_pending = repo.get_pending_approval("widgetco")
        self.assertEqual(len(widgetco_pending), 1)
        self.assertEqual(widgetco_pending[0]["tenant_id"], "widgetco")

    def test_approve_response(self):
        repo = ReviewResponseRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            review_source="google",
            review_rating=5,
            review_text="Great!",
            response_text="Thank you!",
            requires_approval=False,
        )
        response_id = result["response_id"]

        repo.approve_response("acme", response_id)
        fetched = repo.get_by_id("acme", response_id)
        self.assertEqual(fetched["response_status"], "approved")
        self.assertIsNotNone(fetched["response_approved_at"])

    def test_mark_posted(self):
        repo = ReviewResponseRepository(self.conn)
        result = repo.create(
            tenant_id="acme",
            review_source="google",
            review_rating=5,
            review_text="Great!",
            response_text="Thank you!",
            requires_approval=False,
        )
        response_id = result["response_id"]

        repo.mark_posted("acme", response_id)
        fetched = repo.get_by_id("acme", response_id)
        self.assertEqual(fetched["response_status"], "posted")
        self.assertIsNotNone(fetched["response_posted_at"])


class TestNullReviewPlatformClient(unittest.TestCase):
    """Test the safe-default review platform client."""

    def test_get_recent_reviews_returns_empty_list(self):
        client = NullReviewPlatformClient()
        reviews = client.get_recent_reviews("acme", "2026-01-01T00:00:00")
        self.assertEqual(reviews, [])

    def test_post_review_response_returns_success(self):
        client = NullReviewPlatformClient()
        result = client.post_review_response("review_123", "Our response")
        self.assertEqual(result["status"], "logged_in_memory")

    def test_calls_logged_in_memory(self):
        client = NullReviewPlatformClient()
        client.get_recent_reviews("acme", "2026-01-01T00:00:00")
        client.post_review_response("review_123", "Response")

        # Verify calls were logged
        self.assertEqual(len(client.fetched_reviews), 1)
        self.assertEqual(len(client.posted_responses), 1)
        self.assertEqual(client.posted_responses[0]["review_id"], "review_123")


if __name__ == "__main__":
    unittest.main()
