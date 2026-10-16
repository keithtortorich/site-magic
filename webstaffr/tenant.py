"""Tenant Context — the bounded scope every other entity belongs to.

A Tenant is an identifier only. No profile data, settings, or
relationships beyond what other entities reference back to it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class InvalidTenantError(ValueError):
    """Raised when a tenant identifier fails validation."""


@dataclass(frozen=True)
class Tenant:
    """A tenant: identifier only, per the minimal first-slice design."""

    tenant_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or not _ID_PATTERN.match(self.tenant_id):
            raise InvalidTenantError(
                f"Invalid tenant_id: {self.tenant_id!r}. "
                "Must be 1-64 chars of letters, digits, underscore, or hyphen."
            )
