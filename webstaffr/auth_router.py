"""Browser-facing customer session bootstrap and local revocation routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from .customer_auth import CustomerAuthorizer


def create_auth_router(authorizer: CustomerAuthorizer) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/session")
    def start_customer_session(request: Request) -> dict:
        identity = authorizer.start_session(request)
        return {
            "authenticated": True,
            "expires_at": identity.expires_at.isoformat(),
        }

    @router.post("/auth/logout")
    def revoke_customer_session(request: Request) -> dict:
        authorizer.revoke_session(request)
        return {"revoked": True}

    return router
