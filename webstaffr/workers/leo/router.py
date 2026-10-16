"""Leo's HTTP surface: /webhooks/ghl/lead for instant lead follow-up.

Same pattern as Angel's router -- thin per-endpoint validation, no business
logic (that lives in scoring.py). App assembly and router inclusion lives in
webstaffr/app.py.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ...db import DB_ERRORS, get_connection as _db_get_connection
from ...rate_limit import RateLimitExceeded, check_and_increment
from ...tenant import InvalidTenantError, Tenant
from ..angel.api_auth import SharedSecretVerifier, internal_api_verifier_from_env
from .protocol import GHLMessagingClient
from .scoring import calculate_aokai_score

logger = logging.getLogger("webstaffr.leo.router")

# Same message length limit as Angel (/chat messages have max_length=4000)
_MAX_MESSAGE_LENGTH = 4000

# Import verifier from Angel's module (GHL webhook verification is shared)
try:
    from ..angel.api_auth import ghl_webhook_verifier_from_env
except ImportError:
    # Fallback if import fails during testing
    from ..angel.api_auth import SharedSecretVerifier

    def ghl_webhook_verifier_from_env():
        return SharedSecretVerifier(env_key="GHL_WEBHOOK_SECRET")


class LeadWebhookEvent(BaseModel):
    """Incoming lead event from GoHighLevel. Minimal schema: extra fields
    are ignored by pydantic, but critical fields must be present."""

    tenant_id: str
    event_type: str  # e.g. "lead_created"
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    business_name: Optional[str] = None
    industry: Optional[str] = None
    # Accessibility signals
    company_phone_answered: Optional[bool] = None
    owner_answered: Optional[bool] = None
    text_enabled: Optional[bool] = None
    # Business size signals
    employee_count: Optional[int] = None
    vehicle_count: Optional[int] = None
    currently_hiring: Optional[bool] = None
    multiple_locations: Optional[bool] = None
    # Digital maturity signals
    has_website: Optional[bool] = None
    has_booking_system: Optional[bool] = None
    has_crm: Optional[bool] = None
    has_diy_platform: Optional[bool] = None
    # Buying signal indicators
    hiring_office_staff: Optional[bool] = None
    active_reviews_count: Optional[int] = None
    offers_financing: Optional[bool] = None
    recent_service_history: Optional[bool] = None


class ScoreRequest(BaseModel):
    """Internal scoring endpoint (for testing/debugging). Same fields as the
    webhook event, but optional tenant_id."""

    tenant_id: Optional[str] = None
    contact_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    business_name: Optional[str] = None
    industry: Optional[str] = None
    company_phone_answered: Optional[bool] = None
    owner_answered: Optional[bool] = None
    text_enabled: Optional[bool] = None
    employee_count: Optional[int] = None
    vehicle_count: Optional[int] = None
    currently_hiring: Optional[bool] = None
    multiple_locations: Optional[bool] = None
    has_website: Optional[bool] = None
    has_booking_system: Optional[bool] = None
    has_crm: Optional[bool] = None
    has_diy_platform: Optional[bool] = None
    hiring_office_staff: Optional[bool] = None
    active_reviews_count: Optional[int] = None
    offers_financing: Optional[bool] = None
    recent_service_history: Optional[bool] = None


class ScoreResponse(BaseModel):
    score_accessibility: int
    score_business_size: int
    score_digital_maturity: int
    score_revenue_potential: int
    score_buying_signals: int
    score_total: int
    tier: int


class LeadWebhookResponse(BaseModel):
    status: str  # "processed" or "processed_partially"
    lead_id: int
    score: int
    tier: int
    first_touch: str  # "sms" or "email"
    sync_status: str = "synced"  # "synced" or "pending_sync"
    ghl_error: Optional[str] = None


SUPPORTED_EVENT_TYPES = {"lead_created", "contact_updated"}


def _first_touch_channel(tier: int) -> str:
    """Maps tier to first-touch channel: SMS for Tier 1-2 (call-led),
    email for Tier 3 (nurture-led), none for Tier 4 (skip)."""
    if tier in (1, 2):
        return "sms"
    if tier == 3:
        return "email"
    return ""  # Tier 4: skip


def _sms_template_tier_1_2(business_name: Optional[str] = None) -> str:
    """SMS template for Tier 1-2 leads (call-led immediate/same-day follow-up).
    Compact, CTA-focused, asks for callback or demo link."""
    if business_name:
        return f"Hi! NetBuild.Pro helps businesses like {business_name} capture customer requests through a dedicated site and verified call-handling workflow. Would you like details? Reply YES"
    return "Hi! NetBuild.Pro combines a customer site with verified call handling and lead routing. Would you like details? Reply YES"


def _email_template_tier_3(business_name: Optional[str] = None, contact_name: Optional[str] = None) -> tuple[str, str]:
    """Email template for Tier 3 leads (nurture-led, lower priority).
    Returns (subject, body)."""
    greeting = f"Hi {contact_name}," if contact_name else "Hi there,"
    if business_name:
        body = f"""{greeting}

