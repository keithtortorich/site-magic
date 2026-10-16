"""Tests for webstaffr/site_magic_adapters.py: the real (non-Null)
SiteMagicQueue/ArtifactStorage/SiteCrawler implementations. All network
calls go through httpx.MockTransport / a fake DNS resolver -- no live
credentials exist for these yet (see
docs/STANDUP_2026-08-09_IMPECCABLE_PHASE_1.md), so these are unit tests
against the request-building/response-parsing logic only."""

import unittest

import httpx

from webstaffr.site_magic import SiteMagicNotConfiguredError
from webstaffr.site_magic_adapters import (
    ArtifactStorageSiteMagicPublisher,
    HTTPWebhookSiteMagicBuildDispatcher,
    HTTPWebhookSiteMagicQueue,
    HttpxSiteCrawler,
    SupabaseArtifactStorage,
)


def _resolver(*addresses):
    def resolve(host, port):
        return [(2, 1, 6, "", (addr, port)) for addr in addresses]

    return resolve


class TestHTTPWebhookSiteMagicQueue(unittest.TestCase):
    def test_missing_config_raises_not_configured(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            HTTPWebhookSiteMagicQueue(webhook_url=None, secret=None)

    def test_missing_secret_only_still_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            HTTPWebhookSiteMagicQueue(webhook_url="https://worker.example.com/hook", secret=None)

    def test_enqueue_posts_job_and_tenant_with_secret_header(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["json"] = request.content
            seen["secret"] = request.headers.get("x-site-magic-secret")
            return httpx.Response(200)

        queue = HTTPWebhookSiteMagicQueue(
            webhook_url="https://worker.example.com/hook",
            secret="shh",
            transport=httpx.MockTransport(handler),
        )
        queue.enqueue(job_id="job_1", tenant_id="acme_hvac")

        self.assertEqual(seen["url"], "https://worker.example.com/hook")
        self.assertEqual(seen["secret"], "shh")
        self.assertIn(b"job_1", seen["json"])
        self.assertIn(b"acme_hvac", seen["json"])

    def test_enqueue_raises_not_configured_on_http_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        queue = HTTPWebhookSiteMagicQueue(
            webhook_url="https://worker.example.com/hook",
            secret="shh",
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            queue.enqueue(job_id="job_1", tenant_id="acme_hvac")


class TestHTTPWebhookSiteMagicBuildDispatcher(unittest.TestCase):
    def test_missing_config_raises_not_configured(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            HTTPWebhookSiteMagicBuildDispatcher(webhook_url=None, secret=None)

    def test_dispatch_posts_control_plane_build_envelope(self):
        from webstaffr.site_magic_control import SiteMagicBuildRequest

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["json"] = request.content
            seen["secret"] = request.headers.get("x-site-magic-secret")
            return httpx.Response(202)

        dispatcher = HTTPWebhookSiteMagicBuildDispatcher(
            webhook_url="https://engine.example.com/builds",
            secret="shh",
            transport=httpx.MockTransport(handler),
        )
        dispatcher.dispatch(
            build=SiteMagicBuildRequest(
                build_id="build_1", tenant_id="tenant_1", approval_id="approval_1",
                plan_id="plan_1", plan_version=2, plan_hash="sha256:p",
                fact_snapshot_hash="sha256:f", status="requested", requested_by="user_1",
                created_at="now", correlation_id="corr_1", revision_id="rev_1",
                revision_scope=("home.hero",),
            )
        )
        self.assertEqual(seen["secret"], "shh")
        self.assertIn(b'"build_id":"build_1"', seen["json"])
        self.assertIn(b'"correlation_id":"corr_1"', seen["json"])
        self.assertIn(b'"revision_id":"rev_1"', seen["json"])


class TestSupabaseArtifactStorage(unittest.TestCase):
    def test_missing_config_raises_not_configured(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            SupabaseArtifactStorage(base_url=None, service_key=None)

    def test_signed_preview_url_uses_one_hour_ttl(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"signedURL": "/object/sign/site-magic-builds/x?token=abc"})

        storage = SupabaseArtifactStorage(
            base_url="https://project.supabase.co",
            service_key="service-key",
            bucket="site-magic-builds",
            transport=httpx.MockTransport(handler),
        )
        url = storage.signed_preview_url(tenant_id="acme_hvac", locator="acme_hvac/job_1/build_1.tar")

        self.assertEqual(
            seen["url"],
            "https://project.supabase.co/storage/v1/object/sign/site-magic-builds/acme_hvac/job_1/build_1.tar",
        )
        self.assertIn(b'"expiresIn":3600', seen["body"])
        self.assertEqual(seen["auth"], "Bearer service-key")
        self.assertEqual(url, "https://project.supabase.co/storage/v1/object/sign/site-magic-builds/x?token=abc")

    def test_publish_returns_public_bucket_url(self):
        # ADR-029: Phase 1 MVP returns public bucket URL (no signed URL)
        # Bucket is configured to be publicly readable via Supabase bucket policies
        storage = SupabaseArtifactStorage(
            base_url="https://project.supabase.co",
            service_key="service-key",
            transport=httpx.MockTransport(lambda r: httpx.Response(200)),
        )
        url = storage.publish(tenant_id="acme_hvac", locator="acme_hvac/job_1/build_1.tar", build_id="build_1")

        self.assertEqual(
            url,
            "https://project.supabase.co/storage/v1/object/public/site-magic-builds/acme_hvac/job_1/build_1.tar"
        )

    def test_sign_call_failure_raises_not_configured(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403)

        storage = SupabaseArtifactStorage(
            base_url="https://project.supabase.co",
            service_key="service-key",
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            storage.signed_preview_url(tenant_id="acme_hvac", locator="x")

    def test_malformed_sign_response_raises_not_configured(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": "shape"})

        storage = SupabaseArtifactStorage(
            base_url="https://project.supabase.co",
            service_key="service-key",
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            storage.signed_preview_url(tenant_id="acme_hvac", locator="x")


class TestArtifactStorageSiteMagicPublisher(unittest.TestCase):
    def test_adapts_checkpoint_release_to_existing_storage_port(self):
        class Storage:
            def __init__(self):
                self.calls = []

            def publish(self, **kwargs):
                self.calls.append(kwargs)
                return "https://public.example/checkpoint.tar"

        storage = Storage()
        publisher = ArtifactStorageSiteMagicPublisher(storage)
        result = publisher.publish(
            tenant_id="acme_hvac", checkpoint_id="checkpoint_1",
            artifact_locator="acme_hvac/build_1/site.tar", artifact_manifest={"locator": "x"},
        )
        self.assertEqual(result, "https://public.example/checkpoint.tar")
        self.assertEqual(storage.calls[0]["build_id"], "checkpoint_1")

    def test_rejects_checkpoint_without_locator(self):
        publisher = ArtifactStorageSiteMagicPublisher(object())
        with self.assertRaises(SiteMagicNotConfiguredError):
            publisher.publish(
                tenant_id="acme_hvac", checkpoint_id="checkpoint_1",
                artifact_locator="", artifact_manifest={},
            )


class TestHttpxSiteCrawler(unittest.TestCase):
    def test_snapshot_extracts_visible_text_and_strips_scripts(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                html="<html><body><h1>Desert Pro Plumbing</h1><script>evil()</script></body></html>",
            )

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        result = crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")

        self.assertEqual(result["status_code"], 200)
        self.assertIn("Desert Pro Plumbing", result["text"])
        self.assertNotIn("evil", result["text"])

    def test_snapshot_rejects_url_resolving_to_private_address(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, html="<html></html>")

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("10.0.0.5"),
        )
        with self.assertRaises(Exception):
            crawler.snapshot(url="https://internal.example.com/", tenant_id="acme_hvac")

    def test_snapshot_follows_same_origin_redirect(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if str(request.url) == "https://example.com/":
                return httpx.Response(301, headers={"location": "https://example.com/home"})
            return httpx.Response(200, html="<html><body>Home page</body></html>")

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        result = crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")

        self.assertEqual(len(calls), 2)
        self.assertIn("Home page", result["text"])

    def test_snapshot_rejects_off_origin_redirect(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == "https://example.com/":
                return httpx.Response(301, headers={"location": "https://evil.example.org/"})
            return httpx.Response(200, html="<html></html>")

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")

    def test_snapshot_gives_up_after_max_redirects(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(301, headers={"location": "https://example.com/next"})

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")

    def test_snapshot_raises_on_http_error_status(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, html="server error")

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        with self.assertRaises(SiteMagicNotConfiguredError):
            crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")

    def test_snapshot_truncates_oversized_pages(self):
        huge_html = "<html><body>" + ("a" * 6_000_000) + "</body></html>"

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, html=huge_html)

        crawler = HttpxSiteCrawler(
            transport=httpx.MockTransport(handler),
            resolver=_resolver("93.184.216.34"),
        )
        result = crawler.snapshot(url="https://example.com/", tenant_id="acme_hvac")
        self.assertLessEqual(len(result["text"]), 200_000)


if __name__ == "__main__":
    unittest.main()
