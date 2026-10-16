# ARCHITECTURE.md

Reference doc, not governance. Describes the system as it actually exists in this
repo's code, not an aspirational design. If this doc and the code disagree, the
code is right -- fix this doc, not your assumptions.

## System shape

A single FastAPI application, assembled by `webstaffr/app.py`'s `create_app()`
(the composition root), deployed as Vercel serverless functions via `index.py`'s
re-export of `app`. No persistent process, no background workers, no held-open
connections -- every request opens a DB connection, does its work, and closes it.
This constraint shapes several other decisions below (see DECISIONS.md).

Customer-facing site generation is in-repo (site_renderer.py, Jinja2 templates).
This repo owns backend logic only: Angel (the AI receptionist), tenant isolation,
attribution, and integration bridges.

## Composition root: `webstaffr/app.py`

`create_app()` builds one FastAPI instance and wires every router into it:
`intake_router`, `site_router`, `attribution_router`, `social_media_router`,
the workflow-graph router, the Retell router, and Angel's own router
(`webstaffr/workers/angel/router.py`'s `create_angel_router()`). It also owns
`ScopedCORSMiddleware`, the `/health` route, and the two optional routes
(`/v1/audio/speech`, `/integrations/servicetitan/poll`) gated behind env vars.

Each AI-employee worker lives in its own `webstaffr/workers/<name>/` package
and exposes a `create_<name>_router()` factory -- `app.py` is the only place
that includes it. Angel is the first and, as of this repo, only worker; a
future Marketing Coordinator worker adds its own package and its own line in
`create_app()`, as a sibling to Angel's, never nested inside `workers/angel/`.

This split (composition root separate from any one worker's own endpoints)
replaced an earlier shape where the app factory lived inside
`workers/angel/router.py` alongside Angel's own `/chat`/`/book`/`/webhooks/ghl`
handlers -- workable with one worker, but it buried the actual "assemble the
whole app" logic four directories deep under one specific worker's name,
and would have made "add a second worker" mean editing Angel's own module.
See DECISIONS.md.

## Integration pattern: Protocol + Null + real implementation

Every external dependency in this codebase follows the same three-part shape:

| Concern | Protocol | Safe default | Real implementation |
|---|---|---|---|
| AI chat backend | `VoiceBackend` | `NullVoiceBackend` | `GrokVoiceBackend` (xAI) |
| CRM sync | `GHLClient` | `NullGHLClient` | `GoHighLevelClient` |
| Retell webhook auth | `RetellWebhookVerifier` | `NullRetellWebhookVerifier` | `RetellSignatureVerifier` |
| Shared-secret auth | `SharedSecretVerifier` | `NullSharedSecretVerifier` | `StaticSecretVerifier` |

The rule: a real implementation raises a `*NotConfiguredError` at
**construction time** if its required credentials are missing -- it never
silently no-ops or fabricates a successful response. Whether a real
implementation or its Null counterpart gets constructed is decided once,
from environment variables, at app startup (`_backend_from_env()` and
`_ghl_client_from_env()` in `webstaffr/app.py`) -- dependencies are injected
via constructors everywhere, never built internally by the class that uses
them. This means the app runs safely with zero configured credentials
(useful for local dev and CI) and fails loudly, at startup, if a
credential is set but malformed -- never a silent partial failure at
request time.

## Persistence: raw SQL, dual SQLite/Postgres backend

No ORM. Every repository and router is written once against a
`sqlite3.Connection`-shaped surface (`.execute(sql, params)` returning a
cursor with `.fetchone()`/`.fetchall()`/`.lastrowid`, plus
`.commit()`/`.rollback()`/`.close()`), using SQLite-dialect SQL at every
call site (`?` placeholders, `PRAGMA`, `INSERT OR IGNORE`).

`webstaffr/db.py` is the single place that makes this same code run
against Postgres too. When `DATABASE_URL` is set, `get_connection()`
returns a `_PGConnection` wrapping a real `psycopg2` connection; its
`_PGCursor` rewrites SQLite dialect to Postgres dialect on the fly:
`PRAGMA` becomes a no-op, `INSERT OR IGNORE` becomes
`ON CONFLICT DO NOTHING`, inserts into `_LASTROWID_PK` tables get an
auto-appended `RETURNING <pk>` so `cursor.lastrowid` still works, and `?`
becomes `%s`. This shim is covered by dedicated unit tests
(`tests/test_db_pg_shim.py`) against a fake driver -- it has never been
exercised against a real live Postgres server from within this repo's test
suite; that remains a documented, accepted gap.

`migrate()` applies `webstaffr/migrations/*.sql` (non-recursive glob,
sorted by filename) via SQLite `executescript()`, tracked in a
`schema_migrations` table. It is a **no-op under Postgres** -- schema for
the live database is managed out-of-band, directly against Supabase, not
run by the app. Files that are Postgres-only syntax (e.g. `ENABLE ROW
LEVEL SECURITY`) live in `webstaffr/migrations/postgres_manual/`,
deliberately outside the glob path that would otherwise break every local
SQLite run.

`DB_ERRORS = (sqlite3.Error, psycopg2.Error)` is the one exception tuple
every repository and route handler catches, so a database failure under
either backend becomes a `StorageError` or an `HTTPException(503)` --
never an unhandled backend-specific exception leaking connection details
to a client.

## Request lifecycle: `POST /chat`

1. Pydantic validates `ChatRequest` (`tenant_id`, `message` capped at 4000
   chars, optional `session_id`) -- malformed input never reaches handler
   code; rejected with `422`.
2. `Tenant(tenant_id=...)` validates the ID shape -- `400` on failure.
3. A DB connection is opened (SQLite or Postgres, per `DATABASE_URL`) --
   `503` on connection failure.
4. `check_and_increment()` enforces a per-tenant, per-endpoint rate limit
   (fixed-window counter in the `rate_limit_counters` table) -- `429` if
   exceeded. The counter still increments on a rejected request, so a
   request that trips the limit still "uses" its slot.
5. `Angel` is constructed with the tenant, the open connection, and the
   already-selected `voice_backend`/`ghl_client` (real or Null, decided
   once at app startup).
6. `Angel.respond()` renders `angel_prompt.md` (the founder-authored,
   verbatim system prompt) plus a small dynamic-context block, then calls
   `voice_backend.respond()`. Under `GrokVoiceBackend` this is a real HTTP
   call to xAI; network or parse failures degrade to a fixed fallback
   string rather than raising to the caller.
7. Connection commits and closes in a `finally` block regardless of
   outcome.

No chat message is itself persisted (there is no `chat_messages` table) --
only bookings and rate-limit counters touch the database on this path.

## CORS: per-path, not app-wide

`ScopedCORSMiddleware` (a custom `BaseHTTPMiddleware`, not FastAPI's
built-in `CORSMiddleware`, defined in `webstaffr/app.py`) adds
`Access-Control-Allow-Origin: *` only to browser-facing paths: `/chat`,
`/intake`, and anything prefixed with `/intake/presets`, `/sites/`, or
`/tenants/`. Every other route -- `/book`, `/webhooks/ghl`, `/retell/*`,
`/integrations/*`, `/workflow-graph/*` -- carries no CORS headers at all,
because nothing but a server (GHL, Retell, or a future internal caller)
is ever meant to call them directly from outside a browser context.

## Hosting model

Vercel serverless, via `index.py`'s re-export of the FastAPI `app`
object from `webstaffr/app.py`. No `Dockerfile`, no persistent server
process. This is why the lifespan handler explicitly skips opening any DB
connection at all when running under Postgres (`using_postgres()`) --
there is nothing for `migrate()` to do there, and opening a connection
just to no-op on it would mean every cold start depends on DB
reachability even for routes that don't touch the database.

No `pyproject.toml` in this repo, deliberately -- see DECISIONS.md.
`requirements.txt`/`requirements-dev.txt` are the sole dependency source;
`pytest.ini` covers test config.

## What this doc deliberately does not cover

Deployment/hosting status for this specific repo (whether Vercel has been
re-pointed at it yet, whether the two new Postgres migrations have been
applied) -- see `DEPLOYMENT_CHECKLIST.md` and `TASKS.md` for current
state, since that changes independently of the architecture described
here.
