# Impeccable Demo Verification Plan

**Purpose:** Establish a repeatable, trade-specific verification workflow for all 9 demo sites before customer launch. Each demo must pass a 7-stage Impeccable pipeline with per-trade validation gates.

**Status:** 2026-08-09, Planning Phase  
**Target:** All 9 demos verified and approved before merge to main

---

## The 8 Demo Sites

| # | Trade | File | Tenant ID | Status |
|---|-------|------|-----------|--------|
| 1 | HVAC | `site/demos/hvac.html` | `demo-hvac` | Pending |
| 2 | Plumbing | `site/demos/plumbing.html` | `demo-plumbing` | Pending |
| 3 | Roofing | `site/demos/roof.html` | `demo-roof` | Pending |
| 4 | Landscaping | `site/demos/landscape.html` | `demo-landscape` | Pending |
| 5 | Pest Control | `site/demos/pest.html` | `demo-pest` | Pending |
| 6 | Garage Doors | `site/demos/garage.html` | `demo-garage` | Pending |
| 7 | Tree Service | `site/demos/arbor.html` | `demo-arbor` | Pending |
| 8 | Water Damage | `site/demos/waterrestore.html` | `demo-waterrestore` | Pending |

---

## 7-Stage Impeccable Verification Pipeline

### Stage 1: SHAPE (Intent Extraction)

**Goal:** Validate that each demo's intake data correctly expresses its trade, services, and brand intent.

