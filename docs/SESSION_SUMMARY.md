# Session Summary -- 2026-08-11

## Completed

**Site Magic worker deployed live on Railway -- form→site chain now wired end to end**

The worker (`webstaffr/site_magic_worker.ts`) is a persistent Node process with a Playwright/Chromium Evidence Runner, structurally incompatible with Vercel's serverless model. It had no host at all, which is why the queue had never been consumed in production. Shipped `Dockerfile` (node:22-bookworm-slim, `npx playwright install --with-deps chromium`, `npm ci --include=dev` because `impeccable` is a real runtime dependency here -- the Evidence Runner shells out to its `detect` CLI), `.dockerignore`, `railway.json` (Dockerfile builder, restart-on-failure ×5, deliberately no healthcheck path since the worker's only route is POST and a GET check would false-fail), and a `start:site-magic-worker` script. Committed as `8c2b3de`.

Verified before deploying, not just built: local `docker build` succeeded (915MB image), container starts and logs `listening on :8090`, POST with a wrong secret returns 401, GET returns 405 -- which independently confirmed the no-healthcheck-path decision was right.

Deployed to Railway project `melodious-elegance`, service `NetBuild.Pro`, auto-deploying from `main`. Public URL `https://netbuildpro-production.up.railway.app`, target port 8090, status Online.

**Security gap found and closed: Vercel had no `INTERNAL_API_KEY`**

Went looking for the value to copy into Railway and found it doesn't exist -- neither Project nor Shared scope -- despite `webstaffr/workers/angel/api_auth.py:94` requiring it. Rita/Leo/Sam's internal routes have therefore been running `DenyAllSharedSecretVerifier` (always-403, fail-closed) in production since they shipped. Pre-existing, not introduced this session. Generated a fresh secret; it now exists as Vercel `INTERNAL_API_KEY` (Production, Sensitive) and as Railway's `SITE_MAGIC_INTERNAL_API_KEY` -- two env var names, one shared secret across two processes, per `CREDENTIALS.md` #12. Those routes are reachable for the first time.

**RLS gap closed on `rate_limit_dimensions`**

Supabase's advisor flagged it: migration `0005` created the table without RLS, so it shipped fully exposed to the anon/authenticated client roles. Applied `ENABLE ROW LEVEL SECURITY` + `REVOKE ALL FROM anon, authenticated` in Supabase and backfilled `webstaffr/migrations/postgres_manual/0021_rate_limit_dimensions_rls.sql` for migration parity. Zero functional risk -- the backend only reaches this table via service-role raw SQL, which bypasses RLS regardless.

## Blockers

None gating. The chain is wired but unexercised.

## Next

1. **Run one real intake submission through the live chain.** Everything is verified structurally; nothing has executed against real OpenRouter/Playwright in production yet.
2. **Clear the stale prod job first.** `550e8400-e29b-41d4-a716-446655440001` has sat at `status: queued` since 2026-08-10 with `source_payload_json: {"test":"data"}` -- malformed, will fail `resolveSource()` with `UnresolvableSourceError` if the worker picks it up.
3. **Customer bootstrap-on-first-login (D3, still open).** No path creates `customer_users`/`tenant_memberships` after intake, so the dashboard and internal auth surfaces remain unreachable for real tenants.

## Decisions

- **Railway over Render/Fly/VPS** for the worker host (founder-approved). Docker-based so the Chromium version is pinned in the image rather than drifting on a bare box; managed restart and zero-downtime redeploy come free. Render's hobby tier spins down on idle, a real liability for a webhook target that must stay warm.

## Assumptions / context for next session

- Vercel production is project `web-staffr3-3` (team `web-staffr`), serving `netbuild.pro`.
- Supabase project is `ntbnenymyqiautaqhyhe` ("webstaffr"). Migrations `0019`/`0020`/`0021` are applied there.
- The working tree still carries a large uncommitted `.claude/skills/impeccable` + `.github/skills/impeccable` churn (~31 files, plugin auto-sync, not app code) and untracked founder asset drops at the repo root. Deliberately left alone -- not this session's work, needs its own call.

## Files updated

`TASKS.md`, `docs/SESSION_SUMMARY.md`, `outputs/SESSION_SUMMARY.md`, `CREDENTIALS.md`, `Dockerfile`, `.dockerignore`, `railway.json`, `package.json`, `webstaffr/migrations/postgres_manual/0021_rate_limit_dimensions_rls.sql`

---

# Delta Handoff — 2026-08-16 (resume, appended)

Branch: `codex/site-renderer-site-magic`. At `2665e35`: Node 133/133, Python 824/824 (green).

**Shipped (pushed earlier):** four-point fix `2665e35` — schema-constrained `design_assessor`/`finish_reviewer` findings to `Finding[]` + fail-closed `isValidFinding` guard.

**Verified this turn (real tree + pixel check, no fabrication):**
- P2 email-wrap: real UNCOMMITTED 7-line diff in `webstaffr/site_maker_engine.ts` `ensureStableResponsiveLayout` (forces `overflow-wrap:anywhere` on `mailto:`/contact-value). Job `local-1786857894432` burned all 4 remediation rounds on a tablet-width email-wrap finding the model kept re-flagging; enforcing removes it from the model's remediation surface. Node 133/133 pass. Awaiting your commit decision.
- P1 image mismatch: real. `comp-3.webp` (job `local-1786857894432`) pixel-confirmed = HVAC tech's gloved hands on an outdoor AC condenser/compressor; `index.html:118` alt says "metal ductwork and vent grille." Engine root cause confirmed: `generateImagesWithBoundedRetry` runs ONCE at `site_maker_engine.ts:806`; remediation loop (826-899) never calls `images.generate` (grep: zero). Wrong comps unfixable mid-remediation by design. Not patched.
- ADR-030 (Proposed) written to `docs/DECISIONS.md` (~line 597, +96 lines): post-generation image-content vision gate, behind `SITE_MAGIC_IMAGE_VERIFY` flag, additive/isolated. NOT implemented, NOT committed.

**Open founder gates:**
1. ADR-030 approval → I implement + test (flag-off default, reversible, D1 once approved).
2. P2 7-line diff commit decision (separate from ADR).
3. Phase 0 real-pipeline run — CORRECTION: `.env.local` actually holds a 75-char `OPENROUTER_API_KEY` (verified present, value never echoed). Not empty, so missing-key `CodexRuntimeNotConfiguredError` is not the blocker. Gate is key validity/active identity + whether `scripts/local_site_magic_driver.ts` is the intended entry. Confirm/replace key before a real run.

**Untouched untracked:** `.claude/skills/impeccable/` (plugin sync), `scripts/local_site_magic_driver.ts`, `webstaffr/test_import.txt`. `.env.local` gitignored — no secrets in git.

**Uncommitted this session:** `docs/DECISIONS.md` (+96, ADR-030), `webstaffr/site_maker_engine.ts` (+7, P2).
