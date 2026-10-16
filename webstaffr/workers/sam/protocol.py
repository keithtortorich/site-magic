"""Sam's service protocols: GHL quote operations, pricing accessor, objection handler.

Same pattern as Angel's protocols (voice.py, ghl.py) -- an explicit interface,
a safe Null default for tests/unconfigured environments, and a real implementation
that fails loudly if credentials are missing.
"""

from __future__ import annotations

from typing import Protocol


class GHLQuoteClient(Protocol):
    """Send quotes via GHL email and update contact with quote metadata."""

    def send_quote_email(self, contact_id: str, quote_id: str, email_body: str, subject: str) -> dict:
        """Send quote email to a contact via GHL.

        Args:
            contact_id: GHL contact ID
            quote_id: Sam's quote ID (for tracking in notes)
            email_body: HTML email body
            subject: Email subject line

        Returns:
            dict with email_id, status, timestamp

        Raises:
            GHLSyncError if GHL API fails
        """
        ...

    def log_quote_note(self, contact_id: str, quote_id: str, estimate_range: tuple[float, float]) -> None:
        """Log quote details in a GHL contact note for sales tracking.

        Args:
            contact_id: GHL contact ID
            quote_id: Sam's quote ID
            estimate_range: (low, high) tuple for the estimate
        """
        ...


class TradePresetAccessor(Protocol):
    """Retrieve per-trade pricing ranges and service info."""

    def get_pricing_range(self, industry: str, service: str) -> tuple[float, float]:
        """Get the low/high pricing range for a service in a trade.

        Args:
            industry: Normalized industry key (e.g. 'HVAC', 'Plumber')
            service: Service name (e.g. 'AC Repair', 'Leak Detection')

        Returns:
            (low, high) tuple in dollars

        Raises:
            ValueError if industry or service not found
        """
        ...

    def get_services_for_industry(self, industry: str) -> list[str]:
        """Get the list of services for an industry."""
        ...


class ObjectionHandler(Protocol):
    """Retrieve and render objection response templates."""

    def get_response(self, objection_type: str, industry: str, context: dict) -> str:
        """Get a professional response to an objection.

        Args:
            objection_type: Objection key (e.g. 'cost', 'timeline', 'warranty')
            industry: Normalized industry key
            context: Additional context (business_name, services_mentioned, etc.)

        Returns:
            Professional response text (not salesy, educational tone)
        """
        ...

    def get_objection_types(self, industry: str) -> list[str]:
        """Get the list of known objection types for an industry."""
        ...


class NullGHLQuoteClient:
    """Safe default for tests and unconfigured environments."""

    def __init__(self) -> None:
        self.sent_emails: list = []
        self.logged_notes: list = []

    def send_quote_email(self, contact_id: str, quote_id: str, email_body: str, subject: str) -> dict:
        record = {
            "contact_id": contact_id,
            "quote_id": quote_id,
            "subject": subject,
            "email_id": f"null_{quote_id}",
            "status": "captured_locally",
        }
        self.sent_emails.append(record)
        return record

    def log_quote_note(self, contact_id: str, quote_id: str, estimate_range: tuple[float, float]) -> None:
        self.logged_notes.append({
            "contact_id": contact_id,
            "quote_id": quote_id,
            "estimate_range": estimate_range,
        })


class NullTradePresetAccessor:
    """Safe default: all ranges return the baseline fallback."""

    def get_pricing_range(self, industry: str, service: str) -> tuple[float, float]:
        # Fallback for unconfigured/unknown trades: very wide range, forces "Contact for quote"
        return (0.0, 0.0)

    def get_services_for_industry(self, industry: str) -> list[str]:
        return []


class NullObjectionHandler:
    """Safe default: generic, safe responses."""

    _DEFAULT_RESPONSE = (
        "That's an important concern. Our team will discuss this thoroughly during the site visit. "
        "We're committed to finding the best solution for your specific situation."
    )

    def get_response(self, objection_type: str, industry: str, context: dict) -> str:
        return self._DEFAULT_RESPONSE

    def get_objection_types(self, industry: str) -> list[str]:
        return ["cost", "timeline", "warranty"]
