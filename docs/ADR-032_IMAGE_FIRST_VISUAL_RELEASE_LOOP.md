# ADR-032: Image-First, Screenshot-Judged Site Magic

**Status:** Proposed, founder approval required  
**Date:** 2026-08-15

## Problem

The public customer page remains the deterministic Site Renderer fallback until a Site Magic build clears every release gate and is published. The fallback intentionally contains no fabricated imagery, so the live page can be technically correct while looking like a generic template.

Site Magic currently generates three private image comps, but its final design assessment reads HTML, CSS, and project files rather than rendered screenshots. This optimizes code structure, Lighthouse, axe, and detector rules without proving that the actual composition is visually exceptional. A generated image can also satisfy the current asset check by appearing in a fallback gallery instead of functioning as part of the art direction.

Production evidence supports this diagnosis:

- The live Renderer page for submission 64 contains no `<img>` elements.
- Site Magic job `a1281251-3f57-4993-ab19-b6855f7a492f` generated private comps and achieved Lighthouse 100/100/100/100 with axe 0, but remained quarantined at design 27/32 with two P1 mobile-conversion findings.
- Generated candidates are not public or published while quarantined, so the founder correctly sees the image-free Renderer, not the private Site Magic candidate.

## Decision

Replace the text-only design loop with an image-first, screenshot-judged release loop while retaining the Renderer as a safe baseline and all existing deterministic gates.

### 1. Generate images for explicit editorial roles

The direction role must return three separate image briefs grounded only in verified business facts:

1. `hero`: wide 16:9, trade-specific working environment or equipment detail, composed with intentional copy space.
2. `proof`: 4:3 material/process detail supporting the differentiator without implying an unverified employee, customer, credential, property, or completed job.
3. `service`: 4:3 service-context image tied to one submitted service or the verified service area.

Abstract art is not the default. It is allowed only when the direction explains why photography would be misleading or unsupported by the verified facts.

Use OpenRouter's dedicated Image API with the existing `google/gemini-2.5-flash-image` model so aspect ratio is explicit. Continue normalizing outputs to bounded WebP assets with intrinsic dimensions.

### 2. Make image placement a release gate

The builder must place:

- the hero image above the fold as a primary compositional element;
- both supporting images in semantically relevant sections;
- meaningful alt text derived from the image brief, or empty alt only when the image is genuinely decorative.

The image gate fails when a comp is missing, hidden, appended only in the fallback gallery, rendered too small to contribute to the composition, or visually competes with the primary mobile contact action.

### 3. Judge rendered screenshots, not source code alone

After each build/remediation pass, Playwright captures full-page screenshots at 390, 768, and 1440 pixels. The existing vision-capable `openai/gpt-5.6-terra` model receives those screenshots plus verified facts and returns the structured design assessment.

The visual jury scores:

- composition and hierarchy;
- image relevance, crop, and art direction;
- typography and spacing rhythm;
- distinctiveness versus template/AI-default patterns;
- mobile conversion clarity;
- cross-page consistency;
- factual integrity.

HTML/CSS context remains available for actionable file-level remediation, but screenshots are the primary design evidence.

### 4. Raise the visual acceptance contract

A build is `ready_for_review` only when:

- normalized visual score is at least 90%;
- there are no P0 or P1 visual findings;
- all three image-role checks pass;
- Impeccable detector findings are zero;
- all current Lighthouse, axe, responsive, functional, content, asset, and tenant-isolation gates pass.

No automatic weakening of gates and no automatic publication of quarantined work.

### 5. Make the real candidate visible to the founder

When a build reaches `ready_for_review`, surface its signed preview URL in the intake/dashboard workflow. Publishing remains an explicit action and continues to use the existing immutable build and active-build records.

## Consequences

- The visual judge will finally see what a visitor sees.
- Generated images become purposeful layout assets instead of evidence-count artifacts.
- Renderer output stays safe and immediate, while Site Magic becomes the premium candidate rather than an invisible side process.
- Each evaluation adds three screenshot image inputs to Terra, increasing OpenRouter token cost and latency.
- Migrating image generation to the dedicated Image API retains the current vendor/model but changes the adapter response contract and requires live verification.
- This does not fabricate customer photography. Generated imagery must remain non-claiming and grounded in verified trade/service context.

## Approval gate

Founder approval authorizes implementation of the screenshot-based visual jury and migration of the existing image adapter to OpenRouter's dedicated Image API. Push, deployment, production validation spend, and publication remain separately gated unless explicitly authorized.
