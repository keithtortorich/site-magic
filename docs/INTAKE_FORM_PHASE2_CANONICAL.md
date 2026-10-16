# Intake Form — Phase 2 Canonical Spec

**Status:** Live in production  
**Last updated:** 2026-08-01  
**Scope:** Public intake form + multi-section business onboarding  
**Owner:** Backend (webstaffr/intake_router.py + webstaffr/intake.py)

---

## Overview

The WebStaffr intake form is the public entry point where home service businesses apply to join the platform. It is a multi-section form collecting 30+ fields across 9 categories, resulting in a complete business profile and a generated customer website.

**Key flow:**
1. **Public landing page** → 3-field lead capture (business name, phone, email)
2. **Lead triage** → Route to onboarding wizard
3. **Multi-section intake form** (9 sections, ~30 fields)
4. **Validation** → Standardize industry, validate required fields
5. **Database persistence** → Create tenant record + website data
6. **Site generation** → Jinja2 templates render `/sites/{tenant_id}/web`
7. **Angel deployment** → Voice AI widget embedded + live

---

## Form Structure: 9 Sections

### Section 1: Business Basics (Required)

The foundation: who they are, what they do, where they operate.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `biz_name` | string | ✓ | Business legal name (used for tenant_id generation) |
| `phone` | string | ✓ | Business contact number, stored as-is (no normalization yet) |
| `email` | string | ✓ | Primary contact email |
| `industry` | string | ✓ | Normalized to SUPPORTED_INDUSTRIES via trade_presets.py |
| `service_area` | string | ✓ | Geographic service boundary (free text: "Hillsborough County", "Tampa metro", "statewide") |
| `years_in_biz` | int | ✗ | Optional. Used for site copy credibility signals. No default fabrication. |
| `emergency_service` | string | ✗ | "yes" / "no". Gated badge on customer site. |

**Supported industries** (trade_presets.py canonical list):
- HVAC, Plumber, Electrician, Roofing
- Water Damage Restoration, Garage Door Repair, Pest Control
- Landscaping, Tree Service, Cleaning Services
- Other (fallback for unlisted trades)

### Section 2: Current Web Presence

Understanding their existing digital footprint.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `has_site` | string | ✗ | "yes" / "no" |
| `site_url` | string | ✗ | Existing website URL (if `has_site = yes`) |
| `site_platform` | string | ✗ | "Wix", "Squarespace", "WordPress", "custom", "other" |
| `site_issues` | string | ✗ | Free text: "slow", "outdated", "no lead form", etc. |
| `has_gbp` | string | ✗ | "yes" / "no" (Google Business Profile) |
| `gbp_url` | string | ✗ | GBP public profile link |
| `google_review_link` | string | ✗ | Direct link to reviews section |

### Section 3: Brand

Visual identity and design direction.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `has_logo` | string | ✗ | "yes" / "no" |
| `brand_colors` | string | ✗ | Free text: "navy and gold", hex codes, RGB descriptions |
| `brand_words` | string | ✗ | Free text: words that describe the brand personality |
| `inspo_sites` | string | ✗ | URLs to competitor/design reference sites |

### Section 4: Positioning

How they differentiate and describe themselves.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `tagline` | string | ✓ | One-liner for hero section ("Emergency plumbing, same-day response") |
| `differentiator` | string | ✓ | Why they're different (used in homepage copy) |
| `competitors` | string | ✗ | Named competitors (free text, informational only) |
| `tone` | string | ✗ | Voice preference: "professional", "friendly", "authoritative", "casual" |

### Section 5: Services

What they offer, pricing visibility, and licensing.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `services` | list[string] | ✓ | List of service offerings (e.g., ["emergency repair", "maintenance", "restoration"]) |
| `pricing_shown` | string | ✗ | "yes" / "no" — should pricing appear on site? |
| `promos` | string | ✗ | Active promotions or seasonal offers (free text) |
| `license_number` | string | ✓ | License ID (stored but **never displayed** on public site — internal only per site_data.py) |

**No-fabrication rule:** License is stored and validated; never fabricated or assumed. If missing → form fails validation.

### Section 6: Proof & Credibility

Social proof and trust signals.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `rating_value` | float | ✗ | Star rating (e.g., 4.8). Only rendered if present + review_count ≥ 3. |
| `review_count` | int | ✗ | Number of reviews. Gates rating display on site. |
| `certifications` | string | ✗ | Free text: "EPA certified", "GAF Master Elite", "ISSA member" |
| `has_before_after` | string | ✗ | "yes" / "no" — do they have project photos? |
| `testimonials` | string | ✗ | One or more customer quotes (free text, single field, can span multiple paragraphs) |

