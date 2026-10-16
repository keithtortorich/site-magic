# Standup - 2026-08-09 - Impeccable Phase 2

**Status:** Phase 2 (API + tests), 2b (adapter code), 2c (worker circuit), and 2d
(idempotent transitions) are complete locally. Full validation is green. Runtime
wiring to live credentials and production activation remain deliberately incomplete.

## Completed

- Corrected the Impeccable skill pin: was silently on `skill-v4.0.4` (commit
  `1cbee026`, that repo's HEAD) despite `package.json` pinning `3.5.0`. Both
  `.claude/skills/impeccable` and `.github/skills/impeccable` restored from the
  verified real `skill-v3.5.0` commit (`99fbe4bb10a1453c82027a477503ce240d9b0b47`),
  each with `LICENSE`, `NOTICE.md`, `.impeccable-pin.json`.
- 117 Python tests across `test_site_magic_api.py` / `test_site_magic_repository.py`
  / `test_site_magic_security.py` / `test_site_magic_migrations.py` (tenant
  isolation, role checks, state-machine transitions, release gates, SSRF bypass
  classes, migration parity). Found and fixed a real bug while testing:
  `normalize_public_url` treated an explicit port `0` as falsy and silently
  substituted the scheme default instead of rejecting it.
- Intake auto-enqueues a Site Magic job (`source_type=intake`) after commit,
  fail-closed/non-fatal to intake if the queue isn't configured.
- Agency router's embedded `DictLoader` template dict (a second, drifting source
  of truth) replaced with real files at `webstaffr/templates/agency/*.html`. The
  stale pre-governance-cleanup copies that used to live there (fabricated stats,
  "WebStaffr" branding, wrong pricing tiers, a raw non-functional `<form>`) are
  gone; the router now serves the one already-governance-tested version.
