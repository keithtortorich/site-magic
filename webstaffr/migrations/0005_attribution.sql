-- 0005_attribution.sql
-- Per-tenant call attribution: tracking numbers and call-lifecycle events.
-- Unblocks the "pays for itself" guarantee conversation by giving each
-- tenant a persistent tracking identifier and a record of what happened
-- on calls routed through it.
--
-- Design note: this does NOT provision a real phone number (no Twilio/
-- Retell number-buying integration exists yet). tracking_number starts as
-- a server-generated logical identifier at intake time (see
-- webstaffr/attribution.py's get_or_create()) and can be updated later,
-- in place, once a real DID is provisioned for that tenant -- avoids a
-- second migration/schema change purely to add a "real number" concept.
--
-- One tracking_number per tenant (PRIMARY KEY on tenant_id) -- matches
-- this MVP's one-Retell-agent-per-tenant assumption already documented in
-- retell_router.py. Revisit if a tenant ever needs multiple numbers
-- (e.g. per campaign) -- not needed for the current soft-launch scope.

CREATE TABLE IF NOT EXISTS tracking_numbers (
    tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
    tracking_number TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

-- call_events is an append-only log, not a mutable call record: each
-- lifecycle moment (received, ended, appointment booked) is its own row,
-- linked by call_id where the source system provides one. This keeps
-- ingestion a plain INSERT with no read-modify-write race, and lets the
-- metrics/dashboard layer (attribution.py) aggregate however it needs to
-- without the schema having to anticipate every future report shape.
CREATE TABLE IF NOT EXISTS call_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    tracking_number TEXT,
    call_id TEXT,                  -- external call id (e.g. Retell's), for correlating rows about the same call
    event_type TEXT NOT NULL,      -- 'call_received' | 'call_ended' | 'appointment_booked'
    duration_seconds INTEGER,
    outcome TEXT,                  -- e.g. 'answered' | 'voicemail' | 'booked' | 'escalated'
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_events_tenant
    ON call_events(tenant_id);

CREATE INDEX IF NOT EXISTS idx_call_events_tenant_created
    ON call_events(tenant_id, created_at);
