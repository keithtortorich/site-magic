# Site Magic: Impeccable-Driven Site Renderer 2.0

**Status:** D3 Architecture (Impeccable integration into site generation pipeline)  
**Date:** 2026-08-03  
**What:** Complete end-to-end "Site Magic" pipeline: intake → direction engine → auto-generated beautiful websites

---

## The Site Magic Pipeline (7 Stages)

```
[INTAKE FORM]
    ↓
[SHAPE: Extract Intent] (Impeccable)
    ↓
[DIRECTION ENGINE: Visual Roll] (Impeccable)
    ↓ (direction locked: PRODUCT.md, DESIGN.md, surfaces/*.md)
[GENERATE: Render HTML/CSS] (site_renderer 2.0)
    ↓
[EVALUATE: Critique + Audit] (Impeccable)
    ↓ (quality gates: score ≥88, P0=0)
[SELF-HEAL: Auto-Refine Loop] (Impeccable)
    ↓ (quality achieved)
[SHIP: Harden + Deploy] (Impeccable + production build)
    ↓
[LIVE] → https://sites.webstaffr.com/{tenant_id}
```

---

## Stage 1: Intake Form

**Customer provides:**
- Company name
- Services offered
- City/location
- Contact info
- Photos/assets (optional)
- Brand style preference (optional)

**Output:** `IntakePayload` JSON

```typescript
interface IntakePayload {
  tenantId: string;
  company: string;
  services: string[];
  city: string;
  phone?: string;
  email?: string;
  website?: string;
  logoUrl?: string;
  brandStyle?: string;  // e.g., "professional tradesman, dark blue"
  photos?: string[];    // URLs to hero images
}
```

---

## Stage 2: SHAPE (Extract Intent)

**Impeccable Command:** `/impeccable shape`

**Input:** Customer data + form fields  
**Process:**
- Structured discovery interview (who, what, why, constraints)
- Outputs: `brief.md` (compass, not spec)

**In Site Magic:**
- Auto-answer from form data (no manual interview)
- Implicit brief: "{company} in {city}, {services}, professional trustworthy"

**Output:** `sites/{tenant_id}/brief.md`

---

## Stage 3: Direction Engine (Roll & Lock Visual Direction)

**Impeccable Command:** `/impeccable <prompt>, [brand_style]`

**Input:**
- brief.md (company purpose, audience, positioning)
- Optional brandStyle from intake form
- Existing PRODUCT.md + DESIGN.md (for brand re-rolls)

**Process:**
1. **Unattended mode** — no re-rolls, use first-pass direction
2. Generate direction contract with:
   - **THESIS** — One core idea + category default it rejects
   - **OWN-WORLD** — Palette + component language
   - **STORY** — Visitor narrative + primary conversion goal
   - **FIRST VIEWPORT** — Exact composition + primary action placement
   - **FORM & SEED** — Reproducible roll state

**Output:**
- `sites/{tenant_id}/PRODUCT.md` — Strategic context (who, what, why, positioning, evidence, constraints)
- `sites/{tenant_id}/DESIGN.md` — Visual system (Google Stitch format: colors, typography, components, tokens, design rules)
- `sites/{tenant_id}/.impeccable/surfaces/index.md` — Direction contract (150 words, 5 blocks)
- `sites/{tenant_id}/.impeccable/design.json` — Generated token metadata (do not edit)

**Key: Direction is LOCKED before code is written.** This is the seam between Impeccable and site_renderer.

---

## Stage 4: GENERATE (Render HTML/CSS to Direction)

**Engine:** `site_renderer.py` (version 2.0, direction-aware)

