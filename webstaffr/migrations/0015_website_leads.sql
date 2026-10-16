CREATE TABLE website_leads (
    lead_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    message TEXT NOT NULL,
    service TEXT,
    source_path TEXT,
    ghl_contact_id TEXT,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'forwarded', 'forward_failed')),
    forward_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (forward_attempts >= 0),
    last_forward_error_code TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_website_leads_tenant_created
    ON website_leads(tenant_id, created_at);
