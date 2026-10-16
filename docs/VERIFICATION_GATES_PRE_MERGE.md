# Pre-Merge Verification Gates

**Purpose:** Define the comprehensive test matrix that will be embedded in the test suite and health check to guarantee that customer sites render correctly every time.

**Status:** 2026-08-09, Design Phase  
**Target:** Implement as code, integrate with CI/test harness, verify all pass before merge

---

## Why These Gates Matter

Before Phase 1 (demo verification), we have **manual, one-time audits** of static demo files.

Before a customer's site goes live, we need **automated, repeatable gates** that catch:
- Intake data missing required fields (schema audit)
- Rendering breaks after code changes (regression test)
- Angel embed not loading (widget verification)
- Brand palette not applied correctly (color audit)
- Governance violations leaked to public site (linter)
- Content freshness lost between submission and render (pipeline integrity)

These gates must run on every commit, every test, and at deployment time.

---

## The Five Verification Gate Categories

### Gate 1: Site Data Schema Audit

**Problem:** Optional fields can be None, but template expects them to be present. Code change can break page rendering for tenants with incomplete intake data.

**Solution:** 
- Define a `SiteDataValidator` that runs on every intake and every render
- Check that required fields are present and non-empty (tenant_id, biz_name, phone, industry, services, plan)
- Check that optional fields, if present, have valid format (phone is formatted, hex colors are valid, URLs are parseable)
- Return detailed error for every missing/malformed field

**Test Location:** `tests/test_site_data_schema_audit.py`

**When to run:**
- After intake submission (before site generation)
- Before rendering any page (catch data corruption in-flight)
- Health check (baseline scan)

**Expected behavior:**
```
✓ Required field "tenant_id" present
✓ Required field "biz_name" present (length: 24)
✓ Optional field "brand_colors" valid hex format
✓ Optional field "phone" formatted as +1-XXX-XXX-XXXX
✓ Services list has 3 items (not empty)
✓ Schema audit: PASS (0 errors)
```

**Pass criteria:** Zero schema violations.

---

### Gate 2: Template Regression Test (All 9 Demos)

**Problem:** Code change in site_render_router.py, templates/, or Jinja2 context can silently break rendering. A demo that worked yesterday may return 500 today.

**Solution:**
- Create a `test_demo_sites_http_200()` test that fetches all 8 demos at startup
- Verify each returns HTTP 200 and content-type: text/html
- Verify each contains the expected content (company name, services, phone)
- Run as a pre-test smoke test (fail fast before other tests run)

**Test Location:** `tests/test_site_render_router.py::TestDemoSiteRegressions`

**When to run:**
- Before full test suite (smoke test, ~5 seconds)
- After any change to `site_render_router.py`, `webstaffr/templates/`, or `webstaffr/site_data.py`
- CI pipeline (pre-commit, pre-push)

**Expected behavior:**
```
test_demo_hvac_http_200 ✓
test_demo_plumbing_http_200 ✓
test_demo_roof_http_200 ✓
test_demo_landscape_http_200 ✓
test_demo_pest_http_200 ✓
test_demo_garage_http_200 ✓
test_demo_arbor_http_200 ✓
test_demo_waterrestore_http_200 ✓
8 tests passed in 4.2 seconds
```

**Pass criteria:** All 9 demos return HTTP 200 and contain expected content.

---

### Gate 3: Angel Widget Embed Verification

**Problem:** Angel widget (Retell voice snippet) must load on every customer site. If the embed code is missing or malformed, customers can't use the AI employee.

