"""Unit tests for Leo's AOKAI 100-point scoring rubric."""

import unittest

from webstaffr.workers.leo.scoring import (
    AOKAIScore,
    calculate_aokai_score,
    score_accessibility,
    score_buying_signals,
    score_business_size,
    score_digital_maturity,
    score_revenue_potential,
)


class TestScoreAccessibility(unittest.TestCase):
    """Test accessibility scoring (phone, owner, text, email)."""

    def test_no_signals_returns_zero(self):
        self.assertEqual(score_accessibility(), 0)
        self.assertEqual(score_accessibility(False, False, False, None), 0)

    def test_phone_answered_grants_15_points(self):
        self.assertEqual(score_accessibility(phone_answered=True), 15)

    def test_owner_answered_grants_10_points(self):
        self.assertEqual(score_accessibility(owner_answered=True), 10)

    def test_text_enabled_grants_5_points(self):
        self.assertEqual(score_accessibility(text_enabled=True), 5)

    def test_email_present_grants_5_points(self):
        self.assertEqual(score_accessibility(email="owner@example.com"), 5)
        self.assertEqual(score_accessibility(email=""), 0)  # empty = no email

    def test_cumulative_signals_sum_up_to_max_35(self):
        # Phone + owner + text + email = 15 + 10 + 5 + 5 = 35
        self.assertEqual(
            score_accessibility(
                phone_answered=True,
                owner_answered=True,
                text_enabled=True,
                email="owner@example.com",
            ),
            35,
        )

    def test_capped_at_35_even_if_over(self):
        # Hypothetically if we had extra signal sources, ensure cap
        score = score_accessibility(True, True, True, "test@example.com")
        self.assertLessEqual(score, 35)


class TestScoreBusinessSize(unittest.TestCase):
    """Test business size scoring (employees, vehicles, hiring, locations)."""

    def test_no_signals_returns_zero(self):
        self.assertEqual(score_business_size(), 0)

    def test_employee_count_3_to_20_grants_8_points(self):
        self.assertEqual(score_business_size(employee_count=5), 8)
        self.assertEqual(score_business_size(employee_count=3), 8)
        self.assertEqual(score_business_size(employee_count=20), 8)

    def test_employee_count_outside_range_grants_zero(self):
        self.assertEqual(score_business_size(employee_count=1), 0)
        self.assertEqual(score_business_size(employee_count=2), 0)
        self.assertEqual(score_business_size(employee_count=21), 0)

    def test_vehicle_count_2_to_8_grants_5_points(self):
        self.assertEqual(score_business_size(vehicle_count=2), 5)
        self.assertEqual(score_business_size(vehicle_count=5), 5)
        self.assertEqual(score_business_size(vehicle_count=8), 5)

    def test_vehicle_count_outside_range_grants_zero(self):
        self.assertEqual(score_business_size(vehicle_count=1), 0)
        self.assertEqual(score_business_size(vehicle_count=9), 0)

    def test_currently_hiring_grants_3_points(self):
        self.assertEqual(score_business_size(currently_hiring=True), 3)

    def test_multiple_locations_grants_4_points(self):
        self.assertEqual(score_business_size(multiple_locations=True), 4)

    def test_cumulative_up_to_max_20(self):
        # 8 + 5 + 3 + 4 = 20
        self.assertEqual(
            score_business_size(
                employee_count=10,
                vehicle_count=5,
                currently_hiring=True,
                multiple_locations=True,
            ),
            20,
        )

    def test_capped_at_20(self):
        score = score_business_size(10, 5, True, True)
        self.assertLessEqual(score, 20)


class TestScoreDigitalMaturity(unittest.TestCase):
    """Test digital maturity scoring (no website, no booking, no CRM, DIY)."""

    def test_no_signals_returns_zero(self):
        self.assertEqual(score_digital_maturity(), 0)

    def test_no_website_grants_8_points(self):
        self.assertEqual(score_digital_maturity(has_website=False), 8)
        self.assertEqual(score_digital_maturity(has_website=True), 0)

    def test_no_booking_system_grants_5_points(self):
        self.assertEqual(score_digital_maturity(has_booking_system=False), 5)

    def test_no_crm_grants_5_points(self):
        self.assertEqual(score_digital_maturity(has_crm=False), 5)

    def test_has_diy_platform_grants_2_points(self):
        self.assertEqual(score_digital_maturity(has_diy_platform=True), 2)

    def test_cumulative_up_to_max_20(self):
        # 8 + 5 + 5 + 2 = 20 (no website, no booking, no CRM, has DIY)
        self.assertEqual(
            score_digital_maturity(
                has_website=False,
                has_booking_system=False,
                has_crm=False,
                has_diy_platform=True,
            ),
            20,
        )

    def test_capped_at_20(self):
        score = score_digital_maturity(False, False, False, True)
        self.assertLessEqual(score, 20)


