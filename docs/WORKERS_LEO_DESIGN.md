# Leo: Lead Coordinator AI Worker

Status: design + implementation for MVP integration into WebStaffr 4.0.

## Purpose

Leo is a sibling AI-employee worker to Angel (same architecture), specialized in instant lead follow-up: within 2 minutes of a new lead arriving from GoHighLevel (GHL), Leo scores the lead using the AOKAI 100-point rubric, determines routing (call-led for high-value tiers, email-led nurture for lower tiers), and sends the appropriate first outreach SMS or email via GHL's messaging API.

## Scope (MVP)

Leo's MVP deliverables:

- **Webhook receiver** (`POST /webhooks/ghl/lead`): accepts incoming lead events from GHL, tenant-scoped, no CORS headers (server-to-server only)
- **AOKAI 100-point scoring engine**: implements the rubric from `docs/LEAD_ENGINE.md` (Accessibility 35pts, Business Size 20pts, Digital Maturity 20pts, Revenue Potential 15pts, Buying Signals 10pts)
- **Routing logic**: maps scores to tiers (85-100: Tier 1 call-led, 70-84: Tier 2 call-led, 55-69: Tier 3 email-led nurture, <55: skip)
- **GHL integration** for outreach: send SMS (Tier 1-2) or email (Tier 3) via GHL's messaging API
- **Tenant isolation**: all database queries and GHL operations scoped to the lead's tenant_id
- **Error resilience**: if GHL is unreachable, lead is still stored locally with status "pending_sync"

Out of scope (post-MVP):
- Full outreach sequences (7-touch call-led, 5-touch email nurture) — MVP is first touch only
- Retell AI cold-calling integration
- Lead deduplication
- Lead sourcing (Grape Leads, Outscraper)
- Performance tracking, escalation workflows, or manual review UI

## Architecture

### Triggering Events

