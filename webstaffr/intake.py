"""Client intake -- the first stage of the intake -> generated customer site
-> Angel widget MVP flow (CLAUDE.md / PROJECT.md).

Field set and required-field validation are ported from the legacy webstaff
repo's proven 9-section intake form (intake/intake.html), not reinvented --
see the CLAUDE.md session addendum for provenance. Persistence follows the
same repository pattern as booking.py: a plain dataclass plus a repository
class operating on an already-open connection (SQLite or Postgres --
see db.get_connection), tenant-scoped throughout.

Perfect-site principle carried forward from the legacy repo's
Perfect-Site-Checklist audit (2026-07-04): this module only ever stores
what the business actually submitted. It never fabricates a rating, review
count, or testimonial, and callers building a site from this data (e.g. the
site renderer) must apply the same rule -- omit a section rather than
invent content when a field is empty.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .db import DB_ERRORS, StorageError

REQUIRED_FIELDS = (
    "biz_name",
    "phone",
    "email",
    "industry",
    "service_area",
    "tagline",
    "differentiator",
    "services",
    "license_number",
    "plan",
    "lead_routing",
    "approver",
)

VALID_PLANS = {"office_staff"}

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


class IntakeValidationError(ValueError):
    """Raised when an intake submission is missing a required field or has
    an invalid value. Callers (the router) are expected to catch this and
    turn it into a 400, the same pattern InvalidTenantError follows."""


def sanitize_slug(name: str) -> str:
    """Lowercase, alnum-only slug from a business name. Mirrors
    sanitize_slug() in the legacy site_generator.py."""
    slug = _SLUG_PATTERN.sub("_", name.strip().lower()).strip("_")
    return slug or "client"


def generate_tenant_id(biz_name: str) -> str:
    """Business-name slug plus a short random suffix, so two businesses
    with the same or similar name don't collide on tenant_id. The suffix
    is not meant to be secret or unguessable -- just collision-avoidance,
    matching Tenant's ^[a-zA-Z0-9_-]{1,64}$ constraint.

    sanitize_slug()'s trailing .strip("_") already makes a leading
    underscore structurally unreachable from this function (a real
    generated id can never collide with demo_sites.RESERVED_TENANT_PREFIX,
    "_demo_"), but that's an implicit side effect of string stripping,
    not a stated guarantee -- assert it here so the invariant is explicit
    and a future change to sanitize_slug() can't silently break it."""
    slug = sanitize_slug(biz_name)[:40]
    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"{slug}_{suffix}"
    assert not tenant_id.startswith("_"), (
        f"generate_tenant_id produced a reserved-looking id: {tenant_id!r}"
    )
    return tenant_id


def validate_intake_payload(data: dict) -> None:
    """Raises IntakeValidationError listing every problem found, rather than
    failing on the first one -- so a caller can show all validation errors
    at once instead of one round trip per fix."""
    errors: list[str] = []

    for field_name in REQUIRED_FIELDS:
        value = data.get(field_name)
        if field_name == "services":
            if not value or not isinstance(value, list) or not any(str(s).strip() for s in value):
                errors.append("services must be a non-empty list")
            continue
        if not value or not str(value).strip():
            errors.append(f"Missing required field: {field_name}")

    plan = data.get("plan")
    if plan and plan not in VALID_PLANS:
        errors.append(f"plan must be one of {sorted(VALID_PLANS)}, got {plan!r}")

    rating_value = data.get("rating_value")
    if rating_value is not None and not (1.0 <= float(rating_value) <= 5.0):
        errors.append("rating_value must be between 1.0 and 5.0")

    if errors:
        raise IntakeValidationError("; ".join(errors))


