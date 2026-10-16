-- 0002_custom_domains.sql
-- Add custom_domain column to tenants table for phase 2 custom domain support.
-- Allows tenants to serve their sites at a custom domain (e.g., desertcooling.com)
-- instead of the default /sites/{tenant_id}/web path.

ALTER TABLE tenants
ADD COLUMN custom_domain TEXT NULL UNIQUE;

-- Index for efficient Host header → tenant_id lookup in middleware.
CREATE INDEX IF NOT EXISTS idx_tenants_custom_domain ON tenants(custom_domain);
