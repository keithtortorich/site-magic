# Design Constraints: Emil + tasteskill Integration

# NetBuild.Pro 4.0 operationalizes two design philosophies into executable rules passed to every Jinja2 template:

1. **Emil Kowalski's animation engineering** (animations.dev) — taste is trained, unseen details compound
2. **tasteskill's operationalized design directives** — registry of design presets and banned patterns

## Quick Start

Every template receives `design_config`, `spacing`, `hero_layout`, `banned_patterns`, `a11y`, and `perf` automatically. Copy a pattern from `webstaffr/templates/site/_design_constraints_snippet.html` or follow an example from `docs/DESIGN_CONSTRAINTS_EXAMPLE.md`.

### Example: Animated Button (Emil's Framework)

```html
<button class="ws-cta" style="transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1);">
  Call Now
</button>

<style>
.ws-cta:active {
  transform: scale(0.97);  /* Feedback: button feels responsive (Emil) */
}

@media (prefers-reduced-motion: reduce) {
  .ws-cta {
    transition: none;  /* Respect motion sensitivity */
  }
}
</style>
```

## The Four Questions (Emil Kowalski)

Before adding ANY animation, answer these:

| Question | Rule | Example |
|----------|------|---------|
| **Should it animate?** | Never for 100x/day actions (keyboard shortcuts). Rarely for 10x/day. OK for occasional/rare. | Keyboard shortcut = no anim. Button press = feedback anim. First-time onboarding = delight anim. |
| **What's the purpose?** | spatial_consistency, feedback, explanation, or state_indication. Never "looks cool." | Button press = feedback. Toast enter/exit = spatial_consistency. Modal open = explanation. |
| **What easing?** | entrance = ease-out, exit = linear, hover = ease. NEVER ease-in (feels sluggish). | cubic-bezier(0.23, 1, 0.32, 1) for ease-out (custom, not weak CSS default). |
| **How fast?** | button 100-160ms, tooltip 125-200ms, dropdown 150-250ms, modal 200-500ms. UI cap = 300ms. | 180ms dropdown feels more responsive than 400ms. Faster = perceived speed. |

## Key Bans (tasteskill + Emil)

### Visual Tells (AI Slop Patterns)

- ❌ `border-left: 4px` as accent (side stripe) → ✅ full border or bg tint
- ❌ `background-clip: text` with gradient → ✅ single solid color + weight/size
- ❌ `feTurbulence` doodles (sketchy SVG) → ✅ real assets or omit
- ❌ Tiny all-caps kicker on EVERY section → ✅ one deliberate kicker or different cadence
- ❌ Numbered scaffolding 01/02/03 on every section → ✅ use numbers only for real sequences
- ❌ Identical card grid (icon + title + text repeated) → ✅ vary sizes/layouts/densities
- ❌ `scale(0)` entry animations → ✅ `scale(0.95) + opacity: 0`

### Performance Violations

- ❌ Animate `width`, `height`, `top`, `left` → ✅ animate `transform` + `opacity` only
- ❌ Framer Motion `x={100}` prop (not accelerated) → ✅ use `transform="translateX(100px)"`
- ❌ Keyframes on rapid-fire elements (toasts) → ✅ CSS transitions (interruptible)
- ❌ Hover without `@media (hover: hover)` → ✅ gate on pointer: fine (touch fix)

### Accessibility Violations

- ❌ `color: #999` on white → ✅ 4.5:1 contrast minimum
- ❌ `<input placeholder="Email">` (no label) → ✅ `<label>Email</label><input>`
- ❌ `<img alt="">` or missing alt → ✅ meaningful alt text (never empty, never filename)
- ❌ `<button style="outline: none">` → ✅ keep `:focus` ring visible
- ❌ Skip `@media (prefers-reduced-motion: reduce)` → ✅ replace motion with opacity fades

## Emil's Component Patterns

### Button Press (Sonner)

Every button must feel responsive — `scale(0.97)` on `:active`:

```css
.button {
  transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
}
.button:active {
  transform: scale(0.97);  /* Instant feedback */
}
```

### Popover Transform Origin

Popovers scale from their trigger, not center. Modals stay centered:

