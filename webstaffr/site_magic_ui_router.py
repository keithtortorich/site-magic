"""Operator-facing Site Magic workspace shell.

The shell is intentionally thin: authorization and product state transitions
remain in the tenant-scoped control-plane API. Browser code only renders those
projections and sends explicit commands, so a generated draft is never
presented as approved, a preview is never presented as published, and release
is always a separate operator action.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .tenant import InvalidTenantError, Tenant

site_magic_ui_router = APIRouter(tags=["site-magic-ui"])
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _validate_tenant(tenant_id: str) -> None:
    try:
        Tenant(tenant_id=tenant_id)
    except InvalidTenantError as exc:
        raise HTTPException(status_code=404, detail="No Site Magic workspace for this tenant") from exc


def _render(request: Request, tenant_id: str) -> HTMLResponse:
    return _templates.TemplateResponse(
        request,
        "site_magic_operator.html",
        {
            "tenant_id": tenant_id,
            "api_base": str(request.base_url).rstrip("/"),
            "supabase_url": os.environ.get("SUPABASE_URL", ""),
            "supabase_key": os.environ.get("SUPABASE_PUBLISHABLE_KEY", ""),
        },
    )


@site_magic_ui_router.get("/site-magic", response_class=HTMLResponse)
def site_magic_entry(request: Request) -> HTMLResponse:
    return _render(request, "")


@site_magic_ui_router.get("/tenants/{tenant_id}/site-magic", response_class=HTMLResponse)
def site_magic_workspace(tenant_id: str, request: Request) -> HTMLResponse:
    _validate_tenant(tenant_id)
    return _render(request, tenant_id)
