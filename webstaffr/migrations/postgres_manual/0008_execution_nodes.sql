-- 0008_execution_nodes.sql
-- Postgres backend only — SQLite version lives at ../0007_execution_nodes.sql
-- and is applied by migrate() under SQLite. This file is for Supabase
-- out-of-band migration and must be applied directly to the live database
-- (same convention as 0004/0005/0006/0007 in this directory).
--
-- NOT APPLIED YET as of this commit -- requires explicit founder approval
-- per CLAUDE.md's Self-Approval Scope (DB schema changes against a live
-- production system). Same gap as 0007_social_media.sql: execution_nodes
-- has existed as application code (migration 0008 in the prior repo, now
-- ../0007_execution_nodes.sql) with no Postgres DDL and no RLS. Apply via
-- the Supabase MCP's apply_migration once approved, then re-run
-- get_advisors to confirm RLS default-deny covers this new table too.

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

-- Follow-up, same session as applying the above: enable RLS default-deny,
-- consistent with 0004's policy on every other table. No CREATE POLICY
-- statements -- intentional default-deny, same reasoning as 0004: nothing
-- queries this table via PostgREST/anon-key today.

ALTER TABLE execution_nodes ENABLE ROW LEVEL SECURITY;
