-- Postgres migration: Review requests table for Rita (Reputation Manager AI worker)
-- Tracks when we request reviews and delivery method after job completion
-- RLS: tenant_id column; default-deny policy (no policies = read-only to app, safe default)

CREATE TABLE IF NOT EXISTS review_requests (
    request_id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    ghl_job_id TEXT,
    contact_id TEXT NOT NULL,
    contact_name TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    review_source TEXT,
    request_method TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    ghl_synced INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_requests_tenant ON review_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_contact ON review_requests(contact_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_status ON review_requests(status);

-- RLS: enable row-level security
ALTER TABLE review_requests ENABLE ROW LEVEL SECURITY;

-- Default-deny: no policies = reads blocked by default (fail-safe posture)
-- App layer adds policies via RLS context when deployed
