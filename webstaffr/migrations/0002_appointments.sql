-- 0002_appointments.sql
-- Appointments booked by the Angel worker. Tenant-scoped like everything else.

CREATE TABLE IF NOT EXISTS appointments (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
    contact_name TEXT NOT NULL,
    contact_phone TEXT,
    contact_email TEXT,
    starts_at TEXT NOT NULL,   -- ISO 8601 timestamp
    notes TEXT,
    source TEXT NOT NULL DEFAULT 'angel',  -- how the appointment was created
    ghl_synced INTEGER NOT NULL DEFAULT 0, -- 0/1: whether GHL sync has been attempted/succeeded
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_appointments_tenant
    ON appointments(tenant_id);
