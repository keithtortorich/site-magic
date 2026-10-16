"""Public-facing projection of an IntakeSubmission -- what GET
/sites/{tenant_id} returns for the tenant's site to render.

Deliberately NOT a straight dump of the intake_submissions row. Several
fields collected at intake are internal operations data, not content for
a public website, and must never be exposed here:

  - lead_routing / approver: who internally receives leads and who signs
    off on the business -- often a staff member's name and personal phone
    number, not customer-facing content.
  - timeline, notes, extra_pages, assets_status: internal planning fields.
  - has_site / site_url / site_platform / site_issues: about the
    business's OLD site, relevant to us migrating them, meaningless on
    their NEW site.
  - brand_colors: EXPOSED (see docs/DECISIONS.md ADR-001 for rationale).
    Primary brand hex used to generate dynamic site palette. Hex string
    only (#rrggbb format), validated at intake, low-risk exposure.
  - inspo_sites / brand_words / competitors / fsm_system / booking_system:
    internal design/ops inputs, not content.
  - has_logo: internal flag (logo upload planned for phase 2).
  - license_number: removed per a security review and a direct founder
    decision. Supabase's own advisor had already flagged
    `intake_submissions.license_number` as a `sensitive_columns_exposed`
    warning at the database layer (see CLAUDE.md's 2026-07-07 addendum);
    this endpoint was nonetheless still publishing it at the application
    layer regardless of that warning. Founder's call was to pull it rather
    than keep it as a trust-signal display field -- not a technical
    necessity, a deliberate choice, made explicitly rather than carried
    forward implicitly.

Perfect-site principle (see CLAUDE.md session addendum, ported from the
legacy webstaff repo's Perfect-Site-Checklist): this module never invents
a rating, review count, or testimonial. Optional fields that are None in
the submission stay absent from the output entirely, rather than being
filled with a plausible-looking default -- the site renderer's job is to
omit that section when the key is missing, not to fabricate content.
"""

from __future__ import annotations

from .intake import IntakeSubmission


def build_public_site_data(submission: IntakeSubmission) -> dict:
    """Curated, public-safe view of a submission. Optional fields that are
    None are omitted from the returned dict entirely (rather than included
    as `null`) so the site template's job is a simple `"key" in data` /
    `.get("key")` check, not a null-check on every optional field."""
    data: dict = {
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

    optional_fields = (
        "brand_colors",  # primary hex for dynamic palette generation
        "years_in_biz",
        "emergency_service",
        "gbp_url",
        "google_review_link",
        "tone",
        "pricing_shown",
        "promos",
        "rating_value",
        "review_count",
        "certifications",
        "has_before_after",
        "testimonials",
        "facebook_url",
        "instagram_url",
        "keywords",
    )
    for field_name in optional_fields:
        value = getattr(submission, field_name)
        if value is not None and value != "":
            data[field_name] = value

    return data
