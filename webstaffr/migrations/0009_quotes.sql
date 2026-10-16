-- Quotes table: tracks generated quotes, their status, and links to appointments
-- Used by Sam (Sales Consultant AI worker) to track quote generation, acceptance, and conversion to bookings.

CREATE TABLE IF NOT EXISTS quotes (
  id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  contact_id TEXT NOT NULL,
  contact_name TEXT,
  contact_email TEXT,
  service_scope TEXT NOT NULL,
  industry TEXT,
  estimated_range_low REAL NOT NULL,
  estimated_range_high REAL NOT NULL,
  caveat TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  email_template TEXT,
  created_at TEXT NOT NULL,
  sent_at TEXT,
  accepted_at TEXT,
  declined_at TEXT,
  declined_reason TEXT,
  appointment_id INTEGER,
  FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id),
  FOREIGN KEY(appointment_id) REFERENCES appointments(appointment_id)
);

CREATE INDEX IF NOT EXISTS idx_quotes_tenant_status ON quotes(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_quotes_contact ON quotes(tenant_id, contact_id);
CREATE INDEX IF NOT EXISTS idx_quotes_created ON quotes(tenant_id, created_at DESC);
