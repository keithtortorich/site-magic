# Phase 4: Final Verification Checklist

**Purpose:** Confirm all systems pass before staging and pushing to main.

**Date:** 2026-08-09  
**Status:** Ready for execution

---

## Pre-Merge Verification Matrix

### ✅ Code Quality & Tests

- [ ] **Test Suite Passes:** `pytest tests/ -v` returns all green (target: 542+/542+ passing)
  - 8 new schema audit tests (Gate 1)
  - 8 new demo regression tests (Gate 2)
  - 6 new angel embed tests (Gate 3)
  - 8 new brand palette tests (Gate 4)
  - 7 new governance linter tests (Gate 5)
  - 9 new content freshness tests (Gate 6)
  - All existing tests remain passing

- [ ] **Health Check Passes:** `python scripts/health_check.py` returns HEALTHY
  - 10 original checks + 4 new gate checks = 14/14 HEALTHY
  - No new errors or warnings

- [ ] **No Regressions:** All previously passing checks still pass
  - Site rendering: home page, service pages, about, contact, robots.txt, sitemap.xml
  - Tenant scoping: intake round-trip, cross-tenant isolation
  - Data projection: no leaked internal fields
  - CORS headers: scoped correctly (browser-facing vs. server-to-server)
  - Accessibility: WCAG 2.1 AA labels, focus, contrast, heading order

### ✅ Demo Sites Verification

- [ ] **All 9 Demos HTTP 200:**
  - [ ] HVAC demo renders and contains expected content
  - [ ] Plumbing demo renders and contains expected content
  - [ ] Roofing demo renders and contains expected content
  - [ ] Landscaping demo renders and contains expected content
  - [ ] Pest Control demo renders and contains expected content
  - [ ] Garage Doors demo renders and contains expected content
  - [ ] Tree Service demo renders and contains expected content
  - [ ] Water Damage Restoration demo renders and contains expected content
  - [ ] Maid Service demo renders and contains expected content

- [ ] **Angel Embed Present:** first-party Angel widget script in footer on all demos

- [ ] **Tenant Colors Correct:** each demo honors its verified tenant palette; NetBuild.Pro house colors are not forced onto customer sites

- [ ] **No Governance Violations:** No em-dashes, no leaked internal fields on any demo

### ✅ Verification Gates Status

| Gate | Name | Test File | Status | Pass Criteria |
|------|------|-----------|--------|---------------|
| 1 | Schema Audit | `test_site_data_schema_audit.py` | [ ] | All required fields present, valid format |
| 2 | Regression Test | `test_site_render_router.py` (extended) | [ ] | 9/9 demos HTTP 200 |
| 3 | Angel Embed | `test_angel_embed_verification.py` | [ ] | first-party widget present and configured |
| 4 | Brand Palette | `test_brand_palette_audit.py` | [ ] | Colors correct, contrast ≥3:1 |
| 5 | Governance | `test_governance_linter.py` | [ ] | No em-dashes, no leaks, brand name correct |
| 6 | Content Freshness | `test_intake_render_roundtrip.py` | [ ] | All intake data persists in render |

### ✅ Documentation Complete

- [ ] **IMPECCABLE_DEMO_VERIFICATION_PLAN.md** — 7-stage pipeline, complete
- [ ] **VERIFICATION_GATES_PRE_MERGE.md** — 5 gates, implementation roadmap, complete
- [ ] **PHASE4_FINAL_VERIFICATION_CHECKLIST.md** — this file
- [ ] **TASKS.md** — Phase 1–4 progress updated
- [ ] **CLAUDE.md** — engineering invariants still satisfied
- [ ] **DECISIONS.md** - ADR-022 (current house brand) and ADR-020 (em-dash rule) documented

### ✅ Git Status Ready

- [ ] **No uncommitted changes** to tracked files (except TASKS.md)
- [ ] **Files staged for push:**
  - `site/index.html` (rebranded landing page)
  - `tests/test_*.py` (6 new test files)
  - `tests/test_site_render_router.py` (extended with demo regression class)
  - `webstaffr/templates/netbuild_pro.html` (rebranded site template)
  - `scripts/health_check.py` (integrated 4 new gate checks)
  - `docs/IMPECCABLE_DEMO_VERIFICATION_PLAN.md` (new)
  - `docs/VERIFICATION_GATES_PRE_MERGE.md` (new)
  - `docs/PHASE4_FINAL_VERIFICATION_CHECKLIST.md` (this file)
  - `TASKS.md` (updated progress)

