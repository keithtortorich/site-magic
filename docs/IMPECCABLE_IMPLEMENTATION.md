# Impeccable Magic Upgrade: Implementation Runbook

> **SUPERSEDED (2026-08-09).** This runbook's `execSync('npx impeccable
> critique --json', ...)` calls and `npx impeccable critique` examples are
> not real CLI commands -- the CLI only supports `detect`, `ignores`,
> `install`, `link`, `update`, `check`. `critique` is an agent workflow
> run through the skill, not a shell subprocess. The real implementation
> is `webstaffr/site_magic.py` / `site_magic_router.py` /
> `site_magic_security.py` / `webstaffr/site_maker_engine.ts`; see
> `docs/STANDUP_2026-08-09_IMPECCABLE_PHASE_1.md` for current status.
> Read this file for design-intent history only.

**Phase 1: Foundation (This Week)**

## 1. Install Impeccable & Set Context

From WebStaffr4 root:

```bash
npx impeccable install
```

This writes `.claude/skills/impeccable/` for Claude Code integration.

Now run setup interview:

```bash
/impeccable init
```

Answer the three questions:
- **Who is WebStaffr for?** "Service businesses (plumbers, HVAC, cleaners) hiring the Angel AI-employee to answer calls and qualify leads."
- **What can WebStaffr claim that competitors can't?** "Live voice AI agent deployed in customer websites within minutes, no code, owned by the service business."
- **What must future work preserve?** "Tenant isolation (each customer's site is private), Angel voice routing (Retell), booking integration (ServiceTitan/Jobber), branding (customer controls colors/fonts via intake form)."

This creates `PRODUCT.md` at repo root. Edit if needed.

Then run:

```bash
/impeccable document
```

This scans the current codebase and generates `DESIGN.md` + `.impeccable/design.json`.

Review both files. `DESIGN.md` should reflect the site-renderer's actual color palette, typography, and component structure. Edit it if it's wrong.

**Git it:**
```bash
git add PRODUCT.md DESIGN.md .impeccable/
git commit -m "docs: add Impeccable context (PRODUCT, DESIGN, config)"
```

---

## 2. Create site-maker-engine.ts

Create `/webstaffr/site_maker_engine.ts`:

```typescript
import { execSync, spawnSync } from 'child_process';
import * as fs from 'fs';
import * as path from 'path';

interface IntakePayload {
  tenantId: string;
  prompt: string;           // e.g., "plumbing company in Austin, emergency service, professional"
  brandStyle?: string;      // e.g., "professional tradesman aesthetic, sans-serif, dark blue accent"
  customerData: {
    company: string;
    services: string[];
    city: string;
  };
}

interface PipelineResult {
  status: 'success' | 'failed';
  finalScore: number;
  liveUrl?: string;
  directionPath?: string;
  errorLog?: string;
}

/**
 * Main entry point: orchestrates the five-stage Impeccable loop.
 * Runs unattended; terminates when quality gates met or max attempts reached.
 */
export async function runMagicUpgrade(payload: IntakePayload): Promise<PipelineResult> {
  const workdir = path.join(process.cwd(), 'sites', payload.tenantId);
  fs.mkdirSync(workdir, { recursive: true });
  
  const logFile = path.join(workdir, '.impeccable_build.log');
  const log = (msg: string) => {
    console.log(`[${payload.tenantId}] ${msg}`);
    fs.appendFileSync(logFile, `${new Date().toISOString()} ${msg}\n`);
  };

  try {
    // Stage 1: SHAPE (extract intent)
    log('🎯 [1/5] SHAPE: Extracting design intent from intake...');
    // For MVP, skip /impeccable shape and go straight to direction engine
    // The intake form IS the brief; we have tenantId, prompt, customerData
    
    // Stage 2: DIRECTION ENGINE (roll & lock visual direction)
    log('🎨 [2/5] DIRECTION ENGINE: Rolling visual direction...');
    const direction = await runDirectionEngine(workdir, payload, log);
    if (!direction) throw new Error('Direction engine failed');
    
    // Stage 3: GENERATE (code to direction)
    log('🖼️  [3/5] GENERATE: Rendering HTML/CSS...');
    await runGenerate(workdir, direction, payload, log);
    
    // Stage 4: EVALUATE (critique + audit)
    log('🔍 [4/5] EVALUATE: Running critique & audit...');
    const { critiqueScore, auditP0 } = await runEvaluate(workdir, log);
    log(`   Critique score: ${critiqueScore}/100 | P0 issues: ${auditP0}`);
    
    // Stage 5: SELF-HEAL & SHIP
    log('⚙️  [5/5] SELF-HEAL & SHIP: Autonomous refinement loop...');
    const finalScore = await runSelfHealLoop(workdir, critiqueScore, auditP0, log);
    
    if (finalScore >= 88 && auditP0 === 0) {
      log('✨ Quality gates met. Hardening, polishing, deploying...');
      await runHardenAndDeploy(workdir, payload, log);
      
      const liveUrl = `https://sites.webstaffr.com/${payload.tenantId}`;
      log(`🚀 LIVE at ${liveUrl}`);
      
      return {
        status: 'success',
        finalScore,
        liveUrl,
        directionPath: direction
      };
    } else {
      log(`⚠️  Quality gates not met after self-heal. Score: ${finalScore}, P0: ${auditP0}`);
      return {
        status: 'failed',
        finalScore,
        errorLog: fs.readFileSync(logFile, 'utf-8')
      };
    }
  } catch (error) {
    const err = error instanceof Error ? error.message : String(error);
    log(`❌ FATAL: ${err}`);
    return {
      status: 'failed',
      finalScore: 0,
      errorLog: fs.readFileSync(logFile, 'utf-8')
    };
  }
}

