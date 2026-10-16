# Design Constraints: Template Author Checklist

Use this checklist before shipping any new template or component.

## Pre-Build Checklist

### Animation Decision Framework (Emil)

- [ ] Identified animation frequency (never/rarely/occasional/frequent)
- [ ] Identified animation purpose (spatial_consistency/feedback/explanation/state_indication)
- [ ] For high-frequency actions (100+ times/day): removed animation entirely
- [ ] For rare actions: can use longer duration or springs for delight
- [ ] Never animating keyboard-initiated actions (searchbox, command palette, filter toggle)

### Animation Implementation

- [ ] Animation duration is 100-300ms (button 100-160ms, tooltip 125-200ms, dropdown 150-250ms, modal 200-500ms)
- [ ] Easing is appropriate: entrance = ease-out cubic-bezier(0.23, 1, 0.32, 1), never ease-in
- [ ] Entry animations never use scale(0) — always scale(0.95) + opacity: 0
- [ ] Only animating transform (translate, scale, rotate) and opacity, never width/height/left/top
- [ ] Button press includes scale(0.97) on :active for instant feedback
- [ ] Popovers use transform-origin: var(--radix-popover-content-transform-origin) (modals stay centered)
- [ ] Tooltips skip delay and animation on subsequent hovers (data-instant attribute)
- [ ] Used blur(2px) filter for any tricky crossfade transitions

### Accessibility (WCAG 2.1 AA)

- [ ] All text has 4.5:1 contrast minimum (body text, UI components)
- [ ] Large text (≥18pt or bold ≥14pt) has 3:1 contrast minimum
- [ ] All buttons and interactive elements are 44×44px minimum
- [ ] All images have meaningful alt text (never empty, never just filename)
- [ ] All form inputs have `<label>` tags ABOVE the input (never placeholder-only)
- [ ] Keyboard navigation works: Tab, Enter, Escape
- [ ] Focus indicators are visible on all interactive elements (never removed :focus)
- [ ] Form error messages appear inline near the field, not just at form top
- [ ] No auto-playing audio/video or animations

### Reduced Motion Support (Mandatory)

- [ ] Every animation has a @media (prefers-reduced-motion: reduce) alternative
- [ ] Reduced-motion alternatives replace motion with opacity fades (no scale/translate)
- [ ] No auto-play animations at any size (respect user preference)

### Touch Device Safety

- [ ] Hover effects are gated behind @media (hover: hover) and (pointer: fine)
- [ ] No buttons or touch targets smaller than 44px
- [ ] No double-tap zoom prevention (viewport-fit=cover is safe)

### Performance

- [ ] Only animating transform and opacity (not width/height/padding/margin)
- [ ] CSS animations used for predetermined motion (off main thread)
- [ ] Framer Motion using transform string (animate={{ transform: "..." }}) not x/y props
- [ ] No will-change spam (applied only to elements actually being animated)
- [ ] No mixing GSAP + Framer Motion in same component tree
- [ ] No grain/noise filters on scrolling containers
- [ ] No rendering 1000+ items at once (virtualize if needed)

### Design System Compliance

- [ ] Using design_config.spacing_scale for section gaps and card gaps (not hardcoded values)
- [ ] Using design_config.hero_layout for hero section (center/split/offset based on variance)
- [ ] Checked banned_patterns list — zero violations
- [ ] Using allowed fonts only (Geist, Satoshi, Cabinet Grotesk, Outfit — never Inter)
- [ ] No emojis anywhere (use Phosphor or Radix icons instead)
- [ ] No side-stripe borders > 1px (use full border or bg tint instead)
- [ ] No gradient text (use single solid color + weight/size for emphasis)
- [ ] No sketchy SVGs with feTurbulence (use real assets or omit)

### Brand & Tone

- [ ] No em-dashes (use commas, colons, semicolons, periods, parentheses instead)
- [ ] No aphoristic-cadence copy (no "serious statement, then punchy short negation" reflex)
- [ ] No marketing buzzwords (empower, supercharge, leverage, unleash, transform, seamless, world-class)
- [ ] Button labels use verb + object ("Save changes" not "OK", "Delete project" not "Yes")
- [ ] Link text has standalone meaning ("View pricing plans" not "Click here")
- [ ] No placeholder/filler text (omit sections rather than inventing content)

### Visual Design Quality

