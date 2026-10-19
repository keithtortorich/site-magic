"""Run the local, synthetic Site Magic minimum viable demonstration.

This intentionally stops at a private checkpoint. It never publishes, calls
an external provider, or accepts non-synthetic tenant data.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path

from webstaffr.db import connect, migrate
from webstaffr.site_magic_control import (
    ControlPlaneConflictError,
    SiteMagicControlRepository,
)
from webstaffr.site_magic_quality import quality_gates_pass


ROOT = Path(__file__).resolve().parents[1]
FACT_PACKS = {
    "demo-hvac-a": ROOT / "demo/facts/demo-hvac-a.json",
    "demo-hvac-b": ROOT / "demo/facts/demo-hvac-b.json",
}


def _report(tenant_id: str) -> dict[str, object]:
    return {
        "gate_profile": "mvd", "applicable_max": 100, "design_score": 90,
        "open_p0": 0, "open_p1": 1, "detector_findings": 0,
        "axe_violations": 0, "lighthouse": {"accessibility": 90, "performance": 68,
        "best_practices": 82, "seo": 78}, "broken_links": 0, "missing_assets": 0,
        "console_errors": 0, "failed_requests": 0, "responsive_checks_passed": True,
        "functional_checks_passed": True, "content_integrity_passed": True,
        "tenant_isolation_passed": True, "finish_review": "PASS",
        "authored_not_interchangeable": True, "tenant_id": tenant_id,
    }


def _content(fact_id: str, tenant_id: str, *, edited: bool = False) -> dict[str, object]:
    return {
        "pages": [{"page_id": "home", "sections": [
            {"section_id": "hero", "purpose": "Introduce the synthetic business"},
            {"section_id": "services", "purpose": "Show verified services"},
            {"section_id": "proof", "purpose": "Show approved evidence"},
            {"section_id": "contact", "purpose": "Use a verified contact action"},
        ]}],
        "claims": [{"claim_id": "primary-service", "text": "Verified demo service",
                    "status": "supported", "fact_ids": [fact_id]}],
        "ctas": [{"cta_id": "contact", "label": "Contact the demo team", "target": "mailto:demo@example.invalid"}],
        "imagery_requirements": [{"slot": "hero", "proof_required": False}],
        "visual_direction": {"mood": "calm" if not edited else "high-contrast", "tenant": tenant_id},
    }


def _trace(build, fact_id: str, *, revision_id: str | None = None) -> dict[str, object]:
    trace: dict[str, object] = {
        "plan_hash": build.plan_hash, "fact_snapshot_hash": build.fact_snapshot_hash,
        "artifacts": [{"artifact_id": "home.html", "fact_ids": [fact_id], "claim_ids": ["primary-service"]}],
    }
    if revision_id:
        trace.update({"revision_id": revision_id, "changed_scope": ["home.hero"],
                      "unchanged_scope": ["home.services", "home.proof", "home.contact"]})
    return trace


def run(db_path: str) -> dict[str, object]:
    with connect(db_path) as conn:
        migrate(conn)
        user_id = str(uuid.uuid4())
        conn.execute("INSERT INTO customer_users (user_id) VALUES (?)", (user_id,))
        for tenant_id in FACT_PACKS:
            conn.execute("INSERT INTO tenants (tenant_id) VALUES (?)", (tenant_id,))
        repo = SiteMagicControlRepository(conn)
        actor = user_id
        results: dict[str, object] = {"mode": "private-synthetic-mvd", "release": "not_requested", "tenants": {}}
        previews: dict[str, object] = {}

        for tenant_id, pack_path in FACT_PACKS.items():
            pack = json.loads(pack_path.read_text())
            fact_data = next(fact for fact in pack["facts"] if fact["kind"] == "service")
            fact, _ = repo.create_fact(tenant_id=tenant_id, kind=fact_data["kind"], value=fact_data["value"],
                                       source=fact_data["source"], actor_id=user_id,
                                       correlation_id=tenant_id, idempotency_key=f"{tenant_id}:fact")
            fact, _ = repo.verify_fact(tenant_id=tenant_id, fact_id=fact.fact_id, actor_id=user_id,
                                       correlation_id=tenant_id, idempotency_key=f"{tenant_id}:verify")
            plan, _ = repo.propose_plan(tenant_id=tenant_id, fact_ids=[fact.fact_id], actor_id=user_id,
                                        correlation_id=tenant_id, idempotency_key=f"{tenant_id}:proposal")
            plan, _ = repo.patch_plan(tenant_id=tenant_id, plan_id=plan.plan_id, base_version=1,
                                      fact_ids=[fact.fact_id], content=_content(fact.fact_id, tenant_id),
                                      actor_id=user_id, correlation_id=tenant_id, idempotency_key=f"{tenant_id}:edit")
            approval, _ = repo.approve_plan(tenant_id=tenant_id, plan_id=plan.plan_id, version=2,
                                            actor_id=user_id, correlation_id=tenant_id, idempotency_key=f"{tenant_id}:approve")
            build, _ = repo.request_build(tenant_id=tenant_id, approval_id=approval.approval_id, plan_version=2,
                                          actor_id=user_id, correlation_id=tenant_id, idempotency_key=f"{tenant_id}:build")
            report = _report(tenant_id)
            preview, _ = repo.create_preview(
                tenant_id=tenant_id, build_id=build.build_id, preview_locator=f"{tenant_id}/{build.build_id}/preview.tar",
                artifact_manifest={"locator": f"{tenant_id}/{build.build_id}/preview.tar"},
                rendered_evidence={"routes": ["/"]}, trace_manifest=_trace(build, fact.fact_id), quality_report=report,
                actor_type="private_demo", actor_id=actor, correlation_id=tenant_id,
                idempotency_key=f"{tenant_id}:preview",
            )
            replay, replayed = repo.create_preview(
                tenant_id=tenant_id, build_id=build.build_id, preview_locator=f"{tenant_id}/{build.build_id}/preview.tar",
                artifact_manifest={"locator": f"{tenant_id}/{build.build_id}/preview.tar"}, rendered_evidence={"routes": ["/"]},
                trace_manifest=_trace(build, fact.fact_id), quality_report=report, actor_type="private_demo", actor_id=actor,
                correlation_id=tenant_id, idempotency_key=f"{tenant_id}:preview",
            )
            assert replay.preview_id == preview.preview_id and replayed
            revision, _ = repo.request_revision(tenant_id=tenant_id, preview_id=preview.preview_id, scope=["home.hero"],
                                                 request_text="Increase hero contrast", change_class="presentation",
                                                 expected_impact={"claims_changed": False}, actor_id=actor,
                                                 correlation_id=tenant_id, idempotency_key=f"{tenant_id}:revision")
            revised_build, _ = repo.apply_revision(tenant_id=tenant_id, revision_id=revision.revision_id, actor_id=actor,
                                                   correlation_id=tenant_id, idempotency_key=f"{tenant_id}:revision-apply")
            revised_preview, _ = repo.create_preview(
                tenant_id=tenant_id, build_id=revised_build.build_id,
                preview_locator=f"{tenant_id}/{revised_build.build_id}/preview.tar",
                artifact_manifest={"locator": f"{tenant_id}/{revised_build.build_id}/preview.tar"},
                rendered_evidence={"routes": ["/"]}, trace_manifest=_trace(revised_build, fact.fact_id, revision_id=revision.revision_id),
                quality_report=report, actor_type="private_demo", actor_id=actor, correlation_id=tenant_id,
                idempotency_key=f"{tenant_id}:revised-preview",
            )
            checkpoint, _ = repo.accept_checkpoint(tenant_id=tenant_id, preview_id=revised_preview.preview_id,
                                                   actor_id=actor, correlation_id=tenant_id,
                                                   idempotency_key=f"{tenant_id}:checkpoint")
            previews[tenant_id] = (preview, revised_preview)
            results["tenants"][tenant_id] = {"plan_versions": len(plan.versions), "preview": preview.status,
                                              "revised_preview": revised_preview.status, "checkpoint_id": checkpoint.checkpoint_id,
                                              "quality_profile": report["gate_profile"]}

        a_preview = previews["demo-hvac-a"][0]
        assert repo.get_preview(tenant_id="demo-hvac-b", preview_id=a_preview.preview_id) is None
        assert repo.get_plan(tenant_id="demo-hvac-b", plan_id=repo.get_build(tenant_id="demo-hvac-a", build_id=a_preview.build_id).plan_id) is None
        try:
            repo.get_build_source(tenant_id="demo-hvac-b", build_id=a_preview.build_id)
        except (ControlPlaneConflictError, LookupError):
            pass
        else:
            raise AssertionError("cross-tenant build source unexpectedly readable")
        results["isolation"] = "cross-tenant reads and build source denied"
        results["idempotency"] = "duplicate preview callback replayed"
        results["quality_gate"] = quality_gates_pass(_report("demo-hvac-a"), profile="mvd")
        assert results["quality_gate"] is True
        return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", help="SQLite path; defaults to a temporary private database")
    args = parser.parse_args()
    temporary = args.db is None
    fd, db_path = tempfile.mkstemp(prefix="site-magic-private-demo-", suffix=".db") if temporary else (None, args.db)
    if fd is not None:
        os.close(fd)
    try:
        print(json.dumps(run(db_path), indent=2, sort_keys=True))
    finally:
        if temporary:
            Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
