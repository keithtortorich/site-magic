"""Focused smoke tests for the workflow graph execution-trace model."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from webstaffr.integrations.workflow_graph.client import (
    ExecutionNode,
    WorkflowGraphClient,
    WorkflowGraphError,
    VALID_NODE_TYPES,
    VALID_STATUSES,
    create_node,
    get_node,
    list_nodes,
    update_node_status,
)
from webstaffr.integrations.workflow_graph.mocks import MockWorkflowGraphClient
import sqlite3


def test_workflow_graph_exports() -> None:
    assert MockWorkflowGraphClient is not None
    assert WorkflowGraphClient is not None
    assert ExecutionNode is not None
    assert WorkflowGraphError is not None


def test_validation_rejects_bad_types() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with pytest.raises(ValueError):
        create_node(
            conn,
            tenant_id="tenant-1",
            workflow_instance_id="wf-1",
            node_id="node-1",
            type="bad_type",
            status="active",
        )
    with pytest.raises(ValueError):
        create_node(
            conn,
            tenant_id="tenant-1",
            workflow_instance_id="wf-1",
            node_id="node-1",
            type="campaign",
            status="bad_status",
        )


def test_memory_graph_round_trip_with_parent() -> None:
    client = MockWorkflowGraphClient()
    client.create_node(
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="root-1",
        type="intake",
        status="completed",
        payload_ref="intake/submission-1",
    )
    client.create_node(
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="campaign-1",
        type="campaign",
        status="active",
        payload_ref="campaigns/campaign-1.json",
        parent_node_id="root-1",
    )
    assert [node.node_id for node in client.list_nodes(tenant_id="tenant-1", workflow_instance_id="wf-1")] == [
        "root-1",
        "campaign-1",
    ]


def test_sqlite_execution_trace_round_trip() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        (ROOT / "webstaffr" / "migrations" / "0007_execution_nodes.sql").read_text()
    )
    conn.commit()

    create_node(
        conn,
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="root-1",
        type="intake",
        status="completed",
        payload_ref="intake/submission-1",
    )
    update_node_status(
        conn,
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="root-1",
        status="completed",
        completed_at="2026-07-24T00:00:00+00:00",
    )
    root = get_node(conn, tenant_id="tenant-1", workflow_instance_id="wf-1", node_id="root-1")
    assert root is not None
    assert root.status == "completed"
    assert root.completed_at == "2026-07-24T00:00:00+00:00"

    child = create_node(
        conn,
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="publish-1",
        type="publish_job",
        status="awaiting_approval",
        parent_node_id="root-1",
    )
    assert child.parent_node_id == "root-1"
    assert child.type == "publish_job"


def test_tenant_and_instance_scoping() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        (ROOT / "webstaffr" / "migrations" / "0007_execution_nodes.sql").read_text()
    )
    conn.commit()

    create_node(
        conn,
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="node-1",
        type="campaign",
        status="active",
    )
    create_node(
        conn,
        tenant_id="tenant-1",
        workflow_instance_id="wf-2",
        node_id="node-1",
        type="campaign",
        status="active",
    )
    conn.commit()

    wf1_nodes = list_nodes(conn, tenant_id="tenant-1", workflow_instance_id="wf-1")
    wf2_nodes = list_nodes(conn, tenant_id="tenant-1", workflow_instance_id="wf-2")
    assert [node.node_id for node in wf1_nodes] == ["node-1"]
    assert [node.node_id for node in wf2_nodes] == ["node-1"]


def test_status_updates_are_idempotent() -> None:
    client = MockWorkflowGraphClient()
    client.create_node(
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="node-1",
        type="publish_job",
        status="pending",
    )
    first = client.update_node_status(
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="node-1",
        status="active",
    )
    second = client.update_node_status(
        tenant_id="tenant-1",
        workflow_instance_id="wf-1",
        node_id="node-1",
        status="completed",
        completed_at="2026-07-24T00:00:00+00:00",
    )
    assert first.status == "active"
    assert second.status == "completed"
    assert second.completed_at == "2026-07-24T00:00:00+00:00"
