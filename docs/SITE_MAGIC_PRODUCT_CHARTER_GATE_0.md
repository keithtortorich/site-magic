# Site Magic Product Charter and Gate 0 Contract

**Status:** Approved  
**Approval:** Product owner approval received on 2026-10-14.  
**Scope:** Product boundary and Gate 0 contract  
**Implementation rule:** Do not begin schema or production implementation from this document until the charter and contract are approved.

## 1. Product charter

Site Magic is a controlled publishing product. It turns verified business facts into a high-quality website while preserving editorial control, tenant isolation, traceability, and explicit publication authority.

The product loop is:

```text
facts → plan → approval → build → verified preview → revision → checkpoint → publish
```

Models, prompts, repositories, code generators, image providers, hosting systems, and workers are replaceable infrastructure. They must not define the product workflow or its domain language.

### Promise

Site Magic will not invent claims when facts are missing, start a build before a plan is approved, publish without an explicit release action, or allow an artifact to exist without a trace to its facts and approved plan.

### Non-goals

Site Magic is not:

- a general-purpose IDE or code workspace;
- a free-form chatbot;
- a conventional drag-and-drop CMS;
- an autonomous deployment agent;
- a wrapper around one model or image provider;
- a domain model for NetBuild.Pro sales, CRM, employee, or intake rows.

The initial implementation may remain in the NetBuild.Pro repository. Its contracts must remain standalone and must not require NetBuild-specific concepts.

### Product boundaries

| Boundary | Owns | Does not own |
| --- | --- | --- |
| Control plane | tenant authorization, facts, plans, approvals, revisions, checkpoints, releases, audit events | provider prompts, generated code internals, deployment-specific jobs |
| Build engine | implementation generated from an approved plan | approval, publication authority, tenant selection |
| Preview verifier | rendered-site evidence and quality gates | source-of-truth facts, editorial decisions, release authorization |
| Publisher | explicit release of one accepted checkpoint | plan editing, build generation, automatic publishing |
| Providers | model, image, storage, browser, and hosting adapters | product state transitions and authorization |

## 2. Domain contract

The following objects are the product's primary vocabulary. Every object is tenant-scoped. IDs, versions, and hashes are stable references; provider job IDs are implementation details.

### Fact

Verified source material with provenance. A fact has an owner tenant, a source reference, captured content or a normalized value, verification status, and evidence metadata.

Minimum contract:

```json
{
  "fact_id": "fact_123",
  "tenant_id": "tenant_123",
  "kind": "service | credential | location | contact | proof | brand | other",
  "value": "verified source value",
  "source": {"type": "operator_input | document | import | integration", "ref": "source-456"},
  "status": "verified | unverified | rejected | superseded",
  "verified_by": "user_789",
  "verified_at": "2026-10-14T00:00:00Z",
  "content_hash": "sha256:..."
}
```

Unverified material may inform a plan's missing-proof list, but may not be rendered as a factual claim. Facts are versioned or superseded; they are never silently overwritten.

### Plan

An editable site specification. It contains the page and section tree, messages and claims, calls to action, imagery requirements, visual direction, and required proof. A plan is a series of explicit versions.

Every claim in a plan must be one of:

- `supported`: references one or more verified fact IDs;
- `omitted`: intentionally excluded because support is absent; or
- `needs_proof`: an explicit requirement that cannot be rendered as a claim until supported.

An unsupported free-form assertion is invalid. A plan version becomes immutable when approved.

### Approval

An immutable authorization for one exact plan version and its fact snapshot. Approval is not a boolean on a mutable plan. It records the approving actor, timestamp, plan version hash, fact-set hash, and the scope authorized for building.

### Build

An implementation attempt derived from exactly one approved plan version and fact snapshot. A build records its source approval, engine/provider versions, artifact manifest, and outcome. A build request without a valid approval is rejected.

### Preview

Tenant-scoped, isolated evidence of one build. It includes a preview locator, rendered routes, screenshots or equivalent render evidence, console/network findings, accessibility and performance results, claim trace data, and quality-gate results. A preview is not public and is not a release.

### Revision

A bounded change request against one specific preview. It declares the target page/section IDs, requested change, reason, and expected impact. The resulting diff must identify changed and unchanged scope.

Presentation-only revisions may rebuild from the same approval only when they cannot change claims, page structure, required proof, or fact bindings. Any revision that changes those semantics creates a new plan version and requires a new approval before rebuilding.

### Checkpoint

An immutable, accepted build state. It points to one verified preview, its exact artifact manifest, quality-gate results, source approval, and revision lineage. Checkpoints are recoverable and are never edited in place.

### Release