**No-fabrication rule:** No aggregateRating schema or testimonial markup is emitted unless real data backs it. Missing fields → sections omitted from rendered site.

### Section 7: Social & Tools

Digital presence and integrations.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `facebook_url` | string | ✗ | Facebook business page link |
| `instagram_url` | string | ✗ | Instagram profile link |
| `fsm_system` | string | ✗ | Field Service Management: "ServiceTitan", "Housecall Pro", "Jobber", "other" |
| `booking_system` | string | ✗ | "yes" / "no" — does their FSM have public booking? |

### Section 8: Workforce Plan

Angel rollout strategy and decision-maker info.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `plan` | string | ✓ | Tier: "Office Staff" ($497/mo) / "Business Manager" ($2,497/mo) / "Custom" |
| `lead_routing` | string | ✓ | **Internal only** — where should leads go? GHL location ID, internal routing rules, etc. Never exposed via site_data.py. |
| `timeline` | string | ✗ | "ASAP", "2-4 weeks", "1-2 months", "planning phase" |
| `approver` | string | ✓ | **Internal only** — name/email of the person who approved this submission (for audit trail). Never exposed publicly. |

**Internal-only fields:** `lead_routing` and `approver` exist in the database but are explicitly stripped from the public projection (site_data.py) — they are for WebStaffr operations only.

### Section 9: Content & SEO

Additional pages and optimization.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `assets_status` | string | ✗ | "have photos/video", "need photos/video", "will provide later" |
| `keywords` | string | ✗ | Free text: target keywords ("emergency plumbing Phoenix", etc.) |
| `extra_pages` | string | ✗ | Pages beyond standard (Home/Services/About/Contact): "Blog", "Financing options", "Warranty", "FAQ" |
| `notes` | string | ✗ | Catch-all for anything not covered above |

---

## Database Schema

**Table:** `webstaffr_intakes` (SQLite) / Postgres equivalent  
**Primary key:** `submission_id` (autoincrement)  
**Composite key for lookups:** `(tenant_id, submitted_at)`

| Column | Type | Null? | Notes |
|--------|------|-------|-------|
| `submission_id` | INTEGER | ✗ | PK, autoincrement |
| `tenant_id` | TEXT | ✗ | FK → webstaffr_tenants.tenant_id, generated from biz_name |
| `biz_name` | TEXT | ✗ | Copy of IntakeRequest.biz_name |
| `phone` | TEXT | ✗ | Copy of IntakeRequest.phone |
| `email` | TEXT | ✗ | Copy of IntakeRequest.email |
| `industry` | TEXT | ✗ | Normalized industry name |
| `service_area` | TEXT | ✗ | Geographic scope |
| `years_in_biz` | INTEGER | ✓ | NULL if not provided |
| `emergency_service` | TEXT | ✓ | "yes" / "no" / NULL |
| `tagline` | TEXT | ✗ | Hero/tagline copy |
| `differentiator` | TEXT | ✗ | Positioning statement |
| `services` | TEXT | ✗ | JSON array (stored as string): ["service1", "service2"] |
| `plan` | TEXT | ✗ | Pricing tier |
| `license_number` | TEXT | ✗ | Regulatory identifier |
| `lead_routing` | TEXT | ✗ | Internal: GHL/CRM routing info |
| `approver` | TEXT | ✗ | Internal: person/email approving submission |
| ... | TEXT | ✓ | All other optional Section 2-9 fields (20+ more columns) |
| `submitted_at` | TIMESTAMP | ✗ | UTC creation timestamp |
| `updated_at` | TIMESTAMP | ✗ | UTC last-modified timestamp |

**Indexes:**
- `(tenant_id)` — fast lookup of all submissions for one tenant
- `(tenant_id, submitted_at DESC)` — order submissions by time
- `(email)` — duplicate-submission detection

---

## Validation Rules

**Required fields** (400 Bad Request if missing):
- Section 1: `biz_name`, `phone`, `email`, `industry`, `service_area`
- Section 4: `tagline`, `differentiator`
- Section 5: `services` (non-empty list), `license_number`
- Section 8: `plan`, `lead_routing`, `approver`

**Conditional validation:**
- If `has_site = "yes"` → `site_url` and `site_platform` required
- If `has_gbp = "yes"` → `gbp_url` required
- If `pricing_shown = "yes"` → `services` must be non-empty

**Industry normalization** (trade_presets.py):
- Accepts user input: "plumbing", "Plumber", "HVAC", "AC repair", etc.
- Normalizes to canonical: "Plumber", "HVAC", etc.
- Unknown trades → "Other" (never fails)
- Provides hints and FSM software presets per industry

