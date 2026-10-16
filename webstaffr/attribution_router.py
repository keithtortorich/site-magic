"""FastAPI router serving the per-tenant attribution/ROI dashboard reads
(webstaffr/attribution.py). Mounted into the main app via
create_app().include_router(attribution_router) in webstaffr/app.py, same
pattern as intake_router/site_router.

Deliberately read-only from the outside: call events are written by
in-process callers (retell_router.py's webhook handlers, workers/angel/
router.py's /book handler) that already hold an open, tenant-resolved
connection -- not via a public ingestion endpoint. This keeps the public
API surface minimal, avoiding a new unauthenticated write endpoint
alongside /book and /webhooks/ghl -- both of those needed shared-secret
auth added after the fact (see api_auth.py), a lesson worth designing
around here instead of repeating.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from .attribution import CallEventRepository, TrackingNumberRepository
from .customer_auth import CustomerAuthorizer
from .db import DB_ERRORS, get_connection
from .tenant import InvalidTenantError, Tenant

logger = logging.getLogger("webstaffr.attribution_router")

def _get_connection(request: Request):
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        # See site_router.py's identical comment: log the exception type
        # only, never str(exc) (may contain the connection string).
        logger.error("attribution_db_connection_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Attribution data temporarily unavailable") from exc


def _validate_tenant(tenant_id: str) -> None:
    try:
        Tenant(tenant_id=tenant_id)
    except InvalidTenantError as exc:
        # Same non-leaking 404 shape as site_router.get_site_data: a caller
        # shouldn't be able to distinguish "malformed id" from "valid id,
        # no data yet" for a public-facing endpoint.
        raise HTTPException(status_code=404, detail="No tracking data for this tenant") from exc


def create_attribution_router(authorizer: CustomerAuthorizer) -> APIRouter:
    router = APIRouter()

    @router.get("/tenants/{tenant_id}/tracking-number")
    def get_tracking_number(tenant_id: str, request: Request) -> dict:
        context = authorizer.authorize(request, tenant_id, "viewer")
        _validate_tenant(tenant_id)
        conn = _get_connection(request)
        try:
            record = TrackingNumberRepository(conn).get_for_tenant(tenant_id)
        finally:
            conn.close()
        if record is None:
            raise HTTPException(status_code=404, detail="No tracking number for this tenant")
        authorizer.audit(request, context, action="tracking_number.read", resource_type="tracking_number")
        return {"tenant_id": record.tenant_id, "tracking_number": record.tracking_number}

    @router.get("/tenants/{tenant_id}/metrics")
    def get_metrics(tenant_id: str, request: Request) -> dict:
        context = authorizer.authorize(request, tenant_id, "viewer")
        _validate_tenant(tenant_id)
        conn = _get_connection(request)
        try:
            result = CallEventRepository(conn).metrics_for_tenant(tenant_id)
        finally:
            conn.close()
        authorizer.audit(request, context, action="metrics.read", resource_type="call_metrics")
        return result

    @router.get("/tenants/{tenant_id}/calls")
    def list_calls(tenant_id: str, request: Request, limit: int = 50) -> dict:
        context = authorizer.authorize(request, tenant_id, "viewer")
        _validate_tenant(tenant_id)
        capped_limit = max(1, min(limit, 200))
        conn = _get_connection(request)
        try:
            events = CallEventRepository(conn).list_for_tenant(tenant_id, limit=capped_limit)
        finally:
            conn.close()
        result = {
            "tenant_id": tenant_id,
            "calls": [
                {
                    "event_id": e.event_id,
                    "event_type": e.event_type,
                    "call_id": e.call_id,
                    "duration_seconds": e.duration_seconds,
                    "outcome": e.outcome,
                    "created_at": e.created_at,
                }
                for e in events
            ],
        }
        authorizer.audit(request, context, action="calls.read", resource_type="call_event_collection")
        return result

    return router
