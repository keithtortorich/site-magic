# DATABASE.md

Schema reference, generated from the actual migration files in
`webstaffr/migrations/`. If this doc and a migration file disagree, the
migration file is right.

Two backends run the same schema: SQLite locally/in tests (default, no
config needed), Postgres/Supabase in whichever deployment has
`DATABASE_URL` set. See `docs/ARCHITECTURE.md`'s persistence section for
how `db.py` bridges the dialect difference. `migrate()` only ever runs
against SQLite -- the live Postgres schema is applied out-of-band, using
the hand-translated files in `webstaffr/migrations/postgres_manual/`.

**Legacy note**: the live Supabase project this app connects to also
still contains `workflow_definitions` and `execution_records` tables from
the prior repo's now-removed workflow engine. Nothing in this repo's
application code reads or writes either table -- they are not part of
this schema, listed here only so their continued presence in the live
database isn't mistaken for a missing migration. See DECISIONS.md.

## `tenants` (`0001_tenants.sql`)

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | TEXT | PRIMARY KEY |

The root of tenant isolation. Every other table either references this
directly via FK or scopes its queries by `tenant_id` in application code.
`tenant_id` is public -- never treated as a credential anywhere in this
codebase.

## `appointments` (`0002_appointments.sql`)

| Column | Type | Notes |
|---|---|---|
| `appointment_id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `tenant_id` | TEXT | NOT NULL, FK → `tenants(tenant_id)` |
| `contact_name` | TEXT | NOT NULL |
| `contact_phone` | TEXT | nullable |
| `contact_email` | TEXT | nullable |
| `starts_at` | TEXT | NOT NULL, ISO 8601 |
| `notes` | TEXT | nullable |
| `source` | TEXT | NOT NULL, DEFAULT `'angel'` |
| `ghl_synced` | INTEGER | NOT NULL, DEFAULT `0` (0/1 boolean) |
| `created_at` | TEXT | NOT NULL |

Index: `idx_appointments_tenant`. Created via `POST /book` or Angel's
`book_appointment` flow (chat or Retell function-call).

## `intake_submissions` (`0003_intake_submissions.sql`)

The 9-section intake form. Same fields for every industry -- per-trade
variation is presentation-only (`trade_presets.py`), not a schema
difference.

| Column | Type | Notes |
|---|---|---|
| `submission_id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `tenant_id` | TEXT | NOT NULL, FK → `tenants(tenant_id)` |
| `biz_name` | TEXT | NOT NULL |
| `phone` | TEXT | NOT NULL |
| `email` | TEXT | NOT NULL |
| `industry` | TEXT | NOT NULL |
| `service_area` | TEXT | NOT NULL |
| `years_in_biz` | INTEGER | |
| `emergency_service` | TEXT | 'Yes'/'No' |
| `has_site`, `site_url`, `site_platform`, `site_issues` | TEXT | Web presence |
| `has_gbp`, `gbp_url`, `google_review_link` | TEXT | Google Business Profile |
| `has_logo`, `brand_colors`, `brand_words`, `inspo_sites` | TEXT | Brand |
| `tagline` | TEXT | NOT NULL |
| `differentiator` | TEXT | NOT NULL |
| `competitors` | TEXT | **internal-only, never exposed publicly** |
| `tone` | TEXT | |
| `services_json` | TEXT | NOT NULL, JSON array |
| `pricing_shown`, `promos` | TEXT | |
| `license_number` | TEXT | NOT NULL in schema; **internal-only, never exposed publicly** (founder decision -- see DECISIONS.md) |
| `rating_value` | REAL | |
| `review_count` | INTEGER | |
| `certifications`, `has_before_after`, `testimonials` | TEXT | |
| `facebook_url`, `instagram_url`, `fsm_system`, `booking_system` | TEXT | |
| `plan` | TEXT | NOT NULL, `'office_staff'` for initial launch |
| `lead_routing` | TEXT | NOT NULL, **internal-only** |
| `timeline` | TEXT | **internal-only** |
| `approver` | TEXT | NOT NULL, **internal-only** |
| `assets_status`, `keywords`, `extra_pages` | TEXT | |
| `notes` | TEXT | **internal-only** |
| `created_at` | TEXT | NOT NULL |

Index: `idx_intake_submissions_tenant`.

**Internal-only fields are a hard rule, not a suggestion**: `competitors`,
`license_number`, `lead_routing`, `timeline`, `approver`, and `notes` must
never appear in `site_data.py`'s public projection. Any future change to
the public site-data shape must re-check this list, not just re-derive it
from the schema.

## `rate_limit_counters` (`0004_rate_limit_counters.sql`)

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | TEXT | NOT NULL, part of composite PK |
| `endpoint` | TEXT | NOT NULL, part of composite PK |
| `window_start` | INTEGER | NOT NULL, unix timestamp floored to window size, part of composite PK |
| `request_count` | INTEGER | NOT NULL, DEFAULT `0` |

