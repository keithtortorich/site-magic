"""Angel widget embed verification - Gate 3.

Verifies that the Retell voice embed is present and correctly configured
on all rendered customer sites. The Angel AI employee cannot function
without the embed code.

This gate ensures no site renders without the widget.
"""

import os
import re
import tempfile
import unittest

from fastapi.testclient import TestClient
from webstaffr.app import create_app


def _valid_payload(**overrides):
    """Build a valid intake submission."""
    payload = {
        "biz_name": "Test Service",
        "phone": "+1-555-0100",
        "email": "test@example.com",
        "industry": "HVAC Technician",
        "service_area": "Phoenix, AZ",
        "tagline": "Professional service.",
        "differentiator": "Reliable and fast.",
        "services": ["Service A", "Service B"],
        "plan": "office_staff",
        "license_number": "Not displayed publicly",
        "lead_routing": "Founder only",
        "approver": "Founder",
    }
    payload.update(overrides)
    return payload


class TestAngelEmbedVerification(unittest.TestCase):
    """Gate 3: Verify Angel widget is present and configured."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        app = create_app(db_path=self.db_path)
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _make_tenant(self, **overrides) -> str:
        """Create a tenant and return its ID."""
        resp = self.client.post("/intake", json=_valid_payload(**overrides))
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["tenant_id"]

    def test_angel_script_tag_present(self):
        """Rendered site must include the first-party Angel widget."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)

        self.assertIn('src="/static/angel-widget.js"', resp.text)
        self.assertIn(f'data-tenant-id="{tenant_id}"', resp.text)

    def test_angel_script_in_footer_not_head(self):
        """Angel script should load after page content, not in the head."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)

        # Split at </head> tag
        if "</head>" in resp.text.lower():
            head_section = resp.text.lower().split("</head>")[0]
            body_section = resp.text.lower().split("</head>")[1]

            self.assertNotIn("angel-widget.js", head_section)
            self.assertIn("angel-widget.js", body_section)

    def test_angel_embed_has_necessary_attributes(self):
        """Angel embed must identify its tenant and API base."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)

        html = resp.text

        self.assertIn(f'data-tenant-id="{tenant_id}"', html)
        self.assertIn("data-api-base=", html)

    def test_embed_script_src_is_https(self):
        """Script src (if present) must be HTTPS, not HTTP or localhost."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)

        html = resp.text

        script_pattern = r'<script[^>]*src="([^"]*angel-widget\.js[^"]*)"'
        matches = re.findall(script_pattern, html, re.IGNORECASE)

        if matches:
            for src in matches:
                self.assertTrue(
                    src.startswith("https://") or src.startswith("/"),
                    f"Angel script must be HTTPS or same-origin: {src}"
                )
                self.assertNotIn("localhost", src, "Retell src should not be localhost")
                self.assertNotIn("127.0.0.1", src, "Retell src should not be 127.0.0.1")

    def test_home_page_has_embed(self):
        """Home page must have Angel embed."""
        tenant_id = self._make_tenant(biz_name="Test HVAC")
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("angel-widget.js", resp.text.lower())

    def test_embed_verification_multiple_trades(self):
        """Verify embed is present across different trades."""
        trades = [
            {"biz_name": "HVAC Pro", "industry": "HVAC Technician"},
            {"biz_name": "Plumbing Plus", "industry": "Plumber"},
            {"biz_name": "Roofing Co", "industry": "Roofer"},
        ]

        for trade in trades:
            tenant_id = self._make_tenant(**trade)
            resp = self.client.get(f"/sites/{tenant_id}/web")
            self.assertEqual(resp.status_code, 200, f"Failed for {trade['industry']}")
            self.assertIn("angel-widget.js", resp.text.lower(), f"Missing embed for {trade['industry']}")


if __name__ == "__main__":
    unittest.main()