- Real (non-Null) adapters, code only, no live credentials touched:
  - `webstaffr/site_magic_adapters.ts`: `OpenAICodexRuntime` (`@openai/codex-sdk`),
    `OpenAIImageGenerator` (OpenAI Images, `gpt-image-2`), `SupabaseArtifactStore`
    (seals a job workspace into Supabase Storage), `HTTPJobStateSink` (reports
    `SiteMakerEngine` transitions to the Python control plane).
  - `webstaffr/site_magic_adapters.py`: `SupabaseArtifactStorage` (signed
    preview/publish URLs), `HttpxSiteCrawler` (same-origin bounded redirects,
    per-hop SSRF re-validation), `HTTPWebhookSiteMagicQueue` (generic
    authenticated webhook -- this repo has no visibility into the real
    SMMM/Celery worker API, so it defines only our side of the contract rather
    than guessing SMMM's).
- Internal Site Magic control-plane endpoints (`X-API-Key`, matches Rita/Leo/Sam's
  convention): `GET .../internal/jobs/{id}` (full job incl. `source_payload`),
  `POST .../internal/jobs/{id}/transition`.
- `SiteMagicRepository.transition()` now actually persists
  `remediation_rounds`/`rebuild_count`/`quality_summary`/`failure_code` (was
  silently dropping them). `SiteMagicRepository.seal_build_and_advance()` is the
  first real path that writes a `site_magic_builds` row and sets
  `final_build_id` -- previously `ready_for_review` was unreachable for a real
  job outside test fixtures.
- Idempotent event-sequenced transitions: `0017_site_magic_job_events.sql` /
  `postgres_manual/0020_site_magic_job_events.sql` (numbers verified against the
  actual migrations directory, not guessed) add
  `site_magic_jobs.current_event_sequence` and an immutable
  `site_magic_job_events` ledger. `SiteMagicRepository.transition_idempotent()`
  allocates `event_sequence` server-side and replays a retried `event_id`'s
  cached result instead of re-applying or 409ing, even after the job has moved
  further on. `POST .../transition` takes an optional `event_id`; omitted keeps
  the prior non-idempotent behavior. `HTTPJobStateSink.transition()` grew an
  optional 5th `eventId` param for a future retry wrapper (the method itself
  still doesn't retry).
- Reviewed and rejected two externally-drafted architecture documents (pasted
  into chat from a separate, disconnected sandbox session -- never landed as
  files here) rather than adopting them: a `.gitignore` diff that deleted every
  existing rule, Postgres migration numbers that collided with already-applied
  migrations, an `async`/`asyncpg` design against a generic `jobs` table (this
  codebase is sync psycopg2/sqlite3 against `site_magic_jobs`), an UPDATE that
  incremented `rebuild_count`/`remediation_count` on every transition (would
  blow the schema's own CHECK constraints within one ordinary job), a
  client-side sequence counter that resets on worker restart, calls to
  `sink.claimLease()`/etc. never defined on the calling class, and a fabricated
  `npx impeccable critique --json` CLI call (repeats the same wrong-CLI mistake
  already corrected once this session).
- Preserved the pre-existing `webstaffr/templates/site/base.html` change.

## Validation

- Python tests: **767/767 passed**
- Node tests: **21/21 passed**
- Health check: **14/14 HEALTHY**
- All adapter tests use mocked transports/fetch/DNS resolvers. No network calls,
  no live credentials, at any point this session.

## Important Incomplete Work

- **Lease/claim semantics were deliberately not built.** Both rejected drafts
  assumed a shared pull-queue with multiple workers racing to claim jobs. This
  repo's actual queue adapter is a single push webhook to one external worker
  per job -- the "two workers claim the same job" race doesn't obviously apply
  here. Revisit only if the real SMMM worker model turns out to need it.
- **No worker entrypoint script exists.** Nothing wires `SiteMakerEngine`
  (`site_maker_engine.ts`) to the real adapters + `HTTPJobStateSink` end to end.
  Next implementer should build this against a `FakeEvidenceRunner` and the
  existing `NullSiteMagicQueue`/fakes first, per prior engineering advice: prove
  mocked end-to-end orchestration before any live model call.
- **Evidence Runner is not implemented.** Needs Playwright, axe-core, and
  Lighthouse as new npm dependencies -- explicitly not installed without
  approval. The correct design extends the *existing*, tested `QualityReport` /
  `deterministicGatesPass()` already in `site_maker_engine.ts` (camelCase,
  per-metric AND-gates, 6/6 tests passing) -- do not introduce a second,
  parallel `QualityReport` schema or gate model.
- **The queue adapter is a generic webhook, not a real SMMM/Celery client.**
  This repo has no visibility into that service's actual API. SMMM's owner
  needs to define and document a listener contract before a concrete adapter
  can be written -- do not guess it.
- **The crawler revalidates DNS immediately before every request and redirect
  hop, but does not pin the connection to the validated IP.** Narrows the
  TOCTOU window, doesn't close it. Production crawling needs an egress proxy or
  a transport that pins IP while preserving TLS SNI and the Host header.
- **`SupabaseArtifactStorage.publish()` returns a ten-year signed URL.** Explicit
  placeholder, not an acceptable permanent public-serving design. Needs an
  immutable public route or CDN-backed custom-domain mapping with atomic
  active-build resolution -- never equate a long-lived signed object URL with
  publication.
- **The Impeccable npm CLI and both project skill trees are pinned to v3.5.0 at
  source commit `99fbe4bb10a1453c82027a477503ce240d9b0b47`.** Do not run
  `impeccable update` or `impeccable install --force`: the installer ignores
  the local pin and reports the unrelated v4.0.4 release as current.
- No live dry run has occurred: no `OPENAI_API_KEY` exists, GPT Image org
  access is unapproved.
- The Postgres migrations (`0019_site_magic.sql`, `0020_site_magic_job_events.sql`)
  are written only, never applied to Supabase.

## Repository

- Canonical checkout: `/Users/doc/Desktop/NetBuild.Pro`
- Branch: `main`
- No commit, push, deployment, production queue activation, credential change,
  live adapter run, or production migration occurred at any point this session.
- Working tree contains all of the above uncommitted, plus the protected
  pre-existing `webstaffr/templates/site/base.html` edit.

## Next Priorities

1. **Close the worker circuit for real:** executable worker entrypoint wiring
   `SiteMakerEngine` to `OpenAICodexRuntime`/`OpenAIImageGenerator`/
   `SupabaseArtifactStore`/`HTTPJobStateSink`, using `FakeEvidenceRunner` and the
   existing fakes for a first end-to-end dry run. No live credentials needed for
   this step.
2. **Evidence Runner:** get explicit approval for Playwright/axe-core/Lighthouse
   as new npm deps, then build it to extend `site_maker_engine.ts`'s existing
   `QualityReport`/`deterministicGatesPass()` -- do not fork a second schema.
3. **Resolve production boundaries explicitly:** real SMMM listener contract
   (ask SMMM's owner, don't guess), connection-pinned crawler/egress design,
   durable public-serving/CDN route for published builds. Then, and only then:
   `OPENAI_API_KEY` creation, Supabase migration apply, production queue
   activation, publish, push, deploy -- each its own separate approval gate.

## Engineering Advice for the Next Implementer

- Preserve fail-closed behavior throughout. A missing adapter, incomplete
  evidence report, exhausted budget, callback conflict, or unsigned artifact
  must end in `failed` or `quarantined`, never `ready_for_review`.
- Every callback is already idempotent via `event_id` -- use it. A worker retry
  should resend the same `event_id` for the same logical attempt, not a fresh
  one, or the ledger can't help it.
- Do not send crawler output as agent instructions. It's already wrapped in a
  hostile-data envelope (`extract_hostile_source_text`) -- keep it that way.
- Keep design judgment and browser evidence independent. The design assessor
  must not see the evidence report before writing its assessment; the finish
  reviewer must be a fresh invocation.
- Before implementing anything proposed by another session/tool/draft: verify
  it against the actual code and actual disk state first. This standup exists
  because that check caught a wrong commit-hash pin, a destructive `.gitignore`
  diff, colliding migration numbers, a constraint-breaking SQL bug, and a
  fabricated CLI command -- all presented confidently as "ready for
  implementation."
