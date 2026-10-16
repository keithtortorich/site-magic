"""Tenant-scoped persistence for public customer-site service requests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WebsiteLead:
    lead_id: str
    tenant_id: str
    name: str
    phone: Optional[str]
    email: Optional[str]
    message: str
    service: Optional[str]
    source_path: Optional[str]


class WebsiteLeadRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def save(self, lead: WebsiteLead) -> None:
        self._conn.execute(
            """
            INSERT INTO website_leads (
                lead_id, tenant_id, name, phone, email, message, service,
                source_path, status, forward_attempts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'received', 0)
            """,
            (
                lead.lead_id,
                lead.tenant_id,
                lead.name,
                lead.phone,
                lead.email,
                lead.message,
                lead.service,
                lead.source_path,
            ),
        )

    def mark_forwarded(self, tenant_id: str, lead_id: str, ghl_contact_id: str) -> None:
        self._conn.execute(
            """
            UPDATE website_leads
            SET status = 'forwarded', ghl_contact_id = ?,
                forward_attempts = forward_attempts + 1,
                last_forward_error_code = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = ? AND lead_id = ?
            """,
            (ghl_contact_id, tenant_id, lead_id),
        )

    def mark_forward_failed(
        self,
        tenant_id: str,
        lead_id: str,
        error_code: str,
        ghl_contact_id: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE website_leads
            SET status = 'forward_failed',
                forward_attempts = forward_attempts + 1,
                last_forward_error_code = ?,
                ghl_contact_id = COALESCE(?, ghl_contact_id),
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = ? AND lead_id = ?
            """,
            (error_code, ghl_contact_id, tenant_id, lead_id),
        )
