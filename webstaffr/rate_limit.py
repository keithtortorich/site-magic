"""Per-tenant, per-endpoint request rate limiting.

Backed by the existing db.py connection layer (SQLite locally, Postgres/
Supabase in production) rather than a new external dependency (Redis,
Upstash, Vercel KV). That was an explicit choice, not a default: this app
runs as Vercel serverless functions with no persistent process (see
CLAUDE.md's hosting invariant), so an in-memory counter would only ever
enforce a limit within a single warm instance -- Vercel's multiple/cold-
started instances would each get their own counter, giving no real ceiling
in production. A DB-backed counter is correctly shared across every
instance because the count lives in the database, not process memory, and
needs no new vendor relationship (see the matching CLAUDE.md addendum,
2026-07-08, for the tradeoff this was weighed against).

[Inference] This is a fixed-window counter, not sliding-window or token-
bucket: simpler, and precise enough to bound the actual risk this closes
-- an unauthenticated caller running up real, billed xAI usage with no
ceiling -- at the cost of allowing up to ~2x the nominal limit in the
worst case across a window boundary (e.g. a burst at the end of one
window and another at the start of the next). That imprecision is an
accepted MVP-stage tradeoff, not an oversight.

DEFAULT_MAX_REQUESTS_PER_WINDOW is a round, conservative placeholder, not
derived from measured traffic -- no real customer usage data exists yet.
Tune once real usage patterns exist.

Known gap, not fixed here: rows in rate_limit_counters are never pruned.
At MVP request volumes this is not a practical concern, but nothing
automatically deletes old windows -- add a cleanup migration or scheduled
job before this matters at real production volume.
"""

from __future__ import annotations

import time
from typing import Any, Iterable

DEFAULT_WINDOW_SECONDS = 60
DEFAULT_MAX_REQUESTS_PER_WINDOW = 30


def direct_client_ip(request: Any) -> str:
    """Return the ASGI peer address and never trust caller-set forwarding headers.

    A future deployment may add an explicit trusted-proxy allowlist. Until then,
    accepting X-Forwarded-For would let any caller choose its own rate-limit key.
    """
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


class RateLimitExceeded(Exception):
    """Raised by check_and_increment() when a tenant+endpoint has exceeded
    its request budget for the current window. Callers translate this into
    an HTTP 429, not a 5xx -- this is expected caller behavior, not a
    server failure."""

    def __init__(self, tenant_id: str, endpoint: str, count: int, max_requests: int, window_seconds: int) -> None:
        self.tenant_id = tenant_id
        self.endpoint = endpoint
        self.count = count
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        super().__init__(
            f"tenant={tenant_id!r} endpoint={endpoint!r} exceeded {max_requests} "
            f"requests in {window_seconds}s (count={count})"
        )


def check_dimensions(
    conn: Any,
    endpoint: str,
    dimensions: Iterable[tuple[str, str]],
    *,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    max_requests: int = DEFAULT_MAX_REQUESTS_PER_WINDOW,
) -> None:
    """Atomically increment independent account, principal, and IP buckets."""
    window_start = int(time.time() // window_seconds) * window_seconds
    for dimension_type, dimension_key in dimensions:
        conn.execute(
            """
            INSERT INTO rate_limit_dimensions AS t
                (dimension_type, dimension_key, endpoint, window_start, request_count)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT (dimension_type, dimension_key, endpoint, window_start)
            DO UPDATE SET request_count = t.request_count + 1
            """,
            (dimension_type, dimension_key, endpoint, window_start),
        )
        row = conn.execute(
            """
            SELECT request_count FROM rate_limit_dimensions
            WHERE dimension_type = ? AND dimension_key = ?
              AND endpoint = ? AND window_start = ?
            """,
            (dimension_type, dimension_key, endpoint, window_start),
        ).fetchone()
        count = row["request_count"]
        if count > max_requests:
            raise RateLimitExceeded(dimension_key, endpoint, count, max_requests, window_seconds)


def check_and_increment(
    conn: Any,
    tenant_id: str,
    endpoint: str,
    *,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
    max_requests: int = DEFAULT_MAX_REQUESTS_PER_WINDOW,
) -> int:
    """Increments this tenant+endpoint's counter for the current fixed
    window and returns the new count. Raises RateLimitExceeded if that
    count is over max_requests.

    Uses a single portable `INSERT ... ON CONFLICT DO UPDATE` statement --
    both SQLite (3.24+, i.e. any Python 3 bundled sqlite3) and Postgres
    support this upsert syntax natively, so this needed no new dialect
    translation in db.py's _PGConnection shim, unlike the codebase's other
    upserts (which predate SQLite's UPSERT support and use the older
    `INSERT OR IGNORE`/`INSERT OR REPLACE` forms that db.py does translate).

    Caller is responsible for conn.commit() (same convention as every
    other repository in this codebase). Deliberately does NOT roll back
    the increment just because the request is then rejected -- a rejected
    request still "used" its slot; that's the point of counting it at
    all."""
    window_start = int(time.time() // window_seconds) * window_seconds
    conn.execute(
        """
        INSERT INTO rate_limit_counters AS t (tenant_id, endpoint, window_start, request_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT (tenant_id, endpoint, window_start)
        DO UPDATE SET request_count = t.request_count + 1
        """,
        (tenant_id, endpoint, window_start),
    )
    row = conn.execute(
        "SELECT request_count FROM rate_limit_counters WHERE tenant_id = ? AND endpoint = ? AND window_start = ?",
        (tenant_id, endpoint, window_start),
    ).fetchone()
    count = row["request_count"]
    if count > max_requests:
        raise RateLimitExceeded(tenant_id, endpoint, count, max_requests, window_seconds)
    return count
