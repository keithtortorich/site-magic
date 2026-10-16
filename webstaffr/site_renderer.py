"""Server-side rendering of customer/tenant sites using Jinja2 templates.
See docs/SITE_RENDERER_PLAN.md for architecture.

Consumes the same public projection GET /sites/{tenant_id} already
returns (build_public_site_data()) -- this module adds no new fields and
therefore cannot leak anything that projection doesn't already expose.
Pure functions only; no DB access lives here. The router
(site_render_router.py) owns the DB round trip and passes the resulting
dict in.

Follows docs/SITE_WEAVER_SEO_BLUEPRINT.md's page architecture, on-page
element patterns, and schema markup -- except the blueprint's Review
schema example, which hardcodes a fabricated rating/review as
boilerplate. This module renders AggregateRating/Review JSON-LD only
from real rating_value/review_count/testimonials fields already present
in the public projection, and omits that block entirely otherwise --
per CLAUDE.md's no-fabrication invariant (see the flag recorded at the
top of the blueprint doc).
"""

from __future__ import annotations

import colorsys
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from .trade_presets import normalize_industry

logger = logging.getLogger("webstaffr.site_renderer")

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

# schema.org has dedicated LocalBusiness subtypes for HVAC/Plumber/
# Electrician/Roofing (all children of the real schema.org
# HomeAndConstructionBusiness type). None of this list's other trades
# have a dedicated schema.org subtype -- rather than invent one (e.g. a
# fabricated "PestControlBusiness" or "TreeServiceBusiness" isn't a real
# schema.org type), they use the real parent type,
# HomeAndConstructionBusiness, directly. Keyed off intake's own
# normalized industry set (trade_presets.SUPPORTED_INDUSTRIES) so this
# never drifts from what the intake form treats as canonical -- adding a
# new industry there means adding one line here.
_SCHEMA_TYPE_BY_INDUSTRY: dict[str, str] = {
    "HVAC": "HVACBusiness",
    "Plumber": "Plumber",
    "Electrician": "Electrician",
    "Roofing": "RoofingContractor",
    "Water Damage Restoration": "HomeAndConstructionBusiness",
    "Garage Door Repair": "HomeAndConstructionBusiness",
    "Pest Control": "HomeAndConstructionBusiness",
    "Landscaping": "HomeAndConstructionBusiness",
    "Tree Service": "HomeAndConstructionBusiness",
    "Cleaning Services": "HomeAndConstructionBusiness",
    "Other": "LocalBusiness",
}


def slugify(text: str) -> str:
    """URL-safe slug for a service name or similar short label. Dash-joined
    per the SEO blueprint's URL convention (intake's own sanitize_slug()
    uses underscores for tenant_id -- a different namespace with a
    different constraint, not reused here on purpose)."""
    slug = _SLUG_PATTERN.sub("-", text.strip().lower()).strip("-")
    return slug or "service"


def schema_business_type(industry: str) -> str:
    """schema.org type for the LocalBusiness JSON-LD block."""
    return _SCHEMA_TYPE_BY_INDUSTRY.get(normalize_industry(industry), "LocalBusiness")


@dataclass
class ContrastWarning:
    """Accessibility issue for a color pair."""

    issue: str  # e.g., "primary-on-muted-bg"
    actual_ratio: float  # e.g., 3.2
    required_ratio: float  # e.g., 4.5


def _hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Convert #rrggbb hex to (hue, saturation, lightness) in [0,1] range."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    r, g, b = (int(hex_color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, l, s


def _hsl_to_hex_cached(h: float, l: float, s: float) -> str:
    """Convert (hue, saturation, lightness) in [0,1] to #rrggbb hex."""
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


@lru_cache(maxsize=128)
def _hsl_to_hex(h: float, l: float, s: float) -> str:
    """Cached wrapper for HSL to hex conversion."""
    return _hsl_to_hex_cached(h, l, s)


