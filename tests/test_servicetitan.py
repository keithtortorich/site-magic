"""Tests for the ServiceTitan integration package."""
from __future__ import annotations

import os
import unittest
import urllib.error
from unittest.mock import patch

from webstaffr.integrations.servicetitan.client import (
    ServiceTitanClient,
    ServiceTitanHTTPError,
    ServiceTitanNotConfiguredError,
)
from webstaffr.integrations.servicetitan.mocks import MockServiceTitanClient
from webstaffr.integrations.servicetitan.sync import ServiceTitanSync, SyncResult

try:  # optional in minimal test envs
    from fastapi.testclient import TestClient

    HAS_FASTAPI_TESTCLIENT = True
except ModuleNotFoundError:  # pragma: no cover - fallback only
    HAS_FASTAPI_TESTCLIENT = False


class ServiceTitanClientConstructionTests(unittest.TestCase):
    def test_raises_without_credentials(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ServiceTitanNotConfiguredError):
                ServiceTitanClient()

    def test_constructs_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "SERVICETITAN_CLIENT_ID": "cid",
                "SERVICETITAN_CLIENT_SECRET": "secret",
                "SERVICETITAN_TENANT_ID": "tenant",
            },
            clear=True,
        ):
            client = ServiceTitanClient()
        self.assertEqual(client.client_id, "cid")
        self.assertEqual(client.tenant_id, "tenant")

    def test_defaults_use_constructor_args_over_env(self) -> None:
        client = ServiceTitanClient(
            client_id="a",
            client_secret="b",
            tenant_id="c",
            base_url="https://example.invalid",
        )
        self.assertEqual(client.client_id, "a")
        self.assertEqual(client.base_url, "https://example.invalid")


class ServiceTitanClientHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ServiceTitanClient(
            client_id="cid",
            client_secret="secret",
            tenant_id="tenant",
            base_url="https://example.invalid",
        )

    def test_request_sends_bearer_and_oauth_payload(self) -> None:
        captured: list[dict[str, object]] = []

        def fake_urlopen(req, timeout=20):  # type: ignore[override]
            captured.append(
                {
                    "method": req.method,
                    "headers": dict(req.headers),
                    "body": req.data,
                    "path": req.full_url.split("https://example.invalid", 1)[-1],
                }
            )
            fake = unittest.mock.Mock()
            fake.read.return_value = b'{"access_token": "tok", "data": []}'
            fake.__enter__ = unittest.mock.Mock(return_value=fake)
            fake.__exit__ = unittest.mock.Mock(return_value=False)
            return fake

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.client._request("GET", "/jobs")
        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[0]["path"], "/oauth2/token")
        self.assertIn(b"client_credentials", captured[0]["body"])
        self.assertEqual(captured[1]["path"], "/jobs")
        self.assertIn("Bearer tok", captured[1]["headers"]["Authorization"])

    def test_http_error_surfaces_as_expected(self) -> None:
        fake_body = b'{"error":"bad request"}'
        fake_http_error = unittest.mock.Mock(
            code=400,
            read=unittest.mock.Mock(return_value=fake_body),
            fp=unittest.mock.Mock(),
        )

        def fake_urlopen(req, timeout=20):  # type: ignore[override]
            raise urllib.error.HTTPError("https://example.invalid", 400, "Bad Request", {}, fake_http_error)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(ServiceTitanHTTPError):
                self.client._request("GET", "/jobs")


class MockServiceTitanClientTests(unittest.TestCase):
    def test_empty_by_default(self) -> None:
        client = MockServiceTitanClient()
        self.assertEqual(client.list_jobs(), [])

    def test_returns_seeded_records(self) -> None:
        client = MockServiceTitanClient(seed={"jobs": [{"id": 1}]})
        self.assertEqual(client.list_jobs(), [{"id": 1}])

    def test_failure_path(self) -> None:
        client = MockServiceTitanClient(fail="jobs")
        with self.assertRaises(ServiceTitanHTTPError):
            client.list_jobs()


class ServiceTitanSyncTests(unittest.TestCase):
    def test_happy_path(self) -> None:
        client = MockServiceTitanClient(
            seed={
                "jobs": [{"id": 1}],
                "customers": [{"id": 2}],
            }
        )
        sync = ServiceTitanSync(client, limit=50)
        results = sync.run()
        self.assertEqual(len(results), 9)
        jobs = next(result for result in results if result.resource == "jobs")
        self.assertEqual(jobs.fetched, 1)
        self.assertFalse(jobs.failed)
        self.assertEqual(jobs.data, [{"id": 1}])

    def test_isolated_failure(self) -> None:
        client = MockServiceTitanClient(seed={"jobs": [{"id": 1}]}, fail="appointments")
        sync = ServiceTitanSync(client)
        results = sync.run()
        appointments = next(result for result in results if result.resource == "appointments")
        self.assertTrue(appointments.failed)
        self.assertEqual(appointments.fetched, 0)
        jobs = next(result for result in results if result.resource == "jobs")
        self.assertFalse(jobs.failed)


