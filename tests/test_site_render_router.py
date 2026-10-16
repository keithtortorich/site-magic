import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app

# Mirrors CLAUDE.md's never-leak list and test_site_data.py's
# _INTERNAL_FIELDS -- every one of these must never appear, verbatim, in
# any rendered HTML page, exactly as the JSON endpoint already guarantees
# for the API response.
_NEVER_LEAK_VALUES = {
    "lead_routing": "Text Maria at 602-555-0101, replies within 1 hour.",
    "approver": "Maria Lopez",
    "competitors": "Ace Plumbing, Best Plumbing Co",
    "license_number": "ROC 999999",
}

_FORBIDDEN_COPY = ("AI", "—")  # brand governance: no "AI", no em-dash

_UNSUPPORTED_DEFAULT_CLAIMS = (
    "24/7 answering service",
    "free estimate",
    "within 1 hour",
    "within 1 business hour",
    "licensed & insured",
    "licensed & certified",
    "no missed opportunities",
    "no voicemail loops",
    "upfront price",
    "no surprises",
    "day or night",
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
        "license_number": _NEVER_LEAK_VALUES["license_number"],
        "plan": "office_staff",
        "lead_routing": _NEVER_LEAK_VALUES["lead_routing"],
        "approver": _NEVER_LEAK_VALUES["approver"],
        "competitors": _NEVER_LEAK_VALUES["competitors"],
    }
    payload.update(overrides)
    return payload


class SiteRenderTestCase(unittest.TestCase):
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
        resp = self.client.post("/intake", json=_valid_payload(**overrides))
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["tenant_id"]