An explicit publication record for exactly one checkpoint. A release records who requested publication, which checkpoint was selected, the publication result, and the resulting public locator. No build, worker, provider callback, or passing quality gate may create a release implicitly.

## 3. State machine and invariants

### Plan and approval

```text
draft → proposed → approved
  └──────────────→ superseded
```

- `draft` is editable.
- `proposed` is reviewable and may contain explicit missing-proof items.
- `approved` is immutable and build-authorizing.
- Editing after approval creates a successor version; it does not mutate or extend the prior approval.
- `superseded` is historical and cannot authorize a new build.

### Build, preview, checkpoint, and release

```text
approved plan
    ↓ explicit build request
queued → building → preview_ready → checkpoint_accepted → release_requested → published
                    └────────────→ blocked/failed
checkpoint_accepted ──────────────→ release_failed
```

Required invariants:

1. A build request must name a valid, immutable approval and exact plan/fact hashes.
2. A preview must be isolated to the requesting tenant and must not be addressable as a public release.
3. Quality gates evaluate rendered output and evidence, not generated source alone.
4. A checkpoint may be accepted only from a preview that passed required gates and has a complete trace manifest.
5. A release may target only an accepted checkpoint and requires a separate explicit operator action.
6. A failed release does not change the active release or mutate its checkpoint.
7. Rollback selects a prior checkpoint by explicit release action; it is not an implicit recovery side effect.
8. Providers may fail or be replaced without changing any product state meaning.
9. Every read and write is authorized against the tenant context. A caller-supplied tenant ID is not an authorization decision.

## 4. Gate 0: plan gate

Gate 0 is the only required gate before the first build. It proves that the proposed website is an explicit, supportable plan rather than an unreviewed generation result.

### Operator flow

1. Import or enter facts and show their provenance and verification status.
2. Generate a proposed plan from the selected fact set.
3. Edit pages, sections, claims, CTAs, imagery requirements, required proof, and visual direction.
4. Surface missing, unverified, conflicting, and unsupported facts next to the affected plan item.
5. Require every claim to be supported, omitted, or marked as a non-rendered proof requirement.
6. Show a version diff and the exact fact-set snapshot used by the plan.
7. Record immutable `plan_approved` for the exact plan version only after an explicit approval action.
8. Enable building only for that approved version.

The UI must make these states visible without relying on model explanations:

- supported claim and its fact provenance;
- missing proof and the section it blocks or changes;
- omitted content and the operator's reason;
- plan version, approval status, and approval actor;
- whether a requested change requires reapproval.

The UI must never label a generated draft as approved, expose a private preview as published, or offer a publish action for a build that has no accepted checkpoint.

### Gate 0 acceptance criteria

Gate 0 is contract-complete when an implementation can demonstrate that:

- a tenant can create/import a fact with provenance and verification status;
- a proposed plan contains page/section/claim/CTA/imagery/visual-direction data;
- unsupported claims are visible and cannot be rendered as factual copy;
- an operator can edit and version the plan;
- approval names one immutable plan version and fact snapshot;
- the same plan version cannot receive a second conflicting approval;
- no build command is accepted without that approval;
- the approval is represented by an immutable `plan_approved` event;
- tenant A cannot read or write tenant B's facts, plans, approvals, builds, previews, or events;
- provider replacement does not change the control-plane request or event contracts.

## 5. API boundary

The control plane exposes product commands and projections. It does not expose raw model prompts, provider-specific job semantics, arbitrary code execution, or direct storage mutation.

Illustrative resource boundary:

```text
POST   /v1/tenants/{tenant_id}/facts
GET    /v1/tenants/{tenant_id}/facts
POST   /v1/tenants/{tenant_id}/plans
GET    /v1/tenants/{tenant_id}/plans/{plan_id}
PATCH  /v1/tenants/{tenant_id}/plans/{plan_id}/draft
POST   /v1/tenants/{tenant_id}/plans/{plan_id}/versions/{version}/approve
POST   /v1/tenants/{tenant_id}/builds
GET    /v1/tenants/{tenant_id}/builds/{build_id}
GET    /v1/tenants/{tenant_id}/previews/{preview_id}
POST   /v1/tenants/{tenant_id}/previews/{preview_id}/revisions
POST   /v1/tenants/{tenant_id}/revisions/{revision_id}/apply
POST   /v1/tenants/{tenant_id}/previews/{preview_id}/checkpoint
POST   /v1/tenants/{tenant_id}/checkpoints/{checkpoint_id}/release
GET    /v1/tenants/{tenant_id}/events
```

Internal build-engine callbacks are separately authenticated and tenant-bound:

```text
GET  /v1/internal/builds/{build_id}/source?tenant_id=...
POST /v1/internal/builds/{build_id}/failed
POST /v1/internal/builds/{build_id}/preview
```