def _make_router_app(enabled=True):
    """Build a router app with ServiceTitan env toggled on/off.

    Imported lazily so test_servicetitan can keep working in minimal
    environments that lack `fastapi` installed.
    """
    from webstaffr.workers.angel.ghl import NullGHLClient
    from webstaffr.app import create_app
    from webstaffr.workers.angel.voice import NullVoiceBackend

    env = {
        "SERVICETITAN_ENABLED": "true" if enabled else "false",
        "SERVICETITAN_CLIENT_ID": "cid",
        "SERVICETITAN_CLIENT_SECRET": "secret",
        "SERVICETITAN_TENANT_ID": "tenant",
    }
    with patch.dict(os.environ, env, clear=True):
        return create_app(
            db_path=":memory:",
            voice_backend=NullVoiceBackend(),
            ghl_client=NullGHLClient(),
        )


class ServiceTitanPollEndpointTests(unittest.TestCase):
    """Tests for the gated POST /integrations/servicetitan/poll endpoint."""

    def test_returns_503_when_not_configured(self):
        if not HAS_FASTAPI_TESTCLIENT:
            self.skipTest("fastapi not installed in this environment")
        # Deliberately omit SERVICETITAN_CLIENT_ID/SECRET/TENANT_ID so
        # ServiceTitanClient() raises ServiceTitanNotConfiguredError inside
        # the handler, which should surface as a 503 -- this must not reach
        # ServiceTitanSync.run() at all, so no fake_sync/patch is needed here.
        env = {"SERVICETITAN_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=True):
            from webstaffr.workers.angel.ghl import NullGHLClient
            from webstaffr.app import create_app
            from webstaffr.workers.angel.voice import NullVoiceBackend

            app = create_app(
                db_path=":memory:",
                voice_backend=NullVoiceBackend(),
                ghl_client=NullGHLClient(),
            )

            with TestClient(app) as client:
                resp = client.post("/integrations/servicetitan/poll", json={})
                self.assertEqual(resp.status_code, 503)

    def test_returns_404_when_disabled(self):
        if not HAS_FASTAPI_TESTCLIENT:
            self.skipTest("fastapi not installed in this environment")
        app = _make_router_app(enabled=False)
        with TestClient(app) as client:
            resp = client.post("/integrations/servicetitan/poll", json={})
            self.assertEqual(resp.status_code, 404)

    def test_returns_structured_results(self):
        if not HAS_FASTAPI_TESTCLIENT:
            self.skipTest("fastapi not installed in this environment")
        # ServiceTitanSync.run() always returns list[SyncResult] (a
        # dataclass, see sync.py) -- the handler accesses .resource/.fetched/
        # etc. as attributes, not dict keys, so the fake double must return
        # real SyncResult instances to match that contract.
        expected = [
            SyncResult(resource="jobs", fetched=2, failed=False, error=None),
            SyncResult(resource="appointments", fetched=0, failed=True, error="boom"),
        ]
        fake_sync = unittest.mock.Mock()
        fake_sync.run.return_value = expected

        env = {
            "SERVICETITAN_ENABLED": "true",
            "SERVICETITAN_CLIENT_ID": "cid",
            "SERVICETITAN_CLIENT_SECRET": "secret",
            "SERVICETITAN_TENANT_ID": "tenant",
        }
        with patch.dict(os.environ, env, clear=True), patch(
            "webstaffr.integrations.servicetitan.ServiceTitanSync", return_value=fake_sync
        ):
            from webstaffr.workers.angel.ghl import NullGHLClient
            from webstaffr.app import create_app
            from webstaffr.workers.angel.voice import NullVoiceBackend

            app = create_app(
                db_path=":memory:",
                voice_backend=NullVoiceBackend(),
                ghl_client=NullGHLClient(),
            )

            with TestClient(app) as client:
                resp = client.post("/integrations/servicetitan/poll", json={})
                self.assertEqual(resp.status_code, 200)
                body = resp.json()
                self.assertIn("results", body)
                self.assertEqual(len(body["results"]), 2)
                self.assertEqual(body["results"][0]["resource"], "jobs")
                self.assertEqual(body["results"][0]["fetched"], 2)
                self.assertFalse(body["results"][0]["failed"])
                self.assertTrue(body["results"][1]["failed"])
                self.assertEqual(body["results"][1]["error"], "boom")


if __name__ == "__main__":
    unittest.main()
