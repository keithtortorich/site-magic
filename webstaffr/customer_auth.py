"""Customer identity, session, membership, role, and audit enforcement."""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

import httpx
from fastapi import HTTPException, Request

from .db import DB_ERRORS, get_connection

logger = logging.getLogger("webstaffr.customer_auth")

ROLE_RANK = {"viewer": 10, "dispatcher": 20, "manager": 30, "owner": 40}


@dataclass(frozen=True)
class VerifiedIdentity:
    user_id: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class CustomerContext:
    user_id: str
    session_id: str
    tenant_id: str
    role: str
    correlation_id: str


class IdentityVerifier(Protocol):
    def verify(self, access_token: str) -> Optional[VerifiedIdentity]: ...


class DenyAllIdentityVerifier:
    def verify(self, access_token: str) -> Optional[VerifiedIdentity]:
        return None


class SupabaseIdentityVerifier:
    """Verify bearer tokens against the configured Supabase Auth server."""

    def __init__(self, project_url: str, publishable_key: str, timeout_seconds: float = 5.0):
        self._user_url = f"{project_url.rstrip('/')}/auth/v1/user"
        self._publishable_key = publishable_key
        self._timeout_seconds = timeout_seconds

    @staticmethod
    def _verified_claims(access_token: str) -> Optional[dict]:
        try:
            payload = access_token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        except (IndexError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def verify(self, access_token: str) -> Optional[VerifiedIdentity]:
        try:
            response = httpx.get(
                self._user_url,
                headers={
                    "apikey": self._publishable_key,
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            logger.warning("customer_identity_provider_failed error_type=%s", type(exc).__name__)
            return None
        if response.status_code != 200:
            return None

        claims = self._verified_claims(access_token)
        if claims is None:
            return None
        try:
            provider_user_id = str(response.json()["id"])
            user_id = str(uuid.UUID(str(claims["sub"])))
            session_id = str(uuid.UUID(str(claims["session_id"])))
            expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=timezone.utc)
        except (KeyError, TypeError, ValueError, OverflowError, json.JSONDecodeError):
            return None
        if user_id != provider_user_id or expires_at <= datetime.now(timezone.utc):
            return None
        return VerifiedIdentity(user_id=user_id, session_id=session_id, expires_at=expires_at)


def identity_verifier_from_env() -> IdentityVerifier:
    project_url = os.environ.get("SUPABASE_URL")
    publishable_key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if project_url and publishable_key:
        return SupabaseIdentityVerifier(project_url, publishable_key)
    return DenyAllIdentityVerifier()


def _bearer_token(request: Request) -> Optional[str]:
    scheme, separator, token = request.headers.get("Authorization", "").partition(" ")
    if separator and scheme.lower() == "bearer" and token:
        return token
    return None


def _correlation_id(request: Request) -> str:
    supplied = request.headers.get("X-Correlation-ID")
    try:
        value = str(uuid.UUID(supplied)) if supplied else str(uuid.uuid4())
    except ValueError:
        value = str(uuid.uuid4())
    request.state.correlation_id = value
    return value


def _as_utc(value) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class CustomerAuthorizer:
    def __init__(self, verifier: IdentityVerifier):
        self._verifier = verifier

    def verify_identity(self, request: Request) -> VerifiedIdentity:
        token = _bearer_token(request)
        identity = self._verifier.verify(token) if token else None
        if identity is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return identity

    def start_session(self, request: Request) -> VerifiedIdentity:
        identity = self.verify_identity(request)
        conn = self._connection(request)
        try:
            user = conn.execute(
                "SELECT status FROM customer_users WHERE user_id = ?", (identity.user_id,)
            ).fetchone()
            if user is None or user["status"] != "active":
                raise HTTPException(status_code=403, detail="Access denied")
            conn.execute(
                """
                INSERT INTO customer_sessions
                    (session_id, user_id, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (session_id) DO UPDATE SET
                    expires_at = excluded.expires_at,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    identity.session_id,
                    identity.user_id,
                    identity.expires_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            return identity
        finally:
            conn.close()

    def revoke_session(self, request: Request) -> VerifiedIdentity:
        identity = self.verify_identity(request)
        conn = self._connection(request)
        try:
            conn.execute(
                """
                UPDATE customer_sessions SET revoked_at = ?
                WHERE session_id = ? AND user_id = ?
                """,
                (datetime.now(timezone.utc).isoformat(), identity.session_id, identity.user_id),
            )
            conn.commit()
            return identity
        finally:
            conn.close()

    def authorize(self, request: Request, tenant_id: str, minimum_role: str) -> CustomerContext:
        correlation_id = _correlation_id(request)
        identity = self.verify_identity(request)
        conn = self._connection(request)
        try:
            session = conn.execute(
                """
                SELECT user_id, expires_at, revoked_at
                FROM customer_sessions WHERE session_id = ?
                """,
                (identity.session_id,),
            ).fetchone()
            if (
                session is None
                or session["user_id"] != identity.user_id
                or session["revoked_at"] is not None
                or _as_utc(session["expires_at"]) <= datetime.now(timezone.utc)
            ):
                self._audit_event(
                    request,
                    correlation_id=correlation_id,
                    user_id=identity.user_id,
                    session_id=identity.session_id,
                    tenant_id=tenant_id,
                    action="authorization.check",
                    resource_type="tenant",
                    outcome="denied",
                    reason_code="invalid_session",
                )
                raise HTTPException(status_code=401, detail="Authentication required")

            membership = conn.execute(
                """
                SELECT m.role
                FROM tenant_memberships AS m
                JOIN customer_users AS u ON u.user_id = m.user_id
                WHERE m.tenant_id = ? AND m.user_id = ?
                  AND m.status = 'active' AND u.status = 'active'
                """,
                (tenant_id, identity.user_id),
            ).fetchone()
            if membership is None or ROLE_RANK[membership["role"]] < ROLE_RANK[minimum_role]:
                self._audit_event(
                    request,
                    correlation_id=correlation_id,
                    user_id=identity.user_id,
                    session_id=identity.session_id,
                    tenant_id=tenant_id,
                    action="authorization.check",
                    resource_type="tenant",
                    outcome="denied",
                    reason_code="insufficient_membership",
                )
                raise HTTPException(status_code=403, detail="Access denied")

            conn.execute(
                "UPDATE customer_sessions SET last_seen_at = ? WHERE session_id = ?",
                (datetime.now(timezone.utc).isoformat(), identity.session_id),
            )
            conn.commit()
            return CustomerContext(
                user_id=identity.user_id,
                session_id=identity.session_id,
                tenant_id=tenant_id,
                role=membership["role"],
                correlation_id=correlation_id,
            )
        finally:
            conn.close()

    def audit(
        self,
        request: Request,
        context: CustomerContext,
        *,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        outcome: str = "allowed",
        reason_code: Optional[str] = None,
    ) -> None:
        self._audit_event(
            request,
            correlation_id=context.correlation_id,
            user_id=context.user_id,
            session_id=context.session_id,
            tenant_id=context.tenant_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            reason_code=reason_code,
        )

    def _audit_event(
        self,
        request: Request,
        *,
        correlation_id: str,
        user_id: str,
        session_id: str,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        outcome: str,
        reason_code: Optional[str] = None,
    ) -> None:
        conn = self._connection(request)
        try:
            conn.execute(
                """
                INSERT INTO customer_audit_events (
                    audit_id, correlation_id, user_id, session_id, tenant_id,
                    action, resource_type, resource_id, outcome, reason_code,
                    request_method, request_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), correlation_id, user_id,
                    session_id, tenant_id, action, resource_type,
                    resource_id, outcome, reason_code, request.method, request.url.path,
                ),
            )
            conn.commit()
        except DB_ERRORS as exc:
            logger.error("customer_audit_failed error_type=%s", type(exc).__name__)
        finally:
            conn.close()

    @staticmethod
    def _connection(request: Request):
        try:
            return get_connection(request.app.state.db_path)
        except DB_ERRORS as exc:
            logger.error("customer_auth_db_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Authentication temporarily unavailable") from exc
