"""FastAPI router for the social media marketing integration bridge.

Mounted into the main app via create_app().include_router(social_media_router)
in webstaffr/workers/angel/router.py.

This bridge keeps WS3.3's tenant model separate from SMM's public
social_tenant_id identity: mount records map local tenant_id to
SMM's identity without importing SMM auth or database layout.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .api_auth import SharedSecretVerifier
from ...db import DB_ERRORS, get_connection
from ...integrations.social_media.client import (
    SocialMediaClient,
    SocialMediaHTTPError,
    SocialMediaMount,
    SocialMediaIntent,
)
from ...tenant import InvalidTenantError, Tenant

social_media_router = APIRouter()


def _get_connection(request: Request):
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        raise HTTPException(status_code=503, detail="Social media integration temporarily unavailable") from exc


def _require_auth(request: Request, x_api_key: Optional[str]) -> None:
    verifier: SharedSecretVerifier = request.app.state.internal_api_verifier
    if not verifier.verify(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class MountRequest(BaseModel):
    tenant_id: str
    social_tenant_id: str
    platforms: list[str]
    default_brand_id: Optional[str] = None
    mode: str = "agent_managed"


class IntentRequest(BaseModel):
    campaign_intent: dict
    post_draft: dict


@social_media_router.post("/integrations/social-media/mount")
def mount_integration(
    req: MountRequest,
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> dict:
    _require_auth(request, x_api_key)
    try:
        Tenant(tenant_id=req.tenant_id)
    except InvalidTenantError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    conn = _get_connection(request)
    try:
        client = SocialMediaClient(conn=conn)
        result = client.mount(
            tenant_id=req.tenant_id,
            social_tenant_id=req.social_tenant_id,
            platforms=req.platforms,
            default_brand_id=req.default_brand_id,
            mode=req.mode,
        )
    except SocialMediaHTTPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        conn.close()

    return {
        "mount_id": result.mount_id,
        "tenant_id": result.tenant_id,
        "social_tenant_id": result.social_tenant_id,
        "platforms": result.platforms,
        "default_brand_id": result.default_brand_id,
        "mode": result.mode,
        "created_at": result.created_at,
    }


@social_media_router.post("/integrations/social-media/mount/{mount_id}/intent")
def create_intent(
    mount_id: int,
    req: IntentRequest,
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> dict:
    _require_auth(request, x_api_key)
    conn = _get_connection(request)
    try:
        client = SocialMediaClient(conn=conn)
        intent = client.create_intent(mount_id=mount_id, campaign_intent=req.campaign_intent, post_draft=req.post_draft)
    except SocialMediaHTTPError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        conn.close()

    return {
        "status": "pending_review",
        "workflow_instance_id": f"wf_{intent.intent_id}",
        "approval_url": f"/approvals/wf_{intent.intent_id}",
    }
