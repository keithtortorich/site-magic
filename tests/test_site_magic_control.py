"""Gate 0 control-plane tests.

These tests intentionally exercise the standalone facts -> plan -> approval
-> build authorization boundary, not the legacy site_magic_jobs worker path.
"""

from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from webstaffr.app import create_app
from webstaffr.customer_auth import VerifiedIdentity
from webstaffr.db import connect
from webstaffr.workers.angel.api_auth import StaticSecretVerifier


class _IdentityVerifier:
    def __init__(self, identity: VerifiedIdentity):
        self.identity = identity

    def verify(self, access_token):
        return self.identity if access_token == "test-token" else None


class _Publisher:
    def __init__(self):
        self.calls = []

    def publish(self, *, tenant_id, checkpoint_id, artifact_locator, artifact_manifest):
        self.calls.append((tenant_id, checkpoint_id, artifact_locator, artifact_manifest))
        return f"https://published.example/{tenant_id}/{checkpoint_id}"


class _Dispatcher:
    def __init__(self):
        self.builds = []

    def dispatch(self, *, build):
        self.builds.append(build)


class SiteMagicControlPlaneTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.user_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.publisher = _Publisher()
        identity = VerifiedIdentity(
            user_id=self.user_id,
            session_id=self.session_id,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        app = create_app(
            db_path=self.db_path,
            customer_identity_verifier=_IdentityVerifier(identity),
            customer_allowed_origins={"https://example.com"},
            internal_api_verifier=StaticSecretVerifier("internal-test-key"),
            site_magic_build_dispatcher=getattr(self, "dispatcher", None),
            site_magic_publisher=self.publisher,
        )
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO customer_users (user_id) VALUES (?)", (self.user_id,))
        self.client.post("/auth/session", headers=self._headers())
        self.tenant_id = self._make_tenant()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        os.remove(self.db_path)

    def _make_tenant(self, role="owner"):
        tenant_id = f"tenant_{uuid.uuid4().hex[:8]}"
        with connect(self.db_path) as conn:
            conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", (tenant_id,))
            conn.execute(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES (?, ?, ?)",
                (tenant_id, self.user_id, role),
            )
        return tenant_id

    @staticmethod
    def _headers(**extra):
        return {"Authorization": "Bearer test-token", **extra}

    @staticmethod
    def _content(fact_id, *, unsupported=False):
        status = "supported" if not unsupported else "bogus"
        fact_ids = [fact_id] if not unsupported else []
        return {
            "pages": [{"page_id": "home", "sections": [{"section_id": "hero"}]}],
            "claims": [{"claim_id": "service", "text": "Licensed service", "status": status, "fact_ids": fact_ids}],
            "ctas": [{"cta_id": "call", "label": "Call now", "target": "tel:+15551212"}],
            "imagery_requirements": [{"slot": "hero", "proof_required": True}],
            "visual_direction": {"mood": "clear", "palette": "customer-defined"},
        }

    def _post(self, path, body=None, key=None):
        headers = self._headers()
        if key is not None:
            headers["Idempotency-Key"] = key
        return self.client.post(path, json=body, headers=headers)

    def _approved_build(self, key_prefix="lifecycle"):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "service", "value": "Electrical", "source": {"type": "operator_input", "ref": f"{key_prefix}-fact"}},
            key=f"{key_prefix}-fact",
        ).json()
        self._post(
            f"/v1/tenants/{self.tenant_id}/facts/{fact['fact_id']}/verify", key=f"{key_prefix}-verify"
        )
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key=f"{key_prefix}-plan",
        ).json()
        approval = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/versions/1/approve",
            key=f"{key_prefix}-approve",
        ).json()
        build = self._post(
            f"/v1/tenants/{self.tenant_id}/builds",
            {"approval_id": approval["approval_id"], "plan_version": 1},
            key=f"{key_prefix}-build",
        ).json()
        return build

    @staticmethod
    def _quality_report(passed=True):
        return {
            "applicable_max": 100,
            "design_score": 95 if passed else 50,
            "open_p0": 0,
            "open_p1": 0,
            "detector_findings": 0,
            "axe_violations": 0,
            "lighthouse": {"accessibility": 100, "performance": 95, "best_practices": 100, "seo": 100},
            "broken_links": 0,
            "missing_assets": 0,
            "console_errors": 0,
            "failed_requests": 0,
            "responsive_checks_passed": True,
            "functional_checks_passed": True,
            "content_integrity_passed": True,
            "tenant_isolation_passed": True,
            "finish_review": "PASS",
            "authored_not_interchangeable": True,
        }