**Input:**
- Direction contract (DESIGN.md + surfaces/*.md)
- Customer data (company, services, city, contact, photos)
- Jinja2 templates

**Process:**

### 4.1 Load Direction Context
```python
def render_site(tenant_id: str, customer_data: dict):
    # Load direction files written by Impeccable
    design_md = load_design_md(f'sites/{tenant_id}/DESIGN.md')
    product_md = load_product_md(f'sites/{tenant_id}/PRODUCT.md')
    direction_contract = load_direction_contract(f'sites/{tenant_id}/.impeccable/surfaces/index.md')
    
    # Extract design tokens for template use
    colors = extract_colors(design_md)           # {primary: '#...', accent: '#...', ...}
    typography = extract_typography(design_md)  # {h1: 'font-family: X; font-size: Y; ...', ...}
    components = extract_components(design_md)  # {button: {...}, card: {...}, ...}
    
    context = {
        'customer': customer_data,
        'design': {
            'colors': colors,
            'typography': typography,
            'components': components,
            'direction': direction_contract,
        },
        'product': product_md,
    }
```

### 4.2 Render Templates Honoring Direction
```python
    # Template system picks components + styling from DESIGN.md
    # NOT from hardcoded defaults
    
    pages = {
        'index.html': render_template('templates/hero.html', context),
        'services.html': render_template('templates/services.html', context),
        'about.html': render_template('templates/about.html', context),
        'contact.html': render_template('templates/contact.html', context),
    }
    
    # Write CSS root variables from design tokens
    write_design_tokens_css(colors, typography, f'sites/{tenant_id}/web/tokens.css')
    
    # Save all pages
    for filename, html in pages.items():
        (Path(f'sites/{tenant_id}/web') / filename).write_text(html)
```

### 4.3 Template Design (Jinja2)
```html
<!-- templates/hero.html -->
<section class="hero" style="background: var(--color-primary);">
  <h1 style="{{ design.typography.h1 }}">
    {{ customer.company }} — {{ services_summary }}
  </h1>
  <p>
    {{ customer.city }} • {{ customer.phone }}
  </p>
  <button class="cta">
    Call Now
  </button>
</section>

<style>
  :root {
    /* Loaded from DESIGN.md extracted tokens */
    {% for color_name, color_value in design.colors.items() %}
      --color-{{ color_name }}: {{ color_value }};
    {% endfor %}
    
    {% for typo_name, typo_value in design.typography.items() %}
      --typo-{{ typo_name }}: {{ typo_value }};
    {% endfor %}
  }
  
  .hero {
    /* Layout from FIRST VIEWPORT in direction contract */
    display: grid;
    grid-template-columns: 1fr;
    gap: var(--spacing-lg);
    padding: var(--spacing-xl);
  }
</style>
```

**Output:** HTML/CSS files in `sites/{tenant_id}/web/`

---

## Stage 5: EVALUATE (Critique + Audit)

**Impeccable Commands:**
- `/impeccable critique --json`
- `/impeccable audit --json`

**Input:** Generated site (`sites/{tenant_id}/web/`)

**Process:**

### 5.1 Critique (Design Review)
```bash
cd sites/{tenant_id}
npx impeccable critique --json
```

Returns:
- `overallScore` (0–100)
- Persona fit (does it work for stated audience?)
- Visual hierarchy assessment
- AI-slop detection (gradient-text, nested-cards, etc.)
- Specific issues: typography, spacing, color, motion, copy

### 5.2 Audit (Implementation Review)
```bash
npx impeccable audit --json
```

Returns:
- P0–P3 severity findings (critical, high, medium, low)
- Accessibility checks (WCAG AA, contrast, touch targets)
- Responsive breakage
- Performance anti-patterns
- Anti-pattern catalog (glow, shimmer, fabricated data)

**Output:** JSON with scores and issue lists

---

## Stage 6: SELF-HEAL (Autonomous Refinement Loop)

**Impeccable Commands:** `/impeccable typeset`, `/impeccable layout`, `/impeccable colorize`, `/impeccable clarify`, `/impeccable bolder`, `/impeccable quieter`, `/impeccable polish`, etc.

**Process:**

```typescript
async function selfHealLoop(workdir: string): Promise<number> {
  const MAX_ATTEMPTS = 4;
  const TARGET_SCORE = 88;
  let currentScore = 0;
  
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    // Get latest critique
    const critique = JSON.parse(
      execSync('npx impeccable critique --json', { cwd: workdir }).toString()
    );
    
    currentScore = critique.overallScore || 0;
    const issuesText = (critique.issues || []).join(' ').toLowerCase();
    
    // Check gates
    if (currentScore >= TARGET_SCORE) {
      console.log(`✓ Quality gate met at iteration ${attempt}`);
      break;
    }
    
    // DECISION MATRIX: Route to specific command
    if (issuesText.includes('typography')) {
      execSync('npx impeccable typeset', { cwd: workdir });
    } else if (issuesText.includes('layout') || issuesText.includes('spacing')) {
      execSync('npx impeccable layout', { cwd: workdir });
    } else if (issuesText.includes('color') || issuesText.includes('bland')) {
      execSync('npx impeccable colorize', { cwd: workdir });
    } else if (issuesText.includes('confusing') || issuesText.includes('copy')) {
      execSync('npx impeccable clarify', { cwd: workdir });
    } else if (currentScore < 60) {
      execSync('npx impeccable bolder', { cwd: workdir });
    } else {
      execSync('npx impeccable polish', { cwd: workdir });
    }
  }
  
  return currentScore;
}
```

**Quality Gate:**
```typescript
if (currentScore >= 88 && auditP0 === 0) {
  proceed to Stage 7 (SHIP)
} else if (attempt >= MAX_ATTEMPTS) {
  escalate to human review (flag for founder)
} else {
  continue loop
}
```

**Output:** Refined HTML/CSS (ready for hardening)

---

## Stage 7: SHIP (Harden + Deploy)

**Impeccable Commands:**
- `/impeccable audit` (final check)
- `/impeccable harden` (edge cases, responsive)
- `/impeccable polish` (final refinement)
- `/impeccable document` (refresh DESIGN.md)

**Process:**

```bash
# Final checks
npx impeccable audit

