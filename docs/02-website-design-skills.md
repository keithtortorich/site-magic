# Website Design Skills Architecture

## Overview

NetBuild.Pro tenant site rendering pipeline integrates five specialized design and quality skills as an interactive polish loop. This architecture replaces fragmented third-party design tools with a unified, auditable framework aligned with Superpowers skill specifications.

Each skill operates independently on `site_renderer.py` output and passes results to the next stage in the loop, enabling human-in-the-loop review at every checkpoint.

---

## The Five Skills

### 1. **writing-skills**
Refines copy clarity, voice consistency, and persuasiveness across site sections.

- **Input:** Rendered HTML from `site_renderer.py`
- **Focus:** Copy tone, messaging hierarchy, call-to-action clarity
- **WCAG:** Not applicable (content skill)
- **Output:** Flagged passages, suggested rewrites, voice alignment report

### 2. **design-system**
Validates visual consistency, component usage, and design token adherence.

- **Input:** CSS and HTML structure
- **Focus:** Component reuse, spacing systems, typographic scale
- **WCAG:** Not applicable (system compliance skill)
- **Output:** Design token audit, component inventory, consistency gaps

### 3. **design-critique**
Applies visual design principles and composition feedback specific to each industry vertical.

- **Input:** Rendered site HTML and CSS
- **Focus:** Visual hierarchy, color application, layout balance
- **WCAG:** Not applicable (subjective critique)
- **Output:** Design critique report with industry-specific recommendations

### 4. **accessibility-review**
Validates WCAG 2.1 AA compliance with automated and manual checks.

- **Input:** Rendered HTML, CSS, and asset metadata
- **Focus:** Color contrast, semantic HTML, keyboard navigation, screen reader compatibility, alt text
- **WCAG:** Full AA compliance verification
- **Output:** Automated test results + manual audit findings + remediation paths

### 5. **research-synthesis**
Analyzes industry, customer segment, and competitive positioning for messaging alignment.

- **Input:** Tenant metadata (trade, size, region, competitors)
- **Focus:** Market-specific messaging, competitive differentiation, audience fit
- **WCAG:** Not applicable (research skill)
- **Output:** Positioning analysis, messaging gaps, research notes

---

## The Polish Loop

```
[site_renderer.py output]
    ↓
[writing-skills review]
    ↓ (human checkpoint)
[design-system audit]
    ↓ (human checkpoint)
[design-critique feedback]
    ↓ (human checkpoint)
[accessibility-review (WCAG AA)]
    ↓ (auto-fail if AA unmet; human review otherwise)
[research-synthesis alignment check]
    ↓ (human checkpoint)
[Published site]
```

**Human checkpoints** allow operators to accept, reject, or refine recommendations before advancing. No stage auto-gates publication; accessibility failures are the only exception (WCAG AA is non-negotiable).

---

## Integration with Cowork

Each skill runs within **Cowork**, NetBuild.Pro's multi-agent coordination framework. Cowork handles:

- Sequential skill invocation with context preservation
- Human approval gates between stages
- Result aggregation and conflict resolution
- Audit trail logging for compliance
- Integration with the `/sites/{tenant_id}` publishing pipeline

Skills emit structured JSON reports (not raw text), enabling Cowork to parse, merge, and present findings without re-parsing.

---

## Architecture vs. Legacy

| Aspect | Legacy (5 Third-Party Tools) | New (5 Superpowers Skills) |
|--------|-----|-----|
| **Auditability** | Vendor-dependent, unverifiable | Open Superpowers specs, code-reviewed |
| **Integration** | Webhook fragmentation, data loss | Cowork-native, structured output |
| **Human-in-Loop** | Implicit, error-prone | Explicit checkpoints, operator control |
| **WCAG Compliance** | Partial; no guarantee | Full AA validation, auto-enforcement |
| **Vendor Lock** | 5 external dependencies | None; all skills self-contained |
| **Customization** | Not possible | Per-tenant skill configuration |

### Legacy Tools Removed

The following third-party design assessment tools are **deprecated and not invoked**:

- Emil Kowalski design system tool
- Impeccable design critique service
- Taste Skill visual design automation
- UI UX Pro Max interface tool
- 21st.dev design analysis tool

No references to these tools remain in the codebase, configuration, or documentation.

---

## Compliance & Standards

### WCAG 2.1 AA

Accessibility-review enforces **WCAG 2.1 Level AA** as a non-negotiable gate:

- **1.4.3 Contrast (Minimum):** All text meets 4.5:1 (normal) or 3:1 (large)
- **2.1.1 Keyboard:** All interactive elements keyboard-accessible
- **4.1.2 Name, Role, Value:** Semantic HTML and ARIA correctly applied
- **1.1.1 Non-text Content:** All images and icons have descriptive alt text

Failures **block publication** until remediated. Warnings are logged but allow human override.

### Human-in-the-Loop Philosophy

No skill is a "fire and forget" automation. Each stage produces **flagged findings, not commands**. Operators review, contextualize, and choose actions:

- **Accept:** Apply suggestion as-is
- **Customize:** Modify suggestion before applying
- **Defer:** Mark for later review, proceed to next stage
- **Reject:** Flag as false positive, document reason

This preserves human judgment while scaling review consistency.

---

## Operator Workflow

1. Tenant site renders via `site_renderer.py`
2. Cowork dispatches the Polish Loop
3. Each skill produces a report; operator reviews at checkpoint
4. Operator marks findings as **accepted, customized, deferred, or rejected**
5. Next stage begins with updated context
6. On completion, all findings are logged to `tenant.design_audit` table
7. Site publishes if no blocking issues remain

---

## Configuration & Customization

Skills support per-tenant configuration:

```json
{
  "skills": {
    "accessibility-review": {
      "enforceWCAG": "AA",
      "colorBlindSimulation": true,
      "checkKeyboardNav": true
    },
    "design-critique": {
      "verticalStyle": "hvac",  // HVAC-specific guidance
      "emphasizeIndustryTrust": true
    },
    "writing-skills": {
      "tone": "professional-approachable",
      "audienceSegment": "facility-manager"
    }
  }
}
```

---

## Metrics & Reporting

Cowork logs all Polish Loop activity to the audit trail:

- **Skills invoked:** Which stages ran for each tenant
- **Findings per stage:** Count and severity of issues flagged
- **Operator actions:** Accept/customize/defer/reject breakdown
- **Time in loop:** Duration from render to publish
- **Audit trail:** Immutable record of all decisions

Reports roll up to dashboards for QA and product monitoring.

---

## Future Expansion

Skills are composable; the loop can be extended with new stages:

- **SEO-audit** — keyword density, meta completeness, schema validation
- **brand-alignment** — logo usage, color palette fidelity, messaging consistency
- **conversion-optimization** — CTA testing, form friction analysis
- **mobile-experience** — responsive breakpoint validation, touch target sizing

Each new skill plugs into the same loop and checkpoint system with no refactoring.

---

## Security & Compliance

- All skills operate on **rendered HTML only**; no direct database access
- Tenant data is scoped to the specific `tenant_id` being reviewed
- Skill output is immutable once logged (audit trail protection)
- No external vendor calls; all processing is NetBuild.Pro-internal
- GDPR/CCPA: Tenant data stays within NetBuild.Pro infrastructure

---

## Summary

The five Superpowers skills replace a fragmented third-party toolchain with a unified, auditable, human-controlled design review system. WCAG AA compliance is enforced, all findings are logged, and operators retain full discretion at each stage. No vendor lock-in; full transparency and customization by tenant.
