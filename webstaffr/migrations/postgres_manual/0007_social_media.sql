-- 0007_social_media.sql
-- Postgres backend only — SQLite version lives at ../0006_social_media.sql
-- and is applied by migrate() under SQLite. This file is for Supabase
-- out-of-band migration and must be applied directly to the live database
-- (same convention as 0004/0005/0006 in this directory).
--
-- NOT APPLIED YET as of this commit -- requires explicit founder approval
-- per CLAUDE.md's Self-Approval Scope (DB schema changes against a live
-- production system). This closes a real gap identified during the
-- WebStaffr 4.0 rebuild: social_media_mounts/social_media_intents have
-- existed as application code (migration 0007 in the prior repo, now
-- ../0006_social_media.sql) since before this repo's Postgres backend was
-- ever exercised against them -- there was no Postgres DDL for these two
-- tables at all, and no RLS. Apply via the Supabase MCP's apply_migration
-- once approved, then re-run get_advisors to confirm RLS default-deny
-- covers these two new tables too.

CREATE TABLE IF NOT EXISTS social_media_mounts (
    mount_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    social_tenant_id TEXT NOT NULL,
    platforms TEXT NOT NULL DEFAULT '[]',
    default_brand_id TEXT,
    mode TEXT NOT NULL DEFAULT 'agent_managed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_media_intents (
    intent_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mount_id INTEGER NOT NULL,
    campaign_intent TEXT NOT NULL,
    post_draft TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_review',
    workflow_instance_id TEXT,
    approval_url TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_social_media_mounts_tenant
    ON social_media_mounts(tenant_id);

CREATE INDEX IF NOT EXISTS idx_social_media_intents_mount
    ON social_media_intents(mount_id);

-- Follow-up, same session as applying the above: enable RLS default-deny
-- on both new tables, consistent with 0004's policy on every other table.
-- No CREATE POLICY statements -- intentional default-deny, same reasoning
-- as 0004: nothing queries these tables via PostgREST/anon-key today.

ALTER TABLE social_media_mounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE social_media_intents ENABLE ROW LEVEL SECURITY;