@dataclass
class IntakeSubmission:
    tenant_id: str
    biz_name: str
    phone: str
    email: str
    industry: str
    service_area: str
    tagline: str
    differentiator: str
    services: list[str]
    license_number: str
    plan: str
    lead_routing: str
    approver: str
    submission_id: Optional[int] = None
    years_in_biz: Optional[int] = None
    emergency_service: Optional[str] = None
    has_site: Optional[str] = None
    site_url: Optional[str] = None
    site_platform: Optional[str] = None
    site_issues: Optional[str] = None
    has_gbp: Optional[str] = None
    gbp_url: Optional[str] = None
    google_review_link: Optional[str] = None
    has_logo: Optional[str] = None
    brand_colors: Optional[str] = None
    brand_words: Optional[str] = None
    inspo_sites: Optional[str] = None
    competitors: Optional[str] = None
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
    fsm_system: Optional[str] = None
    booking_system: Optional[str] = None
    timeline: Optional[str] = None
    assets_status: Optional[str] = None
    keywords: Optional[str] = None
    extra_pages: Optional[str] = None
    notes: Optional[str] = None

    @classmethod
    def from_payload(cls, tenant_id: str, data: dict) -> "IntakeSubmission":
        return cls(
            tenant_id=tenant_id,
            biz_name=data["biz_name"],
            phone=data["phone"],
            email=data["email"],
            industry=data["industry"],
            service_area=data["service_area"],
            tagline=data["tagline"],
            differentiator=data["differentiator"],
            services=list(data["services"]),
            license_number=data["license_number"],
            plan=data["plan"],
            lead_routing=data["lead_routing"],
            approver=data["approver"],
            years_in_biz=data.get("years_in_biz"),
            emergency_service=data.get("emergency_service"),
            has_site=data.get("has_site"),
            site_url=data.get("site_url"),
            site_platform=data.get("site_platform"),
            site_issues=data.get("site_issues"),
            has_gbp=data.get("has_gbp"),
            gbp_url=data.get("gbp_url"),
            google_review_link=data.get("google_review_link"),
            has_logo=data.get("has_logo"),
            brand_colors=data.get("brand_colors"),
            brand_words=data.get("brand_words"),
            inspo_sites=data.get("inspo_sites"),
            competitors=data.get("competitors"),
            tone=data.get("tone"),
            pricing_shown=data.get("pricing_shown"),
            promos=data.get("promos"),
            rating_value=data.get("rating_value"),
            review_count=data.get("review_count"),
            certifications=data.get("certifications"),
            has_before_after=data.get("has_before_after"),
            testimonials=data.get("testimonials"),
            facebook_url=data.get("facebook_url"),
            instagram_url=data.get("instagram_url"),
            fsm_system=data.get("fsm_system"),
            booking_system=data.get("booking_system"),
            timeline=data.get("timeline"),
            assets_status=data.get("assets_status"),
            keywords=data.get("keywords"),
            extra_pages=data.get("extra_pages"),
            notes=data.get("notes"),
        )


_COLUMNS = [
    "tenant_id", "biz_name", "phone", "email", "industry", "service_area",
    "years_in_biz", "emergency_service", "has_site", "site_url", "site_platform",
    "site_issues", "has_gbp", "gbp_url", "google_review_link", "has_logo",
    "brand_colors", "brand_words", "inspo_sites", "tagline", "differentiator",
    "competitors", "tone", "services_json", "pricing_shown", "promos",
    "license_number", "rating_value", "review_count", "certifications",
    "has_before_after", "testimonials", "facebook_url", "instagram_url",
    "fsm_system", "booking_system", "plan", "lead_routing", "timeline",
    "approver", "assets_status", "keywords", "extra_pages", "notes", "created_at",
]