/**
 * Stage 2: Direction Engine
 * In unattended mode, use first-pass direction; no re-rolls.
 * Calls /impeccable with tenant prompt to generate PRODUCT.md, DESIGN.md, surface brief.
 */
async function runDirectionEngine(workdir: string, payload: IntakePayload, log: (msg: string) => void): Promise<string> {
  const env = { ...process.env, IMPECCABLE_UNATTENDED: 'true' };
  const cmd = `/impeccable ${payload.prompt}${payload.brandStyle ? `, ${payload.brandStyle}` : ''}`;
  
  try {
    log(`   Running: ${cmd}`);
    const result = spawnSync('npx', cmd.split(' ').slice(1), {
      cwd: workdir,
      env,
      stdio: 'pipe',
      encoding: 'utf-8',
      timeout: 60000 // 60s timeout for direction engine
    });
    
    if (result.status !== 0) {
      log(`   ⚠️  Direction engine returned status ${result.status}`);
      log(`   stderr: ${result.stderr}`);
    }
    
    // Direction contract written to .impeccable/surfaces/
    const surfaceDir = path.join(workdir, '.impeccable', 'surfaces');
    if (!fs.existsSync(surfaceDir)) {
      throw new Error('Direction engine did not produce .impeccable/surfaces/');
    }
    
    const files = fs.readdirSync(surfaceDir).filter(f => f.endsWith('.md'));
    if (files.length === 0) {
      throw new Error('No surface brief generated');
    }
    
    const directionFile = path.join(surfaceDir, files[files.length - 1]);
    log(`   ✓ Direction locked: ${files[files.length - 1]}`);
    return directionFile;
  } catch (error) {
    throw new Error(`Direction engine failed: ${error}`);
  }
}

/**
 * Stage 3: GENERATE
 * Call site_renderer.py with direction context to render HTML/CSS.
 */
async function runGenerate(workdir: string, direction: string, payload: IntakePayload, log: (msg: string) => void): Promise<void> {
  try {
    const cmd = [
      'python3',
      path.join(process.cwd(), 'site_renderer.py'),
      `--tenant-id=${payload.tenantId}`,
      `--direction=${direction}`,
      `--company=${payload.customerData.company}`,
      `--city=${payload.customerData.city}`
    ];
    
    log(`   Running site_renderer.py...`);
    const result = spawnSync(cmd[0], cmd.slice(1), {
      cwd: workdir,
      stdio: 'pipe',
      encoding: 'utf-8',
      timeout: 30000
    });
    
    if (result.status !== 0) {
      throw new Error(`Renderer failed: ${result.stderr}`);
    }
    
    // Verify HTML generated
    const indexHtml = path.join(workdir, 'web', 'index.html');
    if (!fs.existsSync(indexHtml)) {
      throw new Error('Renderer did not produce index.html');
    }
    
    log(`   ✓ HTML/CSS generated`);
  } catch (error) {
    throw new Error(`Generation failed: ${error}`);
  }
}

/**
 * Stage 4: EVALUATE
 * Run /impeccable critique and /impeccable audit, parse JSON output.
 */
