-- 0021_rate_limit_dimensions_rls.sql
-- 0005_rate_limit_dimensions.sql never enabled RLS -- table shipped fully
-- exposed to the anon/authenticated Supabase client roles (flagged by
-- Supabase's security advisor 2026-08-10). Backend hits this table only
-- via service-role raw SQL (webstaffr/rate_limit.py through db.py), which
-- bypasses RLS regardless, so default-deny costs zero functional risk --
-- same pattern as 0004_enable_rls_default_deny.sql applied everywhere else.

BEGIN;

ALTER TABLE public.rate_limit_dimensions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.rate_limit_dimensions FROM anon, authenticated;

COMMIT;
