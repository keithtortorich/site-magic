-- Leo's leads table for Postgres/Supabase: AOKAI-scored leads.
-- RLS enabled, default-deny per repo security baseline.

CREATE TABLE IF NOT EXISTS webstaffr_leads (
  lead_id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  ghl_contact_id TEXT,
  contact_name TEXT,
  phone TEXT,
  email TEXT,
  business_name TEXT,
  industry TEXT,
  -- AOKAI score breakdown
  score_accessibility INTEGER DEFAULT 0,
  score_business_size INTEGER DEFAULT 0,
  score_digital_maturity INTEGER DEFAULT 0,
  score_revenue_potential INTEGER DEFAULT 0,
  score_buying_signals INTEGER DEFAULT 0,
  score_total INTEGER DEFAULT 0,
  -- Routing
  tier INTEGER,
  -- Outreach tracking
  first_touch_channel TEXT,
  first_touch_sent_at TIMESTAMP WITH TIME ZONE,
  -- GHL sync status
  sync_status TEXT DEFAULT 'synced',
  ghl_error TEXT,
  -- Audit
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_webstaffr_leads_tenant_id ON webstaffr_leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_webstaffr_leads_ghl_contact_id ON webstaffr_leads(ghl_contact_id);
CREATE INDEX IF NOT EXISTS idx_webstaffr_leads_tier ON webstaffr_leads(tier);
CREATE INDEX IF NOT EXISTS idx_webstaffr_leads_sync_status ON webstaffr_leads(sync_status);

-- RLS: default-deny, no policies (same as other tables in this repo)
ALTER TABLE webstaffr_leads ENABLE ROW LEVEL SECURITY;
