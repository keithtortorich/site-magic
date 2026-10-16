"""Sam's GHL integration: sending quotes via email and logging quote details in contact notes.

Wraps the existing GHLClient from workers/angel/ghl.py.
Same error handling pattern: GHLSyncError propagates, NullGHLQuoteClient is the safe default.
"""

from __future__ import annotations

import os
from typing import Optional

from ..angel.ghl import GHLClient, GHLNotConfiguredError, GHLSyncError, NullGHLClient
from .protocol import GHLQuoteClient, NullGHLQuoteClient


class GoHighLevelQuoteClient:
    """Real GHL client wrapper for quote operations.

    Requires an existing GHLClient instance (passed in or created from env vars).
    Adds quote-specific methods (send_quote_email, log_quote_note) on top of
    the existing appointment/note APIs.
    """

    def __init__(self, ghl_client: Optional[GHLClient] = None) -> None:
        """Initialize with an existing GHL client or create from env vars.

        Args:
            ghl_client: Optional pre-configured GHLClient. If None, creates
                        GoHighLevelClient from GHL_API_KEY and GHL_LOCATION_ID env vars.
                        Fails loudly if env vars are missing.

        Raises:
            GHLNotConfiguredError if no client is provided and env vars are missing
        """
        if ghl_client:
            self.ghl = ghl_client
        else:
            from ..angel.ghl import GoHighLevelClient
            self.ghl = GoHighLevelClient()  # Fails loudly if env vars missing

    def send_quote_email(self, contact_id: str, quote_id: str, email_body: str, subject: str) -> dict:
        """Send a quote email to a contact via GHL.

        Args:
            contact_id: GHL contact ID
            quote_id: Sam's quote ID (for logging)
            email_body: HTML email body with estimate range and caveat
            subject: Email subject line (e.g. "Your Estimate from Acme HVAC")

        Returns:
            dict with keys: contact_id, quote_id, subject, email_id (GHL email ID),
            status ('sent' or 'pending')

        Raises:
            GHLSyncError if the API call fails
        """
        # GHL's email send endpoint (confirmed against live docs)
        # Uses the contact's primary email address.
        try:
            result = self.ghl._request(
                "POST",
                f"/contacts/{contact_id}/email",
                {
                    "subject": subject,
                    "body": email_body,
                },
            )
            # GHL returns { id: "email_id", status: "sent", ... }
            email_id = result.get("id", f"ghl_{quote_id}")
            return {
                "contact_id": contact_id,
                "quote_id": quote_id,
                "subject": subject,
                "email_id": email_id,
                "status": "sent",
            }
        except GHLSyncError:
            raise
        except Exception as exc:
            raise GHLSyncError(f"Failed to send quote email to {contact_id}: {exc}") from exc

    def log_quote_note(self, contact_id: str, quote_id: str, estimate_range: tuple[float, float]) -> None:
        """Log quote details in a GHL contact note for sales team visibility.

        Args:
            contact_id: GHL contact ID
            quote_id: Sam's quote ID
            estimate_range: (low, high) tuple for the estimate

        Raises:
            GHLSyncError if the note creation fails
        """
        low, high = estimate_range
        note = f"Quote {quote_id}: Estimated range ${low:,.0f} - ${high:,.0f}"

        try:
            self.ghl.log_note(contact_id, note)
        except GHLSyncError:
            raise
        except Exception as exc:
            raise GHLSyncError(f"Failed to log quote note for {contact_id}: {exc}") from exc


def ghl_quote_client_from_env() -> Optional[GHLQuoteClient]:
    """Create a GHL quote client from environment variables.

    Returns:
        GoHighLevelQuoteClient if GHL_API_KEY and GHL_LOCATION_ID are set,
        None otherwise (so create_sam_router() can fall back to NullGHLQuoteClient).

    Never silently constructs a client that will fail on first use -- that's why
    this returns None and lets the router handle the fallback, same pattern as
    _ghl_client_from_env() in app.py.
    """
    if os.environ.get("GHL_API_KEY") and os.environ.get("GHL_LOCATION_ID"):
        from ..angel.ghl import GoHighLevelClient
        ghl = GoHighLevelClient()
        return GoHighLevelQuoteClient(ghl_client=ghl)
    return None
