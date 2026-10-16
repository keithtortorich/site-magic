"""Design constraint rules extracted from Emil Kowalski's animation philosophy
and tasteskill's operationalized design directives.

These constraints ensure every customer site and the agency site respect:
- Emil's animation decision framework (frequency, purpose, easing)
- tasteskill's banned patterns (no neon glows, no overstuffed cards, no emoji)
- Apple design principles (springs, interruptibility, velocity handoff)
- Accessibility requirements (contrast, alt text, keyboard nav)
- Performance guardrails (no jank, hardware acceleration)

Wired into site_renderer.py and templates at build time.
"""

from dataclasses import dataclass, field
from typing import Literal

# Animation frequency tiers (from Emil's decision framework)
AnimationFrequency = Literal["never", "rarely", "occasional", "frequent"]

# Design variance dials (from tasteskill)
DesignVariance = Literal["minimal", "balanced", "bold"]
MotionIntensity = Literal["static", "fluid", "cinematic"]
VisualDensity = Literal["spacious", "standard", "dense"]


@dataclass
class AnimationConstraints:
    """Emil Kowalski's animation decision framework: 4 questions before any animation.

    1. Should this animate at all? (frequency → never/rarely/occasional/frequent)
    2. What is the purpose? (spatial_consistency/feedback/explanation/state_indication)
    3. What easing? (entrance → ease-out, exit → linear/no easing, hover → ease)
    4. How fast? (button=100-160ms, tooltip=125-200ms, dropdown=150-250ms, modal=200-500ms)

    Rule: UI animations stay under 300ms. Never animate keyboard-initiated actions.
    """

    frequency: AnimationFrequency = "occasional"
    purpose: str = "spatial_consistency"
    easing: str = "ease-out"  # ease-out (cubic-bezier 0.23,1 0.32,1) for entrances/feedback
    duration_ms: int = 250
    use_springs: bool = False  # True for gesture-driven, drag-to-dismiss, momentum
    spring_stiffness: int = 100  # mass=1, stiffness=100, damping=10 (Apple-style)
    spring_bounce: float = 0.2  # subtle bounce 0.1-0.3 only for delight, not UI

    @property
    def allowed(self) -> bool:
        """Animation should only happen if frequency is not 'never' and purpose is clear."""
        return self.frequency != "never" and self.purpose != ""

    @property
    def banned_patterns(self) -> list[str]:
        """Patterns that violate Emil's animation principles (from animations.dev)."""
        bans = []
        if self.frequency == "frequent" and self.use_springs is False:
            bans.append("FORBIDDEN: CSS transition on high-frequency action (use springs or remove)")
        if self.easing == "ease-in" and self.frequency in ("frequent", "occasional"):
            bans.append("FORBIDDEN: ease-in on entrance (feels sluggish, use ease-out cubic-bezier(0.23,1,0.32,1))")
        if self.duration_ms < 100:
            bans.append("FORBIDDEN: animation duration < 100ms (feels jittery)")
        if self.duration_ms > 800 and self.frequency in ("frequent", "occasional"):
            bans.append("FORBIDDEN: duration > 800ms on high-frequency action (feels slow, cap at 300ms for UI)")
        if self.frequency == "frequent" and self.purpose == "explanation":
            bans.append("FORBIDDEN: explanatory animation on frequent action (reserve explanation for rare first-time)")
        if "scale(0)" in str(getattr(self, "transform", "")):
            bans.append("FORBIDDEN: animate from scale(0) (nothing in real world appears from nothing, start at 0.95 + opacity)")
        return bans

    @property
    def easing_curves(self) -> dict[str, str]:
        """Custom easing curves (from easing.dev, not weak CSS defaults)."""
        return {
            "ease-out": "cubic-bezier(0.23, 1, 0.32, 1)",
            "ease-in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
            "ease-drawer": "cubic-bezier(0.32, 0.72, 0, 1)",
            "linear": "linear",
        }