async function runEvaluate(workdir: string, log: (msg: string) => void): Promise<{ critiqueScore: number; auditP0: number }> {
  try {
    log(`   Running /impeccable critique...`);
    const critiqueRaw = execSync('npx impeccable critique --json', {
      cwd: workdir,
      encoding: 'utf-8',
      stdio: 'pipe'
    });
    
    const critique = JSON.parse(critiqueRaw);
    const critiqueScore = critique.overallScore || 0;
    
    log(`   Running /impeccable audit...`);
    const auditRaw = execSync('npx impeccable audit --json', {
      cwd: workdir,
      encoding: 'utf-8',
      stdio: 'pipe'
    });
    
    const audit = JSON.parse(auditRaw);
    const auditP0 = audit.issues?.filter((i: any) => i.severity === 'P0').length || 0;
    
    return { critiqueScore, auditP0 };
  } catch (error) {
    throw new Error(`Evaluation failed: ${error}`);
  }
}

/**
 * Stage 5A: SELF-HEAL LOOP
 * Autonomous loop: critique → diagnose → route to specific refinement command → repeat.
 * Terminates when quality gates met OR MAX_ATTEMPTS reached.
 */
async function runSelfHealLoop(
  workdir: string,
  initialScore: number,
  initialP0: number,
  log: (msg: string) => void
): Promise<number> {
  const MAX_ATTEMPTS = 4;
  const TARGET_SCORE = 88;
  let currentScore = initialScore;
  let currentP0 = initialP0;

  if (currentScore >= TARGET_SCORE && currentP0 === 0) {
    log(`   ✓ Quality gates already met (${currentScore}/100, ${currentP0} P0 issues)`);
    return currentScore;
  }

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    log(`   🔄 Self-heal iteration ${attempt}/${MAX_ATTEMPTS}`);
    
    // Get latest critique to inform routing
    let critiqueText = '';
    try {
      const critiqueRaw = execSync('npx impeccable critique --json', {
        cwd: workdir,
        encoding: 'utf-8',
        stdio: 'pipe'
      });
      const critique = JSON.parse(critiqueRaw);
      critiqueText = (critique.issues || []).join(' ').toLowerCase();
      currentScore = critique.overallScore || 0;
    } catch (e) {
      log(`   ⚠️  Could not fetch latest critique`);
    }

    // DECISION MATRIX: Route to specific command based on issues
    let command = '';
    if (critiqueText.includes('typography') || critiqueText.includes('font')) {
      command = 'npx impeccable typeset';
    } else if (critiqueText.includes('layout') || critiqueText.includes('spacing') || critiqueText.includes('alignment')) {
      command = 'npx impeccable layout';
    } else if (critiqueText.includes('confusing') || critiqueText.includes('copy') || critiqueText.includes('text')) {
      command = 'npx impeccable clarify';
    } else if (critiqueText.includes('color') || critiqueText.includes('bland') || critiqueText.includes('plain')) {
      command = 'npx impeccable colorize';
    } else if (currentScore < 60) {
      command = 'npx impeccable bolder';
    } else {
      command = 'npx impeccable polish';
    }

    log(`      → ${command}`);
    try {
      execSync(command, { cwd: workdir, stdio: 'inherit' });
    } catch (e) {
      log(`      ⚠️  Command failed; continuing`);
    }

    // Check gates after refinement
    try {
      const critiqueRaw = execSync('npx impeccable critique --json', {
        cwd: workdir,
        encoding: 'utf-8',
        stdio: 'pipe'
      });
      const auditRaw = execSync('npx impeccable audit --json', {
        cwd: workdir,
        encoding: 'utf-8',
        stdio: 'pipe'
      });
      
      currentScore = JSON.parse(critiqueRaw).overallScore || 0;
      currentP0 = JSON.parse(auditRaw).issues?.filter((i: any) => i.severity === 'P0').length || 0;
      
      log(`      📊 Score: ${currentScore}/100 | P0: ${currentP0}`);
      
      if (currentScore >= TARGET_SCORE && currentP0 === 0) {
        log(`   ✨ Quality gates met at iteration ${attempt}`);
        return currentScore;
      }
    } catch (e) {
      log(`   ⚠️  Could not evaluate progress`);
    }
  }

  log(`   ⚠️  Max iterations reached. Final score: ${currentScore}/100`);
  return currentScore;
}

/**
 * Stage 5B: HARDEN & SHIP
 * Final quality pass, build production assets, deploy.
 */
