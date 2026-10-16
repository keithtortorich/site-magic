-- 0022_widen_remediation_rounds_check.sql
-- MAX_REMEDIATION_ROUNDS (site_maker_engine.ts) went from 2 to 4 on
-- 2026-08-14, but this table's CHECK constraint -- a third, independent
-- copy of the same limit, alongside the TS constant and
-- site_magic_router.py's Pydantic Field(le=2) -- still capped at 2. The
-- worker's third remediation round 503'd the state transition instead of
-- remediating. Applied live via Supabase MCP the same day; this file is
-- the tracked parity copy per this repo's postgres_manual convention.

BEGIN;

ALTER TABLE public.site_magic_jobs DROP CONSTRAINT site_magic_jobs_remediation_rounds_check;
ALTER TABLE public.site_magic_jobs ADD CONSTRAINT site_magic_jobs_remediation_rounds_check
    CHECK (remediation_rounds >= 0 AND remediation_rounds <= 4);

COMMIT;
