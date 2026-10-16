"""GHL messaging protocol for Leo: send_sms and send_email methods.

Same pattern as workers/angel/ghl.py -- an explicit Protocol interface,
a safe Null default, and a real client that requires credentials and fails
loudly without them.
"""

from __future__ import annotations

from typing import Protocol


class GHLMessagingClient(Protocol):
    """Protocol for GHL messaging operations (SMS and email). Used by Leo
    for first-touch outreach. Separates interface from implementation."""

    def send_sms(self, contact_id: str, message: str) -> dict: ...

    def send_email(self, contact_id: str, subject: str, body: str) -> dict: ...
