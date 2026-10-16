"""Mechanical accessibility checks for rendered customer/tenant sites.

Deliberately narrow: every check here is a deterministic rule applied to
already-rendered HTML or the shared stylesheet -- contrast ratios computed
from real CSS custom-property values, missing alt text, unlabeled form
inputs, missing focus-visible styling, and heading-order violations. No
model call, no judgment call, no per-tenant cost -- this runs on every
health check (and can run in CI) exactly like the smoke tests in
scripts/health_check.py, at the same near-zero cost.

Explicitly out of scope, on purpose: anything requiring aesthetic or
subjective judgment (motion feel, palette taste, "does this look
premium"). That's a human-reviewed skill loop invoked on demand, not an
automatic check baked into the render path -- see the design-polish skill
work (docs/DECISIONS.md once written) for why the split is intentional.
Folding a live model call into every site render would add real latency
and real per-render cost to a path that is currently free; this module
stays free by construction, only ever parsing text.

Pure functions only, same as site_renderer.py: no DB access, no network,
no template rendering -- inputs are strings (raw HTML, raw CSS) the
caller already has in hand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class A11yIssue:
    check: str
    detail: str


@dataclass
class A11yReport:
    issues: list[A11yIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, check: str, detail: str) -> None:
        self.issues.append(A11yIssue(check=check, detail=detail))

    def __bool__(self) -> bool:  # so `if report:` reads as "has issues"
        return not self.ok


# ---------------------------------------------------------------------------
# Contrast (WCAG 2.1 AA): 4.5:1 normal text, 3:1 large text/UI components.
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    if not _HEX_RE.match(hex_color):
        raise ValueError(f"not a hex color: {hex_color!r}")
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Per WCAG 2.1 formula (sRGB -> linear -> luminance)."""

    def channel(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two hex colors, always >= 1.0."""
    l1 = _relative_luminance(_hex_to_rgb(hex_a))
    l2 = _relative_luminance(_hex_to_rgb(hex_b))
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# Pairs actually used together in site.css for text-on-background --
# updated by hand if a new pairing is introduced. This is the same
# "explicit, not inferred" choice the never-leak list in
# scripts/health_check.py makes: a hardcoded list of what's supposed to be
# true is easier to reason about and review than a generic CSS parser that
# guesses which declarations pair together.
_TEXT_BACKGROUND_PAIRS: list[tuple[str, str, str, float]] = [
    # (label, text_var, bg_var, minimum_ratio)
    ("body text on white", "--ws-ink", "#ffffff", 4.5),
    ("muted text on white", "--ws-muted", "#ffffff", 4.5),
    ("body text on muted bg", "--ws-ink", "--ws-bg-muted", 4.5),
    ("link/accent on white", "--ws-primary", "#ffffff", 4.5),
    ("white text on primary button", "#ffffff", "--ws-primary", 4.5),
    ("white text on header dark", "--ws-ink-invert", "--ws-header-dark", 4.5),
    ("emergency badge text", "#ffffff", "--ws-emergency", 4.5),
]


def _extract_css_vars(css_text: str) -> dict[str, str]:
    """Pulls `--ws-*: #hex;` declarations out of :root. Only hex values are
    captured -- rgba()/gradient values in this stylesheet are decorative
    (shadows, overlays), not text-on-background pairs, so they're outside
    this check's scope by design, not by oversight."""
    return dict(re.findall(r"(--ws-[a-z-]+)\s*:\s*(#[0-9a-fA-F]{3,6})\s*;", css_text))


def check_css_contrast(css_text: str) -> A11yReport:
    """Checks the shared stylesheet's declared text/background color pairs
    against WCAG AA. Runs once against site.css, not per tenant -- colors
    are global CSS custom properties, not tenant-supplied data."""
    report = A11yReport()
    css_vars = _extract_css_vars(css_text)

    def resolve(value: str) -> str | None:
        if value.startswith("--"):
            return css_vars.get(value)
        return value

    for label, text_ref, bg_ref, minimum in _TEXT_BACKGROUND_PAIRS:
        text_hex = resolve(text_ref)
        bg_hex = resolve(bg_ref)
        if text_hex is None or bg_hex is None:
            report.add(
                "css_contrast",
                f"{label}: could not resolve color (text={text_ref!r} -> {text_hex!r}, "
                f"bg={bg_ref!r} -> {bg_hex!r}) -- check site.css still defines this variable",
            )
            continue
        ratio = contrast_ratio(text_hex, bg_hex)
        if ratio < minimum:
            report.add(
                "css_contrast",
                f"{label}: {ratio:.2f}:1, below WCAG AA minimum {minimum}:1 "
                f"({text_hex} on {bg_hex})",
            )
    return report


# ---------------------------------------------------------------------------
# Rendered-HTML structural checks: alt text, form labels, heading order.
# ---------------------------------------------------------------------------


class _A11yHTMLParser(HTMLParser):
    """Single pass over one rendered page. Collects the raw signals the
    checks below need -- doesn't itself decide pass/fail, so the parsing
    and the rules stay independently testable."""

    def __init__(self) -> None:
        super().__init__()
        self.images: list[dict] = []
        self.inputs: list[dict] = []
        self.headings: list[tuple[int, str]] = []
        self._current_label_for: str | None = None
        self._heading_depth: int | None = None
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "img":
            self.images.append(attr_dict)
        elif tag == "input":
            input_type = (attr_dict.get("type") or "text").lower()
            if input_type in ("hidden", "submit", "button", "image"):
                return
            self.inputs.append(attr_dict)
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._heading_depth = int(tag[1])
            self._heading_text = []

    def handle_data(self, data: str) -> None:
        if self._heading_depth is not None:
            self._heading_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._heading_depth is not None and tag == f"h{self._heading_depth}":
            self.headings.append((self._heading_depth, "".join(self._heading_text).strip()))
            self._heading_depth = None
            self._heading_text = []


def check_html_structure(html_text: str, *, page_label: str = "page") -> A11yReport:
    """Structural checks on one rendered page's HTML: every <img> has
    non-empty alt text, every non-hidden <input> has an accessible label
    (aria-label, aria-labelledby, or a matching <label for>), and heading
    levels don't skip (h1 -> h3 with no h2)."""
    report = A11yReport()
    parser = _A11yHTMLParser()
    parser.feed(html_text)

    for img in parser.images:
        alt = img.get("alt")
        if alt is None or not alt.strip():
            src = img.get("src", "unknown src")
            report.add("img_alt", f"{page_label}: <img src={src!r}> missing non-empty alt text")

    label_for_ids = set(re.findall(r'<label[^>]*\sfor="([^"]+)"', html_text))
    for inp in parser.inputs:
        has_aria = bool(inp.get("aria-label") or inp.get("aria-labelledby"))
        input_id = inp.get("id")
        has_label_for = bool(input_id and input_id in label_for_ids)
        if not (has_aria or has_label_for):
            name = inp.get("name") or inp.get("id") or "unnamed"
            report.add(
                "input_label",
                f"{page_label}: <input name/id={name!r}> has no associated <label>, "
                f"aria-label, or aria-labelledby",
            )

    prev_level = 0
    for level, text in parser.headings:
        if prev_level and level > prev_level + 1:
            report.add(
                "heading_order",
                f"{page_label}: heading level jumps from h{prev_level} to h{level} "
                f"({text!r}) -- no intermediate h{prev_level + 1}",
            )
        prev_level = level
    return report


def check_focus_visible(css_text: str) -> A11yReport:
    """Confirms the stylesheet defines a :focus-visible rule for the
    interactive element classes the templates actually use. Doesn't
    validate every selector combination -- just that the mechanism exists
    at all, which is the failure mode worth catching automatically (a
    future edit silently deleting the block)."""
    report = A11yReport()
    if ":focus-visible" not in css_text:
        report.add(
            "focus_visible",
            "site.css defines no :focus-visible rule -- keyboard-navigation focus "
            "indicator is missing",
        )
    return report


def check_page(html_text: str, *, page_label: str = "page") -> A11yReport:
    """Convenience wrapper: all HTML-structure checks for one rendered
    page, combined into a single report."""
    return check_html_structure(html_text, page_label=page_label)
