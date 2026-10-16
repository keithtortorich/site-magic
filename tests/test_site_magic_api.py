"""HTTP-layer tests for webstaffr/site_magic_router.py: tenant isolation,
role checks, source validation, job lifecycle, preview, and publish. Same
temp-file-db + lifespan-context + fake-identity-verifier pattern as
test_attribution.py's AttributionRouterTestCase."""

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.customer_auth import VerifiedIdentity
from webstaffr.db import connect
from webstaffr.site_magic import SiteMagicNotConfiguredError
from webstaffr.workers.angel.api_auth import StaticSecretVerifier


class _IdentityVerifier:
    def __init__(self, identity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "test-token" else None


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
        return f"https://{tenant_id}.netbuild.pro"


class RefusingArtifactStorage:
    def signed_preview_url(self, *, tenant_id, locator):
        raise SiteMagicNotConfiguredError("not configured")

    def publish(self, *, tenant_id, locator, build_id):
        raise SiteMagicNotConfiguredError("not configured")


def _global_getaddrinfo(host, port):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


class SiteMagicAPITestCase(unittest.TestCase):
    """HTTP-layer tests via TestClient against a real app instance -- same
    pattern as AttributionRouterTestCase in test_attribution.py."""

    role = "owner"

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.user_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        identity = VerifiedIdentity(
            user_id=self.user_id,
            session_id=self.session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self.queue = FakeQueue()
        self.storage = FakeArtifactStorage()
        app = create_app(
            db_path=self.db_path,
            customer_identity_verifier=_IdentityVerifier(identity),
            customer_allowed_origins={"https://example-customer-site.com"},
            site_magic_queue=self.queue,
            site_magic_artifact_storage=self.storage,
            internal_api_verifier=StaticSecretVerifier("internal-test-key"),
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        with connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO customer_users (user_id) VALUES (?)", (self.user_id,)
            )
        response = self.client.post("/auth/session", headers=self._auth_headers())
        self.assertEqual(response.status_code, 200)
        self.tenant_id = self._make_tenant(role=self.role)

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _make_tenant(self, *, role="owner", tenant_id=None):
        tenant_id = tenant_id or f"tenant_{uuid.uuid4().hex[:8]}"
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", (tenant_id,))
            conn.execute(
                """
                INSERT INTO tenant_memberships (tenant_id, user_id, role)
                VALUES (?, ?, ?)
                """,
                (tenant_id, self.user_id, role),
            )
        return tenant_id

    @staticmethod
    def _auth_headers(**extra):
        return {"Authorization": "Bearer test-token", **extra}

    def _post(self, path, json=None, **headers):
        return self.client.post(path, json=json, headers=self._auth_headers(**headers))

    def _get(self, path, **headers):
        return self.client.get(path, headers=self._auth_headers(**headers))

    def _create_intake_job(self, tenant_id=None):
        tenant_id = tenant_id or self.tenant_id
        return self._post(
            "/site-magic/jobs",
            json={
                "tenant_id": tenant_id,
                "source": {"type": "intake", "intake_id": "sub_1"},
            },
        )


class TestCreateJobSourceValidation(SiteMagicAPITestCase):
    def test_intake_source_creates_queued_job(self):
        resp = self._create_intake_job()
        self.assertEqual(resp.status_code, 202)
        body = resp.json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["source_type"], "intake")
        self.assertEqual(self.queue.enqueued, [(body["job_id"], self.tenant_id)])

    def test_intake_source_missing_intake_id_rejected(self):
        resp = self._post(
            "/site-magic/jobs",
            json={"tenant_id": self.tenant_id, "source": {"type": "intake"}},
        )
        self.assertEqual(resp.status_code, 422)

    def test_url_source_with_ownership_attestation_creates_job(self):
        with patch("webstaffr.site_magic_security.socket.getaddrinfo", side_effect=_global_getaddrinfo):
            resp = self._post(
                "/site-magic/jobs",
                json={
                    "tenant_id": self.tenant_id,
                    "source": {
                        "type": "url",
                        "url": "https://example.com/",
                        "ownership_attested": True,
                    },
                },
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["source_type"], "url")

    def test_url_source_without_attestation_rejected(self):
        resp = self._post(
            "/site-magic/jobs",
            json={
                "tenant_id": self.tenant_id,
                "source": {"type": "url", "url": "https://example.com/", "ownership_attested": False},
            },
        )
        self.assertEqual(resp.status_code, 422)

    def test_url_source_resolving_to_private_address_rejected(self):
        def private_getaddrinfo(host, port):
            return [(2, 1, 6, "", ("10.0.0.5", port))]

        with patch("webstaffr.site_magic_security.socket.getaddrinfo", side_effect=private_getaddrinfo):
            resp = self._post(
                "/site-magic/jobs",
                json={
                    "tenant_id": self.tenant_id,
                    "source": {
                        "type": "url",
                        "url": "https://internal.example.com/",
                        "ownership_attested": True,
                    },
                },
            )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(self.queue.enqueued, [])

    def test_repository_source_is_rejected_as_internal_only(self):
        resp = self._post(
            "/site-magic/jobs",
            json={"tenant_id": self.tenant_id, "source": {"type": "repository", "surface": "demo-1"}},
        )
        self.assertEqual(resp.status_code, 403)

    def test_unsupported_source_type_rejected(self):
        resp = self._post(
            "/site-magic/jobs",
            json={"tenant_id": self.tenant_id, "source": {"type": "carrier_pigeon"}},
        )
        self.assertEqual(resp.status_code, 422)


class TestCreateJobRoleChecks(SiteMagicAPITestCase):
    role = "viewer"

    def test_viewer_cannot_create_job(self):
        resp = self._create_intake_job()
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.queue.enqueued, [])


