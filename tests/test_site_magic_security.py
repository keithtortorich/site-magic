"""Tests for webstaffr/site_magic_security.py: the SSRF boundary Site Magic's
'url' source crosses before any crawl happens, plus the hostile-HTML text
extractor crawled pages get funneled through."""

import unittest

from webstaffr.site_magic_security import (
    UnsafeSiteSourceError,
    extract_hostile_source_text,
    normalize_public_url,
    same_origin,
)


def _resolver(*addresses):
    """Build a fake getaddrinfo(host, port) that returns the given IPs."""

    def resolve(host, port):
        return [(2, 1, 6, "", (addr, port)) for addr in addresses]

    return resolve


def _resolver_raises(host, port):
    raise OSError("name or service not known")


class TestSchemeAndHostValidation(unittest.TestCase):
    def test_rejects_ftp_scheme(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("ftp://example.com/", resolver=_resolver("93.184.216.34"))

    def test_rejects_file_scheme(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("file:///etc/passwd", resolver=_resolver("93.184.216.34"))

    def test_rejects_javascript_scheme(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("javascript:alert(1)", resolver=_resolver("93.184.216.34"))

    def test_rejects_missing_hostname(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https:///path", resolver=_resolver("93.184.216.34"))

    def test_rejects_userinfo_in_url(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://user:pass@example.com/", resolver=_resolver("93.184.216.34"))

    def test_rejects_oversized_url(self):
        huge = "https://example.com/" + ("a" * 2048)
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url(huge, resolver=_resolver("93.184.216.34"))

    def test_rejects_invalid_idna_host(self):
        oversized_label = "a" * 64  # IDNA labels cap at 63 octets
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url(
                f"https://{oversized_label}.com/", resolver=_resolver("93.184.216.34")
            )


class TestPortValidation(unittest.TestCase):
    def test_accepts_default_https_port(self):
        result = normalize_public_url("https://example.com/", resolver=_resolver("93.184.216.34"))
        self.assertEqual(result, "https://example.com/")

    def test_accepts_default_http_port(self):
        result = normalize_public_url("http://example.com/", resolver=_resolver("93.184.216.34"))
        self.assertEqual(result, "http://example.com/")

    def test_rejects_nonstandard_port(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://example.com:8443/", resolver=_resolver("93.184.216.34"))

    def test_rejects_port_zero(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://example.com:0/", resolver=_resolver("93.184.216.34"))

    def test_explicit_default_port_is_stripped_from_canonical_output(self):
        result = normalize_public_url("https://example.com:443/path", resolver=_resolver("93.184.216.34"))
        self.assertEqual(result, "https://example.com/path")


class TestDNSResolutionAndPrivateAddressBlocking(unittest.TestCase):
    def test_dns_failure_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://nonexistent.invalid/", resolver=_resolver_raises)

    def test_empty_resolution_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://example.com/", resolver=lambda h, p: [])

    def test_loopback_ipv4_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("127.0.0.1"))

    def test_loopback_ipv6_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("::1"))

    def test_private_10_block_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("10.0.0.5"))

    def test_private_172_16_block_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("172.16.5.5"))

    def test_private_192_168_block_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("192.168.1.1"))

    def test_link_local_ipv4_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("169.254.169.254"))

    def test_cloud_metadata_address_rejected(self):
        # 169.254.169.254 is the AWS/GCP/Azure instance-metadata endpoint --
        # the single highest-value SSRF target. Covered by link-local above,
        # asserted explicitly so a refactor can't silently drop the case.
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://metadata.internal/", resolver=_resolver("169.254.169.254"))

    def test_ipv6_unique_local_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("fc00::1"))

    def test_unspecified_address_rejected(self):
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url("https://internal.example.com/", resolver=_resolver("0.0.0.0"))

    def test_multi_answer_resolution_is_rejected_if_any_answer_is_private(self):
        """DNS rebinding / multi-A-record bypass: one public answer plus one
        private answer must still fail closed, not pass on the first hit."""
        with self.assertRaises(UnsafeSiteSourceError):
            normalize_public_url(
                "https://mixed.example.com/", resolver=_resolver("93.184.216.34", "10.0.0.1")
            )

    def test_fully_public_resolution_is_accepted(self):
        result = normalize_public_url("https://example.com/", resolver=_resolver("93.184.216.34"))
        self.assertEqual(result, "https://example.com/")


class TestSameOrigin(unittest.TestCase):
    def test_same_scheme_host_port_is_same_origin(self):
        self.assertTrue(same_origin("https://example.com/a", "https://example.com/b"))

    def test_different_scheme_is_not_same_origin(self):
        self.assertFalse(same_origin("https://example.com/a", "http://example.com/a"))

    def test_different_host_is_not_same_origin(self):
        self.assertFalse(same_origin("https://example.com/a", "https://evil.example.com/a"))

    def test_explicit_default_port_matches_implicit_default_port(self):
        self.assertTrue(same_origin("https://example.com/a", "https://example.com:443/b"))

    def test_different_explicit_port_is_not_same_origin(self):
        self.assertFalse(same_origin("https://example.com:8443/a", "https://example.com/a"))


class TestExtractHostileSourceText(unittest.TestCase):
    def test_strips_script_tags(self):
        html = "<html><body><p>Hello</p><script>alert(document.cookie)</script></body></html>"
        text = extract_hostile_source_text(html)
        self.assertIn("Hello", text)
        self.assertNotIn("alert", text)

    def test_strips_style_tags(self):
        html = "<html><body><p>Hello</p><style>body{color:red}</style></body></html>"
        text = extract_hostile_source_text(html)
        self.assertNotIn("color:red", text)

    def test_strips_iframe_content(self):
        html = "<div>Real content</div><iframe src='https://evil.example.com'>trapped</iframe>"
        text = extract_hostile_source_text(html)
        self.assertIn("Real content", text)
        self.assertNotIn("trapped", text)

    def test_visible_text_is_preserved_across_tags(self):
        html = "<h1>Desert Pro Plumbing</h1><p>We fix leaks fast.</p>"
        text = extract_hostile_source_text(html)
        self.assertIn("Desert Pro Plumbing", text)
        self.assertIn("We fix leaks fast.", text)

    def test_output_is_truncated_to_max_chars(self):
        html = "<p>" + ("x" * 500_000) + "</p>"
        text = extract_hostile_source_text(html, max_chars=1000)
        self.assertLessEqual(len(text), 1000)

    def test_oversized_input_html_does_not_hang_or_crash(self):
        html = "<p>" + ("a" * 2_000_000) + "</p>"
        text = extract_hostile_source_text(html)
        self.assertIsInstance(text, str)


if __name__ == "__main__":
    unittest.main()
