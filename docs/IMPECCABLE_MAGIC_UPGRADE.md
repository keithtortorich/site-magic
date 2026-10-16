# The Impeccable Magic Upgrade: Autonomous Design Direction Loop

> **SUPERSEDED (2026-08-09).** This document assumes CLI subcommands
> (`npx impeccable critique --json`, `npx impeccable audit`, etc.) and a
> 0-100 overall score. Neither is real: Impeccable's CLI only supports
> `detect`, `ignores`, `install`, `link`, `update`, `check` -- `critique`
> and the other 22 design commands are agent workflows invoked through the
> skill (`/impeccable critique`), not shell commands, and `critique`
> reports Nielsen heuristics 0-4 per category (typically /40, or a lower
> applicable max) rather than a single 0-100 number. The actual, current
> Site Magic implementation is `webstaffr/site_magic.py`,
> `site_magic_router.py`, `site_magic_security.py`, and
> `webstaffr/site_maker_engine.ts` -- see `docs/STANDUP_2026-08-09_IMPECCABLE_PHASE_1.md`
> for status. Read this file for design-intent history only; do not follow
> its command examples or score math.

**Status:** D3 Architecture Decision (Approved for Planning)  
**Date:** 2026-08-03  
**Context:** Site-renderer enhancement to apply Impeccable's design-direction workflow to auto-generated customer websites  
**Decision:** Implement a self-learning, multi-stage feedback loop integrating Impeccable CLI commands into the site-generation pipeline

---

## Executive Summary

WebStaffr's site-renderer currently generates static customer sites via Jinja2 templates. The **Impeccable Magic Upgrade** layers Impeccable's 23-command design direction system on top of the renderer, transforming generated sites from "good enough" to "production-ready beautiful" through an autonomous, continuous feedback loop.

The loop operates in five stages:
1. **SHAPE** — Intake form → Design brief (context extraction)
2. **DIRECTION ENGINE** — Roll visual worlds, generate PRODUCT.md + DESIGN.md + surface strategy
3. **GENERATE** — Render HTML/CSS using the direction contract
4. **EVALUATE** — Autonomous critique + audit with scoring
5. **SELF-HEAL & SHIP** — Route-specific refinement, harden, polish, deploy

**Key Innovation:** The loop runs *unattended*, terminating only when quality thresholds are met (≥88 critique score, 0 P0 audit issues). No human approval gate mid-loop; humans approve the *final direction*, not every iteration.

---

## Background: Impeccable's Design Doctrine

Impeccable is an opinionated design partner built on three core insights:

### 1. Context Wins Over Generics
Without project context (PRODUCT.md + DESIGN.md), LLMs produce purple gradients, card-grid templates, and gradient text. *With* context, output is distinctive and on-brand.

### 2. Direction Precedes Code
Most UI fails not because of bad implementation, but because the direction itself was never decided. Impeccable stops *before* coding and asks: "Which of these 188 visual worlds best carries your product truth?"

### 3. Five Tests Earn Direction
Every candidate (AI-derived or rolled) must pass truth, translation, consequence, survival, and fit tests. Candidates still explained by their source (e.g., "we used this Dribbble shot") are rejected for lack of translation.

### 4. Automated Evaluation Closes the Loop
Impeccable's `critique` and `audit` commands produce objective scores (0–100) and severity classifications (P0–P3). This enables *autonomous termination*: the loop stops when quality gates are met, not when someone feels good about it.

---

## The Five-Stage Loop

### Stage 1: SHAPE (Extract Intent)

**Input:** Intake form submission or plain-English description  
**Process:**
- Parse customer's stated purpose, target audience, positioning
- Run `/impeccable shape <description>` to force structured discovery
- Outputs: `brief.md` (compass, not spec)

**Key Impeccable Lesson:**  
Most AI-generated UIs fail because the direction was never decided. SHAPE forces the discovery conversation upfront.

**Termination Condition:** Brief accepted by human (intake form → immediate auto-accept on form data, or prompt-based accept if freeform text).