class TestGate0Flow(SiteMagicControlPlaneTestCase):
    def test_operator_workspace_is_a_tenant_scoped_gate0_shell(self):
        response = self.client.get(f"/tenants/{self.tenant_id}/site-magic")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Facts to an approved plan", response.text)
        self.assertIn("Generate safe starter plan", response.text)
        self.assertIn("Approve exact version", response.text)
        self.assertIn("Release this checkpoint", response.text)
        self.assertIn("/v1/tenants/", response.text)

    def test_plan_list_projection_is_tenant_scoped(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "service", "value": "Electrical", "source": {"type": "operator_input", "ref": "list-fact"}},
            key="list-fact",
        ).json()
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="list-plan",
        ).json()
        listed = self.client.get(
            f"/v1/tenants/{self.tenant_id}/plans", headers=self._headers()
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["plan_id"] for item in listed.json()["plans"]], [plan["plan_id"]])

    def test_safe_plan_proposal_generates_structure_and_proof_review_without_claims(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "service", "value": "Electrical", "source": {"type": "operator_input", "ref": "proposal-fact"}},
            key="proposal-fact",
        ).json()
        response = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/propose",
            {"fact_ids": [fact["fact_id"]]},
            key="proposal-plan",
        )
        self.assertEqual(response.status_code, 201)
        version = response.json()["versions"][0]
        self.assertEqual(version["status"], "proposed")
        self.assertEqual(version["content"]["pages"][0]["page_id"], "home")
        self.assertEqual(version["content"]["claims"][0]["status"], "needs_proof")
        self.assertEqual(version["content"]["claims"][0]["fact_ids"], [])
        self.assertEqual(version["fact_snapshot"][0]["fact_id"], fact["fact_id"])

    def test_build_engine_can_record_failure_and_failed_build_cannot_preview(self):
        build = self._approved_build("build-failure")
        failed = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/failed",
            json={"tenant_id": self.tenant_id, "failure_code": "engine_timeout"},
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "build-failure-callback"}),
        )
        self.assertEqual(failed.status_code, 202)
        self.assertEqual(failed.json()["status"], "failed")
        self.assertEqual(failed.json()["failure_code"], "engine_timeout")
        preview = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/failed-build",
                "artifact_manifest": {"locator": f"{self.tenant_id}/failed-build"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": {
                    "plan_hash": build["plan_hash"],
                    "fact_snapshot_hash": build["fact_snapshot_hash"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "failed-build-preview"}),
        )
        self.assertEqual(preview.status_code, 409)

    def test_facts_plan_approval_and_build_are_explicit_and_traceable(self):
        fact_response = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "credential", "value": {"license": "LIC-123"}, "source": {"type": "operator_input", "ref": "form-1"}},
            key="fact-create-1",
        )
        self.assertEqual(fact_response.status_code, 201)
        fact = fact_response.json()
        self.assertEqual(fact["status"], "unverified")

        verified = self._post(
            f"/v1/tenants/{self.tenant_id}/facts/{fact['fact_id']}/verify",
            key="fact-verify-1",
        )
        self.assertEqual(verified.status_code, 200)
        self.assertEqual(verified.json()["status"], "verified")

        plan_response = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="plan-create-1",
        )
        self.assertEqual(plan_response.status_code, 201)
        plan = plan_response.json()
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(plan["versions"][0]["status"], "proposed")

        before_approval = self._post(
            f"/v1/tenants/{self.tenant_id}/builds",
            {"approval_id": "missing", "plan_version": 1},
            key="build-before-approval",
        )
        self.assertEqual(before_approval.status_code, 404)

        approval_response = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/versions/1/approve",
            key="plan-approve-1",
        )
        self.assertEqual(approval_response.status_code, 200)
        approval = approval_response.json()
        self.assertEqual(approval["plan_version"], 1)

        build_response = self._post(
            f"/v1/tenants/{self.tenant_id}/builds",
            {"approval_id": approval["approval_id"], "plan_version": 1},
            key="build-1",
        )
        self.assertEqual(build_response.status_code, 202)
        build = build_response.json()
        self.assertEqual(build["status"], "requested")
        self.assertEqual(build["approval_id"], approval["approval_id"])
        build_read = self.client.get(
            f"/v1/tenants/{self.tenant_id}/builds/{build['build_id']}",
            headers=self._headers(),
        )
        self.assertEqual(build_read.status_code, 200)
        self.assertEqual(build_read.json()["build_id"], build["build_id"])
        source_read = self.client.get(
            f"/v1/internal/builds/{build['build_id']}/source",
            params={"tenant_id": self.tenant_id},
            headers=self._headers(**{"X-API-Key": "internal-test-key"}),
        )
        self.assertEqual(source_read.status_code, 200)
        self.assertEqual(source_read.json()["build"]["plan_hash"], build["plan_hash"])
        self.assertEqual(source_read.json()["plan"]["version"], 1)
        self.assertEqual(len(source_read.json()["facts"]), 1)
        isolated_source = self.client.get(
            f"/v1/internal/builds/{build['build_id']}/source",
            params={"tenant_id": self._make_tenant()},
            headers=self._headers(**{"X-API-Key": "internal-test-key"}),
        )
        self.assertEqual(isolated_source.status_code, 404)

        events = self.client.get(
            f"/v1/tenants/{self.tenant_id}/events", headers=self._headers()
        ).json()["events"]
        self.assertEqual(
            [event["event_type"] for event in events],
            ["fact_imported", "fact_verified", "plan_proposed", "plan_approved", "build_requested"],
        )
        approval_event = next(event for event in events if event["event_type"] == "plan_approved")
        self.assertEqual(approval_event["payload"]["approval_id"], approval["approval_id"])
        self.assertEqual(approval_event["payload"]["plan_hash"], approval["plan_hash"])

    def test_same_commands_are_idempotent(self):
        first = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "contact", "value": {"phone": "+15551212"}, "source": {"type": "operator_input", "ref": "form-2"}},
            key="same-fact",
        )
        second = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "contact", "value": {"phone": "+15551212"}, "source": {"type": "operator_input", "ref": "form-2"}},
            key="same-fact",
        )
        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(first.json()["fact_id"], second.json()["fact_id"])
        self.assertTrue(second.json()["replayed"])
        with connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM site_magic_facts").fetchone()["n"]
        self.assertEqual(count, 1)

    def test_approval_requires_verified_facts_and_supported_claims(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "proof", "value": "unverified", "source": {"type": "document", "ref": "doc-1"}},
            key="unverified-fact",
        ).json()
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="unverified-plan",
        ).json()
        response = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/versions/1/approve",
            key="unverified-approval",
        )
        self.assertEqual(response.status_code, 409)

        invalid = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [], "content": self._content("unused", unsupported=True)},
            key="invalid-plan",
        )
        self.assertEqual(invalid.status_code, 422)

    def test_editing_after_approval_creates_new_version_and_old_approval_cannot_build(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "service", "value": "Roof repair", "source": {"type": "operator_input", "ref": "form-3"}},
            key="version-fact",
        ).json()
        self._post(
            f"/v1/tenants/{self.tenant_id}/facts/{fact['fact_id']}/verify", key="version-verify"
        )
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="version-plan",
        ).json()
        approval = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/versions/1/approve", key="version-approve"
        ).json()
        edited_content = self._content(fact["fact_id"])
        edited_content["visual_direction"] = {"mood": "warm", "palette": "customer-defined"}
        edited = self.client.patch(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/draft",
            json={"base_version": 1, "fact_ids": [fact["fact_id"]], "content": edited_content},
            headers=self._headers(**{"Idempotency-Key": "version-edit"}),
        )
        self.assertEqual(edited.status_code, 200)
        self.assertEqual(edited.json()["current_version"], 2)
        self.assertEqual(edited.json()["versions"][0]["status"], "superseded")
        old_build = self._post(
            f"/v1/tenants/{self.tenant_id}/builds",
            {"approval_id": approval["approval_id"], "plan_version": 1},
            key="old-build",
        )
        self.assertEqual(old_build.status_code, 409)

    def test_database_enforces_immutable_approval_event_and_plan_content(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "service", "value": "Plumbing", "source": {"type": "operator_input", "ref": "form-5"}},
            key="immutable-fact",
        ).json()
        self._post(
            f"/v1/tenants/{self.tenant_id}/facts/{fact['fact_id']}/verify", key="immutable-verify"
        )
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="immutable-plan",
        ).json()
        approval = self._post(
            f"/v1/tenants/{self.tenant_id}/plans/{plan['plan_id']}/versions/1/approve", key="immutable-approve"
        ).json()
        with connect(self.db_path) as conn:
            with self.assertRaises(Exception):
                conn.execute(
                    "UPDATE site_magic_events SET event_type = 'tampered' WHERE tenant_id = ?",
                    (self.tenant_id,),
                )
            with self.assertRaises(Exception):
                conn.execute(
                    "UPDATE site_magic_approvals SET plan_hash = 'tampered' WHERE approval_id = ?",
                    (approval["approval_id"],),
                )
            with self.assertRaises(Exception):
                conn.execute(
                    "UPDATE site_magic_plan_versions SET content_json = '{}' WHERE plan_id = ?",
                    (plan["plan_id"],),
                )

    def test_rendered_preview_gate_revision_checkpoint_and_explicit_release(self):
        build = self._approved_build()
        trace = {
            "plan_hash": build["plan_hash"],
            "fact_snapshot_hash": build["fact_snapshot_hash"],
            "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
        }
        blocked = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/build-blocked",
                "artifact_manifest": {"locator": f"{self.tenant_id}/build-blocked"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": trace,
                "quality_report": self._quality_report(False),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "preview-blocked"}),
        )
        self.assertEqual(blocked.status_code, 202)
        self.assertEqual(blocked.json()["status"], "blocked")
        blocked_checkpoint = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{blocked.json()['preview_id']}/checkpoint",
            key="blocked-checkpoint",
        )
        self.assertEqual(blocked_checkpoint.status_code, 409)

        ready_build = self._approved_build("ready")
        ready = self.client.post(
            f"/v1/internal/builds/{ready_build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/build-ready",
                "artifact_manifest": {"locator": f"{self.tenant_id}/build-ready"},
                "rendered_evidence": {"routes": ["/", "/services"]},
                "trace_manifest": {
                    "plan_hash": ready_build["plan_hash"],
                    "fact_snapshot_hash": ready_build["fact_snapshot_hash"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "preview-ready"}),
        )
        self.assertEqual(ready.status_code, 202)
        self.assertEqual(ready.json()["status"], "ready")
        self.assertEqual(self.publisher.calls, [])

        presentation = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{ready.json()['preview_id']}/revisions",
            {
                "scope": ["home.hero"], "request_text": "Adjust spacing within the hero",
                "change_class": "presentation", "expected_impact": {"unchanged": ["services"]},
            },
            key="revision-presentation",
        )
        self.assertEqual(presentation.status_code, 201)
        presentation_build = self._post(
            f"/v1/tenants/{self.tenant_id}/revisions/{presentation.json()['revision_id']}/apply",
            key="revision-presentation-apply",
        )
        self.assertEqual(presentation_build.status_code, 202)
        self.assertEqual(presentation_build.json()["revision_id"], presentation.json()["revision_id"])
        self.assertEqual(presentation_build.json()["revision_scope"], ["home.hero"])
        revised_preview = self.client.post(
            f"/v1/internal/builds/{presentation_build.json()['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/build-presentation-revised",
                "artifact_manifest": {"locator": f"{self.tenant_id}/build-presentation-revised"},
                "rendered_evidence": {"routes": ["/", "/services"]},
                "trace_manifest": {
                    "plan_hash": presentation_build.json()["plan_hash"],
                    "fact_snapshot_hash": presentation_build.json()["fact_snapshot_hash"],
                    "revision_id": presentation.json()["revision_id"],
                    "changed_scope": ["home.hero"],
                    "unchanged_scope": [],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "preview-presentation-revised"}),
        )
        self.assertEqual(revised_preview.status_code, 202)

        unbounded = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{ready.json()['preview_id']}/revisions",
            {
                "scope": ["home.hero"], "request_text": "Another bounded visual adjustment",
                "change_class": "presentation", "expected_impact": {},
            },
            key="revision-unbounded",
        ).json()
        unbounded_build = self._post(
            f"/v1/tenants/{self.tenant_id}/revisions/{unbounded['revision_id']}/apply",
            key="revision-unbounded-apply",
        ).json()
        unbounded_preview = self.client.post(
            f"/v1/internal/builds/{unbounded_build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/build-unbounded",
                "artifact_manifest": {"locator": f"{self.tenant_id}/build-unbounded"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": {
                    "plan_hash": unbounded_build["plan_hash"],
                    "fact_snapshot_hash": unbounded_build["fact_snapshot_hash"],
                    "revision_id": unbounded["revision_id"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "preview-unbounded"}),
        )
        self.assertEqual(unbounded_preview.status_code, 422)

        revision = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{ready.json()['preview_id']}/revisions",
            {
                "scope": ["home.hero"], "request_text": "Use the approved warm visual direction",
                "change_class": "semantic", "expected_impact": {"unchanged": ["services"]},
            },
            key="revision-1",
        )
        self.assertEqual(revision.status_code, 201)
        self.assertTrue(revision.json()["requires_reapproval"])
        semantic_apply = self._post(
            f"/v1/tenants/{self.tenant_id}/revisions/{revision.json()['revision_id']}/apply",
            key="revision-semantic-apply-without-approval",
        )
        self.assertEqual(semantic_apply.status_code, 409)

        checkpoint = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{ready.json()['preview_id']}/checkpoint",
            key="checkpoint-1",
        )
        self.assertEqual(checkpoint.status_code, 201)
        self.assertEqual(self.publisher.calls, [])

        release = self._post(
            f"/v1/tenants/{self.tenant_id}/checkpoints/{checkpoint.json()['checkpoint_id']}/release",
            key="release-1",
        )
        self.assertEqual(release.status_code, 202)
        self.assertEqual(release.json()["status"], "published")
        self.assertEqual(len(self.publisher.calls), 1)

    def test_preview_rejects_artifact_trace_outside_approved_fact_snapshot(self):
        build = self._approved_build("trace-boundary")
        response = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/trace-boundary",
                "artifact_manifest": {"locator": f"{self.tenant_id}/trace-boundary"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": {
                    "plan_hash": build["plan_hash"],
                    "fact_snapshot_hash": build["fact_snapshot_hash"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": ["not-approved"]}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "trace-boundary-preview"}),
        )
        self.assertEqual(response.status_code, 409)

    def test_preview_rejects_artifact_locator_outside_tenant_scope(self):
        build = self._approved_build("locator-boundary")
        response = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": "other-tenant/build-1",
                "artifact_manifest": {"locator": "other-tenant/build-1"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": {
                    "plan_hash": build["plan_hash"],
                    "fact_snapshot_hash": build["fact_snapshot_hash"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "locator-boundary-preview"}),
        )
        self.assertEqual(response.status_code, 409)


