-- Customer-auth Data API boundary.
--
-- The FastAPI backend continues to provision and authorize through its
-- trusted direct Postgres connection. Browser-facing Supabase clients may
-- read only the authenticated caller's own identity and membership rows.
-- They cannot create, change, or revoke users, memberships, roles, or status.

ALTER TABLE public.customer_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_memberships ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.customer_users FROM anon, authenticated;
REVOKE ALL ON TABLE public.tenant_memberships FROM anon, authenticated;
GRANT SELECT ON TABLE public.customer_users TO authenticated;
GRANT SELECT ON TABLE public.tenant_memberships TO authenticated;

DROP POLICY IF EXISTS customer_users_select_self ON public.customer_users;
CREATE POLICY customer_users_select_self
    ON public.customer_users
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

DROP POLICY IF EXISTS tenant_memberships_select_self ON public.tenant_memberships;
CREATE POLICY tenant_memberships_select_self
    ON public.tenant_memberships
    FOR SELECT
    TO authenticated
    USING ((SELECT auth.uid()) = user_id);

-- No INSERT, UPDATE, or DELETE policies are intentional. Provisioning and
-- role changes are privileged backend operations, never customer Data API
-- operations. RLS therefore remains default-deny for every mutation.
