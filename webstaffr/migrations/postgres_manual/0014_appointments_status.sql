-- Postgres migration: Adds a status column to appointments so payment
-- webhooks (Stripe) can record paid/payment_failed/refunded against a
-- specific tenant-scoped appointment. Defaults to 'pending' -- an
-- appointment exists before any payment event arrives for it.
--
-- Matches webstaffr/migrations/0012_appointments_status.sql (SQLite).
-- Postgres numbering is independent of SQLite numbering (see other files
-- in this directory) -- this repo's schema is managed out-of-band here,
-- applied manually to the live Supabase project.

ALTER TABLE appointments ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'pending';

CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
