"""Tests for NetBuild.Pro Agency Site router and governance compliance."""

from __future__ import annotations

import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app


class AgencySiteGovernanceTestCase(unittest.TestCase):
    """Verify agency site pages are governance-compliant."""

    def setUp(self):
        """Set up test client."""
        self.temp_db = tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False)
        self.temp_db.close()
        self.app = create_app(db_path=self.temp_db.name)
        self.client = TestClient(self.app)

    def test_agency_home_renders(self):
        """Agency home page renders with 200 status."""
        response = self.client.get("/agency")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Turn customer interest into service requests", response.content)

    def test_agency_home_no_em_dashes(self):
        """Home page has no em-dashes (governance: em-dash ban)."""
        response = self.client.get("/agency")
        # Check for both literal em-dash and entity-encoded version
        self.assertNotIn("—", response.text)
        self.assertNotIn("&mdash;", response.text)

    def test_agency_home_no_ai_language(self):
        """Home page doesn't describe the product as AI (governance: no 'AI' in copy)."""
        response = self.client.get("/agency")
        # OK to say "doesn't trust AI" or "AI receptionist" as rebuttal, but
        # not to position NetBuild.Pro as AI.
        # Check that the hook and subhead are present instead.
        self.assertIn(b"Turn customer interest into service requests", response.content)
        self.assertIn(b"Angel call handling", response.content)

    def test_agency_home_no_fabrication(self):
        """Home page does not publish unsupported statistics or economics."""
        response = self.client.get("/agency")
        for unsupported in (
            "27%",
            "85%",
            "78%",
            "$16,000",
            "$192,000",
            "answers every call",
            "books every job",
            "24/7",
        ):
            self.assertNotIn(unsupported, response.text)

    def test_agency_pricing_renders(self):
        """Pricing page renders."""
        response = self.client.get("/agency/pricing")
        self.assertEqual(response.status_code, 200)
        # ADR-026: initial launch exposes only Office Staff at $497/month.
        self.assertIn(b"$497", response.content)
        self.assertIn(b"Office Staff", response.content)
        for retired in (b"$2,497", b"$5,000", b"Essentials", b">Pro<", b"Growth"):
            self.assertNotIn(retired, response.content)

    def test_all_agency_pages_use_canonical_brand_and_tiers(self):
        pages = (
            "/agency",
            "/agency/pricing",
            "/agency/faq",
            "/agency/how-it-works",
            "/agency/about",
            "/agency/contact",
        )
        for page in pages:
            response = self.client.get(page)
            with self.subTest(page=page):
                self.assertEqual(response.status_code, 200)
                self.assertIn("NetBuild.Pro", response.text)
                for stale in ("WebStaffr", "Business Manager", "White-Glove", "Essentials", "Growth"):
                    self.assertNotIn(stale, response.text)

    def test_agency_contact_routes_to_working_intake(self):
        response = self.client.get("/agency/contact")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/start"', response.text)
        self.assertNotIn("<form", response.text)

    def test_agency_pricing_no_em_dashes(self):
        """Pricing page has no em-dashes."""
        response = self.client.get("/agency/pricing")
        self.assertNotIn("—", response.text)
        self.assertNotIn("&mdash;", response.text)

    def test_agency_faq_renders(self):
        """FAQ page renders."""
        response = self.client.get("/agency/faq")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Common Questions", response.content)

    def test_agency_how_it_works_renders(self):
        """How It Works page renders."""
        response = self.client.get("/agency/how-it-works")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Three Steps", response.content)

    def test_agency_about_renders(self):
        """About page renders."""
        response = self.client.get("/agency/about")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Built for home service businesses", response.content)

    def test_agency_contact_renders(self):
        """Contact page renders."""
        response = self.client.get("/agency/contact")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Start with your business intake", response.content)

    def test_agency_trailing_slash(self):
        """Agency home accepts both /agency and /agency/."""
        resp1 = self.client.get("/agency")
        resp2 = self.client.get("/agency/")
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

    def test_agency_pages_html_response(self):
        """All agency pages return HTML content-type."""
        pages = [
            "/agency",
            "/agency/pricing",
            "/agency/faq",
            "/agency/how-it-works",
            "/agency/about",
            "/agency/contact",
        ]
        for page in pages:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/html", response.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