class TestRenderedPagesRoundTrip(SiteRenderTestCase):
    def test_home_page_renders_business_content(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Desert Pro Plumbing", resp.text)
        self.assertIn("Fast, honest plumbing.", resp.text)
        self.assertIn("Leak Repair", resp.text)
        self.assertIn("Drain Cleaning", resp.text)

    def test_service_page_renders_and_links_back_to_other_services(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/services/leak-repair")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Leak Repair", resp.text)
        self.assertIn("Drain Cleaning", resp.text)  # cross-linked as "other services"

    def test_unknown_service_slug_returns_404(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/services/does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_about_page_renders(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/about")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Desert Pro Plumbing", resp.text)

    def test_about_trust_bar_requires_two_rendered_signals(self):
        tenant_id = self._make_tenant(emergency_service="Yes")
        resp = self.client.get(f"/sites/{tenant_id}/web/about")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('<section class="ws-trust-grid">', resp.text)

    def test_about_trust_bar_renders_when_two_signals_exist(self):
        tenant_id = self._make_tenant(emergency_service="Yes", years_in_biz=8)
        resp = self.client.get(f"/sites/{tenant_id}/web/about")
        self.assertEqual(resp.status_code, 200)
        self.assertIn('<section class="ws-trust-grid">', resp.text)
        self.assertIn("8+", resp.text)
        self.assertIn("Emergency Service", resp.text)

    def test_contact_page_renders_phone_and_email(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/contact")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("602-555-0100", resp.text)
        self.assertIn("owner@example.com", resp.text)

    def test_sitemap_lists_every_page(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/sitemap.xml")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp.headers["content-type"])
        self.assertIn(f"/sites/{tenant_id}/web</loc>", resp.text)
        self.assertIn(f"/sites/{tenant_id}/web/about</loc>", resp.text)
        self.assertIn(f"/sites/{tenant_id}/web/contact</loc>", resp.text)
        self.assertIn(f"/sites/{tenant_id}/web/services/leak-repair</loc>", resp.text)
        # No rating/review data submitted -- reviews page must not be listed.
        self.assertNotIn("/reviews</loc>", resp.text)

    def test_robots_txt_points_at_sitemap(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/robots.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(f"/sites/{tenant_id}/web/sitemap.xml", resp.text)

    def test_static_assets_serve(self):
        css = self.client.get("/static/site.css")
        self.assertEqual(css.status_code, 200)
        self.assertIn("text/css", css.headers["content-type"])

        widget = self.client.get("/static/angel-widget.js")
        self.assertEqual(widget.status_code, 200)
        self.assertIn("javascript", widget.headers["content-type"])


class TestDemoSiteRegressions(SiteRenderTestCase):
    """Gate 2: Regression test for all 8 demo sites.

    Smoke test that verifies all demo sites return HTTP 200 and contain
    expected content. This gate catches code changes that silently break
    rendering. Runs before full test suite (fail fast).
    """

    def test_demo_hvac_http_200(self):
        """HVAC demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="Desert Cooling HVAC",
            industry="HVAC Technician",
            service_area="Phoenix, AZ",
            services=["AC Repair", "Installation", "Maintenance"],
            tagline="24/7 emergency AC service.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"HVAC demo failed: {resp.text[:200]}")
        self.assertIn("Desert Cooling HVAC", resp.text)
        self.assertIn("AC Repair", resp.text)

    def test_demo_plumbing_http_200(self):
        """Plumbing demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="Rivera Plumbing",
            industry="Plumber",
            service_area="Phoenix, AZ",
            services=["Leak Repair", "Drain Cleaning", "Emergency"],
            tagline="Fast, honest plumbing.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Plumbing demo failed: {resp.text[:200]}")
        self.assertIn("Rivera Plumbing", resp.text)
        self.assertIn("Leak Repair", resp.text)

    def test_demo_roof_http_200(self):
        """Roofing demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="SkyGuard Roofing",
            industry="Roofer",
            service_area="Phoenix, AZ",
            services=["Roof Repair", "Installation", "Inspection"],
            tagline="Trusted roofing since 2010.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Roof demo failed: {resp.text[:200]}")
        self.assertIn("SkyGuard Roofing", resp.text)
        self.assertIn("Roof Repair", resp.text)

    def test_demo_landscape_http_200(self):
        """Landscaping demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="Verde Landscape",
            industry="Landscaper",
            service_area="Phoenix, AZ",
            services=["Lawn Care", "Hardscape", "Design"],
            tagline="Beautiful outdoor spaces.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Landscape demo failed: {resp.text[:200]}")
        self.assertIn("Verde Landscape", resp.text)
        self.assertIn("Lawn Care", resp.text)

    def test_demo_pest_http_200(self):
        """Pest control demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="ProShield Pest Control",
            industry="Pest Control",
            service_area="Phoenix, AZ",
            services=["Termite Treatment", "Rodent Control", "General Pest"],
            tagline="Safe, effective pest solutions.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Pest demo failed: {resp.text[:200]}")
        self.assertIn("ProShield Pest Control", resp.text)
        self.assertIn("Termite Treatment", resp.text)

    def test_demo_garage_http_200(self):
        """Garage door demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="GateKeeper Garage Doors",
            industry="Garage Door Specialist",
            service_area="Phoenix, AZ",
            services=["Repair", "Installation", "Opener Replacement"],
            tagline="Swift garage door service.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Garage demo failed: {resp.text[:200]}")
        self.assertIn("GateKeeper Garage Doors", resp.text)
        self.assertIn("Repair", resp.text)

    def test_demo_arbor_http_200(self):
        """Tree service demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="Arbor Care Trees",
            industry="Tree Service",
            service_area="Phoenix, AZ",
            services=["Tree Removal", "Pruning", "Stump Grinding"],
            tagline="Professional tree care.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Arbor demo failed: {resp.text[:200]}")
        self.assertIn("Arbor Care Trees", resp.text)
        self.assertIn("Tree Removal", resp.text)

    def test_demo_waterrestore_http_200(self):
        """Water damage restoration demo must render and contain expected content."""
        tenant_id = self._make_tenant(
            biz_name="SwiftRestore Water Damage",
            industry="Water Damage Restoration",
            service_area="Phoenix, AZ",
            services=["Water Extraction", "Drying", "Mold Remediation"],
            tagline="24/7 emergency water damage response.",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200, f"Water demo failed: {resp.text[:200]}")
        self.assertIn("SwiftRestore Water Damage", resp.text)
        self.assertIn("Water Extraction", resp.text)

    def test_widget_embed_present_on_rendered_page(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertIn('src="/static/angel-widget.js"', resp.text)
        self.assertIn(f'data-tenant-id="{tenant_id}"', resp.text)

    def test_light_brand_color_is_preserved_but_not_used_for_actions(self):
        tenant_id = self._make_tenant(brand_colors="#cccccc")
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("--ws-brand-primary: #cccccc", resp.text)
        self.assertNotIn("--ws-primary: #cccccc", resp.text)


class TestReviewsPageGating(SiteRenderTestCase):
    def test_reviews_page_404s_when_no_rating_on_file(self):
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web/reviews")
        self.assertEqual(resp.status_code, 404)

    def test_reviews_page_renders_when_real_rating_present(self):
        tenant_id = self._make_tenant(
            rating_value=4.9, review_count=214, testimonials="They saved our weekend."
        )
        resp = self.client.get(f"/sites/{tenant_id}/web/reviews")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("4.9", resp.text)
        self.assertIn("214", resp.text)
        self.assertIn("They saved our weekend.", resp.text)

    def test_reviews_page_listed_in_sitemap_only_when_present(self):
        tenant_id = self._make_tenant(rating_value=4.9, review_count=214)
        resp = self.client.get(f"/sites/{tenant_id}/web/sitemap.xml")
        self.assertIn(f"/sites/{tenant_id}/web/reviews</loc>", resp.text)


class TestNoFabrication(SiteRenderTestCase):
    def test_explicit_no_flags_never_render_emergency_or_pricing_claims(self):
        tenant_id = self._make_tenant(
            emergency_service="no",
            pricing_shown="no",
        )

        for path in ("/web", "/web/about", "/web/contact", "/web/services/leak-repair"):
            resp = self.client.get(f"/sites/{tenant_id}{path}")
            self.assertEqual(resp.status_code, 200, path)
            rendered = resp.text.lower()
            self.assertNotIn("24/7 emergency service", rendered, path)
            self.assertNotIn("pricing information available", rendered, path)

    def test_templates_do_not_invent_unsupported_default_promises(self):
        tenant_id = self._make_tenant(years_in_biz=8, certifications="EPA 608")

        for path in ("/web", "/web/about", "/web/contact", "/web/services/leak-repair"):
            resp = self.client.get(f"/sites/{tenant_id}{path}")
            self.assertEqual(resp.status_code, 200, path)
            rendered = resp.text.lower()
            for claim in _UNSUPPORTED_DEFAULT_CLAIMS:
                self.assertNotIn(claim, rendered, f"{claim!r} found in {path}")

        home = self.client.get(f"/sites/{tenant_id}/web").text
        self.assertIn("EPA 608", home)
        self.assertNotIn(">Licensed<", home)

    def test_positive_flags_render_only_the_supported_claim(self):
        tenant_id = self._make_tenant(
            emergency_service="yes",
            pricing_shown="yes",
        )
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("24/7 Emergency Service", resp.text)
        self.assertIn("Pricing Information Available", resp.text)
        self.assertNotIn("Free Estimate", resp.text)

    def test_no_review_schema_without_real_review_data(self):
        """The SEO blueprint's Review schema example hardcodes a fabricated
        rating/review as boilerplate (flagged in
        docs/SITE_WEAVER_SEO_BLUEPRINT.md) -- this asserts the renderer
        never emits an aggregateRating block for a tenant with no real
        rating/review data on file."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertNotIn("aggregateRating", resp.text)
        self.assertNotIn("Mike R.", resp.text)  # the blueprint's example author

    def test_aggregate_rating_schema_present_only_with_real_data(self):
        tenant_id = self._make_tenant(rating_value=4.9, review_count=214)
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertIn("aggregateRating", resp.text)
        self.assertIn("4.9", resp.text)

    def test_no_faq_schema_ever(self):
        """No FAQPage schema anywhere -- intake collects no structured
        Q&A content to back one, so it's never generated (see
        build_page_context's docstring)."""
        tenant_id = self._make_tenant()
        resp = self.client.get(f"/sites/{tenant_id}/web")
        self.assertNotIn("FAQPage", resp.text)

    def test_no_forbidden_brand_copy_in_rendered_output(self):
        """Governance Manual rule (default per CLAUDE.md until reconciled):
        no em-dashes, no 'AI' language, anywhere in NetBuild.Pro-authored
        copy. This checks the template-authored strings only by using a
        payload with no em-dash/'AI' substrings of its own, so a failure
        here means the *template*, not the input, introduced one."""
        tenant_id = self._make_tenant()
        for path in ("/web", "/web/about", "/web/contact"):
            resp = self.client.get(f"/sites/{tenant_id}{path}")
            for forbidden in _FORBIDDEN_COPY:
                self.assertNotIn(
                    forbidden, resp.text, f"{forbidden!r} found in {path}"
                )


class TestNeverLeak(SiteRenderTestCase):
    def test_internal_fields_never_appear_in_rendered_html(self):
        tenant_id = self._make_tenant()
        for path in (
            "/web",
            "/web/about",
            "/web/contact",
            "/web/services/leak-repair",
            "/web/sitemap.xml",
            "/web/robots.txt",
        ):
            resp = self.client.get(f"/sites/{tenant_id}{path}")
            for field_name, value in _NEVER_LEAK_VALUES.items():
                self.assertNotIn(
                    value, resp.text, f"{field_name}'s value leaked into {path}"
                )


class TestTenantIsolation(SiteRenderTestCase):
    def test_one_tenants_rendered_page_never_contains_another_tenants_data(self):
        tenant_a = self._make_tenant(biz_name="Alpha Plumbing", phone="602-555-0001")
        tenant_b = self._make_tenant(biz_name="Beta Electric", phone="602-555-0002")

        page_a = self.client.get(f"/sites/{tenant_a}/web").text
        page_b = self.client.get(f"/sites/{tenant_b}/web").text

        self.assertIn("Alpha Plumbing", page_a)
        self.assertNotIn("Beta Electric", page_a)
        self.assertNotIn("602-555-0002", page_a)

        self.assertIn("Beta Electric", page_b)
        self.assertNotIn("Alpha Plumbing", page_b)
        self.assertNotIn("602-555-0001", page_b)


class TestUnknownTenant(SiteRenderTestCase):
    def test_unknown_tenant_returns_404_on_every_rendered_route(self):
        for path in (
            "/web",
            "/web/about",
            "/web/contact",
            "/web/reviews",
            "/web/services/anything",
            "/web/sitemap.xml",
            "/web/robots.txt",
        ):
            resp = self.client.get(f"/sites/no_such_tenant_at_all{path}")
            self.assertEqual(resp.status_code, 404, path)

    def test_invalid_tenant_id_returns_404_not_500(self):
        resp = self.client.get("/sites/bad id with spaces/web")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
