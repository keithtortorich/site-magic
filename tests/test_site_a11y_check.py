import unittest

from webstaffr.site_a11y_check import (
    check_css_contrast,
    check_focus_visible,
    check_html_structure,
    contrast_ratio,
)


class ContrastRatioTestCase(unittest.TestCase):
    def test_black_on_white_is_max_contrast(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)

    def test_identical_colors_is_min_contrast(self):
        self.assertAlmostEqual(contrast_ratio("#2a6df5", "#2a6df5"), 1.0, places=2)

    def test_order_independent(self):
        a = contrast_ratio("#16202e", "#ffffff")
        b = contrast_ratio("#ffffff", "#16202e")
        self.assertAlmostEqual(a, b, places=6)

    def test_short_hex_supported(self):
        self.assertAlmostEqual(contrast_ratio("#000", "#fff"), 21.0, places=1)


_SITE_CSS_PATH = (
    __import__("pathlib").Path(__file__).parent.parent
    / "webstaffr" / "templates" / "site" / "static" / "site.css"
)


class CssContrastCheckTestCase(unittest.TestCase):
    def test_real_site_css_vars_pass_aa(self):
        # Reads the actual shipped stylesheet, not a copy-pasted literal --
        # this is the regression guard: if someone edits site.css and drops
        # contrast below AA, this test fails without needing a rendered
        # page at all, and can never drift out of sync with the real file.
        css = _SITE_CSS_PATH.read_text()
        report = check_css_contrast(css)
        self.assertTrue(report.ok, f"unexpected contrast failures: {report.issues}")

    def test_flags_insufficient_contrast(self):
        css = """
        :root {
          --ws-primary: #cccccc;
          --ws-primary-dark: #1f4fb8;
          --ws-ink: #16202e;
          --ws-ink-invert: #f4f6f9;
          --ws-muted: #5a6672;
          --ws-bg-muted: #f4f6f9;
          --ws-border: #e2e6ec;
          --ws-header-dark: #101826;
          --ws-emergency: #e74c3c;
        }
        """
        report = check_css_contrast(css)
        self.assertFalse(report.ok)
        self.assertTrue(any("link/accent" in i.detail for i in report.issues))

    def test_flags_unresolvable_variable(self):
        css = ":root { --ws-primary: #2a6df5; }"  # missing most vars
        report = check_css_contrast(css)
        self.assertFalse(report.ok)


class HtmlStructureCheckTestCase(unittest.TestCase):
    def test_clean_page_passes(self):
        html = """
        <html><body>
          <h1>Contact Us</h1>
          <h2>Reach Out</h2>
          <img src="/a.png" alt="Our team on a job site">
          <label for="email">Email</label>
          <input type="email" id="email" name="email">
        </body></html>
        """
        report = check_html_structure(html)
        self.assertTrue(report.ok, f"unexpected issues: {report.issues}")

    def test_flags_missing_alt_text(self):
        html = '<img src="/a.png">'
        report = check_html_structure(html)
        self.assertFalse(report.ok)
        self.assertTrue(any(i.check == "img_alt" for i in report.issues))

    def test_flags_empty_alt_text(self):
        html = '<img src="/a.png" alt="">'
        report = check_html_structure(html)
        self.assertFalse(report.ok)
        self.assertTrue(any(i.check == "img_alt" for i in report.issues))

    def test_flags_unlabeled_input(self):
        html = '<input type="text" name="business_name">'
        report = check_html_structure(html)
        self.assertFalse(report.ok)
        self.assertTrue(any(i.check == "input_label" for i in report.issues))

    def test_input_with_aria_label_passes(self):
        html = '<input type="text" name="business_name" aria-label="Business name">'
        report = check_html_structure(html)
        self.assertTrue(report.ok)

    def test_hidden_and_submit_inputs_exempt(self):
        html = """
        <input type="hidden" name="tenant_id" value="acme">
        <input type="submit" value="Send">
        """
        report = check_html_structure(html)
        self.assertTrue(report.ok)

    def test_flags_skipped_heading_level(self):
        html = "<h1>Title</h1><h3>Skipped h2</h3>"
        report = check_html_structure(html)
        self.assertFalse(report.ok)
        self.assertTrue(any(i.check == "heading_order" for i in report.issues))

    def test_sequential_headings_pass(self):
        html = "<h1>Title</h1><h2>Section</h2><h3>Subsection</h3>"
        report = check_html_structure(html)
        self.assertTrue(report.ok)

    def test_page_label_included_in_detail(self):
        html = '<img src="/a.png">'
        report = check_html_structure(html, page_label="about page")
        self.assertIn("about page", report.issues[0].detail)


class FocusVisibleCheckTestCase(unittest.TestCase):
    def test_passes_when_rule_present(self):
        css = "a:focus-visible { outline: 2px solid blue; }"
        self.assertTrue(check_focus_visible(css).ok)

    def test_flags_when_rule_absent(self):
        css = "a:hover { color: blue; }"
        report = check_focus_visible(css)
        self.assertFalse(report.ok)
        self.assertEqual(report.issues[0].check, "focus_visible")


if __name__ == "__main__":
    unittest.main()