PRIMARY KEY: `(tenant_id, endpoint, window_start)`.

**Deliberately has no FK to `tenants`.** Rate limiting must work against a
guessed or never-registered `tenant_id` -- that's precisely the abuse
case it defends against, so a FK that could reject the write would
defeat the purpose.

## `tracking_numbers` (`0005_attribution.sql`)

| Column | Type | Notes |
|---|---|---|
| `tenant_id` | TEXT | PRIMARY KEY, FK → `tenants(tenant_id)` |
| `tracking_number` | TEXT | NOT NULL, UNIQUE |
| `created_at` | TEXT | NOT NULL |

`tracking_number` is a **logical identifier** (`trk_<tenant>_<random>`),
not a real phone number -- no DID has been provisioned yet. Created
idempotently on first successful `POST /intake` per tenant.

## `call_events` (`0005_attribution.sql`)

| Column | Type | Notes |
|---|---|---|
| `event_id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `tenant_id` | TEXT | NOT NULL, FK → `tenants(tenant_id)` |
| `tracking_number` | TEXT | nullable |
| `call_id` | TEXT | nullable, external (Retell) call ID for correlating rows about the same call |
| `event_type` | TEXT | NOT NULL, `'call_received'\|'call_ended'\|'appointment_booked'` |
| `duration_seconds` | INTEGER | |
| `outcome` | TEXT | e.g. `'answered'`, `'voicemail'`, `'booked'`, `'escalated'` |
| `metadata_json` | TEXT | |
| `created_at` | TEXT | NOT NULL |

Indexes: `idx_call_events_tenant`, `idx_call_events_tenant_created`.
Append-only log. Written only by in-process callers (`intake_router.py`,
`retell_router.py`) that already hold an open, tenant-resolved
connection -- deliberately no public write endpoint.

## `social_media_mounts`, `social_media_intents` (`0006_social_media.sql`)

The WS4.0-side bridge to the SMMM (Marketing Coordinator) product. Binds
a tenant to an SMMM org (`social_media_mounts`) and records
campaign/post intent submissions awaiting review (`social_media_intents`).
`tenant_id` validated through `Tenant(...)` at the router layer, not via
FK here. JSON payload columns avoid schema churn for intent content.

## `execution_nodes` (`0007_execution_nodes.sql`)

Execution trace graph for campaign, post, publish, and approval events --
records of what happened, not a workflow-definition table. Tenant-scoped
first: every query filters by `tenant_id`. Nodes are immutable once
created; a `parent_node_id` self-reference creates a tree/forest per
`workflow_instance_id` without a separate edge table.

| Column | Type | Notes |
|---|---|---|
| `node_id` | TEXT | NOT NULL, part of composite PK |
| `tenant_id` | TEXT | NOT NULL, FK → `tenants(tenant_id)`, part of composite PK |
| `workflow_instance_id` | TEXT | NOT NULL, part of composite PK |
| `type` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL |
| `payload_ref`, `parent_node_id` | TEXT | nullable |
| `created_at` | TEXT | NOT NULL |
| `completed_at`, `failure_reason` | TEXT | nullable |

PRIMARY KEY: `(tenant_id, workflow_instance_id, node_id)`. Indexes:
`idx_execution_nodes_tenant`, `idx_execution_nodes_tenant_instance`,
`idx_execution_nodes_tenant_created`.

## Postgres-only files (`webstaffr/migrations/postgres_manual/`)

Not run by the app's `migrate()` -- applied manually against the live
Supabase project. Live outside the main migrations directory specifically
so `migrate()`'s non-recursive glob never picks them up. This directory
is an append-only run-log against the one live Supabase project this app
has always used -- files here keep their original numbers even where the
SQLite files were renumbered during the WebStaffr 4.0 rebuild (see the
numbering note at the top of `0004_enable_rls_default_deny.sql`).

- **`0004_enable_rls_default_deny.sql`** -- `ENABLE ROW LEVEL SECURITY`
  on every table, no policies (default-deny). Nothing in this codebase
  uses PostgREST/anon-key access today (the backend connects via a direct
  Postgres connection, which bypasses RLS regardless of policy) -- RLS is
  a defense against a future client-side integration.
- **`0005_rate_limit_counters.sql`**, **`0006_attribution.sql`** --
  Postgres-dialect twins of the SQLite files above.
- **`0007_social_media.sql`**, **`0008_execution_nodes.sql`** -- Postgres
  DDL + RLS for the two tables that previously had no Postgres-side
  migration at all. **Not yet applied** -- requires founder approval; see
  `DEPLOYMENT_CHECKLIST.md`.
- **`0009_drop_engine_tables.sql`** -- dormant. Drops the legacy
  `workflow_definitions`/`execution_records` tables. Not run at cutover;
  only after WebStaffr 4.0 has proven stable in production.
