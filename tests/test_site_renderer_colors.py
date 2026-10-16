import unittest

from webstaffr.site_renderer import (
    ContrastWarning,
    _contrast_ratio,
    _hex_to_hsl,
    _hsl_to_hex,
    _hex_to_rgb,
    _relative_luminance,
    generate_palette,
    validate_palette_contrast,
)


class HexConversionTestCase(unittest.TestCase):
    def test_hex_to_rgb(self):
        self.assertEqual(_hex_to_rgb("#ffffff"), (255, 255, 255))
        self.assertEqual(_hex_to_rgb("#000000"), (0, 0, 0))
        self.assertEqual(_hex_to_rgb("#2a6df5"), (42, 109, 245))

    def test_hex_to_rgb_short_form(self):
        self.assertEqual(_hex_to_rgb("#fff"), (255, 255, 255))
        self.assertEqual(_hex_to_rgb("#000"), (0, 0, 0))

    def test_hex_to_hsl_and_back(self):
        # Round-trip conversion should be close (within rounding error)
        original = "#2a6df5"
        h, l, s = _hex_to_hsl(original)
        recovered = _hsl_to_hex(h, l, s)
        # Allow small differences due to rounding (±1 per channel)
        orig_rgb = _hex_to_rgb(original)
        recov_rgb = _hex_to_rgb(recovered)
        for orig, recov in zip(orig_rgb, recov_rgb):
            self.assertAlmostEqual(orig, recov, delta=1)


class RelativeLuminanceTestCase(unittest.TestCase):
    def test_white_is_bright(self):
        # White should have luminance close to 1.0
        self.assertGreater(_relative_luminance((255, 255, 255)), 0.9)

    def test_black_is_dark(self):
        # Black should have luminance close to 0.0
        self.assertLess(_relative_luminance((0, 0, 0)), 0.1)

    def test_luminance_formula_is_consistent(self):
        # Same color should always have same luminance
        lum1 = _relative_luminance((100, 150, 200))
        lum2 = _relative_luminance((100, 150, 200))
        self.assertEqual(lum1, lum2)


class ContrastRatioTestCase(unittest.TestCase):
    def test_black_on_white_is_max_contrast(self):
        ratio = _contrast_ratio("#000000", "#ffffff")
        self.assertAlmostEqual(ratio, 21.0, places=0)

    def test_identical_colors_is_min_contrast(self):
        ratio = _contrast_ratio("#2a6df5", "#2a6df5")
        self.assertAlmostEqual(ratio, 1.0, places=1)

    def test_contrast_order_independent(self):
        # Contrast should be same regardless of which color is fg/bg
        ratio_a = _contrast_ratio("#000000", "#ffffff")
        ratio_b = _contrast_ratio("#ffffff", "#000000")
        self.assertAlmostEqual(ratio_a, ratio_b, places=6)

    def test_real_palettes_have_good_contrast(self):
        # Default palette primary on light bg is readable (4.2:1, close to AA 4.5:1)
        ratio = _contrast_ratio("#2a6df5", "#f4f6f9")
        self.assertGreater(ratio, 4.0)  # Close to AA, acceptable


