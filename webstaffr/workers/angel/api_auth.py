"""Shared-secret authentication for the two server-to-server endpoints that
have no browser caller and are therefore not in ScopedCORSMiddleware's
CORS-scoped set: /book and /webhooks/ghl. Both previously accepted
`tenant_id` -- a public value, returned in API responses and embedded in
generated-site page source -- as if it were a credential, with no auth of
any kind; this module closes that gap.

Environment-driven verifiers fail closed when their credential is absent.
Tests that need a permissive boundary must inject NullSharedSecretVerifier
explicitly through create_app(); production construction never selects it.

This is a minimal shared-secret header, not a full auth system -- no
sessions, no per-caller identity, no token expiry/rotation. That's a
deliberate choice ("even a minimal shared-secret/API-key header" beats
none) rather than building a larger auth system, which is out of MVP
scope per CLAUDE.md.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional, Protocol


class SharedSecretVerifier(Protocol):
    def verify(self, provided: Optional[str], raw_body: Optional[bytes] = None) -> bool: ...


class NullSharedSecretVerifier:
    """Explicit test double. Never selected by an environment factory."""

    def verify(self, provided: Optional[str], raw_body: Optional[bytes] = None) -> bool:
        return True


class DenyAllSharedSecretVerifier:
    """Safe unconfigured production default."""

    def verify(self, provided: Optional[str], raw_body: Optional[bytes] = None) -> bool:
        return False


class StaticSecretVerifier:
    """Constant-time comparison against a configured secret. Fails closed:
    a missing or mismatched header returns False rather than raising, so a
    caller can always treat "not verify()" as "reject the request" without
    a second exception-handling path -- same contract as
    RetellSignatureVerifier.verify().

    raw_body accepted (and ignored) for interface parity with verifiers
    that need it (e.g. StripeSignatureVerifier) -- callers that inject a
    static secret in place of a body-aware verifier still work unchanged."""

    def __init__(self, secret: str) -> None:
        if not secret:
            raise ValueError("StaticSecretVerifier requires a non-empty secret.")
        self._secret = secret

    def verify(self, provided: Optional[str], raw_body: Optional[bytes] = None) -> bool:
        if not provided:
            return False
        return hmac.compare_digest(self._secret, provided)


def ghl_webhook_verifier_from_env() -> SharedSecretVerifier:
    """GHL_WEBHOOK_SECRET set -> real verification against the
    X-Webhook-Secret header. Unset denies access. Configure this as a
    custom header on GoHighLevel's workflow Webhook action. GHL does not
    sign outgoing webhooks itself, so a shared secret set on both sides is
    the mechanism, not HMAC over the body."""
    secret = os.environ.get("GHL_WEBHOOK_SECRET")
    if secret:
        return StaticSecretVerifier(secret)
    return DenyAllSharedSecretVerifier()


def book_api_verifier_from_env() -> SharedSecretVerifier:
    """BOOK_API_KEY set -> real verification against the X-API-Key header.
    Unset denies access. /book has no browser caller today; this is for a
    future booking UI or server-side integration."""
    secret = os.environ.get("BOOK_API_KEY")
    if secret:
        return StaticSecretVerifier(secret)
    return DenyAllSharedSecretVerifier()


def internal_api_verifier_from_env() -> SharedSecretVerifier:
    """Protect Sam, Rita, and Leo internal service routes.

    INTERNAL_API_KEY is intentionally separate from provider webhook secrets.
    Missing configuration denies every request.
    """
    secret = os.environ.get("INTERNAL_API_KEY")
    if secret:
        return StaticSecretVerifier(secret)
    return DenyAllSharedSecretVerifier()