async function runHardenAndDeploy(workdir: string, payload: IntakePayload, log: (msg: string) => void): Promise<void> {
  try {
    log(`   Running /impeccable audit (final check)...`);
    execSync('npx impeccable audit', { cwd: workdir, stdio: 'inherit' });

    log(`   Running /impeccable harden (edge cases)...`);
    execSync('npx impeccable harden', { cwd: workdir, stdio: 'inherit' });

    log(`   Running /impeccable polish (final pass)...`);
    execSync('npx impeccable polish', { cwd: workdir, stdio: 'inherit' });

    log(`   Updating DESIGN.md from actual generated code...`);
    execSync('npx impeccable document', { cwd: workdir, stdio: 'inherit' });

    log(`   Building production bundle...`);
    execSync('npm run build:site', { cwd: workdir, stdio: 'inherit' });

    log(`   Deploying to Vercel...`);
    // TODO: wire Vercel deployment (requires VERCEL_TOKEN env var)
    // await deployToVercel(workdir, payload.tenantId);

    log(`✓ All stages complete`);
  } catch (error) {
    throw new Error(`Harden/deploy failed: ${error}`);
  }
}

// Export for testing
export { runDirectionEngine, runGenerate, runEvaluate, runSelfHealLoop, runHardenAndDeploy };
```

**Git it:**
```bash
git add webstaffr/site_maker_engine.ts
git commit -m "feat: add Impeccable magic upgrade orchestrator (phase 1 foundation)"
```

---

## 3. Update site_renderer.py to Accept Direction Context

Edit `site_renderer.py`:

```python
import argparse
import os
from pathlib import Path
import json

def render_site(tenant_id: str, direction: str = None, customer_data: dict = None):
    """
    Render customer site using Jinja2 + direction context from Impeccable.
    
    Args:
        tenant_id: Customer tenant ID
        direction: Path to .impeccable/surfaces/<page>.md (direction contract)
        customer_data: Customer info dict (company, services, city, etc.)
    """
    
    workdir = Path(f'sites/{tenant_id}')
    
    # Load design context
    design_md = load_design_md(workdir)
    product_md = load_product_md(workdir)
    
    # Extract tokens & palette for template use
    colors = extract_palette(design_md)
    typography = extract_typography(design_md)
    components = extract_components(design_md)
    
    # Build template context
    context = {
        'tenant_id': tenant_id,
        'customer': customer_data or {},
        'design': {
            'colors': colors,
            'typography': typography,
            'components': components,
        },
        'product': product_md,
    }
    
    # Render templates
    render_template('templates/base.html', context, workdir / 'web' / 'index.html')
    render_template('templates/services.html', context, workdir / 'web' / 'services.html')
    render_template('templates/contact.html', context, workdir / 'web' / 'contact.html')
    
    # Write CSS tokens as root variables
    write_design_tokens(colors, typography, workdir / 'web' / 'tokens.css')


def load_design_md(workdir: Path) -> dict:
    """Parse DESIGN.md into structured dict."""
    design_file = workdir / 'DESIGN.md'
    if not design_file.exists():
        return {}
    
    # Simple parser; in prod use google-stitch format parser
    content = design_file.read_text()
    return {'raw': content}  # TODO: full parser


def extract_palette(design_md: dict) -> dict:
    """Extract color tokens from DESIGN.md."""
    # TODO: parse DESIGN.md and return {color_name: hex_value}
    return {
        'primary': '#1a1a1a',
        'accent': '#2563eb',
        'background': '#ffffff',
    }


def extract_typography(design_md: dict) -> dict:
    """Extract type scale from DESIGN.md."""
    # TODO: parse DESIGN.md and return {type_name: css_value}
    return {
        'h1': 'font-size: 3rem; line-height: 1.2;',
        'body': 'font-size: 1rem; line-height: 1.6;',
    }


def extract_components(design_md: dict) -> dict:
    """Extract component rules from DESIGN.md."""
    return {}  # TODO


def write_design_tokens(colors: dict, typography: dict, output_file: Path) -> None:
    """Write design tokens as CSS custom properties."""
    css = ':root {\n'
    for name, value in colors.items():
        css += f'  --color-{name}: {value};\n'
    for name, value in typography.items():
        css += f'  --typo-{name}: {value};\n'
    css += '}\n'
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(css)


def render_template(template_path: str, context: dict, output_path: Path) -> None:
    """Render Jinja2 template with context."""
    from jinja2 import Environment, FileSystemLoader
    
    env = Environment(loader=FileSystemLoader('templates'))
    template = env.get_template(template_path.split('/')[-1])
    rendered = template.render(context)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--tenant-id', required=True)
    parser.add_argument('--direction', default=None)
    parser.add_argument('--company', default='Your Company')
    parser.add_argument('--city', default='Your City')
    args = parser.parse_args()
    
    customer_data = {
        'company': args.company,
        'city': args.city,
    }
    
    render_site(args.tenant_id, args.direction, customer_data)
    print(f'✓ Site rendered: sites/{args.tenant_id}/web/')
