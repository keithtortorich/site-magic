"""AOKAI 100-point lead scoring rubric for Leo.

Implements the complete scoring system from docs/LEAD_ENGINE.md:
- Accessibility (35 points): phone answer, owner contact, text/email capability
- Business Size (20 points): employee count, vehicle fleet, hiring signals, locations
- Digital Maturity (20 points): website presence, booking system, CRM/scheduling
- Revenue Potential (15 points): industry/niche
- Buying Signals (10 points): office-staff hiring, active reviews, financing, service history

Never fabricates scores; uses real data only. Missing fields = 0 points in
that category.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Industry-to-revenue-potential mapping from LEAD_ENGINE.md
INDUSTRY_REVENUE_SCORES = {
    "HVAC": 15,
    "Water Damage": 14,
    "Roofing": 13,
    "Plumbing": 12,
    "Electrical": 11,
    "Garage Door": 10,
    "Pest Control": 9,
    "Landscaping": 8,
    "Tree Service": 8,
    "Cleaning Services": 7,
    "Other": 6,
}


@dataclass
class AOKAIScore:
    """Result of a complete AOKAI scoring."""

    score_accessibility: int  # 0-35
    score_business_size: int  # 0-20
    score_digital_maturity: int  # 0-20
    score_revenue_potential: int  # 0-15
    score_buying_signals: int  # 0-10
    score_total: int  # 0-100

    @property
    def tier(self) -> int:
        """Maps score to tier: 1 (85-100), 2 (70-84), 3 (55-69), 4 (<55)."""
        if self.score_total >= 85:
            return 1
        if self.score_total >= 70:
            return 2
        if self.score_total >= 55:
            return 3
        return 4


def score_accessibility(
    phone_answered: Optional[bool] = None,
    owner_answered: Optional[bool] = None,
    text_enabled: Optional[bool] = None,
    email: Optional[str] = None,
) -> int:
    """Score accessibility (0-35 points).

    Accessibility 35: Phone answered by a human (+15), owner answers (+10),
    text-enabled (+5), email available (+5).
    """
    points = 0

    if phone_answered:
        points += 15
    if owner_answered:
        points += 10
    if text_enabled:
        points += 5
    if email:  # Just check if email field is present and non-empty
        points += 5

    return min(points, 35)


def score_business_size(
    employee_count: Optional[int] = None,
    vehicle_count: Optional[int] = None,
    currently_hiring: Optional[bool] = None,
    multiple_locations: Optional[bool] = None,
) -> int:
    """Score business size (0-20 points).

    Business size 20: 3-20 employees (+8), 2-8 vehicles (+5), currently hiring
    (+3), multiple locations (+4).
    """
    points = 0

    if employee_count is not None and 3 <= employee_count <= 20:
        points += 8
    if vehicle_count is not None and 2 <= vehicle_count <= 8:
        points += 5
    if currently_hiring:
        points += 3
    if multiple_locations:
        points += 4

    return min(points, 20)


def score_digital_maturity(
    has_website: Optional[bool] = None,
    has_booking_system: Optional[bool] = None,
    has_crm: Optional[bool] = None,
    has_diy_platform: Optional[bool] = None,
) -> int:
    """Score digital maturity (0-20 points).

    Digital maturity 20: No website (+8), no booking system (+5), no CRM/
    scheduling (+5), DIY platform only (+2).

    Higher points for less digital sophistication (more receptionist work).

    Each check is `is False`, not `not x`, because these three fields are
    tri-state: True (has it), False (confirmed doesn't), None (not researched
    yet). `not None` is True, so a truthiness check would award the full 18
    points for absence to every lead we simply haven't looked into -- inflating
    unresearched leads toward tier 1 and putting them ahead of leads we actually
    qualified. Unknown must score zero.
    """
    points = 0

    if has_website is False:
        points += 8
    if has_booking_system is False:
        points += 5
    if has_crm is False:
        points += 5
    if has_diy_platform:
        points += 2

    return min(points, 20)


def score_revenue_potential(industry: Optional[str] = None) -> int:
    """Score revenue potential (0-15 points).

    Revenue potential 15: HVAC (+15), Water Damage (+14), Roofing (+13),
    Plumbing (+12), Electrical (+11), others (+6-10).

    Maps industry to points via INDUSTRY_REVENUE_SCORES. Default is "Other" (6).
    """
    if not industry:
        return INDUSTRY_REVENUE_SCORES.get("Other", 6)

    # Try exact match first
    score = INDUSTRY_REVENUE_SCORES.get(industry)
    if score is not None:
        return min(score, 15)

    # Try case-insensitive match
    for key, value in INDUSTRY_REVENUE_SCORES.items():
        if key.lower() == industry.lower():
            return min(value, 15)

    # Default to "Other"
    return INDUSTRY_REVENUE_SCORES.get("Other", 6)


def score_buying_signals(
    hiring_office_staff: Optional[bool] = None,
    active_reviews_count: Optional[int] = None,
    offers_financing: Optional[bool] = None,
    recent_service_history: Optional[bool] = None,
) -> int:
    """Score buying signals (0-10 points).

    Buying signals 10: Hiring office staff (+3), active reviews 2+ (+2),
    offers financing (+2), recent service history (+3).
    """
    points = 0

    if hiring_office_staff:
        points += 3
    if active_reviews_count is not None and active_reviews_count >= 2:
        points += 2
    if offers_financing:
        points += 2
    if recent_service_history:
        points += 3

    return min(points, 10)


def calculate_aokai_score(
    phone_answered: Optional[bool] = None,
    owner_answered: Optional[bool] = None,
    text_enabled: Optional[bool] = None,
    email: Optional[str] = None,
    employee_count: Optional[int] = None,
    vehicle_count: Optional[int] = None,
    currently_hiring: Optional[bool] = None,
    multiple_locations: Optional[bool] = None,
    has_website: Optional[bool] = None,
    has_booking_system: Optional[bool] = None,
    has_crm: Optional[bool] = None,
    has_diy_platform: Optional[bool] = None,
    industry: Optional[str] = None,
    hiring_office_staff: Optional[bool] = None,
    active_reviews_count: Optional[int] = None,
    offers_financing: Optional[bool] = None,
    recent_service_history: Optional[bool] = None,
) -> AOKAIScore:
    """Calculate complete AOKAI score from lead signals.

    Returns AOKAIScore with all category breakdowns and total score (0-100).
    Tier is computed from total score (1, 2, 3, or 4).
    """
    acc = score_accessibility(phone_answered, owner_answered, text_enabled, email)
    size = score_business_size(employee_count, vehicle_count, currently_hiring, multiple_locations)
    maturity = score_digital_maturity(has_website, has_booking_system, has_crm, has_diy_platform)
    revenue = score_revenue_potential(industry)
    signals = score_buying_signals(hiring_office_staff, active_reviews_count, offers_financing, recent_service_history)
    total = acc + size + maturity + revenue + signals

    return AOKAIScore(
        score_accessibility=acc,
        score_business_size=size,
        score_digital_maturity=maturity,
        score_revenue_potential=revenue,
        score_buying_signals=signals,
        score_total=total,
    )
