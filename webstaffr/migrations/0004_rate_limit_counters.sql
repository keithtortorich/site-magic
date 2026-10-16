-- 0004_rate_limit_counters.sql
-- Fixed-window request counters for per-tenant, per-endpoint rate limiting
-- (webstaffr/rate_limit.py): /chat and /webhooks/ghl need a ceiling since
-- GROK_API_KEY is live in production -- an unauthenticated caller could
-- otherwise run up real, billed xAI usage with no limit.
--
-- Deliberately not tenant-scoped via a foreign key to tenants(tenant_id)
-- like every other table in this schema: rate limiting must work even
-- against a guessed/never-registered tenant_id (that's exactly the attack
-- this closes), so an FK constraint that could reject the insert would
-- defeat the purpose. This table is a pure counter/log, not a domain
-- record.

CREATE TABLE IF NOT EXISTS rate_limit_counters (
    tenant_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start INTEGER NOT NULL,  -- unix timestamp, floored to the window size
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, endpoint, window_start)
);