class TestGate0TenantIsolation(SiteMagicControlPlaneTestCase):
    def test_plan_is_not_readable_through_another_tenant_scope(self):
        fact = self._post(
            f"/v1/tenants/{self.tenant_id}/facts",
            {"kind": "brand", "value": {"name": "A"}, "source": {"type": "operator_input", "ref": "form-4"}},
            key="isolation-fact",
        ).json()
        plan = self._post(
            f"/v1/tenants/{self.tenant_id}/plans",
            {"fact_ids": [fact["fact_id"]], "content": self._content(fact["fact_id"])},
            key="isolation-plan",
        ).json()
        other_tenant = self._make_tenant()
        response = self.client.get(
            f"/v1/tenants/{other_tenant}/plans/{plan['plan_id']}", headers=self._headers()
        )
        self.assertEqual(response.status_code, 404)


class TestBuildDispatcher(SiteMagicControlPlaneTestCase):
    def setUp(self):
        self.dispatcher = _Dispatcher()
        super().setUp()

    def test_dispatcher_receives_only_approved_build_envelope(self):
        build = self._approved_build("dispatch")
        self.assertEqual(len(self.dispatcher.builds), 1)
        dispatched = self.dispatcher.builds[0]
        self.assertEqual(dispatched.build_id, build["build_id"])
        self.assertEqual(dispatched.approval_id, build["approval_id"])
        self.assertEqual(dispatched.plan_version, 1)
        self.assertEqual(dispatched.plan_hash, build["plan_hash"])

    def test_dispatcher_receives_revision_scope_on_presentation_rebuild(self):
        build = self._approved_build("dispatch-revision")
        preview = self.client.post(
            f"/v1/internal/builds/{build['build_id']}/preview",
            json={
                "tenant_id": self.tenant_id,
                "preview_locator": f"{self.tenant_id}/dispatch-revision",
                "artifact_manifest": {"locator": f"{self.tenant_id}/dispatch-revision"},
                "rendered_evidence": {"routes": ["/"]},
                "trace_manifest": {
                    "plan_hash": build["plan_hash"],
                    "fact_snapshot_hash": build["fact_snapshot_hash"],
                    "artifacts": [{"artifact_id": "home.html", "fact_ids": []}],
                },
                "quality_report": self._quality_report(True),
            },
            headers=self._headers(**{"X-API-Key": "internal-test-key", "Idempotency-Key": "dispatch-revision-preview"}),
        ).json()
        revision = self._post(
            f"/v1/tenants/{self.tenant_id}/previews/{preview['preview_id']}/revisions",
            {
                "scope": ["home.hero"], "request_text": "Refine hero spacing",
                "change_class": "presentation", "expected_impact": {},
            },
            key="dispatch-revision-request",
        ).json()
        applied = self._post(
            f"/v1/tenants/{self.tenant_id}/revisions/{revision['revision_id']}/apply",
            key="dispatch-revision-apply",
        )
        self.assertEqual(applied.status_code, 202)
        self.assertEqual(len(self.dispatcher.builds), 2)
        dispatched = self.dispatcher.builds[1]
        self.assertEqual(dispatched.revision_id, revision["revision_id"])
        self.assertEqual(list(dispatched.revision_scope), ["home.hero"])
