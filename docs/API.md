# API.md

Endpoint reference, generated from the actual router code. If this doc and
a router disagree, the router is right.

All routes are mounted into one FastAPI app via `create_app()` in
`webstaffr/app.py`, the composition root.

## CORS scoping

A custom `ScopedCORSMiddleware` (not FastAPI's built-in `CORSMiddleware`)
adds `Access-Control-Allow-Origin: *` only to: `/chat`, `/intake` (exact
matches), and anything prefixed with `/intake/presets`, `/sites/`, or
`/tenants/`. Every other route below carries **no CORS headers** --
listed explicitly per route.

## App-level (`app.py`)

### `GET /health`
Liveness check. No DB touch. Auth: none. CORS: not scoped.
Response: `{"status": "ok"}`

### `POST /v1/audio/speech`
Only mounted if `KOKORO_TTS_URL` is set. Proxies an OpenAI-compatible TTS
request to an external Kokoro backend. Auth: none. CORS: not scoped.

### `POST /integrations/servicetitan/poll`
Only mounted if `SERVICETITAN_ENABLED=true`. Bounded read-only poll of
ServiceTitan resources. Auth: none. CORS: not scoped.
Response: `{"results": [...]}` with per-resource fetch/fail counts.

## Angel (`workers/angel/router.py`'s `create_angel_router()`)

### `POST /chat`
Angel chat turn, called from the widget on a generated customer site.
Auth: none (protected by rate limiting instead). CORS: **scoped** (exact path).

Request (`ChatRequest`):
```json
{"tenant_id": "string", "message": "string (max 4000 chars)", "session_id": "string, optional"}
```
Response (`ChatResponse`): `{"reply": "string"}`

Rate-limited (see rate limiting section below). Oversized `message` is
rejected by pydantic with `422` before Angel/Grok is ever called.

### `POST /book`
Direct appointment booking, no conversation turn required. Auth: `X-API-Key`
header checked against `BOOK_API_KEY` env var -- `401` if configured and
mismatched; **open (no auth) if `BOOK_API_KEY` is unset**. CORS: not scoped.

Request (`BookAppointmentRequest`):
```json
{
  "tenant_id": "string",
  "contact_name": "string",
  "starts_at": "ISO 8601 string",
  "contact_phone": "string, optional",
  "contact_email": "string, optional",
  "notes": "string, optional",
  "sync_to_ghl": true,
  "ghl_contact_id": "string, optional"
}
```
Response (`BookAppointmentResponse`):
```json
{"appointment_id": 0, "tenant_id": "string", "contact_name": "string", "starts_at": "string", "ghl_synced": true}
```

### `POST /webhooks/ghl`
GoHighLevel webhook (website_lead / missed_call event) that starts an
Angel session. Auth: `X-Webhook-Secret` header checked against
`GHL_WEBHOOK_SECRET` env var -- `401` if configured and mismatched;
**open if unset**. CORS: not scoped.

Request (`GHLWebhookEvent`):
```json
{"tenant_id": "string", "event_type": "string", "contact_id": "string, optional", "contact_name": "string, optional", "message": "string, optional (max 4000 chars)"}
```
Response: `{"status": "handled", "reply": "string"}`

### Rate limiting (`/chat`, `/webhooks/ghl`)
Both call `check_and_increment(conn, tenant_id, endpoint)` before
processing. Over the limit → `429`, but the counter still increments (a
rejected request still "uses" its window slot). Fixed-window, not
sliding-window/token-bucket -- see DECISIONS.md for the tradeoff this
accepts.

## `retell_router.py` (mounted at prefix `/retell`)

Auth on both routes below: HMAC-SHA256 signature via the `x-retell-signature`
header, verified against `RETELL_WEBHOOK_SECRET`. `401` on a bad signature;
**accepts everything if `RETELL_WEBHOOK_SECRET` is unset.** CORS: not scoped
on either (server-to-server only).

### `POST /retell/webhook`
Call lifecycle events (`call_started`, `call_ended`, etc.). Logs
attribution `call_events` rows; logs a GHL note on call end if a summary
and contact ID are present.

Response: `{"status": "received"}` or `{"status": "ignored", "reason": "..."}`

### `POST /retell/function-call`
Mid-call tool invocation: `book_appointment`, `escalate_to_human`,
`get_availability`. Always returns `200`, even on internal failure --
degrades to a spoken fallback line rather than erroring the live call.

Response (`FunctionCallResult`): `{"result": "string"}`

Voice-booked appointments use `sync_to_ghl=False` (a fresh phone caller
has no existing GHL contact ID yet -- contact lookup/creation isn't
built). Tenant resolution is via `metadata.tenant_id` set by hand in each
tenant's Retell dashboard agent config, echoed back on every payload --
there is no phone-number-to-tenant lookup table.

## `intake_router.py`

### `POST /intake`
Submits the client intake form; creates the tenant and an idempotent
tracking number. Auth: none. CORS: **scoped** (exact path).

Request (`IntakeRequest`) -- required fields: `biz_name`, `phone`,
`email`, `industry`, `service_area`, `tagline`, `differentiator`,
`services` (list of strings), `license_number`, `plan`, `lead_routing`,
`approver`. Full field set mirrors `intake_submissions` -- see
DATABASE.md.

Response (`IntakeResponse`):
```json
{"submission_id": 0, "tenant_id": "string", "biz_name": "string", "industry": "string", "plan": "string"}
```

### `GET /intake/presets`
Lists supported industries. Auth: none. CORS: **scoped** (prefix match).
Response: `{"industries": [...]}`

### `GET /intake/presets/{industry}`
Per-trade hint text and field-service-management software options. Auth:
none. CORS: **scoped** (prefix match). Always resolves (falls back to
`'Other'` for an unrecognized industry).

## `site_router.py`

### `GET /sites/{tenant_id}`
Public site data consumed by the Lovable-hosted customer site frontend.
Auth: none. CORS: **scoped** (prefix match).

Response: curated projection from `build_public_site_data()`. Internal
fields (`lead_routing`, `approver`, `competitors`, `license_number`,
`notes`, and others) are never included; optional-but-empty fields are
omitted from the response entirely rather than sent as `null` (see the
"no fabrication" principle in DECISIONS.md).

`404` is returned identically for an invalid `tenant_id` shape and a
valid-shape-but-no-submission-yet tenant -- a public endpoint shouldn't
leak which tenant IDs are real. `503` on a database connection failure.

## Site Magic control plane (Gate 0)

These authenticated routes define the standalone Site Magic product boundary.
They are tenant-scoped through `CustomerAuthorizer`; every mutating command
requires an `Idempotency-Key` header. They do not use the legacy
`site_magic_jobs` worker object as their domain model.

### Operator workspace

- `GET /tenants/{tenant_id}/site-magic` — authenticated Gate 0 operator
  workspace shell. It is a client of the `/v1` control-plane routes below;
  it does not maintain a second workflow or state machine.

### Facts

- `POST /v1/tenants/{tenant_id}/facts` — import or enter a fact. New facts
  start as `unverified` and include source provenance and a content hash.
- `GET /v1/tenants/{tenant_id}/facts` — list tenant facts.
- `POST /v1/tenants/{tenant_id}/facts/{fact_id}/verify` — explicitly verify a
  fact as the authenticated operator.

### Plans and approval

- `POST /v1/tenants/{tenant_id}/plans/propose` — create a safe editable
  starter plan from a selected fact snapshot. It contains structure and
  `needs_proof` review items only; it does not generate publishable claims.
- `POST /v1/tenants/{tenant_id}/plans` — create a proposed version from a
  fact snapshot and provider-neutral plan content.
- `GET /v1/tenants/{tenant_id}/plans` — list the tenant's versioned plans for
  operator workspace refresh and selection.
- `GET /v1/tenants/{tenant_id}/plans/{plan_id}` — read the plan and all
  immutable versions.
- `PATCH /v1/tenants/{tenant_id}/plans/{plan_id}/draft` — create a successor
  version from an optimistic `base_version`; it never edits a version in
  place.
- `POST /v1/tenants/{tenant_id}/plans/{plan_id}/versions/{version}/approve`
  — record immutable `plan_approved` for the exact current version. Approval
  requires verified facts and owner role.

### Build authorization and ledger

- `POST /v1/tenants/{tenant_id}/builds` — create a provider-neutral build
  request only when its approval ID and plan version match an approved plan.
  When a build-engine adapter is configured, the approved request is handed
  to it through the provider-neutral dispatcher port. It never publishes or
  bypasses the control-plane approval boundary.
- `GET /v1/tenants/{tenant_id}/builds/{build_id}` — read a tenant-scoped build
  request, including revision lineage and any bounded failure code.
- `POST /v1/internal/builds/{build_id}/preview` — authenticated build-engine
  callback that records isolated rendered evidence, trace manifest, artifact
  manifest, and quality-gate results. A revised build must additionally
  identify its revision ID, changed scope, and unchanged scope; every known
  out-of-scope plan section must be accounted for as unchanged. A failing
  rendered gate produces a blocked preview and cannot be checkpointed.
- `POST /v1/internal/builds/{build_id}/failed` — authenticated build-engine
  failure callback with a bounded failure code. Failed builds cannot accept
  preview evidence and remain recoverable as historical attempts.
- `GET /v1/internal/builds/{build_id}/source?tenant_id=...` — authenticated
  build-engine read of the exact approved plan and fact values needed for the
  build. The hashes are rechecked before the source is returned.
- `GET /v1/tenants/{tenant_id}/previews/{preview_id}` — read tenant-scoped
  preview evidence.
- `POST /v1/tenants/{tenant_id}/previews/{preview_id}/revisions` — create a
  bounded revision with explicit section scope. Semantic revisions are marked
  as requiring reapproval; they cannot silently alter unrelated sections.
- `POST /v1/tenants/{tenant_id}/revisions/{revision_id}/apply` — create the
  next build for a bounded revision. Presentation revisions reuse the exact
  source approval and fact snapshot. Semantic revisions must provide a
  different approved `approval_id` and matching `plan_version`; otherwise no
  build is created. The build envelope includes the revision scope.
- `POST /v1/tenants/{tenant_id}/previews/{preview_id}/checkpoint` — explicit
  owner acceptance of a preview that passed rendered-site gates.
- `GET /v1/tenants/{tenant_id}/checkpoints/{checkpoint_id}` — read an
  immutable accepted build state.
- `POST /v1/tenants/{tenant_id}/checkpoints/{checkpoint_id}/release` — the
  only control-plane publication command. It invokes the publisher adapter
  and updates the active release only after successful publication.
- `GET /v1/tenants/{tenant_id}/events` — read the tenant-scoped immutable
  product event ledger.

## `attribution_router.py`

Read-only by design. Writes to `call_events`/`tracking_numbers` only
happen in-process, from `intake_router.py` and `retell_router.py`, which
already hold an open tenant-resolved connection -- there is no public
ingestion endpoint for call events. All three routes below: auth none,
CORS **scoped** (`/tenants/` prefix). All return a non-leaking `404` on
invalid `tenant_id` shape, matching `site_router.py`'s pattern.

### `GET /tenants/{tenant_id}/tracking-number`
Response: `{"tenant_id": "string", "tracking_number": "string"}`

### `GET /tenants/{tenant_id}/metrics`
Response: aggregated call metrics, from `CallEventRepository.metrics_for_tenant()`.

### `GET /tenants/{tenant_id}/calls?limit=50`
`limit` is capped to `[1, 200]`.
Response:
```json
{"tenant_id": "string", "calls": [{"event_id": 0, "event_type": "string", "call_id": "string", "duration_seconds": 0, "outcome": "string", "created_at": "string"}]}
```

## `social_media_router.py`

Server-to-server bridge to the SMMM (Marketing Coordinator) product. Auth:
`X-API-Key` vs `BOOK_API_KEY` (shared with `/book`). CORS: not scoped.

### `POST /integrations/social-media/mount`
Binds a WS4.0 tenant to an SMMM org. Response includes `mount_id`.

### `POST /integrations/social-media/mount/{mount_id}/intent`
Submits a campaign intent + post draft for that mount.

## `workflow_graph_router.py`

Server-to-server execution-trace API. Auth: `X-API-Key` vs a configurable
verifier. CORS: not scoped.

- `POST /workflow-graph/nodes` -- create a node.
- `GET /workflow-graph/nodes/{workflow_instance_id}/{node_id}` -- read one node.
- `GET /workflow-graph/nodes/{workflow_instance_id}` -- list nodes for an instance.
- `POST /workflow-graph/nodes/{workflow_instance_id}/{node_id}/status` -- update status.

## Auth summary (quick reference)

| Route | Auth mechanism | Fails open if unconfigured? |
|---|---|---|
| `/chat`, `/intake*`, `/sites/*`, `/tenants/*` | none (public by design) | n/a |
| `/book` | `X-API-Key` vs `BOOK_API_KEY` | yes |
| `/webhooks/ghl` | `X-Webhook-Secret` vs `GHL_WEBHOOK_SECRET` | yes |
| `/retell/*` | HMAC signature vs `RETELL_WEBHOOK_SECRET` | yes |
| `/integrations/*`, `/workflow-graph/*` | `X-API-Key` vs configured secret | yes |

"Fails open" is a documented, deliberate default (matches this repo's
Null-object pattern for every other integration) -- it means an
unconfigured deployment behaves exactly as it did before auth was added,
and the gap only actually closes once the relevant secret is set as a
real value. See CREDENTIALS.md for how to set each one.
