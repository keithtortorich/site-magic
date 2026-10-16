-- 0009_review_responses.sql
-- Incoming reviews from external platforms and our drafted responses (Rita worker).
-- Tracks reviews received and our drafted/approved/posted responses.

CREATE TABLE IF NOT EXISTS review_responses (
    response_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    request_id INTEGER REFERENCES review_requests(request_id),
    review_source TEXT NOT NULL,  -- "google", "yelp", etc.
    external_review_id TEXT,  -- platform's own review ID
    review_rating INTEGER,  -- 1-5 stars
    review_text TEXT,  -- full review body
    reviewer_name TEXT,  -- customer name from platform
    received_at TEXT,  -- ISO 8601, from platform if available
    response_status TEXT NOT NULL DEFAULT 'pending_draft',
    -- pending_draft: awaiting founder review
    -- approved: founder approved, ready to post
    -- posted: response sent to review platform
    -- failed: posting failed
    response_text TEXT,  -- our drafted response
    response_approved_at TEXT,  -- ISO 8601, when founder approved
    response_posted_at TEXT,  -- ISO 8601, when posted to platform
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_responses_tenant
    ON review_responses(tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_request
    ON review_responses(request_id);
CREATE INDEX IF NOT EXISTS idx_review_responses_status
    ON review_responses(response_status);