@dataclass
class DesignSystemConfig:
    """Operationalized design rules from tasteskill + Emil's component principles.

    tasteskill: Registry-based design with preset skill modules (taste-skill, image-to-code, redesign, etc).
    Emil: Unseen details compound — taste is trained, beauty is leverage.
    Bans: No side-stripe borders, no gradient text, no sketchy SVGs, no identical card grids,
          no tiny eyebrow on every section (saturated AI tell), no numbered scaffolding.
    """

    variance: DesignVariance = "balanced"
    motion_intensity: MotionIntensity = "fluid"
    visual_density: VisualDensity = "standard"
    brand_primary: str = "#2a6df5"
    font_family: str = "Geist"  # Geist (premium), never Inter (overdone in AI)
    container_max_width: str = "max-w-7xl"

    @property
    def spacing_scale(self) -> dict[str, str]:
        """Spacing tokens based on visual density (Emil: unseen details compound)."""
        scales = {
            "spacious": {"section_gap": "py-32 md:py-48", "card_gap": "gap-8", "padding": "p-10"},
            "standard": {"section_gap": "py-20 md:py-32", "card_gap": "gap-6", "padding": "p-8"},
            "dense": {"section_gap": "py-12 md:py-20", "card_gap": "gap-4", "padding": "p-6"},
        }
        return scales[self.visual_density]

    @property
    def button_styles(self) -> dict[str, str]:
        """Button must feel responsive. Add scale(0.97) on :active (Emil principle)."""
        return {
            "base": "transition-transform 160ms ease-out",
            "active": "transform scale-[0.97]",
            "feedback": "scale 160ms ease-out (instant, not delayed)",
        }

    @property
    def popover_transform_origin(self) -> str:
        """Popovers scale from trigger, not center. Modals stay centered (Emil)."""
        return "var(--radix-popover-content-transform-origin) or var(--transform-origin)"

    @property
    def tooltip_pattern(self) -> dict[str, str]:
        """Skip delay + animation on subsequent hovers (feels faster without defeat purpose)."""
        return {
            "first": "delay-200 duration-125ms ease-out",
            "subsequent": "duration-0 (instant, no animation)",
            "markup": "use data-instant attribute on tooltip[data-instant]",
        }

    @property
    def banned_patterns(self) -> list[str]:
        """tasteskill + Emil bans (AI slop tells and pattern violations)."""
        bans = [
            "NO_EMOJI: BANNED in code, markup, alt text, content (use Phosphor/Radix icons)",
            "NO_INTER: BANNED as primary font (use Geist, Satoshi, Cabinet Grotesk, Outfit)",
            "NO_NEON_GLOW: BANNED (no outer glows > 8px, use inner borders or tinted shadows instead)",
            "NO_PURE_BLACK: BANNED (use Zinc-950 #18181b or Off-Black #0f0f0f)",
            "NO_GRADIENT_TEXT: BANNED (background-clip: text, use single solid color + weight/size for emphasis)",
            "NO_SKETCHY_SVG: BANNED (feTurbulence/feDisplacementMap hand-drawn doodles feel amateurish, omit or use real assets)",
            "NO_SIDE_STRIPE: BANNED (border-left/right > 1px as accent, use full borders, bg tints, or leading icons)",
            "NO_EXCESSIVE_GRADIENTS: BANNED on large text (one accent max, saturation < 80%)",
            "NO_3COL_CARDS: BANNED (use 2-col zig-zag, asymmetric grid, horizontal scroll, or nested cards)",
            "NO_CENTERED_HERO_IF_BOLD: BANNED when variance='bold' (force split-screen or offset layout)",
            "NO_CARD_OVERUSE: BANNED on high density (use borders/divide-y, only cards for elevation)",
            "NO_TINY_EYEBROW_EVERY_SECTION: BANNED (small all-caps kicker on EVERY section is 2023 AI scaffold, use one deliberate kicker or different cadence)",
            "NO_NUMBERED_SCAFFOLDING: BANNED on every section (01/02/03 on every section is reflex, not voice — use numbered only for real sequences)",
            "NO_HERO_METRICS_TEMPLATE: BANNED (big number + small label + gradient accent = SaaS cliché)",
            "NO_IDENTICAL_CARD_GRID: BANNED (icon + heading + text repeated is lazy; vary sizes, layouts, densities)",
            "NO_GLASSMORPHISM_DEFAULT: BANNED (blurs/glass cards decorative only, rare and purposeful or nothing)",
            "NO_OVERFLOW_TEXT: BANNED (test headlines at every breakpoint; if overflow, reduce clamp max or rewrite)",
        ]
        if self.motion_intensity == "static":
            bans.append("NO_PERPETUAL_ANIMATION: STATIC mode forbids infinite loops, spinning spinners, micro-interactions")
        return bans

    @property
    def hero_layout(self) -> Literal["center", "split", "offset"]:
        """Hero section layout based on variance dial."""
        layouts = {
            "minimal": "center",
            "balanced": "center",
            "bold": "split",
        }
        return layouts[self.variance]

    @property
    def emil_component_patterns(self) -> dict[str, str]:
        """Exact patterns from Emil Kowalski's design engineering philosophy."""
        return {
            "button_press": "transition: transform 160ms ease-out; :active { transform: scale(0.97) }",
            "enter_not_scale_0": "start from scale(0.95) + opacity: 0, NOT scale(0)",
            "popover_origin": "transform-origin: var(--radix-popover-content-transform-origin)",
            "tooltip_delay_skip": "[data-instant] { transition-duration: 0ms } on subsequent tooltips",
            "blur_transition": "filter: blur(2px) during crossfade between states (bridges visual gap)",
            "clip_path_reveal": "clip-path: inset(0 100% 0 0) → inset(0 0 0 0) for smooth reveals",
            "reduced_motion": "@media (prefers-reduced-motion: reduce) { remove transform-based motion, keep opacity/color }",
        }


