"""ServiceTitan OAuth2 client.

Uses stdlib json + urllib only by design so this integration does not
add a new dependency. httpx is already present in requirements.txt,
but ServiceTitan is a small infrequent call surface; stdlib keeps
_the operational model_ the same as GHL (`ghl.py`), which is itself
usable offline via mocks.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


class ServiceTitanNotConfiguredError(RuntimeError):
    """Raised when the client is instantiated without required env vars."""


class ServiceTitanConfigError(RuntimeError):
    """Raised when configuration is present but invalid."""


class ServiceTitanHTTPError(RuntimeError):
    """Raised when a ServiceTitan API call returns a non-2xx status."""


class ServiceTitanClient:
    """Real ServiceTitan API client.

    Env vars:
      SERVICETITAN_CLIENT_ID
      SERVICETITAN_CLIENT_SECRET
      SERVICETITAN_TENANT_ID
      SERVICETITAN_BASE_URL  optional, defaults to production V2 base
    """

    BASE_URL = "https://app.servicetitan.com/api/v2"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.client_id = client_id or os.environ.get("SERVICETITAN_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("SERVICETITAN_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.environ.get("SERVICETITAN_TENANT_ID")
        self.base_url = base_url or os.environ.get("SERVICETITAN_BASE_URL", self.BASE_URL)

        missing = [
            name
            for name, value in [
                ("SERVICETITAN_CLIENT_ID", self.client_id),
                ("SERVICETITAN_CLIENT_SECRET", self.client_secret),
                ("SERVICETITAN_TENANT_ID", self.tenant_id),
            ]
            if not value
        ]
        if missing:
            raise ServiceTitanNotConfiguredError(
                "ServiceTitan client requires "
                + ", ".join(missing)
                + " (env vars or constructor args)."
            )

        self._access_token: Optional[str] = None

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        url = f"{self.base_url}/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            raise ServiceTitanHTTPError(
                f"ServiceTitan auth failed: {exc.code} {exc.read().decode('utf-8', errors='replace')}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ServiceTitanHTTPError(f"ServiceTitan auth unreachable: {exc}") from exc

        token = body.get("access_token")
        if not token:
            raise ServiceTitanHTTPError(f"ServiceTitan auth response missing access_token: {body}")
        self._access_token = token
        return token

    def _request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        token = self._get_access_token()
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "TenantId": self.tenant_id,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
                return body if isinstance(body, dict) else {"data": body}
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise ServiceTitanHTTPError(
                f"ServiceTitan API error {exc.code} on {method} {path}: {text}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ServiceTitanHTTPError(f"ServiceTitan unreachable for {method} {path}: {exc}") from exc

    def list_jobs(self, *, modified_since: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("jobs", modified_since=modified_since, limit=limit)

    def list_appointments(
        self,
        *,
        modified_since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get_collection("appointments", modified_since=modified_since, limit=limit)

    def list_customers(
        self,
        *,
        modified_since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get_collection("customers", modified_since=modified_since, limit=limit)

    def list_locations(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("locations", limit=limit)

    def list_invoices(
        self,
        *,
        modified_since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get_collection("invoices", modified_since=modified_since, limit=limit)

    def list_payments(
        self,
        *,
        modified_since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._get_collection("payments", modified_since=modified_since, limit=limit)

    def list_projects(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("projects", limit=limit)

    def list_installed_equipment(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("installed-equipment", limit=limit)

    def list_technicians(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("technicians", limit=limit)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self._request("GET", f"/{self.tenant_id}/jobs/{job_id}")

    def list_books(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return self._get_collection("books", limit=limit)

    def _get_collection(
        self,
        resource: str,
        *,
        modified_since: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params = [f"$limit={limit}"]
        if modified_since:
            params.append(f"$filter=modifiedOn ge {modified_since}")
        suffix = "&".join(params)
        return self._request("GET", f"/{self.tenant_id}/{resource}?{suffix}").get("data", [])
