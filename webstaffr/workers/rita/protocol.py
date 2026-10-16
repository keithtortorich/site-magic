"""Review platform integration protocol and safe defaults (Null implementations).

Rita's integration approach mirrors Angel's voice and GHL clients: an explicit
Protocol interface, a NullReviewPlatformClient safe default, and real
implementations that fail loudly when credentials are missing. Dependencies
are injected via constructor, never hidden in global state.
"""

from __future__ import annotations

from typing import Protocol


class ReviewPlatformClient(Protocol):
    """Interface for review platform integrations (Google, Yelp, etc.).

    For MVP, both methods are no-ops; real implementations come post-MVP when
    a platform is chosen and configured."""

    def get_recent_reviews(self, tenant_id: str, since: str) -> list[dict]:
        """Fetch reviews received since a given ISO 8601 timestamp.

        Args:
            tenant_id: WebStaffr tenant ID (used to scope to that tenant's platform account)
            since: ISO 8601 timestamp; return reviews received after this time

        Returns:
            List of dicts, each with keys: external_review_id, review_rating,
            review_text, reviewer_name, received_at (ISO 8601), review_source.
            Empty list if platform unavailable or no reviews found.
        """
        ...

    def post_review_response(self, review_id: str, response_text: str) -> dict:
        """Post our response to a review on the external platform.

        Args:
            review_id: External platform's review ID (from get_recent_reviews)
            response_text: Our response text (drafted by Rita, approved by founder)

        Returns:
            Dict with at least 'status' key: 'posted', 'failed', 'not_found', etc.
        """
        ...


class NullReviewPlatformClient:
    """Safe default: records calls in memory, makes no network requests.
    Used for tests and for any tenant that hasn't configured a review
    platform yet."""

    def __init__(self) -> None:
        self.fetched_reviews: list = []
        self.posted_responses: list = []

    def get_recent_reviews(self, tenant_id: str, since: str) -> list[dict]:
        """Return empty list (no-op)."""
        self.fetched_reviews.append({"tenant_id": tenant_id, "since": since})
        return []

    def post_review_response(self, review_id: str, response_text: str) -> dict:
        """Log the call, return success (no-op)."""
        self.posted_responses.append({"review_id": review_id, "response_text": response_text})
        return {"status": "logged_in_memory"}