class IntakeRepository:
    """Persists and loads IntakeSubmissions. Follows the same pattern as
    AppointmentRepository: caller-owned connection, tenant_id always part
    of every query."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def save(self, submission: IntakeSubmission) -> int:
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)",
                (submission.tenant_id,),
            )
            values = {
                "tenant_id": submission.tenant_id,
                "biz_name": submission.biz_name,
                "phone": submission.phone,
                "email": submission.email,
                "industry": submission.industry,
                "service_area": submission.service_area,
                "years_in_biz": submission.years_in_biz,
                "emergency_service": submission.emergency_service,
                "has_site": submission.has_site,
                "site_url": submission.site_url,
                "site_platform": submission.site_platform,
                "site_issues": submission.site_issues,
                "has_gbp": submission.has_gbp,
                "gbp_url": submission.gbp_url,
                "google_review_link": submission.google_review_link,
                "has_logo": submission.has_logo,
                "brand_colors": submission.brand_colors,
                "brand_words": submission.brand_words,
                "inspo_sites": submission.inspo_sites,
                "tagline": submission.tagline,
                "differentiator": submission.differentiator,
                "competitors": submission.competitors,
                "tone": submission.tone,
                "services_json": json.dumps(submission.services),
                "pricing_shown": submission.pricing_shown,
                "promos": submission.promos,
                "license_number": submission.license_number,
                "rating_value": submission.rating_value,
                "review_count": submission.review_count,
                "certifications": submission.certifications,
                "has_before_after": submission.has_before_after,
                "testimonials": submission.testimonials,
                "facebook_url": submission.facebook_url,
                "instagram_url": submission.instagram_url,
                "fsm_system": submission.fsm_system,
                "booking_system": submission.booking_system,
                "plan": submission.plan,
                "lead_routing": submission.lead_routing,
                "timeline": submission.timeline,
                "approver": submission.approver,
                "assets_status": submission.assets_status,
                "keywords": submission.keywords,
                "extra_pages": submission.extra_pages,
                "notes": submission.notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            placeholders = ", ".join("?" for _ in _COLUMNS)
            columns = ", ".join(_COLUMNS)
            cursor = self._conn.execute(
                f"INSERT INTO intake_submissions ({columns}) VALUES ({placeholders})",
                tuple(values[col] for col in _COLUMNS),
            )
        except DB_ERRORS as exc:
            raise StorageError(
                f"Failed to save intake submission for tenant {submission.tenant_id!r}: {exc}"
            ) from exc
        submission.submission_id = cursor.lastrowid
        return submission.submission_id

    def load(self, tenant_id: str, submission_id: int) -> Optional[IntakeSubmission]:
        try:
            row = self._conn.execute(
                "SELECT * FROM intake_submissions WHERE tenant_id = ? AND submission_id = ?",
                (tenant_id, submission_id),
            ).fetchone()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to load intake submission {submission_id}: {exc}") from exc

        if row is None:
            return None

        return self._row_to_submission(row)

    def load_latest_for_tenant(self, tenant_id: str) -> Optional[IntakeSubmission]:
        """Most recent submission for a tenant -- what the public site-data
        endpoint (GET /sites/{tenant_id}) renders from. A tenant re-submitting
        intake (e.g. updating their info) should show up here without needing
        a separate "current submission" pointer column."""
        try:
            row = self._conn.execute(
                """
                SELECT * FROM intake_submissions
                WHERE tenant_id = ?
                ORDER BY submission_id DESC
                LIMIT 1
                """,
                (tenant_id,),
            ).fetchone()
        except DB_ERRORS as exc:
            raise StorageError(
                f"Failed to load latest intake submission for tenant {tenant_id!r}: {exc}"
            ) from exc

        if row is None:
            return None

        return self._row_to_submission(row)

    @staticmethod
    def _row_to_submission(row: Any) -> IntakeSubmission:
        data = dict(row)
        data["services"] = json.loads(data.pop("services_json"))
        data.pop("created_at", None)
        return IntakeSubmission(**data)

    def list_for_tenant(self, tenant_id: str) -> list:
        try:
            rows = self._conn.execute(
                "SELECT submission_id FROM intake_submissions WHERE tenant_id = ? ORDER BY submission_id",
                (tenant_id,),
            ).fetchall()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to list intake submissions for tenant {tenant_id!r}: {exc}") from exc
        return [row["submission_id"] for row in rows]
