#!/usr/bin/env python3
"""Apply an explicit, evidence-linked selection manifest to raw SERP data.

The DataForSEO collector intentionally emits only unclassified candidates.
This command is the narrow authorization boundary that assigns selected
training/holdout sites, franchise controls, and exclusions. It never infers
business identity or invents a reason for an unselected domain.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


PARTITIONS = {"training", "holdout", "franchise", "excluded"}
EXCLUSION_REASONS = {
    "paid-placement",
    "directory",
    "aggregator",
    "duplicate-domain",
    "duplicate-brand",
    "outside-metro",
    "not-contractor",
    "inaccessible",
    "insufficient-evidence",
    "other",
}


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: root must be an object")
    return value


def select(raw: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("raw corpus must contain candidates")
    by_id = {candidate.get("candidateId"): candidate for candidate in candidates}
    if len(by_id) != len(candidates) or None in by_id:
        raise ValueError("raw corpus candidateId values must be unique and non-null")

    partition_by_id: dict[str, str] = {}
    for partition in PARTITIONS:
        values = manifest.get(partition, [])
        if not isinstance(values, list):
            raise ValueError(f"manifest.{partition} must be an array")
        for candidate_id in values:
            if not isinstance(candidate_id, str) or candidate_id not in by_id:
                raise ValueError(f"manifest.{partition}: unknown candidateId {candidate_id!r}")
            if candidate_id in partition_by_id:
                raise ValueError(f"candidateId appears in multiple partitions: {candidate_id}")
            partition_by_id[candidate_id] = partition

    missing = set(by_id) - set(partition_by_id)
    if missing:
        raise ValueError(f"manifest must partition every raw candidate; missing {sorted(missing)}")

    exclusions = manifest.get("exclusions", {})
    if not isinstance(exclusions, dict):
        raise ValueError("manifest.exclusions must be an object keyed by candidateId")

    output = copy.deepcopy(raw)
    output["surveyRunId"] = f"{raw.get('surveyRunId', 'survey')}-selected"
    output_candidates = []
    for candidate in output["candidates"]:
        candidate_id = candidate["candidateId"]
        partition = partition_by_id[candidate_id]
        candidate.pop("exclusion", None)
        candidate["franchiseControl"] = partition == "franchise"
        if partition in {"training", "holdout"}:
            candidate["classification"] = "independent"
            candidate["split"] = partition
        elif partition == "franchise":
            candidate["classification"] = "franchise"
            candidate["split"] = "excluded"
        else:
            candidate["classification"] = "excluded"
            candidate["split"] = "excluded"
            exclusion = exclusions.get(candidate_id)
            if not isinstance(exclusion, dict):
                raise ValueError(f"excluded candidate requires manifest.exclusions[{candidate_id!r}]")
            reason = exclusion.get("reason")
            evidence_refs = exclusion.get("evidenceRefs")
            if reason not in EXCLUSION_REASONS:
                raise ValueError(f"invalid exclusion reason for {candidate_id}: {reason!r}")
            if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, str) for ref in evidence_refs):
                raise ValueError(f"exclusion evidenceRefs required for {candidate_id}")
            candidate["exclusion"] = {
                "reason": reason,
                "evidenceRefs": evidence_refs,
            }
            if isinstance(exclusion.get("details"), str):
                candidate["exclusion"]["details"] = exclusion["details"]
        output_candidates.append(candidate)
    output["candidates"] = output_candidates
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = select(load_object(args.raw), load_object(args.manifest))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