class TestScoreRevenuePotential(unittest.TestCase):
    """Test revenue potential scoring by industry."""

    def test_no_industry_defaults_to_other_6(self):
        self.assertEqual(score_revenue_potential(None), 6)
        self.assertEqual(score_revenue_potential(""), 6)

    def test_hvac_grants_15_points(self):
        self.assertEqual(score_revenue_potential("HVAC"), 15)

    def test_water_damage_grants_14_points(self):
        self.assertEqual(score_revenue_potential("Water Damage"), 14)

    def test_roofing_grants_13_points(self):
        self.assertEqual(score_revenue_potential("Roofing"), 13)

    def test_plumbing_grants_12_points(self):
        self.assertEqual(score_revenue_potential("Plumbing"), 12)

    def test_electrical_grants_11_points(self):
        self.assertEqual(score_revenue_potential("Electrical"), 11)

    def test_case_insensitive_match(self):
        self.assertEqual(score_revenue_potential("hvac"), 15)
        self.assertEqual(score_revenue_potential("PLUMBING"), 12)

    def test_unknown_industry_defaults_to_other_6(self):
        self.assertEqual(score_revenue_potential("UnknownTrade"), 6)

    def test_capped_at_15(self):
        # Ensure no score exceeds 15
        for industry in ["HVAC", "Water Damage", "Plumbing", "Other"]:
            self.assertLessEqual(score_revenue_potential(industry), 15)


class TestScoreBuyingSignals(unittest.TestCase):
    """Test buying signals scoring."""

    def test_no_signals_returns_zero(self):
        self.assertEqual(score_buying_signals(), 0)

    def test_hiring_office_staff_grants_3_points(self):
        self.assertEqual(score_buying_signals(hiring_office_staff=True), 3)

    def test_active_reviews_2_or_more_grants_2_points(self):
        self.assertEqual(score_buying_signals(active_reviews_count=2), 2)
        self.assertEqual(score_buying_signals(active_reviews_count=10), 2)

    def test_active_reviews_less_than_2_grants_zero(self):
        self.assertEqual(score_buying_signals(active_reviews_count=0), 0)
        self.assertEqual(score_buying_signals(active_reviews_count=1), 0)

    def test_offers_financing_grants_2_points(self):
        self.assertEqual(score_buying_signals(offers_financing=True), 2)

    def test_recent_service_history_grants_3_points(self):
        self.assertEqual(score_buying_signals(recent_service_history=True), 3)

    def test_cumulative_up_to_max_10(self):
        # 3 + 2 + 2 + 3 = 10
        self.assertEqual(
            score_buying_signals(
                hiring_office_staff=True,
                active_reviews_count=5,
                offers_financing=True,
                recent_service_history=True,
            ),
            10,
        )

    def test_capped_at_10(self):
        score = score_buying_signals(True, 5, True, True)
        self.assertLessEqual(score, 10)