def generate_palette(brand_primary: Optional[str]) -> dict[str, str]:
    """Generate a palette from a brand primary hex color.

    Returns a dict with keys: primary, primary_dark, primary_light, neutral_dark,
    neutral_light. If brand_primary is None or invalid, returns the default
    hardcoded palette.

    Algorithm: HSL-based lightening/darkening of the brand primary, plus
    neutral grays derived from the primary's hue and saturation."""
    default_palette = {
        "primary": "#2a6df5",
        "primary_dark": "#1f4fb8",
        "primary_light": "#5b8dff",
        "neutral_dark": "#16202e",
        "neutral_light": "#f4f6f9",
    }

    if not brand_primary:
        palette = default_palette
        palette["primary_accessible"] = _accessible_action_color(palette)
        palette["primary_accessible_dark"] = _accessible_action_dark_color(palette)
        return palette

    try:
        h, l, s = _hex_to_hsl(brand_primary)
    except (ValueError, IndexError):
        logger.warning("Invalid brand color %s, using default palette", brand_primary)
        palette = default_palette
        palette["primary_accessible"] = _accessible_action_color(palette)
        palette["primary_accessible_dark"] = _accessible_action_dark_color(palette)
        return palette

    palette = {
        "primary": brand_primary,
        "primary_dark": _hsl_to_hex(h, max(0.2, l - 0.25), s),  # darken 25%
        "primary_light": _hsl_to_hex(h, min(0.9, l + 0.25), s),  # lighten 25%
        "neutral_dark": "#16202e",  # fixed dark (not derived)
        "neutral_light": "#f4f6f9",  # fixed light (not derived)
    }
    palette["primary_accessible"] = _accessible_action_color(palette)
    palette["primary_accessible_dark"] = _accessible_action_dark_color(palette)
    return palette


