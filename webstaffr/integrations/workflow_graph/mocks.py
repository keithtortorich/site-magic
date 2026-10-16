"""Workflow graph mock for offline tests and local development."""
from __future__ import annotations

from typing import Any, Optional

from .client import ExecutionNode


class MockWorkflowGraphClient:
    """In-memory stand-in for WorkflowGraphClient."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, tuple, dict]] = []

    def _key(self, tenant_id: str, workflow_instance_id: str, node_id: str) -> str:
        return f"{tenant_id}||{workflow_instance_id}||{node_id}"

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
        now = "1970-01-01T00:00:00+00:00"
        record = {
            "tenant_id": tenant_id,
            "workflow_instance_id": workflow_instance_id,
            "node_id": node_id,
            "type": type,
            "status": status,
            "payload_ref": payload_ref,
            "parent_node_id": parent_node_id,
            "created_at": now,
            "completed_at": None,
            "failure_reason": None,
        }
        self._nodes[self._key(tenant_id, workflow_instance_id, node_id)] = record
        self.calls.append(
            (
                "create_node",
                (tenant_id, workflow_instance_id, node_id, type, status),
                {"payload_ref": payload_ref, "parent_node_id": parent_node_id},
            )
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
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
        node_id: str,
    ) -> Optional[ExecutionNode]:
        record = self._nodes.get(self._key(tenant_id, workflow_instance_id, node_id))
        self.calls.append(("get_node", (tenant_id, workflow_instance_id, node_id), {}))
        if record is None:
            return None
        return ExecutionNode(
            node_id=record["node_id"],
            tenant_id=record["tenant_id"],
            workflow_instance_id=record["workflow_instance_id"],
            type=record["type"],
            status=record["status"],
            payload_ref=record["payload_ref"],
            parent_node_id=record["parent_node_id"],
            created_at=record["created_at"],
            completed_at=record["completed_at"],
            failure_reason=record["failure_reason"],
        )

    def list_nodes(
        self,
        *,
        tenant_id: str,
        workflow_instance_id: str,
    ) -> list[ExecutionNode]:
        results = []
        for record in self._nodes.values():
            if record["tenant_id"] != tenant_id:
                continue
            if record["workflow_instance_id"] != workflow_instance_id:
                continue
            results.append(
                ExecutionNode(
                    node_id=record["node_id"],
                    tenant_id=record["tenant_id"],
                    workflow_instance_id=record["workflow_instance_id"],
                    type=record["type"],
                    status=record["status"],
                    payload_ref=record["payload_ref"],
                    parent_node_id=record["parent_node_id"],
                    created_at=record["created_at"],
                    completed_at=record["completed_at"],
                    failure_reason=record["failure_reason"],
                )
            )
        self.calls.append(("list_nodes", (tenant_id, workflow_instance_id), {}))
        results.sort(key=lambda node: node.created_at)
        return results

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
        key = self._key(tenant_id, workflow_instance_id, node_id)
        record = self._nodes.get(key)
        if record is None:
            return None
        record["status"] = status
        record["completed_at"] = completed_at
        record["failure_reason"] = failure_reason
        updated = ExecutionNode(
            node_id=record["node_id"],
            tenant_id=record["tenant_id"],
            workflow_instance_id=record["workflow_instance_id"],
            type=record["type"],
            status=record["status"],
            payload_ref=record["payload_ref"],
            parent_node_id=record["parent_node_id"],
            created_at=record["created_at"],
            completed_at=completed_at,
            failure_reason=failure_reason,
        )
        self.calls.append(
            ("update_node_status", (tenant_id, workflow_instance_id, node_id, status), {}),
        )
        return updated