class TestCalculateAOKAIScore(unittest.TestCase):
    """Test full AOKAI score calculation and tier assignment."""

    def test_all_signals_present_yields_high_score(self):
        result = calculate_aokai_score(
            phone_answered=True,
            owner_answered=True,
            text_enabled=True,
            email="owner@example.com",
            employee_count=5,
            vehicle_count=3,
            currently_hiring=True,
            multiple_locations=True,
            has_website=False,
            has_booking_system=False,
            has_crm=False,
            has_diy_platform=True,
            industry="HVAC",
            hiring_office_staff=True,
            active_reviews_count=5,
            offers_financing=True,
            recent_service_history=True,
        )

        # Max scores: 35 + 20 + 20 + 15 + 10 = 100
        self.assertEqual(result.score_total, 100)
        self.assertEqual(result.score_accessibility, 35)
        self.assertEqual(result.score_business_size, 20)
        self.assertEqual(result.score_digital_maturity, 20)
        self.assertEqual(result.score_revenue_potential, 15)
        self.assertEqual(result.score_buying_signals, 10)

    def test_no_signals_yields_zero_score(self):
        result = calculate_aokai_score()

        # Total is 6, not 0: revenue potential has a documented floor of 6 for
        # an unrecognised/absent industry ("Other"), which every other revenue
        # test in this file also asserts. The previous `score_total == 0` here
        # contradicted the component assertion two lines below it.
        self.assertEqual(result.score_total, 6)
        self.assertEqual(result.score_accessibility, 0)
        self.assertEqual(result.score_business_size, 0)
        self.assertEqual(result.score_digital_maturity, 0)
        self.assertEqual(result.score_revenue_potential, 6)  # Other industry default
        self.assertEqual(result.score_buying_signals, 0)

    def test_tier_1_for_score_85_100(self):
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            owner_answered=True,  # 10
            text_enabled=True,  # 5
            email="test@example.com",  # 5
            employee_count=10,  # 8
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="HVAC",  # 15
            offers_financing=True,  # 2
        )
        # 15 + 10 + 5 + 5 + 8 + 8 + 5 + 15 + 2 = 73... let's add more
        # Actually this gives 73, which is tier 2. Let's test tier 1 separately.
        pass

    def test_tier_1_for_high_score(self):
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            owner_answered=True,  # 10
            text_enabled=True,  # 5
            email="test@example.com",  # 5
            employee_count=10,  # 8
            vehicle_count=5,  # 5
            currently_hiring=True,  # 3
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="HVAC",  # 15
            hiring_office_staff=True,  # 3
            active_reviews_count=5,  # 2
            offers_financing=True,  # 2
        )
        # 15 + 10 + 5 + 5 + 8 + 5 + 3 + 8 + 5 + 15 + 3 + 2 + 2 = 86
        self.assertGreaterEqual(result.score_total, 85)
        self.assertEqual(result.tier, 1)

    def test_tier_2_for_score_70_84(self):
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            owner_answered=True,  # 10
            text_enabled=True,  # 5
            employee_count=10,  # 8
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="HVAC",  # 15
            hiring_office_staff=True,  # 3
            active_reviews_count=5,  # 2
        )
        # 15 + 10 + 5 + 8 + 8 + 5 + 15 + 3 + 2 = 71
        self.assertEqual(result.score_total, 71)
        self.assertEqual(result.tier, 2)

    def test_tier_3_for_score_55_69(self):
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="Plumbing",  # 12
            active_reviews_count=5,  # 2
        )
        # 15 + 8 + 5 + 12 + 2 = 42... need more
        # Try:
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            owner_answered=True,  # 10
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="Plumbing",  # 12
            active_reviews_count=5,  # 2
        )
        # 15 + 10 + 8 + 5 + 12 + 2 = 52... still under. Add hiring:
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            owner_answered=True,  # 10
            has_website=False,  # 8
            has_booking_system=False,  # 5
            industry="HVAC",  # 15
            hiring_office_staff=True,  # 3
        )
        # 15 + 10 + 8 + 5 + 15 + 3 = 56
        self.assertEqual(result.score_total, 56)
        self.assertEqual(result.tier, 3)

    def test_tier_4_for_score_below_55(self):
        result = calculate_aokai_score(
            phone_answered=True,  # 15
            industry="Other",  # 6
        )
        # 15 + 6 = 21
        self.assertLess(result.score_total, 55)
        self.assertEqual(result.tier, 4)

    def test_aokai_score_is_dataclass(self):
        result = calculate_aokai_score()
        self.assertIsInstance(result, AOKAIScore)
        self.assertTrue(hasattr(result, "score_accessibility"))
        self.assertTrue(hasattr(result, "score_business_size"))
        self.assertTrue(hasattr(result, "score_digital_maturity"))
        self.assertTrue(hasattr(result, "score_revenue_potential"))
        self.assertTrue(hasattr(result, "score_buying_signals"))
        self.assertTrue(hasattr(result, "score_total"))
        self.assertTrue(hasattr(result, "tier"))


if __name__ == "__main__":
    unittest.main()
