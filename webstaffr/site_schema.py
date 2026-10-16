"""Impeccable-based site schema and builder.

Replaces the ad-hoc field handling in site_data.py and site_renderer.py with
a single source of truth: SiteSchema, a complete, guaranteed-present definition
of every field a rendered site can use.

Principles:
1. Schema completeness: Every field that may appear in a template is explicitly
   defined here, with type and default value.
2. No missing keys: Templates never encounter KeyError or undefined checks --
   all fields are present, with None for absent data.
3. Derived fields: Computed properties (trust_signal_count, has_reviews, etc)
   live in Python, not scattered across templates.
4. Fail-safe defaults: Missing optional fields become sensible defaults
   (None, empty list, etc), never invented content.
5. Single responsibility: This module owns "what data does a site need" so
   templates only own "how to display it".
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from typing import Optional

from .intake import IntakeSubmission
from .site_renderer import (
    has_real_reviews,
    schema_business_type,
    service_pages,
    generate_palette,
    validate_palette_contrast,
    page_title,
    meta_description,
    local_business_schema,
    service_schema,
)


def _enabled_flag(value: object) -> bool:
    """Interpret intake yes/no fields explicitly instead of by string truthiness."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "24/7"}


@dataclass
class SiteSchema:
    """Complete schema for a rendered site. Every field that appears in a
    template or JSON-LD block is defined here, guaranteed to be present."""

    # --- Required fields (always present, never None)
    tenant_id: str
    biz_name: str
    phone: str
    email: str
    industry: str
    service_area: str
    tagline: str
    differentiator: str
    services: list[str]
    plan: str

    # --- Optional fields (present, may be None or empty)
    brand_colors: Optional[str] = None
    years_in_biz: Optional[int] = None
    emergency_service: Optional[str] = None
    gbp_url: Optional[str] = None
    google_review_link: Optional[str] = None
    tone: Optional[str] = None
    pricing_shown: Optional[str] = None
    promos: Optional[str] = None
    rating_value: Optional[float] = None
    review_count: Optional[int] = None
    certifications: Optional[str] = None
    has_before_after: Optional[str] = None
    testimonials: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    keywords: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to a dict safe for Jinja2 template rendering.
        All fields are present; None values render as falsy in templates."""
        return asdict(self)

    @property
    def trust_signal_count(self) -> int:
        """Number of trust signals available (rating, reviews, certifications,
        emergency service, pricing information). Used to gate the trust bar section
        (show only if ≥2 to avoid empty grid cells)."""
        count = 0
        if self.rating_value and self.review_count:
            count += 1
        if self.certifications:
            count += 1
        if self.has_emergency_service:
            count += 1
        if self.shows_pricing:
            count += 1
        return count

    @property
    def has_emergency_service(self) -> bool:
        return _enabled_flag(self.emergency_service)

    @property
    def shows_pricing(self) -> bool:
        return _enabled_flag(self.pricing_shown)

    @property
    def about_trust_signal_count(self) -> int:
        """Number of trust items rendered by the about-page trust bar."""
        count = 0
        if self.years_in_biz:
            count += 1
        if self.certifications:
            count += 1
        if self.has_emergency_service:
            count += 1
        if self.rating_value and self.review_count:
            count += 1
        return count

    @property
    def has_reviews(self) -> bool:
        """True only when real rating/review data is present."""
        return bool(self.rating_value and self.review_count)

    @property
    def service_pages(self) -> list[dict]:
        """List of (name, slug) tuples for every service on this site."""
        return service_pages(self.to_dict())

    @property
    def palette(self) -> dict[str, str]:
        """Color palette dict (primary, secondary, neutrals, etc) for CSS
        variable injection into rendered pages."""
        palette = generate_palette(self.brand_colors)
        validate_palette_contrast(palette)
        return palette

    @classmethod
    def from_intake(cls, submission: IntakeSubmission) -> SiteSchema:
        """Build a SiteSchema from an IntakeSubmission.
        Required fields are pulled directly; optional fields become None
        if missing or empty."""
        optional_field_names = {f.name for f in fields(cls) if f.default is None or f.default_factory is not None}

        kwargs = {
            "tenant_id": submission.tenant_id,
            "biz_name": submission.biz_name,
            "phone": submission.phone,
            "email": submission.email,
            "industry": submission.industry,
            "service_area": submission.service_area,
            "tagline": submission.tagline,
            "differentiator": submission.differentiator,
            "services": submission.services,
            "plan": submission.plan,
        }

        # Load optional fields; None/empty becomes None
        for field_name in optional_field_names:
            value = getattr(submission, field_name, None)
            kwargs[field_name] = value if (value is not None and value != "") else None

        return cls(**kwargs)


def build_page_context(
    schema: SiteSchema,
    site_root: str,
    page_url: str,
    service_name: Optional[str] = None,
    current_year: int = None,
) -> dict:
    """Build a complete Jinja2 template context from a SiteSchema.

    Every field in the dict is guaranteed to be present (no KeyError in
    templates). Derived fields (title, meta description, schema markup,
    palette) are computed here, not in templates.

    Args:
        schema: The complete SiteSchema for this site
        site_root: Base URL for this tenant's site (e.g. /sites/{tenant_id}/web)
        page_url: Full URL of the specific page being rendered
        service_name: If rendering a service page, the service name
        current_year: Current year for copyright/footer (defaults to now)

    Returns:
        Dict safe for templates.TemplateResponse(request, template, context)
    """
    from datetime import datetime, timezone

    if current_year is None:
        current_year = datetime.now(timezone.utc).year

    return {
        # --- Raw site data (all fields guaranteed present)
        "site": schema.to_dict(),

        # --- Derived page metadata
        "title": page_title(schema.to_dict(), service_name),
        "meta_description": meta_description(schema.to_dict(), service_name),

        # --- Design & theming
        "palette": schema.palette,
        "brand_primary": schema.brand_colors,

        # --- Navigation & structure
        "services": schema.service_pages,
        "current_service": service_name,

        # --- Content gates (computed boolean checks)
        "has_reviews": schema.has_reviews,
        "trust_signal_count": schema.trust_signal_count,
        "show_trust_bar": schema.trust_signal_count >= 2,
        "show_about_trust_bar": schema.about_trust_signal_count >= 2,
        "has_emergency_service": schema.has_emergency_service,
        "shows_pricing": schema.shows_pricing,

        # --- Schema markup (JSON-LD)
        "schema_type": schema_business_type(schema.industry),
        "local_business_schema": local_business_schema(schema.to_dict(), page_url),
        "service_schema": service_schema(schema.to_dict(), service_name, page_url) if service_name else None,

        # --- Routing & metadata
        "site_root": site_root,
        "page_url": page_url,
        "current_year": current_year,
    }