- [ ] No pure black (#000000) — use Zinc-950 (#18181b) or Off-Black (#0f0f0f)
- [ ] No neon glows (outer shadow > 8px) — use inner borders or tinted shadows
- [ ] No excessive gradients on large text (one accent max, saturation < 80%)
- [ ] No 3-column identical card grids (use 2-col zig-zag, asymmetric, or horizontal scroll)
- [ ] No tiny all-caps eyebrow kickers on EVERY section (AI scaffold tell)
- [ ] No numbered scaffolding (01/02/03) on every section (numbered only for real sequences)
- [ ] No identical hero metrics template (big number + label + gradient = SaaS cliché)
- [ ] No glassmorphism decorations (blurs/glass only for rare, purposeful use)
- [ ] No headline text overflow (test at every breakpoint, reduce clamp max or rewrite if needed)

### Testing

- [ ] Reviewed animation at 0.25× speed (DevTools Animations panel) to spot timing issues
- [ ] Tested on real touch device (not simulator) if any gesture interactions
- [ ] Tested focus keyboard navigation (Tab, Shift+Tab, Enter, Escape)
- [ ] Tested in reduced-motion mode (browser accessibility settings)
- [ ] Tested all button/link hover states (desktop) — don't trigger on touch
- [ ] Verified contrast ratios with a contrast checker (all critical paths)
- [ ] Tested at multiple viewport sizes (mobile, tablet, desktop)

### Documentation

- [ ] Component includes inline comments for why animation exists (purpose, frequency)
- [ ] Linked to `docs/DESIGN_CONSTRAINTS_EXAMPLE.md` pattern in code comments if using a pattern
- [ ] Used a macro from `_design_constraints_snippet.html` if one exists
- [ ] Documented any custom constraints or exceptions (and why they're needed)

## During Code Review

### Reviewer Checklist

- [ ] Are there animations without documented purpose/frequency?
- [ ] Is any animation on a high-frequency action (keyboard, search input change)?
- [ ] Does any animation use ease-in on entrance? (Flag for change to ease-out)
- [ ] Is any animation > 300ms for UI elements? (Should be shorter)
- [ ] Are any animations on width/height/padding/margin? (Should be transform-only)
- [ ] Is prefers-reduced-motion honored? (Check @media queries)
- [ ] Are hover states gated on @media (hover: hover)? (Touch safety)
- [ ] Does every image have alt text? (Non-empty, meaningful)
- [ ] Do form inputs have `<label>` tags above them? (Not placeholder-only)
- [ ] Are any banned patterns present? (emoji, Inter font, neon glow, side stripes, etc.)
- [ ] Are focus indicators visible on all interactive elements?
- [ ] Is contrast 4.5:1+ for body text?
- [ ] Are touch targets 44×44px minimum?

## Common Mistakes

### Animation Mistakes

| Mistake | Why It's Wrong | Fix |
|---------|----------------|-----|
| `scale(0)` entry | Nothing in real world appears from nothing | Use `scale(0.95) + opacity: 0` |
| `ease-in` on entrance | Starts slow, feels sluggish | Use `ease-out cubic-bezier(0.23, 1, 0.32, 1)` |
| 400ms animation | Too slow for UI, feels sluggish | Cap at 300ms (button 160ms, dropdown 200ms) |
| Animate width/height | Causes layout recalc, jank | Animate transform + opacity only |
| Hover without media query | Triggers on touch tap (false positive) | Gate on `@media (hover: hover) and (pointer: fine)` |

### Accessibility Mistakes

| Mistake | Why It's Wrong | Fix |
|---------|----------------|-----|
| `color: #999` on white | 2.8:1 contrast (fails WCAG 2.1 AA) | Use darker text (4.5:1+) |
| `<input placeholder="Email">` | No label for screen readers | Add `<label>Email</label>` above input |
| `<img alt="">` | Empty alt is inaccessible | Write meaningful alt text |
| `<button style="outline: none">` | Removes focus indicator | Keep :focus ring visible |
| Button 30px tall | Too small to touch (WCAG requires 44px) | Make it 44×44px minimum |

### Design System Mistakes

| Mistake | Why It's Wrong | Fix |
|---------|----------------|-----|
| Hardcoded `py-24` spacing | Doesn't respect design variance | Use `{{ design_config.spacing_scale.section_gap }}` |
| Three-column card grid | Identical card grid is AI tell | Vary sizes (2-col, asymmetric, or scroll) |
| `font-family: Inter` | Overused in AI designs | Use Geist, Satoshi, Cabinet Grotesk, or Outfit |
| `border-left: 4px` accent | Side stripe is AI slop pattern | Use full border or background tint |
| Tiny caps eyebrow on every section | 2023 scaffold tell | Use one deliberate kicker or different cadence |

## Red Flags for Code Review

- 🚩 Animation on keyboard action (type, search, filter) → remove it
- 🚩 `scale(0)` entry animation → rewrite to `scale(0.95)`
- 🚩 `ease-in` on UI entrance → change to `ease-out cubic-bezier(0.23, 1, 0.32, 1)`
- 🚩 Animation > 300ms on UI → reduce duration
- 🚩 No `@media (prefers-reduced-motion: reduce)` → add it
- 🚩 No `@media (hover: hover)` on hover state → add it for touch safety
- 🚩 Empty alt text (`alt=""`) → write meaningful alt
- 🚩 Placeholder-only form input (no label) → add `<label>` above
- 🚩 `outline: none` on button → restore :focus
- 🚩 Hardcoded spacing values → use design_config.spacing_scale
- 🚩 Three-column identical card grid → vary sizes/layouts/densities
- 🚩 `font-family: Inter` → change to Geist or approved alternative
- 🚩 No branded color scheme (all gray) → apply palette colors intentionally

## Approval Gates

Before merging a PR with new templates or components:

1. **Animation**: Designer reviews animation timing + purpose
2. **Accessibility**: WCAG 2.1 AA verified (contrast, alt text, labels, focus, touch targets)
3. **Performance**: No layout-thrashing animations, no high-frequency motion, reduced-motion supported
4. **Design System**: Spacing scale used, banned patterns zero, brand compliance verified
5. **Testing**: Tested on real device, multiple viewports, keyboard nav, reduced-motion mode

## Useful Links

- Design constraints module: `webstaffr/design_constraints.py`
- Template snippets: `webstaffr/templates/site/_design_constraints_snippet.html`
- Examples: `docs/DESIGN_CONSTRAINTS_EXAMPLE.md`
- README: `docs/DESIGN_CONSTRAINTS_README.md`
- Emil Kowalski: https://animations.dev
- tasteskill: https://github.com/tasteskill/tasteskill
- WCAG 2.1 AA: https://www.w3.org/WAI/WCAG21/quickref/