**No-fabrication checks:**
- Missing `years_in_biz` → do not show "15 years of experience" fallback
- Missing `rating_value` and `review_count` → omit stars/rating from site
- Missing `testimonials` → omit testimonial section (don't show placeholder)
- Empty `services` list → form fails validation (required for pricing display)

---

## API Contract

### `POST /intake`

**Request body:**
```json
{
  "biz_name": "Radiant Plumbing & Air Conditioning",
  "phone": "(813) 555-0123",
  "email": "owner@radiant.local",
  "industry": "Plumber",
  "service_area": "Tampa, FL metro",
  "years_in_biz": 12,
  "emergency_service": "yes",
  "has_site": "yes",
  "site_url": "https://radiant-plumbing.com",
  "tagline": "24/7 emergency plumbing, same-day response",
  "differentiator": "Family-owned, licensed, 97% same-day scheduling",
  "services": ["emergency repair", "installations", "maintenance"],
  "plan": "Office Staff",
  "license_number": "CPL012345",
  "lead_routing": "ghl_location_012345",
  "approver": "Keith Tortorich <keith@webstaffr.com>"
}
```

**Response (201 Created):**
```json
{
  "submission_id": 1,
  "tenant_id": "radiant_plumbing_air_conditioning_d07dc1d1",
  "biz_name": "Radiant Plumbing & Air Conditioning",
  "industry": "Plumber",
  "plan": "Office Staff"
}
```

**Error responses:**
- `400 Bad Request` — validation failed (missing required field, invalid enum, etc.)
- `503 Service Unavailable` — database connection error

### `GET /intake/presets`

Returns all supported industries and their display names.

**Response:**
```json
{
  "industries": [
    "HVAC",
    "Plumber",
    "Electrician",
    "Roofing",
    "Water Damage Restoration",
    "Garage Door Repair",
    "Pest Control",
    "Landscaping",
    "Tree Service",
    "Cleaning Services",
    "Other"
  ]
}
```

### `GET /intake/presets/{industry}`

Returns industry-specific hints (FSM software, business model notes).

**Response (for "Plumber"):**
```json
{
  "industry": "Plumber",
  "hints": "Residential and commercial plumbing services. Leads often time-sensitive.",
  "fsm_software": ["Jobber", "ServiceTitan", "Housecall Pro"],
  "trade_hints": "Average job $150–$500. Emergency calls +50% markup. Seasonal peaks: winter (burst pipes)."
}
```

---

## Site Data Projection

The intake form data is normalized and stored in the `webstaffr_intakes` table. When rendering a customer website, `site_data.py` reads this table and projects a **public-safe subset** via the `build_public_site_data(tenant_id)` function.

**Never-leak fields** (internal only, explicitly omitted from public projection):
- `lead_routing` — CRM configuration
- `approver` — internal audit trail
- `license_number` — regulatory info (stored but not displayed)
- `competitors` — competitive analysis
- Any raw email/phone before sanitization

**Projected fields** (safe for public site):
- Business basics: `biz_name`, `phone`, `email`, `industry`, `service_area`, `years_in_biz`, `emergency_service`
- Positioning: `tagline`, `differentiator`, `tone`
- Services: `services` (list)
- Proof: `rating_value`, `review_count`, `certifications`, `testimonials`, `has_before_after`
- Social: `facebook_url`, `instagram_url`

**Gating logic:**
- Show stars → `rating_value` present AND `review_count` >= 3
- Show testimonials section → `testimonials` is not empty
- Show emergency badge → `emergency_service = "yes"`
- Show pricing → `pricing_shown = "yes"` OR plan includes pricing

---

## Frontend Integration

The intake form is typically served by a standalone HTML form on the landing page or embedded in the site renderer.

**Frontend must:**
1. Render 9 sections in logical groupings (can be tabs, accordions, or a wizard flow)
2. Call `GET /intake/presets` on load to populate the industry dropdown
3. Call `GET /intake/presets/{industry}` when industry changes, to show hints
4. Validate required fields before submission
5. POST to `/intake` with the complete payload
6. Handle 400/503 error responses gracefully (show error message, preserve form state)
7. Redirect to success page with `submission_id` and `tenant_id` on 201 Created

**No backend in intake form flow:**
- The intake form itself has no business logic — it is a pure data capture UI
- Validation, normalization, and persistence happen entirely in `intake_router.py` and `intake.py`
- The frontend cannot and should not bypass validation

---

## Workflow After Submission

1. **Intake accepted** → `submission_id` + `tenant_id` returned
2. **Tenant created** (if new) → `webstaffr_tenants` row inserted
3. **Tracking number assigned** → `webstaffr_tracking_numbers` row created (auto-generated phone-based number)
4. **Site data cached** → `build_public_site_data(tenant_id)` called, stored in `webstaffr_sites` (optional, for fast renders)
5. **Site generated** → Customer's website live at `/sites/{tenant_id}/web` (Jinja2 + site_renderer.py)
6. **Angel deployed** → Retell widget embedded, listening for customer chat
7. **Lead routing configured** → GHL webhook subscribed (if credentials set)

---

## Testing Strategy

**Unit tests** (`tests/test_intake.py`):
- Validation logic (required fields, industry normalization, conditional rules)
- Database persistence (IntakeRepository.save(), retrieval by tenant_id)
- No-fabrication checks (rating gating, testimonial presence)

**Integration tests** (`tests/test_intake_router.py`):
- Full POST /intake round-trip with realistic payload
- 400 responses on missing required fields
- 503 on database error
- Tenant generation and tracking number assignment
- Site data projection (never-leak fields omitted)

**End-to-end** (via health_check.py):
- Intake round-trip from landing form → site render
- Verify `/sites/{tenant_id}/web` returns 200 with correct schema

---

## Constraints & Scope

**In scope (MVP):**
- 9-section form capturing 30+ fields
- Industry standardization via trade_presets.py
- Database persistence with tenant isolation
- Public site data projection (no-fabrication enforcement)
- API validation and error handling
- CORS scoping (POST /intake has no CORS headers — internal/Lovable only)

**Out of scope (post-MVP):**
- Form UX/design (Lovable project domain)
- Multi-language form (intake is US-only, Phase 2+)
- File uploads (logo, before-after photos) — Phase 2
- Dynamic pricing based on industry/location
- Form prefill from GHL contact data
- A/B testing form flows
- Admin dashboard to view/edit submissions

---

## Decisions & Rationale

| Item | Decision | Why |
|------|----------|-----|
| 9 sections | Organize by business data type (basics, web presence, brand, positioning, services, proof, tools, workforce, content) | Helps users understand data requirements without overwhelming them; mirrors the site structure |
| Internal-only fields in form | `lead_routing`, `approver` stored but never exposed | Supports WebStaffr operations (CRM routing, audit) without leaking internal logic to customers |
| No-fabrication enforcement | Missing data gates sections, never fabricates placeholders | Builds trust; every stat on a customer site is real data they provided |
| Industry as free text + normalization | Accept any text, normalize to canonical list | Handles user misspellings ("plumbing" → "Plumber") without form friction |
| Single services list | Not a structured service catalog yet | MVP scope; Phase 2 can break out service-specific pricing/detail pages |
| Phone number as-is | No formatting/validation | Users can submit any format; Lovable/frontend can normalize if needed |
| Rating display gated on count | Stars only show if ≥3 reviews | Prevents stat inflation ("5.0 stars / 1 review" looks fabricated) |

---

## Governance Compliance

**Brand rules applied:**
- No em-dashes in form labels or default text (Governance Manual: absolute ban)
- No "AI" language in form copy (use "Angel", "receptionist", "office staff")
- No emoji in form UI or error messages
- Company name always "WebStaffr" (capital W, capital S)

**Data handling:**
- PII (phone, email) stored encrypted in transit (HTTPS), in database with tenant isolation
- License numbers stored but never publicly displayed
- No third-party data brokers or sharing (data stays in this repo's Supabase project)

**Tenant isolation:**
- Every query filters by `tenant_id`
- Submissions from one tenant cannot be read by another
- Tracking numbers assigned per tenant, not shared

---

## Future Enhancements (Post-MVP)

1. **Phase 2 Multi-Section Wizard** — Current form is linear; Phase 2 can break into standalone sections (progress bar, save-and-resume, skip optional sections)
2. **File uploads** — Logo, before-after photos, certifications
3. **Service catalog** — Structured service definitions with per-service pricing tiers
4. **GHL prefill** — If intake is triggered from a GHL contact, prefill from existing lead data
5. **Form analytics** — Track drop-off points, completion rates by industry
6. **A/B variants** — Test different form lengths, section orders, optional-field visibility
7. **Admin interface** — WebStaffr ops team can view/edit submissions, flag for manual review
8. **Resubmission** — Allow customers to update their profile post-launch
9. **Localization** — Spanish, French forms for non-English-speaking businesses

---

**Document owner:** Claude  
**Last reviewed:** 2026-08-01  
**Next review:** Post-MVP, when Phase 2 form enhancements begin  