**Checklist per demo:**
- [ ] Industry slug matches trade (e.g., `industry: "HVAC Technician"`)
- [ ] Services list is complete for that trade (not generic, not missing key offerings)
- [ ] Tagline is unique to trade, not copy-paste boilerplate
- [ ] Differentiator is specific and believable (e.g., "24/7 emergency response" for HVAC, not for tree service)
- [ ] Service area is realistic for trade (HVAC in Phoenix is credible; tree service in downtown Manhattan is not)
- [ ] Brand colors are set and valid hex format (#rrggbb)
- [ ] Phone number is formatted consistently
- [ ] No prohibited terms or governance violations in intake data

**Sign-off:** All fields present, brand intent clear.

---

### Stage 2: DIRECTION ENGINE (Visual Rollout)

**Goal:** Verify that each site's visual direction matches its verified tenant brand and is appropriate for the trade. ADR-022's house palette applies only to NetBuild.Pro-owned surfaces.

**Checklist per demo:**
- [ ] Tenant primary color applied consistently
- [ ] Accent and hover states retain accessible contrast
- [ ] Action colors are visually clear and meet UI contrast requirements
- [ ] Neutral backgrounds support readable text contrast
- [ ] Logo visible and properly sized (if present)
- [ ] Typography hierarchy clear: H1 > H2 > H3 > body text
- [ ] No em-dashes in any copy (governance ADR-020)
- [ ] Layout responsive (visual direction works on mobile, tablet, desktop)

**Sign-off:** Brand doctrine applied, no governance violations.

---

### Stage 3: GENERATE (HTML/CSS Rendering)

**Goal:** Confirm the rendered HTML/CSS matches the direction and is free of markup errors.

**Checklist per demo:**
- [ ] HTTP 200 response when fetched at `/sites/{tenant_id}/web`
- [ ] Content-Type: text/html; charset=utf-8
- [ ] All expected sections present: header, hero, services, trust signals, CTA, footer
- [ ] Angel widget embed code present in footer (Retell snippet or placeholder)
- [ ] Business name appears in page title and heading
- [ ] Services are listed as interactive cards or grid
- [ ] Phone number is clickable (tel: link)
- [ ] Email is present (if provided at intake)
- [ ] No markup errors (W3C validator passes or only warnings)
- [ ] All internal links are absolute and correct (no 404s)

**Sign-off:** HTML renders clean, all content sections present, links work.

---

### Stage 4: EVALUATE (Critique + Audit)

**Goal:** Run design feedback and accessibility audits to catch quality issues before customer sees them.

**Checklist per demo:**

**Design Critique (via design-critique skill):**
- [ ] Visual hierarchy is clear (eyes know where to look first)
- [ ] CTA buttons are obvious and clickable (sufficient size, high contrast)
- [ ] Whitespace is used effectively (not cramped, not excessive)
- [ ] Color contrast meets WCAG AA (4.5:1 for normal text, 3:1 for large)
- [ ] Imagery (if present) is relevant and correctly sized
- [ ] Trust signals (reviews, ratings, certifications) are positioned prominently

**Accessibility Audit (via accessibility-review skill):**
- [ ] All images have alt text
- [ ] Form labels are associated with inputs
- [ ] Keyboard navigation works (Tab key moves through all interactive elements)
- [ ] Focus indicators are visible
- [ ] Color is not the only way to convey information (e.g., error state not just red)
- [ ] Text has sufficient line height and letter spacing
- [ ] Font size is at least 14px for body text

**Governance Linter (via governance-compliance-linter):**
- [ ] No em-dashes (literal or entity-encoded)
- [ ] No prohibited terms (depends on trade, but examples: "guaranteed," "best," "only")
- [ ] No leaked internal fields (lead_routing, approver, competitors, license_number)
- [ ] Brand name spelled "NetBuild.Pro" (not "NetBuild Pro" or other variant)

**SEO & Content Audit (via seo-audit skill):**
- [ ] Page title is unique and descriptive (not generic)
- [ ] Meta description is present and under 160 characters
- [ ] H1 appears exactly once on page
- [ ] Heading hierarchy is correct (no H1 → H3 jump)
- [ ] Internal linking is present (links to other services, related pages)
- [ ] Schema markup is present (LocalBusiness, Service, etc.)

**Sign-off:** Critique score ≥85/100, zero P0 audit issues, governance pass.

---

### Stage 5: SELF-HEAL (Autonomous Refinement)

**Goal:** If Stage 4 found issues, run automated fixes and re-evaluate until quality gates are met.

**Process:**
1. If critique score < 85, apply fixes: button sizing, whitespace, contrast
2. If audit has P0 issues, fix immediately: add missing alt text, fix heading hierarchy
3. If governance violations found, remove or rephrase offending copy
4. Re-run Stage 4 evaluation
5. Repeat until: critique ≥88 AND audit P0 count = 0

**Sign-off:** Quality gates met, no manual fixes needed.

---

### Stage 6: SHIP (Hardening & Deployment)

**Goal:** Finalize assets and prepare for live deployment.

**Checklist per demo:**
- [ ] All assets optimized (images compressed, CSS minified, JS bundled)
- [ ] Production secrets are not present (no API keys in HTML, no debug flags)
- [ ] Cache headers are set appropriately (static assets: 1 year, HTML: no-cache)
- [ ] Security headers are present (CSP, X-Frame-Options, etc.)
- [ ] Performance baseline recorded (Lighthouse score if applicable)
- [ ] Fallback assets present (if 3rd-party CDN fails, site still loads)

**Sign-off:** Ready for live traffic.

---

### Stage 7: VERIFICATION (Final Sign-Off)

**Goal:** Confirm the live rendered site matches all previous stages and is customer-ready.

**Checklist per demo:**
- [ ] Site loads from production endpoint in < 2 seconds
- [ ] All content from intake is correctly rendered
- [ ] No errors in browser console (F12 dev tools)
- [ ] No console.log or debug output visible
- [ ] All CTAs work (Call, Book, Email)
- [ ] Angel widget initializes (check browser console for Retell startup)
- [ ] Mobile responsive (test on iPhone SE, iPad, desktop)
- [ ] All links are clickable and lead to correct destinations
- [ ] Brand colors are consistent across all pages

**Sign-off:** Live, customer-ready.

---

## Verification Workflow (Per Demo)

### Phase A: Manual Review (15 min per demo)

1. **Fetch the live site:** `GET /sites/{tenant_id}/web`
2. **Run through Stage 1 checklist** (intake data)
3. **Visually inspect** (browser, mobile, F12 console)
4. **Document findings** in a trade-specific verification log

### Phase B: Automated Validation (5 min per demo)

1. **Run test suite:** `pytest tests/test_site_render_router.py -v`
2. **Run health check:** `python health_check.py`
3. **Run governance linter:** `governance-compliance-linter site/demos/{trade}.html`
4. **Check Angel embed:** Verify Retell snippet is present and script loads
5. **Capture results** (pass/fail per check)

### Phase C: Trade-Specific Audit (10 min per demo)

1. **Validate services list** against industry standard (HVAC should have: AC repair, install, maintenance; plumbing should have: leak repair, drain cleaning, etc.)
2. **Check trust signals** (reviews, ratings, certifications appropriate for trade)
3. **Verify differentiators** are credible (no implausible claims for that industry)
4. **Confirm service area** makes geographic sense

### Phase D: Design & A11y Audit (10 min per demo)

1. **Run design-critique skill** on rendered HTML
2. **Run accessibility-review skill** (WCAG 2.1 AA)
3. **Run seo-audit skill** (title, meta, schema, headings)
4. **Document score** (critique ≥85, audit P0 = 0, governance pass)

### Phase E: Final Approval (5 min per demo)

1. **Sign-off checklist:** All 7 stages complete, no blockers
2. **Escalate if:** Critique < 85 OR audit P0 > 0 OR governance violations
3. **Mark complete** in table above

**Total per demo:** ~45 minutes  
**Total for 8 demos:** ~6 hours (can parallelize)

---

## Quality Gates (Non-Negotiable)

| Gate | Threshold | Consequence |
|------|-----------|-------------|
| Critique Score | ≥88/100 | Do not ship if lower |
| Audit P0 Issues | 0 | Do not ship if any |
| Governance Pass | 100% | Do not ship if violations |
| HTTP 200 | All pages | Do not ship if any 4xx/5xx |
| Angel Embed | Present & loads | Do not ship if missing |
| Brand Colors | Correct for verified tenant direction | Do not ship if fabricated or inaccessible |
| Mobile Responsive | Pass | Do not ship if fails |

---

## Sign-Off Template (Per Demo)

```markdown
## {Trade} Demo Verification

**Date:** 2026-08-09  
**Reviewed by:** [Name]  
**Status:** [PASS / PASS WITH NOTES / FAIL]

### Stage 1: SHAPE
- [x] Industry slug correct
- [x] Services complete
- [x] No governance violations
**Sign-off:** PASS

### Stage 2: DIRECTION ENGINE
- [x] Brand colors correct (navy, blue, orange)
- [x] Typography hierarchy clear
- [x] No em-dashes
**Sign-off:** PASS

### Stage 3: GENERATE
- [x] HTTP 200
- [x] All sections present
- [x] Angel embed present
**Sign-off:** PASS

### Stage 4: EVALUATE
- [x] Critique score: 91/100
- [x] Audit P0 issues: 0
- [x] Governance: PASS
**Sign-off:** PASS

### Stage 5: SELF-HEAL
- [x] No fixes needed
**Sign-off:** N/A (gates already met)

### Stage 6: SHIP
- [x] Assets optimized
- [x] Security headers present
**Sign-off:** PASS

### Stage 7: VERIFICATION
- [x] Live site loads < 2 sec
- [x] All CTAs work
- [x] Mobile responsive
**Sign-off:** PASS

**Final Status:** ✅ APPROVED FOR LAUNCH
```

---

## Next Steps

1. **Run Phase A–E for each of 8 demos** (can parallelize across trades)
2. **Capture results** in a summary table (see VERIFICATION SUMMARY section below)
3. **Escalate any failures** to team for triage
4. **Once all 8 pass**, move to Phase 2: implement verification gates in test suite

---

## Verification Summary (To Be Completed)

| Demo | Stage 1 | Stage 2 | Stage 3 | Stage 4 | Stage 5 | Stage 6 | Stage 7 | Status |
|------|---------|---------|---------|---------|---------|---------|---------|--------|
| HVAC | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Plumbing | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Roofing | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Landscaping | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Pest Control | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Garage Doors | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Tree Service | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |
| Water Damage | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | ⏳ | Pending |

**Legend:** ✅ Pass | ⚠️ Pass with notes | ❌ Fail | ⏳ Pending

---

## Decision: Single-Pass Unattended Mode

Per IMPECCABLE_MAGIC_UPGRADE.md, demos run in **unattended mode**: no human approval gates between stages, quality checks are automated, and loop terminates only when gates are met.

**Rationale:**
- Founder's time is valuable; demo verification should not require mid-pipeline approval
- Quality gates are objective (critique score, audit P0 count, governance checks)
- Self-heal loop handles minor issues autonomously
- Final approval is only after all stages complete and gates are met

---

## References

- `docs/IMPECCABLE_MAGIC_UPGRADE.md` — Architecture and decision matrix
- `docs/IMPECCABLE_IMPLEMENTATION.md` — Setup runbook
- `docs/DECISIONS.md` ADR-022 - NetBuild.Pro house brand doctrine
- `docs/DECISIONS.md` ADR-020 — Em-dash governance rule
- `TASKS.md` — Session tracking and blockers

---

**Document version:** 1.0  
**Last updated:** 2026-08-09  
**Status:** Ready for Phase A execution
