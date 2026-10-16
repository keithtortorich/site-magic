#!/usr/bin/env python3
"""Fail-closed, secret-safe environment preflight for MVP activation."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


MVP_REQUIRED_ENV = (
    "DATABASE_URL",
    "SUPABASE_URL",
    "SUPABASE_PUBLISHABLE_KEY",
    "CUSTOMER_ALLOWED_ORIGINS",
    "GROK_API_KEY",
    "GHL_API_KEY",
    "GHL_LOCATION_ID",
    "GHL_WEBHOOK_SECRET",
    "RETELL_WEBHOOK_SECRET",
    "BOOK_API_KEY",
)


@dataclass(frozen=True)
class PreflightResult:
    name: str
    passed: bool
    detail: str


def run_preflight(environ: Mapping[str, str]) -> list[PreflightResult]:
    results = []
    for name in MVP_REQUIRED_ENV:
        present = bool(environ.get(name, "").strip())
        results.append(
            PreflightResult(
                name=name,
                passed=present,
                detail="configured" if present else "missing",
            )
        )

    leo_enabled = environ.get("LEO_OUTREACH_ENABLED", "").strip().lower() == "true"
    results.append(
        PreflightResult(
            name="LEO_OUTREACH_DISABLED",
            passed=not leo_enabled,
            detail="disabled" if not leo_enabled else "enabled before TCPA/DNC approval",
        )
    )
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check MVP environment presence without printing secret values"
    )
    parser.add_argument("--json", action="store_true", help="Emit safe JSON output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    results = run_preflight(os.environ)
    if args.json:
        print(json.dumps([asdict(result) for result in results], sort_keys=True))
    else:
        for result in results:
            label = "PASS" if result.passed else "FAIL"
            print(f"[{label}] {result.name}: {result.detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
