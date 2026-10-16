#!/usr/bin/env python3
"""Validate Phase 0 corpus data and its Phase 2 section-registry merge.

This validator intentionally uses only the Python standard library. JSON Schema
handles shape; this module handles cross-record invariants and split integrity.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Iterable


EXPECTED_METROS = {"phoenix", "chicago", "dallas_fort_worth"}
EXPECTED_QUERY_FAMILIES = {
    "hvac-contractor",
    "ac-repair",
    "furnace-repair",
    "emergency-hvac",
}
SELECTED_CLASSIFICATIONS = {"independent"}
SELECTED_SPLITS = {"training", "holdout"}
EXCLUDED_REASONS = {
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
RENDERABLE_FACT_SOURCES = {"contractor-fact-ref", "derived-from-facts"}


def load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path}: cannot read JSON: {exc}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{path}: root must be an object")
        return None
    return value


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def unique(values: Iterable[Any]) -> bool:
    values = list(values)
    return len(values) == len(set(values))


def validate_corpus(corpus: dict[str, Any], errors: list[str]) -> None:
    require(corpus.get("schemaVersion") == "1.0.0", errors, "corpus: schemaVersion must be 1.0.0")
    require(set(corpus.get("metros", [])) == EXPECTED_METROS, errors, "corpus: metros must contain exactly the three target metros")
    require(set(corpus.get("queryFamilies", [])) == EXPECTED_QUERY_FAMILIES, errors, "corpus: queryFamilies must contain exactly the four query families")

    policy = corpus.get("crawlPolicy", {})
    require(policy.get("robotsTxtRequired") is True, errors, "corpus: robotsTxtRequired must be true")
    require(policy.get("delayMs") == 2000, errors, "corpus: delayMs must be 2000")
    require(policy.get("concurrency") == 2, errors, "corpus: concurrency must be 2")
    require(policy.get("screenshotsOutsideProductRepo") is True, errors, "corpus: screenshots must be outside the product repo")

    candidates = corpus.get("candidates", [])
    candidate_ids = [candidate.get("candidateId") for candidate in candidates]
    require(unique(candidate_ids), errors, "corpus: candidateId values must be unique")

    selected = []
    training = []
    holdout = []
    franchises = []
    selected_domains: set[str] = set()

    for index, candidate in enumerate(candidates):
        prefix = f"corpus.candidates[{index}]"
        classification = candidate.get("classification")
        split = candidate.get("split")
        domain = candidate.get("canonicalDomain") or candidate.get("domain")
        serp = candidate.get("serpCollection", [])

        require(classification in {"independent", "franchise", "excluded"}, errors, f"{prefix}: invalid classification")
        require(split in {"training", "holdout", "excluded"}, errors, f"{prefix}: invalid split")
        require(candidate.get("metro") in EXPECTED_METROS, errors, f"{prefix}: invalid metro")
        require(bool(serp), errors, f"{prefix}: at least one SERP observation is required")
        require(unique(observation.get("query") for observation in serp), errors, f"{prefix}: SERP query observations must be unique")

        if classification == "excluded":
            require(split == "excluded", errors, f"{prefix}: excluded candidates must use split=excluded")
            exclusion = candidate.get("exclusion") or {}
            require(exclusion.get("reason") in EXCLUDED_REASONS, errors, f"{prefix}: excluded candidate needs a valid exclusion reason")
            require(bool(exclusion.get("evidenceRefs")), errors, f"{prefix}: exclusion needs evidenceRefs")
            continue

        require(split in SELECTED_SPLITS, errors, f"{prefix}: selected candidate must be training or holdout")
        if classification == "franchise":
            franchises.append(candidate)
            require(candidate.get("franchiseControl") is True, errors, f"{prefix}: franchise must be marked franchiseControl")
            require(split == "excluded", errors, f"{prefix}: franchise controls cannot enter training or holdout")
            continue

        require(classification in SELECTED_CLASSIFICATIONS, errors, f"{prefix}: non-franchise selected candidate must be independent")
        require(candidate.get("franchiseControl") is False, errors, f"{prefix}: independent candidate cannot be a franchise control")
        require(domain not in selected_domains, errors, f"{prefix}: duplicate selected domain {domain!r}")
        selected_domains.add(domain)
        organic = [item for item in serp if item.get("resultType") == "organic" and isinstance(item.get("organicPosition"), int)]
        require(bool(organic), errors, f"{prefix}: selected candidate needs an organic SERP observation with a position")
        selected.append(candidate)
        (training if split == "training" else holdout).append(candidate)

    selection_policy = corpus.get("selectionPolicy", {})
    require(12 <= len(selected) <= 15, errors, f"corpus: selected independent sites must total 12-15, got {len(selected)}")
    require(3 <= len(holdout) <= 4, errors, f"corpus: holdout must contain 3-4 sites, got {len(holdout)}")
    require({candidate.get("metro") for candidate in holdout} == EXPECTED_METROS, errors, "corpus: holdout must include each metro")
    require(len(training) + len(holdout) == len(selected), errors, "corpus: training and holdout must partition selected sites")

    by_metro = {metro: 0 for metro in EXPECTED_METROS}
    for candidate in selected:
        by_metro[candidate["metro"]] += 1
    for metro, count in by_metro.items():
        require(4 <= count <= 5, errors, f"corpus: {metro} must have 4-5 selected independent sites, got {count}")

    require(selection_policy.get("franchisesAreControlsOnly") is True, errors, "corpus: franchisesAreControlsOnly must be true")
    require(all(candidate.get("split") == "excluded" for candidate in franchises), errors, "corpus: franchise controls must be excluded")


def validate_registry(registry: dict[str, Any], corpus: dict[str, Any], errors: list[str]) -> None:
    require(registry.get("schemaVersion") == "1.0.0", errors, "registry: schemaVersion must be 1.0.0")
    derived = registry.get("derivedFrom", {})
    candidates = corpus.get("candidates", [])
    training_ids = {candidate["candidateId"] for candidate in candidates if candidate.get("classification") == "independent" and candidate.get("split") == "training"}
    holdout_ids = {candidate["candidateId"] for candidate in candidates if candidate.get("classification") == "independent" and candidate.get("split") == "holdout"}
    franchise_ids = {candidate["candidateId"] for candidate in candidates if candidate.get("classification") == "franchise"}

    require(derived.get("split") == "training-only", errors, "registry: derivedFrom.split must be training-only")
    require(set(derived.get("trainingSiteIds", [])) == training_ids, errors, "registry: trainingSiteIds must match corpus training sites")
    require(set(derived.get("holdoutSiteIdsExcluded", [])) == holdout_ids, errors, "registry: holdoutSiteIdsExcluded must match corpus holdout sites")
    require(set(derived.get("franchiseControlSiteIdsExcluded", [])) == franchise_ids, errors, "registry: franchise controls must be excluded from registry derivation")

    provenance = registry.get("provenanceRequirements", [])
    provenance_by_id = {item.get("id"): item for item in provenance}
    require(len(provenance_by_id) == len(provenance), errors, "registry: provenance requirement IDs must be unique")
    prohibited = registry.get("prohibitedClaimPatterns", [])
    prohibited_ids = [item.get("patternId") for item in prohibited]
    require(unique(prohibited_ids), errors, "registry: prohibited claim pattern IDs must be unique")
    for index, item in enumerate(prohibited):
        prefix = f"registry.prohibitedClaimPatterns[{index}]"
        require(item.get("renderable") is False, errors, f"{prefix}: prohibited claims must be non-renderable")
        require(item.get("permanent") is True, errors, f"{prefix}: prohibited claims must be permanent")
        require(item.get("provenancePath") is None, errors, f"{prefix}: prohibited claims cannot have a provenance path")

    section_ids = [section.get("sectionType") for section in registry.get("sections", [])]
    require(unique(section_ids), errors, "registry: sectionType values must be unique")
    for section_index, section in enumerate(registry.get("sections", [])):
        prefix = f"registry.sections[{section_index}]"
        require(section.get("allowsArbitraryHtml") is False, errors, f"{prefix}: arbitrary HTML is forbidden")
        require(section.get("allowsArbitraryCss") is False, errors, f"{prefix}: arbitrary CSS is forbidden")
        require(section.get("allowsCustomSection") is False, errors, f"{prefix}: custom sections are forbidden")
        require(section.get("franchiseOnly") is False, errors, f"{prefix}: franchise-only sections cannot enter core registry")
        evidence = section.get("evidence", {})
        sites_providing = set(evidence.get("sitesProviding", []))
        observed = evidence.get("trainingSitesObserved")
        total = evidence.get("trainingSitesTotal")
        frequency = evidence.get("frequency")
        require(sites_providing <= training_ids, errors, f"{prefix}: sitesProviding must contain training sites only")
        require(observed == len(sites_providing), errors, f"{prefix}: trainingSitesObserved must equal sitesProviding length")
        require(isinstance(total, int) and total == len(training_ids), errors, f"{prefix}: trainingSitesTotal must equal training corpus size")
        if isinstance(total, int) and total:
            require(math.isclose(frequency, observed / total, rel_tol=0, abs_tol=1e-9), errors, f"{prefix}: frequency does not match observed/total")
        require(evidence.get("holdoutEvidenceIncluded") is False, errors, f"{prefix}: registry cannot include holdout evidence")
        require(evidence.get("directionalOnly") is True, errors, f"{prefix}: frequency must be marked directionalOnly")

        for field_index, field in enumerate(section.get("fields", [])):
            field_prefix = f"{prefix}.fields[{field_index}]"
            factual = field.get("factual") is True
            fact_kind = field.get("factKind")
            provenance_id = field.get("provenanceRequirementId")
            if factual:
                require(field.get("valueSource") in RENDERABLE_FACT_SOURCES, errors, f"{field_prefix}: factual fields require a ContractorFacts source")
                requirement = provenance_by_id.get(provenance_id)
                require(requirement is not None, errors, f"{field_prefix}: unknown provenanceRequirementId {provenance_id!r}")
                if requirement is not None:
                    require(requirement.get("factKind") == fact_kind, errors, f"{field_prefix}: factKind must match provenance requirement")
            else:
                require(not fact_kind and not provenance_id, errors, f"{field_prefix}: non-factual fields cannot reference facts or provenance")
                if field.get("valueSource") == "authored-copy":
                    require(field.get("claimScreening") == "no-material-claims", errors, f"{field_prefix}: authored copy needs claim screening")

        for variant_index, variant in enumerate(section.get("variants", [])):
            variant_prefix = f"{prefix}.variants[{variant_index}]"
            require(variant.get("compositionOnly") is True, errors, f"{variant_prefix}: variants must be composition-only")
            require(variant.get("changesFactualContent") is False, errors, f"{variant_prefix}: variants cannot change facts")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("registry", type=Path, nargs="?", help="optional training-only section registry")
    args = parser.parse_args()

    errors: list[str] = []
    corpus = load_json(args.corpus, errors)
    if corpus is not None:
        validate_corpus(corpus, errors)
        if args.registry is not None:
            registry = load_json(args.registry, errors)
            if registry is not None:
                validate_registry(registry, corpus, errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"FAILED: {len(errors)} validation error(s)", file=sys.stderr)
        return 1
    print("PASS: corpus validation completed")
    if args.registry is not None:
        print("PASS: registry merge invariants completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
