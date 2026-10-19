"""Validated, local design directions for generated trade sites.

The renderer consumes this bounded registry rather than reaching OriginKit at
build or runtime. The JSON catalog remains the human/audit-facing source.
"""

from __future__ import annotations

from typing import Optional

from .trade_presets import normalize_industry


DESIGN_VARIANTS = {
    "workshop-contrast": {
        "tokens": {"ink": "#111827", "surface": "#F7F7F2", "accent": "#E87524", "support": "#2B5963"},
        "best_for": {"HVAC", "Electrician", "Roofing", "Garage Door Repair"},
    },
    "field-notebook": {
        "tokens": {"ink": "#20312B", "surface": "#F3EFE5", "accent": "#2F6B4F", "support": "#C98B52"},
        "best_for": {"Landscaping", "Tree Service", "Cleaning Services", "Other"},
    },
    "after-hours": {
        "tokens": {"ink": "#0B1F2A", "surface": "#EFF6F8", "accent": "#C97945", "support": "#367C91"},
        "best_for": {"Plumber", "Water Damage Restoration", "HVAC"},
    },
}


def resolve_design_variant(variant: Optional[str], industry: str) -> str:
    """Return a known variant, using a deterministic trade default."""
    if variant in DESIGN_VARIANTS:
        return variant
    normalized = normalize_industry(industry)
    if normalized in {"Plumber", "Water Damage Restoration"}:
        return "after-hours"
    if normalized in {"Landscaping", "Tree Service", "Cleaning Services"}:
        return "field-notebook"
    return "workshop-contrast"


def design_tokens(variant: str) -> dict[str, str]:
    """Return a copy so templates/callers cannot mutate the registry."""
    resolved = variant if variant in DESIGN_VARIANTS else "workshop-contrast"
    return dict(DESIGN_VARIANTS[resolved]["tokens"])
