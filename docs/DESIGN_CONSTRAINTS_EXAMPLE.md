# Design Constraints: Template Usage Examples

NetBuild.Pro's `design_constraints.py` module operationalizes Emil Kowalski's animation philosophy and tasteskill's design directives into executable rules. These constraints are automatically passed to every Jinja2 template via `build_page_context()`.

## What Gets Passed to Templates

Every template receives:

```python
{
    "design_config": DesignSystemConfig,      # preset (minimal/balanced/bold/dense-dashboard)
    "spacing": dict,                          # spacing scale tokens by density
    "hero_layout": str,                       # "center", "split", or "offset"
    "banned_patterns": list[str],             # things you must NOT do
    "a11y": AccessibilityConstraints,         # WCAG 2.1 AA baseline
    "perf": PerformanceGuardrails,           # animation performance rules
}
```

## Example 1: Animation Decision Framework (From Emil)

**Before adding ANY animation, answer 4 questions:**

```html
{% if design_config.motion_intensity != "static" %}
<!-- Question 1: How often will users see this? -->
<!-- More than 100x/day (keyboard shortcut) → NO animation EVER -->
<!-- Tens of times/day (hover effect) → Remove or drastically reduce -->
<!-- Occasional (modal open) → Standard animation (150-300ms) -->
<!-- Rare (first-time onboarding) → Can add delight (longer, springs) -->

<!-- Question 2: What is the PURPOSE? -->
<!-- spatial_consistency, feedback, explanation, state_indication -->

<!-- Question 3: What EASING? -->
<!-- entrance → ease-out cubic-bezier(0.23, 1, 0.32, 1) -->
<!-- hover/color change → ease -->
<!-- never → ease-in (makes UI feel sluggish) -->

<!-- Question 4: How FAST? -->
<!-- button press = 100-160ms, tooltip = 125-200ms, dropdown = 150-250ms, modal = 200-500ms -->
<!-- UI animations stay under 300ms -->

<button class="ws-cta" style="
  transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
">
  {{ icons.icon('phone', 16) }} Call Now
</button>

<style>
.ws-cta:active {
  transform: scale(0.97);  /* Feedback: button feels responsive to press (Emil) */
}

/* Never animate on keyboard actions */
@media (prefers-reduced-motion: reduce) {
  .ws-cta {
    transition: none;  /* Respect motion sensitivity */
  }
}
</style>
{% endif %}
```

## Example 2: Spacing Scale (From tasteskill)

tasteskill uses design variance dials. NetBuild.Pro collapses these to 3 levels: minimal/balanced/bold. Each has different spacing.

```html
<!-- Access the spacing scale for the current design preset -->
<section class="ws-section {{ design_config.spacing_scale.section_gap }}">
  <!-- spacious: py-32 md:py-48 -->
  <!-- standard: py-20 md:py-32 (default) -->
  <!-- dense: py-12 md:py-20 -->
</section>

<!-- Use card gap too -->
<div class="grid {{ design_config.spacing_scale.card_gap }}">
  <!-- spacious: gap-8 -->
  <!-- standard: gap-6 -->
  <!-- dense: gap-4 -->
</div>
```

## Example 3: Banned Patterns (Absolute Refuses)

tasteskill + Emil explicitly ban these. They are tells of AI slop.

```html
<!-- ❌ FORBIDDEN: Side-stripe border (design tell) -->
<div style="border-left: 4px solid var(--ws-primary)">Content</div>

<!-- ✅ Instead: Full border, background tint, or leading icon -->
<div style="border-left: 1px solid var(--ws-border); padding-left: 1rem">Content</div>

<!-- ❌ FORBIDDEN: Gradient text (background-clip: text) -->
<h1 style="background: linear-gradient(...); background-clip: text">Text</h1>

<!-- ✅ Instead: Single solid color, emphasis via weight/size -->
<h1 style="color: var(--ws-primary); font-weight: 700">Text</h1>

<!-- ❌ FORBIDDEN: Tiny eyebrow on EVERY section (2023 AI scaffold tell) -->
<p style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em">FEATURES</p>
<h2>Section Title</h2>
<!-- (repeated on every section = reflex, not voice) -->

<!-- ✅ Instead: One deliberate kicker, or different cadence -->
<h2>Features</h2>  <!-- No eyebrow, just title -->

<!-- ❌ FORBIDDEN: Numbered scaffolding on every section (01 / 02 / 03) -->
<p>01 · About</p>
<p>02 · Process</p>
<p>03 · Pricing</p>

<!-- ✅ Only if it's a REAL sequence (3-step process, ordered flow) -->
<ol>
  <li>Step 1</li>
  <li>Step 2</li>
  <li>Step 3</li>
</ol>

<!-- ❌ FORBIDDEN: Identical card grid (icon + heading + text, repeated) -->
{% for item in items %}
<div class="card">
  {{ item.icon }}
  <h3>{{ item.title }}</h3>
  <p>{{ item.description }}</p>
</div>
{% endfor %}

<!-- ✅ Instead: Vary sizes, layouts, densities -->
{% for item in items %}
  {% if loop.index0 % 3 == 0 %}
    <div class="card-large">  <!-- Larger card for first of every 3 -->
  {% else %}
    <div class="card-standard">
  {% endif %}
    {{ item.icon }}
    <h3>{{ item.title }}</h3>
    <p>{{ item.description }}</p>
  </div>
{% endfor %}
```

