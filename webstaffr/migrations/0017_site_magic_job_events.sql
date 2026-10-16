-- Idempotency ledger for Site Magic transition callbacks. event_sequence is
-- server-authoritative (site_magic_jobs.current_event_sequence, incremented
-- in the same statement as the status UPDATE) -- callers never supply it,
-- so there is no "client sent a stale sequence number" failure class to
-- guard against. A caller retries by resending the same event_id; the
-- ledger's (job_id, event_id) uniqueness is what makes that a no-op replay
-- instead of a double-apply.
ALTER TABLE site_magic_jobs ADD COLUMN current_event_sequence INTEGER NOT NULL DEFAULT 0;

CREATE TABLE site_magic_job_events (
    event_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    prior_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    payload_json TEXT,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (job_id, event_id),
    FOREIGN KEY (job_id) REFERENCES site_magic_jobs(job_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX idx_site_magic_job_events_sequence
    ON site_magic_job_events(job_id, event_sequence);

CREATE INDEX idx_site_magic_job_events_tenant
    ON site_magic_job_events(tenant_id, created_at DESC);
