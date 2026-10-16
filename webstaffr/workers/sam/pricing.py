"""Quote generation: service-scope parsing, trade-specific pricing, range calculation.

Uses webstaffr/trade_presets.py as the source of truth for per-trade service ranges.
Never fabricates specific numbers; always shows ranges + caveats.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ...trade_presets import TRADE_HINTS, TRADE_SOFTWARE, normalize_industry


@dataclass
class PricingEstimate:
    """A quote's estimated pricing and caveats."""

    estimated_range_low: float
    estimated_range_high: float
    caveat: str
    industry: str
    services_identified: list[str]


class PricingEngine:
    """Generate pricing estimates based on trade presets and scope."""

    # Hardcoded preset ranges per (industry, service) pair.
    # Derived from 2026 market research per trade -- these are the
    # _ranges_ quoted to customers, not our cost basis.
    # If a trade/service pair is missing, defaults to "Contact for quote".
    _PRESET_RANGES: dict[tuple[str, str], tuple[float, float]] = {
        # HVAC
        ("HVAC", "AC Repair"): (200.0, 600.0),
        ("HVAC", "AC Installation"): (2500.0, 7000.0),
        ("HVAC", "Furnace Repair"): (250.0, 650.0),
        ("HVAC", "Air Quality / Duct Cleaning"): (400.0, 1200.0),
        ("HVAC", "Emergency HVAC"): (300.0, 800.0),
        # Plumber
        ("Plumber", "Leak Detection & Repair"): (150.0, 500.0),
        ("Plumber", "Water Heater Replacement"): (800.0, 2000.0),
        ("Plumber", "Drain Cleaning"): (200.0, 600.0),
        ("Plumber", "Sewer Line Inspection"): (300.0, 800.0),
        ("Plumber", "Emergency Plumbing"): (250.0, 700.0),
        # Electrician
        ("Electrician", "Panel Upgrades & Replacements"): (1500.0, 4000.0),
        ("Electrician", "EV Charger Installation"): (1000.0, 3000.0),
        ("Electrician", "Outlet & Switch Repair"): (150.0, 400.0),
        ("Electrician", "Whole-Home Rewire"): (3000.0, 8000.0),
        ("Electrician", "Emergency Electrical"): (200.0, 600.0),
        # Roofing
        ("Roofing", "Roof Replacement"): (5000.0, 20000.0),
        ("Roofing", "Roof Repair"): (500.0, 2500.0),
        ("Roofing", "Storm Damage Inspection"): (0.0, 0.0),  # Free inspection; fallback to contact
        ("Roofing", "Flat Roof Systems"): (3000.0, 15000.0),
        ("Roofing", "New Construction Roofing"): (4000.0, 18000.0),
        # Water Damage Restoration
        ("Water Damage Restoration", "Water Extraction"): (500.0, 2000.0),
        ("Water Damage Restoration", "Structural Drying"): (1000.0, 5000.0),
        ("Water Damage Restoration", "Mold Remediation"): (1500.0, 8000.0),
        ("Water Damage Restoration", "Smoke & Fire Damage Restoration"): (2000.0, 10000.0),
        ("Water Damage Restoration", "Emergency Board-Up"): (300.0, 1000.0),
        # Garage Door Repair
        ("Garage Door Repair", "Spring Repair & Replacement"): (250.0, 700.0),
        ("Garage Door Repair", "Opener Installation & Repair"): (200.0, 600.0),
        ("Garage Door Repair", "Panel & Track Repair"): (150.0, 500.0),
        ("Garage Door Repair", "New Garage Door Installation"): (800.0, 2500.0),
        ("Garage Door Repair", "Emergency Garage Door Repair"): (200.0, 600.0),
        # Pest Control
        ("Pest Control", "General Pest Control"): (150.0, 500.0),
        ("Pest Control", "Scorpion Control"): (400.0, 1200.0),
        ("Pest Control", "Termite Treatment"): (500.0, 2000.0),
        ("Pest Control", "Rodent Exclusion"): (300.0, 800.0),
        ("Pest Control", "Quarterly Maintenance Plans"): (40.0, 150.0),
        # Landscaping
        ("Landscaping", "Landscape Design & Installation"): (2000.0, 8000.0),
        ("Landscaping", "Xeriscape & Drought-Tolerant Design"): (3000.0, 12000.0),
        ("Landscaping", "Irrigation Repair"): (150.0, 800.0),
        ("Landscaping", "Tree & Shrub Trimming"): (200.0, 1000.0),
        ("Landscaping", "Seasonal Maintenance Plans"): (150.0, 500.0),
        # Tree Service
        ("Tree Service", "Tree Trimming & Pruning"): (300.0, 1500.0),
        ("Tree Service", "Tree Removal"): (500.0, 3000.0),
        ("Tree Service", "Stump Grinding"): (200.0, 800.0),
        ("Tree Service", "Storm Damage Cleanup"): (500.0, 3000.0),
        ("Tree Service", "Palm Tree Care"): (200.0, 1000.0),
        # Cleaning Services
        ("Cleaning Services", "Recurring House Cleaning"): (150.0, 400.0),
        ("Cleaning Services", "Deep Cleaning"): (300.0, 800.0),
        ("Cleaning Services", "Move-In/Move-Out Cleaning"): (400.0, 1200.0),
        ("Cleaning Services", "Post-Construction Cleaning"): (500.0, 2000.0),
        ("Cleaning Services", "Office & Commercial Cleaning"): (300.0, 1000.0),
    }

    @classmethod
    def generate_estimate(
        cls,
        service_scope: str,
        industry: str,
        location: Optional[str] = None,
        urgency: str = "routine",
    ) -> PricingEstimate:
        """Generate a pricing estimate from service scope and trade.

        Args:
            service_scope: Free-text description of the work needed
            industry: Normalized industry (e.g. 'HVAC', 'Plumber')
            location: Geographic area (optional, used for location premium)
            urgency: 'routine' (1.0x), 'urgent' (1.2x), 'emergency' (1.5x)

        Returns:
            PricingEstimate with range, caveat, and identified services

        Never fabricates: if no range is found, defaults to "Contact for quote"
        with a (0, 0) range that the caller handles by showing contact CTA.
        """
        industry = normalize_industry(industry)

        # Identify services mentioned in the scope
        services_identified = cls._extract_services(service_scope, industry)

        # Get ranges for identified services
        ranges = []
        for service in services_identified:
            key = (industry, service)
            if key in cls._PRESET_RANGES:
                low, high = cls._PRESET_RANGES[key]
                if low > 0 or high > 0:  # Skip zero-range placeholders
                    ranges.append((low, high))

        # If no valid ranges found, fall back to "Contact for quote"
        if not ranges:
            return PricingEstimate(
                estimated_range_low=0.0,
                estimated_range_high=0.0,
                caveat="Please contact us for a custom quote based on your specific needs.",
                industry=industry,
                services_identified=services_identified or ["Unspecified service"],
            )

        # Compute aggregate low/high from all identified services
        estimated_low = min(r[0] for r in ranges)
        estimated_high = max(r[1] for r in ranges)

        # Apply urgency multiplier
        urgency_multiplier = cls._urgency_multiplier(urgency)
        estimated_low *= urgency_multiplier
        estimated_high *= urgency_multiplier

        # Apply location premium if provided
        if location:
            location_multiplier = cls._location_multiplier(location)
            estimated_low *= location_multiplier
            estimated_high *= location_multiplier

        # Round to nearest 50 for readability
        estimated_low = round(estimated_low / 50) * 50
        estimated_high = round(estimated_high / 50) * 50

        # Ensure low < high
        if estimated_low >= estimated_high:
            estimated_high = estimated_low + 50

        caveat = cls._build_caveat(urgency)

        return PricingEstimate(
            estimated_range_low=estimated_low,
            estimated_range_high=estimated_high,
            caveat=caveat,
            industry=industry,
            services_identified=services_identified or ["Unspecified service"],
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.lower()
        text = text.replace("&", " and ")
        text = text.replace("/", " ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _match_phrases_for_service(cls, service: str) -> list[str]:
        phrases = {cls._normalize_text(service)}
        if "/" in service:
            for part in service.split("/"):
                part_norm = cls._normalize_text(part)
                if part_norm:
                    phrases.add(part_norm)
        if "&" in service:
            phrases.add(cls._normalize_text(service.replace("&", " ")))
        return [p for p in phrases if p]

    @staticmethod
    def _extract_services(scope: str, industry: str) -> list[str]:
        """Extract service keywords mentioned in the scope text.

        Matches against the services list for the industry from trade_presets.py.
        """
        services_for_industry = TRADE_HINTS.get(industry, {}).get("services", [])

        identified = []
        scope_norm = PricingEngine._normalize_text(scope)

        for service in services_for_industry:
            for phrase in PricingEngine._match_phrases_for_service(service):
                if phrase in scope_norm:
                    identified.append(service)
                    break

        return identified

    @staticmethod
    def _urgency_multiplier(urgency: str) -> float:
        """Return price multiplier based on urgency level.

        Emergency service typically commands a premium.
        """
        multipliers = {
            "routine": 1.0,
            "urgent": 1.2,
            "emergency": 1.5,
        }
        return multipliers.get(urgency, 1.0)

    @staticmethod
    def _location_multiplier(location: str) -> float:
        """Return price multiplier based on location.

        Remote areas or rural locations may have travel premiums.
        For MVP, returns 1.0 (no adjustment); can be enhanced later
        with zip-code-based cost-of-living databases.
        """
        # Placeholder: MVP always returns 1.0 (no location premium)
        # Future: integrate zip-code or metro-area cost data
        return 1.0

    @staticmethod
    def _build_caveat(urgency: str) -> str:
        """Build caveat text explaining the estimate.

        Always includes "subject to site inspection" disclaimer.
        """
        base = "Final price determined after site inspection"

        if urgency == "emergency":
            return f"{base}. Emergency surcharge may apply."

        return f"{base}."
