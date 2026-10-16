"""Standalone Site Magic control-plane contracts for Gate 0.

This module deliberately does not use the legacy ``site_magic_jobs`` tables.
It owns the product boundary for facts, versioned plans, approvals, build
authorization, and the append-only product event ledger. Worker jobs and
provider callbacks can be adapters behind this boundary later.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional, Protocol

from .site_magic_quality import quality_gates_pass


class ControlPlaneNotFoundError(LookupError):
    pass


class ControlPlaneConflictError(ValueError):
    pass


class ControlPlaneValidationError(ValueError):
    pass


class ControlPlaneNotConfiguredError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _decode(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    return json.loads(value)


def _hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _fact_snapshot_hash(facts: list[dict[str, Any]]) -> str:
    return _hash([
        {"fact_id": fact["fact_id"], "content_hash": fact["content_hash"], "status": fact["status"]}
        for fact in sorted(facts, key=lambda item: item["fact_id"])
    ])


def _validate_tenant_locator(tenant_id: str, locator: Any, label: str) -> None:
    """Require private artifact paths to be rooted in their owning tenant."""
    if not isinstance(locator, str) or not locator:
        raise ControlPlaneValidationError(f"{label} locator is required")
    parts = locator.split("/")
    if len(parts) < 2 or parts[0] != tenant_id or any(part in {"", ".", ".."} for part in parts):
        raise ControlPlaneConflictError(f"{label} locator is outside the tenant scope")


def _as_fact(row) -> "SiteMagicFact":
    return SiteMagicFact(
        fact_id=str(row["fact_id"]), tenant_id=str(row["tenant_id"]), kind=str(row["kind"]),
        value=_decode(row["value_json"]), source=_decode(row["source_json"]),
        status=str(row["status"]), verified_by=row["verified_by"], verified_at=row["verified_at"],
        content_hash=str(row["content_hash"]), created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def _as_preview(row) -> "SiteMagicPreview":
    return SiteMagicPreview(
        preview_id=str(row["preview_id"]), build_id=str(row["build_id"]),
        tenant_id=str(row["tenant_id"]), preview_locator=str(row["preview_locator"]),
        artifact_manifest=_decode(row["artifact_manifest_json"]),
        rendered_evidence=_decode(row["rendered_evidence_json"]),
        trace_manifest=_decode(row["trace_manifest_json"]),
        quality_report=_decode(row["quality_report_json"]), status=str(row["status"]),
        created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
    )


def _as_revision(row) -> "SiteMagicRevision":
    return SiteMagicRevision(
        revision_id=str(row["revision_id"]), preview_id=str(row["preview_id"]),
        tenant_id=str(row["tenant_id"]), scope=_decode(row["scope_json"]),
        request_text=str(row["request_text"]), change_class=str(row["change_class"]),
        expected_impact=_decode(row["expected_impact_json"]), status=str(row["status"]),
        created_by=str(row["created_by"]), created_at=str(row["created_at"]),
    )


def _as_checkpoint(row) -> "SiteMagicCheckpoint":
    return SiteMagicCheckpoint(
        checkpoint_id=str(row["checkpoint_id"]), preview_id=str(row["preview_id"]),
        build_id=str(row["build_id"]), tenant_id=str(row["tenant_id"]),
        artifact_manifest=_decode(row["artifact_manifest_json"]),
        trace_manifest=_decode(row["trace_manifest_json"]),
        quality_report=_decode(row["quality_report_json"]),
        accepted_by=str(row["accepted_by"]), accepted_at=str(row["accepted_at"]),
    )


def _as_release(row) -> "SiteMagicRelease":
    return SiteMagicRelease(
        release_id=str(row["release_id"]), checkpoint_id=str(row["checkpoint_id"]),
        tenant_id=str(row["tenant_id"]), status=str(row["status"]),
        public_locator=row["public_locator"], requested_by=str(row["requested_by"]),
        failure_code=row["failure_code"], created_at=str(row["created_at"]),
        published_at=row["published_at"],
    )


@dataclass(frozen=True)
class SiteMagicFact:
    fact_id: str
    tenant_id: str
    kind: str
    value: Any
    source: dict[str, Any]
    status: str
    verified_by: Optional[str]
    verified_at: Optional[str]
    content_hash: str
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id, "tenant_id": self.tenant_id, "kind": self.kind,
            "value": self.value, "source": self.source, "status": self.status,
            "verified_by": self.verified_by, "verified_at": self.verified_at,
            "content_hash": self.content_hash, "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SiteMagicPlanVersion:
    plan_id: str
    tenant_id: str
    version: int
    content: dict[str, Any]
    fact_snapshot: list[dict[str, Any]]
    plan_hash: str
    fact_snapshot_hash: str
    status: str
    created_by: Optional[str]
    created_at: str

    def public(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id, "tenant_id": self.tenant_id, "version": self.version,
            "content": self.content, "fact_snapshot": self.fact_snapshot,
            "plan_hash": self.plan_hash, "fact_snapshot_hash": self.fact_snapshot_hash,
            "status": self.status, "created_by": self.created_by, "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SiteMagicPlan:
    plan_id: str
    tenant_id: str
    current_version: int
    status: str
    versions: tuple[SiteMagicPlanVersion, ...]
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id, "tenant_id": self.tenant_id,
            "current_version": self.current_version, "status": self.status,
            "versions": [version.public() for version in self.versions],
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SiteMagicApproval:
    approval_id: str
    tenant_id: str
    plan_id: str
    plan_version: int
    plan_hash: str
    fact_snapshot_hash: str
    approved_by: str
    approved_at: str

    def public(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id, "tenant_id": self.tenant_id,
            "plan_id": self.plan_id, "plan_version": self.plan_version,
            "plan_hash": self.plan_hash, "fact_snapshot_hash": self.fact_snapshot_hash,
            "approved_by": self.approved_by, "approved_at": self.approved_at,
        }


@dataclass(frozen=True)
class SiteMagicBuildRequest:
    build_id: str
    tenant_id: str
    approval_id: str
    plan_id: str
    plan_version: int
    plan_hash: str
    fact_snapshot_hash: str
    status: str
    requested_by: str
    created_at: str
    correlation_id: str = ""
    failure_code: Optional[str] = None
    revision_id: Optional[str] = None
    revision_scope: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id, "tenant_id": self.tenant_id,
            "approval_id": self.approval_id, "plan_id": self.plan_id,
            "plan_version": self.plan_version, "plan_hash": self.plan_hash,
            "fact_snapshot_hash": self.fact_snapshot_hash, "status": self.status,
            "requested_by": self.requested_by, "created_at": self.created_at,
            "correlation_id": self.correlation_id,
            "failure_code": self.failure_code,
            "revision_id": self.revision_id,
            "revision_scope": list(self.revision_scope),
        }


@dataclass(frozen=True)
class SiteMagicPreview:
    preview_id: str
    build_id: str
    tenant_id: str
    preview_locator: str
    artifact_manifest: dict[str, Any]
    rendered_evidence: dict[str, Any]
    trace_manifest: dict[str, Any]
    quality_report: dict[str, Any]
    status: str
    created_at: str
    updated_at: str

    def public(self) -> dict[str, Any]:
        return {
            "preview_id": self.preview_id, "build_id": self.build_id,
            "tenant_id": self.tenant_id, "preview_locator": self.preview_locator,
            "artifact_manifest": self.artifact_manifest,
            "rendered_evidence": self.rendered_evidence,
            "trace_manifest": self.trace_manifest,
            "quality_report": self.quality_report, "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SiteMagicRevision:
    revision_id: str
    preview_id: str
    tenant_id: str
    scope: list[str]
    request_text: str
    change_class: str
    expected_impact: dict[str, Any]
    status: str
    created_by: str
    created_at: str

    def public(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id, "preview_id": self.preview_id,
            "tenant_id": self.tenant_id, "scope": self.scope,
            "request_text": self.request_text, "change_class": self.change_class,
            "expected_impact": self.expected_impact, "status": self.status,
            "created_by": self.created_by, "created_at": self.created_at,
            "requires_reapproval": self.change_class == "semantic",
        }


@dataclass(frozen=True)
class SiteMagicCheckpoint:
    checkpoint_id: str
    preview_id: str
    build_id: str
    tenant_id: str
    artifact_manifest: dict[str, Any]
    trace_manifest: dict[str, Any]
    quality_report: dict[str, Any]
    accepted_by: str
    accepted_at: str

    def public(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id, "preview_id": self.preview_id,
            "build_id": self.build_id, "tenant_id": self.tenant_id,
            "artifact_manifest": self.artifact_manifest,
            "trace_manifest": self.trace_manifest,
            "quality_report": self.quality_report,
            "accepted_by": self.accepted_by, "accepted_at": self.accepted_at,
        }


@dataclass(frozen=True)
class SiteMagicRelease:
    release_id: str
    checkpoint_id: str
    tenant_id: str
    status: str
    public_locator: Optional[str]
    requested_by: str
    failure_code: Optional[str]
    created_at: str
    published_at: Optional[str]

    def public(self) -> dict[str, Any]:
        return {
            "release_id": self.release_id, "checkpoint_id": self.checkpoint_id,
            "tenant_id": self.tenant_id, "status": self.status,
            "public_locator": self.public_locator, "requested_by": self.requested_by,
            "failure_code": self.failure_code, "created_at": self.created_at,
            "published_at": self.published_at,
        }


class SiteMagicPublisher(Protocol):
    def publish(
        self, *, tenant_id: str, checkpoint_id: str, artifact_locator: str,
        artifact_manifest: dict[str, Any],
    ) -> str: ...


class NullSiteMagicPublisher:
    def publish(
        self, *, tenant_id: str, checkpoint_id: str, artifact_locator: str,
        artifact_manifest: dict[str, Any],
    ) -> str:
        raise ControlPlaneNotConfiguredError("Site Magic publisher is not configured")


class SiteMagicBuildDispatcher(Protocol):
    def dispatch(self, *, build: SiteMagicBuildRequest) -> None: ...


class NullSiteMagicBuildDispatcher:
    def dispatch(self, *, build: SiteMagicBuildRequest) -> None:
        raise ControlPlaneNotConfiguredError("Site Magic build engine is not configured")


def validate_plan_content(content: dict[str, Any]) -> None:
    """Validate the provider-neutral shape needed by Gate 0."""
    required = {"pages", "claims", "ctas", "imagery_requirements", "visual_direction"}
    missing = sorted(required - set(content))
    if missing:
        raise ControlPlaneValidationError(f"Plan is missing required fields: {', '.join(missing)}")
    if not isinstance(content["pages"], list) or not isinstance(content["claims"], list):
        raise ControlPlaneValidationError("Plan pages and claims must be lists")
    if not isinstance(content["ctas"], list) or not isinstance(content["imagery_requirements"], list):
        raise ControlPlaneValidationError("Plan CTAs and imagery requirements must be lists")
    if not isinstance(content["visual_direction"], (dict, str)):
        raise ControlPlaneValidationError("Plan visual_direction must be an object or string")
    for index, claim in enumerate(content["claims"]):
        if not isinstance(claim, dict):
            raise ControlPlaneValidationError(f"Claim {index} must be an object")
        if not claim.get("claim_id") or not claim.get("text"):
            raise ControlPlaneValidationError(f"Claim {index} needs claim_id and text")
        if claim.get("status") not in {"supported", "omitted", "needs_proof"}:
            raise ControlPlaneValidationError(
                f"Claim {claim.get('claim_id', index)} must be supported, omitted, or needs_proof"
            )
        fact_ids = claim.get("fact_ids", [])
        if not isinstance(fact_ids, list) or any(not isinstance(item, str) for item in fact_ids):
            raise ControlPlaneValidationError(f"Claim {claim.get('claim_id', index)} fact_ids must be a list")
        if claim["status"] == "supported" and not fact_ids:
            raise ControlPlaneValidationError(f"Supported claim {claim['claim_id']} needs fact_ids")
        if claim["status"] != "supported" and fact_ids:
            raise ControlPlaneValidationError(
                f"Non-supported claim {claim['claim_id']} cannot carry supporting fact_ids"
            )


def safe_starter_plan_content(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a provider-neutral, non-publishing starter plan.

    The proposal contains structure and explicit review tasks, not generated
    customer copy. Every fact remains in the plan snapshot for provenance, but
    the generated review items are ``needs_proof`` and therefore cannot render
    as claims until an operator edits and explicitly supports or omits them.
    """
    claims = [
        {
            "claim_id": f"proof-review-{fact['fact_id']}",
            "text": f"Review the verified {fact['kind']} fact before publication.",
            "status": "needs_proof",
            "fact_ids": [],
        }
        for fact in facts
    ]
    content = {
        "pages": [{
            "page_id": "home",
            "title": "Home",
            "sections": [
                {"section_id": "hero", "purpose": "Introduce the business after operator review"},
                {"section_id": "services", "purpose": "Show only supported services"},
                {"section_id": "proof", "purpose": "Show approved evidence or an explicit proof requirement"},
                {"section_id": "contact", "purpose": "Use a verified contact action only"},
            ],
        }],
        "claims": claims,
        "ctas": [],
        "imagery_requirements": [
            {"slot": "hero", "proof_required": False, "notes": "Use editorial imagery without implying a real customer result"},
            {"slot": "proof", "proof_required": True, "notes": "Requires operator-approved evidence or remain omitted"},
        ],
        "visual_direction": {
            "mood": "operator_defined",
            "palette": "operator_defined",
            "notes": "Choose visual direction during Gate 0 review; do not infer brand claims",
        },
    }
    validate_plan_content(content)
    return content