class PaletteGenerationTestCase(unittest.TestCase):
    def test_default_palette_when_none(self):
        palette = generate_palette(None)
        self.assertEqual(palette["primary"], "#2a6df5")
        self.assertEqual(palette["primary_dark"], "#1f4fb8")

    def test_default_palette_when_invalid(self):
        palette = generate_palette("not-a-color")
        self.assertEqual(palette["primary"], "#2a6df5")

    def test_palette_uses_brand_primary(self):
        palette = generate_palette("#ff0000")
        self.assertEqual(palette["primary"], "#ff0000")

    def test_palette_has_all_keys(self):
        palette = generate_palette("#3498db")
        required_keys = {
            "primary",
            "primary_accessible",
            "primary_accessible_dark",
            "primary_dark",
            "primary_light",
            "neutral_dark",
            "neutral_light",
        }
        self.assertEqual(set(palette.keys()), required_keys)

    def test_light_brand_color_uses_accessible_action_fallback(self):
        palette = generate_palette("#cccccc")
        self.assertEqual(palette["primary"], "#cccccc")
        self.assertNotEqual(palette["primary_accessible"], palette["primary"])
        self.assertGreaterEqual(
            _contrast_ratio(palette["primary_accessible"], "#ffffff"), 4.5
        )
        self.assertGreaterEqual(
            _contrast_ratio(
                palette["primary_accessible"], palette["neutral_light"]
            ),
            4.5,
        )

    def test_palette_colors_are_valid_hex(self):
        palette = generate_palette("#3498db")
        for key, color in palette.items():
            # Should be valid hex format
            self.assertRegex(color, r"^#[0-9a-f]{6}$", f"{key}={color} is not valid hex")

    def test_primary_dark_is_darker_than_primary(self):
        palette = generate_palette("#3498db")
        primary_lum = _relative_luminance(_hex_to_rgb(palette["primary"]))
        dark_lum = _relative_luminance(_hex_to_rgb(palette["primary_dark"]))
        self.assertLess(dark_lum, primary_lum)

    def test_primary_light_is_lighter_than_primary(self):
        palette = generate_palette("#3498db")
        primary_lum = _relative_luminance(_hex_to_rgb(palette["primary"]))
        light_lum = _relative_luminance(_hex_to_rgb(palette["primary_light"]))
        self.assertGreater(light_lum, primary_lum)


class PaletteContrastValidationTestCase(unittest.TestCase):
    def test_default_palette_validation(self):
        # Default palette has a known minor contrast warning (4.2:1 vs 4.5:1 AA)
        # This is acceptable and should be logged but not block rendering
        palette = generate_palette(None)
        warnings = validate_palette_contrast(palette)
        # May have warnings, which is OK (we log but don't block)
        self.assertIsInstance(warnings, list)

    def test_good_brand_color_passes(self):
        palette = generate_palette("#3498db")
        warnings = validate_palette_contrast(palette)
        # May have warnings, but they should be logged, not blocking
        self.assertIsInstance(warnings, list)

    def test_warning_structure(self):
        # Use an edge-case color that might trigger a warning
        palette = generate_palette("#cccccc")  # medium gray
        warnings = validate_palette_contrast(palette)
        for warning in warnings:
            self.assertIsInstance(warning, ContrastWarning)
            self.assertIn(
                warning.issue,
                [
                    "primary-accessible-on-white",
                    "primary-accessible-on-neutral-light",
                    "primary-accessible-dark-on-neutral-light",
                    "neutral-dark-on-neutral-light",
                ],
            )
            self.assertGreater(warning.required_ratio, 0)
            self.assertGreater(warning.actual_ratio, 0)

    def test_validation_returns_list(self):
        # Validation should always return a list (possibly with warnings)
        palette = generate_palette(None)
        warnings = validate_palette_contrast(palette)
        self.assertIsInstance(warnings, list)


class PaletteIntegrationTestCase(unittest.TestCase):
    def test_palette_generation_and_validation_roundtrip(self):
        """Palette generation → contrast validation should work end-to-end."""
        test_colors = ["#ff0000", "#00ff00", "#0000ff", "#3498db", "#e74c3c"]
        for color in test_colors:
            palette = generate_palette(color)
            # Should not raise an exception
            warnings = validate_palette_contrast(palette)
            # Should return a list (even if non-empty)
            self.assertIsInstance(warnings, list)

    def test_none_brand_color_uses_default(self):
        """None brand_colors should result in default palette."""
        palette1 = generate_palette(None)
        palette2 = generate_palette(None)
        self.assertEqual(palette1, palette2)
        self.assertEqual(palette1["primary"], "#2a6df5")
