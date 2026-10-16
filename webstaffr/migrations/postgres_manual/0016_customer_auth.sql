CREATE TABLE customer_users (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE tenant_memberships (
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES customer_users(user_id) ON DELETE CASCADE,
    role TEXT NOT NULL
        CHECK (role IN ('owner', 'manager', 'dispatcher', 'viewer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'revoked')),
    created_by UUID REFERENCES customer_users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX idx_tenant_memberships_user
    ON tenant_memberships(user_id, status);

CREATE TABLE customer_sessions (
    session_id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES customer_users(user_id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_customer_sessions_user
    ON customer_sessions(user_id, revoked_at);

CREATE TABLE customer_audit_events (
    audit_id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    correlation_id UUID NOT NULL,
    user_id UUID REFERENCES customer_users(user_id) ON DELETE SET NULL,
    session_id UUID,
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

ALTER TABLE customer_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_audit_events ENABLE ROW LEVEL SECURITY;

-- Intentionally no Data API policies. The FastAPI backend uses its trusted
-- direct Postgres connection; anon/authenticated Data API access stays denied.