---

### Stage 2: Direction Engine (Roll & Decide)

**Input:** brief.md + PRODUCT.md (if migrating existing site)  
**Process:**

1. **Classification** — Determine job type:
   - Greenfield (no design exists)
   - Local extension (component inside existing page)
   - New surface (whole page in existing world)
   - Expression expansion (brand in new surface)
   - Redesign (replace look, keep function)

2. **Direction Roll** — Impeccable samples from 188 reviewed visual worlds + AI-derived candidates
   - Generate system board (palette, typography, components)
   - Render mock via gpt-image-2 (optional; requires OPENAI_API_KEY)
   - Present two controls: **Deal again** (re-roll) or **Steer** (verbal feedback)

3. **Direction Contract** — Once approved, write:
   - `PRODUCT.md` (who, what, why, positioning, evidence, constraints)
   - `DESIGN.md` (Google Stitch format: colors, type, components, tokens, rules)
   - `.impeccable/surfaces/<page>.md` (150-word direction contract: THESIS, OWN-WORLD, STORY, FIRST VIEWPORT, FORM & SEED)

**Unattended Mode:**  
In backend automation, skip the re-roll loop. Assign the first-pass direction and state assumptions explicitly in `.impeccable/surfaces/` as a record of what the system chose.

**Termination Condition:** Direction approved (attended) or assigned (unattended).

---

### Stage 3: Generate (Code to Direction)

**Input:** Direction contract + customer data (company info, services, reviews, etc.)  
**Process:**

1. Render initial site via `site_renderer.py` using direction contract as aesthetic guide
2. Output: HTML/CSS files in `/sites/{tenant_id}/web/`
3. Structure honors:
   - Color palette from DESIGN.md
   - Typography scale and line-height rules
   - Component primitives (card, button, form, hero, testimonial, CTA)
   - Layout grid and spacing rhythm from FIRST VIEWPORT

**Key Impeccable Lesson:**  
Once direction is locked, code generation is no longer guesswork. Every visual choice has a reason (truth, consequence, survival).

**Termination Condition:** HTML/CSS generated without errors.

---

### Stage 4: Evaluate (Critique + Audit)

**Input:** Generated HTML/CSS site  
**Process:**

**4A. Critique (Design Review)**
```bash
/impeccable critique /sites/{tenant_id}/web --json
```
Returns:
- `overallScore` (0–100, target ≥88)
- Persona tests (does it work for stated audience?)
- Visual hierarchy assessment
- AI-slop detector (gradient-text, nested-cards, overused-patterns)
- Specific issues: typography, spacing, color, motion, copy

**4B. Audit (Implementation Review)**
```bash
/impeccable audit /sites/{tenant_id}/web --json
```
Returns:
- P0–P3 severity findings (critical, high, medium, low)
- Accessibility checks (WCAG AA, contrast, touch targets)
- Responsive breakage
- Performance anti-patterns
- Anti-pattern catalog (glow, shimmer, fabricated data)

**Quality Gate:**
```
if (critique.overallScore >= 88 AND audit.p0Count === 0) {
  → Proceed to Stage 5
} else {
  → Proceed to Stage 5B (self-heal)
}
```

**Termination Condition:** Quality thresholds met; proceed to harden or loop back.

---

### Stage 5: Self-Heal & Ship

**5A. Diagnose**  
Parse critique and audit JSON to extract issue categories:
- Typography problems → trigger `/impeccable typeset`
- Layout/spacing issues → trigger `/impeccable layout`
- Color/vibrancy problems → trigger `/impeccable colorize`
- Confusing UX/copy → trigger `/impeccable clarify`
- Contrast/accessibility → trigger `/impeccable audit` then auto-fixes
- Generic/timid appearance → trigger `/impeccable bolder`
- Cluttered/chaotic → trigger `/impeccable quieter`