def _hex_to_rgb_cached(hex_color: str) -> tuple[int, int, int]:
    """Convert #rrggbb or #rgb to RGB tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@lru_cache(maxsize=64)
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Cached wrapper for hex to RGB conversion."""
    return _hex_to_rgb_cached(hex_color)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """WCAG 2.1 relative luminance of an RGB color."""

    def channel(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG 2.1 contrast ratio between two hex colors (1:1 to 21:1)."""
    rgb_a = _hex_to_rgb(hex_a)
    rgb_b = _hex_to_rgb(hex_b)
    l_a = _relative_luminance(rgb_a)
    l_b = _relative_luminance(rgb_b)
    lighter = max(l_a, l_b)
    darker = min(l_a, l_b)
    return (lighter + 0.05) / (darker + 0.05)


def _accessible_action_color(palette: dict[str, str]) -> str:
    """Keep the tenant brand color when safe, otherwise use a safe dark variant.

    Action color is used both as text on light surfaces and as a background
    behind white button text, so it must meet 4.5:1 against both surfaces.
    The original primary remains available for decorative brand treatment.
    """
    backgrounds = ("#ffffff", palette["neutral_light"])
    for candidate in (
        palette["primary"],
        palette["primary_dark"],
        palette["neutral_dark"],
    ):
        if all(_contrast_ratio(candidate, background) >= 4.5 for background in backgrounds):
            return candidate
    return "#16202e"


def _accessible_action_dark_color(palette: dict[str, str]) -> str:
    """Return an accessible hover/active companion for the action color."""
    backgrounds = ("#ffffff", palette["neutral_light"])
    for candidate in (palette["primary_dark"], palette["neutral_dark"]):
        if all(_contrast_ratio(candidate, background) >= 4.5 for background in backgrounds):
            return candidate
    return palette["primary_accessible"]


def validate_palette_contrast(palette: dict[str, str]) -> list[ContrastWarning]:
    """Validate WCAG 2.1 AA contrast ratios for key color pairs.

    Returns a list of ContrastWarning objects (empty if all pass). Does NOT block
    rendering; warnings are logged for manual review."""
    warnings = []
    checks = [
        ("primary-accessible-on-white", palette["primary_accessible"], "#ffffff", 4.5),
        (
            "primary-accessible-on-neutral-light",
            palette["primary_accessible"],
            palette["neutral_light"],
            4.5,
        ),
        (
            "primary-accessible-dark-on-neutral-light",
            palette["primary_accessible_dark"],
            palette["neutral_light"],
            4.5,
        ),
        ("neutral-dark-on-neutral-light", palette["neutral_dark"], palette["neutral_light"], 4.5),
    ]

    for issue, fg, bg, required in checks:
        try:
            ratio = _contrast_ratio(fg, bg)
            if ratio < required:
                warnings.append(
                    ContrastWarning(issue=issue, actual_ratio=round(ratio, 2), required_ratio=required)
                )
        except (ValueError, IndexError) as e:
            logger.warning("Failed to compute contrast for %s: %s", issue, e)

    if warnings:
        logger.warning(
            "Palette contrast warnings: %s",
            "; ".join(f"{w.issue} {w.actual_ratio:.1f}:1 (need {w.required_ratio}:1)" for w in warnings),
        )

    return warnings


def service_pages(site_data: dict) -> list[dict]:
    """One {name, slug} entry per service in the public site data, in
    submission order. De-duplicates slugs (two differently-worded services
    that happen to slugify to the same string) with a numeric suffix, so no
    two services on one tenant's site collide on URL."""
    seen: dict[str, int] = {}
    pages = []
    for name in site_data.get("services", []):
        base_slug = slugify(name)
        count = seen.get(base_slug, 0)
        seen[base_slug] = count + 1
        slug = base_slug if count == 0 else f"{base_slug}-{count + 1}"
        pages.append({"name": name, "slug": slug})
    return pages


def find_service(site_data: dict, slug: str) -> Optional[dict]:
    """The one service page whose slug matches, or None -- turning that
    into a 404 is the router's job, not this module's."""
    for page in service_pages(site_data):
        if page["slug"] == slug:
            return page
    return None


def has_real_reviews(site_data: dict) -> bool:
    """True only when real rating/review data is present in the public
    projection -- gates the AggregateRating/Review JSON-LD block and the
    /reviews page. This only ever looks at what build_public_site_data()
    actually returned for a real submission, so it can never be true from
    placeholder or example data."""
    return bool(site_data.get("rating_value") and site_data.get("review_count"))


def page_title(site_data: dict, service_name: Optional[str] = None) -> str:
    """`[Service] in [Service Area] | [Business Name]` pattern from the SEO
    blueprint's title-tag convention. Falls back to an industry-based
    homepage title when no specific service is given."""
    biz_name = site_data["biz_name"]
    area = site_data.get("service_area", "")
    if service_name:
        suffix = f" in {area}" if area else ""
        return f"{service_name}{suffix} | {biz_name}"
    industry = site_data.get("industry", "")
    suffix = f" in {area}" if area else ""
    return f"{industry} Services{suffix} | {biz_name}" if industry else biz_name


def meta_description(site_data: dict, service_name: Optional[str] = None) -> str:
    """Meta description built only from real intake fields (tagline,
    differentiator) -- never invented copy. Truncated to a conventional
    ~155 chars so search engines don't cut it off mid-word."""
    biz_name = site_data["biz_name"]
    area = site_data.get("service_area", "")
    parts = [biz_name]
    if service_name:
        parts.append(f"provides {service_name.lower()}" + (f" in {area}" if area else ""))
    else:
        tagline = site_data.get("tagline")
        if tagline:
            parts.append(tagline)
    differentiator = site_data.get("differentiator")
    if differentiator:
        parts.append(differentiator)
    text = ". ".join(p.strip().rstrip(".") for p in parts if p) + "."
    if len(text) > 155:
        text = text[:152].rsplit(" ", 1)[0] + "..."
    return text


def local_business_schema(site_data: dict, page_url: str) -> dict:
    """LocalBusiness (or trade-specific subtype) JSON-LD, built only from
    fields intake actually collects. Deliberately leaner than the SEO
    blueprint's example: this repo's intake form has no street address,
    lat/long, opening-hours, or logo-image fields, so `address`/`geo`/
    `openingHours`/`image` are omitted rather than invented -- the
    no-fabrication invariant applies to schema markup exactly as it does
    to visible copy. `areaServed` uses the freeform `service_area` string
    as a Place name rather than assuming it parses to one City."""
    schema: dict = {
        "@context": "https://schema.org",
        "@type": schema_business_type(site_data.get("industry", "")),
        "name": site_data["biz_name"],
        "url": page_url,
        "telephone": site_data["phone"],
        "email": site_data["email"],
    }
    description = site_data.get("tagline") or site_data.get("differentiator")
    if description:
        schema["description"] = description
    area = site_data.get("service_area")
    if area:
        schema["areaServed"] = {"@type": "Place", "name": area}
    same_as = [
        url for url in (site_data.get("facebook_url"), site_data.get("instagram_url")) if url
    ]
    if same_as:
        schema["sameAs"] = same_as
    if has_real_reviews(site_data):
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": site_data["rating_value"],
            "reviewCount": site_data["review_count"],
            "bestRating": 5,
            "worstRating": 1,
        }
    return schema


