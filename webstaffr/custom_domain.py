"""Custom domain routing for rendered sites.

Allows tenants to serve their sites at a custom domain (e.g., desertcooling.com)
instead of the path-based /sites/{tenant_id}/web route. Resolves custom_domain
column in the tenants table via Host header lookup.

Phase 2 feature (see docs/DECISIONS.md ADR-002).
"""

from __future__ import annotations

import logging
from typing import Optional

from .db import get_connection, DB_ERRORS

logger = logging.getLogger("webstaffr.custom_domain")


def resolve_tenant_from_host(host_header: str, db_path: str) -> Optional[str]:
    """Resolve tenant_id from a custom domain via Host header lookup.

    Args:
        host_header: The HTTP Host header value (e.g., 'desertcooling.com:8080')
        db_path: Path to the database

    Returns:
        tenant_id if the domain is registered as a custom_domain, None otherwise.
        Returns None for invalid lookups, connection errors, etc. (falls back to
        path-based routing).
    """
    if not host_header:
        return None

    # Strip port if present (Host header may include port)
    domain = host_header.split(":")[0].lower()

    try:
        conn = get_connection(db_path)
        try:
            cursor = conn.execute(
                "SELECT tenant_id FROM tenants WHERE custom_domain = ?",
                (domain,),
            )
            row = cursor.fetchone()
            return row["tenant_id"] if row else None
        finally:
            conn.close()
    except DB_ERRORS as exc:
        logger.warning(
            "custom_domain_resolution_failed domain=%s error_type=%s",
            domain,
            type(exc).__name__,
        )
        return None
