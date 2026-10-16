"""Quote persistence: create, read, update quote records in the database.

Same pattern as workers/angel/booking.py -- raw SQL via webstaffr/db.py,
all queries tenant-scoped. Uses uuid for quote IDs.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from sqlite3 import Connection
from typing import Optional

from ...db import DB_ERRORS, StorageError


@dataclass
class Quote:
    """Immutable quote record."""

    id: str
    tenant_id: str
    contact_id: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    service_scope: str
    industry: Optional[str]
    estimated_range_low: float
    estimated_range_high: float
    caveat: str
    status: str  # pending, sent, accepted, declined
    email_template: Optional[str]
    created_at: str
    sent_at: Optional[str]
    accepted_at: Optional[str]
    declined_at: Optional[str]
    declined_reason: Optional[str]
    appointment_id: Optional[int] = None


class QuoteRepository:
    """Quote persistence layer."""

    @staticmethod
    def create_quote(
        conn: Connection,
        tenant_id: str,
        contact_id: str,
        contact_name: Optional[str],
        contact_email: Optional[str],
        service_scope: str,
        industry: Optional[str],
        estimated_range_low: float,
        estimated_range_high: float,
        caveat: str,
        email_template: Optional[str] = None,
    ) -> Quote:
        """Create a new quote record.

        Args:
            conn: Database connection
            tenant_id: Tenant ID (scoped)
            contact_id: GHL contact ID
            contact_name: Contact name
            contact_email: Contact email
            service_scope: Free-text description of work
            industry: Normalized industry
            estimated_range_low: Low estimate
            estimated_range_high: High estimate
            caveat: Disclaimer text
            email_template: HTML email body (if sent)

        Returns:
            Quote object with generated ID

        Raises:
            StorageError on DB failure
        """
        quote_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO quotes (
                    id, tenant_id, contact_id, contact_name, contact_email,
                    service_scope, industry, estimated_range_low, estimated_range_high,
                    caveat, status, email_template, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote_id,
                    tenant_id,
                    contact_id,
                    contact_name,
                    contact_email,
                    service_scope,
                    industry,
                    estimated_range_low,
                    estimated_range_high,
                    caveat,
                    "pending",
                    email_template,
                    now,
                ),
            )
            conn.commit()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to create quote: {exc}") from exc

        return Quote(
            id=quote_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            contact_name=contact_name,
            contact_email=contact_email,
            service_scope=service_scope,
            industry=industry,
            estimated_range_low=estimated_range_low,
            estimated_range_high=estimated_range_high,
            caveat=caveat,
            status="pending",
            email_template=email_template,
            created_at=now,
            sent_at=None,
            accepted_at=None,
            declined_at=None,
            declined_reason=None,
        )

    @staticmethod
    def get_quote(conn: Connection, quote_id: str, tenant_id: str) -> Optional[Quote]:
        """Fetch a quote by ID (tenant-scoped).

        Args:
            conn: Database connection
            quote_id: Quote ID
            tenant_id: Tenant ID (for scoping)

        Returns:
            Quote object if found, None otherwise

        Raises:
            StorageError on DB failure
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tenant_id, contact_id, contact_name, contact_email,
                       service_scope, industry, estimated_range_low, estimated_range_high,
                       caveat, status, email_template, created_at, sent_at,
                       accepted_at, declined_at, declined_reason, appointment_id
                FROM quotes
                WHERE id = ? AND tenant_id = ?
                """,
                (quote_id, tenant_id),
            )
            row = cursor.fetchone()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to fetch quote: {exc}") from exc

        if not row:
            return None

        return Quote(
            id=row[0],
            tenant_id=row[1],
            contact_id=row[2],
            contact_name=row[3],
            contact_email=row[4],
            service_scope=row[5],
            industry=row[6],
            estimated_range_low=row[7],
            estimated_range_high=row[8],
            caveat=row[9],
            status=row[10],
            email_template=row[11],
            created_at=row[12],
            sent_at=row[13],
            accepted_at=row[14],
            declined_at=row[15],
            declined_reason=row[16],
            appointment_id=row[17],
        )

    @staticmethod
    def update_quote_sent(conn: Connection, quote_id: str, tenant_id: str, email_template: str) -> Quote:
        """Mark a quote as sent.

        Args:
            conn: Database connection
            quote_id: Quote ID
            tenant_id: Tenant ID (for scoping)
            email_template: HTML email body that was sent

        Returns:
            Updated Quote object

        Raises:
            StorageError on DB failure
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE quotes
                SET status = 'sent', sent_at = ?, email_template = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (now, email_template, quote_id, tenant_id),
            )
            conn.commit()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to update quote: {exc}") from exc

        # Fetch and return updated quote
        quote = QuoteRepository.get_quote(conn, quote_id, tenant_id)
        if not quote:
            raise StorageError(f"Quote {quote_id} not found after update")
        return quote

    @staticmethod
    def update_quote_accepted(
        conn: Connection, quote_id: str, tenant_id: str, appointment_id: int
    ) -> Quote:
        """Mark a quote as accepted and link to appointment.

        Args:
            conn: Database connection
            quote_id: Quote ID
            tenant_id: Tenant ID (for scoping)
            appointment_id: Appointment ID created from quote acceptance

        Returns:
            Updated Quote object

        Raises:
            StorageError on DB failure
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE quotes
                SET status = 'accepted', accepted_at = ?, appointment_id = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (now, appointment_id, quote_id, tenant_id),
            )
            conn.commit()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to accept quote: {exc}") from exc

        # Fetch and return updated quote
        quote = QuoteRepository.get_quote(conn, quote_id, tenant_id)
        if not quote:
            raise StorageError(f"Quote {quote_id} not found after update")
        return quote

    @staticmethod
    def update_quote_declined(
        conn: Connection, quote_id: str, tenant_id: str, reason: Optional[str] = None
    ) -> Quote:
        """Mark a quote as declined.

        Args:
            conn: Database connection
            quote_id: Quote ID
            tenant_id: Tenant ID (for scoping)
            reason: Optional reason for declining

        Returns:
            Updated Quote object

        Raises:
            StorageError on DB failure
        """
        now = datetime.now(timezone.utc).isoformat()

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE quotes
                SET status = 'declined', declined_at = ?, declined_reason = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (now, reason, quote_id, tenant_id),
            )
            conn.commit()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to decline quote: {exc}") from exc

        # Fetch and return updated quote
        quote = QuoteRepository.get_quote(conn, quote_id, tenant_id)
        if not quote:
            raise StorageError(f"Quote {quote_id} not found after update")
        return quote

    @staticmethod
    def list_quotes_by_contact(
        conn: Connection, tenant_id: str, contact_id: str, limit: int = 10
    ) -> list[Quote]:
        """Fetch recent quotes for a contact (tenant-scoped).

        Args:
            conn: Database connection
            tenant_id: Tenant ID (for scoping)
            contact_id: GHL contact ID
            limit: Max number of quotes to return

        Returns:
            List of Quote objects, ordered by created_at DESC

        Raises:
            StorageError on DB failure
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tenant_id, contact_id, contact_name, contact_email,
                       service_scope, industry, estimated_range_low, estimated_range_high,
                       caveat, status, email_template, created_at, sent_at,
                       accepted_at, declined_at, declined_reason, appointment_id
                FROM quotes
                WHERE tenant_id = ? AND contact_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (tenant_id, contact_id, limit),
            )
            rows = cursor.fetchall()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to list quotes: {exc}") from exc

        return [
            Quote(
                id=row[0],
                tenant_id=row[1],
                contact_id=row[2],
                contact_name=row[3],
                contact_email=row[4],
                service_scope=row[5],
                industry=row[6],
                estimated_range_low=row[7],
                estimated_range_high=row[8],
                caveat=row[9],
                status=row[10],
                email_template=row[11],
                created_at=row[12],
                sent_at=row[13],
                accepted_at=row[14],
                declined_at=row[15],
                declined_reason=row[16],
                appointment_id=row[17],
            )
            for row in rows
        ]

    @staticmethod
    def list_quotes_by_tenant_status(
        conn: Connection, tenant_id: str, status: str, limit: int = 100
    ) -> list[Quote]:
        """Fetch quotes by status for a tenant (tenant-scoped).

        Useful for queries like "show me all pending quotes" or "quotes accepted this week".

        Args:
            conn: Database connection
            tenant_id: Tenant ID (for scoping)
            status: Status filter (pending, sent, accepted, declined)
            limit: Max number of quotes to return

        Returns:
            List of Quote objects, ordered by created_at DESC

        Raises:
            StorageError on DB failure
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, tenant_id, contact_id, contact_name, contact_email,
                       service_scope, industry, estimated_range_low, estimated_range_high,
                       caveat, status, email_template, created_at, sent_at,
                       accepted_at, declined_at, declined_reason, appointment_id
                FROM quotes
                WHERE tenant_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (tenant_id, status, limit),
            )
            rows = cursor.fetchall()
        except DB_ERRORS as exc:
            raise StorageError(f"Failed to list quotes by status: {exc}") from exc

        return [
            Quote(
                id=row[0],
                tenant_id=row[1],
                contact_id=row[2],
                contact_name=row[3],
                contact_email=row[4],
                service_scope=row[5],
                industry=row[6],
                estimated_range_low=row[7],
                estimated_range_high=row[8],
                caveat=row[9],
                status=row[10],
                email_template=row[11],
                created_at=row[12],
                sent_at=row[13],
                accepted_at=row[14],
                declined_at=row[15],
                declined_reason=row[16],
                appointment_id=row[17],
            )
            for row in rows
        ]
