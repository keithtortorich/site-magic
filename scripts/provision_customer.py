#!/usr/bin/env python3
"""Provision an existing Supabase Auth user into one tenant.

The database operation is intentionally separate from provider lookup so the
identity resolver can be injected by an approved administrative integration.
The command-line boundary fails closed until such a resolver is configured.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webstaffr.db import DB_ERRORS, get_connection

ROLES = ("owner", "manager", "dispatcher", "viewer")


class ProvisioningError(RuntimeError):
    """Expected, operator-safe provisioning failure."""


class AuthIdentityResolver(Protocol):
    def resolve(self, email: str) -> Sequence[str]: ...


class UnconfiguredAuthIdentityResolver:
    """Safe default: public Supabase credentials cannot enumerate Auth users."""

    def resolve(self, email: str) -> Sequence[str]:
        raise ProvisioningError(
            "Supabase Auth identity lookup is not configured. No changes were made."
        )


class DatabaseAuthIdentityResolver:
    """Resolve identity through the trusted Postgres connection to auth.users."""

    def __init__(self, connection_factory: Callable[[], object] = get_connection):
        self._connection_factory = connection_factory

    def resolve(self, email: str) -> Sequence[str]:
        conn = None
        try:
            conn = self._connection_factory()
            rows = conn.execute(
                """
                SELECT id FROM auth.users
                WHERE lower(email) = lower(?)
                ORDER BY id
                LIMIT 2
                """,
                (email,),
            ).fetchall()
            return [str(row["id"]) for row in rows]
        except DB_ERRORS as exc:
            raise ProvisioningError(
                "Supabase Auth identity lookup failed. No changes were made."
            ) from exc
        finally:
            if conn is not None:
                conn.close()


@dataclass(frozen=True)
class ProvisioningResult:
    outcome: str
    email: str
    tenant_id: str
    role: str


def _normalized_email(email: str) -> str:
    value = email.strip().lower()
    if not value or "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ProvisioningError("A valid customer email is required. No changes were made.")
    return value


def _resolved_user_id(resolver: AuthIdentityResolver, email: str) -> str:
    matches = list(resolver.resolve(email))
    if not matches:
        raise ProvisioningError(
            f"No Supabase Auth user found for {email}. Invite or create the user, then retry."
        )
    if len(matches) != 1:
        raise ProvisioningError(
            f"Multiple Supabase Auth users found for {email}. No changes were made."
        )
    try:
        return str(uuid.UUID(str(matches[0])))
    except (TypeError, ValueError) as exc:
        raise ProvisioningError(
            f"Supabase Auth returned an invalid identity for {email}. No changes were made."
        ) from exc


def provision_customer(
    email: str,
    tenant_id: str,
    role: str,
    resolver: AuthIdentityResolver,
    *,
    connection_factory: Callable[[], object] = get_connection,
) -> ProvisioningResult:
    """Create an active customer and membership in one transaction."""
    email = _normalized_email(email)
    tenant_id = tenant_id.strip()
    role = role.strip().lower()
    if role not in ROLES:
        raise ProvisioningError(f"Role must be one of: {', '.join(ROLES)}.")
    if not tenant_id:
        raise ProvisioningError("Tenant ID is required. No changes were made.")

    user_id = _resolved_user_id(resolver, email)
    conn = None
    try:
        conn = connection_factory()
        tenant = conn.execute(
            "SELECT tenant_id FROM tenants WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        if tenant is None:
            raise ProvisioningError(
                f"Tenant {tenant_id} was not found. No changes were made."
            )

        user = conn.execute(
            "SELECT status FROM customer_users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if user is not None and user["status"] != "active":
            raise ProvisioningError(
                f"Customer user already exists with status {user['status']}. No changes were made."
            )

        membership = conn.execute(
            """
            SELECT role, status FROM tenant_memberships
            WHERE tenant_id = ? AND user_id = ?
            """,
            (tenant_id, user_id),
        ).fetchone()
        if membership is not None:
            if membership["role"] == role and membership["status"] == "active":
                conn.rollback()
                return ProvisioningResult("no-op", email, tenant_id, role)
            value = f"{membership['role']}/{membership['status']}"
            raise ProvisioningError(
                f"Membership already exists with role or status {value}. No changes were made."
            )

        if user is None:
            conn.execute(
                "INSERT INTO customer_users (user_id, status) VALUES (?, 'active')",
                (user_id,),
            )
        conn.execute(
            """
            INSERT INTO tenant_memberships (tenant_id, user_id, role, status)
            VALUES (?, ?, ?, 'active')
            """,
            (tenant_id, user_id, role),
        )
        conn.commit()
        return ProvisioningResult("created", email, tenant_id, role)
    except ProvisioningError:
        if conn is not None:
            conn.rollback()
        raise
    except DB_ERRORS as exc:
        if conn is not None:
            conn.rollback()
        raise ProvisioningError(
            "Customer provisioning failed. No changes were made."
        ) from exc
    finally:
        if conn is not None:
            conn.close()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Provision existing customer access")
    parser.add_argument("--email", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--role", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    resolver: AuthIdentityResolver | None = None,
    connection_factory: Callable[[], object] = get_connection,
) -> int:
    args = _parser().parse_args(argv)
    if resolver is None:
        resolver = (
            DatabaseAuthIdentityResolver(connection_factory)
            if os.environ.get("DATABASE_URL")
            else UnconfiguredAuthIdentityResolver()
        )
    try:
        result = provision_customer(
            args.email,
            args.tenant_id,
            args.role,
            resolver,
            connection_factory=connection_factory,
        )
    except ProvisioningError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if result.outcome == "no-op":
        print(
            f"Access already provisioned for {result.email} as {result.role} "
            f"on tenant {result.tenant_id}. No changes were needed."
        )
    else:
        print(
            f"Access provisioned for {result.email} as {result.role} on tenant "
            f"{result.tenant_id}. Verify sign-in and tenant access before sending "
            "account-ready confirmation."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
