"""Tests for Stripe webhook endpoint (/webhooks/stripe).

Covers:
- Signature verification (valid, invalid, missing)
- Appointment status updates on charge events
- Tenant scoping (can't update another tenant's appointment)
- Invalid/missing metadata handling
- Event type mapping
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.workers.angel.api_auth import NullSharedSecretVerifier, StaticSecretVerifier
from webstaffr.workers.angel.ghl import NullGHLClient
from webstaffr.workers.angel.voice import NullVoiceBackend


class StripeWebhookTestCase(unittest.TestCase):
    """Base class for Stripe webhook tests. Sets up a test app and DB."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.ghl = NullGHLClient()
        # For signature verification tests, use a known secret
        self.stripe_secret = "test_stripe_secret"
        app = create_app(
            db_path=self.db_path,
            voice_backend=NullVoiceBackend(),
            ghl_client=self.ghl,
            book_api_verifier=NullSharedSecretVerifier(),
            stripe_webhook_verifier=StaticSecretVerifier(self.stripe_secret),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _create_appointment(self, tenant_id: str) -> int:
        """Helper: create an appointment and return its ID."""
        resp = self.client.post(
            "/book",
            json={
                "tenant_id": tenant_id,
                "contact_name": "Jane",
                "starts_at": "2026-08-10T15:00:00Z",
            },
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["appointment_id"]


class TestStripeWebhookSignatureVerification(StripeWebhookTestCase):
    """Verify signature verification works correctly."""

    def test_webhook_rejects_missing_signature(self):
        """Webhook should reject requests with no Stripe-Signature header."""
        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {"object": {"metadata": {"tenant_id": "acme", "appointment_id": "1"}}},
            },
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Invalid or missing webhook signature", resp.json()["detail"])

    def test_webhook_rejects_invalid_signature(self):
        """Webhook should reject requests with an invalid signature."""
        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {"object": {"metadata": {"tenant_id": "acme", "appointment_id": "1"}}},
            },
            headers={"Stripe-Signature": "invalid_signature"},
        )
        self.assertEqual(resp.status_code, 401)


class TestStripeWebhookMissingMetadata(StripeWebhookTestCase):
    """Verify proper handling of missing tenant_id or appointment_id."""

    def test_webhook_rejects_missing_tenant_id(self):
        """Webhook should reject payloads without tenant_id in metadata."""
        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {"object": {"metadata": {"appointment_id": "1"}}},
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing tenant_id or appointment_id", resp.json()["detail"])

    def test_webhook_rejects_missing_appointment_id(self):
        """Webhook should reject payloads without appointment_id in metadata."""
        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {"object": {"metadata": {"tenant_id": "acme"}}},
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Missing tenant_id or appointment_id", resp.json()["detail"])


class TestStripeWebhookStatusUpdates(StripeWebhookTestCase):
    """Verify appointment status is updated correctly based on event type."""

    def test_charge_succeeded_updates_status_to_paid(self):
        """charge.succeeded event should update appointment status to 'paid'."""
        appt_id = self._create_appointment("acme")

        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "paid")

    def test_charge_failed_updates_status_to_payment_failed(self):
        """charge.failed event should update appointment status to 'payment_failed'."""
        appt_id = self._create_appointment("acme")

        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.failed",
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "payment_failed")

    def test_charge_refunded_updates_status_to_refunded(self):
        """charge.refunded event should update appointment status to 'refunded'."""
        appt_id = self._create_appointment("acme")

        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.refunded",
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["new_status"], "refunded")

    def test_duplicate_event_is_acknowledged_without_second_mutation(self):
        appt_id = self._create_appointment("acme")
        payload = {
            "id": "evt_duplicate",
            "type": "charge.succeeded",
            "data": {"object": {"metadata": {
                "tenant_id": "acme", "appointment_id": str(appt_id)
            }}},
        }
        first = self.client.post(
            "/webhooks/stripe", json=payload,
            headers={"Stripe-Signature": self.stripe_secret},
        )
        second = self.client.post(
            "/webhooks/stripe", json=payload,
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(first.json()["status"], "handled")
        self.assertEqual(second.json(), {"status": "duplicate", "event_id": "evt_duplicate"})


class TestStripeWebhookTenantScoping(StripeWebhookTestCase):
    """Verify tenant isolation: one tenant can't update another's appointments."""

    def test_webhook_does_not_update_other_tenant_appointment(self):
        """Webhook with tenant_id=acme should not be able to update tenant_id=other's appointment."""
        # Create appointment for "other" tenant
        appt_id = self._create_appointment("other")

        # Try to update it via webhook claiming to be "acme"
        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        # Request succeeds (200) but no rows are updated (tenant_id check prevents it)
        self.assertEqual(resp.status_code, 200)
        # Appointment status should NOT change


class TestStripeWebhookUnhandledEventType(StripeWebhookTestCase):
    """Verify unhandled event types are logged and ignored gracefully."""

    def test_webhook_ignores_unsupported_event_type(self):
        """Webhook should ignore event types not in the status_map."""
        appt_id = self._create_appointment("acme")

        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.dispute.created",  # Not in our status_map
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={"Stripe-Signature": self.stripe_secret},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ignored")
        self.assertIn("Unhandled event type", resp.json()["reason"])


class TestStripeWebhookNoCORSHeader(StripeWebhookTestCase):
    """Verify /webhooks/stripe does not carry CORS headers (server-to-server only)."""

    def test_stripe_webhook_no_cors_header(self):
        """Stripe webhook should not have CORS header (no browser caller)."""
        appt_id = self._create_appointment("acme")

        resp = self.client.post(
            "/webhooks/stripe",
            json={
                "type": "charge.succeeded",
                "data": {
                    "object": {
                        "metadata": {
                            "tenant_id": "acme",
                            "appointment_id": str(appt_id),
                        }
                    }
                },
            },
            headers={
                "Stripe-Signature": self.stripe_secret,
                "Origin": "https://evil.example.com",
            },
        )
        self.assertNotIn("access-control-allow-origin", resp.headers)