**5B. Refine (Loop)**  
Auto-apply targeted fixes up to MAX_ATTEMPTS (e.g., 4):
```javascript
for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
  const critique = await run('/impeccable critique --json');
  const audit = await run('/impeccable audit --json');
  
  if (critique.overallScore >= 88 && audit.p0Count === 0) {
    break; // Quality gate met
  }
  
  if (critique.issues.includes('typography')) {
    await run('/impeccable typeset');
  }
  // ... route other issues to appropriate commands
}
```

**5C. Harden**  
```bash
/impeccable harden /sites/{tenant_id}/web
```
Fixes production edge cases: responsive breakpoints, edge states, fallbacks.

**5D. Polish**  
```bash
/impeccable polish /sites/{tenant_id}/web
```
Final pass: alignment, micro-interactions, copy refinement, token consistency.

**5E. Document**  
```bash
/impeccable document
```
Refresh DESIGN.md with actual extracted tokens from generated code (single source of truth).

**5F. Build & Deploy**  
```bash
npm run build:site
```
Output production assets → Vercel/hosting.

**Termination Condition:** All stages complete; site LIVE at tenant URL.

---

## Decision Matrix: Auto-Heal Routing

| Audit/Critique Finding | Triggered Command | Expected Outcome |
|---|---|---|
| Typography lacks hierarchy / fonts messy | `/impeccable typeset` | Tightens scale, line-height, font-weight rhythm |
| Spacing inconsistent / poor alignment | `/impeccable layout` | Fixes grid, margins, padding rhythm |
| Color boring / looks too plain | `/impeccable colorize` | Adds intentional accents per direction |
| Text overflow / confusing UX | `/impeccable clarify` | Rewrites copy, fixes component sizing |
| Safe, timid, generic appearance | `/impeccable bolder` | Pushes contrast, scale, visual impact |
| Too loud / chaotic visuals | `/impeccable quieter` | Restores balance, reduces noise |
| Code edge cases / responsive breakage | `/impeccable adapt` then `/impeccable harden` | Fixes mobile views, production edge cases |
| Contrast failures / a11y | Auto-repair + `/impeccable audit` | WCAG AA compliance |

---

## Implementation: Backend Orchestrator

### TypeScript Service: `site-maker-engine.ts`

