-- 0012_appointments_status.sql
-- Adds a status column to appointments so payment webhooks (Stripe) can
-- record paid/payment_failed/refunded against a specific tenant-scoped
-- appointment. Defaults to 'pending' -- an appointment exists before any
-- payment event arrives for it.

ALTER TABLE appointments ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_appointments_status
    ON appointments(status);
