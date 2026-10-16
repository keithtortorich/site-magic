CREATE TABLE webhook_deliveries (
    provider TEXT NOT NULL,
    event_key TEXT NOT NULL,
    tenant_id TEXT,
    event_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'processed')),
    response_json TEXT,
    created_epoch BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    PRIMARY KEY (provider, event_key)
);

CREATE INDEX idx_webhook_deliveries_created_at
    ON webhook_deliveries(created_epoch);

ALTER TABLE webhook_deliveries ENABLE ROW LEVEL SECURITY;

CREATE TABLE rate_limit_dimensions (
    dimension_type TEXT NOT NULL,
    dimension_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start BIGINT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dimension_type, dimension_key, endpoint, window_start)
);

ALTER TABLE rate_limit_dimensions ENABLE ROW LEVEL SECURITY;