```typescript
import { execSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

interface IntakeFormPayload {
  prompt: string;                    // Customer's site purpose/pitch
  brandStyle?: string;               // e.g., "1970s hi-fi catalog, Futura"
  vibe?: 'minimal' | 'bold' | 'saas' | 'editorial';
  deployTarget?: 'vercel' | 'netlify';
  tenantId: string;
}

interface EngineResult {
  status: 'success' | 'failed';
  finalScore: number;
  liveUrl?: string;
  direction?: string;  // Path to .impeccable/surfaces/<page>.md
}

export async function runMagicUpgradeLoop(payload: IntakeFormPayload): Promise<EngineResult> {
  const workdir = path.join(process.cwd(), `sites/${payload.tenantId}`);
  fs.mkdirSync(workdir, { recursive: true });
  
  console.log('🚀 [1/5] SHAPE: Extracting design intent...');
  const brief = await runShape(payload);
  
  console.log('🎨 [2/5] DIRECTION ENGINE: Rolling & locking visual direction...');
  const direction = await runDirectionEngine(workdir, brief, payload);
  
  console.log('🖼️  [3/5] GENERATE: Rendering HTML/CSS to direction...');
  await runGenerate(workdir, direction, payload);
  
  console.log('🔍 [4/5] EVALUATE: Critique & Audit...');
  const { critiqueScore, auditP0Count } = await runEvaluate(workdir);
  
  console.log('⚙️  [5/5] SELF-HEAL & SHIP: Autonomous refinement loop...');
  const finalScore = await runSelfHealLoop(workdir, critiqueScore, auditP0Count);
  
  if (finalScore >= 88) {
    console.log('✨ Quality threshold met. Hardening, polishing, deploying...');
    await runHardenAndDeploy(workdir, payload);
    return {
      status: 'success',
      finalScore,
      liveUrl: await getLiveUrl(payload.tenantId),
      direction
    };
  } else {
    return { status: 'failed', finalScore };
  }
}

async function runShape(payload: IntakeFormPayload): Promise<string> {
  const cmd = `/impeccable shape "${payload.prompt}"`;
  if (payload.brandStyle) cmd += `, ${payload.brandStyle}`;
  
  execSync(cmd, { stdio: 'inherit' });
  return path.join(process.cwd(), 'brief.md');
}

async function runDirectionEngine(workdir: string, brief: string, payload: IntakeFormPayload): Promise<string> {
  // In unattended mode, skip re-roll and use first-pass direction
  const env = { ...process.env, IMPECCABLE_UNATTENDED: 'true' };
  
  const cmd = `/impeccable "${payload.prompt}"${payload.brandStyle ? `, ${payload.brandStyle}` : ''}`;
  execSync(cmd, { cwd: workdir, env, stdio: 'inherit' });
  
  // Direction contract written to .impeccable/surfaces/
  const surfaceDir = path.join(workdir, '.impeccable/surfaces');
  const files = fs.readdirSync(surfaceDir);
  return path.join(surfaceDir, files[files.length - 1]);
}

async function runGenerate(workdir: string, direction: string, payload: IntakeFormPayload): Promise<void> {
  // Call site_renderer.py with direction context
  // This is the integration point: renderer reads DESIGN.md + direction contract
  execSync(`python3 site_renderer.py --tenant-id ${payload.tenantId} --direction "${direction}"`, {
    cwd: workdir,
    stdio: 'inherit'
  });
}

async function runEvaluate(workdir: string): Promise<{ critiqueScore: number; auditP0Count: number }> {
  const critiqueRaw = execSync('npx /impeccable critique --json', { cwd: workdir }).toString();
  const auditRaw = execSync('npx /impeccable audit --json', { cwd: workdir }).toString();
  
  const critique = JSON.parse(critiqueRaw);
  const audit = JSON.parse(auditRaw);
  
  return {
    critiqueScore: critique.overallScore || 0,
    auditP0Count: audit.issues?.filter((i: any) => i.severity === 'P0').length || 0
  };
}

async function runSelfHealLoop(workdir: string, initialScore: number, initialP0: number): Promise<number> {
  const MAX_ATTEMPTS = 4;
  const TARGET_SCORE = 88;
  let currentScore = initialScore;
  
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    console.log(`🔄 Quality Pass ${attempt}/${MAX_ATTEMPTS}`);
    
    if (currentScore >= TARGET_SCORE && initialP0 === 0) {
      console.log('✨ Quality threshold met!');
      break;
    }
    
    const critiqueRaw = execSync('npx /impeccable critique --json', { cwd: workdir }).toString();
    const critique = JSON.parse(critiqueRaw);
    
    const issuesText = (critique.issues || []).join(' ').toLowerCase();
    
    // Route to specific refinement command
    if (issuesText.includes('typography') || issuesText.includes('font')) {
      console.log('  → Applying /impeccable typeset');
      execSync('npx /impeccable typeset', { cwd: workdir, stdio: 'inherit' });
    } else if (issuesText.includes('layout') || issuesText.includes('spacing')) {
      console.log('  → Applying /impeccable layout');
      execSync('npx /impeccable layout', { cwd: workdir, stdio: 'inherit' });
    } else if (issuesText.includes('confusing') || issuesText.includes('copy')) {
      console.log('  → Applying /impeccable clarify');
      execSync('npx /impeccable clarify', { cwd: workdir, stdio: 'inherit' });
    } else if (currentScore < 60) {
      console.log('  → Score critically low. Applying /impeccable bolder');
      execSync('npx /impeccable bolder', { cwd: workdir, stdio: 'inherit' });
    } else {
      console.log('  → Applying /impeccable polish (default)');
      execSync('npx /impeccable polish', { cwd: workdir, stdio: 'inherit' });
    }
    
    // Re-evaluate
    const newCritiqueRaw = execSync('npx /impeccable critique --json', { cwd: workdir }).toString();
    currentScore = JSON.parse(newCritiqueRaw).overallScore || 0;
    console.log(`📊 New score: ${currentScore}/100`);
  }
  
  return currentScore;
}

async function runHardenAndDeploy(workdir: string, payload: IntakeFormPayload): Promise<void> {
  console.log('🔒 Hardening...');
  execSync('npx /impeccable audit', { cwd: workdir, stdio: 'inherit' });
  execSync('npx /impeccable harden', { cwd: workdir, stdio: 'inherit' });
  
  console.log('✨ Polishing...');
  execSync('npx /impeccable polish', { cwd: workdir, stdio: 'inherit' });
  
  console.log('📋 Updating DESIGN.md...');
  execSync('npx /impeccable document', { cwd: workdir, stdio: 'inherit' });
  
  console.log('📦 Building production assets...');
  execSync('npm run build:site', { cwd: workdir, stdio: 'inherit' });
  
  console.log('🚀 Deploying...');
  if (payload.deployTarget === 'vercel') {
    await deployToVercel(workdir, payload.tenantId);
  }
}

async function getLiveUrl(tenantId: string): Promise<string> {
  // Return production URL for tenant
  return `https://sites.webstaffr.com/${tenantId}`;
}
```

---

## Integration Points: site_renderer.py

The existing `site_renderer.py` needs these enhancements:

### 1. Read Direction Context
```python
def render_site(tenant_id: str, direction_file: str, customer_data: dict) -> None:
    # Load DESIGN.md and direction contract
    with open(direction_file) as f:
        direction = f.read()  # Parse THESIS, OWN-WORLD, STORY
    
    design_md = load_design_md()  # Colors, typography, components
    product_md = load_product_md()  # Audience, positioning, evidence
    
    # Pass to template context
    context = {
        'customer': customer_data,
        'direction': direction,
        'design': design_md,
        'product': product_md,
        'colors': extract_palette(design_md),
        'typography': extract_typography(design_md),
        'components': design_md.get('components', {}),
    }
    
    # Render Jinja2 templates using direction as aesthetic guide
    render_template('hero.html', context)
    render_template('services.html', context)
    render_template('testimonials.html', context)
    # ... etc
