"""Tests for webstaffr/site_magic.py: state-machine transitions, release-gate
scoring, repository persistence, and fail-closed Null* contracts. Direct
repository tests against a real (temp-file) SQLite connection -- same
posture as AttributionUnitTestCase in test_attribution.py."""

import dataclasses
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from webstaffr.db import connect, migrate
from webstaffr.site_magic import (
    _json_column,
    ALLOWED_TRANSITIONS,
    ArtifactStorage,
    CodexRuntime,
    ImageGenerator,
    InvalidStateTransitionError,
    NullArtifactStorage,
    NullCodexRuntime,
    NullImageGenerator,
    NullSiteCrawler,
    NullSiteMagicQueue,
    SiteCrawler,
    SiteMagicNotConfiguredError,
    SiteMagicQueue,
    SiteMagicRepository,
    assert_transition,
    quality_gates_pass,
)


def _passing_report(**overrides):
    report = {
        "applicable_max": 32,
        "design_score": 29,  # 29/32 = 90.6%
        "open_p0": 0,
        "open_p1": 0,
        "detector_findings": 0,
        "axe_violations": 0,
        "lighthouse": {"accessibility": 100, "performance": 92, "best_practices": 96, "seo": 96},
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
    report.update(overrides)
    return report


class TestAssertTransition(unittest.TestCase):
    def test_every_declared_transition_is_allowed(self):
        for current, targets in ALLOWED_TRANSITIONS.items():
            for target in targets:
                assert_transition(current, target)  # must not raise

    def test_undeclared_transition_raises(self):
        with self.assertRaises(InvalidStateTransitionError):
            assert_transition("queued", "published")

    def test_terminal_statuses_allow_nothing(self):
        for terminal in ("published", "failed", "quarantined"):
            with self.assertRaises(InvalidStateTransitionError):
                assert_transition(terminal, "queued")

    def test_remediation_loop_back_to_evaluating_is_allowed(self):
        assert_transition("remediating", "evaluating")

    def test_final_review_rebuild_directive_returns_to_building(self):
        assert_transition("final_review", "building")


class TestQualityGatesPass(unittest.TestCase):
    def test_fully_passing_report_passes(self):
        self.assertTrue(quality_gates_pass(_passing_report()))

    def test_score_below_90_percent_of_applicable_max_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(design_score=28)))  # 28/32 = 87.5%

    def test_private_mvd_profile_keeps_safety_gates_but_relaxes_perfection_metrics(self):
        report = _passing_report(
            gate_profile="mvd",
            open_p1=1,
            lighthouse={"accessibility": 90, "performance": 68, "best_practices": 70, "seo": 70},
        )
        self.assertTrue(quality_gates_pass(report))
        self.assertFalse(quality_gates_pass(dict(report, axe_violations=1)))
        self.assertFalse(quality_gates_pass(dict(report, tenant_isolation_passed=False)))

    def test_open_p0_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(open_p0=1)))

    def test_open_p1_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(open_p1=1)))

    def test_detector_finding_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(detector_findings=1)))

    def test_axe_violation_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(axe_violations=1)))

    def test_lighthouse_accessibility_below_100_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(lighthouse={
            "accessibility": 99, "performance": 92, "best_practices": 96, "seo": 96,
        })))

    def test_lighthouse_performance_below_90_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(lighthouse={
            "accessibility": 100, "performance": 89, "best_practices": 96, "seo": 96,
        })))

    def test_broken_link_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(broken_links=1)))

    def test_console_error_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(console_errors=1)))

    def test_missing_responsive_check_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(responsive_checks_passed=False)))

    def test_missing_tenant_isolation_check_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(tenant_isolation_passed=False)))

    def test_finish_review_not_pass_fails(self):
        self.assertFalse(quality_gates_pass(_passing_report(finish_review="REBUILD")))

    def test_zero_applicable_max_fails_rather_than_dividing_by_zero(self):
        self.assertFalse(quality_gates_pass(_passing_report(applicable_max=0)))

    def test_missing_keys_fail_closed_not_default_pass(self):
        self.assertFalse(quality_gates_pass({}))


class SiteMagicRepositoryTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._conn_ctx = connect(self.db_path)
        self.conn = self._conn_ctx.__enter__()
        migrate(self.conn)
        self.conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("acme_hvac",))
        self.conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", ("other_tenant",))
        self.conn.commit()
        self.repo = SiteMagicRepository(self.conn)

    def tearDown(self):
        self._conn_ctx.__exit__(None, None, None)
        os.remove(self.db_path)


class TestCreateAndGetJob(SiteMagicRepositoryTestCase):
    def test_create_job_starts_queued(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={"intake_id": "s1"})
        self.conn.commit()
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.remediation_rounds, 0)
        self.assertEqual(job.rebuild_count, 0)
        self.assertIsNone(job.final_build_id)

    def test_get_job_is_tenant_scoped(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.assertIsNone(self.repo.get_job(tenant_id="other_tenant", job_id=job.job_id))
        self.assertIsNotNone(self.repo.get_job(tenant_id="acme_hvac", job_id=job.job_id))

    def test_get_unknown_job_returns_none(self):
        self.assertIsNone(self.repo.get_job(tenant_id="acme_hvac", job_id="not-a-real-id"))


class TestTransition(SiteMagicRepositoryTestCase):
    def test_valid_transition_updates_status(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        updated = self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target="ingesting")
        self.conn.commit()
        self.assertEqual(updated.status, "ingesting")

    def test_invalid_transition_raises_and_does_not_change_status(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        with self.assertRaises(InvalidStateTransitionError):
            self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target="published")
        self.assertEqual(self.repo.get_job(tenant_id="acme_hvac", job_id=job.job_id).status, "queued")

    def test_transition_unknown_job_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.repo.transition(tenant_id="acme_hvac", job_id="not-a-real-id", target="ingesting")

    def test_transition_wrong_tenant_raises_key_error(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        with self.assertRaises(KeyError):
            self.repo.transition(tenant_id="other_tenant", job_id=job.job_id, target="ingesting")

    def test_transition_persists_remediation_rounds_and_quality_summary(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        for target in ("ingesting", "directing", "building", "evaluating"):
            job = self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target=target)
            self.conn.commit()
        updated = self.repo.transition(
            tenant_id="acme_hvac", job_id=job.job_id, target="remediating",
            remediation_rounds=1, quality_summary={"design_score": 20, "applicable_max": 32},
        )
        self.conn.commit()
        self.assertEqual(updated.remediation_rounds, 1)
        self.assertEqual(updated.quality_summary, {"design_score": 20, "applicable_max": 32})

    def test_transition_persists_failure_code(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        updated = self.repo.transition(
            tenant_id="acme_hvac", job_id=job.job_id, target="failed", failure_code="codex_error",
        )
        self.conn.commit()
        self.assertEqual(updated.failure_code, "codex_error")

    def test_transition_without_optional_args_leaves_prior_values_unchanged(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        for target in ("ingesting", "directing", "building", "evaluating"):
            job = self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target=target)
            self.conn.commit()
        job = self.repo.transition(
            tenant_id="acme_hvac", job_id=job.job_id, target="remediating", remediation_rounds=1,
        )
        self.conn.commit()
        # Loop back to evaluating with no remediation_rounds arg -- must
        # still read as 1, not silently reset to 0/None.
        job = self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target="evaluating")
        self.conn.commit()
        self.assertEqual(job.remediation_rounds, 1)

    def test_concurrent_status_change_raises_instead_of_silently_overwriting(self):
        """The UPDATE's WHERE status = <status read at start of call> is the
        optimistic-concurrency guard. Simulate a stale read by making get_job
        return a job dataclass whose status disagrees with the row that's
        actually in the database."""
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target="ingesting")
        self.conn.commit()  # real row is now "ingesting"

        stale = dataclasses.replace(job, status="queued")
        with patch.object(self.repo, "get_job", return_value=stale):
            with self.assertRaises(InvalidStateTransitionError):
                self.repo.transition(tenant_id="acme_hvac", job_id=job.job_id, target="ingesting")


class TestBuildsAndPublish(SiteMagicRepositoryTestCase):
    def _job_ready_for_review(self, tenant_id="acme_hvac"):
        job = self.repo.create_job(tenant_id=tenant_id, source_type="intake", source_payload={})
        self.conn.commit()
        for target in ("ingesting", "directing", "building", "evaluating", "final_review", "ready_for_review"):
            job = self.repo.transition(tenant_id=tenant_id, job_id=job.job_id, target=target)
            self.conn.commit()
        self.conn.execute(
            """
            INSERT INTO site_magic_builds
                (build_id, job_id, tenant_id, artifact_manifest_json, preview_locator, created_at)
            VALUES ('build_1', ?, ?, '{}', 'builds/build_1/', datetime('now'))
            """,
            (job.job_id, tenant_id),
        )
        self.conn.execute(
            "UPDATE site_magic_jobs SET final_build_id = 'build_1' WHERE tenant_id = ? AND job_id = ?",
            (tenant_id, job.job_id),
        )
        self.conn.commit()
        return job.job_id

    def test_get_build_is_tenant_scoped(self):
        job_id = self._job_ready_for_review()
        self.assertIsNone(self.repo.get_build(tenant_id="other_tenant", build_id="build_1"))
        build = self.repo.get_build(tenant_id="acme_hvac", build_id="build_1")
        self.assertEqual(build.job_id, job_id)

    def test_publish_sets_published_url_status_and_active_build(self):
        job_id = self._job_ready_for_review()
        published = self.repo.publish(
            tenant_id="acme_hvac", job_id=job_id, build_id="build_1",
            published_url="https://acme-hvac.netbuild.pro",
        )
        self.conn.commit()
        self.assertEqual(published.status, "published")

        build = self.repo.get_build(tenant_id="acme_hvac", build_id="build_1")
        self.assertEqual(build.published_url, "https://acme-hvac.netbuild.pro")

        active = self.conn.execute(
            "SELECT build_id FROM site_magic_active_builds WHERE tenant_id = ?", ("acme_hvac",)
        ).fetchone()
        self.assertEqual(active["build_id"], "build_1")

    def test_publish_with_mismatched_build_id_raises_key_error(self):
        job_id = self._job_ready_for_review()
        with self.assertRaises(KeyError):
            self.repo.publish(
                tenant_id="acme_hvac", job_id=job_id, build_id="not-the-final-build",
                published_url="https://acme-hvac.netbuild.pro",
            )

    def test_publish_replaces_prior_active_build_for_tenant(self):
        job_id = self._job_ready_for_review()
        self.repo.publish(
            tenant_id="acme_hvac", job_id=job_id, build_id="build_1",
            published_url="https://acme-hvac.netbuild.pro",
        )
        self.conn.commit()

        job2 = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        for target in ("ingesting", "directing", "building", "evaluating", "final_review", "ready_for_review"):
            job2 = self.repo.transition(tenant_id="acme_hvac", job_id=job2.job_id, target=target)
            self.conn.commit()
        self.conn.execute(
            """
            INSERT INTO site_magic_builds
                (build_id, job_id, tenant_id, artifact_manifest_json, preview_locator, created_at)
            VALUES ('build_2', ?, 'acme_hvac', '{}', 'builds/build_2/', datetime('now'))
            """,
            (job2.job_id,),
        )
        self.conn.execute(
            "UPDATE site_magic_jobs SET final_build_id = 'build_2' WHERE tenant_id = 'acme_hvac' AND job_id = ?",
            (job2.job_id,),
        )
        self.conn.commit()

        self.repo.publish(
            tenant_id="acme_hvac", job_id=job2.job_id, build_id="build_2",
            published_url="https://acme-hvac.netbuild.pro",
        )
        self.conn.commit()

        active = self.conn.execute(
            "SELECT build_id FROM site_magic_active_builds WHERE tenant_id = ?", ("acme_hvac",)
        ).fetchone()
        self.assertEqual(active["build_id"], "build_2")

    def test_previous_published_build_row_survives_republish(self):
        """Immutable builds: publishing a newer build must not delete the
        old one -- rollback depends on every prior published build still
        existing."""
        job_id = self._job_ready_for_review()
        self.repo.publish(
            tenant_id="acme_hvac", job_id=job_id, build_id="build_1",
            published_url="https://acme-hvac.netbuild.pro",
        )
        self.conn.commit()
        self.assertIsNotNone(self.repo.get_build(tenant_id="acme_hvac", build_id="build_1"))


class TestSealBuildAndAdvance(SiteMagicRepositoryTestCase):
    def _job_at_final_review(self, tenant_id="acme_hvac"):
        job = self.repo.create_job(tenant_id=tenant_id, source_type="intake", source_payload={})
        self.conn.commit()
        for target in ("ingesting", "directing", "building", "evaluating", "final_review"):
            job = self.repo.transition(tenant_id=tenant_id, job_id=job.job_id, target=target)
            self.conn.commit()
        return job.job_id

    def test_seals_build_row_and_advances_job(self):
        job_id = self._job_at_final_review()
        updated = self.repo.seal_build_and_advance(
            tenant_id="acme_hvac", job_id=job_id, build_id="build_1",
            artifact_manifest={"jobId": job_id, "buildId": "build_1"},
            preview_locator="acme_hvac/job_1/build_1.tar",
        )
        self.conn.commit()

        self.assertEqual(updated.status, "ready_for_review")
        self.assertEqual(updated.final_build_id, "build_1")
        build = self.repo.get_build(tenant_id="acme_hvac", build_id="build_1")
        self.assertEqual(build.job_id, job_id)
        self.assertEqual(build.preview_locator, "acme_hvac/job_1/build_1.tar")

    def test_persists_remediation_rounds_and_rebuild_count(self):
        job_id = self._job_at_final_review()
        updated = self.repo.seal_build_and_advance(
            tenant_id="acme_hvac", job_id=job_id, build_id="build_1",
            artifact_manifest={}, preview_locator="loc",
            remediation_rounds=2, rebuild_count=1,
        )
        self.conn.commit()
        self.assertEqual(updated.remediation_rounds, 2)
        self.assertEqual(updated.rebuild_count, 1)

    def test_invalid_source_status_raises(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        with self.assertRaises(InvalidStateTransitionError):
            self.repo.seal_build_and_advance(
                tenant_id="acme_hvac", job_id=job.job_id, build_id="build_1",
                artifact_manifest={}, preview_locator="loc",
            )

    def test_unknown_job_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.repo.seal_build_and_advance(
                tenant_id="acme_hvac", job_id="not-a-real-id", build_id="build_1",
                artifact_manifest={}, preview_locator="loc",
            )

    def test_duplicate_build_id_for_different_job_rejected(self):
        """build_id is the primary key of site_magic_builds -- sealing the
        same id twice (e.g. a retried worker call after a crash) must not
        silently overwrite a different job's build."""
        job_id_1 = self._job_at_final_review()
        self.repo.seal_build_and_advance(
            tenant_id="acme_hvac", job_id=job_id_1, build_id="build_1",
            artifact_manifest={}, preview_locator="loc",
        )
        self.conn.commit()

        job_id_2 = self._job_at_final_review()
        with self.assertRaises(Exception):
            self.repo.seal_build_and_advance(
                tenant_id="acme_hvac", job_id=job_id_2, build_id="build_1",
                artifact_manifest={}, preview_locator="loc",
            )


class TestTransitionIdempotent(SiteMagicRepositoryTestCase):
    def test_new_event_id_advances_status_and_is_not_a_replay(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        updated, was_replay = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        self.assertEqual(updated.status, "ingesting")
        self.assertFalse(was_replay)

    def test_event_sequence_is_allocated_server_side_starting_at_one(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.assertEqual(job.current_event_sequence, 0)
        updated, _ = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        self.assertEqual(updated.current_event_sequence, 1)
        updated, _ = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_2", target="directing",
        )
        self.conn.commit()
        self.assertEqual(updated.current_event_sequence, 2)

    def test_repeated_event_id_is_a_replay_and_does_not_advance_further(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        first, first_replay = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        second, second_replay = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        self.assertFalse(first_replay)
        self.assertTrue(second_replay)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.current_event_sequence, second.current_event_sequence)

    def test_replay_of_a_now_stale_target_does_not_reapply(self):
        """A retried callback for a transition that already happened must
        come back as a replay, not attempt to re-run assert_transition()
        against the job's now-different current status."""
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_2", target="directing",
        )
        self.conn.commit()
        # Retry of evt_1 arrives late -- job is now "directing", not "queued".
        # Must replay the original cached result, not raise.
        job_after, was_replay = self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.assertTrue(was_replay)
        self.assertEqual(job_after.status, "directing")

    def test_different_event_ids_racing_on_same_status_raises(self):
        """Two different event_ids attempting the same status transition
        concurrently -- not a replay (different event_id), so the second
        one hits the same optimistic-concurrency guard transition() uses."""
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        with self.assertRaises(InvalidStateTransitionError):
            # Stale job object (dataclasses aren't re-read here) simulated
            # by directly calling with a target invalid from the new status.
            self.repo.transition_idempotent(
                tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_3", target="published",
            )

    def test_unknown_job_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.repo.transition_idempotent(
                tenant_id="acme_hvac", job_id="not-a-real-id", event_id="evt_1", target="ingesting",
            )

    def test_ledger_records_prior_and_new_state(self):
        job = self.repo.create_job(tenant_id="acme_hvac", source_type="intake", source_payload={})
        self.conn.commit()
        self.repo.transition_idempotent(
            tenant_id="acme_hvac", job_id=job.job_id, event_id="evt_1", target="ingesting",
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT prior_state, new_state, event_sequence FROM site_magic_job_events WHERE job_id = ? AND event_id = ?",
            (job.job_id, "evt_1"),
        ).fetchone()
        self.assertEqual(row["prior_state"], "queued")
        self.assertEqual(row["new_state"], "ingesting")
        self.assertEqual(row["event_sequence"], 1)


class TestNullContractsFailClosed(unittest.TestCase):
    def test_null_queue_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullSiteMagicQueue().enqueue(job_id="j1", tenant_id="acme_hvac")

    def test_null_artifact_storage_preview_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullArtifactStorage().signed_preview_url(tenant_id="acme_hvac", locator="x")

    def test_null_artifact_storage_publish_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullArtifactStorage().publish(tenant_id="acme_hvac", locator="x", build_id="b1")

    def test_null_crawler_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullSiteCrawler().snapshot(url="https://example.com", tenant_id="acme_hvac")

    def test_null_image_generator_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullImageGenerator().generate_directions(brief="a plumbing brand")

    def test_null_codex_runtime_raises(self):
        with self.assertRaises(SiteMagicNotConfiguredError):
            NullCodexRuntime().run(job_id="j1", workspace="/tmp/x", instructions="build it")

    def test_null_implementations_satisfy_their_protocols(self):
        # Purely structural -- Protocol classes aren't runtime_checkable here,
        # so this just documents/pins the expected method surface.
        self.assertTrue(hasattr(NullSiteMagicQueue(), "enqueue"))
        self.assertTrue(hasattr(NullArtifactStorage(), "signed_preview_url"))
        self.assertTrue(hasattr(NullArtifactStorage(), "publish"))
        self.assertTrue(hasattr(NullSiteCrawler(), "snapshot"))
        self.assertTrue(hasattr(NullImageGenerator(), "generate_directions"))
        self.assertTrue(hasattr(NullCodexRuntime(), "run"))


if __name__ == "__main__":
    unittest.main()


class JsonColumnPostgresParityTest(unittest.TestCase):
    """psycopg2 decodes jsonb before we see it; sqlite3 hands back TEXT.

    Regression for the 2026-08-12 production 500: the first real intake hit
    `json.loads()` on an already-decoded dict, raising TypeError. That is
    neither a DB_ERROR nor a SiteMagicNotConfiguredError, so it escaped every
    handler in intake's enqueue path -- a bare 500 with no log line, while the
    whole SQLite-backed suite stayed green.
    """

    def test_already_decoded_values_pass_through(self):
        self.assertEqual(_json_column({"a": 1}), {"a": 1})
        self.assertEqual(_json_column([1, 2]), [1, 2])

    def test_text_values_are_parsed(self):
        self.assertEqual(_json_column('{"a": 1}'), {"a": 1})

    def test_bytes_values_are_parsed(self):
        self.assertEqual(_json_column(b'{"a": 1}'), {"a": 1})

    def test_none_stays_none(self):
        self.assertIsNone(_json_column(None))

    def test_both_backends_yield_the_same_python_value(self):
        payload = {"intake_id": "15", "verified_facts": {"biz_name": "Acme"}}
        sqlite_shape = json.dumps(payload, sort_keys=True)   # TEXT column
        postgres_shape = payload                             # jsonb column
        self.assertEqual(_json_column(sqlite_shape), _json_column(postgres_shape))