Boundary rules:

- Authentication establishes the tenant context; path and body tenant IDs must match it.
- Cross-tenant access returns a non-leaking not-found or authorization response according to the security policy, never another tenant's existence or data.
- Mutating commands require an idempotency key and optimistic version check where a resource is editable.
- Build commands carry `approval_id`, `plan_version`, `plan_hash`, `fact_snapshot_hash`, and a correlation ID.
- Worker and provider callbacks are internal adapters. They may report progress or evidence, but cannot approve plans or publish releases.
- Public site delivery is a separate read path from control-plane previews and must resolve only the active release.

The internal build-engine port is provider-neutral:

```json
{
  "build_id": "build_123",
  "tenant_id": "tenant_123",
  "approval_id": "approval_456",
  "plan_version": 7,
  "plan_hash": "sha256:...",
  "fact_snapshot_hash": "sha256:...",
  "requested_by": "user_789",
  "correlation_id": "corr_..."
}
```

## 6. Event-ledger semantics

The event ledger is append-only, tenant-scoped, and audit-complete. Domain state and its event are committed atomically. Events are evidence of what happened, not a permission shortcut.

Every event includes:

```json
{
  "event_id": "evt_123",
  "tenant_id": "tenant_123",
  "aggregate_type": "plan",
  "aggregate_id": "plan_456",
  "aggregate_version": 7,
  "event_type": "plan_approved",
  "occurred_at": "2026-10-14T00:00:00Z",
  "actor": {"type": "user", "id": "user_789"},
  "correlation_id": "corr_...",
  "causation_id": "evt_122",
  "idempotency_key": "approve-plan-7",
  "payload_schema_version": 1,
  "payload": {"approval_id": "approval_999", "plan_hash": "sha256:...", "fact_snapshot_hash": "sha256:..."},
  "prev_event_hash": "sha256:...",
  "event_hash": "sha256:..."
}
```

Minimum event vocabulary:

`fact_imported`, `fact_verified`, `fact_rejected`, `plan_proposed`, `plan_version_created`, `plan_approved`, `build_requested`, `build_started`, `build_failed`, `preview_ready`, `preview_blocked`, `revision_requested`, `revision_applied`, `checkpoint_accepted`, `release_requested`, `release_published`, `release_failed`, and `release_rolled_back`.

Ledger rules:

- Events cannot be updated or deleted. Sensitive source content is referenced by ID and hash rather than copied into broad audit payloads.
- Idempotency is enforced per tenant and command, so retries cannot create duplicate approvals, checkpoints, or releases.
- Aggregate ordering is monotonic. Consumers must be idempotent; global ordering is not required.
- `plan_approved` is the authorization boundary. It must contain the exact plan version and fact snapshot hash and can never be rewritten to point elsewhere.
- `release_published` is the publication boundary. It must contain the exact checkpoint ID and publisher result.
- Provider logs, prompts, and job records may be retained separately, but they do not replace product events or become the product's domain model.

## 7. Approval checkpoint before implementation

This document intentionally stops at the product contract. Before schema design or production implementation, the product owner must approve:

1. the charter and non-goals;
2. the eight domain objects and their ownership boundaries;
3. the state transitions and invariants;
4. Gate 0 acceptance criteria;
5. the control-plane versus build-engine API boundary; and
6. the immutable event-ledger rules.

Compatibility work on the existing Site Magic engine may continue as engine hardening, but it must be evaluated against this contract and must not be treated as the definition of the standalone product.

## 8. Existing implementation reconciliation

The current repository contains useful engine-hardening work, but its legacy names and routes must not become the product contract:

- `site_magic_jobs` and the worker's job callbacks are orchestration records and transport adapters. They are not the standalone domain object named `Build`, and they must not replace the plan, approval, preview, checkpoint, or release boundaries.
- `/site-magic/jobs/*` is a compatibility API around the current job pipeline. The canonical API is the control-plane boundary in Section 5; any migration may adapt the old routes, but new product behavior must not be specified in terms of worker jobs.
- `demo_job_manager.py` currently auto-publishes reserved demo tenants. That is a demo harness exception, not customer-product behavior and not evidence that automatic publication is allowed. It must remain isolated from the customer release path.
- The current worker transition callback may report build and preview evidence, but it cannot approve a plan, accept a checkpoint, or create a release.
- A provider or storage URL returned by the current engine is not by itself a durable `Release`. Public serving still requires an explicit release record that resolves an active checkpoint and supports recovery.

These are migration and hardening concerns to resolve after charter approval. They do not change the Gate 0 contract or authorize schema changes before approval.