def service_schema(site_data: dict, service_name: str, page_url: str) -> dict:
    """Service JSON-LD for one service page. No `offers`/price block --
    `pricing_shown` is a yes/no intake flag, not an actual price, and
    inventing one would violate the no-fabrication invariant."""
    schema: dict = {
        "@context": "https://schema.org",
        "@type": "Service",
        "serviceType": service_name,
        "provider": {
            "@type": schema_business_type(site_data.get("industry", "")),
            "name": site_data["biz_name"],
        },
        "url": page_url,
    }
    area = site_data.get("service_area")
    if area:
        schema["areaServed"] = {"@type": "Place", "name": area}
    schema["description"] = meta_description(site_data, service_name)
    return schema


def build_page_context(
    site_data: dict, site_root: str, page_url: str, service_name: Optional[str] = None
) -> dict:
    """Everything a template needs for one page: the raw public site data,
    derived SEO fields (title, meta description, schema type, the
    service-page list, the reviews gate), the JSON-LD schema dict(s),
    and the color palette (from brand_colors or default).

    `site_root` is this tenant's site root (e.g.
    `https://host/sites/{tenant_id}/web`, no trailing slash) -- what nav
    links and the widget's `data-api-base` are built from. `page_url` is
    the full URL of the specific page being rendered -- used for the
    canonical tag and each schema object's own `.url`. Both are supplied
    by the router from the live request; this module stays a pure
    function of its inputs and never guesses its own deployed host.

    No FAQPage schema: the SEO blueprint's FAQ example uses invented
    question/answer copy, and intake collects no structured Q&A content
    to back a real one -- adding fabricated FAQ schema was considered and
    deliberately not built, rather than silently generating filler.
    Same reasoning for individual `Review` objects: `testimonials` is a
    single free-text field with no author/date, so it renders as visible
    page copy only, never as invented structured Review entries."""
    
    palette = generate_palette(site_data.get("brand_colors"))
    validate_palette_contrast(palette)

    # Calculate trust signals for template gating
    trust_signal_count = 0
    if site_data.get('rating_value') and site_data.get('review_count'):
        trust_signal_count += 1
    if site_data.get('certifications'):
        trust_signal_count += 1
    if site_data.get('emergency_service') == 'true':
        trust_signal_count += 1
    if site_data.get('pricing_shown') == 'true':
        trust_signal_count += 1
    
    return {
        "site": site_data,
        "title": page_title(site_data, service_name),
        "meta_description": meta_description(site_data, service_name),
        "schema_type": schema_business_type(site_data.get("industry", "")),
        "services": service_pages(site_data),
        "has_reviews": has_real_reviews(site_data),
        "trust_signal_count": trust_signal_count,
        "show_trust_bar": trust_signal_count >= 2,
        "current_service": service_name,
        "site_root": site_root,
        "page_url": page_url,
        "static_css": f"{site_root}/static/angel-widget.css",
        "static_js": f"{site_root}/static/angel-widget.js",
        "local_business_schema": local_business_schema(site_data, page_url),
        "service_schema": (
            service_schema(site_data, service_name, page_url) if service_name else None
        ),
        "palette": palette,
    }
