CREATE TABLE IF NOT EXISTS public.website_leads (
    lead_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL REFERENCES public.tenants(tenant_id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    message TEXT NOT NULL,
    service TEXT,
    source_path TEXT,
    ghl_contact_id TEXT,
    status TEXT NOT NULL DEFAULT 'received'
        CHECK (status IN ('received', 'forwarded', 'forward_failed')),
    forward_attempts INTEGER NOT NULL DEFAULT 0
        CHECK (forward_attempts >= 0),
    last_forward_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_website_leads_tenant_created
    ON public.website_leads(tenant_id, created_at);

ALTER TABLE public.website_leads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.website_leads FROM anon, authenticated;

-- Public visitors write only through the rate-limited FastAPI endpoint using
-- the backend's trusted direct connection. No Data API policies are intended.
