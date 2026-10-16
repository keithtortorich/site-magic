# Site Schema System — Impeccable-Based Site Generation

## Overview

Replaces the ad-hoc field handling in `site_data.py` and scattered template logic with a single source of truth: `SiteSchema`, a complete, guaranteed-present definition of every field a rendered site can use.

**Problem solved:** Before, optional fields were omitted from the context dict when missing, causing `KeyError` in templates when they checked `site.years_in_biz` or computed `trust_signal_count`. Templates had to defensively use `.get()` (a Python dict method, not valid in Jinja2) or duplicate logic (`{% if site.field_name %}`).

**Solution:** SiteSchema guarantees all fields are present. Missing optional fields become None, which is falsy in templates. Business logic (derived properties, content gates) lives in Python, not scattered across templates.

## Architecture

### SiteSchema (site_schema.py)

A dataclass with two sections:

**Required fields** (always present, never None):
- `tenant_id`, `biz_name`, `phone`, `email`, `industry`, `service_area`, `tagline`, `differentiator`, `services`, `plan`

**Optional fields** (always present, may be None):
- `brand_colors`, `years_in_biz`, `emergency_service`, rating/review data, certifications, social URLs, etc.

#### Key methods:

- `to_dict()` — Returns a Jinja2-safe dict with all fields present
- `from_intake(submission)` — Builds SiteSchema from IntakeSubmission
- **Computed properties:**
  - `trust_signal_count` — Integer count of trust signals (rating, reviews, certs, emergency, pricing); used to gate the trust bar (show only if ≥2)
  - `has_reviews` — Boolean; true only if rating_value AND review_count both present
  - `service_pages` — List of service (name, slug) tuples
  - `palette` — Color palette dict for CSS variable injection

### build_page_context() (site_schema.py)

Builds a complete template context from a SiteSchema. Every key is guaranteed to be present.

Returns:
- `site` — The raw schema dict (all fields present)
- `title`, `meta_description` — Derived SEO fields
- `palette` — Color palette
- `services`, `current_service` — Navigation structure
- `has_reviews`, `trust_signal_count`, `show_trust_bar` — **Computed boolean checks (not in templates!)**
- `local_business_schema`, `service_schema` — JSON-LD markup
- `site_root`, `page_url`, `current_year` — Routing metadata

### Integration: site_render_router.py

Routes load SiteSchema and pass it to templates:

```python
@site_render_router.get("/sites/{tenant_id}/web")
def render_home(tenant_id: str, request: Request) -> Response:
    schema = _load_site_schema(tenant_id, request)  # Returns SiteSchema
    return _render(request, "home.html", schema, tenant_id)
```

The `_render()` function calls `build_page_context()` and passes the context to Jinja2.

## Benefits

1. **No missing keys**: Templates never encounter `KeyError` or undefined checks
2. **Single source of truth**: What data a site needs is defined once, in SiteSchema
3. **Testability**: Each stage (schema → context → template) is independently testable
4. **No template logic**: Business logic (trust signal count, content gates) lives in Python
5. **Type safety**: SiteSchema is a typed dataclass; IDEs can autocomplete; Python will catch typos
6. **Fail-safe defaults**: Missing optional fields become None, never invented content

## Principles Applied

**Schema completeness**: Every field that may appear in a template is explicitly defined.

**No missing keys**: All fields are present; None values render as falsy in templates (`{% if site.field %}`).

**Derived fields in Python**: Computed properties live in SiteSchema or build_page_context(), not scattered across templates.

**Fail-safe defaults**: Missing optional fields become sensible defaults (None, empty list), never invented content.

**Single responsibility**: This module owns "what data does a site need" so templates only own "how to display it".

## Migration Path

If adding a new site field:

1. Add it to `SiteSchema` (required or optional with default)
2. Update `SiteSchema.from_intake()` to pull it from IntakeSubmission
3. If it's derived (computed), add a property to SiteSchema
4. If it gates content, add a boolean property and include it in `build_page_context()`
5. Templates reference it as `site.field_name` or check the gate property

No more:
- Omitting fields from the dict
- Defensive `.get()` checks in templates
- Duplicated logic across templates

## Impeccable Alignment

The system follows Impeccable principles:

- **Clarity**: Field definitions are explicit, not inferred
- **Completeness**: All possible fields are defined; no surprises
- **Testability**: Each component can be tested independently
- **No fabrication**: Missing data becomes None, never invented defaults
- **Single source**: One schema owns all site data needs
