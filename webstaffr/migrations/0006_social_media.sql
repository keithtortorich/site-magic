-- 0006_social_media.sql
-- Social media marketing integration bridge.
--
-- Adds two tables:
--   social_media_mounts      - maps a WS3.3 tenant to an SMM org/social_tenant_id
--   social_media_intents     - campaign/post intent requests awaiting review/approval
--
-- Design matches existing conventions:
-- - SQLite dialect, migrated via db.migrate() in dev/tests
-- - tenant_id validated through Tenant(...) at the router layer, not via FK here
-- - JSON payload columns avoid schema churn for intent content

CREATE TABLE IF NOT EXISTS social_media_mounts (
    mount_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    social_tenant_id TEXT NOT NULL,
    platforms TEXT NOT NULL DEFAULT '[]',
    default_brand_id TEXT,
    mode TEXT NOT NULL DEFAULT 'agent_managed',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS social_media_intents (
    intent_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
