BEGIN;

ALTER TABLE public.site_magic_jobs
    ADD COLUMN current_event_sequence INTEGER NOT NULL DEFAULT 0;

CREATE TABLE public.site_magic_job_events (
    event_id TEXT NOT NULL,
    job_id UUID NOT NULL REFERENCES public.site_magic_jobs(job_id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    event_sequence INTEGER NOT NULL,
    prior_state TEXT NOT NULL,
    new_state TEXT NOT NULL,
    payload_json JSONB,
    response_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, event_id)
);

CREATE UNIQUE INDEX idx_site_magic_job_events_sequence
    ON public.site_magic_job_events(job_id, event_sequence);

CREATE INDEX idx_site_magic_job_events_tenant
    ON public.site_magic_job_events(tenant_id, created_at DESC);

ALTER TABLE public.site_magic_job_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.site_magic_job_events FROM anon, authenticated;

COMMIT;
