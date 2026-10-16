"""Angel's own HTTP surface: /chat, /book, /webhooks/ghl.

Kept intentionally thin per-endpoint: the router's job is to validate
the incoming payload, resolve a Tenant, and hand off to Angel -- not to
contain Angel's own logic.

App assembly (FastAPI instance, middleware, other workers' routers) lives
in webstaffr/app.py, the composition root -- not here. This module owns
only Angel's request/response models and its own three endpoints,
exposed as create_angel_router() for app.py to include.
"""

from __future__ import annotations

import logging
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from ...db import DB_ERRORS, get_connection as _db_get_connection
from ...rate_limit import RateLimitExceeded, check_and_increment, check_dimensions, direct_client_ip
from ...tenant import InvalidTenantError, Tenant
from ...webhook_replay import claim_delivery, complete_delivery, payload_digest
from .angel import Angel
from .api_auth import SharedSecretVerifier, book_api_verifier_from_env, ghl_webhook_verifier_from_env
from .ghl import GHLClient
from .voice import VoiceBackend
from .stripe_webhook import stripe_webhook_verifier_from_env

logger = logging.getLogger("webstaffr.angel.router")

# ChatRequest.message and GHLWebhookEvent.message had no length limit --
# capped only by voice.py's max_tokens=500 on Grok's *output*, not the
# caller-supplied input. With GROK_API_KEY live in production, an
# arbitrarily large message is a real, billed xAI cost, not just a
# storage concern. 4000 chars is generous for a real chat turn or
# webhook-sourced message (well beyond a typical SMS/web-form message)
# while bounding the worst case; picked as a round, conservative number,
# not derived from a specific token-cost calculation -- adjust if real
# usage patterns say otherwise.
_MAX_MESSAGE_LENGTH = 4000


class GHLWebhookEvent(BaseModel):
    """Minimal shape of the GHL events this router handles. GHL's real
    payloads carry more fields than this -- extra fields are ignored by
    pydantic by default, so this stays intentionally narrow to what Angel
    actually needs: treat external input as untrusted, validate before
    use."""

    tenant_id: str
    event_type: str  # e.g. "website_lead", "missed_call"
    contact_id: Optional[str] = None
    contact_name: Optional[str] = None
    message: Optional[str] = Field(default=None, max_length=_MAX_MESSAGE_LENGTH)


class StripeWebhookEvent(BaseModel):
    """Minimal shape of Stripe payment events. Stripe's real payloads carry
    more fields -- extra fields are ignored by pydantic by default. Validate
    Stripe's signature server-side before trusting the event."""

    type: str  # e.g. "charge.succeeded", "charge.failed"
    data: dict  # Contains 'object' with charge/payment details
    tenant_id: str  # Added by our webhook handler (not in Stripe's payload)


class ChatRequest(BaseModel):
    tenant_id: str
    message: str = Field(..., max_length=_MAX_MESSAGE_LENGTH)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    reply: str


class BookAppointmentRequest(BaseModel):
    """Exposes Angel.book_appointment over HTTP. Previously only reachable
    in-process (e.g. from the /chat or /webhooks/ghl handlers) -- this is
    for callers that want to book directly without going through a
    conversation turn at all (a future booking UI, a server-side
    integration, etc.)."""

    tenant_id: str
    contact_name: str
    starts_at: str
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    sync_to_ghl: bool = True
    ghl_contact_id: Optional[str] = None


class BookAppointmentResponse(BaseModel):
    appointment_id: int
    tenant_id: str
    contact_name: str
    starts_at: str
    ghl_synced: bool


SUPPORTED_EVENT_TYPES = {"website_lead", "missed_call"}


