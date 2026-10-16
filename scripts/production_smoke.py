#!/usr/bin/env python3
"""Read-only smoke test for a deployed NetBuild.Pro release.

This command performs GET requests only. It never creates a tenant, submits a
lead, writes production data, or reads credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Sequence
from urllib.parse import quote, urlparse


@dataclass(frozen=True)
class SmokeResult:
    name: str
    passed: bool
    detail: str


def _fetch(url: str, timeout: float = 10.0) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": "NetBuild.Pro production smoke/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, dict(response.headers.items()), response.read()


def run_smoke(
    base_url: str,
    tenant_id: str | None = None,
    *,
    expected_sha: str | None = None,
    fetch: Callable[[str, float], tuple[int, dict[str, str], bytes]] = _fetch,
    timeout: float = 10.0,
) -> list[SmokeResult]:
    base_url = base_url.rstrip("/")
    checks: list[SmokeResult] = []

    try:
        status, headers, body = fetch(f"{base_url}/health", timeout)
        payload = json.loads(body.decode("utf-8"))
        security_headers = {key.lower(): value for key, value in headers.items()}
        expected_headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "strict-origin-when-cross-origin",
            "permissions-policy": "camera=(), microphone=(), geolocation=()",
        }
        headers_match = all(
            security_headers.get(name) == value
            for name, value in expected_headers.items()
        )
        hsts_present = "max-age=" in security_headers.get(
            "strict-transport-security", ""
        )
        release_matches = not expected_sha or payload.get("release") == expected_sha
        passed = (
            status == 200
            and payload.get("status") == "ok"
            and release_matches
            and headers_match
            and hsts_present
        )
        checks.append(
            SmokeResult(
                "health_and_security_headers",
                passed,
                "HTTP 200, healthy JSON, release SHA, and baseline security headers"
                if passed and expected_sha
                else "HTTP 200, healthy JSON, and baseline security headers"
                if passed
                else "health, release SHA, or baseline security headers did not match",
            )
        )
    except (OSError, ValueError, UnicodeError, urllib.error.URLError) as exc:
        checks.append(SmokeResult("health_and_security_headers", False, type(exc).__name__))

    try:
        status, _, body = fetch(f"{base_url}/", timeout)
        passed = status == 200 and b"NetBuild.Pro" in body
        checks.append(
            SmokeResult(
                "public_landing",
                passed,
                "HTTP 200 with canonical brand" if passed else "landing response did not match",
            )
        )
    except (OSError, urllib.error.URLError) as exc:
        checks.append(SmokeResult("public_landing", False, type(exc).__name__))

    if tenant_id:
        tenant_path = quote(tenant_id, safe="")
        for name, suffix, marker in (
            ("tenant_home", "/web", b"<html"),
            ("tenant_contact", "/web/contact", b'name="message"'),
        ):
            try:
                status, _, body = fetch(f"{base_url}/sites/{tenant_path}{suffix}", timeout)
                passed = status == 200 and marker.lower() in body.lower()
                checks.append(
                    SmokeResult(
                        name,
                        passed,
                        "HTTP 200 with expected generated-site surface"
                        if passed
                        else "tenant site response did not match",
                    )
                )
            except (OSError, urllib.error.URLError) as exc:
                checks.append(SmokeResult(name, False, type(exc).__name__))

    return checks


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only production smoke checks")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--tenant-id")
    parser.add_argument(
        "--expected-sha",
        help="Require /health to report this exact Vercel commit SHA",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument(
        "--allow-http",
        action="store_true",
        help="Allow plain HTTP for an explicitly local test server",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    parsed = urlparse(args.base_url)
    if parsed.scheme not in ({"https", "http"} if args.allow_http else {"https"}):
        print("Base URL must use HTTPS (or pass --allow-http for local testing).", file=sys.stderr)
        return 2
    if not parsed.netloc or args.timeout <= 0:
        print("A valid base URL and positive timeout are required.", file=sys.stderr)
        return 2

    results = run_smoke(
        args.base_url,
        args.tenant_id,
        expected_sha=args.expected_sha,
        timeout=args.timeout,
    )
    for result in results:
        label = "PASS" if result.passed else "FAIL"
        print(f"[{label}] {result.name}: {result.detail}")
    return 0 if all(result.passed for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
