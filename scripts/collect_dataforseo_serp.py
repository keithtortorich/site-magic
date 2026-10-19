#!/usr/bin/env python3
"""Collect authoritative DataForSEO Google organic observations.

The command fails closed when credentials or explicit location codes are
missing. It never falls back to generic search, model output, or fabricated
SERP records. Credentials are read from the environment and never printed.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUERIES = {
    "hvac-contractor": "HVAC contractor",
    "ac-repair": "AC repair",
    "furnace-repair": "furnace repair",
    "emergency-hvac": "emergency HVAC",
}
METROS = ("phoenix", "chicago", "dallas_fort_worth")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required; refusing to substitute non-authoritative SERP data")
    return value


def request_json(url: str, login: str, password: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DataForSEO request failed: {type(exc).__name__}") from exc


def extract_observations(response: dict[str, Any], *, metro: str, location_code: str, query_family: str, device: str) -> list[dict[str, Any]]:
    tasks = response.get("tasks") or []
    if not tasks or tasks[0].get("status_code") != 20000:
        raise RuntimeError(f"DataForSEO returned an unsuccessful task for {metro}/{query_family}/{device}")
    result = ((tasks[0].get("result") or [{}])[0])
    items = result.get("items") or []
    observations: list[dict[str, Any]] = []
    for item in items:
        if item.get("type") != "organic":
            continue
        url = item.get("url")
        position = item.get("rank_absolute")
        if not isinstance(url, str) or not isinstance(position, int):
            continue
        observations.append({
            "provider": "dataforseo",
            "locationCode": location_code,
            "locationName": metro,
            "device": device,
            "language": "en",
            "query": QUERIES[query_family],
            "observedAt": utc_now(),
            "organicPosition": position,
            "resultType": "organic",
            "resultUrl": url,
        })
    return observations


def collect(location_codes: dict[str, str], output: Path, *, device: str, delay_ms: int = 2000) -> None:
    login = required_env("DATAFORSEO_LOGIN")
    password = required_env("DATAFORSEO_PASSWORD")
    if set(location_codes) != set(METROS):
        raise RuntimeError(f"location codes must cover exactly {', '.join(METROS)}")
    # Keep one candidate per domain/metro pair. A domain appearing in more
    # than one metro must be explicitly deduplicated by the selection review;
    # silently collapsing it here would erase geo evidence.
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    endpoint = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    for metro in METROS:
        for query_family, keyword in QUERIES.items():
            payload = [{
                "language_code": "en",
                "location_code": int(location_codes[metro]),
                "keyword": f"{keyword} {metro.replace('_', ' ')}",
                "device": device,
                "depth": 10,
                "se_domain": "google.com",
            }]
            response = request_json(endpoint, login, password, payload)
            for observation in extract_observations(
                response, metro=metro, location_code=location_codes[metro], query_family=query_family, device=device
            ):
                host = observation["resultUrl"].split("/", 3)[2].lower().split(":", 1)[0]
                candidate_key = (host, metro)
                candidate_id = f"{host.replace('.', '-')}-{metro}"[:90]
                candidates.setdefault(candidate_key, {
                    "candidateId": candidate_id,
                    "domain": host,
                    "companyName": "Unclassified public SERP candidate",
                    "metro": metro,
                    "franchiseControl": False,
                    "serpCollection": [],
                    # Raw SERP evidence is not enough to establish business
                    # identity, independence, or a train/holdout split. The
                    # explicit selection-manifest step assigns those fields.
                    "classification": "excluded",
                    "split": "excluded",
                    "exclusion": {
                        "reason": "insufficient-evidence",
                        "evidenceRefs": [candidate_id],
                    },
                    "notes": "Domain-only candidate; requires explicit selection review.",
                })["serpCollection"].append(observation)
            time.sleep(delay_ms / 1000)
    result = {
        "schemaVersion": "1.0.0",
        "surveyRunId": f"dataforseo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        "generatedAt": utc_now(),
        "metros": list(METROS),
        "queryFamilies": list(QUERIES),
        "crawlPolicy": {
            "robotsTxtRequired": True,
            "delayMs": delay_ms,
            "concurrency": 2,
            "screenshotsOutsideProductRepo": True,
            "screenshotDirectory": "private-research/screenshots",
        },
        "selectionPolicy": {
            "minimumIndependentSites": 12,
            "maximumIndependentSites": 15,
            "minimumIndependentSitesPerMetro": 4,
            "maximumIndependentSitesPerMetro": 5,
            "holdoutSiteCount": 3,
            "holdoutMustIncludeEachMetro": True,
            "paidPlacementsExcluded": True,
            "directoriesExcluded": True,
            "aggregatorsExcluded": True,
            "duplicatesExcluded": True,
            "franchisesAreControlsOnly": True,
        },
        "candidates": list(candidates.values()),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location-code", action="append", required=True, metavar="METRO=CODE")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", choices=("desktop", "mobile"), default="desktop")
    args = parser.parse_args()
    try:
        location_codes = dict(item.split("=", 1) for item in args.location_code)
        if any(not key or not value.isdigit() for key, value in location_codes.items()):
            raise RuntimeError("each --location-code must use METRO=integer")
        collect(location_codes, args.output, device=args.device)
    except (RuntimeError, ValueError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
