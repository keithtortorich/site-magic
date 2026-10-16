"""Voice/chat backend abstraction for Angel.

Kept as an explicit interface so Angel's logic never depends on a specific
vendor. GrokVoiceBackend requires a real API key via environment variable
and raises a clear, descriptive error if not configured -- it never
silently no-ops or fabricates a response on a *configuration* problem.
NullVoiceBackend is the safe default for tests and offline/text-only
operation.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

import httpx

logger = logging.getLogger("webstaffr.angel.voice")


class VoiceBackendNotConfiguredError(RuntimeError):
    """Raised when a voice backend is used without its required credentials."""


class VoiceBackend(Protocol):
    def respond(self, message: str, context: dict) -> str:
        """Given an incoming message and context, return Angel's reply text."""
        ...


class NullVoiceBackend:
    """Safe default: deterministic, no external calls. Used for tests and
    for any tenant that hasn't configured a real voice backend yet."""

    def respond(self, message: str, context: dict) -> str:
        return (
            "Thanks for reaching out! I'm not fully set up to respond yet -- "
            "a real person will follow up with you shortly."
        )


_FALLBACK_REPLY = (
    "I'm having a bit of trouble connecting right now. "
    "A real team member will get back to you very soon."
)


class GrokVoiceBackend:
    """Text chat via xAI's Grok API (the standard synchronous chat-
    completions endpoint -- NOT the realtime audio/WebSocket API).

    A synchronous request/response chat completion is enough to satisfy
    this class's `respond(message, context) -> str` contract; live
    realtime audio streaming remains separate future work if/when Angel
    needs actual voice rather than text chat.

    Model name and endpoint verified against xAI's live docs
    (docs.x.ai, checked 2026-07-08): "grok-beta" was retired as of
    xAI's May 15, 2026 model deprecation and now silently auto-redirects
    to grok-4.3 at standard grok-4.3 pricing. Updated to request
    "grok-4.3" explicitly rather than relying on that redirect. The
    `/v1/chat/completions` endpoint itself is still live but is now
    documented by xAI as a "legacy" surface -- new features land on
    their Responses API (`/v1/responses`) first. Kept on chat/completions
    here since it satisfies this class's stateless request/response
    contract and migrating to Responses is a separate, larger change.
    Still [Unverified] against a live GROK_API_KEY -- confirmed against
    current docs, not yet exercised against a real account.
    """

    API_URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("GROK_API_KEY")
        if not self.api_key:
            raise VoiceBackendNotConfiguredError(
                "GrokVoiceBackend requires GROK_API_KEY to be set (env var or constructor arg). "
                "Refusing to start with no credentials rather than failing later, silently."
            )
        self.client = httpx.Client(timeout=30.0)

    def respond(self, message: str, context: dict) -> str:
        """Call the xAI chat-completions endpoint using the rendered Angel
        system prompt already attached to context by Angel.respond().

        Network/API failures and unexpected response shapes both degrade
        to a fixed fallback reply rather than raising into the caller --
        callers should never see a raw exception from a flaky vendor API.
        But the two failure modes are caught and logged separately rather
        than through one blanket `except Exception`: a genuine bug (e.g.
        xAI changing its response shape) is distinguishable in logs from
        an ordinary transient network outage, instead of both looking
        identical from the caller's perspective."""
        system_prompt = context.get("system_prompt") or "You are Angel, a helpful receptionist."
        try:
            response = self.client.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "grok-4.3",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except httpx.HTTPError as exc:
            logger.warning("grok_api_call_failed error_type=%s", type(exc).__name__)
            return _FALLBACK_REPLY
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning("grok_api_response_unparseable error_type=%s", type(exc).__name__)
            return _FALLBACK_REPLY

    def __del__(self) -> None:
        if hasattr(self, "client"):
            self.client.close()
