"""ServiceTitan integration package.

Enabled/disabled by env var: SERVICETITAN_ENABLED=true|false
All network access is isolated here; everything else imports from this
package, not from urllib directly.
"""
from __future__ import annotations

from .client import (
    ServiceTitanClient,
    ServiceTitanConfigError,
    ServiceTitanHTTPError,
    ServiceTitanNotConfiguredError,
)
from .sync import ServiceTitanSync, SyncResult
from .mocks import MockServiceTitanClient

__all__ = [
    "ServiceTitanClient",
    "ServiceTitanConfigError",
    "ServiceTitanHTTPError",
    "ServiceTitanNotConfiguredError",
    "ServiceTitanSync",
    "SyncResult",
    "MockServiceTitanClient",
]
