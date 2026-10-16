"""Tests for Sam's pricing estimation logic."""

import unittest

from webstaffr.workers.sam.pricing import PricingEngine


class TestPricingEngine(unittest.TestCase):
    def test_generate_estimate_known_service(self):
        """generate_estimate returns correct range for known service."""
        estimate = PricingEngine.generate_estimate(
            service_scope="AC Repair on my split system",
            industry="HVAC",
            urgency="routine",
        )

        # AC Repair in HVAC: $200-600
        self.assertGreaterEqual(estimate.estimated_range_low, 200)
        self.assertLessEqual(estimate.estimated_range_high, 600)
        self.assertIn("site inspection", estimate.caveat.lower())
        self.assertEqual(estimate.industry, "HVAC")

    def test_generate_estimate_unknown_service_fallback(self):
        """generate_estimate returns contact-for-quote for unknown service."""
        estimate = PricingEngine.generate_estimate(
            service_scope="some weird service that doesn't exist",
            industry="HVAC",
            urgency="routine",
        )

        # Should default to contact for quote
        self.assertEqual(estimate.estimated_range_low, 0)
        self.assertEqual(estimate.estimated_range_high, 0)
        self.assertIn("contact", estimate.caveat.lower())

    def test_generate_estimate_urgency_emergency(self):
        """generate_estimate applies 1.5x multiplier for emergency."""
        routine = PricingEngine.generate_estimate(
            service_scope="AC Repair",
            industry="HVAC",
            urgency="routine",
        )

        emergency = PricingEngine.generate_estimate(
            service_scope="AC Repair",
            industry="HVAC",
            urgency="emergency",
        )

        # Emergency should be ~1.5x routine
        self.assertGreater(emergency.estimated_range_high, routine.estimated_range_high)
        self.assertIn("surcharge", emergency.caveat.lower())

    def test_generate_estimate_urgency_urgent(self):
        """generate_estimate applies 1.2x multiplier for urgent."""
        routine = PricingEngine.generate_estimate(
            service_scope="AC Repair",
            industry="HVAC",
            urgency="routine",
        )

        urgent = PricingEngine.generate_estimate(
            service_scope="AC Repair",
            industry="HVAC",
            urgency="urgent",
        )

        # Urgent should be 1.2x routine
        self.assertGreater(urgent.estimated_range_high, routine.estimated_range_high)

    def test_generate_estimate_multiple_services(self):
        """generate_estimate identifies multiple services in scope."""
        estimate = PricingEngine.generate_estimate(
            service_scope="I need AC repair and duct cleaning",
            industry="HVAC",
            urgency="routine",
        )

        # Should identify both services
        self.assertIn("AC Repair", estimate.services_identified)
        self.assertIn("Air Quality / Duct Cleaning", estimate.services_identified)

        # Range should be wider than single service (max of both)
        self.assertGreater(estimate.estimated_range_high, 600)

    def test_generate_estimate_low_less_than_high(self):
        """generate_estimate always has low < high."""
        for industry in ["HVAC", "Plumber", "Electrician"]:
            for scope in ["Basic service", "Complex service"]:
                estimate = PricingEngine.generate_estimate(
                    service_scope=scope,
                    industry=industry,
                    urgency="routine",
                )
                if estimate.estimated_range_low > 0:
                    self.assertLess(estimate.estimated_range_low, estimate.estimated_range_high)

    def test_generate_estimate_all_supported_industries(self):
        """generate_estimate works for all supported industries."""
        supported = [
            "HVAC",
            "Plumber",
            "Electrician",
            "Roofing",
            "Water Damage Restoration",
            "Garage Door Repair",
            "Pest Control",
            "Landscaping",
            "Tree Service",
            "Cleaning Services",
        ]

        for industry in supported:
            estimate = PricingEngine.generate_estimate(
                service_scope=f"I need {industry.lower()} service",
                industry=industry,
                urgency="routine",
            )
            self.assertEqual(estimate.industry, industry)
            self.assertIsNotNone(estimate.caveat)

    def test_extract_services_plumber(self):
        """_extract_services correctly identifies plumbing services."""
        services = PricingEngine._extract_services(
            "I need leak detection and repair plus a water heater replacement",
            "Plumber",
        )

        self.assertIn("Leak Detection & Repair", services)
        self.assertIn("Water Heater Replacement", services)

    def test_extract_services_case_insensitive(self):
        """_extract_services is case-insensitive."""
        services = PricingEngine._extract_services(
            "i need ROOF REPAIR and storm damage inspection",
            "Roofing",
        )

        self.assertIn("Roof Repair", services)
        self.assertIn("Storm Damage Inspection", services)

    def test_urgency_multiplier_values(self):
        """_urgency_multiplier returns correct multipliers."""
        self.assertEqual(PricingEngine._urgency_multiplier("routine"), 1.0)
        self.assertEqual(PricingEngine._urgency_multiplier("urgent"), 1.2)
        self.assertEqual(PricingEngine._urgency_multiplier("emergency"), 1.5)
        self.assertEqual(PricingEngine._urgency_multiplier("unknown"), 1.0)

    def test_location_multiplier_returns_one(self):
        """_location_multiplier returns 1.0 for MVP (no location premium yet)."""
        self.assertEqual(PricingEngine._location_multiplier("Phoenix, AZ"), 1.0)
        self.assertEqual(PricingEngine._location_multiplier("Rural Area"), 1.0)

    def test_caveat_text_format(self):
        """_build_caveat returns appropriate messages."""
        routine_caveat = PricingEngine._build_caveat("routine")
        emergency_caveat = PricingEngine._build_caveat("emergency")

        self.assertIn("site inspection", routine_caveat.lower())
        self.assertIn("site inspection", emergency_caveat.lower())
        self.assertIn("surcharge", emergency_caveat.lower())


if __name__ == "__main__":
    unittest.main()