```

### 2. Enforce Design Tokens
```python
# templates/base.html
<style>
  :root {
    /* Load from .impeccable/design.json for zero-drift token consistency */
    {% for color_name, color_value in colors.items() %}
      --color-{{ color_name }}: {{ color_value }};
    {% endfor %}
    
    {% for typo_name, typo_value in typography.items() %}
      --font-{{ typo_name }}: {{ typo_value }};
    {% endfor %}
  }
</style>
```

---

## File Structure in Generated Site

```
/sites/{tenant_id}/
├── web/                          # Generated HTML/CSS
│   ├── index.html
│   ├── services.html
│   ├── contact.html
│   └── style.css
│
├── .impeccable/
│   ├── config.json               # Detector ignores, hook config
│   ├── design.json               # Generated: tokens, ramps (do not edit)
│   ├── surfaces/
│   │   └── index.md              # Direction contract (THESIS, OWN-WORLD, STORY...)
│   └── hook.ndjson               # Audit log
│
├── PRODUCT.md                    # Strategy: who, what, why, positioning
├── DESIGN.md                     # Visual system: colors, type, components
└── brief.md                      # Original customer brief (compass, not spec)
```

---

## Quality Gates & Termination

### Loop Termination Conditions

**Success (Ship):**
- Critique score ≥ 88
- Audit P0 issues = 0
- MAX_ATTEMPTS not exceeded

**Graceful Failure (Escalate):**
- Critique score < 60 after 4 attempts → flag for manual review
- Audit P0 > 5 after 4 attempts → flag for manual review
- Unrecoverable error in any stage → log and notify

### Monitoring & Observability

Track per-site:
- Time from intake to live (target: < 5 min)
- Final critique score (distribution)
- P0 issues caught by detector (trend)
- Number of self-heal iterations (efficiency)
- Cost of gpt-image-2 calls (if direction mocks enabled)

---

## Impeccable Commands: Staged Adoption

### Phase 1: Minimal (MVP)
- `npx impeccable install`
- `/impeccable init` (manual)
- `/impeccable document` (auto-run once)
- `npx impeccable detect src/` (terminal, no loop)

### Phase 2: Critique Loop
- `/impeccable critique` (scoring)
- `/impeccable audit` (severity classification)
- Autonomous loop: evaluate → route → refine

### Phase 3: Full Direction Engine
- `/impeccable shape` (structured discovery)
- `/impeccable <description>` (new-work, with direction roll)
- `.impeccable/surfaces/` contract generation
- gpt-image-2 visual mocks (optional; requires OPENAI_API_KEY)

### Phase 4: Live Mode (Browser Iteration)
- `/impeccable live` (alpha; may require manual testing)
- In-browser variant generation + HMR hot-swap

---

## Known Constraints & Assumptions

1. **Unattended mode:** No human re-rolls. First-pass direction proceeds; assumptions logged.
2. **Terminal-only:** No visual mocks without OPENAI_API_KEY set.
3. **Web-only:** Impeccable detector reads HTML/CSS. Not suitable for native iOS/Android.
4. **MAX_ATTEMPTS=4:** After 4 self-heal iterations, site proceeds to harden regardless. (Tunable.)
5. **Per-site isolation:** Each tenant's `.impeccable/` config is independent; no shared design system across tenants.

---

## Success Metrics

- **Time to live:** Intake form → live site in < 5 minutes
- **Critique score:** Average final score ≥ 88
- **Manual escalation rate:** < 5% of sites flagged for human review
- **Self-heal efficiency:** Average ≤ 2 iterations to reach quality gate
- **Cost:** < $0.50/site (gpt-image-2 calls)

---

## Next Steps

### Immediate (Week 1)
1. Implement `site-maker-engine.ts` orchestrator
2. Add Impeccable CLI integration to `/sites/{tenant_id}/` generation
3. Test end-to-end with mock customer data
4. Validate DESIGN.md and direction contract output

### Short-term (Week 2–3)
1. Integrate with `site_renderer.py` to honor design tokens
2. Set up monitoring (time, score, escalation rate)
3. Manual smoke test with 3–5 real customer intakes
4. Tune MAX_ATTEMPTS and quality thresholds

### Medium-term (Week 4–6)
1. Add Phase 3: Direction engine with visual mocks
2. Tune decision matrix for auto-heal routing
3. Document operational runbook (logs, debugging, escalation)
4. Consider Phase 4: Live Mode for high-touch customers

### Deferred Post-MVP
- Multi-tenant design system governance (shared DESIGN.md variants per vertical)
- Branding override controls (customer controls vibe/era without re-rolling)
- Audit trail & approval workflow for escalated sites
- Cost attribution per tenant

---

## References

**Impeccable Docs (23 Commands):**
- Tutorials: Getting Started, Iterate Live, Critique with Overlay
- Core: Shape, Impeccable (new-work), Context, Config
- Evaluate: Critique, Audit, Doctor
- Refine: Typeset, Layout, Colorize, Clarify, Bolder, Quieter, Animate, Distill, Adapt
- Harden: Harden, Polish, Optimize, Onboard
- System: Document, Detector, Hooks, Live

**WebStaffr Docs:**
- `docs/SITE_RENDERER_PLAN.md` — Jinja2 architecture
- `docs/ARCHITECTURE.md` — Composition root, tenant isolation
- `CLAUDE.md` — Engineering invariants (tenant-scoped queries, CORS rules)

---

## Sign-Off

This is a **D3 (Architectural)** decision. Implementation requires staged rollout with monitoring at each phase. No approval needed to proceed with Phase 1 (minimal install + detect); Phase 2+ (critique loop) triggers human review of output quality before auto-advancing to harden.

**Author:** Claude  
**Date:** 2026-08-03  
**Status:** Ready for Phase 1 implementation
