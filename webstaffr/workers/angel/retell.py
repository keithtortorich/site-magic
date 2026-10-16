"""Retell AI integration for Angel's voice/telephony layer.

Retell hosts the live phone call and the persistent realtime audio session
itself -- this app never holds a WebSocket open for the duration of a call.
That split was a deliberate decision, not a default: native Grok Voice Agent
API would have required this app to hold that connection itself, which is
incompatible with the current Vercel serverless deployment (see the
"voice vendor hosting constraint" memory note, 2026-07-08). Retell (and
Vapi) absorb that job into their own infrastructure; this app only ever
needs to answer short HTTP requests -- which is what retell_router.py does.

This module holds the one piece of real logic Retell integration needs
beyond thin webhook handling: verifying that a webhook actually came from
Retell before trusting its payload.

Implements Retell's documented ``X-Retell-Signature`` contract:
``v=<timestamp_ms>,d=<hmac_sha256>`` over the raw body plus timestamp,
with a five-minute freshness tolerance. Live staging verification remains
required before production activation.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from typing import Optional, Protocol


class RetellWebhookVerifier(Protocol):
    def verify(self, payload: bytes, signature_header: Optional[str]) -> bool: ...


class NullRetellWebhookVerifier:
    """Explicit test double. Never selected by verifier_from_env()."""

    def verify(self, payload: bytes, signature_header: Optional[str]) -> bool:
        return True


class DenyAllRetellWebhookVerifier:
    """Safe unconfigured production default."""

    def verify(self, payload: bytes, signature_header: Optional[str]) -> bool:
        return False


class RetellSignatureVerifier:
    """Verify Retell's documented ``v=<ms>,d=<hex>`` signature format."""

    MAX_SIGNATURE_AGE_SECONDS = 300

    def __init__(self, signing_secret: str) -> None:
        if not signing_secret:
            raise ValueError("RetellSignatureVerifier requires a non-empty signing secret.")
        self._secret = signing_secret.encode("utf-8")

    def verify(self, payload: bytes, signature_header: Optional[str]) -> bool:
        if not signature_header:
            return False
        match = re.fullmatch(r"v=(\d+),d=([0-9a-fA-F]{64})", signature_header.strip())
        if not match:
            return False
        timestamp_ms, candidate = match.groups()
        try:
            age = abs(time.time() - (int(timestamp_ms) / 1000))
        except ValueError:
            return False
        if age > self.MAX_SIGNATURE_AGE_SECONDS:
            return False
        expected = hmac.new(
            self._secret, payload + timestamp_ms.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, candidate.lower())


def verifier_from_env() -> RetellWebhookVerifier:
    """Return a real verifier when configured, otherwise deny all."""
    secret = os.environ.get("RETELL_WEBHOOK_SECRET")
    if secret:
        return RetellSignatureVerifier(secret)
    return DenyAllRetellWebhookVerifier()
