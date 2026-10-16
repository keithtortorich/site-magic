CREATE TABLE public.site_magic_revision_builds (
    revision_id UUID PRIMARY KEY REFERENCES public.site_magic_revisions(revision_id) ON DELETE RESTRICT,
    build_id UUID NOT NULL UNIQUE REFERENCES public.site_magic_build_requests(build_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    scope_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_magic_revision_builds_tenant_time
    ON public.site_magic_revision_builds(tenant_id, created_at DESC);

ALTER TABLE public.site_magic_revision_builds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.site_magic_revision_builds FROM anon, authenticated;

CREATE TRIGGER site_magic_revision_builds_immutable_update
BEFORE UPDATE ON public.site_magic_revision_builds
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();

CREATE TRIGGER site_magic_revision_builds_immutable_delete
BEFORE DELETE ON public.site_magic_revision_builds
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();
