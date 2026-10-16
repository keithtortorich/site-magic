-- 0007_execution_nodes.sql
-- Execution trace graph for campaign, post, publish, and approval events --
-- execution-trace nodes recording what happened, not workflow-definition
-- nodes describing what could happen.
--
-- Rules:
-- - Tenant-scoped first: every query filters by tenant_id.
-- - Nodes are immutable once created; status/completed_at/failure_reason
--   updates happen via new child rows or updates to the same node_id,
--   following the design's idempotency rule.
-- - parent_node_id creates a tree/forest per workflow_instance_id without
--   a separate edge table.

CREATE TABLE IF NOT EXISTS execution_nodes (
    node_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    workflow_instance_id TEXT NOT NULL,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_ref TEXT,
    parent_node_id TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    failure_reason TEXT,
    PRIMARY KEY (tenant_id, workflow_instance_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_nodes_tenant
    ON execution_nodes(tenant_id);

CREATE INDEX IF NOT EXISTS idx_execution_nodes_tenant_instance
    ON execution_nodes(tenant_id, workflow_instance_id);

CREATE INDEX IF NOT EXISTS idx_execution_nodes_tenant_created
    ON execution_nodes(tenant_id, created_at);