def create_angel_router(
    db_path: str = "webstaffr.db",
    voice_backend: Optional[VoiceBackend] = None,
    ghl_client: Optional[GHLClient] = None,
    book_api_verifier: Optional[SharedSecretVerifier] = None,
    ghl_webhook_verifier: Optional[SharedSecretVerifier] = None,
    stripe_webhook_verifier: Optional[SharedSecretVerifier] = None,
) -> APIRouter:
    """Factory (not a module-level router) so the caller controls exactly
    which db_path/backends/verifiers Angel's endpoints use, same pattern
    as create_retell_router() and app.create_app()."""

    router = APIRouter()

    # An explicit verifier wins. Environment factories deny access when
    # their credential is absent; permissive verifiers are test-only and
    # must be injected explicitly.
    active_ghl_webhook_verifier = ghl_webhook_verifier or ghl_webhook_verifier_from_env()
    active_book_api_verifier = book_api_verifier or book_api_verifier_from_env()
    active_stripe_webhook_verifier = stripe_webhook_verifier or stripe_webhook_verifier_from_env()

    def get_connection():
        """Backend (SQLite vs Postgres) is chosen by db.get_connection()
        based on DATABASE_URL -- everything downstream of this factory
        doesn't need to know which one it got. Raises HTTPException(503) on
        a DB-layer failure instead of letting a raw psycopg2/sqlite3
        exception propagate to the client."""
        try:
            return _db_get_connection(db_path)
        except DB_ERRORS as exc:
            # Log the exception type only, never str(exc) (may contain the
            # connection string). Shared by /chat, /book, /webhooks/ghl.
            logger.error("angel_db_connection_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable") from exc

    @router.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        """Used by angel-widget.js on generated customer sites -- a direct
        chat turn, separate from the GHL webhook flow below.

        Rate-limited per tenant (see rate_limit.py) since a real, billed
        xAI call happens here once GROK_API_KEY is live -- an
        unauthenticated caller would otherwise have no ceiling on how many
        of those it could trigger."""
        try:
            tenant = Tenant(tenant_id=req.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        conn = get_connection()
        try:
            try:
                check_and_increment(conn, req.tenant_id, "chat")
            except RateLimitExceeded as exc:
                conn.commit()  # keep the counter increment even though this request is rejected
                raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly.") from exc

            angel = Angel(tenant=tenant, conn=conn, voice_backend=voice_backend, ghl_client=ghl_client)
            reply = angel.respond(req.message)
            conn.commit()
        finally:
            conn.close()

        logger.info("chat_handled tenant=%s", req.tenant_id)
        return ChatResponse(reply=reply)

    @router.post("/book", response_model=BookAppointmentResponse)
    def book(
        req: BookAppointmentRequest,
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    ) -> BookAppointmentResponse:
        """Direct booking endpoint -- same underlying Angel.book_appointment
        used by /chat and /webhooks/ghl, exposed for callers that don't go
        through a conversation turn. Untrusted input is validated the same
        way as the other endpoints: reject before touching the DB, not
        after.

        Requires X-API-Key matching BOOK_API_KEY when that env var is set
        (see api_auth.py) -- unconfigured, this remains open, matching this
        repo's existing Null-verifier convention until a real caller and
        secret exist."""
        if not active_book_api_verifier.verify(x_api_key):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        try:
            tenant = Tenant(tenant_id=req.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not req.contact_name.strip():
            raise HTTPException(status_code=400, detail="contact_name must not be empty")
        if not req.starts_at.strip():
            raise HTTPException(status_code=400, detail="starts_at must not be empty")

        conn = get_connection()
        try:
            angel = Angel(tenant=tenant, conn=conn, voice_backend=voice_backend, ghl_client=ghl_client)
            appt = angel.book_appointment(
                contact_name=req.contact_name,
                starts_at=req.starts_at,
                contact_phone=req.contact_phone,
                contact_email=req.contact_email,
                notes=req.notes,
                sync_to_ghl=req.sync_to_ghl,
                ghl_contact_id=req.ghl_contact_id,
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "appointment_booked_via_http tenant=%s appointment_id=%s",
            req.tenant_id,
            appt.appointment_id,
        )
        return BookAppointmentResponse(
            appointment_id=appt.appointment_id,
            tenant_id=appt.tenant_id,
            contact_name=appt.contact_name,
            starts_at=appt.starts_at,
            ghl_synced=appt.ghl_synced,
        )

    @router.post("/webhooks/ghl")
    async def ghl_webhook(
        request: Request,
        event: GHLWebhookEvent,
        x_webhook_secret: Optional[str] = Header(default=None, alias="X-Webhook-Secret"),
    ) -> dict:
        """Requires X-Webhook-Secret matching GHL_WEBHOOK_SECRET when that
        env var is set (see api_auth.py) -- configure it as a custom header
        on GoHighLevel's workflow Webhook action. Unconfigured, this remains
        open, matching this repo's existing Null-verifier convention (same
        shape as Retell's webhook verification before RETELL_WEBHOOK_SECRET
        is set)."""
        if not active_ghl_webhook_verifier.verify(x_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")

        try:
            tenant = Tenant(tenant_id=event.tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if event.event_type not in SUPPORTED_EVENT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported event_type: {event.event_type!r}. "
                f"Supported: {sorted(SUPPORTED_EVENT_TYPES)}",
            )

        raw_body = await request.body()
        event_key = f"payload:{payload_digest(raw_body)}"
        conn = get_connection()
        try:
            try:
                check_dimensions(
                    conn,
                    "webhooks_ghl",
                    [
                        ("account", event.tenant_id),
                        ("principal", "ghl"),
                        ("ip", direct_client_ip(request)),
                    ],
                )
                check_and_increment(conn, event.tenant_id, "webhooks_ghl")
            except RateLimitExceeded as exc:
                conn.commit()  # keep the counter increment even though this request is rejected
                raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly.") from exc

            claim = claim_delivery(
                conn,
                provider="ghl",
                event_key=event_key,
                event_type=event.event_type,
                raw_body=raw_body,
                tenant_id=event.tenant_id,
            )
            if not claim.is_new:
                conn.commit()
                return {"status": "duplicate"}

            angel = Angel(
                tenant=tenant,
                conn=conn,
                voice_backend=voice_backend,
                ghl_client=ghl_client,
            )
            reply = angel.respond(
                event.message or f"New {event.event_type} from {event.contact_name or 'a contact'}.",
                extra_context={"event_type": event.event_type, "contact_id": event.contact_id},
            )
            result = {"status": "handled", "reply": reply}
            complete_delivery(
                conn,
                provider="ghl",
                event_key=event_key,
                response_json=json.dumps(result, sort_keys=True),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "ghl_webhook_handled tenant=%s event_type=%s",
            event.tenant_id,
            event.event_type,
        )
        return result

    @router.post("/webhooks/stripe")
    async def stripe_webhook(
        request: Request,
        payload: dict,
        stripe_signature: Optional[str] = Header(default=None, alias="Stripe-Signature"),
    ) -> dict:
        """Stripe payment status webhook. Requires Stripe-Signature matching
        STRIPE_WEBHOOK_SECRET when that env var is set (see stripe_webhook.py).
        Unconfigured, this remains open (Null-verifier pattern).

        Stripe payload must include:
        - type: event type (e.g. "charge.succeeded", "charge.failed")
        - data.object.metadata.tenant_id: tenant identifier for the appointment
        - data.object.metadata.appointment_id: local appointment ID to update

        On charge.succeeded, updates appointment status to 'paid' in the database.
        On charge.failed, updates status to 'payment_failed'.

        Raw body is read explicitly (Starlette caches it, so `payload`'s own
        parse and this read see the same bytes) because Stripe's HMAC is
        computed over the exact raw bytes it sent, not the re-serialized
        parsed dict -- re-serializing can change byte-for-byte formatting
        and silently break every real signature check.
        """
        raw_body = await request.body()
        if not active_stripe_webhook_verifier.verify(stripe_signature, raw_body):
            raise HTTPException(status_code=401, detail="Invalid or missing webhook signature")

        event_type = payload.get("type", "")
        data = payload.get("data", {})
        charge = data.get("object", {})
        metadata = charge.get("metadata", {})

        tenant_id = metadata.get("tenant_id")
        appointment_id = metadata.get("appointment_id")

        if not tenant_id or not appointment_id:
            raise HTTPException(
                status_code=400,
                detail="Missing tenant_id or appointment_id in Stripe metadata"
            )

        try:
            tenant = Tenant(tenant_id=tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Map Stripe event type to appointment status
        status_map = {
            "charge.succeeded": "paid",
            "charge.failed": "payment_failed",
            "charge.refunded": "refunded",
        }
        new_status = status_map.get(event_type)

        if not new_status:
            logger.info("stripe_webhook_ignored tenant=%s event_type=%s", tenant_id, event_type)
            return {"status": "ignored", "reason": f"Unhandled event type: {event_type}"}

        event_key = payload.get("id") or f"payload:{payload_digest(raw_body)}"
        conn = get_connection()
        try:
            try:
                check_dimensions(
                    conn,
                    "webhooks_stripe",
                    [
                        ("account", tenant_id),
                        ("principal", "stripe"),
                        ("ip", direct_client_ip(request)),
                    ],
                )
            except RateLimitExceeded as exc:
                conn.commit()
                raise HTTPException(status_code=429, detail="Rate limit exceeded, try again shortly.") from exc
            claim = claim_delivery(
                conn,
                provider="stripe",
                event_key=event_key,
                event_type=event_type,
                raw_body=raw_body,
                tenant_id=tenant_id,
            )
            if not claim.is_new:
                conn.commit()
                return {"status": "duplicate", "event_id": event_key}

            # Update appointment status in DB (tenant-scoped by appointment_id + tenant_id WHERE clause)
            cursor = conn.execute(
                "UPDATE appointments SET status = ? WHERE appointment_id = ? AND tenant_id = ?",
                (new_status, int(appointment_id), tenant_id),
            )
            rows_updated = cursor.rowcount
            result = {
                "status": "handled",
                "appointment_id": appointment_id,
                "new_status": new_status,
            }
            complete_delivery(
                conn,
                provider="stripe",
                event_key=event_key,
                response_json=json.dumps(result, sort_keys=True),
            )
            conn.commit()

            if rows_updated == 0:
                logger.warning(
                    "stripe_webhook_no_rows_updated tenant=%s appointment_id=%s event_type=%s",
                    tenant_id,
                    appointment_id,
                    event_type,
                )

            logger.info(
                "stripe_webhook_handled tenant=%s appointment_id=%s event_type=%s new_status=%s",
                tenant_id,
                appointment_id,
                event_type,
                new_status,
            )
        finally:
            conn.close()

        return result

    return router