Customer requests can arrive while your team is busy in the field.

NetBuild.Pro combines a customer-ready site with lead capture and a call-handling workflow that is activated after its integrations are verified.

If that workflow is relevant to {business_name}, reply and we will share the current setup details.

Talk soon,
NetBuild.Pro"""
    else:
        body = f"""{greeting}

Customer requests can arrive while your team is busy in the field.

NetBuild.Pro combines a customer-ready site with lead capture and a call-handling workflow that is activated after its integrations are verified.

Reply if you would like the current setup details.

Talk soon,
NetBuild.Pro"""

    subject = f"Customer-request workflow for {business_name}" if business_name else "Customer site and call-handling workflow"
    return subject, body


def create_leo_router(
    db_path: str = "webstaffr.db",
    ghl_messaging_client: Optional[GHLMessagingClient] = None,
    ghl_webhook_verifier = None,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
) -> APIRouter:
    """Factory for Leo's router (same pattern as Angel's create_angel_router).
    The caller controls db_path, backends, and verifiers."""

    router = APIRouter()

    # Verifier: explicit arg wins, otherwise fall back to env, otherwise Null
    active_ghl_webhook_verifier = ghl_webhook_verifier or ghl_webhook_verifier_from_env()
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()

    def get_connection():
        """Same pattern as Angel: DB error → 503, never propagate raw error."""
        try:
            return _db_get_connection(db_path)
        except DB_ERRORS as exc:
            logger.error("leo_db_connection_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    @router.post("/leo/score", response_model=ScoreResponse)
    def score_lead(
        req: ScoreRequest,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> ScoreResponse:
        """Internal scoring endpoint for testing/debugging. No webhook
        verification, no GHL sync, just AOKAI calculation."""

        if not active_internal_api_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        result = calculate_aokai_score(
            phone_answered=req.company_phone_answered,
            owner_answered=req.owner_answered,
            text_enabled=req.text_enabled,
            email=req.email,
            employee_count=req.employee_count,
            vehicle_count=req.vehicle_count,
            currently_hiring=req.currently_hiring,
            multiple_locations=req.multiple_locations,
            has_website=req.has_website,
            has_booking_system=req.has_booking_system,
            has_crm=req.has_crm,
            has_diy_platform=req.has_diy_platform,
            industry=req.industry,
            hiring_office_staff=req.hiring_office_staff,
            active_reviews_count=req.active_reviews_count,
            offers_financing=req.offers_financing,
            recent_service_history=req.recent_service_history,
        )

        return ScoreResponse(
            score_accessibility=result.score_accessibility,
            score_business_size=result.score_business_size,
            score_digital_maturity=result.score_digital_maturity,
            score_revenue_potential=result.score_revenue_potential,
            score_buying_signals=result.score_buying_signals,
            score_total=result.score_total,
            tier=result.tier,
        )

    @router.post("/webhooks/ghl/lead", response_model=LeadWebhookResponse)
    def ghl_lead_webhook(
        event: LeadWebhookEvent,
        x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    ) -> LeadWebhookResponse:
        """Receive and process new leads from GoHighLevel. Scores the lead,
        determines tier, sends first-touch outreach (SMS for Tier 1-2,
        email for Tier 3), stores lead record for tracking."""

        # Verify webhook signature
        if not active_ghl_webhook_verifier.verify(x_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

        # Validate tenant
        try:
            tenant = Tenant(tenant_id=event.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Validate event type
        if event.event_type not in SUPPORTED_EVENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported event_type: {event.event_type!r}. "
                f"Supported: {sorted(SUPPORTED_EVENT_TYPES)}",
            )

        conn = get_connection()
        try:
            # Rate limit (same counter as /chat and /webhooks/ghl)
            try:
                check_and_increment(conn, event.tenant_id, "webhooks_ghl_lead")
            except RateLimitExceeded as exc:
                conn.commit()  # preserve counter increment
                raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly.") from exc

            # Calculate AOKAI score
            score_result = calculate_aokai_score(
                phone_answered=event.company_phone_answered,
                owner_answered=event.owner_answered,
                text_enabled=event.text_enabled,
                email=event.email,
                employee_count=event.employee_count,
                vehicle_count=event.vehicle_count,
                currently_hiring=event.currently_hiring,
                multiple_locations=event.multiple_locations,
                has_website=event.has_website,
                has_booking_system=event.has_booking_system,
                has_crm=event.has_crm,
                has_diy_platform=event.has_diy_platform,
                industry=event.industry,
                hiring_office_staff=event.hiring_office_staff,
                active_reviews_count=event.active_reviews_count,
                offers_financing=event.offers_financing,
                recent_service_history=event.recent_service_history,
            )

            # Determine first-touch channel
            first_touch_channel = _first_touch_channel(score_result.tier)

            # Insert lead record into database
            cursor = conn.execute(
                """
                INSERT INTO webstaffr_leads (
                  tenant_id, ghl_contact_id, contact_name, phone, email,
                  business_name, industry,
                  score_accessibility, score_business_size, score_digital_maturity,
                  score_revenue_potential, score_buying_signals, score_total,
                  tier, first_touch_channel, sync_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.tenant_id,
                    event.contact_id,
                    event.contact_name,
                    event.phone,
                    event.email,
                    event.business_name,
                    event.industry,
                    score_result.score_accessibility,
                    score_result.score_business_size,
                    score_result.score_digital_maturity,
                    score_result.score_revenue_potential,
                    score_result.score_buying_signals,
                    score_result.score_total,
                    score_result.tier,
                    first_touch_channel,
                    "synced",  # initial status
                ),
            )
            lead_id = cursor.lastrowid

            # Send first-touch outreach via GHL (if client configured and tier < 4)
            ghl_error = None
            sync_status = "synced"

            if ghl_messaging_client and first_touch_channel and score_result.tier < 4:
                try:
                    if first_touch_channel == "sms" and event.contact_id and event.phone:
                        # Send SMS for Tier 1-2
                        sms_body = _sms_template_tier_1_2(event.business_name)
                        ghl_messaging_client.send_sms(event.contact_id, sms_body)
                        conn.execute(
                            "UPDATE webstaffr_leads SET first_touch_sent_at = CURRENT_TIMESTAMP WHERE lead_id = ?",
                            (lead_id,),
                        )

                    elif first_touch_channel == "email" and event.contact_id and event.email:
                        # Send email for Tier 3
                        subject, body = _email_template_tier_3(event.business_name, event.contact_name)
                        ghl_messaging_client.send_email(event.contact_id, subject, body)
                        conn.execute(
                            "UPDATE webstaffr_leads SET first_touch_sent_at = CURRENT_TIMESTAMP WHERE lead_id = ?",
                            (lead_id,),
                        )

                except Exception as exc:  # noqa: BLE001
                    # Store a safe diagnostic category, never provider
                    # response text or customer data.
                    ghl_error = type(exc).__name__
                    sync_status = "pending_sync"
                    conn.execute(
                        "UPDATE webstaffr_leads SET sync_status = ?, ghl_error = ? WHERE lead_id = ?",
                        (sync_status, ghl_error, lead_id),
                    )
                    logger.warning(
                        "leo_ghl_sync_failed lead_id=%s error_type=%s",
                        lead_id,
                        ghl_error,
                    )

            conn.commit()
        finally:
            conn.close()

        logger.info(
            "ghl_lead_webhook_handled tenant=%s lead_id=%s score=%s tier=%s",
            event.tenant_id,
            lead_id,
            score_result.score_total,
            score_result.tier,
        )

        return LeadWebhookResponse(
            status="processed" if sync_status == "synced" else "processed_partially",
            lead_id=lead_id,
            score=score_result.score_total,
            tier=score_result.tier,
            first_touch=first_touch_channel,
            sync_status=sync_status,
            ghl_error=ghl_error,
        )

    return router
