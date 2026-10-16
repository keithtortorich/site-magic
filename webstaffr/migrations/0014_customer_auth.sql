CREATE TABLE customer_users (
    user_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE tenant_memberships (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES customer_users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL
        CHECK (role IN ('owner', 'manager', 'dispatcher', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    created_by TEXT REFERENCES customer_users(user_id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX idx_tenant_memberships_user
    ON tenant_memberships(user_id, status);

CREATE TABLE customer_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES customer_users(user_id) ON DELETE CASCADE,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_customer_sessions_user
    ON customer_sessions(user_id, revoked_at);

CREATE TABLE customer_audit_events (
    audit_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    correlation_id TEXT NOT NULL,
    user_id TEXT REFERENCES customer_users(user_id) ON DELETE SET NULL,
    session_id TEXT,
    tenant_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('allowed', 'denied', 'failed')),
    reason_code TEXT,
    request_method TEXT NOT NULL,
    request_path TEXT NOT NULL
);

CREATE INDEX idx_customer_audit_tenant_time
    ON customer_audit_events(tenant_id, occurred_at);
