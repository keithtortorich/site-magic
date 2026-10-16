-- 0002_custom_domains.sql
-- Add custom_domain column to tenants table for phase 2 custom domain support.
-- Allows tenants to serve their sites at a custom domain (e.g., desertcooling.com)
-- instead of the default /sites/{tenant_id}/web path.

ALTER TABLE tenants
ADD COLUMN custom_domain TEXT NULL;

-- Index for efficient Host header → tenant_id lookup in middleware.
CREATE INDEX IF NOT EXISTS idx_tenants_custom_domain ON tenants(custom_domain);

-- Note: UNIQUE constraint on custom_domain is enforced in application logic
-- rather than at the database level, since SQLite doesn't support adding a
-- UNIQUE constraint to an existing table with NULLs. The application ensures
-- only one tenant per custom_domain value via resolve_tenant_from_host().