@dataclass
class AccessibilityConstraints:
    """WCAG 2.1 AA baseline + Apple/tasteskill UX rules."""

    contrast_ratio_normal: float = 4.5  # body text, UI components
    contrast_ratio_large: float = 3.0  # 18pt+ or bold 14pt+
    touch_target_min_px: int = 44  # Apple HIG + WCAG
    min_font_size_px: int = 12  # body text (max 16px is default)
    require_alt_text: bool = True
    require_labels_above_inputs: bool = True
    require_keyboard_nav: bool = True
    require_reduced_motion_support: bool = True

    @property
    def mandatory_checks(self) -> list[str]:
        """Pre-delivery checklist."""
        return [
            "Contrast 4.5:1+ on body/UI, 3:1+ on large text",
            "Touch targets 44x44px minimum (spacing 8px+)",
            "Alt text on all images (never empty, never just filename)",
            "Labels sit ABOVE inputs (never placeholder-only)",
            "Keyboard navigation works (Tab, Enter, Escape)",
            "Reduced-motion: prefers-reduced-motion honored (no auto-play, instant feedback)",
            "Form errors appear inline near field (not just at top)",
            "Focus indicators visible (never remove :focus ring)",
        ]


@dataclass
class PerformanceGuardrails:
    """Animation performance constraints from Emil Kowalski + Apple HIG.

    Emil's rule: Only animate transform (translate, scale, rotate) and opacity.
    Framer Motion gotcha: x/y/scale props are NOT hardware-accelerated (use transform string).
    CSS animations beat JS under load (run off main thread, stay smooth during page loads).
    """

    animate_only_transform_opacity: bool = True
    use_will_change_sparingly: bool = True
    avoid_layout_thrashing: bool = True
    prefer_css_grid_over_flexbox_math: bool = True
    hardware_accelerate_transforms: bool = True
    max_z_index_layers: int = 5
    debounce_scroll_listeners_ms: int = 16
    virtualize_long_lists: bool = True

    @property
    def animation_do_dont(self) -> dict[str, list[str]]:
        """Emil's do's/don'ts for 60fps animations (from animations.dev)."""
        return {
            "DO": [
                "Animate transform (translate, scale, rotate) and opacity only",
                "Use springs for gesture-driven interactions, momentum, drag-to-dismiss",
                "Use CSS animations for predetermined motion (off main thread, smooth under load)",
                "Use WAAPI (Web Animations API) for programmatic CSS animations with JS control",
                "Batch DOM reads/writes (read all, then write all)",
                "Isolate perpetual animations in own memoized/memo'd component",
                "Use transform-origin for scale/rotation anchoring (popovers from trigger, modals centered)",
                "Isolate GSAP/ThreeJS in fixed backgrounds (pointer-events-none)",
                "Prefer CSS Grid (grid-cols-3) over flexbox percentage math",
                "Use clip-path for reveals, tabs, comparison sliders (hardware-accelerated)",
                "Test on real devices for touch interactions (Xcode Simulator insufficient)",
                "Review animations at slow motion (DevTools Animations) to spot timing issues",
            ],
            "DON'T": [
                "Animate width, height, top, left, padding, margin (causes layout recalc)",
                "Use Framer Motion x/y/scale props (not hardware-accelerated, use transform string)",
                "Use will-change as band-aid (measure performance impact first)",
                "Trigger scroll listeners on every pointermove (debounce 16ms minimum)",
                "Mix GSAP + Framer Motion in same component tree (conflicting animations)",
                "Render 1000 list items at once (virtualize with React Window / Tan stack)",
                "Use h-screen for full-height (use min-h-[100dvh] for mobile safe area)",
                "Apply grain/noise filters to scrolling containers (triggers GPU repaints on every frame)",
                "Animate keyframes on rapidly-triggered elements (use CSS transitions for interruptibility)",
                "Use ease-in on UI elements (starts slow, feels sluggish)",
                "Skip @media (prefers-reduced-motion: reduce) (motion sickness requirement)",
                "Hover animations without @media (hover: hover) and (pointer: fine) (breaks on touch)",
            ],
        }

    @property
    def framer_motion_notes(self) -> dict[str, str]:
        """Framer Motion gotchas (from Emil + Vercel dashboard incident)."""
        return {
            "x_y_not_accelerated": "motion.div animate={{ x: 100 }} drops frames under load → use animate={{ transform: 'translateX(100px)' }}",
            "under_load": "CSS animations (offscreen) beat Framer Motion (requestAnimationFrame) when main thread busy",
            "interruptible": "Shared Layout Animations cause frame drops during page loads; prefer CSS transitions",
            "solution": "Use CSS for predetermined animations; JS (Framer Motion) for dynamic, interruptible ones",
        }

    @property
    def sonner_principles(self) -> dict[str, str]:
        """From Sonner (13M+ weekly npm, used by Vercel): what makes loved components."""
        return {
            "dx_first": "No hooks, no context, no setup friction. Insert once, use everywhere.",
            "good_defaults": "Ship beautiful out of box. Most users never customize.",
            "naming": "Identity matters (Sonner = elegant, not react-toast = forgettable)",
            "edge_cases": "Pause timers when tab hidden, handle gaps invisibly, capture pointer events",
            "transitions_not_keyframes": "Transitions retarget smoothly on interruption; keyframes restart from zero",
            "cohesion": "Animation style matches component vibe (playful = bouncier, professional = crisp)",
            "review_next_day": "Fresh eyes catch imperfections invisible during dev",
        }