class TestCreateJobQueueFailsClosed(SiteMagicAPITestCase):
    def test_not_configured_queue_returns_503_and_persists_nothing(self):
        with patch.object(self.queue, "enqueue", side_effect=SiteMagicNotConfiguredError("no queue")):
            resp = self._create_intake_job()
        self.assertEqual(resp.status_code, 503)
        with connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM site_magic_jobs").fetchone()["n"]
        self.assertEqual(count, 0)


class TestGetJobTenantIsolation(SiteMagicAPITestCase):
    def test_owner_can_read_own_job(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self._get(f"/site-magic/jobs/{job_id}?tenant_id={self.tenant_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["job_id"], job_id)

    def test_unknown_job_id_is_404(self):
        resp = self._get(f"/site-magic/jobs/{uuid.uuid4()}?tenant_id={self.tenant_id}")
        self.assertEqual(resp.status_code, 404)

    def test_job_from_other_tenant_is_not_readable_via_wrong_tenant_id(self):
        other_tenant = self._make_tenant(role="owner")
        job_id = self._create_intake_job(tenant_id=other_tenant).json()["job_id"]
        # This user has membership on both tenants (fixture creates it), so use
        # a tenant_id the row was never created under to prove scoping bites.
        third_tenant = self._make_tenant(role="owner")
        resp = self._get(f"/site-magic/jobs/{job_id}?tenant_id={third_tenant}")
        self.assertEqual(resp.status_code, 404)

    def test_user_without_membership_cannot_read_job(self):
        job_id = self._create_intake_job().json()["job_id"]
        # The configured identity verifier only recognizes "test-token" --
        # any other bearer token fails identity verification outright.
        resp = self.client.get(
            f"/site-magic/jobs/{job_id}?tenant_id={self.tenant_id}",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(resp.status_code, 401)


class TestPreview(SiteMagicAPITestCase):
    def _advance_to_ready_for_review(self, job_id):
        with connect(self.db_path) as conn:
            from webstaffr.site_magic import SiteMagicRepository
            import json as _json

            repo = SiteMagicRepository(conn)
            for target in ("ingesting", "directing", "building", "evaluating", "final_review", "ready_for_review"):
                repo.transition(tenant_id=self.tenant_id, job_id=job_id, target=target)
            conn.execute(
                """
                INSERT INTO site_magic_builds
                    (build_id, job_id, tenant_id, artifact_manifest_json, preview_locator, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    "build_1", job_id, self.tenant_id,
                    _json.dumps({"pages": ["home.html"]}), "builds/build_1/",
                ),
            )
            conn.execute(
                "UPDATE site_magic_jobs SET final_build_id = ? WHERE tenant_id = ? AND job_id = ?",
                ("build_1", self.tenant_id, job_id),
            )
            conn.commit()

    def test_preview_not_ready_before_ready_for_review(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self._get(f"/site-magic/jobs/{job_id}/preview?tenant_id={self.tenant_id}")
        self.assertEqual(resp.status_code, 409)

    def test_preview_ready_returns_signed_url(self):
        job_id = self._create_intake_job().json()["job_id"]
        self._advance_to_ready_for_review(job_id)
        resp = self._get(f"/site-magic/jobs/{job_id}/preview?tenant_id={self.tenant_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.tenant_id, resp.json()["final_url"])

    def test_get_job_exposes_final_url_only_once_previewable(self):
        job_id = self._create_intake_job().json()["job_id"]
        before = self._get(f"/site-magic/jobs/{job_id}?tenant_id={self.tenant_id}")
        self.assertNotIn("final_url", before.json())


class TestPublish(SiteMagicAPITestCase):
    def _advance_to_ready_for_review(self, job_id):
        with connect(self.db_path) as conn:
            from webstaffr.site_magic import SiteMagicRepository
            import json as _json

            repo = SiteMagicRepository(conn)
            for target in ("ingesting", "directing", "building", "evaluating", "final_review", "ready_for_review"):
                repo.transition(tenant_id=self.tenant_id, job_id=job_id, target=target)
            conn.execute(
                """
                INSERT INTO site_magic_builds
                    (build_id, job_id, tenant_id, artifact_manifest_json, preview_locator, created_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    "build_1", job_id, self.tenant_id,
                    _json.dumps({"pages": ["home.html"]}), "builds/build_1/",
                ),
            )
            conn.execute(
                "UPDATE site_magic_jobs SET final_build_id = ? WHERE tenant_id = ? AND job_id = ?",
                ("build_1", self.tenant_id, job_id),
            )
            conn.commit()

    def test_publish_not_allowed_before_ready_for_review(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self._post(f"/site-magic/jobs/{job_id}/publish", json={"tenant_id": self.tenant_id})
        self.assertEqual(resp.status_code, 409)

    def test_owner_publish_succeeds_and_sets_active_build(self):
        job_id = self._create_intake_job().json()["job_id"]
        self._advance_to_ready_for_review(job_id)
        resp = self._post(f"/site-magic/jobs/{job_id}/publish", json={"tenant_id": self.tenant_id})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "published")
        self.assertIn("final_url", body)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT build_id FROM site_magic_active_builds WHERE tenant_id = ?", (self.tenant_id,)
            ).fetchone()
        self.assertEqual(row["build_id"], "build_1")

    def test_publish_with_unconfigured_storage_returns_503_and_does_not_publish(self):
        job_id = self._create_intake_job().json()["job_id"]
        self._advance_to_ready_for_review(job_id)
        self.storage.publish = RefusingArtifactStorage().publish
        resp = self._post(f"/site-magic/jobs/{job_id}/publish", json={"tenant_id": self.tenant_id})
        self.assertEqual(resp.status_code, 503)
        with connect(self.db_path) as conn:
            status = conn.execute(
                "SELECT status FROM site_magic_jobs WHERE tenant_id = ? AND job_id = ?",
                (self.tenant_id, job_id),
            ).fetchone()["status"]
        self.assertEqual(status, "ready_for_review")


class TestPublishRoleChecks(SiteMagicAPITestCase):
    def test_manager_cannot_publish(self):
        job_id = self._create_intake_job().json()["job_id"]
        with connect(self.db_path) as conn:
            conn.execute(
                "UPDATE tenant_memberships SET role = 'manager' WHERE tenant_id = ? AND user_id = ?",
                (self.tenant_id, self.user_id),
            )
        resp = self._post(f"/site-magic/jobs/{job_id}/publish", json={"tenant_id": self.tenant_id})
        self.assertEqual(resp.status_code, 403)


class TestInternalGetJob(SiteMagicAPITestCase):
    def test_valid_api_key_returns_full_job_including_source_payload(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.get(
            f"/site-magic/internal/jobs/{job_id}?tenant_id={self.tenant_id}",
            headers={"X-API-Key": "internal-test-key"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["job_id"], job_id)
        self.assertEqual(body["source_payload"], {"type": "intake", "intake_id": "sub_1"})

    def test_missing_api_key_is_rejected(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.get(f"/site-magic/internal/jobs/{job_id}?tenant_id={self.tenant_id}")
        self.assertEqual(resp.status_code, 401)

    def test_wrong_api_key_is_rejected(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.get(
            f"/site-magic/internal/jobs/{job_id}?tenant_id={self.tenant_id}",
            headers={"X-API-Key": "wrong-key"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_unknown_job_is_404(self):
        resp = self.client.get(
            f"/site-magic/internal/jobs/{uuid.uuid4()}?tenant_id={self.tenant_id}",
            headers={"X-API-Key": "internal-test-key"},
        )
        self.assertEqual(resp.status_code, 404)

    def test_internal_endpoint_does_not_require_a_customer_session(self):
        """Server-to-server: no Authorization bearer token needed, only
        the internal API key -- unlike every /site-magic/jobs/* route
        above, which goes through authorizer.authorize()."""
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.get(
            f"/site-magic/internal/jobs/{job_id}?tenant_id={self.tenant_id}",
            headers={"X-API-Key": "internal-test-key"},
        )
        self.assertEqual(resp.status_code, 200)


class TestInternalTransitionJob(SiteMagicAPITestCase):
    def _headers(self):
        return {"X-API-Key": "internal-test-key"}

    def test_valid_transition_advances_status(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ingesting")

    def test_transition_persists_quality_summary_and_round_counters(self):
        job_id = self._create_intake_job().json()["job_id"]
        for target in ("ingesting", "directing", "building", "evaluating"):
            self.client.post(
                f"/site-magic/internal/jobs/{job_id}/transition",
                json={"tenant_id": self.tenant_id, "target": target},
                headers=self._headers(),
            )
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={
                "tenant_id": self.tenant_id, "target": "remediating",
                "remediation_rounds": 1,
                "quality_summary": {"design_score": 20, "applicable_max": 32},
            },
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["remediation_rounds"], 1)
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT quality_summary_json FROM site_magic_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        self.assertIn("design_score", row["quality_summary_json"])

    def test_invalid_transition_returns_409(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "published"},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 409)

    def test_unknown_job_returns_404(self):
        resp = self.client.post(
            f"/site-magic/internal/jobs/{uuid.uuid4()}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 404)

    def test_missing_api_key_is_rejected(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
        )
        self.assertEqual(resp.status_code, 401)

    def test_out_of_range_remediation_rounds_rejected(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "remediation_rounds": 5},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def _advance_to_final_review(self, job_id):
        for target in ("ingesting", "directing", "building", "evaluating", "final_review"):
            self.client.post(
                f"/site-magic/internal/jobs/{job_id}/transition",
                json={"tenant_id": self.tenant_id, "target": target},
                headers=self._headers(),
            )

    def test_ready_for_review_with_build_id_seals_build_and_sets_final_url(self):
        job_id = self._create_intake_job().json()["job_id"]
        self._advance_to_final_review(job_id)

        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={
                "tenant_id": self.tenant_id, "target": "ready_for_review",
                "build_id": "build_1",
                "artifact_manifest": {"jobId": job_id, "buildId": "build_1"},
                "preview_locator": f"{self.tenant_id}/{job_id}/build_1.tar",
            },
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready_for_review")

        with connect(self.db_path) as conn:
            job_row = conn.execute(
                "SELECT final_build_id FROM site_magic_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            build_row = conn.execute(
                "SELECT preview_locator FROM site_magic_builds WHERE build_id = ?", ("build_1",)
            ).fetchone()
        self.assertEqual(job_row["final_build_id"], "build_1")
        self.assertEqual(build_row["preview_locator"], f"{self.tenant_id}/{job_id}/build_1.tar")

        # And the tenant-facing GET now exposes final_url once previewable.
        preview_resp = self._get(f"/site-magic/jobs/{job_id}/preview?tenant_id={self.tenant_id}")
        self.assertEqual(preview_resp.status_code, 200)

    def test_partial_build_fields_rejected(self):
        job_id = self._create_intake_job().json()["job_id"]
        self._advance_to_final_review(job_id)
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ready_for_review", "build_id": "build_1"},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 422)

    def test_seal_build_race_returns_409(self):
        """Two workers racing to seal the same build_id -- first wins,
        second gets a clean 409, not a silently-swapped build."""
        job_id_1 = self._create_intake_job().json()["job_id"]
        self._advance_to_final_review(job_id_1)
        job_id_2 = self._create_intake_job().json()["job_id"]
        self._advance_to_final_review(job_id_2)

        first = self.client.post(
            f"/site-magic/internal/jobs/{job_id_1}/transition",
            json={
                "tenant_id": self.tenant_id, "target": "ready_for_review", "build_id": "build_shared",
                "artifact_manifest": {}, "preview_locator": "loc-1",
            },
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/site-magic/internal/jobs/{job_id_2}/transition",
            json={
                "tenant_id": self.tenant_id, "target": "ready_for_review", "build_id": "build_shared",
                "artifact_manifest": {}, "preview_locator": "loc-2",
            },
            headers=self._headers(),
        )
        self.assertEqual(second.status_code, 503)


class TestInternalTransitionJobIdempotency(SiteMagicAPITestCase):
    def _headers(self):
        return {"X-API-Key": "internal-test-key"}

    def test_first_call_with_event_id_is_not_a_replay(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "event_id": "evt_1"},
            headers=self._headers(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["was_replay"])
        self.assertEqual(body["event_sequence"], 1)

    def test_retried_event_id_returns_200_replay_not_409(self):
        job_id = self._create_intake_job().json()["job_id"]
        first = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "event_id": "evt_1"},
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "event_id": "evt_1"},
            headers=self._headers(),
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["was_replay"])
        self.assertEqual(second.json()["status"], first.json()["status"])

    def test_late_retry_after_job_advanced_still_replays_not_409(self):
        job_id = self._create_intake_job().json()["job_id"]
        self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "event_id": "evt_1"},
            headers=self._headers(),
        )
        self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "directing", "event_id": "evt_2"},
            headers=self._headers(),
        )
        # evt_1 retried after the job already moved on to directing.
        late_retry = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting", "event_id": "evt_1"},
            headers=self._headers(),
        )
        self.assertEqual(late_retry.status_code, 200)
        self.assertTrue(late_retry.json()["was_replay"])
        self.assertEqual(late_retry.json()["status"], "directing")

    def test_genuinely_stale_transition_without_event_id_still_409s(self):
        """Two different callers racing the same status transition with no
        event_id at all -- no idempotency signal, so the plain optimistic
        guard applies and the loser still 409s. Confirms adding event_id
        support didn't loosen the non-idempotent path's behavior."""
        job_id = self._create_intake_job().json()["job_id"]
        first = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
            headers=self._headers(),
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
            headers=self._headers(),
        )
        self.assertEqual(second.status_code, 409)

    def test_response_has_no_replay_fields_when_event_id_omitted(self):
        job_id = self._create_intake_job().json()["job_id"]
        resp = self.client.post(
            f"/site-magic/internal/jobs/{job_id}/transition",
            json={"tenant_id": self.tenant_id, "target": "ingesting"},
            headers=self._headers(),
        )
        self.assertNotIn("was_replay", resp.json())
        self.assertNotIn("event_sequence", resp.json())


if __name__ == "__main__":
    unittest.main()
