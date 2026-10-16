BEGIN;

CREATE TABLE public.site_magic_jobs (
    job_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL CHECK (source_type IN ('intake', 'url', 'repository')),
    source_payload_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'queued', 'ingesting', 'directing', 'building', 'evaluating',
        'remediating', 'final_review', 'ready_for_review', 'published',
        'failed', 'quarantined'
    )),
    remediation_rounds INTEGER NOT NULL DEFAULT 0 CHECK (remediation_rounds BETWEEN 0 AND 2),
    rebuild_count INTEGER NOT NULL DEFAULT 0 CHECK (rebuild_count BETWEEN 0 AND 1),
    quality_summary_json JSONB,
    final_build_id UUID,
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_site_magic_jobs_tenant_created
    ON public.site_magic_jobs(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_builds (
    build_id UUID PRIMARY KEY,
    job_id UUID NOT NULL UNIQUE REFERENCES public.site_magic_jobs(job_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    artifact_manifest_json JSONB NOT NULL,
    preview_locator TEXT NOT NULL,
    published_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.site_magic_jobs
    ADD CONSTRAINT site_magic_jobs_final_build_fk
    FOREIGN KEY (final_build_id) REFERENCES public.site_magic_builds(build_id) ON DELETE RESTRICT;

CREATE INDEX idx_site_magic_builds_tenant_created
    ON public.site_magic_builds(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_active_builds (
    tenant_id TEXT PRIMARY KEY REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    build_id UUID NOT NULL REFERENCES public.site_magic_builds(build_id) ON DELETE RESTRICT,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.site_magic_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_builds ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_active_builds ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.site_magic_jobs FROM anon, authenticated;
REVOKE ALL ON TABLE public.site_magic_builds FROM anon, authenticated;
REVOKE ALL ON TABLE public.site_magic_active_builds FROM anon, authenticated;

COMMIT;
