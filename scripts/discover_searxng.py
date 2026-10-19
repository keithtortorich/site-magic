#!/usr/bin/env python3
"""Record SearXNG discovery results without treating them as SERP evidence.

SearXNG is a useful open-source replacement for paid search-discovery tools,
but its federated results do not provide the fixed geo-qualified ranking
contract required by the authoritative corpus validator. This artifact is
therefore discovery-only and cannot be passed to validate_corpus.py.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def discover(base_url: str, queries: list[str]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    endpoint = base_url.rstrip("/") + "/search"
    for query in queries:
        params = urllib.parse.urlencode({"q": query, "format": "json", "language": "en"})
        request = urllib.request.Request(f"{endpoint}?{params}", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # provider details stay out of the artifact
            raise RuntimeError(f"SearXNG discovery request failed for {query!r}: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError(f"SearXNG returned a non-object response for {query!r}")
        for item in payload.get("results", []):
            if not isinstance(item, dict) or not isinstance(item.get("url"), str):
                continue
            results.append({
                "query": query,
                "title": item.get("title"),
                "url": item["url"],
                "engines": item.get("engines", []),
            })
    return {
        "schemaVersion": "1.0.0",
        "provider": "searxng",
        "observedAt": now(),
        "authoritative": False,
        "selectionEligible": False,
        "queries": queries,
        "results": results,
        "limitations": [
            "No fixed geo-qualified rank is asserted.",
            "No business identity or independence is inferred.",
            "Use DataForSEO or another approved authoritative provider for corpus selection.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="Private SearXNG base URL")
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = discover(args.base_url, args.query)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"WROTE: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