```css
.popover {
  transform-origin: var(--radix-popover-content-transform-origin);
}
.modal {
  transform-origin: center;  /* EXCEPTION: modals stay centered */
}
```

### Tooltip Skip-Delay

First hover waits 200ms, subsequent hovers instant (feels faster):

```css
.tooltip {
  transition-delay: 200ms;  /* First */
}
.tooltip[data-instant] {
  transition-duration: 0ms;  /* Instant on subsequent */
}
```

### Never scale(0)

Nothing in real world appears from nothing. Start from `scale(0.95)`:

```css
.card-enter {
  transform: scale(0.95);  /* Visible but small */
  opacity: 0;
  animation: revealCard 250ms ease-out forwards;
}

@keyframes revealCard {
  to {
    transform: scale(1);
    opacity: 1;
  }
}
```

### Blur Transitions

When a crossfade feels off despite trying easing/duration, add `filter: blur(2px)`:

```css
.button-content.transitioning {
  filter: blur(2px);
  opacity: 0.7;
}
```

## Spacing Scale (tasteskill)

Design variance dials set spacing:

| Density | section_gap | card_gap | padding |
|---------|------------|----------|---------|
| **spacious** | py-32 md:py-48 | gap-8 | p-10 |
| **standard** | py-20 md:py-32 | gap-6 | p-8 |
| **dense** | py-12 md:py-20 | gap-4 | p-6 |

Access via `{{ design_config.spacing_scale.section_gap }}`.

## Presets

Four ready-to-use constraint sets:

```python
PRESET_MINIMAL        # minimal variance, static motion, spacious density
PRESET_BALANCED       # balanced variance, fluid motion, standard density (default)
PRESET_BOLD          # bold variance, cinematic motion, standard density
PRESET_DENSE_DASHBOARD  # minimal variance, fluid motion, dense density (Geist Mono)
```

Use via `build_page_context(..., design_preset="bold")`.

## Mandatory Accessibility Checks

Before shipping any template:

1. **Contrast:** 4.5:1 on body text, 3:1 on large (≥18pt or bold ≥14pt)
2. **Touch targets:** 44×44px minimum (include 8px spacing)
3. **Alt text:** On all images (never empty, never just filename)
4. **Labels:** Above inputs, never placeholder-only
5. **Keyboard nav:** Tab, Enter, Escape all work
6. **Reduced motion:** `@media (prefers-reduced-motion: reduce)` implemented
7. **Focus ring:** Never remove `:focus` outline
8. **Inline errors:** Near field, not just form top

## Files

| File | Purpose |
|------|---------|
| `webstaffr/design_constraints.py` | Core module (AnimationConstraints, DesignSystemConfig, AccessibilityConstraints, PerformanceGuardrails, presets) |
| `webstaffr/templates/site/_design_constraints_snippet.html` | 10 reusable Jinja2 macros (copy-paste) |
| `docs/DESIGN_CONSTRAINTS_EXAMPLE.md` | 8 real template examples with explanations |
| `webstaffr/site_renderer.py` | Wires constraints to templates via `build_page_context()` |

## References

- **Emil Kowalski** — animations.dev (animation decision framework, component patterns, performance)
- **tasteskill** — GitHub repo (design variance dials, banned patterns, operationalized rules)
- **Impeccable** (pbakaus) — design engineering skill (reference/craft.md, design quality checklist)
- **Apple Human Interface Guidelines** — touch targets, springs, motion (used in AccessibilityConstraints)
- **Sonner** — 13M+ weekly npm (component DX, edge case handling, cohesion)

## For Template Authors

1. Copy a macro from `_design_constraints_snippet.html`
2. Follow the pattern in `DESIGN_CONSTRAINTS_EXAMPLE.md`
3. Always include `@media (prefers-reduced-motion: reduce)` alternative
4. Test `@media (hover: hover) and (pointer: fine)` for hover states
5. Check contrast with `_contrast_ratio()` in `site_renderer.py` (built into tests)
6. Review animations at 0.25× speed (DevTools Animations panel) before shipping

## Next Steps

- Implement constraint macros in new templates
- Port existing templates to use spacing_scale and hero_layout
- Add constraint validation to site render tests (check for banned patterns at build time)
- Surface constraint violations in health_check.py for live sites
