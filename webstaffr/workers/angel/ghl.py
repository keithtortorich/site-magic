"""GoHighLevel (GHL) integration for Angel: syncing notes and appointments.

Same pattern as voice.py -- an explicit interface, a safe Null default, and
a real client that requires credentials and fails loudly without them.
Uses stdlib urllib only, to avoid adding `requests` as another dependency
for what is currently a small, infrequent call surface.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional, Protocol


class GHLNotConfiguredError(RuntimeError):
    """Raised when the GHL client is used without required credentials."""


class GHLSyncError(RuntimeError):
    """Raised when a GHL API call fails."""


class GHLClient(Protocol):
    def upsert_contact(
        self, name: str, phone: Optional[str], email: Optional[str], source: str
    ) -> dict: ...
    def log_note(self, contact_id: str, note: str) -> None: ...
    def create_appointment(self, contact_id: str, starts_at: str, notes: str) -> dict: ...
    def update_appointment(self, appointment_id: str, starts_at: str, notes: str) -> dict: ...
    def cancel_appointment(self, appointment_id: str) -> dict: ...
    def send_sms(self, contact_id: str, message: str) -> dict: ...
    def send_email(self, contact_id: str, subject: str, body: str) -> dict: ...


class NullGHLClient:
    """Safe default: records calls in memory, makes no network requests.
    Used for tests and for any tenant that hasn't configured GHL yet."""

    def __init__(self) -> None:
        self.logged_notes: list = []
        self.created_appointments: list = []
        self.updated_appointments: list = []
        self.cancelled_appointments: list = []
        self.sent_sms: list = []
        self.sent_emails: list = []
        self.upserted_contacts: list = []

    def upsert_contact(
        self, name: str, phone: Optional[str], email: Optional[str], source: str
    ) -> dict:
        contact_id = f"null-contact-{len(self.upserted_contacts) + 1}"
        record = {
            "name": name,
            "phone": phone,
            "email": email,
            "source": source,
            "contact": {"id": contact_id},
        }
        self.upserted_contacts.append(record)
        return {"new": True, "contact": {"id": contact_id}}

    def log_note(self, contact_id: str, note: str) -> None:
        self.logged_notes.append({"contact_id": contact_id, "note": note})

    def create_appointment(self, contact_id: str, starts_at: str, notes: str) -> dict:
        record = {"contact_id": contact_id, "starts_at": starts_at, "notes": notes, "ghl_id": None}
        self.created_appointments.append(record)
        return record

    def update_appointment(self, appointment_id: str, starts_at: str, notes: str) -> dict:
        record = {
            "appointment_id": appointment_id,
            "starts_at": starts_at,
            "notes": notes,
            "action": "updated",
        }
        self.updated_appointments.append(record)
        return record

    def cancel_appointment(self, appointment_id: str) -> dict:
        record = {"appointment_id": appointment_id, "action": "cancelled"}
        self.cancelled_appointments.append(record)
        return record

    def send_sms(self, contact_id: str, message: str) -> dict:
        record = {"contact_id": contact_id, "message": message}
        self.sent_sms.append(record)
        return {"status": "sent"}

    def send_email(self, contact_id: str, subject: str, body: str) -> dict:
        record = {"contact_id": contact_id, "subject": subject, "body": body}
        self.sent_emails.append(record)
        return {"status": "sent"}


class GoHighLevelClient:
    """Real GHL client. Requires GHL_API_KEY and GHL_LOCATION_ID. Fails
    loudly at construction if not configured -- never silently degrades
    to a no-op that looks like success."""

    BASE_URL = "https://services.leadconnectorhq.com"

    def __init__(self, api_key: Optional[str] = None, location_id: Optional[str] = None) -> None:
        self.api_key = api_key or os.environ.get("GHL_API_KEY")
        self.location_id = location_id or os.environ.get("GHL_LOCATION_ID")
        if not self.api_key or not self.location_id:
            raise GHLNotConfiguredError(
                "GoHighLevelClient requires GHL_API_KEY and GHL_LOCATION_ID "
                "(env vars or constructor args). Refusing to start with no credentials."
            )

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        url = f"{self.BASE_URL}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Version": "2021-07-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            raise GHLSyncError(f"GHL API error {exc.code} on {method} {path}: {exc.read()}") from exc
        except urllib.error.URLError as exc:
            raise GHLSyncError(f"GHL API unreachable for {method} {path}: {exc}") from exc

    def log_note(self, contact_id: str, note: str) -> None:
        self._request("POST", f"/contacts/{contact_id}/notes", {"body": note})

    def upsert_contact(
        self, name: str, phone: Optional[str], email: Optional[str], source: str
    ) -> dict:
        """Create or update a contact using HighLevel's documented upsert API."""
        payload = {
            "name": name,
            "locationId": self.location_id,
            "source": source,
            "createNewIfDuplicateAllowed": False,
        }
        if phone:
            payload["phone"] = phone
        if email:
            payload["email"] = email
        return self._request("POST", "/contacts/upsert", payload)

    def create_appointment(self, contact_id: str, starts_at: str, notes: str) -> dict:
        return self._request(
            "POST",
            "/calendars/events/appointments",
            {
                "locationId": self.location_id,
                "contactId": contact_id,
                "startTime": starts_at,
                "notes": notes,
            },
        )

    def update_appointment(self, appointment_id: str, starts_at: str, notes: str) -> dict:
        # Endpoint path confirmed against HighLevel's live API docs
        # (marketplace.gohighlevel.com/docs, checked 2026-07-08):
        # PUT /calendars/events/appointments/:eventId. Payload shape
        # (startTime/notes) is still [Unverified] against a live account --
        # the docs page doesn't render request-body fields in fetched text.
        return self._request(
            "PUT",
            f"/calendars/events/appointments/{appointment_id}",
            {
                "startTime": starts_at,
                "notes": notes,
            },
        )

    def cancel_appointment(self, appointment_id: str) -> dict:
        # Bug fix (2026-07-08): this previously called
        # DELETE /calendars/events/appointments/{id}, which does not
        # exist. HighLevel's live docs confirm the real endpoint is
        # DELETE /calendars/events/{eventId} -- no "/appointments"
        # segment, unlike create/update. Confirmed against docs;
        # still [Unverified] against a live account/response shape.
        return self._request("DELETE", f"/calendars/events/{appointment_id}")

    def send_sms(self, contact_id: str, message: str) -> dict:
        """Send SMS to contact via GHL's messaging API. Used by Leo for
        first-touch outreach to Tier 1-2 leads."""
        return self._request(
            "POST",
            f"/contacts/{contact_id}/send-sms",
            {"body": message},
        )

    def send_email(self, contact_id: str, subject: str, body: str) -> dict:
        """Send email to contact via GHL's messaging API. Used by Leo for
        first-touch outreach to Tier 3 leads."""
        return self._request(
            "POST",
            f"/contacts/{contact_id}/send-email",
            {
                "subject": subject,
                "body": body,
            },
        )
