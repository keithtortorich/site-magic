"""FastAPI router serving public, tenant_id-driven site data -- what the
customer site fetches client-side to render a business's page.

Mounted into the main app via create_app().include_router(site_router) in
webstaffr/app.py, same pattern as intake_router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from .db import DB_ERRORS, get_connection
from .intake import IntakeRepository
from .site_data import build_public_site_data
from .tenant import InvalidTenantError, Tenant

logger = logging.getLogger("webstaffr.site_router")

site_router = APIRouter()


def _get_connection(request: Request):
    """Backend (SQLite vs Postgres) is chosen by db.get_connection() based
    on DATABASE_URL -- this router doesn't need to know which one it got.
    Raises HTTPException(503) on a DB-layer failure (e.g. Postgres
    unreachable) instead of letting a raw psycopg2/sqlite3 exception -- and
    the connection details in its message -- propagate to the client."""
    try:
        return get_connection(request.app.state.db_path)
    except DB_ERRORS as exc:
        # Log the exception type only -- never str(exc), which for a
        # psycopg2 error can include the connection string (host, user).
        # Without this, a 503 here was previously silent: no traceback,
        # no log line, nothing visible in Vercel's request logs to
        # distinguish "DB unreachable" from any other cause.
        logger.error("site_data_db_connection_failed error_type=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Site data temporarily unavailable") from exc


@site_router.get("/sites/{tenant_id}")
def get_site_data(tenant_id: str, request: Request) -> dict:
    """Public site content for one tenant. 404 if the tenant_id is invalid
    or no intake submission exists yet -- either way, there's no site to
    render, and the caller shouldn't be able to tell which case it was
    (no information leakage about which tenant_ids are valid)."""
    try:
        Tenant(tenant_id=tenant_id)
    except InvalidTenantError as exc:
        raise HTTPException(status_code=404, detail="No site found for this tenant") from exc

    conn = _get_connection(request)
    try:
        submission = IntakeRepository(conn).load_latest_for_tenant(tenant_id)
    finally:
        conn.close()

    if submission is None:
        raise HTTPException(status_code=404, detail="No site found for this tenant")

    return build_public_site_data(submission)
