"""Workflow graph models, persistence, and client surface.

Read-first bounded operations for execution trace nodes, using the same
raw-SQL shape as the intake/attribution/social_media repositories: an
already-open connection, `?` placeholders, and db.py's `_PGConnection`
handling Postgres param translation.

Consolidated during the WebStaffr 4.0 rebuild: this module previously
split into three layers over one table (client.py wrapping sync.py's
functions, plus a repository.py wrapping the same four operations a
second time with no caller other than tests). One layer is enough here
-- the module-level functions below are called directly by
WorkflowGraphClient's methods and by tests that want the persistence
layer in isolation.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class ExecutionNode:
    node_id: str
    tenant_id: str
    workflow_instance_id: str
    type: str
    status: str
    payload_ref: Optional[str]
    parent_node_id: Optional[str]
    created_at: str
    completed_at: Optional[str]
    failure_reason: Optional[str]


VALID_NODE_TYPES = frozenset(
    {"intake", "campaign", "post", "publish_job", "approval", "integration_event"}
)
VALID_STATUSES = frozenset(
    {"pending", "active", "awaiting_approval", "completed", "failed", "canceled"}
)


class WorkflowGraphError(RuntimeError):
    """Raised when workflow graph integration config or calls fail."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_json(value: Optional[str]) -> Any:
    return json.loads(value) if value is not None else None


def _validate_types(value: Optional[str], field: str, allowed: set[str]) -> None:
    if value is not None and value not in allowed:
        raise ValueError(f"node {field} must be one of {sorted(allowed)}, got {value!r}")


