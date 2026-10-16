-- Leo's leads table: AOKAI-scored leads awaiting first-touch outreach.
-- Stores score breakdown, tier, sync status, and outreach tracking.

CREATE TABLE webstaffr_leads (
  lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  ghl_contact_id TEXT,  -- GHL's internal contact UUID
  contact_name TEXT,
  phone TEXT,
  email TEXT,
  business_name TEXT,
  industry TEXT,
  -- AOKAI score breakdown (0-100 total)
  score_accessibility INTEGER DEFAULT 0,   -- 0-35: phone/owner/text/email
  score_business_size INTEGER DEFAULT 0,   -- 0-20: employees/vehicles/hiring/locations
  score_digital_maturity INTEGER DEFAULT 0, -- 0-20: website/booking/CRM/DIY
  score_revenue_potential INTEGER DEFAULT 0, -- 0-15: industry value
  score_buying_signals INTEGER DEFAULT 0,   -- 0-10: office hiring/reviews/financing/service
  score_total INTEGER DEFAULT 0,            -- 0-100: sum of above
  -- Routing
  tier INTEGER,  -- 1 (85-100: call), 2 (70-84: call), 3 (55-69: email), 4 (<55: skip)
  -- Outreach tracking
  first_touch_channel TEXT,  -- 'sms' (for Tier 1-2) or 'email' (for Tier 3)
  first_touch_sent_at TIMESTAMP,
  -- GHL sync status
  sync_status TEXT DEFAULT 'synced',  -- 'synced' or 'pending_sync' (GHL API unreachable)
  ghl_error TEXT,  -- error message from GHL API if sync fails
  -- Audit
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

CREATE INDEX idx_webstaffr_leads_tenant_id ON webstaffr_leads(tenant_id);
CREATE INDEX idx_webstaffr_leads_ghl_contact_id ON webstaffr_leads(ghl_contact_id);
CREATE INDEX idx_webstaffr_leads_tier ON webstaffr_leads(tier);
CREATE INDEX idx_webstaffr_leads_sync_status ON webstaffr_leads(sync_status);