**Solution:**
- Parse rendered HTML for first-party Angel widget script
- Verify script src is correct (https://..., not malformed, not localhost)
- Verify Retell API key is present (if required)
- Verify script is in footer, after all content (not in head, not blocking render)
- Check that the script loads without errors (in health check, use fetch to test endpoint)

**Test Location:** `tests/test_angel_embed_verification.py`

**When to run:**
- After site generation (part of intake response)
- Health check (verify all production sites have working widget)
- Manual verification (F12 console, check for Retell startup messages)

**Expected behavior:**
```
✓ first-party Angel widget script present in HTML
✓ Script src: https://...retell-web-embed.js
✓ API key in data-attributes (if required)
✓ Script position: footer (not head, not blocking)
✓ Retell endpoint reachable (ping /retell/status)
✓ Angel embed: PASS
```

**Pass criteria:** Script present, src valid, endpoint reachable.

---

### Gate 4: Brand Palette & WCAG Compliance Audit

**Problem:** Tenant colors can drift from verified intake direction or create inaccessible contrast. ADR-022 house colors must not be forced onto customer sites.

**Solution:**
- Extract all CSS color values from rendered HTML
- Check that the submitted tenant color is represented consistently
- Check that NetBuild.Pro house colors are not substituted for tenant direction
- Check that action and focus colors remain distinguishable
- For every text+background pair, calculate contrast ratio
- Flag any pair with contrast < 4.5:1 (WCAG AA normal text) or < 3:1 (large text/UI)
- Report as warning (does not fail tests, but logged in health check)

**Test Location:** `tests/test_brand_palette_audit.py` + `health_check.py`

**When to run:**
- After site generation (catch color data corruption early)
- Health check (baseline palette compliance)
- Before release (ensure no regressions)

**Expected behavior:**
```
✓ Primary color (#000080) used 4 times (H1, 3x buttons)
✓ Secondary color (#4169E1) used 2 times (links, accents)
✓ Highlight color (#FF6600) used 1 time (main CTA)
⚠ Contrast ratio navy on gray: 4.2:1 (below WCAG AA 4.5:1)
   Recommendation: Darken gray (#E0E0E0 → #D0D0D0) or brighten navy
✓ Brand palette: PASS (1 warning)
```

**Pass criteria:** Colors match palette. Warnings allowed; errors (< 3:1) fail.

---

### Gate 5: Governance Linter (No Em-Dashes, No Prohibited Terms, No Leaked Fields)

**Problem:** Copy is manually written; governance violations can slip through (em-dashes, leaked internal fields, prohibited terms). Template changes might accidentally expose lead_routing or approver.

**Solution:**
- Run existing governance-compliance-linter on rendered HTML
- Check for literal em-dashes: —
- Check for entity-encoded em-dashes: &mdash;
- Check for prohibited terms (varies by trade, but examples: "guaranteed," "best," "only," "AI")
- Check that internal-only fields never appear: lead_routing, approver, competitors, license_number
- Check that brand name is spelled correctly ("NetBuild.Pro", not "NetBuild Pro")

**Test Location:** `tests/test_governance_linter.py` + `health_check.py`

**When to run:**
- After intake submission (before site generation)
- After site rendering (catch template-level leaks)
- CI pipeline (pre-push)

**Expected behavior:**
```
Scanning: site/demos/hvac.html
✓ No em-dashes found (literal or entity-encoded)
✓ No prohibited terms found
✓ No leaked internal fields (lead_routing, approver, competitors, license_number)
✓ Brand name spelled correctly (5 instances of "NetBuild.Pro")
✓ Governance linter: PASS
```

**Pass criteria:** Zero governance violations.

---

### Gate 6: Content Freshness (Intake → Render Pipeline Integrity)

**Problem:** Intake data is submitted, stored in DB, fetched, and rendered. A bug in the fetch/render pipeline could silently lose data (e.g., services list becomes empty, phone number disappears).

**Solution:**
- Create an intake-to-render round-trip test
- Submit intake with known data (company name, services, phone, etc.)
- Fetch rendered site from `/sites/{tenant_id}/web`
- Verify all submitted data appears in rendered HTML
- Check that optional fields (if submitted) appear; if not submitted, they're omitted (not faked)

**Test Location:** `tests/test_intake_render_roundtrip.py` + `tests/test_site_render_router.py`

**When to run:**
- After intake submission (immediate smoke test)
- Before rendering any page
- Health check (baseline round-trip for demo tenants)

**Expected behavior:**
```
Intake: { company: "HVAC Pro", services: ["AC Repair", "Install"], phone: "602-555-0100" }
Render: GET /sites/{tenant_id}/web
✓ "HVAC Pro" found in rendered HTML
✓ "AC Repair" found in services section
✓ "Install" found in services section
✓ "602-555-0100" found in header and CTA
✓ Optional field "rating_value" not submitted, not present in HTML (correct)
✓ Content freshness: PASS
```

**Pass criteria:** All submitted data present. Submitted-but-empty fields omitted. No data loss.

---

## Implementation Roadmap

### Step 1: Unit Tests (Each Gate Gets a Test File)

```
tests/
├── test_site_data_schema_audit.py       (Gate 1)
├── test_demo_site_regressions.py        (Gate 2 — extend test_site_render_router.py)
├── test_angel_embed_verification.py     (Gate 3)
├── test_brand_palette_audit.py          (Gate 4)
├── test_governance_linter.py            (Gate 5 — may exist)
└── test_intake_render_roundtrip.py      (Gate 6 — extend test_site_render_router.py)
```

Each test:
- Has a descriptive docstring
- Clearly states what it's checking
- Provides detailed error messages (not just "FAIL")
- Can be run independently (`pytest tests/test_X.py -v`)

### Step 2: Integrate Into Health Check

```python
# health_check.py additions

def check_demo_site_regressions():
    """Smoke test: all 8 demos return HTTP 200."""
    # Call each demo, verify HTTP 200

def check_angel_embed_verification():
    """Verify Angel widget script is present and reachable."""
    # Fetch demo sites, check for Retell tag, ping endpoint

def check_brand_palette_compliance():
    """Audit brand colors and WCAG contrast."""
    # Extract colors, check against verified tenant direction, calculate contrast ratios

def check_governance_linter():
    """Run linter on all rendered demo sites."""
    # Check for em-dashes, leaked fields, prohibited terms

def check_content_freshness():
    """Round-trip test: intake → render pipeline."""
    # Submit intake, fetch rendered site, verify data present
```

Expected output in health check:

```
[9/12] Demo Site Regressions: PASS (9/9 demos HTTP 200)
[10/12] Angel Embed Verification: PASS (8 widgets reachable)
[11/12] Brand Palette Compliance: PASS (1 contrast warning, no errors)
[12/12] Governance Linter: PASS (0 violations)

Health: 12/12 PASS
```

### Step 3: CI Integration

Add to pre-commit or CI pipeline:

```bash
# Smoke test (fast, fail-fast)
pytest tests/test_demo_site_regressions.py -v

# Full test suite
pytest tests/ -v

# Health check
python health_check.py
```

### Step 4: Documentation

Update:
- `README.md` — How to run verification gates
- `CLAUDE.md` — Verification gate locations and when they run
- `docs/TESTING_STRATEGY.md` — Gate design, rationale, maintenance notes

---

## Expected Test Output (All Gates Passing)

```
$ pytest tests/ -v --tb=short
...
tests/test_site_data_schema_audit.py::test_required_fields_present PASSED
tests/test_site_data_schema_audit.py::test_optional_fields_valid_format PASSED
tests/test_demo_site_regressions.py::test_demo_hvac_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_plumbing_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_roof_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_landscape_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_pest_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_garage_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_arbor_http_200 PASSED
tests/test_demo_site_regressions.py::test_demo_waterrestore_http_200 PASSED
tests/test_angel_embed_verification.py::test_retell_script_present PASSED
tests/test_angel_embed_verification.py::test_retell_endpoint_reachable PASSED
tests/test_brand_palette_audit.py::test_primary_color_used_correctly PASSED
tests/test_brand_palette_audit.py::test_wcag_contrast_audit PASSED
tests/test_governance_linter.py::test_no_emdashes PASSED
tests/test_governance_linter.py::test_no_leaked_internal_fields PASSED
tests/test_governance_linter.py::test_brand_name_spelled_correctly PASSED
tests/test_intake_render_roundtrip.py::test_intake_data_appears_in_render PASSED

========================= 542 passed in 12.4s =========================

$ python health_check.py
[1/12] Imports: PASS
[2/12] Migrations: PASS
[3/12] App Boot + Chat: PASS
[4/12] Intake Round-Trip: PASS
[5/12] Site Data Projection: PASS
[6/12] Rendered Site Smoke Test: PASS
[7/12] Site A11y: PASS
[8/12] CORS Scoping: PASS
[9/12] Rate Limit: PASS
[10/12] Angel Prompt Load: PASS
[11/12] Demo Site Regressions: PASS (9/9 demos HTTP 200)
[12/12] Brand Palette Compliance: PASS (1 contrast warning)
========================= HEALTHY (12/12) ==========================
```

---

## Decision: Gates Are Mandatory, Not Optional

All five gates must pass before any merge to main. Exceptions:

1. **WCAG Contrast Warnings:** Known exceptions require explicit approval and documentation; otherwise inaccessible text and UI combinations fail the gate.

2. **Optional Field Omission:** If a customer doesn't provide a field at intake, it's correct that it's omitted from the rendered site (not filled with fake data).

No other exceptions.

---

## References

- `docs/IMPECCABLE_DEMO_VERIFICATION_PLAN.md` — 7-stage demo verification
- `docs/DECISIONS.md` ADR-022 - NetBuild.Pro house brand doctrine
- `docs/DECISIONS.md` ADR-020 — Em-dash governance rule
- `CLAUDE.md` — Engineering invariants, tenant scoping, no fabrication rule
- `tests/test_site_render_router.py` — Existing render tests (extend with gates)

---

**Document version:** 1.0  
**Last updated:** 2026-08-09  
**Status:** Design complete, ready for implementation