# Preset configurations (ready-to-use constraint sets)
PRESET_MINIMAL = DesignSystemConfig(
    variance="minimal",
    motion_intensity="static",
    visual_density="spacious",
)

PRESET_BALANCED = DesignSystemConfig(
    variance="balanced",
    motion_intensity="fluid",
    visual_density="standard",
)

PRESET_BOLD = DesignSystemConfig(
    variance="bold",
    motion_intensity="cinematic",
    visual_density="standard",
)

PRESET_DENSE_DASHBOARD = DesignSystemConfig(
    variance="minimal",
    motion_intensity="fluid",
    visual_density="dense",
    font_family="Geist Mono",  # monospace for dashboards
)


def validate_constraints(config: DesignSystemConfig) -> list[str]:
    """Audit a design config for violations. Returns list of violations (empty if clean)."""
    violations = []
    violations.extend(config.banned_patterns)
    return violations


def apply_constraints(site_data: dict, preset: str = "balanced") -> dict:
    """Apply design constraints to site data context for template rendering.

    Returns enhanced context with animation rules, banned patterns, spacing scale, etc."""
    presets = {
        "minimal": PRESET_MINIMAL,
        "balanced": PRESET_BALANCED,
        "bold": PRESET_BOLD,
        "dense-dashboard": PRESET_DENSE_DASHBOARD,
    }
    config = presets.get(preset, PRESET_BALANCED)

    return {
        "design_config": config,
        "spacing": config.spacing_scale,
        "hero_layout": config.hero_layout,
        "banned_patterns": config.banned_patterns,
        "a11y": AccessibilityConstraints(),
        "perf": PerformanceGuardrails(),
    }
