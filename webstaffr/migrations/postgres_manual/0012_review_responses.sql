-- Postgres migration: Review responses table for Rita (Reputation Manager AI worker)
-- Tracks reviews received from external platforms and our drafted/approved/posted responses
-- RLS: tenant_id column; default-deny policy (no policies = read-only to app, safe default)

CREATE TABLE IF NOT EXISTS review_responses (
    response_id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    request_id INTEGER REFERENCES public.review_requests(request_id) ON DELETE SET NULL,
    review_source TEXT NOT NULL,
    external_review_id TEXT,
    review_rating INTEGER,
    review_text TEXT,
    reviewer_name TEXT,
    received_at TEXT,
    response_status TEXT NOT NULL DEFAULT 'pending_draft',
    response_text TEXT,
    response_approved_at TEXT,
    response_posted_at TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_responses_tenant ON review_responses(tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_request ON review_responses(request_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_status ON review_responses(response_status);

-- RLS: enable row-level security
ALTER TABLE review_responses ENABLE ROW LEVEL SECURITY;

-- Default-deny: no policies = reads blocked by default (fail-safe posture)
-- App layer adds policies via RLS context when deployed
