"""ServiceTitan sync logic.

Read-first bounded sync. One `SyncResult` per resource type. Failures
are isolated so a disconnect on one endpoint does not abort the whole
run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .client import ServiceTitanClient, ServiceTitanHTTPError

logger = logging.getLogger("webstaffr.integrations.servicetitan")


@dataclass(frozen=True)
class SyncResult:
    resource: str
    fetched: int = 0
    failed: bool = False
    error: Optional[str] = None
    data: Sequence[dict[str, Any]] = field(default_factory=list)


class ServiceTitanSync:
    """Coordinates bounded reads from ServiceTitan."""

    def __init__(
        self,
        client: ServiceTitanClient,
        *,
        limit: int = 100,
        modified_since: Optional[str] = None,
    ) -> None:
        self.client = client
        self.limit = limit
        self.modified_since = modified_since

    def run(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        for name, fn in [
            ("jobs", lambda: self.client.list_jobs(limit=self.limit, modified_since=self.modified_since)),
            ("appointments", lambda: self.client.list_appointments(limit=self.limit, modified_since=self.modified_since)),
            ("customers", lambda: self.client.list_customers(limit=self.limit, modified_since=self.modified_since)),
            ("locations", lambda: self.client.list_locations(limit=self.limit)),
            ("invoices", lambda: self.client.list_invoices(limit=self.limit, modified_since=self.modified_since)),
            ("payments", lambda: self.client.list_payments(limit=self.limit, modified_since=self.modified_since)),
            ("projects", lambda: self.client.list_projects(limit=self.limit)),
            ("installed_equipment", lambda: self.client.list_installed_equipment(limit=self.limit)),
            ("technicians", lambda: self.client.list_technicians(limit=self.limit)),
        ]:
            results.append(self._safe_fetch(name, fn))
        return results

    def _safe_fetch(self, name: str, fn: Callable[[], Sequence[dict[str, Any]]]) -> SyncResult:
        try:
            data = fn()
            return SyncResult(resource=name, fetched=len(data), data=list(data))
        except ServiceTitanHTTPError as exc:
            logger.warning(
                "servicetitan_sync_failed resource=%s error_type=%s",
                name,
                type(exc).__name__,
            )
            return SyncResult(resource=name, failed=True, error=str(exc))
