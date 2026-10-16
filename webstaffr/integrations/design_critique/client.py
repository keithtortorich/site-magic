"""Design-critique client: an on-demand, human-invoked design/UI review
pass over one rendered tenant site page, backed by OpenRouter.

This is deliberately NOT part of site_renderer.py's render path. Every
render is free (webstaffr/site_a11y_check.py's mechanical WCAG checks run
on every render at zero cost). Design *taste* -- does this look premium,
is the motion right, is this palette working -- needs a model's judgment,
which means a real API call with real per-call cost. That cost is
incurred only when this client is explicitly invoked (a founder session,
a future Cowork skill loop), never automatically per render. See
docs/DECISIONS.md for the ADR recording this split.

Same Protocol + Null* + real-implementation shape as every other
integration in this repo (webstaffr/workers/angel/voice.py's
VoiceBackend/GrokVoiceBackend is the canonical example). OpenRouter is a
single HTTPS call -- no persistent process, no self-hosted inference --
which is why it's the integration used here rather than a self-hosted
model (Ollama, NVIDIA NIM): this app runs as stateless Vercel serverless
functions with no warm process to keep a local model loaded in, and
adding one would mean standing up infrastructure this product has
deliberately avoided everywhere else (Supabase for DB, Vercel for
compute, nothing self-managed).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol

import httpx

logger = logging.getLogger("webstaffr.integrations.design_critique")

# Default model: cheapest capable tier on OpenRouter, per founder
# direction (2026-08-01) -- this is invoked on demand, not per render, so
# raw speed matters less than cost per call staying near-zero. Override
# via DESIGN_CRITIQUE_MODEL without a code change if OpenRouter's pricing
# or model lineup shifts.
_DEFAULT_MODEL = "meta-llama/llama-3.1-8b-instruct"

_SYSTEM_PROMPT = (
    "You are a senior design reviewer critiquing a rendered small-business "
    "website page. You are given raw HTML. Give specific, actionable "
    "feedback on visual hierarchy, layout, spacing, typography, and overall "
    "polish -- the kind of feedback that helps a human decide what to "
    "change before this page ships to a real customer. Do not comment on "
    "accessibility (contrast, alt text, form labels) -- that's already "
    "checked separately by a mechanical, deterministic tool. Do not invent "
    "facts about the business. Keep feedback to concrete, prioritized "
    "points, not generic praise."
)


class DesignCritiqueNotConfiguredError(RuntimeError):
    """Raised when the client is instantiated without required env vars."""


class DesignCritiqueError(RuntimeError):
    """Raised when a design-critique call fails or returns an unusable response."""


class DesignCritiqueClient(Protocol):
    def critique(self, html: str, *, page_label: str = "page") -> str:
        """Given one rendered page's HTML, return free-text design
        feedback. Raises DesignCritiqueError on failure -- this is a
        human-invoked, synchronous call; the caller is waiting on the
        result and needs to know if it didn't work, unlike Angel's
        voice backend which must always degrade gracefully mid-conversation."""
        ...


class NullDesignCritiqueClient:
    """Safe default: deterministic, no external calls, no cost. Used for
    tests and whenever OPENROUTER_API_KEY isn't configured."""

    def critique(self, html: str, *, page_label: str = "page") -> str:
        return (
            f"Design critique is not configured for this environment "
            f"(no OPENROUTER_API_KEY set) -- no review was performed for {page_label!r}."
        )


class OpenRouterDesignCritiqueClient:
    """Real design-critique client via OpenRouter's OpenAI-compatible
    chat-completions endpoint.

    Env vars:
      OPENROUTER_API_KEY     required
      DESIGN_CRITIQUE_MODEL  optional, defaults to a cheap capable model
    """

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise DesignCritiqueNotConfiguredError(
                "OpenRouterDesignCritiqueClient requires OPENROUTER_API_KEY to be set "
                "(env var or constructor arg). Refusing to start with no credentials "
                "rather than failing later, silently."
            )
        self.model = model or os.environ.get("DESIGN_CRITIQUE_MODEL", _DEFAULT_MODEL)
        self.client = httpx.Client(timeout=60.0)

    def critique(self, html: str, *, page_label: str = "page") -> str:
        """Sends the page's HTML to OpenRouter for review. Raises
        DesignCritiqueError on any failure -- deliberately does NOT
        degrade to a fallback string the way Angel's voice backend does,
        because this is a synchronous, human-invoked call: a founder
        session waiting on a design review needs to know the call failed,
        not receive a silently-wrong placeholder response."""
        try:
            response = self.client.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    # OpenRouter asks for these to attribute usage; both
                    # optional but cost nothing to include correctly.
                    "HTTP-Referer": "https://webstaffr.com",
                    "X-Title": "WebStaffr Design Critique",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Page: {page_label}\n\nHTML:\n{html}",
                        },
                    ],
                    "temperature": 0.4,
                    "max_tokens": 800,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "design_critique_call_failed model=%s error_type=%s",
                self.model,
                type(exc).__name__,
            )
            raise DesignCritiqueError(f"OpenRouter call failed: {exc}") from exc

        try:
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, ValueError) as exc:
            logger.warning(
                "design_critique_response_unparseable model=%s error_type=%s",
                self.model,
                type(exc).__name__,
            )
            raise DesignCritiqueError(f"OpenRouter response unparseable: {exc}") from exc

    def __del__(self) -> None:
        if hasattr(self, "client"):
            self.client.close()
