"""Per-tenant customer dashboard aggregation.

Builds the single payload the client-facing dashboard reads: a tenant's
business snapshot, ROI/call metrics, lead and appointment counts, review
and quote progress, site-build status, Angel (voice agent) presence, and a
recent-activity feed.

This is a READ-ONLY aggregation layer. It composes existing repositories
(attribution.CallEventRepository) and COUNT/MAX queries against tables that
already exist (intake_submissions, website_leads, appointments,
review_requests, review_responses, quotes, site_magic_jobs, call_events).
No new table, no migration, no write path. Every number is computed from
real rows -- a tenant with no activity sees zeros and empty sections, never
a fabricated "looks busy" figure (perfect-site principle, same as
attribution.py).

Tenant isolation is structural: every query in this module carries
`WHERE tenant_id = ?`. There is no path that aggregates across tenants.

Follows the same repository shape as attribution.py / intake.py: a dataclass
plus a repository class operating on an already-open connection (SQLite or
Postgres via db.get_connection), with `?` placeholders throughout.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .attribution import CallEventRepository
from .db import DB_ERRORS


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _count(conn: Any, table: str, tenant_id: str, extra_where: str = "", params: tuple = ()) -> int:
    """Tenant-scoped COUNT helper. `extra_where` must already be
    tenant-safe (caller appends `AND ...` with its own `?` params); the
    tenant_id predicate is always applied first."""
    sql = f"SELECT COUNT(*) AS n FROM {table} WHERE tenant_id = ? {extra_where}"
    try:
        row = conn.execute(sql, (tenant_id, *params)).fetchone()
    except DB_ERRORS as exc:  # pragma: no cover - exercised via router 503 path
        raise
    return int(row["n"]) if row is not None else 0


@dataclass
class DashboardData:
    tenant_id: str
    generated_at: str
    business: Optional[dict]
    kpis: dict
    roi: dict
    site: Optional[dict]
    angel: dict
    activity: list[dict]


class DashboardRepository:
    """Reads the dashboard payload for one tenant off an open connection."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def business_snapshot(self, tenant_id: str) -> Optional[dict]:
        """Header identity for the dashboard, from the latest intake row.
        Returns None when the tenant has no intake submission yet (the
        dashboard still renders, just without a business name/industry)."""
        row = self._conn.execute(
            """
            SELECT biz_name, industry, service_area, plan, tagline, created_at
            FROM intake_submissions
            WHERE tenant_id = ?
            ORDER BY created_at DESC, submission_id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "biz_name": row["biz_name"],
            "industry": row["industry"],
            "service_area": row["service_area"],
            "plan": row["plan"],
            "tagline": row["tagline"],
            "onboarded_at": row["created_at"],
        }

    def site_status(self, tenant_id: str) -> Optional[dict]:
        """Latest Site Magic job status + published URL for the tenant."""
        row = self._conn.execute(
            """
            SELECT job_id, status, final_build_id, created_at, updated_at
            FROM site_magic_jobs
            WHERE tenant_id = ?
            ORDER BY created_at DESC, job_id DESC
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()
        if row is None:
            return None
        published_url = None
        if row["final_build_id"] is not None:
            pub = self._conn.execute(
                "SELECT published_url FROM site_magic_builds WHERE build_id = ? AND tenant_id = ?",
                (row["final_build_id"], tenant_id),
            ).fetchone()
            if pub is not None:
                published_url = pub["published_url"]
        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "published_url": published_url,
            "updated_at": row["updated_at"],
        }

    def review_summary(self, tenant_id: str) -> dict:
        """Counts + average rating from real review rows. Average is None
        when no rated reviews exist (never 0.0 faked)."""
        received = _count(self._conn, "review_responses", tenant_id)
        pending = _count(
            self._conn, "review_responses", tenant_id,
            "AND response_status = ?", ("pending_draft",),
        )
        requests_sent = _count(self._conn, "review_requests", tenant_id)
        rating_row = self._conn.execute(
            """
            SELECT AVG(review_rating) AS avg_rating, COUNT(review_rating) AS rated
            FROM review_responses
            WHERE tenant_id = ? AND review_rating IS NOT NULL
            """,
            (tenant_id,),
        ).fetchone()
        avg = None
        if rating_row is not None and rating_row["rated"]:
            avg = round(float(rating_row["avg_rating"]), 2)
        return {
            "reviews_received": received,
            "responses_pending": pending,
            "requests_sent": requests_sent,
            "avg_rating": avg,
        }

    def quote_summary(self, tenant_id: str) -> dict:
        pending = _count(self._conn, "quotes", tenant_id, "AND status = ?", ("pending",))
        accepted = _count(self._conn, "quotes", tenant_id, "AND status = ?", ("accepted",))
        total = _count(self._conn, "quotes", tenant_id)
        return {"total": total, "pending": pending, "accepted": accepted}

    def appointment_summary(self, tenant_id: str) -> dict:
        total = _count(self._conn, "appointments", tenant_id)
        upcoming = self._conn.execute(
            """
            SELECT COUNT(*) AS n FROM appointments
            WHERE tenant_id = ? AND starts_at > ?
            """,
            (tenant_id, _now_iso()),
        ).fetchone()
        upcoming_n = int(upcoming["n"]) if upcoming is not None else 0
        return {"total": total, "upcoming": upcoming_n}

    def angel_presence(self, tenant_id: str) -> dict:
        """Derives Angel (voice agent) status from real signals only.
        - tracking_number_present: a tracking line was provisioned at intake
        - calls_fielded: count of call_events (received/ended/booked)
        We never claim the agent is "live" without at least a tracking line;
        "active" requires actual call events to have been logged."""
        tn_row = self._conn.execute(
            "SELECT tracking_number FROM tracking_numbers WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        tracking_present = tn_row is not None
        calls = _count(self._conn, "call_events", tenant_id)
        if calls > 0:
            status = "active"
        elif tracking_present:
            status = "configured"
        else:
            status = "not_configured"
        return {
            "status": status,
            "tracking_number_present": tracking_present,
            "calls_fielded": calls,
        }

    def activity_feed(self, tenant_id: str, limit: int = 12) -> list[dict]:
        """Union of the most recent tenant events across every tracked
        surface, newest first. Each row is a small normalized event; the
        dashboard renders a human label from `type` + payload."""
        events: list[tuple[str, str, dict]] = []

        for row in self._conn.execute(
            """
            SELECT event_id, event_type, outcome, created_at
            FROM call_events WHERE tenant_id = ? ORDER BY created_at DESC, event_id DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("call", row["created_at"], {
                "event_type": row["event_type"], "outcome": row["outcome"],
            }))

        for row in self._conn.execute(
            """
            SELECT lead_id, name, service, status, created_at
            FROM website_leads WHERE tenant_id = ? ORDER BY created_at DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("lead", row["created_at"], {
                "name": row["name"], "service": row["service"], "status": row["status"],
            }))

        for row in self._conn.execute(
            """
            SELECT appointment_id, contact_name, starts_at, source, created_at
            FROM appointments WHERE tenant_id = ? ORDER BY created_at DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("appointment", row["created_at"], {
                "contact_name": row["contact_name"], "starts_at": row["starts_at"],
                "source": row["source"],
            }))

        for row in self._conn.execute(
            """
            SELECT response_id, review_source, review_rating, response_status, received_at
            FROM review_responses WHERE tenant_id = ? ORDER BY received_at DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("review", row["received_at"], {
                "review_source": row["review_source"], "review_rating": row["review_rating"],
                "response_status": row["response_status"],
            }))

        for row in self._conn.execute(
            """
            SELECT id, contact_name, status, created_at
            FROM quotes WHERE tenant_id = ? ORDER BY created_at DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("quote", row["created_at"], {
                "contact_name": row["contact_name"], "status": row["status"],
            }))

        for row in self._conn.execute(
            """
            SELECT job_id, status, updated_at
            FROM site_magic_jobs WHERE tenant_id = ? ORDER BY updated_at DESC
            """,
            (tenant_id,),
        ).fetchall():
            events.append(("site", row["updated_at"], {
                "job_id": row["job_id"], "status": row["status"],
            }))

        # Normalize timestamps for sorting; rows may carry 'Z' or naive iso.
        def _sort_key(item: tuple[str, str, dict]) -> str:
            ts = item[1] or ""
            return ts

        events.sort(key=_sort_key, reverse=True)
        return [
            {"type": t, "timestamp": ts, "payload": p}
            for (t, ts, p) in events[:limit]
        ]


def build_dashboard_data(conn: Any, tenant_id: str) -> DashboardData:
    """Compose the full dashboard payload for one tenant.

    Every aggregation is tenant-scoped. No row from another tenant is ever
    readable through this function."""
    repo = DashboardRepository(conn)
    metrics = CallEventRepository(conn).metrics_for_tenant(tenant_id)

    kpis = {
        "calls_received": metrics["calls_received"],
        "calls_completed": metrics["calls_completed"],
        "appointments_booked": metrics["appointments_booked"],
        "appointments_upcoming": repo.appointment_summary(tenant_id)["upcoming"],
        "appointments_total": repo.appointment_summary(tenant_id)["total"],
        "leads_received": _count(conn, "website_leads", tenant_id),
        "reviews_received": repo.review_summary(tenant_id)["reviews_received"],
        "review_avg_rating": repo.review_summary(tenant_id)["avg_rating"],
        "review_responses_pending": repo.review_summary(tenant_id)["responses_pending"],
        "quotes_pending": repo.quote_summary(tenant_id)["pending"],
        "quotes_accepted": repo.quote_summary(tenant_id)["accepted"],
    }

    return DashboardData(
        tenant_id=tenant_id,
        generated_at=_now_iso(),
        business=repo.business_snapshot(tenant_id),
        kpis=kpis,
        roi={
            "appointments_booked": metrics["appointments_booked"],
            "estimated_value_usd": metrics["estimated_value_usd"],
            "estimated_value_note": metrics["estimated_value_note"],
        },
        site=repo.site_status(tenant_id),
        angel=repo.angel_presence(tenant_id),
        activity=repo.activity_feed(tenant_id),
    )


def dashboard_data_to_dict(data: DashboardData) -> dict:
    return {
        "tenant_id": data.tenant_id,
        "generated_at": data.generated_at,
        "business": data.business,
        "kpis": data.kpis,
        "roi": data.roi,
        "site": data.site,
        "angel": data.angel,
        "activity": data.activity,
    }
