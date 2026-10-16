"""Angel -- the first AI Worker. Ties together the core prompt, a pluggable
voice/chat backend, appointment booking, and GHL logging.

Dependencies (voice backend, GHL client, DB connection) are injected via
the constructor rather than constructed internally, so tests can supply
Null implementations without needing real credentials or a real database
file. This is the same explicit-dependency pattern as WorkflowExecutor.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from ...tenant import Tenant
from .booking import Appointment, AppointmentRepository, _normalize_starts_at
from .ghl import GHLClient, NullGHLClient
from .voice import NullVoiceBackend, VoiceBackend

logger = logging.getLogger("webstaffr.angel")

_PROMPT_PATH = Path(__file__).parent / "angel_prompt.md"


def load_prompt_template() -> str:
    """Loads whatever is currently in angel_prompt.md (the founder's real
    core prompt). Swapping that file's content requires no code change
    here."""
    return _PROMPT_PATH.read_text()


class Angel:
    """One Angel instance handles conversation and booking for one tenant."""

    def __init__(
        self,
        tenant: Tenant,
        conn: Any,
        voice_backend: Optional[VoiceBackend] = None,
        ghl_client: Optional[GHLClient] = None,
        business_name: str = "your business",
        ghl_max_attempts: int = 3,
    ) -> None:
        if ghl_max_attempts < 1:
            raise ValueError("ghl_max_attempts must be >= 1.")
        self.tenant = tenant
        self.conn = conn
        self.voice_backend = voice_backend or NullVoiceBackend()
        self.ghl_client = ghl_client or NullGHLClient()
        self.business_name = business_name
        self.ghl_max_attempts = ghl_max_attempts
        self._appointments = AppointmentRepository(conn)

    def _call_ghl_with_retry(self, fn, *, description: str):
        """Calls `fn()` with up to `self.ghl_max_attempts` attempts on any
        exception -- same bounded-retry shape as WorkflowExecutor._run_step
        (repeated attempts, no sleep/backoff between them). No delay is
        deliberate: this runs inline within a live conversation turn or an
        HTTP request, where a real backoff delay would stall the caller;
        bounding the *attempt count* is what buys resilience against a
        transient blip without also making failures slow. Re-raises the
        last exception if every attempt fails, leaving the caller's
        existing try/except to decide how to degrade -- this only adds
        retry, it doesn't change the failure contract."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.ghl_max_attempts + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 -- retried broadly, same as WorkflowExecutor
                last_exc = exc
                logger.warning(
                    "ghl_call_attempt_failed tenant=%s description=%s attempt=%d/%d error=%s",
                    self.tenant.tenant_id,
                    description,
                    attempt,
                    self.ghl_max_attempts,
                    exc,
                )
        raise last_exc

    def build_context(self, extra: Optional[dict] = None) -> dict:
        """Dynamic context loading: assembles what Angel knows for this
        turn. Minimal for now (tenant + business name + whatever the
        caller passes in) -- this is the seam where richer per-tenant
        context (past appointments, CRM notes) plugs in later without
        changing the interface."""
        context = {
            "tenant_id": self.tenant.tenant_id,
            "business_name": self.business_name,
        }
        if extra:
            context.update(extra)
        return context

    def render_prompt(self, context: dict) -> str:
        """Combines the static core prompt (angel_prompt.md, verbatim) with
        this session's dynamic context, per the prompt's own closing
        instruction: "At the start of every session, you will receive
        dynamic context... Use it to personalize every response."

        The real prompt has no string-template placeholders to fill in --
        it's a fixed system prompt. Dynamic context is appended as a
        clearly separate, structured block rather than interpolated into
        the prompt text, so the core prompt can be swapped without ever
        needing to match a particular template shape."""
        template = load_prompt_template()
        if not context:
            return template
        context_lines = "\n".join(f"- {key}: {value}" for key, value in context.items())
        return f"{template}\n\nDynamic context for this session:\n{context_lines}"

    def respond(self, message: str, extra_context: Optional[dict] = None) -> str:
        """Handle one incoming message and return Angel's reply text."""
        context = self.build_context(extra_context)
        context["system_prompt"] = self.render_prompt(context)
        logger.info("angel_message_received tenant=%s", self.tenant.tenant_id)
        reply = self.voice_backend.respond(message, context)
        logger.info("angel_message_answered tenant=%s", self.tenant.tenant_id)
        return reply

    def book_appointment(
        self,
        contact_name: str,
        starts_at: str,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        notes: Optional[str] = None,
        sync_to_ghl: bool = True,
        ghl_contact_id: Optional[str] = None,
    ) -> Appointment:
        """Books an appointment locally first -- that's the source of
        truth. GHL sync is best-effort and never rolls back the local
        booking if it fails; a failed sync is logged, not swallowed.
        `starts_at` is normalized through `_normalize_starts_at` so
        common spoken/relative times from voice callers still resolve
        to a valid ISO-8601 value instead of being recorded verbatim.
        """
        appt = Appointment(
            tenant_id=self.tenant.tenant_id,
            contact_name=contact_name,
            starts_at=starts_at,
            contact_phone=contact_phone,
            contact_email=contact_email,
            notes=notes,
        )
        appt.starts_at = _normalize_starts_at(appt.starts_at)
        self._appointments.save(appt)
        logger.info(
            "appointment_booked tenant=%s appointment_id=%s",
            self.tenant.tenant_id,
            appt.appointment_id,
        )

        if sync_to_ghl and ghl_contact_id:
            try:
                self._call_ghl_with_retry(
                    lambda: self.ghl_client.create_appointment(ghl_contact_id, appt.starts_at, notes or ""),
                    description="create_appointment",
                )
                self._appointments.mark_ghl_synced(self.tenant.tenant_id, appt.appointment_id)
                appt.ghl_synced = True
            except Exception as exc:  # noqa: BLE001 -- GHL failure must not break booking
                logger.warning(
                    "ghl_sync_failed tenant=%s appointment_id=%s attempts=%d error=%s",
                    self.tenant.tenant_id,
                    appt.appointment_id,
                    self.ghl_max_attempts,
                    exc,
                )

        return appt

    def log_note_to_ghl(self, ghl_contact_id: str, note: str) -> bool:
        """Best-effort GHL note logging. Returns True/False instead of
        raising -- a note-logging failure is never allowed to break the
        conversation flow that triggered it."""
        try:
            self._call_ghl_with_retry(
                lambda: self.ghl_client.log_note(ghl_contact_id, note),
                description="log_note",
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "ghl_note_log_failed tenant=%s attempts=%d error=%s",
                self.tenant.tenant_id,
                self.ghl_max_attempts,
                exc,
            )
            return False
