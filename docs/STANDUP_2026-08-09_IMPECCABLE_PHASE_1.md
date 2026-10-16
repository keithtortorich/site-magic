# Standup - 2026-08-09 - Impeccable Phase 1

**Status:** Phase 1 foundation and external-service adapters are implemented locally. Full validation is green. Runtime wiring and production activation remain deliberately incomplete.

## Completed

- Replaced the nonfunctional `site_maker_engine.ts` shell-command prototype with a bounded, dependency-injected state machine.
- Added normalized Impeccable scoring, ordered P0-P3 weakness handling, two-remediation-round ceiling, one-rebuild ceiling, quarantine behavior, fresh finish review, private immutable sealing, and delayed preview release.
- Added fail-closed Codex, image, evidence, artifact, crawler, and queue contracts with `Null*` implementations.
- Added the authenticated Site Magic control-plane routes for job creation, status, final preview, and owner-approved publishing.
- Added tenant-scoped raw-SQL persistence for jobs, immutable builds, and the atomic active-build pointer.
- Added SQLite migration `0016_site_magic.sql` and matching unapplied Postgres migration `0019_site_magic.sql` with default-deny RLS.
- Added URL-source validation for HTTP(S), ports 80/443, userinfo rejection, DNS resolution, public-address enforcement, canonicalization, and hostile HTML text extraction.
- Removed the runtime homemade `ImpeccablePipeline` enrichment that mutated verified tenant data and fabricated urgency, trust, and conversion claims.
- Removed both duplicate homemade pipeline modules and their obsolete unit test.
- Added a project Node package and lockfile. Installed `impeccable` 3.5.0, `@openai/codex-sdk` 0.98.0, and `openai` 5.19.1 locally. No API key was created or used.
- Added real TypeScript adapters for the Codex SDK, OpenAI Images (`gpt-image-2`), and private immutable Supabase artifact sealing.
- Added real Python adapters for signed preview/publish URLs, authenticated queue-webhook dispatch, and bounded same-origin crawling with per-hop SSRF revalidation.
- Added internal API-key-protected job snapshot and transition endpoints using the existing Rita/Leo/Sam server-to-server convention.
- Added `HTTPJobStateSink`, closing the callback path from the Node engine to the Python control plane.
- Made transitions persist remediation counts, rebuild counts, quality summaries, and failure codes.
- Added `seal_build_and_advance()`, which atomically creates the immutable build record and makes `ready_for_review` reachable without test fixtures.
- Rejects retried build-ID collisions with 503 instead of silently changing build ownership.
- Added mocked-transport adapter coverage without network calls or live credentials.
- Preserved the pre-existing `webstaffr/templates/site/base.html` change.

## Validation

- Python tests: **745/745 passed**
- Node tests: **19/19 passed**
- Health check: **14/14 HEALTHY**
- Adapter tests use mocked transports. No network calls or live credentials were used.

## Important Incomplete Work

- Two implementation-ready architecture drafts were reported at `/workspace/docs/IDEMPOTENT_JOB_TRANSITIONS_ARCHITECTURE.md` and `/workspace/docs/DETERMINISTIC_EVIDENCE_RUNNER_ARCHITECTURE.md`, but those files are not present in this canonical checkout. They must be copied or recreated under this repository's `docs/` before implementation or review.
- Intake does not yet auto-enqueue a Site Magic job after commit.
- The queue adapter is an authenticated generic webhook, not an SMMM/Celery client. SMMM must expose and document a listener contract before a concrete adapter is written.
- The crawler revalidates DNS immediately before every request and redirect hop, but does not pin the connection to the validated IP. Production crawling needs an egress proxy or a transport that pins IP while preserving TLS SNI and the Host header.
- `SupabaseArtifactStorage.publish()` currently returns a ten-year signed URL. This is not an acceptable permanent public-serving design; publishing needs an immutable public route or CDN-backed custom-domain mapping with atomic active-build resolution.
- The evidence runner is not implemented. Playwright, axe, Lighthouse, and pinned Impeccable detector execution still need to be composed into one deterministic report.
- Transition retries still rely on optimistic state guards. There is no correlation ID, monotonic event sequence, or idempotency ledger to distinguish an already-applied callback from a genuinely stale callback; both return 409.
- No worker lease/claim or heartbeat semantics exist, so duplicate workers are not yet safely coordinated.
- The executable worker entrypoint is not implemented. `SiteMakerEngine` and its real adapters are individually wired, but there is no process that claims a queued job and runs them end to end.
- No live dry run occurred because no `OPENAI_API_KEY` exists and GPT Image access is not approved/configured.
- The Impeccable npm CLI and both project skill trees are pinned to v3.5.0 at source commit `99fbe4bb10a1453c82027a477503ce240d9b0b47`. Each skill tree includes `LICENSE`, `NOTICE.md`, and `.impeccable-pin.json`. Do not run `impeccable update` or `impeccable install --force`: the installer ignores the local pin and reports the unrelated v4.0.4 release as current.
- The agency router still uses its embedded template dictionary. Filesystem-template consolidation is not done.
- Stale Impeccable architecture documents, deployment checklist, source/license manifest, and ADR updates remain. `TASKS.md` and `CREDENTIALS.md` were updated for this round.
- The Postgres migration is written only. It has not been applied to Supabase.

