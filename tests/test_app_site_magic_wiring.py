"""Tests for webstaffr/app.py's environment-driven Site Magic wiring.

These cover a gap that was invisible in production: the deployment
environment had SITE_MAGIC_WORKER_WEBHOOK_URL set, but nothing in the
process ever read it -- app.py built the app with site_magic_queue=None,
so every intake created a `queued` site_magic_jobs row that no worker was
ever notified about. The factories under test are the only place that
turns those env vars into a real queue/storage instance, so they get
direct coverage rather than being exercised only implicitly at import.
"""

import unittest
from unittest import mock

from webstaffr.app import (
    _site_magic_artifact_storage_from_env,
    _site_magic_control_build_dispatcher_from_env,
    _site_magic_queue_from_env,
)
from webstaffr.site_magic_adapters import (
    HTTPWebhookSiteMagicQueue,
    SupabaseArtifactStorage,
)


class TestSiteMagicQueueFromEnv(unittest.TestCase):
    def test_returns_none_when_no_env_set(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_site_magic_queue_from_env())

    def test_returns_none_when_only_url_set(self):
        """The exact production state before this wiring existed: URL set,
        secret absent. Must degrade to None (-> NullSiteMagicQueue), never
        construct a half-configured queue."""
        with mock.patch.dict(
            "os.environ",
            {"SITE_MAGIC_WORKER_WEBHOOK_URL": "https://worker.example.com/hook"},
            clear=True,
        ):
            self.assertIsNone(_site_magic_queue_from_env())

    def test_returns_none_when_only_secret_set(self):
        with mock.patch.dict(
            "os.environ", {"SITE_MAGIC_WORKER_WEBHOOK_SECRET": "s3cret"}, clear=True
        ):
            self.assertIsNone(_site_magic_queue_from_env())

    def test_builds_queue_when_both_set(self):
        with mock.patch.dict(
            "os.environ",
            {
                "SITE_MAGIC_WORKER_WEBHOOK_URL": "https://worker.example.com/hook",
                "SITE_MAGIC_WORKER_WEBHOOK_SECRET": "s3cret",
            },
            clear=True,
        ):
            queue = _site_magic_queue_from_env()
        self.assertIsInstance(queue, HTTPWebhookSiteMagicQueue)
        self.assertEqual(queue.webhook_url, "https://worker.example.com/hook")
        self.assertEqual(queue.secret, "s3cret")


class TestSiteMagicArtifactStorageFromEnv(unittest.TestCase):
    def test_returns_none_when_no_env_set(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_site_magic_artifact_storage_from_env())

    def test_returns_none_when_service_key_missing(self):
        """SUPABASE_URL alone is always present in production (customer auth
        needs it) -- storage must not be considered configured because of it."""
        with mock.patch.dict(
            "os.environ",
            {"SUPABASE_URL": "https://proj.supabase.co"},
            clear=True,
        ):
            self.assertIsNone(_site_magic_artifact_storage_from_env())

    def test_does_not_accept_publishable_key_as_service_key(self):
        """SITE_MAGIC_STORAGE_SERVICE_KEY is the service-role key and is
        deliberately a distinct var from SUPABASE_PUBLISHABLE_KEY."""
        with mock.patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://proj.supabase.co",
                "SUPABASE_PUBLISHABLE_KEY": "publishable-not-service-role",
            },
            clear=True,
        ):
            self.assertIsNone(_site_magic_artifact_storage_from_env())

    def test_builds_storage_when_both_set(self):
        with mock.patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://proj.supabase.co",
                "SITE_MAGIC_STORAGE_SERVICE_KEY": "service-role-key",
            },
            clear=True,
        ):
            storage = _site_magic_artifact_storage_from_env()
        self.assertIsInstance(storage, SupabaseArtifactStorage)
        self.assertEqual(storage.base_url, "https://proj.supabase.co")
        self.assertEqual(storage.bucket, "site-magic-builds")


class TestSiteMagicControlBuildDispatcherFromEnv(unittest.TestCase):
    def test_returns_none_when_control_webhook_is_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(_site_magic_control_build_dispatcher_from_env())

    def test_builds_control_dispatcher_from_dedicated_env(self):
        with mock.patch.dict(
            "os.environ",
            {
                "SITE_MAGIC_CONTROL_BUILD_WEBHOOK_URL": "https://engine.example.com/builds",
                "SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET": "s3cret",
            },
            clear=True,
        ):
            dispatcher = _site_magic_control_build_dispatcher_from_env()
        self.assertEqual(dispatcher.webhook_url, "https://engine.example.com/builds")
        self.assertEqual(dispatcher.secret, "s3cret")


if __name__ == "__main__":
    unittest.main()
