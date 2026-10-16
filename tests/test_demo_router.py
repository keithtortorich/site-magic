"""HTTP-layer tests for webstaffr/demo_router.py + demo_job_manager.py:
enqueue-on-first-access, idempotency, building/ready/failed states,
auto-publish, and legacy URL redirects. Same temp-file-db + TestClient
pattern as test_site_magic_api.py."""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.db import connect
from webstaffr.demo_sites import DEMO_FIXTURES
from webstaffr.site_magic import SiteMagicRepository


class FakeQueue:
    def __init__(self):
        self.enqueued = []

    def enqueue(self, *, job_id, tenant_id):
        self.enqueued.append((job_id, tenant_id))


class FakeArtifactStorage:
    def __init__(self):
        self.published = []

    def signed_preview_url(self, *, tenant_id, locator):
        return f"https://preview.example.com/{tenant_id}/{locator}"

    def publish(self, *, tenant_id, locator, build_id):
        self.published.append((tenant_id, locator, build_id))
        return f"https://{tenant_id}.demo.netbuild.pro"


def _advance_to_final_review(conn, tenant_id, job_id):
    repo = SiteMagicRepository(conn)
    for target in ("ingesting", "directing", "building", "evaluating", "final_review"):
        repo.transition(tenant_id=tenant_id, job_id=job_id, target=target)
    conn.commit()


class DemoRouterTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.queue = FakeQueue()
        self.storage = FakeArtifactStorage()
        app = create_app(
            db_path=self.db_path,
            site_magic_queue=self.queue,
            site_magic_artifact_storage=self.storage,
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def test_gallery_lists_every_demo(self):
        response = self.client.get("/demos")
        self.assertEqual(response.status_code, 200)
        for fixture in DEMO_FIXTURES.values():
            self.assertIn(fixture.verified_facts["biz_name"], response.text)

    def test_unknown_slug_is_404(self):
        response = self.client.get("/demos/not-a-real-trade", follow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_first_access_enqueues_and_shows_building(self):
        response = self.client.get("/demos/hvac", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Building", response.text)
        self.assertEqual(len(self.queue.enqueued), 1)
        _, tenant_id = self.queue.enqueued[0]
        self.assertEqual(tenant_id, DEMO_FIXTURES["hvac"].reserved_tenant_id)

    def test_second_access_does_not_enqueue_a_second_job(self):
        self.client.get("/demos/hvac", follow_redirects=False)
        self.client.get("/demos/hvac", follow_redirects=False)
        self.assertEqual(len(self.queue.enqueued), 1)

    def test_ready_job_auto_publishes_and_redirects(self):
        self.client.get("/demos/hvac", follow_redirects=False)
        job_id, tenant_id = self.queue.enqueued[0]
        with connect(self.db_path) as conn:
            _advance_to_final_review(conn, tenant_id, job_id)
            repo = SiteMagicRepository(conn)
            repo.seal_build_and_advance(
                tenant_id=tenant_id, job_id=job_id, build_id="build_1",
                artifact_manifest={"jobId": job_id}, preview_locator=f"{tenant_id}/build_1.tar",
            )
            conn.commit()

        response = self.client.get("/demos/hvac", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], f"https://{tenant_id}.demo.netbuild.pro")
        self.assertEqual(len(self.storage.published), 1)

    def test_already_published_job_redirects_without_republishing(self):
        self.client.get("/demos/hvac", follow_redirects=False)
        job_id, tenant_id = self.queue.enqueued[0]
        with connect(self.db_path) as conn:
            _advance_to_final_review(conn, tenant_id, job_id)
            repo = SiteMagicRepository(conn)
            repo.seal_build_and_advance(
                tenant_id=tenant_id, job_id=job_id, build_id="build_1",
                artifact_manifest={}, preview_locator=f"{tenant_id}/build_1.tar",
            )
            conn.commit()

        first = self.client.get("/demos/hvac", follow_redirects=False)
        second = self.client.get("/demos/hvac", follow_redirects=False)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(first.headers["location"], second.headers["location"])
        # publish() called once (during the first request's auto-publish);
        # the second request finds status already "published" and reuses
        # the stored published_url rather than publishing again.
        self.assertEqual(len(self.storage.published), 1)

    def test_failed_job_shows_fallback_not_500(self):
        self.client.get("/demos/hvac", follow_redirects=False)
        job_id, tenant_id = self.queue.enqueued[0]
        with connect(self.db_path) as conn:
            SiteMagicRepository(conn).transition(tenant_id=tenant_id, job_id=job_id, target="failed")
            conn.commit()

        response = self.client.get("/demos/hvac", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("unavailable", response.text.lower())

    def test_legacy_slug_redirects_to_canonical(self):
        response = self.client.get("/demos/arbor", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/demos/tree-service")

    def test_legacy_html_file_url_redirects(self):
        response = self.client.get("/demo-sites/hvac.html", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/demos/hvac")

    def test_legacy_retired_slug_file_url_redirects_to_canonical(self):
        response = self.client.get("/demo-sites/roof.html", follow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers["location"], "/demos/roofing")


if __name__ == "__main__":
    unittest.main()