Leo is triggered by GoHighLevel when:
- A new contact is created in GHL (or updated with qualifying signals)
- GHL webhook includes contact details (phone, email, business info, interaction history)
- Webhook is signed with `GHL_WEBHOOK_SECRET` (same verifier as Angel's `/webhooks/ghl`)

### Data Flow

```
GHL webhook event → Leo webhook receiver
  ↓
Parse & validate event (tenant_id, contact fields)
  ↓
AOKAI scoring engine (35+20+20+15+10 = 100 points max)
  ↓
Tier determination (score range → routing)
  ↓
First-touch outreach (SMS or Email via GHL)
  ↓
Store lead record in `webstaffr_leads` table (new)
  ↓
If GHL sync fails, mark `sync_status = "pending_sync"`, retry on next poll
```

### Database Schema (New)

```sql
CREATE TABLE webstaffr_leads (
  lead_id INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id TEXT NOT NULL,
  ghl_contact_id TEXT,
  contact_name TEXT,
  phone TEXT,
  email TEXT,
  business_name TEXT,
  industry TEXT,
  -- AOKAI score breakdown
  score_accessibility INTEGER DEFAULT 0,  -- 0-35
  score_business_size INTEGER DEFAULT 0,   -- 0-20
  score_digital_maturity INTEGER DEFAULT 0, -- 0-20
  score_revenue_potential INTEGER DEFAULT 0, -- 0-15
  score_buying_signals INTEGER DEFAULT 0,  -- 0-10
  score_total INTEGER DEFAULT 0,           -- 0-100
  tier INTEGER,                            -- 1, 2, 3, or 4 (skip)
  -- Outreach tracking
  first_touch_channel TEXT,                -- 'sms' or 'email'
  first_touch_sent_at TIMESTAMP,
  sync_status TEXT DEFAULT 'synced',      -- 'synced' or 'pending_sync'
  ghl_error TEXT,
  -- Audit
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
```

### API Contract

#### Webhook: POST /webhooks/ghl/lead

Request (from GHL):
```json
{
  "tenant_id": "abc123",
  "event_type": "lead_created",
  "contact_id": "ghl-contact-uuid",
  "contact_name": "John Smith",
  "phone": "+1-602-555-0123",
  "email": "john@example.com",
  "business_name": "Smith Plumbing",
  "industry": "Plumber",
  "company_phone_answered": true,
  "owner_answered": false,
  "text_enabled": true,
  "employee_count": 5,
  "vehicle_count": 2,
  "currently_hiring": true,
  "has_website": false,
  "has_booking_system": false,
  "active_reviews_count": 8,
  "offers_financing": true
}
```

Response (from Leo):
```json
{
  "status": "processed",
  "lead_id": 1,
  "score": 78,
  "tier": 2,
  "first_touch": "sms"
}
```

Error response (webhook validation fails):
```json
{"detail": "Invalid or missing webhook secret"}
```

Error response (lead processing succeeds, but GHL sync fails):
```json
{
  "status": "processed_partially",
  "lead_id": 1,
  "score": 78,
  "tier": 2,
  "sync_error": "GHL API returned 503: Service Unavailable"
}
```

#### Internal Route: POST /leo/score (for testing)

Request:
```json
{
  "tenant_id": "abc123",
  "contact_name": "John Smith",
  "phone": "+1-602-555-0123",
  "business_name": "Smith Plumbing",
  "industry": "Plumber",
  "company_phone_answered": true,
  "owner_answered": false,
  "text_enabled": true,
  "employee_count": 5,
  "vehicle_count": 2,
  "currently_hiring": true,
  "has_website": false,
  "has_booking_system": false,
  "active_reviews_count": 8,
  "offers_financing": true
}
```

Response:
```json
{
  "score_accessibility": 25,
  "score_business_size": 16,
  "score_digital_maturity": 18,
  "score_revenue_potential": 15,
  "score_buying_signals": 4,
  "score_total": 78,
  "tier": 2
}
```

### AOKAI Scoring Rubric

| Category | Max | Signals |
|----------|-----|---------|
| **Accessibility** (35) | 35 | Phone answered by human (+15), Owner answered (+10), Text-enabled (+5), Email available (+5) |
| **Business Size** (20) | 20 | 3-20 employees (+8), 2-8 vehicles (+5), Currently hiring (+3), Has multiple locations (+4) |
| **Digital Maturity** (20) | 20 | No website (+8), No booking system (+5), No CRM/scheduling (+5), DIY platform only (+2) |
| **Revenue Potential** (15) | 15 | HVAC (+15), Water Damage (+14), Roofing (+13), Plumbing (+12), Electrical (+11), Other services (+6-10) |
| **Buying Signals** (10) | 10 | Hiring office staff (+3), Active reviews (2+, +2), Offers financing (+2), Recent service history (+3) |

### Tier Assignments

| Tier | Score | Action | Channel | Cadence |
|------|-------|--------|---------|---------|
| 1 | 85-100 | Call within 1 hour | SMS intro + Retell voice call | Immediate |
| 2 | 70-84 | Call same day, within 4 hours | SMS intro + Retell voice call | <4h |
| 3 | 55-69 | Nurture sequence | Email + scheduled SMS | Weekly check-in |
| 4 | <55 | Skip, remove from active list | — | — |

For MVP: only first touch is sent. Full sequences are post-MVP work.

### Security & Compliance

- **Tenant isolation**: every database query and GHL API call includes `tenant_id` parameter; impossible to query/sync across tenants
- **Webhook verification**: `X-Webhook-Secret` header validated against `GHL_WEBHOOK_SECRET` (same as Angel's pattern)
- **CORS**: `/webhooks/ghl/lead` carries no CORS headers (server-to-server only, not called from browser)
- **No fabrication**: AOKAI scores use real lead data only; never apply default/assumed values
- **Error handling**: invalid/missing lead data → 400 Bad Request with explanation; GHL sync failure → 200 OK with `sync_status = "pending_sync"` for later retry
- **Credentials**: GHL_API_KEY, GHL_LOCATION_ID verified at construction; missing credentials raise `GHLNotConfiguredError` (Null default for tests)

### Integration Points

1. **Existing GHL client** (`workers/angel/ghl.py`): reused for `create_appointment()`, extended with `send_sms()` and `send_email()` for outreach messaging
2. **Existing rate limiter** (`rate_limit.py`): same per-tenant counter for `/webhooks/ghl/lead` as for `/chat` and other Angel endpoints
3. **Existing Tenant model** (`tenant.py`): validates tenant_id, raises `InvalidTenantError` if missing
4. **Existing Null verifier pattern** (`workers/angel/api_auth.py`): GHL webhook secret verification matches Angel's verifier behavior (fails open unconfigured, fails closed when set)
5. **Composition root** (`app.py`): Leo's router included as a sibling to Angel's, not nested inside Angel's package

## Testing Strategy

### Unit Tests (test_leo_scoring.py)

- Scoring rubric: verify each category's max points and signal logic
- Edge cases: missing fields (None → 0 points), out-of-range values (clamped), industry not in list (mapped to default points)
- Tier assignment: verify score ranges map to correct tiers

### Integration Tests (test_leo_router.py)

- Webhook round-trip: valid lead event → lead stored in DB → AOKAI score calculated → SMS/email sent via GHL → response includes score/tier
- Tenant isolation: attempt to query lead from wrong tenant → 400 Bad Request or empty result
- Webhook verification: invalid secret → 401; no secret when unconfigured → 200 (Null verifier accepts)
- GHL sync failure: API unreachable → lead still stored locally with `sync_status = "pending_sync"`
- Rate limiting: exceed per-tenant limit → 429 Too Many Requests

### Happy Path (Full Round-Trip)

1. Create test tenant
2. POST `/webhooks/ghl/lead` with valid lead event
3. Verify lead inserted into `webstaffr_leads` with correct score, tier, and first_touch_channel
4. Verify GHL API was called with correct SMS/email payload
5. Verify response includes score, tier, sync_status

## Files

- `webstaffr/workers/leo/` — new worker package
  - `__init__.py` — exports
  - `protocol.py` — GHLClient protocol (Protocol interface, same as Angel's)
  - `client.py` — GHL API wrapper (extended with send_sms/send_email)
  - `scoring.py` — AOKAI 100-point rubric implementation
  - `router.py` — FastAPI routes (/webhooks/ghl/lead, /leo/score for testing)
- `webstaffr/migrations/0008_leo_leads.sql` — new table schema
- `webstaffr/migrations/postgres_manual/0009_leo_leads.sql` — Postgres RLS version
- `tests/test_leo_scoring.py` — unit tests for AOKAI scoring
- `tests/test_leo_router.py` — integration tests for webhook and routing
- `webstaffr/app.py` — updated to wire Leo's router (one line added)

## Rollout & Fallback

Deployment:
1. Apply migrations to dev/staging (new `webstaffr_leads` table with RLS)
2. Deploy backend code with Leo's router wired into app.py
3. Configure `GHL_WEBHOOK_SECRET` in Vercel environment (reuses existing secret if shared, or creates new one if separate flows needed)
4. Configure GHL workflow to send webhook to `POST /webhooks/ghl/lead` (same webhook URL as Angel's, different event type)

Fallback:
- If Leo's service is down, GHL webhook still arrives but gets 5xx response; GHL retries (standard webhook retry logic)
- If GHL API is unreachable, lead is stored with `sync_status = "pending_sync"` and a background job can retry later (post-MVP)
- If AOKAI scoring is wrong, the only user-visible impact is the wrong routing tier — no customer data is lost, and manual review can correct the tier before outreach (post-MVP escalation workflow)

## Open Items & Post-MVP

1. **Full outreach sequences** — MVP sends first touch only; full 7-touch (Tier 1-2) and 5-touch (Tier 3) sequences are post-MVP
2. **Background retry for pending_sync leads** — MVP stores them; post-MVP job polls and retries
3. **Lead deduplication** — not implemented; GHL handles duplicate detection on their side
4. **Compliance** — TCPA, DNC registry, calling-hour windows are documented in `docs/LEAD_ENGINE.md` as required but not implemented; must be resolved before any automated calls or SMS go live
5. **Performance monitoring** — no dashboards, metrics, or alerts wired up; post-MVP instrumentation
6. **Manual review escalation** — 48-hour escalation rule from `docs/LEAD_ENGINE.md` is not implemented; post-MVP workflow
