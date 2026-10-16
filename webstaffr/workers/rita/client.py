"""Review request and response repositories.

All operations are tenant-scoped (tenant_id required on every query).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("webstaffr.rita.client")


class ReviewRequestRepository:
    """Handles database operations for review_requests table."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def create(
        self,
        tenant_id: str,
        contact_id: str,
        contact_name: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        review_source: str = "google",
        request_method: str = "sms",
        ghl_job_id: Optional[str] = None,
    ) -> dict:
        """Create a new review request after job completion."""
        from datetime import datetime

        cursor = self.conn.execute(
            """
            INSERT INTO review_requests (
                tenant_id, contact_id, contact_name, contact_phone, contact_email,
                review_source, request_method, ghl_job_id, requested_at, status,
                ghl_synced, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 0, ?)
            """,
            (
                tenant_id,
                contact_id,
                contact_name,
                contact_phone,
                contact_email,
                review_source,
                request_method,
                ghl_job_id,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
        request_id = cursor.lastrowid
        return {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "contact_id": contact_id,
            "created_at": datetime.utcnow().isoformat(),
        }

    def get_by_id(self, tenant_id: str, request_id: int) -> Optional[dict]:
        """Fetch a single review request by ID (tenant-scoped)."""
        cursor = self.conn.execute(
            "SELECT * FROM review_requests WHERE request_id = ? AND tenant_id = ?",
            (request_id, tenant_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_by_contact_id(self, tenant_id: str, contact_id: str) -> list[dict]:
        """Fetch every review request for a contact, scoped to one tenant.

        Returns a list because the same contact can be asked for a review more
        than once over time. The tenant_id predicate is what keeps one tenant's
        requests invisible to another, so it is never optional here.
        """
        cursor = self.conn.execute(
            "SELECT * FROM review_requests WHERE contact_id = ? AND tenant_id = ? "
            "ORDER BY request_id",
            (contact_id, tenant_id),
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_status(self, tenant_id: str, request_id: int, status: str) -> None:
        """Update the status of a review request."""
        self.conn.execute(
            "UPDATE review_requests SET status = ? WHERE request_id = ? AND tenant_id = ?",
            (status, request_id, tenant_id),
        )

    def mark_ghl_synced(self, tenant_id: str, request_id: int) -> None:
        """Mark a review request as synced to GHL."""
        self.conn.execute(
            "UPDATE review_requests SET ghl_synced = 1 WHERE request_id = ? AND tenant_id = ?",
            (request_id, tenant_id),
        )


class ReviewResponseRepository:
    """Handles database operations for review_responses table."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def create(
        self,
        tenant_id: str,
        review_source: str,
        review_rating: int,
        review_text: str,
        response_text: str,
        requires_approval: bool,
        external_review_id: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        request_id: Optional[int] = None,
    ) -> dict:
        """Create a new review response record."""
        from datetime import datetime

        status = "pending_draft"
        cursor = self.conn.execute(
            """
            INSERT INTO review_responses (
                tenant_id, request_id, review_source, external_review_id,
                review_rating, review_text, reviewer_name, received_at,
                response_status, response_text, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id,
                request_id,
                review_source,
                external_review_id,
                review_rating,
                review_text,
                reviewer_name,
                datetime.utcnow().isoformat(),
                status,
                response_text,
                datetime.utcnow().isoformat(),
            ),
        )
        response_id = cursor.lastrowid
        return {
            "response_id": response_id,
            "tenant_id": tenant_id,
            "response_status": status,
            "created_at": datetime.utcnow().isoformat(),
        }

    def get_by_id(self, tenant_id: str, response_id: int) -> Optional[dict]:
        """Fetch a single review response by ID (tenant-scoped)."""
        cursor = self.conn.execute(
            "SELECT * FROM review_responses WHERE response_id = ? AND tenant_id = ?",
            (response_id, tenant_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_pending_approval(self, tenant_id: str) -> list[dict]:
        """Fetch all responses pending founder approval (tenant-scoped)."""
        cursor = self.conn.execute(
            "SELECT * FROM review_responses WHERE tenant_id = ? AND response_status = 'pending_draft' ORDER BY created_at ASC",
            (tenant_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def approve_response(self, tenant_id: str, response_id: int) -> None:
        """Mark a response as approved and ready to post."""
        from datetime import datetime

        self.conn.execute(
            "UPDATE review_responses SET response_status = 'approved', response_approved_at = ? WHERE response_id = ? AND tenant_id = ?",
            (datetime.utcnow().isoformat(), response_id, tenant_id),
        )

    def mark_posted(self, tenant_id: str, response_id: int) -> None:
        """Mark a response as posted to the review platform."""
        from datetime import datetime

        self.conn.execute(
            "UPDATE review_responses SET response_status = 'posted', response_posted_at = ? WHERE response_id = ? AND tenant_id = ?",
            (datetime.utcnow().isoformat(), response_id, tenant_id),
        )

    def mark_failed(self, tenant_id: str, response_id: int, error: str) -> None:
        """Mark a response posting as failed."""
        self.conn.execute(
            "UPDATE review_responses SET response_status = 'failed' WHERE response_id = ? AND tenant_id = ?",
            (response_id, tenant_id),
        )
        logger.error(
            "review_response_posting_failed tenant=%s response_id=%s error=%s",
            tenant_id,
            response_id,
            error,
        )