## Example 4: Emil's Component Patterns

### Button Press (Sonner Pattern)

```html
<button class="ws-btn" style="
  transition: transform 160ms cubic-bezier(0.23, 1, 0.32, 1);
">
  Get Started
</button>

<style>
.ws-btn:active {
  transform: scale(0.97);  /* Scale (0.95-0.98), not scale(0) */
}

@media (prefers-reduced-motion: reduce) {
  .ws-btn {
    transition: none;
  }
}
</style>
```

### Entry Animations (Never scale(0))

```html
<div class="ws-toast" style="
  transform: translateY(100%);
  opacity: 0;
  animation: slideIn 400ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
">
  Message sent!
</div>

<style>
@keyframes slideIn {
  from {
    transform: translateY(100%);  /* Hidden below */
    opacity: 0;
  }
  to {
    transform: translateY(0);     /* Visible */
    opacity: 1;
  }
}

/* NEVER: from { transform: scale(0) } — nothing in real world appears from nothing */
</style>
```

### Popover Transform Origin (Emil)

Popovers scale from their trigger, not center. Modals stay centered.

```html
<!-- Radix Popover (automatically provides data attribute) -->
<div class="ws-popover" style="
  transform-origin: var(--radix-popover-content-transform-origin);
  transform: scale(0.95) translateY(-10px);
  opacity: 0;
  animation: popoverEnter 125ms cubic-bezier(0.23, 1, 0.32, 1) forwards;
">
  Menu
</div>

<style>
@keyframes popoverEnter {
  to {
    transform: scale(1) translateY(0);
    opacity: 1;
  }
}

/* EXCEPTION: Modals stay centered (never popover origin) */
.modal {
  transform-origin: center;  /* Center screen, not trigger */
}
</style>
```

### Tooltip Skip-Delay Pattern (Emil)

```html
<div class="ws-tooltip" style="
  transition: opacity 125ms cubic-bezier(0.23, 1, 0.32, 1), 
              transform 125ms cubic-bezier(0.23, 1, 0.32, 1);
  transform: scale(0.97);
  opacity: 0;
  pointer-events: none;
">
  Hover info
</div>

<style>
.ws-tooltip-trigger:hover ~ .ws-tooltip {
  transition-delay: 200ms;  /* First hover waits 200ms */
  transform: scale(1);
  opacity: 1;
}

/* Skip delay + animation on subsequent tooltips (feels faster) */
.ws-tooltip[data-instant] {
  transition-duration: 0ms;  /* Instant, no animation */
}
</style>
```

## Example 5: Performance Guardrails

### Only Animate transform + opacity

```html
<!-- ✅ GOOD: Hardware-accelerated, runs on GPU -->
<div style="
  animation: slideIn 200ms ease-out;
">
  Content
</div>

<style>
@keyframes slideIn {
  from { transform: translateX(-100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>

<!-- ❌ BAD: Causes layout recalc, jank -->
<div style="
  animation: expandHeight 200ms ease-out;
">
  Content
</div>

<style>
@keyframes expandHeight {
  from { height: 0; }
  to { height: 100%; }  <!-- Layout recalc on every frame -->
}
</style>

<!-- ✅ GOOD: Framer Motion with hardware-accelerated transform -->
<motion.div animate={{ transform: "translateX(100px)" }} />

<!-- ❌ BAD: Framer Motion with x prop (not accelerated) -->
<motion.div animate={{ x: 100 }} />  <!-- Uses requestAnimationFrame, drops frames under load -->
</style>
```

### Reduced Motion (Mandatory)

```html
<div class="ws-animated">
  Content
</div>

<style>
.ws-animated {
  animation: fadeIn 400ms ease-out;
}

/* MANDATORY: Respect prefers-reduced-motion (motion sickness) */
@media (prefers-reduced-motion: reduce) {
  .ws-animated {
    animation: fade 200ms ease;  /* Opacity only, no motion */
  }
}
</style>
```

### Touch Device Hover States (Mandatory)

```html
<button class="ws-btn-hover">Hover effect</button>

<style>
/* Only apply hover animations on devices that can hover */
@media (hover: hover) and (pointer: fine) {
  .ws-btn-hover:hover {
    transform: scale(1.05);  /* Desktop only */
  }
}

/* Touch devices skip hover (it triggers on tap, causing false positives) */
</style>
```

## Example 6: Accessibility Mandatory Checks

