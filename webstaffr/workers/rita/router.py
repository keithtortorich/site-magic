"""Rita's HTTP surface: /webhooks/ghl/job_completed, /workers/rita/draft-response.

Kept intentionally thin per-endpoint: validate payload, resolve Tenant, hand off to Rita.
App assembly lives in webstaffr/app.py, not here.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ...db import DB_ERRORS, get_connection as _db_get_connection
from ...rate_limit import RateLimitExceeded, check_and_increment
from ...tenant import InvalidTenantError, Tenant
from .client import ReviewRequestRepository, ReviewResponseRepository
from .protocol import NullReviewPlatformClient, ReviewPlatformClient
from .templates import select_response_template
from ..angel.api_auth import (
    SharedSecretVerifier,
    ghl_webhook_verifier_from_env,
    internal_api_verifier_from_env,
)
from ..angel.ghl import GHLClient, NullGHLClient

logger = logging.getLogger("webstaffr.rita.router")

_MAX_REVIEW_TEXT_LENGTH = 5000


class GHLJobCompletedEvent(BaseModel):
    """Minimal shape of the GHL job_completed event."""
    tenant_id: str
    event_type: str = "job_completed"
    job_id: Optional[str] = None
    contact_id: str
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None


class JobCompletedResponse(BaseModel):
    """Response to job completion webhook."""
    status: str
    request_id: int
    contact_id: str


class DraftResponseRequest(BaseModel):
    """Request to draft a response to an incoming review."""
    tenant_id: str
    review_id: str
    review_text: str = Field(..., max_length=_MAX_REVIEW_TEXT_LENGTH)
    review_rating: int = Field(..., ge=1, le=5)
    review_source: str = "google"


class DraftResponseResponse(BaseModel):
    """Response to draft-response request."""
    response_id: int
    review_id: str
    response_status: str
    response_text: str
    requires_approval: bool


def create_rita_router(
    db_path: str = "webstaffr.db",
    ghl_client: Optional[GHLClient] = None,
    review_platform_client: Optional[ReviewPlatformClient] = None,
    ghl_webhook_verifier = None,
    internal_api_verifier: Optional[SharedSecretVerifier] = None,
) -> APIRouter:
    """Factory for Rita's router."""

    router = APIRouter()

    active_ghl_client = ghl_client or NullGHLClient()
    active_review_platform_client = review_platform_client or NullReviewPlatformClient()
    active_ghl_webhook_verifier = ghl_webhook_verifier or ghl_webhook_verifier_from_env()
    active_internal_api_verifier = internal_api_verifier or internal_api_verifier_from_env()

    def get_connection():
        try:
            return _db_get_connection(db_path)
        except DB_ERRORS as exc:
            logger.error("rita_db_connection_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    @router.post("/webhooks/ghl/job_completed", response_model=JobCompletedResponse)
    def ghl_job_completed(
        event: GHLJobCompletedEvent,
        x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    ) -> JobCompletedResponse:
        """Webhook triggered when a job/appointment is marked complete in GHL."""
        if not active_ghl_webhook_verifier.verify(x_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

        try:
            tenant = Tenant(tenant_id=event.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not event.contact_id.strip():
            raise HTTPException(status_code=400, detail="contact_id must not be empty")

        conn = get_connection()
        try:
            try:
                check_and_increment(conn, event.tenant_id, "webhooks_ghl_job_completed")
            except RateLimitExceeded as exc:
                conn.commit()
                raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly.") from exc

            review_requests = ReviewRequestRepository(conn)
            result = review_requests.create(
                tenant_id=event.tenant_id,
                contact_id=event.contact_id,
                contact_name=event.contact_name,
                contact_phone=event.contact_phone,
                contact_email=event.contact_email,
                ghl_job_id=event.job_id,
                review_source="google",
                request_method="sms" if event.contact_phone else "email",
            )

            request_id = result["request_id"]

            try:
                active_ghl_client.log_note(
                    event.contact_id,
                    f"Review request initiated on {result['created_at']} via Rita",
                )
                review_requests.mark_ghl_synced(event.tenant_id, request_id)
            except Exception as exc:
                logger.warning(
                    "ghl_note_log_failed tenant=%s contact_id=%s error=%s",
                    event.tenant_id,
                    event.contact_id,
                    exc,
                )

            conn.commit()
        finally:
            conn.close()

        logger.info(
            "ghl_job_completed_handled tenant=%s contact_id=%s request_id=%s",
            event.tenant_id,
            event.contact_id,
            request_id,
        )
        return JobCompletedResponse(
            status="review_request_logged",
            request_id=request_id,
            contact_id=event.contact_id,
        )

    @router.post("/workers/rita/draft-response", response_model=DraftResponseResponse)
    def draft_response(
        req: DraftResponseRequest,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> DraftResponseResponse:
        """Draft a response to an incoming review."""
        if not active_internal_api_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        try:
            tenant = Tenant(tenant_id=req.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not req.review_text.strip():
            raise HTTPException(status_code=400, detail="review_text must not be empty")
        if req.review_rating < 1 or req.review_rating > 5:
            raise HTTPException(status_code=400, detail="review_rating must be 1-5")

        conn = get_connection()
        try:
            business_name = tenant.tenant_id
            response_text, requires_approval = select_response_template(
                req.review_rating,
                req.review_text,
                business_name,
            )

            review_responses = ReviewResponseRepository(conn)
            result = review_responses.create(
                tenant_id=req.tenant_id,
                review_source=req.review_source,
                review_rating=req.review_rating,
                review_text=req.review_text,
                response_text=response_text,
                requires_approval=requires_approval,
                external_review_id=req.review_id,
            )

            conn.commit()
        finally:
            conn.close()

        logger.info(
            "review_response_drafted tenant=%s review_id=%s rating=%d requires_approval=%s",
            req.tenant_id,
            req.review_id,
            req.review_rating,
            requires_approval,
        )
        return DraftResponseResponse(
            response_id=result["response_id"],
            review_id=req.review_id,
            response_status=result["response_status"],
            response_text=response_text,
            requires_approval=requires_approval,
        )

    return router
