#!/usr/bin/env python3
"""Validate the VRE-safe Site Magic synthetic demo artifacts.

This validator deliberately uses only the standard library. It enforces the
synthetic-tenant boundary, claim provenance, bounded model-analysis shape, and
the private-checkpoint finish line without contacting any external service.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


TENANTS = {"demo-hvac-a", "demo-hvac-b"}
FACT_STATUSES = {"verified"}
CLAIM_STATUSES = {"supported", "omitted", "needs_proof"}
DESIGN_VARIANTS = {"workshop-contrast", "field-notebook", "after-hours"}
MODEL_WORKERS = {"gemini-visual", "grok-text-seo", "gemini-critic", "grok-critic"}
REAL_CONTACT_MARKERS = ("@gmail.", "@yahoo.", "@outlook.", "@hotmail.", "@icloud.")


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def synthetic_hash(facts: dict[str, Any]) -> str:
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_facts(value: dict[str, Any], errors: list[str]) -> str | None:
    tenant_id = value.get("tenantId")
    if tenant_id not in TENANTS:
        fail(errors, f"facts: tenantId must be one of {sorted(TENANTS)}")
    if value.get("tenantMode") != "synthetic-demo":
        fail(errors, "facts: tenantMode must be synthetic-demo")
    facts = value.get("facts")
    if not isinstance(facts, list) or not facts:
        fail(errors, "facts: facts must be a non-empty array")
        return tenant_id if isinstance(tenant_id, str) else None
    fact_ids: set[str] = set()
    for index, fact in enumerate(facts):
        prefix = f"facts[{index}]"
        if not isinstance(fact, dict):
            fail(errors, f"{prefix}: must be an object")
            continue
        fact_id = fact.get("factId")
        if not isinstance(fact_id, str) or fact_id in fact_ids:
            fail(errors, f"{prefix}: factId must be unique")
        fact_ids.add(fact_id)
        if fact.get("status") not in FACT_STATUSES:
            fail(errors, f"{prefix}: only synthetic verified facts are allowed")
        source = fact.get("source")
        if not isinstance(source, dict) or source.get("type") != "demo-only" or source.get("ref") != "VRE_SAFE_DEMO.md":
            fail(errors, f"{prefix}: source must be demo-only and reference VRE_SAFE_DEMO.md")
        raw = json.dumps(fact.get("value"), ensure_ascii=False).lower()
        if any(marker in raw for marker in REAL_CONTACT_MARKERS):
            fail(errors, f"{prefix}: real-looking email provider is prohibited")
        if "@" in raw and ".invalid" not in raw:
            fail(errors, f"{prefix}: email values must use .invalid")
    return tenant_id if isinstance(tenant_id, str) else None


def validate_site_spec(value: dict[str, Any], facts: dict[str, Any], errors: list[str]) -> None:
    tenant_id = value.get("tenantId")
    if tenant_id not in TENANTS or tenant_id != facts.get("tenantId"):
        fail(errors, "site-spec: tenantId must match the synthetic fact pack")
    if value.get("tenantMode") != "synthetic-demo":
        fail(errors, "site-spec: tenantMode must be synthetic-demo")
    expected_hash = synthetic_hash(facts)
    if value.get("factSnapshotHash") != expected_hash:
        fail(errors, "site-spec: factSnapshotHash does not match the fact pack")
    if value.get("designVariant") is not None and value.get("designVariant") not in DESIGN_VARIANTS:
        fail(errors, f"site-spec: designVariant must be one of {sorted(DESIGN_VARIANTS)}")
    fact_ids = {item.get("factId") for item in facts.get("facts", [])}
    sections = value.get("sections")
    if not isinstance(sections, list) or not sections:
        fail(errors, "site-spec: sections must be a non-empty array")
        return
    section_ids: set[str] = set()
    for index, section in enumerate(sections):
        prefix = f"site-spec.sections[{index}]"
        if not isinstance(section, dict):
            fail(errors, f"{prefix}: must be an object")
            continue
        section_id = section.get("sectionId")
        if not isinstance(section_id, str) or section_id in section_ids:
            fail(errors, f"{prefix}: sectionId must be unique")
        section_ids.add(section_id)
        for claim_index, claim in enumerate(section.get("claims", [])):
            claim_prefix = f"{prefix}.claims[{claim_index}]"
            if not isinstance(claim, dict):
                fail(errors, f"{claim_prefix}: must be an object")
                continue
            status = claim.get("status")
            if status not in CLAIM_STATUSES:
                fail(errors, f"{claim_prefix}: invalid claim status")
            claim_fact_ids = claim.get("factIds", [])
            if not isinstance(claim_fact_ids, list):
                fail(errors, f"{claim_prefix}: factIds must be an array")
                claim_fact_ids = []
            unknown = set(claim_fact_ids) - fact_ids
            if unknown:
                fail(errors, f"{claim_prefix}: unknown fact IDs {sorted(unknown)}")
            if status == "supported" and not claim_fact_ids:
                fail(errors, f"{claim_prefix}: supported claims require factIds")
            if status != "supported" and claim_fact_ids:
                fail(errors, f"{claim_prefix}: omitted/needs_proof claims cannot bind facts")
            if status == "needs_proof" and not claim.get("reason"):
                fail(errors, f"{claim_prefix}: needs_proof claims require a reason")


def validate_model_analysis(value: dict[str, Any], errors: list[str]) -> None:
    worker = value.get("worker")
    if worker not in MODEL_WORKERS:
        fail(errors, "model-analysis: unknown worker")
    scope = value.get("scope")
    if not isinstance(scope, dict) or scope.get("tenantMode") not in {"public-research", "synthetic-demo"}:
        fail(errors, "model-analysis: scope.tenantMode must be public-research or synthetic-demo")
    findings = value.get("findings")
    if not isinstance(findings, list):
        fail(errors, "model-analysis: findings must be an array")
        return
    finding_ids: set[str] = set()
    for index, finding in enumerate(findings):
        prefix = f"model-analysis.findings[{index}]"
        if not isinstance(finding, dict):
            fail(errors, f"{prefix}: must be an object")
            continue
        finding_id = finding.get("findingId")
        if not isinstance(finding_id, str) or finding_id in finding_ids:
            fail(errors, f"{prefix}: findingId must be unique")
        finding_ids.add(finding_id)
        if finding.get("factual") is not False:
            fail(errors, f"{prefix}: model findings must be observations, never facts")
        refs = finding.get("evidenceRefs")
        if not isinstance(refs, list) or not refs:
            fail(errors, f"{prefix}: evidenceRefs are required")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--facts", action="append", type=Path, default=[])
    parser.add_argument("--site-spec", action="append", type=Path, default=[])
    parser.add_argument("--model-analysis", action="append", type=Path, default=[])
    args = parser.parse_args()
    errors: list[str] = []
    fact_by_tenant: dict[str, dict[str, Any]] = {}
    for path in args.facts:
        try:
            value = load(path)
            tenant_id = validate_facts(value, errors)
            if tenant_id:
                if tenant_id in fact_by_tenant:
                    fail(errors, f"facts: duplicate tenant pack {tenant_id}")
                fact_by_tenant[tenant_id] = value
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            fail(errors, f"{path}: {exc}")
    for path in args.site_spec:
        try:
            value = load(path)
            tenant_id = value.get("tenantId")
            facts = fact_by_tenant.get(tenant_id)
            if facts is None:
                fail(errors, f"{path}: no fact pack for tenant {tenant_id!r}")
            else:
                validate_site_spec(value, facts, errors)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            fail(errors, f"{path}: {exc}")
    for path in args.model_analysis:
        try:
            validate_model_analysis(load(path), errors)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            fail(errors, f"{path}: {exc}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} validation error(s)", file=sys.stderr)
        return 1
    print("PASS: VRE-safe demo artifacts validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