## Repository

- Canonical checkout: `/Users/doc/Desktop/NetBuild.Pro`
- Branch: `main`
- Site Magic Phase 2 commit: `869895e` (`feat: Site Magic Phase 2 -- API, repository, adapters, worker entrypoint`)
- Local `main`, `origin/main`, and `origin/HEAD` all resolve to `869895e`.
- The scoped Site Magic Phase 2 changes were committed and pushed to GitHub `main`. This means **available on origin**, not deployed to production.
- No deployment, production queue activation, credential activation, Supabase migration, or production smoke test occurred.
- The remaining dirty tree was deliberately excluded from the push and must be reviewed as a separate change set.

## Remaining Dirty-Tree Review Gate

- The v3.5.0 Impeccable restore still appears as extensive `.claude/skills/impeccable` and `.github/skills/impeccable` churn against the previously tracked v4 tree. Do not stage it until both restored trees are compared file-for-file against source commit `99fbe4bb10a1453c82027a477503ce240d9b0b47`.
- Finder-style conflict files such as `SKILL 2.md`, `SKILL 3.md`, `adapt 2.md`, and similarly suffixed scripts are not canonical upstream paths. After hash comparison, remove only confirmed duplicates in a recoverable way; never include them in the pin commit.
- `webstaffr/skills.py`, `webstaffr/skills/__init__.py`, and `tests/test_site_magic_engine.py` were intentionally retired by the approved plan because the homemade pipeline fabricated customer claims and the test covered that obsolete implementation. Their deletion is expected, but should receive one final isolated regression review before its own commit.
- `webstaffr/templates/agency/static/agency.css` and `agency.js` were not part of the pushed Site Magic scope. Verify that the refactored agency router and templates no longer reference or serve them before accepting deletion; otherwise restore them.
- `.gitignore` is additive and limited to Node/Site Magic runtime artifacts.
- The pre-existing `webstaffr/templates/site/base.html` modification remains protected and unrelated.

## Next Three Priorities

1. **Land and reconcile the architecture drafts:** bring both `/workspace/docs/` documents into the canonical checkout, review their SQL against existing migration `0016`/Postgres `0019`, and collapse four proposed migrations into the repository's actual SQLite/Postgres migration sequence. Do not apply production schema.
2. **Implement the local circuit and evidence runner:** add event-envelope idempotency, lease/heartbeat claims, executable worker entrypoint, and `FakeEvidenceRunner` first. Obtain approval before adding Playwright, axe, or Lighthouse dependencies; then implement deterministic browser evidence and pinned Impeccable detection.
3. **Resolve production boundaries explicitly:** choose an SMMM listener contract, connection-pinned crawler/egress design, and durable public-serving/CDN route. Then finish intake enqueueing and docs. Keep OpenAI credentials, Supabase migration/bucket creation, production queue activation, publish, push, and deployment behind separate approval gates.

## Engineering Advice for the Next Implementer

- Preserve the current fail-closed behavior. A missing adapter, incomplete evidence report, exhausted budget, callback conflict, or unsigned artifact must end in `failed` or `quarantined`, never `ready_for_review`.
- Extend every callback with `job_id`, `tenant_id`, expected prior state, and a unique event ID or monotonic sequence. Store the accepted event in the same transaction as the state change. Return the prior success result for an identical retry; reject stale or cross-tenant events.
- Claim jobs with a time-bounded lease, worker identity, heartbeat, and compare-and-swap renewal. A crashed worker may be recovered only after lease expiry; a second worker must never build or seal concurrently.
- Do not send crawler output as agent instructions. Keep it in the hostile-data envelope, strip executable content, cap bytes/pages/time, and record the resolved addresses used for each hop.
- Never equate a long-lived signed object URL with publication. The active-build pointer should select an immutable build behind a stable tenant/custom-domain route, preserving instant rollback.
- Keep design judgment and browser evidence independent. The design assessor must not see the evidence report before writing its assessment, and the final reviewer must be a fresh invocation.
- Run the first live model job only after mocked end-to-end orchestration passes, spend/deadline limits are enforced, and no production secret is available inside the coding/browser sandbox.
- Correct the evidence draft before treating it as authoritative: the approved design gate is at least **90% of the applicable Impeccable maximum**, not a fixed score of 88, and accessibility requires **zero axe violations**, not merely zero critical/serious violations. Lighthouse remains accessibility 100, performance at least 90, best practices at least 95, and SEO at least 95.
- UUID v7 is suitable for event ordering only when sequence authority is still enforced server-side. Do not trust client timestamps or UUID lexical order as the monotonic transition rule; allocate or compare the per-job sequence transactionally in Postgres.
- HMAC signing must include method, canonical path, timestamp, nonce/event ID, and raw-body digest, with constant-time verification and a narrow replay window. Keep it distinct from browser auth and tenant identity.
