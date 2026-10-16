-- 0001_tenants.sql
-- The one table every other table references: tenant_id is public, never
-- a credential, and every query in this codebase is scoped by it.

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY
);
