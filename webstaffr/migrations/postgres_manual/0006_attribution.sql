-- 0006_attribution.sql
-- Postgres backend only — SQLite version lives at ../0005_attribution.sql
-- (renumbered during the WebStaffr 4.0 rebuild; this Postgres-side file
-- keeps its original number since it's an append-only run-log against the
-- live database, not renumbered along with it) and is applied by
-- migrate() under SQLite. This file is for Supabase out-of-band migration
-- and must be applied directly to the live database (same convention as
-- 0004/0005 in this directory).
--
-- NOT APPLIED YET as of this commit -- requires explicit founder approval
-- per CLAUDE.md's Self-Approval Scope (DB schema changes against a live
-- production system). Apply via the Supabase MCP's apply_migration once
-- approved, then re-run get_advisors to confirm RLS default-deny still
-- covers these two new tables (it should -- 0004's ALTER DEFAULT
-- PRIVILEGES doesn't exist in this repo; RLS was enabled per-table, so
-- these two new tables need their own ENABLE ROW LEVEL SECURITY once
-- created -- see the note at the bottom of this file).

CREATE TABLE IF NOT EXISTS tracking_numbers (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
    tracking_number TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS call_events (
    event_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    tracking_number TEXT,
    call_id TEXT,
    event_type TEXT NOT NULL,
    duration_seconds INTEGER,
    outcome TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_events_tenant
    ON call_events(tenant_id);

CREATE INDEX IF NOT EXISTS idx_call_events_tenant_created
    ON call_events(tenant_id, created_at);

-- Follow-up, same session as applying the above: enable RLS default-deny
-- on both new tables, consistent with 0004's policy on every other table:
--
-- ALTER TABLE tracking_numbers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE call_events ENABLE ROW LEVEL SECURITY;
