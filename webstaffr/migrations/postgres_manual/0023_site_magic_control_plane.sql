CREATE TABLE public.site_magic_facts (
    fact_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value_json JSONB NOT NULL,
    source_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verified', 'unverified', 'rejected', 'superseded')),
    verified_by UUID REFERENCES public.customer_users(user_id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_magic_facts_tenant_status
    ON public.site_magic_facts(tenant_id, status, created_at DESC);

CREATE TABLE public.site_magic_plans (
    plan_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version > 0),
    status TEXT NOT NULL CHECK (status IN ('draft', 'proposed', 'approved', 'superseded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_magic_plans_tenant_updated
    ON public.site_magic_plans(tenant_id, updated_at DESC);

CREATE TABLE public.site_magic_plan_versions (
    plan_version_id UUID PRIMARY KEY,
    plan_id UUID NOT NULL REFERENCES public.site_magic_plans(plan_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    version INTEGER NOT NULL CHECK (version > 0),
    content_json JSONB NOT NULL,
    fact_snapshot_json JSONB NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'proposed', 'approved', 'superseded')),
    created_by UUID REFERENCES public.customer_users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, plan_id, version)
);

CREATE INDEX idx_site_magic_plan_versions_tenant_plan
    ON public.site_magic_plan_versions(tenant_id, plan_id, version DESC);

CREATE TABLE public.site_magic_approvals (
    approval_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES public.site_magic_plans(plan_id) ON DELETE CASCADE,
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    approved_by UUID NOT NULL REFERENCES public.customer_users(user_id) ON DELETE RESTRICT,
    approved_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, plan_id, plan_version)
);

CREATE INDEX idx_site_magic_approvals_tenant_time
    ON public.site_magic_approvals(tenant_id, approved_at DESC);

CREATE TABLE public.site_magic_build_requests (
    build_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    approval_id UUID NOT NULL REFERENCES public.site_magic_approvals(approval_id) ON DELETE RESTRICT,
    plan_id UUID NOT NULL REFERENCES public.site_magic_plans(plan_id) ON DELETE RESTRICT,
    plan_version INTEGER NOT NULL,
    plan_hash TEXT NOT NULL,
    fact_snapshot_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'started', 'failed', 'preview_ready', 'blocked')),
    requested_by UUID NOT NULL REFERENCES public.customer_users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_magic_build_requests_tenant_time
    ON public.site_magic_build_requests(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_previews (
    preview_id UUID PRIMARY KEY,
    build_id UUID NOT NULL REFERENCES public.site_magic_build_requests(build_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    preview_locator TEXT NOT NULL,
    artifact_manifest_json JSONB NOT NULL,
    rendered_evidence_json JSONB NOT NULL,
    trace_manifest_json JSONB NOT NULL,
    quality_report_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('verifying', 'ready', 'blocked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, build_id)
);

CREATE INDEX idx_site_magic_previews_tenant_time
    ON public.site_magic_previews(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_revisions (
    revision_id UUID PRIMARY KEY,
    preview_id UUID NOT NULL REFERENCES public.site_magic_previews(preview_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    scope_json JSONB NOT NULL,
    request_text TEXT NOT NULL,
    change_class TEXT NOT NULL CHECK (change_class IN ('presentation', 'semantic')),
    expected_impact_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('requested', 'applied', 'rejected')),
    created_by UUID NOT NULL REFERENCES public.customer_users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_site_magic_revisions_tenant_time
    ON public.site_magic_revisions(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_checkpoints (
    checkpoint_id UUID PRIMARY KEY,
    preview_id UUID NOT NULL REFERENCES public.site_magic_previews(preview_id) ON DELETE RESTRICT,
    build_id UUID NOT NULL REFERENCES public.site_magic_build_requests(build_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    artifact_manifest_json JSONB NOT NULL,
    trace_manifest_json JSONB NOT NULL,
    quality_report_json JSONB NOT NULL,
    accepted_by UUID NOT NULL REFERENCES public.customer_users(user_id) ON DELETE RESTRICT,
    accepted_at TIMESTAMPTZ NOT NULL,
    UNIQUE (tenant_id, preview_id)
);

CREATE INDEX idx_site_magic_checkpoints_tenant_time
    ON public.site_magic_checkpoints(tenant_id, accepted_at DESC);

CREATE TABLE public.site_magic_releases (
    release_id UUID PRIMARY KEY,
    checkpoint_id UUID NOT NULL REFERENCES public.site_magic_checkpoints(checkpoint_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('requested', 'publishing', 'published', 'failed', 'rolled_back')),
    public_locator TEXT,
    requested_by UUID NOT NULL REFERENCES public.customer_users(user_id) ON DELETE RESTRICT,
    failure_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_site_magic_releases_tenant_time
    ON public.site_magic_releases(tenant_id, created_at DESC);

CREATE TABLE public.site_magic_active_releases (
    tenant_id TEXT PRIMARY KEY REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    release_id UUID NOT NULL REFERENCES public.site_magic_releases(release_id) ON DELETE RESTRICT,
    checkpoint_id UUID NOT NULL REFERENCES public.site_magic_checkpoints(checkpoint_id) ON DELETE RESTRICT,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.site_magic_events (
    event_id UUID PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version INTEGER NOT NULL,
    aggregate_sequence INTEGER NOT NULL CHECK (aggregate_sequence > 0),
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    actor_type TEXT NOT NULL,
    actor_id UUID,
    correlation_id UUID NOT NULL,
    causation_id UUID,
    idempotency_key TEXT NOT NULL,
    payload_schema_version INTEGER NOT NULL DEFAULT 1,
    payload_json JSONB NOT NULL,
    prev_event_hash TEXT,
    event_hash TEXT NOT NULL,
    UNIQUE (tenant_id, idempotency_key),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, aggregate_sequence)
);

CREATE INDEX idx_site_magic_events_tenant_time
    ON public.site_magic_events(tenant_id, occurred_at DESC);

CREATE INDEX idx_site_magic_events_aggregate
    ON public.site_magic_events(tenant_id, aggregate_type, aggregate_id, aggregate_sequence);

ALTER TABLE public.site_magic_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_plan_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_build_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_previews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_revisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_releases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.site_magic_active_releases ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.site_magic_facts, public.site_magic_plans,
    public.site_magic_plan_versions, public.site_magic_approvals,
    public.site_magic_build_requests, public.site_magic_events,
    public.site_magic_previews, public.site_magic_revisions,
    public.site_magic_checkpoints, public.site_magic_releases,
    public.site_magic_active_releases
    FROM anon, authenticated;

CREATE OR REPLACE FUNCTION public.site_magic_reject_immutable_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
END;
$$;

CREATE OR REPLACE FUNCTION public.site_magic_reject_event_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'site_magic_events is append-only';
END;
$$;

CREATE TRIGGER site_magic_events_immutable_update
BEFORE UPDATE ON public.site_magic_events
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();

CREATE TRIGGER site_magic_events_immutable_delete
BEFORE DELETE ON public.site_magic_events
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_event_delete();

CREATE TRIGGER site_magic_approvals_immutable_update
BEFORE UPDATE ON public.site_magic_approvals
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();

CREATE TRIGGER site_magic_approvals_immutable_delete
BEFORE DELETE ON public.site_magic_approvals
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();

CREATE OR REPLACE FUNCTION public.site_magic_reject_plan_content_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.plan_version_id IS DISTINCT FROM OLD.plan_version_id
       OR NEW.plan_id IS DISTINCT FROM OLD.plan_id
       OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
       OR NEW.version IS DISTINCT FROM OLD.version
       OR NEW.content_json IS DISTINCT FROM OLD.content_json
       OR NEW.fact_snapshot_json IS DISTINCT FROM OLD.fact_snapshot_json
       OR NEW.plan_hash IS DISTINCT FROM OLD.plan_hash
       OR NEW.fact_snapshot_hash IS DISTINCT FROM OLD.fact_snapshot_hash
       OR NEW.created_by IS DISTINCT FROM OLD.created_by
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'approved plan content is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER site_magic_plan_versions_immutable_content
BEFORE UPDATE ON public.site_magic_plan_versions
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_plan_content_update();

CREATE TRIGGER site_magic_checkpoints_immutable_update
BEFORE UPDATE ON public.site_magic_checkpoints
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();

CREATE TRIGGER site_magic_checkpoints_immutable_delete
BEFORE DELETE ON public.site_magic_checkpoints
FOR EACH ROW EXECUTE FUNCTION public.site_magic_reject_immutable_update();
