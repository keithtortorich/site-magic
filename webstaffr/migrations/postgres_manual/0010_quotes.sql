-- Postgres migration: Quotes table for Sam (Sales Consultant AI worker)
-- Tracks generated quotes, their status, and links to appointments
-- RLS: tenant_id column; default-deny policy (no policies = read-only to app, safe default)

CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
  contact_id TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT,
  service_scope TEXT NOT NULL,
  industry TEXT,
  estimated_range_low NUMERIC NOT NULL,
  estimated_range_high NUMERIC NOT NULL,
  caveat TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  email_template TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  accepted_at TEXT,
  declined_at TEXT,
  declined_reason TEXT,
  appointment_id INTEGER REFERENCES public.appointments(appointment_id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_quotes_tenant_status ON quotes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_quotes_contact ON quotes(tenant_id, contact_id);
CREATE INDEX IF NOT EXISTS idx_quotes_created ON quotes(tenant_id, created_at DESC);

-- RLS: enable row-level security
ALTER TABLE quotes ENABLE ROW LEVEL SECURITY;

-- Default-deny: no policies = reads blocked by default (fail-safe posture)
-- App layer adds policies via RLS context when deployed
