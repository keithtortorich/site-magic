"""FastAPI router for client intake -- the first stage of the intake -> 
generated customer site -> Angel widget MVP flow (CLAUDE.md / PROJECT.md).

Mounted into the main app via create_app().include_router(intake_router)
in webstaffr/workers/angel/router.py, keeping that file's own router
Angel-specific per its existing docstring.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .attribution import TrackingNumberRepository
from .db import DB_ERRORS, StorageError, get_connection
from .intake import (
    IntakeRepository,
    IntakeSubmission,
    IntakeValidationError,
    generate_tenant_id,
    validate_intake_payload,
)
from .site_data import build_public_site_data
from .site_magic import SiteMagicNotConfiguredError, SiteMagicRepository
from .site_magic_engine import SiteGenerationResult, generate_site_for_submission, resolve_site_workdir
from .trade_presets import SUPPORTED_INDUSTRIES, get_preset
from .rate_limit import (
    RateLimitExceeded,
    check_dimensions,
    direct_client_ip,
)

logger = logging.getLogger("webstaffr.intake_router")

intake_router = APIRouter()


class IntakeRequest(BaseModel):
    # Section 1: Business Basics
    biz_name: str
    phone: str
    email: str
    industry: str
    service_area: str
    years_in_biz: Optional[int] = None
    emergency_service: Optional[str] = None

    # Section 2: Current Web Presence
    has_site: Optional[str] = None
    site_url: Optional[str] = None
    site_platform: Optional[str] = None
    site_issues: Optional[str] = None
    has_gbp: Optional[str] = None
    gbp_url: Optional[str] = None
    google_review_link: Optional[str] = None

    # Section 3: Brand
    has_logo: Optional[str] = None
    brand_colors: Optional[str] = None
    brand_words: Optional[str] = None
    inspo_sites: Optional[str] = None

    # Section 4: Positioning
    tagline: str
    differentiator: str
    competitors: Optional[str] = None
    tone: Optional[str] = None

    # Section 5: Services
    services: list[str]
    pricing_shown: Optional[str] = None
    promos: Optional[str] = None
    license_number: str

    # Section 6: Proof & Credibility
    rating_value: Optional[float] = None
    review_count: Optional[int] = None
    certifications: Optional[str] = None
    has_before_after: Optional[str] = None
    testimonials: Optional[str] = None

    # Section 7: Social & Tools
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    fsm_system: Optional[str] = None
    booking_system: Optional[str] = None

    # Section 8: Workforce Plan
    plan: str
    lead_routing: str
    timeline: Optional[str] = None
    approver: str

    # Section 9: Content & SEO
    assets_status: Optional[str] = None
    keywords: Optional[str] = None
    extra_pages: Optional[str] = None
    notes: Optional[str] = None


class IntakeResponse(BaseModel):
    submission_id: int
    tenant_id: str
    biz_name: str
    industry: str
    plan: str


def _get_connection(request: Request):
    """Reads the db_path the app was created with (create_app stores it on
    app.state) rather than importing a module-level default -- keeps this
    router testable against whatever database a given app instance uses.
    Backend (SQLite vs Postgres) is chosen by db.get_connection() based on
    DATABASE_URL -- this router doesn't need to know which one it got.
    Raises HTTPException(503) on a DB-layer failure instead of letting a
    raw psycopg2/sqlite3 exception propagate to the client.
    """
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        # See site_router.py's identical comment: log the exception type
        # only, never str(exc) (may contain the connection string).
        logger.error("intake_db_connection_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Intake temporarily unavailable -- please try again shortly") from exc


@intake_router.post("/intake", response_model=IntakeResponse)
def submit_intake(req: IntakeRequest, request: Request) -> IntakeResponse:
    data = req.model_dump()

    try:
        validate_intake_payload(data)
    except IntakeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conn = _get_connection(request)
    try:
        try:
            check_dimensions(
                conn,
                "intake",
                [("ip", direct_client_ip(request))],
            )
        except RateLimitExceeded as exc:
            conn.commit()
            raise HTTPException(
                status_code=429,
                detail="Too many setup requests. Please try again shortly.",
            ) from exc

        try:
            tenant_id = generate_tenant_id(req.biz_name)
            submission = IntakeSubmission.from_payload(tenant_id, data)
            repo = IntakeRepository(conn)
            repo.save(submission)

            # Every tenant gets a tracking number the moment they have a real
            # site to point it at -- get_or_create() is idempotent, so a
            # resubmission for the same tenant_id (there isn't one today, but
            # nothing here assumes there never will be) can't create a second
            # one. See attribution.py's module docstring for why this isn't a
            # real phone number yet.
            TrackingNumberRepository(conn).get_or_create(tenant_id)
            conn.commit()
        except (DB_ERRORS + (StorageError,)) as exc:
            # A persistence failure (e.g. a missing/partially-applied schema
            # in production) must surface as a clean JSON error the browser
            # can parse and show -- not an unhandled exception that leaks a
            # 500 HTML page and makes the frontend's response.json() throw
            # "Unexpected token 'I', \"Internal S\"...". Log the exception type
            # only (never str(exc), which may embed connection details), then
            # roll back and return 503 so the form shows a real message.
            logger.error(
                "intake_persist_failed error_type=%s",
                type(exc).__name__,
            )
            conn.rollback()
            raise HTTPException(
                status_code=503,
                detail="Intake temporarily unavailable. Please try again shortly.",
            ) from exc
    finally:
        conn.close()

    renderer_result = _generate_site_if_enabled(submission, request.app.state.db_path)
    _enqueue_site_magic_job_if_configured(submission, request, renderer_result)

    return IntakeResponse(
        submission_id=submission.submission_id,
        tenant_id=tenant_id,
        biz_name=submission.biz_name,
        industry=submission.industry,
        plan=submission.plan,
    )


def _generate_site_if_enabled(
    submission: IntakeSubmission, db_path: str
) -> Optional[SiteGenerationResult]:
    """Best-effort site generation after a successful intake.

    Site generation must never fail the intake response: a prospect should
    not receive a 500 because template rendering hiccuped. Failures are
    logged with the real exception type and swallowed here; success is
    silent.
    """
    try:
        return generate_site_for_submission(submission, resolve_site_workdir(db_path))
    except Exception as exc:
        logger.error(
            "site_generation_failed tenant_id=%s error_type=%s",
            submission.tenant_id,
            type(exc).__name__,
        )
        return None


def _enqueue_site_magic_job_if_configured(
    submission: IntakeSubmission,
    request: Request,
    renderer_result: Optional[SiteGenerationResult],
) -> None:
    """Best-effort Site Magic job creation after a successful intake commit.

    Runs in its own connection/transaction, strictly after the intake
    transaction above has already committed -- a Site Magic failure must
    never roll back or fail the intake response, same posture as
    _generate_site_if_enabled.

    source_payload carries verified_facts alongside intake_id: the same
    build_public_site_data() projection GET /sites/{tenant_id} uses, so
    the worker's SiteSource.verifiedFacts is the already-vetted
    internal-fields-stripped view (see site_data.py's module docstring for
    the never-leak list -- lead_routing, approver, competitors,
    license_number, etc.), not a raw dump of intake_submissions. The
    renderer_baseline makes the deterministic renderer's successful output
    an explicit input to Site Magic instead of running both pipelines as
    unrelated side effects. The worker materializes this route into its
    workspace before product/direction/build roles run.

    The worker needs the facts inline: nothing resolves an intake_id back to
    a submission from the Node side, and duplicating that lookup there
    would be a second, drifting source of truth for what's public-safe.
    """
    conn = _get_connection(request)
    try:
        source_payload = {
            "intake_id": str(submission.submission_id),
            "verified_facts": build_public_site_data(submission),
        }
        # The public renderer route is database-backed and exists as soon as
        # the intake transaction commits. Do not condition this contract on
        # the optional on-disk artifact writer: Vercel's serverless filesystem
        # may reject that best-effort write even while /sites/{tenant}/web is
        # fully available. Site Magic must always receive the live renderer.
        source_payload["renderer_baseline"] = {
            "path": f"/sites/{submission.tenant_id}/web",
            "pages": (
                renderer_result.pages
                if renderer_result is not None
                else ["home", "about", "contact", "services"]
            ),
        }

        job = SiteMagicRepository(conn).create_job(
            tenant_id=submission.tenant_id,
            source_type="intake",
            source_payload=source_payload,
        )
        request.app.state.site_magic_queue.enqueue(job_id=job.job_id, tenant_id=submission.tenant_id)
        conn.commit()
    except SiteMagicNotConfiguredError:
        conn.rollback()
        logger.info("site_magic_enqueue_skipped tenant_id=%s reason=not_configured", submission.tenant_id)
    except Exception as exc:
        # Deliberately broad. This function's contract is that a Site Magic
        # failure never fails the intake response, and the previous
        # `except DB_ERRORS` did not honour it: on 2026-08-12 the first real
        # production intake raised TypeError here (jsonb decoded to a dict,
        # then json.loads() on it), which matched no handler and surfaced to
        # the prospect as a bare 500 -- after their tenant, submission, and
        # tracking number had already been committed. Narrowing this back to
        # specific types re-opens that hole; the enqueue is best-effort and
        # every failure mode belongs in the log, not in the response.
        conn.rollback()
        logger.error(
            "site_magic_enqueue_failed tenant_id=%s error_type=%s",
            submission.tenant_id, type(exc).__name__,
        )
    finally:
        conn.close()


@intake_router.get("/intake/presets")
def list_presets() -> dict:
    """All supported industries, for populating the intake form's industry
    selector without hardcoding the list on the frontend side.
    """
    return {"industries": SUPPORTED_INDUSTRIES}


@intake_router.get("/intake/presets/{industry}")
def industry_preset(industry: str) -> dict:
    """Per-trade hint text and FSM software options for one industry.
    Always resolves (falls back to 'Other') -- see trade_presets.get_preset.
    """
    return get_preset(industry)