def create_node(
    conn: Any,
    *,
    tenant_id: str,
    workflow_instance_id: str,
    node_id: str,
    type: str,
    status: str,
    payload_ref: Optional[str] = None,
    parent_node_id: Optional[str] = None,
) -> ExecutionNode:
    _validate_types(type, "type", VALID_NODE_TYPES)
    _validate_types(status, "status", VALID_STATUSES)
    now = _now_iso()
    # execution_nodes.tenant_id carries a real FK to tenants(tenant_id)
    # (unlike social_media_mounts/social_media_intents, which deliberately
    # have none -- see the social_media migration's header comment).
    # Ensure the tenant row exists first, same pattern as
    # intake.py/booking.py, so a caller creating the very first node for a
    # tenant doesn't hit an IntegrityError just because no other write
    # path has touched `tenants` for this tenant_id yet.
    #
    # Guarded with a table-existence check rather than a bare INSERT:
    # this module's own test suite (test_workflow_graph.py) deliberately
    # applies only the execution_nodes migration to an isolated in-memory
    # connection to test the persistence layer in genuine isolation, with
    # no `tenants` table present at all -- a real, intentional testing
    # choice, not an oversight to route around by forcing every caller to
    # apply the full app's migrations. The real deployed app always runs
    # the full migration set (the tenants table is created first), so
    # this guard is a no-op there; it only matters for a connection that
    # was deliberately given a narrower schema.
    has_tenants_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tenants'"
    ).fetchone()
    if has_tenants_table:
        conn.execute("INSERT OR IGNORE INTO tenants (tenant_id) VALUES (?)", (tenant_id,))
    conn.execute(
        """
        INSERT INTO execution_nodes
            (node_id, tenant_id, workflow_instance_id, type, status,
             payload_ref, parent_node_id, created_at, completed_at, failure_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            node_id,
            tenant_id,
            workflow_instance_id,
            type,
            status,
            payload_ref,
            parent_node_id,
            now,
            None,
            None,
        ),
    )
    return ExecutionNode(
        node_id=node_id,
        tenant_id=tenant_id,
        workflow_instance_id=workflow_instance_id,
        type=type,
        status=status,
        payload_ref=payload_ref,
        parent_node_id=parent_node_id,
        created_at=now,
        completed_at=None,
        failure_reason=None,
    )


def get_node(
    conn: Any,
    *,
    tenant_id: str,
    workflow_instance_id: str,
    node_id: str,
) -> Optional[ExecutionNode]:
    row = conn.execute(
        """
        SELECT node_id, tenant_id, workflow_instance_id, type, status,
               payload_ref, parent_node_id, created_at, completed_at, failure_reason
        FROM execution_nodes
        WHERE tenant_id = ? AND workflow_instance_id = ? AND node_id = ?
        """,
        (tenant_id, workflow_instance_id, node_id),
    ).fetchone()
    if row is None:
        return None
    return ExecutionNode(
        node_id=row["node_id"],
        tenant_id=row["tenant_id"],
        workflow_instance_id=row["workflow_instance_id"],
        type=row["type"],
        status=row["status"],
        payload_ref=row["payload_ref"],
        parent_node_id=row["parent_node_id"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
        failure_reason=row["failure_reason"],
    )


def list_nodes(
    conn: Any,
    *,
    tenant_id: str,
    workflow_instance_id: str,
) -> list[ExecutionNode]:
    rows = conn.execute(
        """
        SELECT node_id, tenant_id, workflow_instance_id, type, status,
               payload_ref, parent_node_id, created_at, completed_at, failure_reason
        FROM execution_nodes
        WHERE tenant_id = ? AND workflow_instance_id = ?
        ORDER BY created_at
        """,
        (tenant_id, workflow_instance_id),
    ).fetchall()
    return [
        ExecutionNode(
            node_id=row["node_id"],
            tenant_id=row["tenant_id"],
            workflow_instance_id=row["workflow_instance_id"],
            type=row["type"],
            status=row["status"],
            payload_ref=row["payload_ref"],
            parent_node_id=row["parent_node_id"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            failure_reason=row["failure_reason"],
        )
        for row in rows
    ]


def update_node_status(
    conn: Any,
    *,
    tenant_id: str,
    workflow_instance_id: str,
    node_id: str,
    status: str,
    completed_at: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> Optional[ExecutionNode]:
    _validate_types(status, "status", VALID_STATUSES)
    conn.execute(
        """
        UPDATE execution_nodes
        SET status = ?, completed_at = ?, failure_reason = ?
        WHERE tenant_id = ? AND workflow_instance_id = ? AND node_id = ?
        """,
        (status, completed_at, failure_reason, tenant_id, workflow_instance_id, node_id),
    )
    return get_node(
        conn,
        tenant_id=tenant_id,
        workflow_instance_id=workflow_instance_id,
        node_id=node_id,
    )


class WorkflowGraphClient:
    """Thin wrapper around the module-level functions above so routers
    can swap this for an HTTP-backed client later without changing
    handler code.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def create_node(
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
        node_id: str,
        type: str,
        status: str,
        payload_ref: Optional[str] = None,
        parent_node_id: Optional[str] = None,
    ) -> ExecutionNode:
        return create_node(
            self._conn,
            tenant_id=tenant_id,
            workflow_instance_id=workflow_instance_id,
            node_id=node_id,
            type=type,
            status=status,
            payload_ref=payload_ref,
            parent_node_id=parent_node_id,
        )

    def get_node(
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
        node_id: str,
    ) -> Optional[ExecutionNode]:
        return get_node(
            self._conn,
            tenant_id=tenant_id,
            workflow_instance_id=workflow_instance_id,
            node_id=node_id,
        )

    def list_nodes(
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
    ) -> list[ExecutionNode]:
        return list_nodes(
            self._conn,
            tenant_id=tenant_id,
            workflow_instance_id=workflow_instance_id,
        )

    def update_node_status(
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
        node_id: str,
        status: str,
        completed_at: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Optional[ExecutionNode]:
        return update_node_status(
            self._conn,
            tenant_id=tenant_id,
            workflow_instance_id=workflow_instance_id,
            node_id=node_id,
            status=status,
            completed_at=completed_at,
            failure_reason=failure_reason,
        )