### ✅ Security & Compliance

- [ ] **Tenant Isolation:** All queries scoped by tenant_id (verified in test_intake_render_roundtrip.py)
- [ ] **No Secrets:** No API keys, credentials, or tokens in commit
- [ ] **CORS Scoping:** Browser-facing routes only (/chat, /sites/*, /intake*); server-to-server routes (/book, /webhooks/*) carry no CORS headers
- [ ] **Internal Fields:** Never leaked (lead_routing, approver, competitors, license_number verified in governance linter)
- [ ] **No Fabrication:** Ratings, reviews, testimonials omitted if not submitted (perfect-site principle verified in content freshness tests)

### ✅ Performance & Scalability

- [ ] **Test Runtime:** Full suite < 15 seconds (measured after phase 3 implementation)
- [ ] **Health Check Runtime:** < 5 seconds
- [ ] **Demo Site Rendering:** Each demo < 500ms (smoke test in demo regression gate)
- [ ] **No Blocking Assets:** Angel widget loads async, CORS headers allow widget to load from customer sites

---

## Manual Verification Steps (Before Push)

### Step 1: Run Full Test Suite
```bash
cd /Users/doc/Desktop/NetBuild.Pro
pytest tests/ -v --tb=short
# Expected: All tests pass, no warnings
```

### Step 2: Run Health Check
```bash
python scripts/health_check.py
# Expected: HEALTHY (14/14), no errors
```

### Step 3: Verify Demo Sites Locally
```bash
# Create a test tenant and fetch a demo site
# (Manual: POST /intake, GET /sites/{tenant_id}/web)
# Expected: HTTP 200, brand colors correct, Angel embed present
```

### Step 4: Check Git Status
```bash
git status
# Expected: Only tracked files modified, no untracked files
git diff --stat
# Expected: 6 test files, 1 health check update, 3 doc updates
```

### Step 5: Confirm No Secrets Leaked
```bash
git diff HEAD | grep -E "(password|secret|key|token|credential)"
# Expected: No matches (grep returns 0)
```

---

## Sign-Off Criteria

All of the following must be true to proceed with push:

1. ✅ All 542+ tests passing (no regressions)
2. ✅ Health check 14/14 HEALTHY (all new gates pass)
3. ✅ All 8 demo sites HTTP 200 + Angel embed + brand colors correct
4. ✅ No governance violations (no em-dashes, no leaks, brand name correct)
5. ✅ No security issues (tenant scoping, no secrets, CORS correct)
6. ✅ Documentation complete (all 3 new doc files + TASKS.md updated)
7. ✅ Git status clean (only intended files staged)

---

## If Any Check Fails

**Do NOT push.** Instead:

1. **Identify the failure:** Run the failing test in isolation (`pytest tests/test_X.py::test_Y -v`)
2. **Analyze the error:** Read the detailed error message and stack trace
3. **Determine root cause:** Is it a code issue, a test issue, or an environmental issue?
4. **Fix:** Apply the minimal fix (not a refactor or redesign)
5. **Verify:** Re-run the failing test + full suite + health check
6. **Log:** Document the issue and fix in TASKS.md
7. **Retry:** Start from Step 1 above

**Blockers:**
- Test failure (code issue): Fix code, re-run suite
- Health check failure (configuration issue): Fix config or test expectation
- Security/compliance issue: Do not push; escalate to founder
- Git issue (uncommitted changes, stale branch): Resolve, then retry

---

## Next Steps After Sign-Off

Once all checks pass and gates are signed off:

1. **Stage files:** `git add <list of files>`
2. **Commit:** `git commit -m "feat: add verification gates and Impeccable pipeline docs"`
3. **Push:** `git push origin main`
4. **Deploy:** Vercel auto-deploys on push to main
5. **Verify:** Confirm deployment succeeds (Vercel dashboard)
6. **Mark Complete:** Update TASKS.md Phase 4 as complete, close session with summary

---

**Document version:** 1.0  
**Created:** 2026-08-09  
**Status:** Ready for Phase 4 execution
