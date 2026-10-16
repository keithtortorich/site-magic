-- 0005_rate_limit_counters.sql
-- Fixed-window request counters for per-tenant, per-endpoint rate limiting
-- (webstaffr/rate_limit.py).
--
-- Postgres backend only — SQLite version lives at ../0004_rate_limit_counters.sql
-- (renumbered during the WebStaffr 4.0 rebuild; this Postgres-side file
-- keeps its original number since it's an append-only run-log against the
-- live database, not renumbered along with it) and is applied by
-- migrate() under SQLite. This file is for Supabase out-of-band migration
-- and must be applied directly to the live database.

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    tenant_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start INTEGER NOT NULL,  -- unix timestamp, floored to the window size
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, endpoint, window_start)
);
