"""Generated pages must carry URLs, not filesystem paths.

Regression for a defect found 2026-08-11: `generate_site_for_submission()`
built its link base from `web_dir.as_posix()`, so every generated page shipped
`href="/Users/doc/Desktop/NetBuild.Pro/generated_sites/<tenant>/web/..."` in
its navigation, its `<link rel="canonical">`, and its `og:url`. Broken
wherever the site is actually served, and it leaked the build machine's
directory layout into public HTML and into SEO canonical tags.

The URL space here must match what `site_render_router` serves:
`/sites/{tenant_id}/web`.
"""

import os

import pytest

from webstaffr.intake import IntakeSubmission
from webstaffr.site_magic_engine import (
    generate_site_for_submission,
    resolve_public_base_url,
)


def _submission(tenant_id: str = "urltest_hvac") -> IntakeSubmission:
    return IntakeSubmission(
        tenant_id=tenant_id,
        biz_name="Ridgeline Heating and Air",
        phone="(509) 555-0142",
        email="office@ridgelinehvac.example",
        industry="HVAC",
        service_area="Spokane Valley, WA",
        tagline="Comfort you can count on.",
        differentiator="Family owned since 2009.",
        services=["Furnace repair", "AC repair", "Heat pump service"],
        license_number="WA-RIDGEH*123CD",
        plan="growth",
        lead_routing="dispatch@ridgelinehvac.example",
        approver="Dana Whitlock",
    )


@pytest.fixture(autouse=True)
def _clear_base_url(monkeypatch):
    monkeypatch.delenv("NETBUILD_PUBLIC_BASE_URL", raising=False)


def _generated_html(workdir) -> dict[str, str]:
    result = generate_site_for_submission(_submission(), workdir)
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in result.output_dir.glob("*.html")
    }


def test_no_filesystem_path_leaks_into_generated_html(tmp_path):
    pages = _generated_html(tmp_path)
    assert pages, "expected at least one generated page"

    workdir_marker = str(tmp_path)
    for name, html in pages.items():
        assert workdir_marker not in html, f"{name} leaks the on-disk workdir path"
        assert "/Users/" not in html, f"{name} leaks an absolute filesystem path"


def test_links_use_the_route_url_space(tmp_path):
    pages = _generated_html(tmp_path)
    home = pages["home.html"]

    assert 'href="/sites/urltest_hvac/web/services/' in home


def test_relative_canonical_and_og_url_are_omitted_not_emitted_invalid(tmp_path):
    """A relative `rel=canonical` is invalid, and Lighthouse fails the
    `canonical` audit on one -- which is what dropped the generated site's SEO
    score to 91. With no configured origin there is no correct absolute URL to
    emit, and tenant sites can live on their own custom domains, so there is
    no origin worth hardcoding either. Omit both tags instead."""
    pages = _generated_html(tmp_path)

    for name, html in pages.items():
        assert "rel=\"canonical\"" not in html, f"{name} emits a canonical with no origin set"
        assert "og:url" not in html, f"{name} emits og:url with no origin set"
        # The rest of the head is unaffected.
        assert 'property="og:title"' in html
        assert 'property="og:type"' in html


def test_public_base_url_makes_canonical_and_og_absolute(tmp_path, monkeypatch):
    monkeypatch.setenv("NETBUILD_PUBLIC_BASE_URL", "https://netbuild.pro/")
    pages = _generated_html(tmp_path)
    home = pages["home.html"]

    assert (
        '<link rel="canonical" href="https://netbuild.pro/sites/urltest_hvac/web">'
        in home
    )
    assert (
        '<meta property="og:url" content="https://netbuild.pro/sites/urltest_hvac/web">'
        in home
    )
    assert 'href="https://netbuild.pro/sites/urltest_hvac/web/services/' in home


def test_about_page_canonical_points_at_its_own_path(tmp_path, monkeypatch):
    monkeypatch.setenv("NETBUILD_PUBLIC_BASE_URL", "https://netbuild.pro")
    pages = _generated_html(tmp_path)
    about = pages["about.html"]

    assert (
        '<link rel="canonical" href="https://netbuild.pro/sites/urltest_hvac/web/about">'
        in about
    )


@pytest.mark.parametrize(
    "configured,expected",
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("https://netbuild.pro", "https://netbuild.pro"),
        ("https://netbuild.pro/", "https://netbuild.pro"),
        ("  https://netbuild.pro//  ", "https://netbuild.pro"),
    ],
)
def test_resolve_public_base_url_normalizes(monkeypatch, configured, expected):
    if configured is None:
        monkeypatch.delenv("NETBUILD_PUBLIC_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("NETBUILD_PUBLIC_BASE_URL", configured)
    assert resolve_public_base_url() == expected


def test_root_token_style_block_is_valid_css(tmp_path):
    """Regression: the inline `:root { ... }` block was built with an
    f-string missing its literal braces (`f":root {_tokens_css_vars(...)}"`),
    so every generated page shipped `:root --ws-brand-primary: ...;` with no
    enclosing `{}` -- invalid CSS that browsers silently drop, killing all
    brand color styling."""
    pages = _generated_html(tmp_path)
    home = pages["home.html"]

    assert ":root {" in home
    assert "--ws-brand-primary:" in home
    style_block = home.split("<style>", 1)[1].split("</style>", 1)[0]
    assert style_block.count("{") == style_block.count("}")
