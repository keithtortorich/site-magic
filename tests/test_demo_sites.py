"""Fixture-shape tests for webstaffr/demo_sites.py -- guards the
no-fabrication and reserved-namespace invariants ADR-030 and the prior
STANDUP_2026-08-09 demo cleanup both depend on."""

import re
import unittest

from webstaffr.demo_sites import (
    DEMO_FIXTURES,
    RESERVED_TENANT_PREFIX,
    is_reserved_tenant_id,
)
from webstaffr.intake import generate_tenant_id
from webstaffr.trade_presets import SUPPORTED_INDUSTRIES

_EM_DASH = "—"
_RESERVED_PHONE_BLOCK = re.compile(r"^\(555\) 01\d\d$")


class DemoFixtureShapeTests(unittest.TestCase):
    def test_every_supported_industry_except_other_has_a_demo(self):
        covered = {fixture.industry_key for fixture in DEMO_FIXTURES.values()}
        expected = set(SUPPORTED_INDUSTRIES) - {"Other"}
        self.assertEqual(covered, expected)

    def test_no_fabricated_review_data(self):
        for slug, fixture in DEMO_FIXTURES.items():
            facts = fixture.verified_facts
            for banned_field in ("rating_value", "review_count", "testimonials", "certifications", "license_number"):
                self.assertNotIn(banned_field, facts, f"{slug} leaks {banned_field}")

    def test_no_em_dashes_anywhere_in_copy(self):
        for slug, fixture in DEMO_FIXTURES.items():
            for key, value in fixture.verified_facts.items():
                if isinstance(value, str):
                    self.assertNotIn(_EM_DASH, value, f"{slug}.{key} contains an em-dash")
                if isinstance(value, list):
                    for item in value:
                        self.assertNotIn(_EM_DASH, str(item), f"{slug}.{key} contains an em-dash")

    def test_phone_numbers_in_reserved_fictional_block(self):
        for slug, fixture in DEMO_FIXTURES.items():
            phone = fixture.verified_facts["phone"]
            self.assertRegex(phone, _RESERVED_PHONE_BLOCK, f"{slug} phone {phone!r} not in reserved block")

    def test_phone_numbers_are_unique_per_demo(self):
        phones = [fixture.verified_facts["phone"] for fixture in DEMO_FIXTURES.values()]
        self.assertEqual(len(phones), len(set(phones)))

    def test_emails_on_reserved_example_domain(self):
        for slug, fixture in DEMO_FIXTURES.items():
            email = fixture.verified_facts["email"]
            self.assertTrue(email.endswith(".example.com"), f"{slug} email {email!r} not on example.com")

    def test_reserved_tenant_ids_start_with_prefix(self):
        for slug, fixture in DEMO_FIXTURES.items():
            self.assertTrue(fixture.reserved_tenant_id.startswith(RESERVED_TENANT_PREFIX))
            self.assertTrue(is_reserved_tenant_id(fixture.reserved_tenant_id))

    def test_reserved_tenant_ids_are_unique(self):
        ids = [fixture.reserved_tenant_id for fixture in DEMO_FIXTURES.values()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_real_generated_tenant_id_never_collides_with_reserved_namespace(self):
        # Structural guarantee (sanitize_slug's strip("_")) plus the
        # explicit assertion added in intake.generate_tenant_id() -- this
        # test proves the invariant holds for the actual code path real
        # customers go through, not just for hand-picked demo slugs.
        for slug in DEMO_FIXTURES:
            biz_name = f"_demo_{slug} Services"
            tenant_id = generate_tenant_id(biz_name)
            self.assertFalse(is_reserved_tenant_id(tenant_id), tenant_id)

    def test_verified_facts_have_required_public_projection_fields(self):
        required = {"tenant_id", "biz_name", "phone", "email", "industry", "service_area", "tagline", "differentiator", "services", "plan"}
        for slug, fixture in DEMO_FIXTURES.items():
            missing = required - fixture.verified_facts.keys()
            self.assertFalse(missing, f"{slug} missing {missing}")

    def test_plan_is_valid(self):
        for slug, fixture in DEMO_FIXTURES.items():
            self.assertEqual(fixture.verified_facts["plan"], "office_staff")


if __name__ == "__main__":
    unittest.main()
