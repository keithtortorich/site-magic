"""Public, tenant-scoped service-request endpoint for generated sites."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from starlette.concurrency import run_in_threadpool

from .db import DB_ERRORS, StorageError, get_connection
from .intake import IntakeRepository
from .rate_limit import RateLimitExceeded, check_dimensions, direct_client_ip
from .site_renderer import service_pages
from .tenant import InvalidTenantError, Tenant
from .website_leads import WebsiteLead, WebsiteLeadRepository
from .workers.angel.ghl import GHLClient

logger = logging.getLogger("webstaffr.website_lead_router")

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SERVICE_SOURCE_PATTERN = re.compile(r"^/services/([a-z0-9]+(?:-[a-z0-9]+)*)$")


class WebsiteLeadRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=254)
    message: str = Field(min_length=1, max_length=2000)
    service: Optional[str] = Field(default=None, max_length=160)
    source_path: Optional[str] = Field(default=None, max_length=500)
    website: Optional[str] = Field(default=None, max_length=200)

    @field_validator("name", "phone", "email", "message", "service", "source_path", "website")
    @classmethod
    def strip_strings(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return value.strip()

    @model_validator(mode="after")
    def validate_contact_and_content(self):
        if not self.name:
            raise ValueError("name must not be blank")
        if not self.message:
            raise ValueError("message must not be blank")
        if not self.phone and not self.email:
            raise ValueError("phone or email is required")
        if self.email and not _EMAIL_PATTERN.fullmatch(self.email):
            raise ValueError("email is invalid")
        return self


def _payload_from_form_body(body: bytes) -> dict:
    try:
        decoded = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid lead request") from exc
    return {key: values[-1] for key, values in parse_qs(decoded, keep_blank_values=True).items()}


async def _parse_payload(request: Request) -> tuple[WebsiteLeadRequest, bool]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    wants_json = content_type == "application/json"
    try:
        raw = await request.json() if wants_json else _payload_from_form_body(await request.body())
        return WebsiteLeadRequest.model_validate(raw), wants_json
    except (ValidationError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Invalid lead request") from exc


def _normalize_service_and_source(submission, requested_service: Optional[str], source_path: Optional[str]):
    published = service_pages({"services": submission.services})
    names_by_slug = {item["slug"]: item["name"] for item in published}
    names = set(names_by_slug.values())

    service = requested_service if requested_service in names else None
    normalized_source = source_path if source_path in {"/", "/contact"} else None
    if source_path:
        match = _SERVICE_SOURCE_PATTERN.fullmatch(source_path)
        if match and match.group(1) in names_by_slug:
            normalized_source = source_path
            if service is None:
                service = names_by_slug[match.group(1)]
    return service, normalized_source


def _confirmation_html(lead_id: str, site_path: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Request received</title></head><body><main>"
        "<h1>Request received</h1><p>Your service request was saved.</p>"
        f"<p>Reference: <code>{lead_id}</code></p>"
        f"<p><a href=\"{site_path}\">Return to the site</a></p>"
        "</main></body></html>"
    )


def _record_forward_result(
    db_path: str,
    tenant_id: str,
    lead_id: str,
    *,
    contact_id: Optional[str] = None,
    error_code: Optional[str] = None,
) -> None:
    """Best-effort bookkeeping that never changes the public response."""
    try:
        conn = get_connection(db_path)
        try:
            repository = WebsiteLeadRepository(conn)
            if contact_id:
                if error_code:
                    repository.mark_forward_failed(
                        tenant_id, lead_id, error_code, contact_id
                    )
                else:
                    repository.mark_forwarded(tenant_id, lead_id, contact_id)
            elif error_code:
                repository.mark_forward_failed(tenant_id, lead_id, error_code)
            conn.commit()
        except (StorageError, *DB_ERRORS):
            conn.rollback()
            raise
        finally:
            conn.close()
    except (StorageError, *DB_ERRORS) as exc:
        logger.error(
            "website_lead_forward_status_failed error_type=%s",
            type(exc).__name__,
        )


def create_website_lead_router(ghl_client: Optional[GHLClient] = None) -> APIRouter:
    router = APIRouter()

    @router.post("/sites/{tenant_id}/leads")
    async def submit_website_lead(tenant_id: str, request: Request):
        try:
            Tenant(tenant_id=tenant_id)
        except InvalidTenantError as exc:
            raise HTTPException(status_code=404, detail="Site not found") from exc

        payload, wants_json = await _parse_payload(request)
        lead_id = str(uuid.uuid4())
        stored = False
        service = None

        try:
            conn = get_connection(request.app.state.db_path)
        except DB_ERRORS as exc:
            logger.error("website_lead_db_connection_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Lead capture temporarily unavailable") from exc

        try:
            submission = IntakeRepository(conn).load_latest_for_tenant(tenant_id)
            if submission is None:
                raise HTTPException(status_code=404, detail="Site not found")

            try:
                check_dimensions(
                    conn,
                    "website_leads",
                    [
                        ("account", tenant_id),
                        ("ip", direct_client_ip(request)),
                    ],
                )
            except RateLimitExceeded as exc:
                conn.commit()
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again shortly.",
                ) from exc

            if not payload.website:
                service, source_path = _normalize_service_and_source(
                    submission,
                    payload.service,
                    payload.source_path,
                )
                WebsiteLeadRepository(conn).save(
                    WebsiteLead(
                        lead_id=lead_id,
                        tenant_id=tenant_id,
                        name=payload.name,
                        phone=payload.phone or None,
                        email=payload.email or None,
                        message=payload.message,
                        service=service,
                        source_path=source_path,
                    )
                )
                stored = True
            conn.commit()
        except HTTPException:
            raise
        except (StorageError, *DB_ERRORS) as exc:
            conn.rollback()
            logger.error("website_lead_save_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Lead capture temporarily unavailable") from exc
        finally:
            conn.close()

        # Persist first. External forwarding is deliberately best effort and
        # can never roll back or hide a locally accepted service request.
        if stored and ghl_client is not None:
            contact_id = None
            try:
                result = await run_in_threadpool(
                    ghl_client.upsert_contact,
                    payload.name,
                    payload.phone or None,
                    payload.email or None,
                    f"NetBuild.Pro website ({tenant_id})",
                )
                contact_id = str((result.get("contact") or {}).get("id") or "").strip()
                if not contact_id:
                    raise RuntimeError("GHL response missing contact id")
                note = f"Website service request for {submission.biz_name} ({tenant_id})"
                if service:
                    note += f", service: {service}"
                safe_message = re.sub(
                    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", payload.message
                )
                note += f": {safe_message}"
                await run_in_threadpool(ghl_client.log_note, contact_id, note)
            except Exception as exc:  # noqa: BLE001 - provider failures are isolated
                error_code = type(exc).__name__
                logger.warning(
                    "website_lead_forward_failed tenant=%s lead_id=%s error_type=%s",
                    tenant_id,
                    lead_id,
                    error_code,
                )
                _record_forward_result(
                    request.app.state.db_path,
                    tenant_id,
                    lead_id,
                    contact_id=contact_id,
                    error_code=error_code,
                )
            else:
                _record_forward_result(
                    request.app.state.db_path,
                    tenant_id,
                    lead_id,
                    contact_id=contact_id,
                )

        logger.info("website_lead_received tenant=%s lead_id=%s", tenant_id, lead_id)
        if wants_json:
            return JSONResponse(
                status_code=201,
                content={"lead_id": lead_id, "status": "received"},
            )
        return HTMLResponse(
            status_code=201,
            content=_confirmation_html(lead_id, f"/sites/{tenant_id}/web"),
        )

    return router
