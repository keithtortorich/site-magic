-- 0003_intake_submissions.sql
-- Client intake submissions -- the first stage of the intake -> generated
-- customer site -> Angel widget MVP flow (see CLAUDE.md / PROJECT.md).
--
-- Field set ported from the proven 9-section intake form in the legacy
-- webstaff repo (intake/intake.html), NOT reinvented from scratch -- see
-- the CLAUDE.md session addendum for provenance. Fields are the same for
-- every industry; what varies per trade is presentation-layer hint text
-- and FSM software options (webstaffr/trade_presets.py), not this schema.
--
-- Tenant-scoped like every other table. tenant_id is generated server-side
-- from the business name at submission time (see webstaffr/intake.py),
-- not supplied by the caller.

CREATE TABLE IF NOT EXISTS intake_submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),

    -- Section 1: Business Basics
    biz_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    industry TEXT NOT NULL,
    service_area TEXT NOT NULL,
    years_in_biz INTEGER,
    emergency_service TEXT,             -- 'Yes' | 'No'

    -- Section 2: Current Web Presence
    has_site TEXT,                      -- 'Yes' | 'No'
    site_url TEXT,
    site_platform TEXT,
    site_issues TEXT,
    has_gbp TEXT,                       -- 'Yes' | 'No' | 'Not sure'
    gbp_url TEXT,
    google_review_link TEXT,

    -- Section 3: Brand
    has_logo TEXT,                      -- 'Yes' | 'No'
    brand_colors TEXT,                  -- 'I have them' | 'Choose for me'
    brand_words TEXT,
    inspo_sites TEXT,

    -- Section 4: Positioning
    tagline TEXT NOT NULL,
    differentiator TEXT NOT NULL,
    competitors TEXT,
    tone TEXT,                          -- Professional | Friendly | Bold | Urgent | Luxury

    -- Section 5: Services
    services_json TEXT NOT NULL,        -- JSON array of strings
    pricing_shown TEXT,
    promos TEXT,
    license_number TEXT NOT NULL,

    -- Section 6: Proof & Credibility
    rating_value REAL,
    review_count INTEGER,
    certifications TEXT,
    has_before_after TEXT,              -- 'Yes' | 'No'
    testimonials TEXT,

    -- Section 7: Social & Tools
    facebook_url TEXT,
    instagram_url TEXT,
    fsm_system TEXT,
    booking_system TEXT,

    -- Section 8: Workforce Plan
    plan TEXT NOT NULL,                 -- office_staff for initial launch
    lead_routing TEXT NOT NULL,
    timeline TEXT,
    approver TEXT NOT NULL,

    -- Section 9: Content & SEO
    assets_status TEXT,                 -- 'Have plenty' | 'Have some' | 'Need shoot'
    keywords TEXT,
    extra_pages TEXT,
    notes TEXT,

    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_intake_submissions_tenant
    ON intake_submissions(tenant_id);
