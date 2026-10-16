"""ServiceTitan client mock for offline tests and local development."""
from __future__ import annotations

from typing import Any, Optional

from .client import ServiceTitanClient, ServiceTitanHTTPError


class MockServiceTitanClient:
    """Deterministic, credential-free fake ServiceTitan client."""

    def __init__(self, *, seed: Optional[dict[str, list[dict[str, Any]]]] = None, fail: Optional[str] = None) -> None:
        self.seed = seed or {}
        self.fail = fail
        self.calls: list[tuple[str, str, Optional[dict[str, Any]]]] = []

    def _accept_sync_kwargs(self, key: str, modified_since=None, limit=100):  # type: ignore[override]
        if self.fail == key:
            raise ServiceTitanHTTPError(f"forced failure for {key}")
        return list(self.seed.get(key, []))

    def list_jobs(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("jobs", *args, **kwargs)

    def list_appointments(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("appointments", *args, **kwargs)

    def list_customers(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("customers", *args, **kwargs)

    def list_locations(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("locations", *args, **kwargs)

    def list_invoices(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("invoices", *args, **kwargs)

    def list_payments(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("payments", *args, **kwargs)

    def list_projects(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("projects", *args, **kwargs)

    def list_installed_equipment(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("installed_equipment", *args, **kwargs)

    def list_technicians(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("technicians", *args, **kwargs)

    def get_job(self, job_id: str) -> dict[str, Any]:  # type: ignore[override]
        for item in self._accept_sync_kwargs("jobs"):
            if str(item.get("id")) == str(job_id):
                return item
        return {}

    def list_books(self, *args, **kwargs):  # type: ignore[override]
        return self._accept_sync_kwargs("books", *args, **kwargs)