# Production hardening
npx impeccable harden
npx impeccable polish

# Update DESIGN.md with actual generated tokens
npx impeccable document

# Build production assets
npm run build:site

# Deploy to Vercel/hosting
# (TODO: wire deployment)
```

**Output:**
- Production-optimized HTML/CSS
- Refreshed DESIGN.md (source of truth)
- Live URL: `https://sites.webstaffr.com/{tenant_id}`

---

## File Structure: Generated Site

```
sites/{tenant_id}/
├── PRODUCT.md                      # Strategy: who, what, why, positioning, evidence
├── DESIGN.md                       # Visual system: colors, typography, components, tokens, rules
├── brief.md                        # Original customer brief (compass)
├── .impeccable/
│   ├── config.json                 # Detector ignores, hook config
│   ├── design.json                 # Generated: tokens, ramps (DO NOT EDIT)
│   ├── surfaces/
│   │   └── index.md                # Direction contract (THESIS, OWN-WORLD, STORY, FIRST VIEWPORT, FORM)
│   └── hook.ndjson                 # Audit log (optional)
│
├── web/                            # Production output
│   ├── index.html
│   ├── services.html
│   ├── about.html
│   ├── contact.html
│   ├── style.css
│   ├── tokens.css                  # Generated: design tokens as CSS custom properties
│   └── images/
│
└── .impeccable_build.log           # Build log (all stages, all commands)
```

---

## Quality Gates & Termination Conditions

| Gate | Metric | Target | Meaning |
|---|---|---|---|
| **Critique Score** | overallScore | ≥ 88 / 100 | Passes Nielsen heuristics, persona tests, AI-slop detector |
| **Audit P0 Issues** | P0 count | = 0 | Zero critical accessibility/performance/anti-pattern failures |
| **Max Iterations** | attempts | ≤ 4 | Fail-safe: terminates and escalates if thresholds not met |

**Termination:**
```
if (critiqueScore >= 88 AND auditP0 === 0) {
  → SHIP (proceed to hardening + deployment)
} else if (attempt > MAX_ATTEMPTS) {
  → ESCALATE (flag for human review, log to founder)
} else {
  → LOOP (repeat self-heal)
}
```

---

## Decision Matrix: Auto-Heal Routing

When critique reveals issues, route to the right Impeccable command:

| Finding | Command | Fixes |
|---|---|---|
| Typography messy, hierarchy broken | `/impeccable typeset` | Font scale, line-height, font-weight rhythm |
| Spacing/alignment inconsistent | `/impeccable layout` | Grid, margins, padding, whitespace |
| Color boring, looks plain | `/impeccable colorize` | Adds intentional accents per direction |
| Text overflow, confusing UX, copy issues | `/impeccable clarify` | Rewrites copy, fixes component sizing |
| Safe, timid, generic appearance | `/impeccable bolder` | Pushes contrast, scale, visual impact |
| Too loud, chaotic, overstimulating | `/impeccable quieter` | Reduces visual noise, restores balance |
| Responsive breakage, mobile issues | `/impeccable adapt` + `/impeccable harden` | Fixes mobile views, responsive fallbacks |
| Multiple issues (catch-all) | `/impeccable polish` | General refinement pass |

---

## Integration: site_renderer.py 2.0

### Changes from 1.0

**Before (1.0):**
- Static templates with hardcoded colors/fonts
- No design context awareness
- Manual polish passes needed

**After (2.0):**
- Reads DESIGN.md + direction contract before rendering
- Extracts design tokens and passes to templates
- Renders CSS custom properties from DESIGN.md
- No hardcoded color/font values; all from tokens

### Key Implementation Points

1. **Load direction context at startup**
   ```python
   design_md = load_design_md(f'sites/{tenant_id}/DESIGN.md')
   design_tokens = extract_tokens(design_md)
   ```

