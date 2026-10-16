from __future__ import annotations

import unittest

from scripts.production_smoke import main, run_smoke


class TestProductionSmoke(unittest.TestCase):
    def test_read_only_checks_cover_release_and_optional_tenant(self):
        calls = []

        def fetch(url, timeout):
            calls.append((url, timeout))
            if url.endswith("/health"):
                return 200, {
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "strict-origin-when-cross-origin",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                }, b'{"status":"ok","release":"candidate123"}'
            if url.endswith("/web/contact"):
                return 200, {}, b'<html><textarea name="message"></textarea></html>'
            return 200, {}, b"<html>NetBuild.Pro</html>"

        results = run_smoke(
            "https://netbuild.example/",
            "tenant with spaces",
            expected_sha="candidate123",
            fetch=fetch,
            timeout=3,
        )

        self.assertTrue(all(result.passed for result in results), results)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(method_timeout == 3 for _, method_timeout in calls))
        self.assertTrue(all(url.startswith("https://") for url, _ in calls))
        self.assertIn("tenant%20with%20spaces", calls[-1][0])

    def test_health_requires_security_headers(self):
        def fetch(url, timeout):
            return 200, {}, b'{"status":"ok"}'

        results = run_smoke("https://netbuild.example", fetch=fetch)

        health = next(item for item in results if item.name == "health_and_security_headers")
        self.assertFalse(health.passed)

    def test_expected_release_sha_mismatch_fails(self):
        def fetch(url, timeout):
            if url.endswith("/health"):
                return 200, {
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "strict-origin-when-cross-origin",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                }, b'{"status":"ok","release":"wrong"}'
            return 200, {}, b"<html>NetBuild.Pro</html>"

        results = run_smoke(
            "https://netbuild.example",
            expected_sha="candidate123",
            fetch=fetch,
        )

        health = next(item for item in results if item.name == "health_and_security_headers")
        self.assertFalse(health.passed)

    def test_invalid_or_insecure_base_url_fails_before_network(self):
        self.assertEqual(main(["--base-url", "http://production.example"]), 2)
        self.assertEqual(main(["--base-url", "not-a-url"]), 2)
        self.assertEqual(
            main(["--base-url", "https://production.example", "--timeout", "0"]),
            2,
        )


if __name__ == "__main__":
    unittest.main()
