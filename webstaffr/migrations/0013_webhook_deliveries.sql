CREATE TABLE webhook_deliveries (
    provider TEXT NOT NULL,
    event_key TEXT NOT NULL,
    tenant_id TEXT,
    event_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('processing', 'processed')),
    response_json TEXT,
    created_epoch INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    processed_at TEXT,
    PRIMARY KEY (provider, event_key)
);

CREATE INDEX idx_webhook_deliveries_created_at
    ON webhook_deliveries(created_epoch);

CREATE TABLE rate_limit_dimensions (
    dimension_type TEXT NOT NULL,
    dimension_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dimension_type, dimension_key, endpoint, window_start)
);