```html
<!-- ✅ Contrast 4.5:1 on body text -->
<p style="color: var(--ws-ink); background: var(--ws-bg-muted)">
  Body text with sufficient contrast
</p>

<!-- ❌ Contrast < 4.5:1 (fails WCAG 2.1 AA) -->
<p style="color: #999; background: white">Gray text on white (bad)</p>

<!-- ✅ Touch targets 44x44px minimum -->
<button style="min-width: 44px; min-height: 44px; padding: 8px">
  Touch-safe button
</button>

<!-- ✅ Alt text on all images (never empty) -->
<img src="photo.jpg" alt="HVAC technician installing a unit in a residential home">

<!-- ❌ Missing alt text (accessibility violation) -->
<img src="photo.jpg" alt="">  <!-- Empty alt is inaccessible -->
<img src="photo.jpg">           <!-- No alt attribute at all -->

<!-- ✅ Labels above inputs (never placeholder-only) -->
<label for="phone">Phone Number</label>
<input id="phone" type="tel" placeholder="(555) 123-4567">

<!-- ❌ Placeholder-only (label missing) -->
<input type="tel" placeholder="Phone Number">

<!-- ✅ Keyboard navigation (Tab, Enter, Escape work) -->
<button onclick="alert('clicked')">Keyboard-accessible</button>

<!-- ✅ Focus indicators visible (never remove :focus) -->
<button style="outline: 2px solid var(--ws-primary)">Visible focus ring</button>

<!-- ❌ Hidden focus ring (breaks keyboard nav) -->
<button style="outline: none">No focus ring (bad for keyboard users)</button>

<!-- ✅ Inline error messages near field -->
<label for="email">Email</label>
<input id="email" type="email">
<span class="error" style="color: var(--ws-emergency)">Invalid email format</span>
```

## Example 7: Hero Layout (From tasteskill)

tasteskill uses variance dials to change hero layout.

```html
{% if design_config.hero_layout == "center" %}
  <!-- Centered hero (minimal/balanced variance) -->
  <section class="ws-hero" style="text-align: center">
    <h1>{{ site.biz_name }}</h1>
    <p>{{ site.tagline }}</p>
  </section>

{% elif design_config.hero_layout == "split" %}
  <!-- Split/asymmetric hero (bold variance) -->
  <section class="ws-hero" style="display: grid; grid-cols: 1fr 1fr; align-items: center">
    <div>
      <h1>{{ site.biz_name }}</h1>
      <p>{{ site.tagline }}</p>
    </div>
    <div>
      <!-- Image, illustration, or accent element on right -->
    </div>
  </section>

{% elif design_config.hero_layout == "offset" %}
  <!-- Offset hero (bold variance, alternative) -->
  <section class="ws-hero" style="position: relative">
    <div style="position: absolute; top: -2rem; right: -5rem">
      <!-- Floating element for visual interest -->
    </div>
    <h1>{{ site.biz_name }}</h1>
  </section>
{% endif %}
```

## Example 8: Design Config Access in Templates

```html
<!-- Current design preset -->
<body data-design="{{design_config.variance}}">
  <!-- spacious, standard, or dense -->
</body>

<!-- Font family (never Inter) -->
<style>
body {
  font-family: {{ design_config.font_family }};  /* Geist, Satoshi, Cabinet Grotesk, Outfit */
}
</style>

<!-- Container max-width -->
<div class="{{ design_config.container_max_width }}">
  <!-- max-w-7xl (1280px) default -->
</div>

<!-- Animation decision framework -->
{% if design_config.motion_intensity == "cinematic" %}
  <!-- Can use spring animations, longer durations, more delight -->
{% elif design_config.motion_intensity == "fluid" %}
  <!-- Standard animations (150-300ms, purposeful) -->
{% elif design_config.motion_intensity == "static" %}
  <!-- NO perpetual animations, no micro-interactions -->
{% endif %}
```

## Summary: The Rules

1. **Before animating:** Answer Emil's 4 questions (frequency, purpose, easing, duration)
2. **Never animate:** `scale(0)`, `ease-in` on entrance, width/height/padding, keyboard actions
3. **Always animate:** Only `transform` + `opacity`, with respect to `prefers-reduced-motion`
4. **Button press:** `scale(0.97)` on `:active` (Sonner pattern)
5. **Duration:** UI under 300ms, button 100-160ms, tooltip 125-200ms, modal 200-500ms
6. **Easing:** entrance `ease-out cubic-bezier(0.23, 1, 0.32, 1)`, never weak CSS defaults
7. **Accessibility:** 4.5:1 contrast, 44px touch targets, alt text, labels above inputs, focus rings
8. **Performance:** Use CSS for predetermined animation, JS for dynamic/interruptible
9. **Banned patterns:** No gradient text, no side stripes, no sketchy SVGs, no identical cards
10. **Popovers:** Scale from trigger origin, modals stay centered

For more details, see `webstaffr/design_constraints.py`, Emil Kowalski's [animations.dev](https://animations.dev/), and tasteskill's operationalized design modules.