def _plan_section_ids(content: dict[str, Any]) -> set[str]:
    """Return the stable page.section IDs used to bound revision diffs."""
    section_ids: set[str] = set()
    for page in content.get("pages", []):
        if not isinstance(page, dict) or not page.get("page_id"):
            continue
        page_id = str(page["page_id"])
        sections = page.get("sections", [])
        if not sections:
            section_ids.add(page_id)
            continue
        for section in sections:
            if isinstance(section, dict) and section.get("section_id"):
                section_ids.add(f"{page_id}.{section['section_id']}")
    return section_ids


class SiteMagicControlRepository:
    def __init__(self, conn) -> None:
        self._conn = conn

    def _existing_idempotent(self, tenant_id: str, idempotency_key: str) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            "SELECT payload_json FROM site_magic_events WHERE tenant_id = ? AND idempotency_key = ?",
            (tenant_id, idempotency_key),
        ).fetchone()
        return _decode(row["payload_json"]) if row else None

    def _facts(self, tenant_id: str, fact_ids: list[str]) -> list[dict[str, Any]]:
        if not fact_ids:
            return []
        placeholders = ",".join("?" for _ in fact_ids)
        rows = self._conn.execute(
            f"""SELECT fact_id, tenant_id, kind, value_json, source_json, status,
                       verified_by, verified_at, content_hash, created_at, updated_at
                FROM site_magic_facts
                WHERE tenant_id = ? AND fact_id IN ({placeholders})""",
            (tenant_id, *fact_ids),
        ).fetchall()
        by_id = {str(row["fact_id"]): _as_fact(row).public() for row in rows}
        if set(by_id) != set(fact_ids):
            raise ControlPlaneValidationError("Plan references a missing fact")
        return [by_id[fact_id] for fact_id in fact_ids]

    def _append_event(
        self,
        *,
        tenant_id: str,
        aggregate_type: str,
        aggregate_id: str,
        aggregate_version: int,
        event_type: str,
        actor_type: str,
        actor_id: Optional[str],
        correlation_id: str,
        idempotency_key: str,
        payload: dict[str, Any],
        causation_id: Optional[str] = None,
    ) -> dict[str, Any]:
        existing = self._existing_idempotent(tenant_id, idempotency_key)
        if existing is not None:
            return existing
        prior = self._conn.execute(
            """SELECT aggregate_sequence, event_hash FROM site_magic_events
               WHERE tenant_id = ? AND aggregate_type = ? AND aggregate_id = ?
               ORDER BY aggregate_sequence DESC LIMIT 1""",
            (tenant_id, aggregate_type, aggregate_id),
        ).fetchone()
        sequence = int(prior["aggregate_sequence"]) + 1 if prior else 1
        previous_hash = prior["event_hash"] if prior else None
        event_id = str(uuid.uuid4())
        occurred_at = _now()
        unsigned = {
            "event_id": event_id, "tenant_id": tenant_id, "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id, "aggregate_version": aggregate_version,
            "aggregate_sequence": sequence, "event_type": event_type,
            "occurred_at": occurred_at, "actor_type": actor_type, "actor_id": actor_id,
            "correlation_id": correlation_id, "causation_id": causation_id,
            "idempotency_key": idempotency_key, "payload_schema_version": 1,
            "payload": payload, "prev_event_hash": previous_hash,
        }
        event_hash = _hash(unsigned)
        self._conn.execute(
            """INSERT INTO site_magic_events (
                event_id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
                aggregate_sequence, event_type, occurred_at, actor_type, actor_id,
                correlation_id, causation_id, idempotency_key, payload_schema_version,
                payload_json, prev_event_hash, event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)""",
            (
                event_id, tenant_id, aggregate_type, aggregate_id, aggregate_version,
                sequence, event_type, occurred_at, actor_type, actor_id, correlation_id,
                causation_id, idempotency_key, _json(payload), previous_hash, event_hash,
            ),
        )
        return {**payload, "event_id": event_id, "event_hash": event_hash}

    def create_fact(
        self, *, tenant_id: str, kind: str, value: Any, source: dict[str, Any],
        actor_id: str, correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicFact, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            fact = self.get_fact(tenant_id=tenant_id, fact_id=replay["fact_id"])
            if fact is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing fact")
            return fact, True
        if not kind or not isinstance(source, dict) or not source.get("type"):
            raise ControlPlaneValidationError("Fact kind and source.type are required")
        fact_id = str(uuid.uuid4())
        now = _now()
        content_hash = _hash({"kind": kind, "value": value, "source": source})
        self._conn.execute(
            """INSERT INTO site_magic_facts (
                fact_id, tenant_id, kind, value_json, source_json, status,
                content_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'unverified', ?, ?, ?)""",
            (fact_id, tenant_id, kind, _json(value), _json(source), content_hash, now, now),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="fact", aggregate_id=fact_id,
            aggregate_version=1, event_type="fact_imported", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"fact_id": fact_id, "content_hash": content_hash},
        )
        return self.get_fact(tenant_id=tenant_id, fact_id=fact_id), False

    def get_fact(self, *, tenant_id: str, fact_id: str) -> Optional[SiteMagicFact]:
        row = self._conn.execute(
            """SELECT fact_id, tenant_id, kind, value_json, source_json, status,
                       verified_by, verified_at, content_hash, created_at, updated_at
                FROM site_magic_facts WHERE tenant_id = ? AND fact_id = ?""",
            (tenant_id, fact_id),
        ).fetchone()
        return _as_fact(row) if row else None

    def list_facts(self, *, tenant_id: str) -> list[SiteMagicFact]:
        rows = self._conn.execute(
            """SELECT fact_id, tenant_id, kind, value_json, source_json, status,
                       verified_by, verified_at, content_hash, created_at, updated_at
                FROM site_magic_facts WHERE tenant_id = ? ORDER BY created_at, fact_id""",
            (tenant_id,),
        ).fetchall()
        return [_as_fact(row) for row in rows]

    def verify_fact(
        self, *, tenant_id: str, fact_id: str, actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicFact, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            fact = self.get_fact(tenant_id=tenant_id, fact_id=replay["fact_id"])
            if fact is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing fact")
            return fact, True
        fact = self.get_fact(tenant_id=tenant_id, fact_id=fact_id)
        if fact is None:
            raise ControlPlaneNotFoundError(fact_id)
        if fact.status == "rejected":
            raise ControlPlaneConflictError("Rejected facts cannot be verified")
        now = _now()
        self._conn.execute(
            """UPDATE site_magic_facts SET status = 'verified', verified_by = ?,
               verified_at = ?, updated_at = ? WHERE tenant_id = ? AND fact_id = ?""",
            (actor_id, now, now, tenant_id, fact_id),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="fact", aggregate_id=fact_id,
            aggregate_version=2, event_type="fact_verified", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"fact_id": fact_id, "content_hash": fact.content_hash},
        )
        return self.get_fact(tenant_id=tenant_id, fact_id=fact_id), False

    def _plan_version(self, *, tenant_id: str, plan_id: str, version: int) -> Optional[SiteMagicPlanVersion]:
        row = self._conn.execute(
            """SELECT plan_id, tenant_id, version, content_json, fact_snapshot_json,
                       plan_hash, fact_snapshot_hash, status, created_by, created_at
                FROM site_magic_plan_versions
                WHERE tenant_id = ? AND plan_id = ? AND version = ?""",
            (tenant_id, plan_id, version),
        ).fetchone()
        if not row:
            return None
        return SiteMagicPlanVersion(
            plan_id=str(row["plan_id"]), tenant_id=str(row["tenant_id"]), version=int(row["version"]),
            content=_decode(row["content_json"]), fact_snapshot=_decode(row["fact_snapshot_json"]),
            plan_hash=str(row["plan_hash"]), fact_snapshot_hash=str(row["fact_snapshot_hash"]),
            status=str(row["status"]), created_by=row["created_by"], created_at=str(row["created_at"]),
        )

    def create_plan(
        self, *, tenant_id: str, fact_ids: list[str], content: dict[str, Any],
        actor_id: str, correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicPlan, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            plan = self.get_plan(tenant_id=tenant_id, plan_id=replay["plan_id"])
            if plan is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing plan")
            return plan, True
        validate_plan_content(content)
        facts = self._facts(tenant_id, fact_ids)
        fact_snapshot = [
            {"fact_id": fact["fact_id"], "content_hash": fact["content_hash"], "status": fact["status"]}
            for fact in facts
        ]
        plan_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO site_magic_plans
               (plan_id, tenant_id, current_version, status, created_at, updated_at)
               VALUES (?, ?, 1, 'proposed', ?, ?)""",
            (plan_id, tenant_id, now, now),
        )
        self._conn.execute(
            """INSERT INTO site_magic_plan_versions (
                plan_version_id, plan_id, tenant_id, version, content_json,
                fact_snapshot_json, plan_hash, fact_snapshot_hash, status,
                created_by, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'proposed', ?, ?)""",
            (
                version_id, plan_id, tenant_id, _json(content), _json(fact_snapshot),
                _hash(content), _fact_snapshot_hash(facts), actor_id, now,
            ),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="plan", aggregate_id=plan_id,
            aggregate_version=1, event_type="plan_proposed", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"plan_id": plan_id, "version": 1, "plan_hash": _hash(content)},
        )
        return self.get_plan(tenant_id=tenant_id, plan_id=plan_id), False

    def propose_plan(
        self, *, tenant_id: str, fact_ids: list[str], actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicPlan, bool]:
        """Create a safe editable proposal from a selected fact snapshot."""
        facts = self._facts(tenant_id, fact_ids)
        return self.create_plan(
            tenant_id=tenant_id, fact_ids=fact_ids,
            content=safe_starter_plan_content(facts), actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
        )

    def patch_plan(
        self, *, tenant_id: str, plan_id: str, base_version: int, fact_ids: list[str],
        content: dict[str, Any], actor_id: str, correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicPlan, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            plan = self.get_plan(tenant_id=tenant_id, plan_id=replay["plan_id"])
            if plan is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing plan")
            return plan, True
        validate_plan_content(content)
        current = self.get_plan(tenant_id=tenant_id, plan_id=plan_id)
        if current is None:
            raise ControlPlaneNotFoundError(plan_id)
        if current.current_version != base_version:
            raise ControlPlaneConflictError("Plan changed; refresh before editing")
        facts = self._facts(tenant_id, fact_ids)
        fact_snapshot = [
            {"fact_id": fact["fact_id"], "content_hash": fact["content_hash"], "status": fact["status"]}
            for fact in facts
        ]
        next_version = current.current_version + 1
        now = _now()
        self._conn.execute(
            """UPDATE site_magic_plan_versions SET status = 'superseded'
               WHERE tenant_id = ? AND plan_id = ? AND version = ?""",
            (tenant_id, plan_id, base_version),
        )
        self._conn.execute(
            """INSERT INTO site_magic_plan_versions (
                plan_version_id, plan_id, tenant_id, version, content_json,
                fact_snapshot_json, plan_hash, fact_snapshot_hash, status,
                created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposed', ?, ?)""",
            (
                str(uuid.uuid4()), plan_id, tenant_id, next_version, _json(content),
                _json(fact_snapshot), _hash(content), _fact_snapshot_hash(facts), actor_id, now,
            ),
        )
        self._conn.execute(
            """UPDATE site_magic_plans SET current_version = ?, status = 'proposed', updated_at = ?
               WHERE tenant_id = ? AND plan_id = ?""",
            (next_version, now, tenant_id, plan_id),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="plan", aggregate_id=plan_id,
            aggregate_version=next_version, event_type="plan_version_created", actor_type="user",
            actor_id=actor_id, correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"plan_id": plan_id, "version": next_version, "plan_hash": _hash(content)},
        )
        return self.get_plan(tenant_id=tenant_id, plan_id=plan_id), False

    def get_plan(self, *, tenant_id: str, plan_id: str) -> Optional[SiteMagicPlan]:
        row = self._conn.execute(
            """SELECT plan_id, tenant_id, current_version, status, created_at, updated_at
               FROM site_magic_plans WHERE tenant_id = ? AND plan_id = ?""",
            (tenant_id, plan_id),
        ).fetchone()
        if not row:
            return None
        versions = self._conn.execute(
            """SELECT plan_id, tenant_id, version, content_json, fact_snapshot_json,
                      plan_hash, fact_snapshot_hash, status, created_by, created_at
               FROM site_magic_plan_versions WHERE tenant_id = ? AND plan_id = ?
               ORDER BY version""",
            (tenant_id, plan_id),
        ).fetchall()
        return SiteMagicPlan(
            plan_id=str(row["plan_id"]), tenant_id=str(row["tenant_id"]),
            current_version=int(row["current_version"]), status=str(row["status"]),
            versions=tuple(
                SiteMagicPlanVersion(
                    plan_id=str(version["plan_id"]), tenant_id=str(version["tenant_id"]),
                    version=int(version["version"]), content=_decode(version["content_json"]),
                    fact_snapshot=_decode(version["fact_snapshot_json"]),
                    plan_hash=str(version["plan_hash"]),
                    fact_snapshot_hash=str(version["fact_snapshot_hash"]),
                    status=str(version["status"]), created_by=version["created_by"],
                    created_at=str(version["created_at"]),
                ) for version in versions
            ),
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
        )

    def list_plans(self, *, tenant_id: str) -> list[SiteMagicPlan]:
        rows = self._conn.execute(
            """SELECT plan_id FROM site_magic_plans
               WHERE tenant_id = ? ORDER BY updated_at DESC, plan_id DESC""",
            (tenant_id,),
        ).fetchall()
        plans = []
        for row in rows:
            plan = self.get_plan(tenant_id=tenant_id, plan_id=str(row["plan_id"]))
            if plan is not None:
                plans.append(plan)
        return plans

    def approve_plan(
        self, *, tenant_id: str, plan_id: str, version: int, actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicApproval, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            approval = self.get_approval(tenant_id=tenant_id, approval_id=replay["approval_id"])
            if approval is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing approval")
            return approval, True
        plan = self.get_plan(tenant_id=tenant_id, plan_id=plan_id)
        plan_version = self._plan_version(tenant_id=tenant_id, plan_id=plan_id, version=version)
        if plan is None or plan_version is None:
            raise ControlPlaneNotFoundError(plan_id)
        if plan.current_version != version:
            raise ControlPlaneConflictError("Only the current plan version can be approved")
        if plan_version.status not in {"draft", "proposed"}:
            raise ControlPlaneConflictError("Plan version is not awaiting approval")
        facts = self._facts(tenant_id, [item["fact_id"] for item in plan_version.fact_snapshot])
        if any(fact["status"] != "verified" for fact in facts):
            raise ControlPlaneConflictError("All plan facts must be verified before approval")
        current_snapshot_hash = _fact_snapshot_hash(facts)
        if current_snapshot_hash != plan_version.fact_snapshot_hash:
            raise ControlPlaneConflictError("Fact snapshot changed; create a new plan version")
        validate_plan_content(plan_version.content)
        fact_by_id = {fact["fact_id"]: fact for fact in facts}
        for claim in plan_version.content["claims"]:
            if claim["status"] == "supported" and any(
                fact_by_id.get(fact_id, {}).get("status") != "verified" for fact_id in claim["fact_ids"]
            ):
                raise ControlPlaneConflictError(f"Claim {claim['claim_id']} is not supported by verified facts")
        existing = self._conn.execute(
            "SELECT approval_id FROM site_magic_approvals WHERE tenant_id = ? AND plan_id = ? AND plan_version = ?",
            (tenant_id, plan_id, version),
        ).fetchone()
        if existing:
            raise ControlPlaneConflictError("This plan version already has an approval")
        approval_id = str(uuid.uuid4())
        approved_at = _now()
        self._conn.execute(
            """INSERT INTO site_magic_approvals (
                approval_id, tenant_id, plan_id, plan_version, plan_hash,
                fact_snapshot_hash, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                approval_id, tenant_id, plan_id, version, plan_version.plan_hash,
                plan_version.fact_snapshot_hash, actor_id, approved_at,
            ),
        )
        self._conn.execute(
            """UPDATE site_magic_plan_versions SET status = 'approved'
               WHERE tenant_id = ? AND plan_id = ? AND version = ?""",
            (tenant_id, plan_id, version),
        )
        self._conn.execute(
            """UPDATE site_magic_plans SET status = 'approved', updated_at = ?
               WHERE tenant_id = ? AND plan_id = ?""",
            (approved_at, tenant_id, plan_id),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="plan", aggregate_id=plan_id,
            aggregate_version=version, event_type="plan_approved", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={
                "approval_id": approval_id, "plan_id": plan_id, "plan_version": version,
                "plan_hash": plan_version.plan_hash, "fact_snapshot_hash": plan_version.fact_snapshot_hash,
            },
        )
        return self.get_approval(tenant_id=tenant_id, approval_id=approval_id), False

    def get_approval(self, *, tenant_id: str, approval_id: str) -> Optional[SiteMagicApproval]:
        row = self._conn.execute(
            """SELECT approval_id, tenant_id, plan_id, plan_version, plan_hash,
                      fact_snapshot_hash, approved_by, approved_at
               FROM site_magic_approvals WHERE tenant_id = ? AND approval_id = ?""",
            (tenant_id, approval_id),
        ).fetchone()
        if not row:
            return None
        return SiteMagicApproval(
            approval_id=str(row["approval_id"]), tenant_id=str(row["tenant_id"]),
            plan_id=str(row["plan_id"]), plan_version=int(row["plan_version"]),
            plan_hash=str(row["plan_hash"]), fact_snapshot_hash=str(row["fact_snapshot_hash"]),
            approved_by=str(row["approved_by"]), approved_at=str(row["approved_at"]),
        )

    def request_build(
        self, *, tenant_id: str, approval_id: str, plan_version: int, actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicBuildRequest, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            build = self.get_build(tenant_id=tenant_id, build_id=replay["build_id"])
            if build is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing build")
            return build, True
        approval = self.get_approval(tenant_id=tenant_id, approval_id=approval_id)
        if approval is None:
            raise ControlPlaneNotFoundError(approval_id)
        if approval.plan_version != plan_version:
            raise ControlPlaneConflictError("Build version does not match the approval")
        plan_version_row = self._plan_version(
            tenant_id=tenant_id, plan_id=approval.plan_id, version=approval.plan_version
        )
        if plan_version_row is None or plan_version_row.status != "approved":
            raise ControlPlaneConflictError("Build requires an approved current plan version")
        build_id = self._create_build(
            tenant_id=tenant_id, approval=approval, actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
        )
        return self.get_build(tenant_id=tenant_id, build_id=build_id), False

    def _create_build(
        self, *, tenant_id: str, approval: SiteMagicApproval, actor_id: str,
        correlation_id: str, idempotency_key: str, revision_id: Optional[str] = None,
        revision_scope: Optional[list[str]] = None,
    ) -> str:
        build_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO site_magic_build_requests (
                build_id, tenant_id, approval_id, plan_id, plan_version,
                plan_hash, fact_snapshot_hash, status, requested_by, created_at, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?, ?)""",
            (
                build_id, tenant_id, approval.approval_id, approval.plan_id, approval.plan_version,
                approval.plan_hash, approval.fact_snapshot_hash, actor_id, now, correlation_id,
            ),
        )
        if revision_id is not None:
            self._conn.execute(
                """INSERT INTO site_magic_revision_builds
                   (revision_id, build_id, tenant_id, scope_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (revision_id, build_id, tenant_id, _json(revision_scope or []), now),
            )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="build", aggregate_id=build_id,
            aggregate_version=1, event_type="build_requested", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={
                "build_id": build_id, "approval_id": approval.approval_id,
                "plan_id": approval.plan_id, "plan_version": approval.plan_version,
                "plan_hash": approval.plan_hash, "fact_snapshot_hash": approval.fact_snapshot_hash,
                "revision_id": revision_id, "revision_scope": revision_scope or [],
            },
        )
        return build_id

    def get_build(self, *, tenant_id: str, build_id: str) -> Optional[SiteMagicBuildRequest]:
        row = self._conn.execute(
            """SELECT b.build_id, b.tenant_id, b.approval_id, b.plan_id, b.plan_version,
                      b.plan_hash, b.fact_snapshot_hash, b.status, b.requested_by, b.created_at,
                      b.correlation_id, b.failure_code,
                      rb.revision_id, rb.scope_json AS revision_scope_json
               FROM site_magic_build_requests b
               LEFT JOIN site_magic_revision_builds rb
                 ON rb.tenant_id = b.tenant_id AND rb.build_id = b.build_id
               WHERE b.tenant_id = ? AND b.build_id = ?""",
            (tenant_id, build_id),
        ).fetchone()
        if not row:
            return None
        return SiteMagicBuildRequest(
            build_id=str(row["build_id"]), tenant_id=str(row["tenant_id"]),
            approval_id=str(row["approval_id"]), plan_id=str(row["plan_id"]),
            plan_version=int(row["plan_version"]), plan_hash=str(row["plan_hash"]),
            fact_snapshot_hash=str(row["fact_snapshot_hash"]), status=str(row["status"]),
            requested_by=str(row["requested_by"]), created_at=str(row["created_at"]),
            correlation_id=str(row["correlation_id"] or ""),
            failure_code=row["failure_code"],
            revision_id=row["revision_id"],
            revision_scope=tuple(_decode(row["revision_scope_json"]) or []),
        )

    def apply_revision(
        self, *, tenant_id: str, revision_id: str, actor_id: str,
        correlation_id: str, idempotency_key: str, approval_id: Optional[str] = None,
        plan_version: Optional[int] = None,
    ) -> tuple[SiteMagicBuildRequest, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            build = self.get_build(tenant_id=tenant_id, build_id=replay.get("build_id", ""))
            if build is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing revision build")
            return build, True
        revision = self.get_revision(tenant_id=tenant_id, revision_id=revision_id)
        if revision is None:
            raise ControlPlaneNotFoundError(revision_id)
        if revision.status != "requested":
            raise ControlPlaneConflictError("Revision is no longer awaiting application")
        preview = self.get_preview(tenant_id=tenant_id, preview_id=revision.preview_id)
        if preview is None:
            raise ControlPlaneNotFoundError(revision.preview_id)
        if preview.status != "ready":
            raise ControlPlaneConflictError("Revisions require a ready source preview")
        source_build = self.get_build(tenant_id=tenant_id, build_id=preview.build_id)
        if source_build is None:
            raise ControlPlaneNotFoundError(preview.build_id)
        if revision.change_class == "presentation":
            if approval_id is not None or plan_version is not None:
                raise ControlPlaneConflictError("Presentation revisions must reuse their approved plan")
            approval = self.get_approval(tenant_id=tenant_id, approval_id=source_build.approval_id)
        else:
            if not approval_id or plan_version is None:
                raise ControlPlaneConflictError("Semantic revisions require a new approved plan version")
            if approval_id == source_build.approval_id:
                raise ControlPlaneConflictError("Semantic revisions cannot reuse the source approval")
            approval = self.get_approval(tenant_id=tenant_id, approval_id=approval_id)
            if approval is None or approval.plan_version != plan_version:
                raise ControlPlaneConflictError("Revision build version does not match the approval")
            if approval.plan_id != source_build.plan_id or approval.plan_version <= source_build.plan_version:
                raise ControlPlaneConflictError("Semantic revisions require a successor version of the source plan")
        if approval is None:
            raise ControlPlaneNotFoundError("revision approval")
        build_id = self._create_build(
            tenant_id=tenant_id, approval=approval, actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=f"{idempotency_key}:build",
            revision_id=revision_id, revision_scope=revision.scope,
        )
        updated = self._conn.execute(
            """UPDATE site_magic_revisions SET status = 'applied'
               WHERE tenant_id = ? AND revision_id = ? AND status = 'requested'""",
            (tenant_id, revision_id),
        ).rowcount
        if updated != 1:
            raise ControlPlaneConflictError("Revision was applied concurrently")
        self._append_event(
            tenant_id=tenant_id, aggregate_type="revision", aggregate_id=revision_id,
            aggregate_version=2, event_type="revision_applied", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={
                "revision_id": revision_id, "preview_id": revision.preview_id,
                "build_id": build_id, "approval_id": approval.approval_id,
                "plan_version": approval.plan_version,
            },
        )
        return self.get_build(tenant_id=tenant_id, build_id=build_id), False

    def get_build_source(self, *, tenant_id: str, build_id: str) -> dict[str, Any]:
        """Return the exact approved source needed by a build engine."""
        build = self.get_build(tenant_id=tenant_id, build_id=build_id)
        if build is None:
            raise ControlPlaneNotFoundError(build_id)
        if build.status not in {"requested", "started"}:
            raise ControlPlaneConflictError("Build source is no longer available for execution")
        approval = self.get_approval(tenant_id=tenant_id, approval_id=build.approval_id)
        plan = self._plan_version(
            tenant_id=tenant_id, plan_id=build.plan_id, version=build.plan_version
        )
        if approval is None or plan is None or plan.status != "approved":
            raise ControlPlaneConflictError("Build source no longer matches an approved plan")
        if approval.plan_hash != build.plan_hash or approval.plan_hash != plan.plan_hash:
            raise ControlPlaneConflictError("Build source plan hash does not match the approval")
        if approval.fact_snapshot_hash != build.fact_snapshot_hash or approval.fact_snapshot_hash != plan.fact_snapshot_hash:
            raise ControlPlaneConflictError("Build source fact snapshot does not match the approval")
        fact_ids = [item["fact_id"] for item in plan.fact_snapshot]
        facts = self._facts(tenant_id, fact_ids)
        if _fact_snapshot_hash(facts) != build.fact_snapshot_hash:
            raise ControlPlaneConflictError("Build source facts changed after approval")
        return {
            "build": build.public(),
            "approval": approval.public(),
            "plan": plan.public(),
            "facts": facts,
        }

    def fail_build(
        self, *, tenant_id: str, build_id: str, failure_code: str,
        actor_id: Optional[str], correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicBuildRequest, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            build = self.get_build(tenant_id=tenant_id, build_id=replay.get("build_id", ""))
            if build is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing build")
            return build, True
        if not failure_code.strip():
            raise ControlPlaneValidationError("Build failure_code is required")
        build = self.get_build(tenant_id=tenant_id, build_id=build_id)
        if build is None:
            raise ControlPlaneNotFoundError(build_id)
        if build.status == "failed":
            raise ControlPlaneConflictError("Build is already failed")
        if build.status not in {"requested", "started"}:
            raise ControlPlaneConflictError("Build is no longer failing")
        bounded_code = failure_code.strip()[:128]
        updated = self._conn.execute(
            """UPDATE site_magic_build_requests
               SET status = 'failed', failure_code = ?
               WHERE tenant_id = ? AND build_id = ? AND status IN ('requested', 'started')""",
            (bounded_code, tenant_id, build_id),
        ).rowcount
        if updated != 1:
            raise ControlPlaneConflictError("Build failed concurrently")
        self._append_event(
            tenant_id=tenant_id, aggregate_type="build", aggregate_id=build_id,
            aggregate_version=2, event_type="build_failed", actor_type="build_engine",
            actor_id=actor_id, correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"build_id": build_id, "failure_code": bounded_code},
        )
        return self.get_build(tenant_id=tenant_id, build_id=build_id), False

    def create_preview(
        self, *, tenant_id: str, build_id: str, preview_locator: str,
        artifact_manifest: dict[str, Any], rendered_evidence: dict[str, Any],
        trace_manifest: dict[str, Any], quality_report: dict[str, Any],
        actor_type: str, actor_id: Optional[str], correlation_id: str,
        idempotency_key: str,
    ) -> tuple[SiteMagicPreview, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            preview = self.get_preview(tenant_id=tenant_id, preview_id=replay["preview_id"])
            if preview is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing preview")
            return preview, True
        build = self.get_build(tenant_id=tenant_id, build_id=build_id)
        if build is None:
            raise ControlPlaneNotFoundError(build_id)
        if build.status not in {"requested", "started"}:
            raise ControlPlaneConflictError("Build is not accepting preview evidence")
        if not isinstance(artifact_manifest, dict):
            raise ControlPlaneValidationError("Preview locator and artifact manifest are required")
        _validate_tenant_locator(tenant_id, preview_locator, "Preview")
        _validate_tenant_locator(tenant_id, artifact_manifest.get("locator"), "Artifact")
        if not isinstance(rendered_evidence, dict) or not isinstance(trace_manifest, dict):
            raise ControlPlaneValidationError("Rendered evidence and trace manifest must be objects")
        if trace_manifest.get("plan_hash") != build.plan_hash:
            raise ControlPlaneConflictError("Preview trace does not match the approved plan")
        if trace_manifest.get("fact_snapshot_hash") != build.fact_snapshot_hash:
            raise ControlPlaneConflictError("Preview trace does not match the approved facts")
        approved_plan = self._plan_version(
            tenant_id=tenant_id, plan_id=build.plan_id, version=build.plan_version
        )
        if approved_plan is None or approved_plan.status != "approved":
            raise ControlPlaneConflictError("Preview trace does not match an approved plan version")
        approved_fact_ids = {item["fact_id"] for item in approved_plan.fact_snapshot}
        approved_claims = {
            claim["claim_id"]: claim for claim in approved_plan.content.get("claims", [])
        }
        artifacts = trace_manifest.get("artifacts")
        if not isinstance(artifacts, list):
            raise ControlPlaneValidationError("Preview trace must include an artifacts list")
        for artifact in artifacts:
            if not isinstance(artifact, dict) or not artifact.get("artifact_id"):
                raise ControlPlaneValidationError("Every traced artifact needs an artifact_id")
            fact_ids = artifact.get("fact_ids", [])
            if not isinstance(fact_ids, list):
                raise ControlPlaneValidationError("Every traced artifact fact_ids must be a list")
            if any(fact_id not in approved_fact_ids for fact_id in fact_ids):
                raise ControlPlaneConflictError("Artifact trace references a fact outside the approved snapshot")
            claim_ids = artifact.get("claim_ids", [])
            if not isinstance(claim_ids, list):
                raise ControlPlaneValidationError("Every traced artifact claim_ids must be a list")
            if any(
                claim_id not in approved_claims or approved_claims[claim_id]["status"] != "supported"
                for claim_id in claim_ids
            ):
                raise ControlPlaneConflictError("Artifact trace references an unsupported or missing claim")
        if build.revision_id:
            revision = self.get_revision(tenant_id=tenant_id, revision_id=build.revision_id)
            if revision is None:
                raise ControlPlaneConflictError("Preview build references a missing revision")
            if trace_manifest.get("revision_id") != build.revision_id:
                raise ControlPlaneConflictError("Preview trace does not identify the applied revision")
            changed_scope = trace_manifest.get("changed_scope")
            unchanged_scope = trace_manifest.get("unchanged_scope")
            if not isinstance(changed_scope, list) or not isinstance(unchanged_scope, list):
                raise ControlPlaneValidationError(
                    "Revision preview trace must include changed_scope and unchanged_scope lists"
                )
            if any(not isinstance(item, str) for item in changed_scope + unchanged_scope):
                raise ControlPlaneValidationError("Revision scope entries must be strings")
            if any(item not in revision.scope for item in changed_scope):
                raise ControlPlaneConflictError("Revision trace changed a section outside its bounded scope")
            if set(changed_scope).intersection(unchanged_scope):
                raise ControlPlaneConflictError("Revision trace cannot mark a section changed and unchanged")
            known_sections = _plan_section_ids(approved_plan.content)
            if not known_sections.issubset(set(changed_scope).union(unchanged_scope)):
                raise ControlPlaneConflictError("Revision trace does not account for every plan section")
        if not isinstance(quality_report, dict):
            raise ControlPlaneValidationError("Quality report must be an object")
        preview_id = str(uuid.uuid4())
        now = _now()
        status = "ready" if quality_gates_pass(quality_report) else "blocked"
        self._conn.execute(
            """INSERT INTO site_magic_previews (
                preview_id, build_id, tenant_id, preview_locator, artifact_manifest_json,
                rendered_evidence_json, trace_manifest_json, quality_report_json,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                preview_id, build_id, tenant_id, preview_locator, _json(artifact_manifest),
                _json(rendered_evidence), _json(trace_manifest), _json(quality_report),
                status, now, now,
            ),
        )
        if build.status == "requested":
            self._append_event(
                tenant_id=tenant_id, aggregate_type="build", aggregate_id=build_id,
                aggregate_version=1, event_type="build_started", actor_type=actor_type, actor_id=actor_id,
                correlation_id=correlation_id, idempotency_key=f"{idempotency_key}:started",
                payload={"build_id": build_id},
            )
        self._conn.execute(
            "UPDATE site_magic_build_requests SET status = ?, created_at = created_at WHERE tenant_id = ? AND build_id = ?",
            ("preview_ready" if status == "ready" else "blocked", tenant_id, build_id),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="preview", aggregate_id=preview_id,
            aggregate_version=1, event_type="preview_ready" if status == "ready" else "preview_blocked",
            actor_type=actor_type, actor_id=actor_id, correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            payload={"preview_id": preview_id, "build_id": build_id, "status": status},
        )
        return self.get_preview(tenant_id=tenant_id, preview_id=preview_id), False

    def get_preview(self, *, tenant_id: str, preview_id: str) -> Optional[SiteMagicPreview]:
        row = self._conn.execute(
            """SELECT preview_id, build_id, tenant_id, preview_locator,
                      artifact_manifest_json, rendered_evidence_json,
                      trace_manifest_json, quality_report_json, status,
                      created_at, updated_at
               FROM site_magic_previews WHERE tenant_id = ? AND preview_id = ?""",
            (tenant_id, preview_id),
        ).fetchone()
        return _as_preview(row) if row else None

    def request_revision(
        self, *, tenant_id: str, preview_id: str, scope: list[str], request_text: str,
        change_class: str, expected_impact: dict[str, Any], actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicRevision, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            revision = self.get_revision(tenant_id=tenant_id, revision_id=replay["revision_id"])
            if revision is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing revision")
            return revision, True
        preview = self.get_preview(tenant_id=tenant_id, preview_id=preview_id)
        if preview is None:
            raise ControlPlaneNotFoundError(preview_id)
        if preview.status != "ready":
            raise ControlPlaneConflictError("Revisions require a ready preview")
        if not scope or len(scope) != len(set(scope)) or any(not item.strip() for item in scope):
            raise ControlPlaneValidationError("Revision scope must contain unique non-empty section IDs")
        if change_class not in {"presentation", "semantic"}:
            raise ControlPlaneValidationError("Revision change_class must be presentation or semantic")
        if not request_text.strip() or not isinstance(expected_impact, dict):
            raise ControlPlaneValidationError("Revision request and expected impact are required")
        source_build = self.get_build(tenant_id=tenant_id, build_id=preview.build_id)
        if source_build is None:
            raise ControlPlaneNotFoundError(preview.build_id)
        source_plan = self._plan_version(
            tenant_id=tenant_id, plan_id=source_build.plan_id, version=source_build.plan_version
        )
        known_sections = _plan_section_ids(source_plan.content) if source_plan else set()
        if known_sections and any(item not in known_sections for item in scope):
            raise ControlPlaneValidationError("Revision scope must reference sections in the source plan")
        revision_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO site_magic_revisions (
                revision_id, preview_id, tenant_id, scope_json, request_text,
                change_class, expected_impact_json, status, created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?)""",
            (
                revision_id, preview_id, tenant_id, _json(scope), request_text.strip(),
                change_class, _json(expected_impact), actor_id, now,
            ),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="revision", aggregate_id=revision_id,
            aggregate_version=1, event_type="revision_requested", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={
                "revision_id": revision_id, "preview_id": preview_id,
                "scope": scope, "change_class": change_class,
            },
        )
        return self.get_revision(tenant_id=tenant_id, revision_id=revision_id), False

    def get_revision(self, *, tenant_id: str, revision_id: str) -> Optional[SiteMagicRevision]:
        row = self._conn.execute(
            """SELECT revision_id, preview_id, tenant_id, scope_json, request_text,
                      change_class, expected_impact_json, status, created_by, created_at
               FROM site_magic_revisions WHERE tenant_id = ? AND revision_id = ?""",
            (tenant_id, revision_id),
        ).fetchone()
        return _as_revision(row) if row else None

    def accept_checkpoint(
        self, *, tenant_id: str, preview_id: str, actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicCheckpoint, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            checkpoint = self.get_checkpoint(tenant_id=tenant_id, checkpoint_id=replay["checkpoint_id"])
            if checkpoint is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing checkpoint")
            return checkpoint, True
        preview = self.get_preview(tenant_id=tenant_id, preview_id=preview_id)
        if preview is None:
            raise ControlPlaneNotFoundError(preview_id)
        if preview.status != "ready" or not quality_gates_pass(preview.quality_report):
            raise ControlPlaneConflictError("Only a preview that passed rendered-site gates can be checkpointed")
        existing = self._conn.execute(
            "SELECT checkpoint_id FROM site_magic_checkpoints WHERE tenant_id = ? AND preview_id = ?",
            (tenant_id, preview_id),
        ).fetchone()
        if existing:
            raise ControlPlaneConflictError("Preview already has a checkpoint")
        checkpoint_id = str(uuid.uuid4())
        accepted_at = _now()
        self._conn.execute(
            """INSERT INTO site_magic_checkpoints (
                checkpoint_id, preview_id, build_id, tenant_id, artifact_manifest_json,
                trace_manifest_json, quality_report_json, accepted_by, accepted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                checkpoint_id, preview_id, preview.build_id, tenant_id,
                _json(preview.artifact_manifest), _json(preview.trace_manifest),
                _json(preview.quality_report), actor_id, accepted_at,
            ),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="checkpoint", aggregate_id=checkpoint_id,
            aggregate_version=1, event_type="checkpoint_accepted", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"checkpoint_id": checkpoint_id, "preview_id": preview_id, "build_id": preview.build_id},
        )
        return self.get_checkpoint(tenant_id=tenant_id, checkpoint_id=checkpoint_id), False

    def get_checkpoint(self, *, tenant_id: str, checkpoint_id: str) -> Optional[SiteMagicCheckpoint]:
        row = self._conn.execute(
            """SELECT checkpoint_id, preview_id, build_id, tenant_id,
                      artifact_manifest_json, trace_manifest_json,
                      quality_report_json, accepted_by, accepted_at
               FROM site_magic_checkpoints WHERE tenant_id = ? AND checkpoint_id = ?""",
            (tenant_id, checkpoint_id),
        ).fetchone()
        return _as_checkpoint(row) if row else None

    def request_release(
        self, *, tenant_id: str, checkpoint_id: str, actor_id: str,
        correlation_id: str, idempotency_key: str,
    ) -> tuple[SiteMagicRelease, bool]:
        replay = self._existing_idempotent(tenant_id, idempotency_key)
        if replay:
            release = self.get_release(tenant_id=tenant_id, release_id=replay["release_id"])
            if release is None:
                raise ControlPlaneConflictError("Idempotency record points to a missing release")
            return release, True
        checkpoint = self.get_checkpoint(tenant_id=tenant_id, checkpoint_id=checkpoint_id)
        if checkpoint is None:
            raise ControlPlaneNotFoundError(checkpoint_id)
        release_id = str(uuid.uuid4())
        now = _now()
        self._conn.execute(
            """INSERT INTO site_magic_releases (
                release_id, checkpoint_id, tenant_id, status, requested_by, created_at
            ) VALUES (?, ?, ?, 'requested', ?, ?)""",
            (release_id, checkpoint_id, tenant_id, actor_id, now),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="release", aggregate_id=release_id,
            aggregate_version=1, event_type="release_requested", actor_type="user", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"release_id": release_id, "checkpoint_id": checkpoint_id},
        )
        return self.get_release(tenant_id=tenant_id, release_id=release_id), False

    def get_release(self, *, tenant_id: str, release_id: str) -> Optional[SiteMagicRelease]:
        row = self._conn.execute(
            """SELECT release_id, checkpoint_id, tenant_id, status, public_locator,
                      requested_by, failure_code, created_at, published_at
               FROM site_magic_releases WHERE tenant_id = ? AND release_id = ?""",
            (tenant_id, release_id),
        ).fetchone()
        return _as_release(row) if row else None

    def complete_release(
        self, *, tenant_id: str, release_id: str, public_locator: str,
        actor_id: Optional[str], correlation_id: str, idempotency_key: str,
    ) -> SiteMagicRelease:
        release = self.get_release(tenant_id=tenant_id, release_id=release_id)
        if release is None:
            raise ControlPlaneNotFoundError(release_id)
        if release.status == "published":
            return release
        if release.status != "requested":
            raise ControlPlaneConflictError("Release is no longer publishable")
        now = _now()
        self._conn.execute(
            """UPDATE site_magic_releases SET status = 'published', public_locator = ?, published_at = ?
               WHERE tenant_id = ? AND release_id = ? AND status = 'requested'""",
            (public_locator, now, tenant_id, release_id),
        )
        self._conn.execute(
            """INSERT INTO site_magic_active_releases (tenant_id, release_id, checkpoint_id, activated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (tenant_id) DO UPDATE SET
                   release_id = excluded.release_id,
                   checkpoint_id = excluded.checkpoint_id,
                   activated_at = excluded.activated_at""",
            (tenant_id, release_id, release.checkpoint_id, now),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="release", aggregate_id=release_id,
            aggregate_version=2, event_type="release_published", actor_type="publisher", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"release_id": release_id, "checkpoint_id": release.checkpoint_id, "public_locator": public_locator},
        )
        return self.get_release(tenant_id=tenant_id, release_id=release_id)

    def fail_release(
        self, *, tenant_id: str, release_id: str, failure_code: str,
        actor_id: Optional[str], correlation_id: str, idempotency_key: str,
    ) -> SiteMagicRelease:
        release = self.get_release(tenant_id=tenant_id, release_id=release_id)
        if release is None:
            raise ControlPlaneNotFoundError(release_id)
        if release.status == "failed":
            return release
        if release.status != "requested":
            raise ControlPlaneConflictError("Release is no longer pending")
        self._conn.execute(
            """UPDATE site_magic_releases SET status = 'failed', failure_code = ?
               WHERE tenant_id = ? AND release_id = ? AND status = 'requested'""",
            (failure_code[:128], tenant_id, release_id),
        )
        self._append_event(
            tenant_id=tenant_id, aggregate_type="release", aggregate_id=release_id,
            aggregate_version=2, event_type="release_failed", actor_type="publisher", actor_id=actor_id,
            correlation_id=correlation_id, idempotency_key=idempotency_key,
            payload={"release_id": release_id, "failure_code": failure_code[:128]},
        )
        return self.get_release(tenant_id=tenant_id, release_id=release_id)

    def list_events(self, *, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT event_id, tenant_id, aggregate_type, aggregate_id,
                      aggregate_version, aggregate_sequence, event_type, occurred_at,
                      actor_type, actor_id, correlation_id, causation_id, idempotency_key,
                      payload_schema_version, payload_json, prev_event_hash, event_hash
               FROM site_magic_events WHERE tenant_id = ?
               ORDER BY occurred_at, event_id LIMIT ?""",
            (tenant_id, max(1, min(limit, 200))),
        ).fetchall()
        return [
            {
                "event_id": str(row["event_id"]), "tenant_id": str(row["tenant_id"]),
                "aggregate_type": str(row["aggregate_type"]), "aggregate_id": str(row["aggregate_id"]),
                "aggregate_version": int(row["aggregate_version"]),
                "aggregate_sequence": int(row["aggregate_sequence"]),
                "event_type": str(row["event_type"]), "occurred_at": str(row["occurred_at"]),
                "actor_type": str(row["actor_type"]), "actor_id": row["actor_id"],
                "correlation_id": str(row["correlation_id"]), "causation_id": row["causation_id"],
                "idempotency_key": str(row["idempotency_key"]),
                "payload_schema_version": int(row["payload_schema_version"]),
                "payload": _decode(row["payload_json"]), "prev_event_hash": row["prev_event_hash"],
                "event_hash": str(row["event_hash"]),
            }
            for row in rows
        ]
