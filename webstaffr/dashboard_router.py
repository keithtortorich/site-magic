"""FastAPI router for the client-facing NetBuild dashboard.

Two surfaces:

1. The dashboard SPA shell -- GET /dashboard and
   GET /tenants/{tenant_id}/dashboard serve the same single-file branded
   HTML app (webstaffr/templates/dashboard.html). The shell is public (a
   browser can render the login prompt); it only fetches data once it has
   a Supabase session token.

2. The data API -- GET /tenants/{tenant_id}/dashboard-data returns the
   aggregated JSON payload (webstaffr/dashboard.py). It is gated by
   CustomerAuthorizer at the "viewer" role and tenant-scoped top to
   bottom. This is a read-only endpoint: no write path, no new table.

Read-only and tenant-scoped like attribution_router.py -- same rationale
for not exposing a public write endpoint. CORS: because the path is under
/tenants/, ScopedCORSMiddleware already allows credentialed cross-origin
reads from the configured CUSTOMER_ALLOWED_ORIGINS (see webstaffr/app.py).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .customer_auth import CustomerAuthorizer
from .dashboard import build_dashboard_data, dashboard_data_to_dict
from .db import DB_ERRORS, get_connection
from .tenant import InvalidTenantError, Tenant

logger = logging.getLogger("webstaffr.dashboard_router")

dashboard_router = APIRouter(tags=["dashboard"])

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _get_connection(request: Request):
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        logger.error("dashboard_db_connection_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Dashboard data temporarily unavailable") from exc


def _validate_tenant(tenant_id: str) -> None:
    try:
        Tenant(tenant_id=tenant_id)
    except InvalidTenantError as exc:
        raise HTTPException(status_code=404, detail="No dashboard for this tenant") from exc


def _supabase_env() -> dict:
    return {
        "supabase_url": os.environ.get("SUPABASE_URL", ""),
        "supabase_key": os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
    }


def _render_shell(request: Request, tenant_id: str) -> HTMLResponse:
    env = _supabase_env()
    return _templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "tenant_id": tenant_id,
            "api_base": str(request.base_url).rstrip("/"),
            "supabase_url": env["supabase_url"],
            "supabase_key": env["supabase_key"],
        },
    )


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
def dashboard_entry(request: Request) -> HTMLResponse:
    """Product entry point. Renders the shell in "enter your business code"
    mode; once the visitor supplies a code they are routed to
    /tenants/{code}/dashboard."""
    return _render_shell(request, "")


@dashboard_router.get("/tenants/{tenant_id}/dashboard", response_class=HTMLResponse)
def dashboard_page(tenant_id: str, request: Request) -> HTMLResponse:
    _validate_tenant(tenant_id)
    return _render_shell(request, tenant_id)


@dashboard_router.get("/tenants/{tenant_id}/dashboard-data")
def dashboard_data(tenant_id: str, request: Request) -> dict:
    context = request.app.state.customer_authorizer.authorize(request, tenant_id, "viewer")
    _validate_tenant(tenant_id)
    conn = _get_connection(request)
    try:
        data = build_dashboard_data(conn, tenant_id)
    finally:
        conn.close()
    request.app.state.customer_authorizer.audit(
        request, context, action="dashboard.read", resource_type="dashboard"
    )
    return dashboard_data_to_dict(data)
