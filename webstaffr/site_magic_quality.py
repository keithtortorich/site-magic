"""Provider-neutral rendered-site quality gate used by Site Magic flows."""

from __future__ import annotations

from typing import Any


def quality_gates_pass(report: dict[str, Any]) -> bool:
    """Return true only when rendered evidence clears every required gate."""
    applicable_max = report.get("applicable_max")
    score = report.get("design_score")
    lighthouse = report.get("lighthouse", {})
    return bool(
        isinstance(applicable_max, (int, float))
        and applicable_max > 0
        and isinstance(score, (int, float))
        and score / applicable_max >= 0.90
        and report.get("open_p0", 1) == 0
        and report.get("open_p1", 1) == 0
        and report.get("detector_findings", 1) == 0
        and report.get("axe_violations", 1) == 0
        and lighthouse.get("accessibility", 0) == 100
        and lighthouse.get("performance", 0) >= 90
        and lighthouse.get("best_practices", 0) >= 95
        and lighthouse.get("seo", 0) >= 95
        and report.get("broken_links", 1) == 0
        and report.get("missing_assets", 1) == 0
        and report.get("console_errors", 1) == 0
        and report.get("failed_requests", 1) == 0
        and report.get("responsive_checks_passed") is True
        and report.get("functional_checks_passed") is True
        and report.get("content_integrity_passed") is True
        and report.get("tenant_isolation_passed") is True
        and report.get("finish_review") == "PASS"
        and report.get("authored_not_interchangeable") is True
    )
