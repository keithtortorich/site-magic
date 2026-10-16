# SECURITY.md

Findings from a real code audit, not a policy template. Dated so it's
clear when each claim was actually checked.

## Audit — WebStaffr 4.0 rebuild

Scope: all Python source in `webstaffr/`, `.github/workflows/ci.yml`,
`requirements.txt`. This audit covers the rebuilt codebase's own code;
live Supabase infrastructure state (RLS status, advisor findings) was
**not** re-queried this session -- see "Not covered" below.

### Checked, no issue found

- **No hardcoded secrets.** Grepped for key/secret/password/token
  assignments to string literals across `webstaffr/`; every match was
  either an `os.environ.get(...)` read, a docstring, or a function
  parameter -- nothing that looks like a committed credential.
- **No SQL injection surface.** Every `.execute()` call parameterizes
  user-supplied values with `?` placeholders. The one place a query
  string is built with an f-string (`intake.py`'s `INSERT INTO
  intake_submissions (...)`) interpolates a fixed, code-controlled column
  name list (`_COLUMNS`), not user data -- actual values still go through
  `?` placeholders as a separate parameter tuple.
- **Bearer tokens sourced correctly.** Both `ghl.py` and `voice.py` build
  their `Authorization: Bearer <token>` header from `os.environ.get(...)`
  only -- no default, no fallback literal.
- **Signature/secret verification is constant-time and fails closed.**
  `RetellSignatureVerifier` (`retell.py`) and `StaticSecretVerifier`
  (`api_auth.py`) both use `hmac.compare_digest()`, not `==`, and both
  return `False` (never raise) on a missing or malformed header -- callers
  have one code path for "reject," not two.
- **CI doesn't leak secrets.** `.github/workflows/ci.yml` runs tests and
  the health check against no real credentials (everything defaults to
  the Null-object path) -- nothing in the workflow references a secret
  that could appear in logs.
- **No genuinely dead auth surface.** The rebuild removed
  `_LASTROWID_PK["execution_records"]` and the `INSERT OR REPLACE INTO
  workflow_definitions` special case from `db.py`'s Postgres shim -- both
  targeted tables that belonged to the now-removed workflow engine and
  had zero remaining callers in this repo. Verified by grep across
  `webstaffr/` and `tests/` before removing, and by the full test suite
  passing after.

### Known, accepted gaps (not bugs -- documented tradeoffs, see DECISIONS.md)

- **`/book`, `/webhooks/ghl`, `/retell/*`, `/integrations/*`,
  `/workflow-graph/*` fail open when unconfigured.** Each checks a shared
  secret against a request header, but falls back to a Null verifier that
  accepts everything if the relevant env var is unset. This is a
  deliberate, repo-wide convention (matches every other Protocol+Null
  pattern in this codebase), not an oversight -- but it means **an
  unconfigured deployment has zero auth on these routes**, not reduced
  auth. Confirm the relevant secrets are set in Vercel before this
  deployment goes live -- see `DEPLOYMENT_CHECKLIST.md`.
- **Retell signature format is `[Unverified]`.** `retell.py`'s header-name
  and prefix-stripping logic are implemented from Retell's publicly
  documented convention, never exercised against a real Retell-signed
  request as of this doc.
- **`rate_limit_counters` has no pruning.** Rows accumulate forever. Not a
  practical problem at MVP volume; add a cleanup job before it is one.
- **Postgres dialect shim (`db.py`) has no live-Postgres test coverage.**
  Covered by unit tests against a fake driver (`tests/test_db_pg_shim.py`),
  never exercised against a real running Postgres server from within this
  repo's test suite.
- **`license_number` is collected but not publicly exposed** -- a
  deliberate founder decision (see `docs/DECISIONS.md`), not a gap, noted
  here only because it's the kind of thing a security review would
  otherwise flag as an open question.
- **`social_media_mounts`/`social_media_intents`/`execution_nodes` have
  no Postgres RLS applied yet.** New migrations exist
  (`postgres_manual/0007_social_media.sql`, `0008_execution_nodes.sql`)
  but require founder approval to run against the live database -- see
  `DEPLOYMENT_CHECKLIST.md`. Until applied, these three tables are the
  only ones in the live schema without RLS.

### Not covered by this audit

- **Live Supabase infrastructure state.** The prior repo's last live
  audit (via Supabase's `get_advisors`) found RLS enabled with
  default-deny on all tables that existed at that time, zero policies,
  and no ERROR-level findings. That check has **not** been re-run this
  session -- re-verify via the Supabase MCP or dashboard before treating
  it as current, especially after applying the two new migrations above.
- Dependency CVE scan results (Dependabot surfaces these automatically;
  none were manually checked against a CVE database this session).
- Vercel/hosting-platform-level security (access controls on the Vercel
  team, GitHub App permissions).
- Anything in the WS3.0 or WS3.3 archive repos -- out of scope, separate
  codebases.

## How to keep this current

This file reflects a point-in-time check. Before trusting a claim above,
verify it's still true rather than assuming -- especially the "no
hardcoded secrets" and "no SQL injection surface" findings, which need
re-checking any time new code touches secret handling or raw SQL
construction. Add a new dated section for future audits rather than
editing this one in place.
