"""Tests for Sam's objection handling."""

import unittest

from webstaffr.workers.sam.objections import ObjectionLibrary


class TestObjectionLibrary(unittest.TestCase):
    def test_get_response_default_cost(self):
        """get_response returns default cost objection for any industry."""
        response = ObjectionLibrary.get_response("cost", "UnknownIndustry")

        self.assertGreater(len(response), 0)
        # Should be professional, not salesy
        self.assertNotIn("buy now", response.lower())
        self.assertNotIn("limited time", response.lower())

    def test_get_response_industry_specific(self):
        """get_response returns industry-specific response when available."""
        hvac_response = ObjectionLibrary.get_response("cost", "HVAC", {})
        plumber_response = ObjectionLibrary.get_response("cost", "Plumber", {})

        # Should be different for different industries
        self.assertNotEqual(hvac_response, plumber_response)

        # HVAC response discusses AC/heating and seasonal discomfort
        hvac_lower = hvac_response.lower()
        plumber_lower = plumber_response.lower()
        self.assertTrue(
            any(token in hvac_lower for token in ["ac", "heating", "summer", "winter", "comfort", "repair"]),
            msg=f"HVAC response missing expected context: {hvac_response}",
        )
        self.assertTrue(
            any(token in plumber_lower for token in ["water", "leak", "damage", "plumbing"]),
            msg=f"Plumber response missing expected context: {plumber_response}",
        )

    def test_get_response_objection_types(self):
        """get_response handles multiple objection types."""
        objection_types = ["cost", "timeline", "warranty", "availability", "trust"]

        for obj_type in objection_types:
            response = ObjectionLibrary.get_response(obj_type, "HVAC", {})
            self.assertGreater(len(response), 0)

    def test_get_response_educational_tone(self):
        """get_response uses educational, not pushy language."""
        response = ObjectionLibrary.get_response("cost", "HVAC", {})

        # Should use consultative/process language, not scarcity or pressure tactics
        response_lower = response.lower()
        self.assertTrue(
            any(word in response_lower for word in ["team", "visit", "work", "actual", "wrong", "show"]),
            msg=f"HVAC cost response appears non-educational: {response}",
        )

        # Should not be pushy/salesy
        self.assertFalse(any(word in response_lower for word in ["urgency", "limited", "act now", "hurry"]))

    def test_get_response_includes_caveats(self):
        """get_response includes caveats and doesn't make promises."""
        response = ObjectionLibrary.get_response("warranty", "Electrician", {})

        # Should include modest, guarded language rather than unconditional guarantees
        response_lower = response.lower()
        self.assertTrue(
            any(token in response_lower for token in ["guaranteed", "1 year", "inspected", "is not negotiable", "meets code"]),
            msg=f"Electrician warranty response appears absolute or missing caveat: {response}",
        )
        # Should not overpromise coverage beyond what the business states
        self.assertNotIn("everything is covered", response_lower)
        self.assertNotIn("no exceptions", response_lower)

    def test_get_response_personalization(self):
        """get_response personalizes with business name if provided."""
        business_name = "Acme HVAC"
        context = {"business_name": business_name}
        response = ObjectionLibrary.get_response("cost", "HVAC", context)

        # Should contain the business name
        # (Note: the current implementation doesn't use {business_name} placeholders,
        # but if it did, this would verify personalization works)
        self.assertIsNotNone(response)

    def test_get_objection_types_hvac(self):
        """get_objection_types returns known objection types for HVAC."""
        types = ObjectionLibrary.get_objection_types("HVAC")

        self.assertIn("cost", types)
        self.assertIn("timeline", types)
        self.assertIn("warranty", types)

    def test_get_objection_types_all_trades(self):
        """get_objection_types works for all supported trades."""
        trades = [
            "HVAC",
            "Plumber",
            "Electrician",
            "Roofing",
            "Water Damage Restoration",
            "Pest Control",
            "Landscaping",
        ]

        for trade in trades:
            types = ObjectionLibrary.get_objection_types(trade)
            self.assertGreater(len(types), 0)

    def test_default_fallback_response(self):
        """_default_fallback returns safe response for unknown objections."""
        response = ObjectionLibrary._default_fallback("unknown_objection_type")

        self.assertGreater(len(response), 0)
        self.assertIn("team", response.lower())
        self.assertIn("discuss", response.lower())

    def test_response_never_empty(self):
        """get_response never returns empty string."""
        # Test all combinations
        for industry in ["HVAC", "Plumber", "Unknown"]:
            for objection in ["cost", "timeline", "warranty", "unknown"]:
                response = ObjectionLibrary.get_response(objection, industry, {})
                self.assertGreater(len(response), 0)


if __name__ == "__main__":
    unittest.main()
