-- 0008_review_requests.sql
-- Review requests sent to customers after job completion (Rita worker).
-- Tracks when we request reviews and delivery method.

CREATE TABLE IF NOT EXISTS review_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    ghl_job_id TEXT,  -- appointment/event ID in GHL for cross-referencing
    contact_id TEXT NOT NULL,  -- GHL contact ID
    contact_name TEXT,  -- customer name, used in templates
    contact_phone TEXT,  -- SMS destination if available
    contact_email TEXT,  -- email destination if available
    review_source TEXT,  -- "google", "yelp", "native", etc.; determines platform
    request_method TEXT NOT NULL,  -- "sms", "email", "both"
    requested_at TEXT NOT NULL,  -- ISO 8601 timestamp
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, responded, failed
    ghl_synced INTEGER NOT NULL DEFAULT 0,  -- 0/1: whether we logged to GHL
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_requests_tenant
    ON review_requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_contact
    ON review_requests(contact_id);
CREATE INDEX IF NOT EXISTS idx_review_requests_status
    ON review_requests(status);
