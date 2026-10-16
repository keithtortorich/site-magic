import os
import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from scripts.provision_customer import (
    DatabaseAuthIdentityResolver,
    ProvisioningError,
    main,
    provision_customer,
)
from webstaffr.db import connect, get_connection, migrate
from webstaffr.app import create_app
from webstaffr.customer_auth import VerifiedIdentity


class Resolver:
    def __init__(self, matches):
        self.matches = matches

    def resolve(self, email):
        return self.matches


class IdentityVerifier:
    def __init__(self, identity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "provisioned-token" else None


@pytest.fixture
def database():
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    with connect(path) as conn:
        migrate(conn)
        conn.execute("INSERT INTO tenants (tenant_id) VALUES ('tenant_a')")
    yield path
    os.remove(path)


def factory(path):
    return lambda: get_connection(path)


def rows(path, table):
    with connect(path) as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def test_creates_real_resolved_user_and_membership(database):
    user_id = str(uuid.uuid4())
    result = provision_customer(
        " Customer@Example.com ", "tenant_a", "owner", Resolver([user_id]),
        connection_factory=factory(database),
    )
    assert result.outcome == "created"
    assert rows(database, "customer_users")[0]["user_id"] == user_id
    membership = rows(database, "tenant_memberships")[0]
    assert (membership["tenant_id"], membership["role"], membership["status"]) == (
        "tenant_a", "owner", "active"
    )


def test_identical_active_membership_is_no_op_without_duplicate(database):
    user_id = str(uuid.uuid4())
    kwargs = dict(connection_factory=factory(database))
    provision_customer("a@example.com", "tenant_a", "viewer", Resolver([user_id]), **kwargs)
    result = provision_customer("a@example.com", "tenant_a", "viewer", Resolver([user_id]), **kwargs)
    assert result.outcome == "no-op"
    assert len(rows(database, "customer_users")) == 1
    assert len(rows(database, "tenant_memberships")) == 1


@pytest.mark.parametrize("matches", [[], [str(uuid.uuid4()), str(uuid.uuid4())]])
def test_unknown_or_ambiguous_auth_user_makes_no_writes(database, matches):
    with pytest.raises(ProvisioningError):
        provision_customer("a@example.com", "tenant_a", "viewer", Resolver(matches),
                           connection_factory=factory(database))
    assert rows(database, "customer_users") == []
    assert rows(database, "tenant_memberships") == []


def test_invalid_provider_identity_is_not_replaced_with_random_uuid(database, monkeypatch):
    def forbidden():
        raise AssertionError("random UUID generation is forbidden")
    monkeypatch.setattr(uuid, "uuid4", forbidden)
    with pytest.raises(ProvisioningError, match="invalid identity"):
        provision_customer("a@example.com", "tenant_a", "viewer", Resolver(["not-a-uuid"]),
                           connection_factory=factory(database))
    assert rows(database, "customer_users") == []


@pytest.mark.parametrize("role", ["admin", "", "OWNERISH"])
def test_unknown_role_fails_before_lookup_or_writes(database, role):
    with pytest.raises(ProvisioningError, match="Role must be one of"):
        provision_customer("a@example.com", "tenant_a", role, Resolver([str(uuid.uuid4())]),
                           connection_factory=factory(database))
    assert rows(database, "customer_users") == []


def test_unknown_tenant_leaves_no_partial_user(database):
    with pytest.raises(ProvisioningError, match="Tenant missing was not found"):
        provision_customer("a@example.com", "missing", "viewer", Resolver([str(uuid.uuid4())]),
                           connection_factory=factory(database))
    assert rows(database, "customer_users") == []


@pytest.mark.parametrize("existing_role,status", [("manager", "active"), ("viewer", "suspended"), ("viewer", "revoked")])
def test_existing_role_or_status_conflict_fails_closed(database, existing_role, status):
    user_id = str(uuid.uuid4())
    with connect(database) as conn:
        conn.execute("INSERT INTO customer_users (user_id) VALUES (?)", (user_id,))
        conn.execute(
            "INSERT INTO tenant_memberships (tenant_id,user_id,role,status) VALUES (?,?,?,?)",
            ("tenant_a", user_id, existing_role, status),
        )
    with pytest.raises(ProvisioningError, match="Membership already exists"):
        provision_customer("a@example.com", "tenant_a", "viewer", Resolver([user_id]),
                           connection_factory=factory(database))
    assert rows(database, "tenant_memberships")[0]["role"] == existing_role
    assert rows(database, "tenant_memberships")[0]["status"] == status


def test_disabled_customer_user_conflicts(database):
    user_id = str(uuid.uuid4())
    with connect(database) as conn:
        conn.execute("INSERT INTO customer_users (user_id,status) VALUES (?,'disabled')", (user_id,))
    with pytest.raises(ProvisioningError, match="status disabled"):
        provision_customer("a@example.com", "tenant_a", "viewer", Resolver([user_id]),
                           connection_factory=factory(database))
    assert rows(database, "tenant_memberships") == []


def test_membership_insert_failure_rolls_back_customer_user(database):
    user_id = str(uuid.uuid4())
    with connect(database) as conn:
        conn.execute("CREATE TRIGGER reject_membership BEFORE INSERT ON tenant_memberships BEGIN SELECT RAISE(ABORT, 'no'); END")
    with pytest.raises(ProvisioningError, match="provisioning failed"):
        provision_customer("a@example.com", "tenant_a", "viewer", Resolver([user_id]),
                           connection_factory=factory(database))
    assert rows(database, "customer_users") == []
    assert rows(database, "tenant_memberships") == []


def test_cli_default_fails_closed_without_provider_lookup(database, capsys):
    code = main(["--email", "a@example.com", "--tenant-id", "tenant_a", "--role", "viewer"],
                connection_factory=factory(database))
    captured = capsys.readouterr()
    assert code == 1
    assert "identity lookup is not configured" in captured.err
    assert rows(database, "customer_users") == []


class AuthLookupConnection:
    def __init__(self, matches=None, error=None):
        self.matches = matches or []
        self.error = error
        self.closed = False
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        if self.error:
            raise self.error
        return self

    def fetchall(self):
        return [{"id": value} for value in self.matches]

    def close(self):
        self.closed = True


def test_database_auth_resolver_queries_auth_users_case_insensitively():
    user_id = str(uuid.uuid4())
    conn = AuthLookupConnection([user_id])
    result = DatabaseAuthIdentityResolver(lambda: conn).resolve("Customer@Example.com")
    assert result == [user_id]
    assert "FROM auth.users" in conn.query
    assert "lower(email) = lower(?)" in conn.query
    assert "LIMIT 2" in conn.query
    assert conn.params == ("Customer@Example.com",)
    assert conn.closed is True


def test_database_auth_resolver_wraps_database_failure_safely():
    import sqlite3

    conn = AuthLookupConnection(error=sqlite3.OperationalError("secret database detail"))
    with pytest.raises(ProvisioningError, match="identity lookup failed") as captured:
        DatabaseAuthIdentityResolver(lambda: conn).resolve("a@example.com")
    assert "secret database detail" not in str(captured.value)
    assert conn.closed is True


def test_cli_uses_database_auth_resolver_when_database_url_is_configured(
    database, capsys, monkeypatch
):
    user_id = str(uuid.uuid4())
    auth_conn = AuthLookupConnection([user_id])
    local_factory = factory(database)
    calls = iter([auth_conn, local_factory()])
    monkeypatch.setenv("DATABASE_URL", "postgresql://configured-but-not-printed")

    code = main(
        ["--email", "a@example.com", "--tenant-id", "tenant_a", "--role", "viewer"],
        connection_factory=lambda: next(calls),
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "Access provisioned" in captured.out
    assert "postgresql://" not in captured.out + captured.err
    monkeypatch.delenv("DATABASE_URL")
    assert rows(database, "customer_users")[0]["user_id"] == user_id


def test_cli_output_is_safe(database, capsys):
    secret = "never-print-this-secret"
    user_id = str(uuid.uuid4())
    code = main(["--email", "a@example.com", "--tenant-id", "tenant_a", "--role", "dispatcher"],
                resolver=Resolver([user_id]), connection_factory=factory(database))
    output = capsys.readouterr()
    assert code == 0
    assert "Access provisioned for a@example.com as dispatcher on tenant tenant_a" in output.out
    assert user_id not in output.out + output.err
    assert secret not in output.out + output.err


def test_provisioned_user_completes_auth_and_tenant_isolation_round_trip(database):
    user_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    with connect(database) as conn:
        conn.execute("INSERT INTO tenants (tenant_id) VALUES ('tenant_b')")

    result = provision_customer(
        "owner@example.com",
        "tenant_a",
        "owner",
        Resolver([user_id]),
        connection_factory=factory(database),
    )
    assert result.outcome == "created"

    identity = VerifiedIdentity(
        user_id=user_id,
        session_id=session_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    app = create_app(
        db_path=database,
        customer_identity_verifier=IdentityVerifier(identity),
        customer_allowed_origins={"https://dashboard.example"},
    )
    headers = {
        "Authorization": "Bearer provisioned-token",
        "X-Correlation-ID": str(uuid.uuid4()),
    }
    with TestClient(app) as client:
        assert client.post("/auth/session", headers=headers).status_code == 200
        assert client.get("/tenants/tenant_a/metrics", headers=headers).status_code == 200
        assert client.get("/tenants/tenant_b/metrics", headers=headers).status_code == 403

    with connect(database) as conn:
        events = [
            dict(row)
            for row in conn.execute(
                """
                SELECT tenant_id, action, outcome, reason_code
                FROM customer_audit_events
                ORDER BY tenant_id
                """
            ).fetchall()
        ]
    assert events == [
        {
            "tenant_id": "tenant_a",
            "action": "metrics.read",
            "outcome": "allowed",
            "reason_code": None,
        },
        {
            "tenant_id": "tenant_b",
            "action": "authorization.check",
            "outcome": "denied",
            "reason_code": "insufficient_membership",
        },
    ]
