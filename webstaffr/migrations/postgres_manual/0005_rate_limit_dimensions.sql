-- 0005_rate_limit_dimensions.sql
-- Fixed-window request counters for per-endpoint rate limiting by dimension
-- (webstaffr/rate_limit.py): /intake and other public endpoints need a
-- ceiling since backend APIs are billed or have rate limits. Supports
-- multiple dimension types (ip, tenant_id, etc.) with independent counters.
--
-- Deliberately not tenant-scoped via a foreign key to tenants(tenant_id):
-- rate limiting must work even against a guessed/never-registered tenant_id
-- (that's exactly the attack this closes), so an FK constraint would defeat
-- the purpose. This table is a pure counter/log, not a domain record.

CREATE TABLE IF NOT EXISTS rate_limit_dimensions (
    dimension_type TEXT NOT NULL,
    dimension_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start INTEGER NOT NULL,  -- unix timestamp, floored to the window size
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dimension_type, dimension_key, endpoint, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_dimensions_endpoint_window
    ON rate_limit_dimensions (endpoint, window_start);
