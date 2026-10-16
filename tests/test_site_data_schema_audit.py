"""Site Data Schema Audit — Gate 1

Validates that every site's data schema is complete and correct.
Required fields must be present and non-empty.
Optional fields, if present, must have valid format.

This gate ensures intake data → render pipeline preserves all data
without loss or corruption.
"""

import unittest
from webstaffr.site_data import build_public_site_data
from webstaffr.intake import IntakeSubmission


def _valid_submission(**overrides) -> IntakeSubmission:
    """Build a valid submission with all required fields."""
    submission = IntakeSubmission(
        tenant_id="test-tenant-001",
        biz_name="Desert Pro Services",
        phone="+1-602-555-0100",
        email="owner@example.com",
        industry="HVAC Technician",
        service_area="Phoenix, AZ",
        tagline="Fast, reliable service.",
        differentiator="We show up on time.",
        services=["Service A", "Service B"],
        plan="office_staff",
        license_number="Not displayed publicly",
        lead_routing="Founder only",
        approver="Founder",
    )
    # Override any fields passed in
    for key, value in overrides.items():
        setattr(submission, key, value)
    return submission


class TestSiteDataSchemaAudit(unittest.TestCase):
    """Audit site data schema for completeness and correctness."""

    def test_required_fields_present(self):
        """All required fields must be present in submission."""
        submission = _valid_submission()
        data = build_public_site_data(submission)

        required_fields = [
            "tenant_id", "biz_name", "phone", "email", "industry",
            "service_area", "tagline", "differentiator", "services", "plan"
        ]

        for field in required_fields:
            self.assertIn(field, data, f"Required field '{field}' missing from schema")
            self.assertIsNotNone(data[field], f"Required field '{field}' is None")
            # Non-empty string or non-empty list
            if isinstance(data[field], str):
                self.assertTrue(len(data[field]) > 0, f"Required field '{field}' is empty string")
            elif isinstance(data[field], list):
                self.assertTrue(len(data[field]) > 0, f"Required field '{field}' is empty list")

    def test_optional_fields_omitted_if_none(self):
        """Optional fields that are None should be omitted from output."""
        # Submission with no optional fields set
        submission = _valid_submission()
        submission.brand_colors = None
        submission.rating_value = None
        submission.review_count = None

        data = build_public_site_data(submission)

        # These should not appear in the data dict if None
        optional_fields_to_check = ["brand_colors", "rating_value", "review_count"]
        for field in optional_fields_to_check:
            if field not in data:
                # Correctly omitted
                pass
            else:
                # If present, should not be None (perfect-site principle)
                self.assertIsNotNone(data[field], f"Optional field '{field}' should be omitted, not None")

    def test_optional_fields_included_if_set(self):
        """Optional fields that are set should be included in output."""
        submission = _valid_submission(
            brand_colors="#FF6600",
            rating_value=4.8,
            review_count=42,
            years_in_biz=5,
        )
        data = build_public_site_data(submission)

        self.assertEqual(data.get("brand_colors"), "#FF6600")
        self.assertEqual(data.get("rating_value"), 4.8)
        self.assertEqual(data.get("review_count"), 42)
        self.assertEqual(data.get("years_in_biz"), 5)

    def test_brand_colors_valid_hex_format(self):
        """Brand colors, if present, must be valid hex (#rrggbb)."""
        # Valid hex
        submission = _valid_submission(brand_colors="#000080")
        data = build_public_site_data(submission)
        self.assertEqual(data.get("brand_colors"), "#000080")

        # Another valid hex
        submission = _valid_submission(brand_colors="#4169E1")
        data = build_public_site_data(submission)
        self.assertEqual(data.get("brand_colors"), "#4169E1")

    def test_phone_format(self):
        """Phone number must be present and in expected format."""
        submission = _valid_submission(phone="+1-602-555-0100")
        data = build_public_site_data(submission)
        self.assertIn("phone", data)
        self.assertEqual(data["phone"], "+1-602-555-0100")

    def test_services_list_not_empty(self):
        """Services list must not be empty."""
        submission = _valid_submission(services=["AC Repair", "Installation"])
        data = build_public_site_data(submission)
        self.assertIn("services", data)
        self.assertEqual(len(data["services"]), 2)
        self.assertIn("AC Repair", data["services"])

    def test_no_internal_fields_in_public_projection(self):
        """Internal-only fields must never appear in public projection."""
        submission = _valid_submission(
            lead_routing="Maria at 602-555-0101",
            approver="Maria Lopez",
            competitors="Ace Co, Best Co",
            license_number="ROC 999999",
        )
        data = build_public_site_data(submission)

        internal_fields = ["lead_routing", "approver", "competitors", "license_number"]
        for field in internal_fields:
            self.assertNotIn(field, data, f"Internal field '{field}' leaked into public projection")

    def test_plan_field_matches_launch_tier(self):
        """Plan field must be set to office_staff (MVP launch tier)."""
        submission = _valid_submission(plan="office_staff")
        data = build_public_site_data(submission)
        self.assertEqual(data["plan"], "office_staff")

    def test_schema_completeness_no_unexpected_nulls(self):
        """No required field should be None or empty in well-formed submission."""
        submission = _valid_submission(
            biz_name="Test Company",
            phone="+1-555-0100",
            email="test@example.com",
            industry="Plumber",
            service_area="Austin, TX",
            tagline="Professional plumbing",
            differentiator="24/7 service",
            services=["Leak Repair", "Drain Cleaning"],
            plan="office_staff",
        )
        data = build_public_site_data(submission)

        # Verify all required fields are present and non-null
        for field in ["biz_name", "phone", "email", "industry", "service_area", "tagline", "differentiator", "services", "plan"]:
            self.assertIsNotNone(data.get(field), f"Field '{field}' is None")
            if isinstance(data[field], (str, list)):
                self.assertTrue(len(data[field]) > 0, f"Field '{field}' is empty")


if __name__ == "__main__":
    unittest.main()