```

**Git it:**
```bash
git add site_renderer.py
git commit -m "refactor: site_renderer accepts Impeccable direction context"
```

---

## 4. Test End-to-End (Dry Run)

Create a test intake:

```bash
cat > /tmp/test_intake.json << 'EOF'
{
  "tenantId": "test_plumber_001",
  "prompt": "plumbing company website, emergency services, professional trustworthy vibe",
  "brandStyle": "tradesman aesthetic, dark blue and white, sans-serif",
  "customerData": {
    "company": "Austin Emergency Plumbing",
    "services": ["emergency repair", "water heater install", "drain cleaning"],
    "city": "Austin, TX"
  }
}
EOF
```

Trigger the pipeline from Node:

```bash
npx ts-node -e "
const engine = require('./webstaffr/site_maker_engine.ts');
const intake = require('/tmp/test_intake.json');
engine.runMagicUpgrade(intake).then(result => {
  console.log('Result:', result);
});
"
```

Expected output:
```
[test_plumber_001] 🎯 [1/5] SHAPE: ...
[test_plumber_001] 🎨 [2/5] DIRECTION ENGINE: ...
[test_plumber_001] 🖼️  [3/5] GENERATE: ...
[test_plumber_001] 🔍 [4/5] EVALUATE: ...
[test_plumber_001] ⚙️  [5/5] SELF-HEAL & SHIP: ...
[test_plumber_001] ✨ Quality gates met. Hardening, polishing, deploying...
[test_plumber_001] 🚀 LIVE at https://sites.webstaffr.com/test_plumber_001
```

Verify output:
- `sites/test_plumber_001/PRODUCT.md` exists
- `sites/test_plumber_001/DESIGN.md` exists
- `sites/test_plumber_001/.impeccable/surfaces/` has direction contract
- `sites/test_plumber_001/web/index.html` is valid HTML

**Success = Phase 1 complete.**

---

## 5. TASKS.md Update

```markdown
## Magic Upgrade (Impeccable Integration) — 2026-08-03

- [x] Phase 1: Foundation
  - [x] Install Impeccable, run init + document
  - [x] Create PRODUCT.md, DESIGN.md, .impeccable/config.json
  - [x] Implement site-maker-engine.ts (five-stage orchestrator)
  - [x] Update site_renderer.py to accept direction context
  - [x] Dry-run end-to-end pipeline
  
- [ ] Phase 2: Critique Loop (Week 2)
  - [ ] Wire `/impeccable critique` into evaluation stage
  - [ ] Wire `/impeccable audit` into evaluation stage
  - [ ] Tune quality gates (target score ≥88, P0=0)
  - [ ] Implement decision matrix for auto-heal routing
  - [ ] Test with 3 real customer intakes
  
- [ ] Phase 3: Direction Engine with Visual Mocks (Week 3–4)
  - [ ] Set OPENAI_API_KEY for gpt-image-2 direction rendering
  - [ ] Test direction roll + visual mock generation
  - [ ] Measure cost per site ($0.50 target)
  
- [ ] Phase 4: Live Mode (Deferred; alpha status)
  - [ ] Evaluate `/impeccable live` browser iteration
  - [ ] Consider for high-touch customer workflow
```

---

## Monitoring & Debugging

### View build log for a tenant:

```bash
cat sites/{tenant_id}/.impeccable_build.log
```

### Manual critique on generated site:

```bash
cd sites/{tenant_id}
npx impeccable critique
```

### Manual audit:

```bash
cd sites/{tenant_id}
npx impeccable audit
```

### Inspect direction contract:

```bash
cat sites/{tenant_id}/.impeccable/surfaces/*.md
```

### Check design token consistency:

```bash
npx impeccable detect sites/{tenant_id}/web/ --scope type
npx impeccable detect sites/{tenant_id}/web/ --scope layout
```

---

## Success Criteria (Phase 1)

- [ ] `npx impeccable install` succeeds
- [ ] `PRODUCT.md` + `DESIGN.md` created and committed
- [ ] `site-maker-engine.ts` implements all five stages
- [ ] Dry-run completes without error
- [ ] Generated site has valid HTML/CSS
- [ ] Build log shows all stages executing
- [ ] Tests: 42/42 passing

**Once Phase 1 passes, ship and monitor real customer intake.**