2. **Pass to template context**
   ```python
   context = {
       'design': {
           'colors': design_tokens['colors'],
           'typography': design_tokens['typography'],
           'components': design_tokens['components'],
       },
       'customer': customer_data,
   }
   ```

3. **Write CSS root variables**
   ```python
   css_vars = ':root {\n'
   for name, value in design_tokens['colors'].items():
       css_vars += f'  --color-{name}: {value};\n'
   # ... typography, spacing, etc.
   Path(f'sites/{tenant_id}/web/tokens.css').write_text(css_vars)
   ```

4. **Template uses CSS variables**
   ```html
   <button class="cta" style="background: var(--color-accent);">
   <h1 style="font-family: var(--typo-h1-family); font-size: var(--typo-h1-size);">
   ```

---

## Monitoring & Observability

### Build Log
```bash
cat sites/{tenant_id}/.impeccable_build.log
```

Tracks all 7 stages, timestamps, command outputs, errors.

### Critique & Audit Results
```bash
cd sites/{tenant_id}
npx impeccable critique --json > critique.json
npx impeccable audit --json > audit.json
```

### Metrics Per Site
- **Time to live:** Start to finish (target: < 5 min)
- **Final critique score:** 0–100 (target: ≥ 88)
- **P0 issues:** Count (target: 0)
- **Self-heal iterations:** Count (target: ≤ 2, efficiency metric)
- **Cost:** gpt-image-2 calls if direction mocks enabled (target: < $0.50)

### Fleet-Wide Metrics
- **Success rate:** % sites reaching quality gates (target: ≥ 95%)
- **Manual escalation rate:** % sites flagged for human review (target: < 5%)
- **Average time:** Across all sites (target: < 5 min)
- **Cost per site:** Average across fleet

---

## Error Handling & Escalation

| Scenario | Action |
|---|---|
| Direction engine fails | Log error, escalate to founder (D4: new customer intake) |
| site_renderer crashes | Log error, escalate to founder (implementation bug) |
| Critique/audit unavailable | Retry once; if still fails, escalate (Impeccable CLI issue) |
| Score < 88 after 4 attempts | Escalate: site generated but quality insufficient, needs manual review |
| P0 issues present after harden | Escalate: critical issues remain, cannot ship |
| Deployment fails | Escalate: site generated fine, infrastructure issue |

**Escalation:** Log full build output + critique/audit JSON + site files to founder's dashboard (TBD: implement escalation UI).

---

## Phase Rollout

### Phase 1: Foundation (This Week)
- [x] Design architecture (this document)
- [ ] Install Impeccable, init, document
- [ ] Implement site-maker-engine.ts (stages 1–7 orchestrator)
- [ ] Update site_renderer.py 2.0 (load direction context)
- [ ] Dry-run end-to-end

### Phase 2: Critique Loop (Week 2)
- [ ] Wire critique + audit (stages 5–6)
- [ ] Test with 3 real customer intakes
- [ ] Tune quality gates & decision matrix

### Phase 3: Direction Engine with Visual Mocks (Week 3–4)
- [ ] Set OPENAI_API_KEY for gpt-image-2
- [ ] Test direction roll + visual rendering
- [ ] Measure cost per site

### Phase 4: Live Mode & Manual Iteration (Deferred)
- [ ] Evaluate `/impeccable live` for high-touch workflows
- [ ] Customer-facing direction picker UI (optional)

---

## Success Criteria (Phase 1)

- [ ] Impeccable installed + init run
- [ ] PRODUCT.md + DESIGN.md created
- [ ] site-maker-engine.ts implements all 7 stages
- [ ] site_renderer.py 2.0 reads direction context
- [ ] Dry-run completes without error
- [ ] Generated site has valid HTML/CSS
- [ ] Build log shows all stages executing
- [ ] Tests: 42/42 passing, health 10/10 HEALTHY
- [ ] Site can be shipped to production

---

## References

- **Impeccable Docs:** https://impeccable.style/
- **Magic Upgrade Architecture:** IMPECCABLE_MAGIC_UPGRADE.md
- **Implementation Runbook:** IMPECCABLE_IMPLEMENTATION.md
- **Cheat Sheet:** IMPECCABLE_CHEAT_SHEET.md
- **Site Renderer Docs:** docs/SITE_RENDERER_PLAN.md
- **Engineering Invariants:** CLAUDE.md (tenant isolation, composition root, etc.)

---

**Status:** Ready for Phase 1 implementation. No approval needed to begin.
