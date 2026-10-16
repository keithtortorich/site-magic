"""Sam's HTTP surface: quote generation, retrieval, acceptance.

Routes: POST /quotes/generate, GET /quotes/{id}, POST /quotes/{id}/accept
Thin validation layer; business logic delegated to pricing.py and objections.py.
Tenant isolation enforced per endpoint.

Per CLAUDE.md: POST routes carry no CORS headers (server-to-server only).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ...db import DB_ERRORS, get_connection as _db_get_connection
from ...tenant import InvalidTenantError, Tenant
from ..angel.api_auth import SharedSecretVerifier, internal_api_verifier_from_env
from .client import GoHighLevelQuoteClient, ghl_quote_client_from_env
from .objections import ObjectionLibrary
from .pricing import PricingEngine
from .protocol import GHLQuoteClient, NullGHLQuoteClient
from .quote_repository import Quote, QuoteRepository

logger = logging.getLogger("webstaffr.sam.router")


class GenerateQuoteRequest(BaseModel):
    """Generate a quote for a lead."""

    tenant_id: str
    contact_id: str
    contact_name: str = Field(..., min_length=1)
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    service_scope: str = Field(..., min_length=5, max_length=2000)
    industry: Optional[str] = None
    location: Optional[str] = None
    urgency: str = Field(default="routine", pattern="^(routine|urgent|emergency)$")
    auto_send: bool = True  # If True, send via GHL immediately


class QuoteResponse(BaseModel):
    """A generated quote."""

    quote_id: str
    tenant_id: str
    contact_id: str
    contact_name: str
    contact_email: Optional[str]
    estimated_range_low: float
    estimated_range_high: float
    caveat: str
    status: str
    email_sent: bool
    created_at: str


class QuoteDetailResponse(BaseModel):
    """Full quote details for GET /quotes/{id}."""

    quote_id: str
    tenant_id: str
    contact_id: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    service_scope: str
    industry: Optional[str]
    estimated_range_low: float
    estimated_range_high: float
    caveat: str
    status: str
    created_at: str
    sent_at: Optional[str]
    accepted_at: Optional[str]
    declined_at: Optional[str]
    appointment_id: Optional[int]


class AcceptQuoteRequest(BaseModel):
    """Accept a quote and create an appointment."""

    tenant_id: str
    preferred_time: Optional[str] = None  # ISO 8601 datetime


class QuoteAcceptedResponse(BaseModel):
    """Response when quote is accepted."""

    quote_id: str
    appointment_id: int
    status: str
    accepted_at: str
    appointment_scheduled: bool


def create_sam_router(
    db_path: str = "webstaffr.db",
    ghl_client: Optional[GHLQuoteClient] = None,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
) -> APIRouter:
    """Factory (not a module-level router) so the caller controls db_path and GHL client.

    Same pattern as create_angel_router() and create_retell_router().
    """

    router = APIRouter()

    # Use provided GHL client, fall back to env, otherwise use Null default
    active_ghl_client = ghl_client or ghl_quote_client_from_env() or NullGHLQuoteClient()
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()

    def require_internal_auth(x_api_key: Optional[str]) -> None:
        if not active_internal_api_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    def get_connection():
        """Get DB connection, raising 503 on failure."""
        try:
            return _db_get_connection(db_path)
        except DB_ERRORS as exc:
            logger.error("sam_db_connection_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    @router.post("/quotes/generate", response_model=QuoteResponse)
    def generate_quote(
        req: GenerateQuoteRequest,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> QuoteResponse:
        """Generate and optionally send a quote.

        Validates service scope, pulls pricing from trade presets,
        creates quote record, optionally sends via GHL email.

        Server-to-server route: no CORS headers.
        """
        require_internal_auth(x_api_key)
        try:
            tenant = Tenant(tenant_id=req.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not req.service_scope.strip():
            raise HTTPException(status_code=400, detail="service_scope must not be empty")

        # Generate pricing estimate
        estimate = PricingEngine.generate_estimate(
            service_scope=req.service_scope,
            industry=req.industry or "Other",
            location=req.location,
            urgency=req.urgency,
        )

        # Create quote record
        conn = get_connection()
        try:
            quote = QuoteRepository.create_quote(
                conn=conn,
                tenant_id=req.tenant_id,
                contact_id=req.contact_id,
                contact_name=req.contact_name,
                contact_email=req.contact_email,
                service_scope=req.service_scope,
                industry=estimate.industry,
                estimated_range_low=estimate.estimated_range_low,
                estimated_range_high=estimate.estimated_range_high,
                caveat=estimate.caveat,
                email_template=None,  # Will be filled if we send
            )

            # Send via GHL if requested and email is available
            email_sent = False
            if req.auto_send and req.contact_email and req.contact_name:
                try:
                    email_body = _build_quote_email(
                        contact_name=req.contact_name,
                        quote=quote,
                        industry=estimate.industry,
                    )
                    active_ghl_client.send_quote_email(
                        contact_id=req.contact_id,
                        quote_id=quote.id,
                        email_body=email_body,
                        subject=f"Your Estimate from {req.contact_name}'s Business",
                    )

                    # Mark as sent in DB
                    quote = QuoteRepository.update_quote_sent(conn, quote.id, req.tenant_id, email_body)
                    email_sent = True
                    logger.info("quote_email_sent quote_id=%s contact_id=%s", quote.id, req.contact_id)
                except Exception as exc:
                    # Log but don't fail -- quote is still created locally
                    logger.warning(
                        "quote_email_send_failed quote_id=%s error_type=%s",
                        quote.id,
                        type(exc).__name__,
                    )

            # Log quote in GHL contact notes for sales visibility
            try:
                active_ghl_client.log_quote_note(
                    contact_id=req.contact_id,
                    quote_id=quote.id,
                    estimate_range=(quote.estimated_range_low, quote.estimated_range_high),
                )
            except Exception as exc:
                logger.warning(
                    "quote_note_log_failed quote_id=%s error_type=%s",
                    quote.id,
                    type(exc).__name__,
                )

            conn.commit()
        finally:
            conn.close()

        logger.info("quote_generated quote_id=%s tenant=%s email_sent=%s", quote.id, req.tenant_id, email_sent)
        return QuoteResponse(
            quote_id=quote.id,
            tenant_id=quote.tenant_id,
            contact_id=quote.contact_id,
            contact_name=quote.contact_name or "",
            contact_email=quote.contact_email,
            estimated_range_low=quote.estimated_range_low,
            estimated_range_high=quote.estimated_range_high,
            caveat=quote.caveat,
            status=quote.status,
            email_sent=email_sent,
            created_at=quote.created_at,
        )

    @router.get("/quotes/{quote_id}", response_model=QuoteDetailResponse)
    def get_quote(
        quote_id: str,
        tenant_id: str,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> QuoteDetailResponse:
        """Retrieve a quote by ID (tenant-scoped).

        Server-to-server route: no CORS headers.
        """
        require_internal_auth(x_api_key)
        try:
            tenant = Tenant(tenant_id=tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        conn = get_connection()
        try:
            quote = QuoteRepository.get_quote(conn, quote_id, tenant_id)
        finally:
            conn.close()

        if not quote:
            raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")

        return QuoteDetailResponse(
            quote_id=quote.id,
            tenant_id=quote.tenant_id,
            contact_id=quote.contact_id,
            contact_name=quote.contact_name,
            contact_email=quote.contact_email,
            service_scope=quote.service_scope,
            industry=quote.industry,
            estimated_range_low=quote.estimated_range_low,
            estimated_range_high=quote.estimated_range_high,
            caveat=quote.caveat,
            status=quote.status,
            created_at=quote.created_at,
            sent_at=quote.sent_at,
            accepted_at=quote.accepted_at,
            declined_at=quote.declined_at,
            appointment_id=quote.appointment_id,
        )

    @router.post("/quotes/{quote_id}/accept", response_model=QuoteAcceptedResponse)
    def accept_quote(
        quote_id: str,
        req: AcceptQuoteRequest,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> QuoteAcceptedResponse:
        """Accept a quote and create an appointment.

        Calls Angel's book_appointment logic under the hood.
        Server-to-server route: no CORS headers.
        """
        require_internal_auth(x_api_key)
        try:
            tenant = Tenant(tenant_id=req.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        conn = get_connection()
        try:
            # Fetch quote to confirm it exists and belongs to this tenant
            quote = QuoteRepository.get_quote(conn, quote_id, req.tenant_id)
            if not quote:
                raise HTTPException(status_code=404, detail=f"Quote {quote_id} not found")

            # Import Angel here to use its booking logic
            from ..angel.angel import Angel

            angel = Angel(tenant=tenant, conn=conn)
            appt = angel.book_appointment(
                contact_name=quote.contact_name or "Contact",
                starts_at=req.preferred_time or "2026-08-10T10:00:00Z",
                contact_phone=None,
                contact_email=quote.contact_email,
                notes=f"Quote accepted: {quote.id}",
                sync_to_ghl=True,
                ghl_contact_id=quote.contact_id,
            )

            # Link quote to appointment
            quote = QuoteRepository.update_quote_accepted(conn, quote_id, req.tenant_id, appt.appointment_id)
            conn.commit()

            logger.info(
                "quote_accepted quote_id=%s appointment_id=%s tenant=%s",
                quote_id,
                appt.appointment_id,
                req.tenant_id,
            )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(
                "quote_accept_failed quote_id=%s error_type=%s",
                quote_id,
                type(exc).__name__,
            )
            raise HTTPException(status_code=500, detail="Failed to create appointment") from exc
        finally:
            conn.close()

        return QuoteAcceptedResponse(
            quote_id=quote.id,
            appointment_id=quote.appointment_id or 0,
            status="accepted",
            accepted_at=quote.accepted_at or "",
            appointment_scheduled=True,
        )

    return router


def _build_quote_email(contact_name: str, quote: Quote, industry: str) -> str:
    """Build HTML email body for a quote.

    Professional, not salesy. Always shows range + caveat, never specific numbers
    without context.
    """
    low = f"{quote.estimated_range_low:,.0f}"
    high = f"{quote.estimated_range_high:,.0f}"

    if quote.estimated_range_low == 0 and quote.estimated_range_high == 0:
        # Contact for quote scenario
        estimate_section = f"""
        <p>Based on the service you described, we recommend getting a site inspection to provide you with an accurate quote.</p>
        <p>Our team will assess your specific situation and provide a detailed estimate during the visit.</p>
        """
    else:
        estimate_section = f"""
        <p><strong>Estimated range: ${low} - ${high}</strong></p>
        <p>This estimate is based on the description you provided. {quote.caveat}</p>
        """

    objection_responses = ObjectionLibrary.get_response("cost", industry, {"business_name": contact_name})

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <p>Hi {contact_name},</p>

        <p>Thank you for reaching out! We've reviewed the details of your {industry.lower()} service request.</p>

        {estimate_section}

        <h3>Next Steps</h3>
        <p>Our team will contact you to confirm whether a site visit is needed. If scheduled, the visit will:</p>
        <ul>
            <li>Assess your specific situation in detail</li>
            <li>Answer any questions you have</li>
            <li>Provide a final quote before any work begins</li>
        </ul>

        <p>We look forward to helping you out.</p>

        <p>Best regards,<br/>
        The {industry} Team</p>
    </body>
    </html>
    """.strip()

    return html
