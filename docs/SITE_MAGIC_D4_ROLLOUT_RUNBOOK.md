# Site Magic D4 rollout runbook

Status: prepared locally; not executed.

This runbook is the approval boundary for taking the standalone Site Magic
control plane from the verified repository state into production. It is
deliberately separate from the Gate 0 product contract. No step below should
be performed until the production owner explicitly approves the rollout.

## Scope

The rollout has two independently verifiable parts:

1. Deploy the standalone build engine and prove the approved-build webhook and
   source handoff path.
2. Apply and verify the Postgres control-plane migrations.

No customer plan, build, checkpoint, or release should be created during the
rollout. Use a disposable test tenant only after the schema and worker checks
pass, and keep publication disabled.

## Preflight

- Confirm the target Supabase project and production application/worker
  environments.
- Confirm a backup/restore point exists and record its timestamp.
- Confirm the worker image contains `npm run start:site-magic-worker` and the
  rendered evidence dependencies.
- Configure the separate control-plane handoff pair:
  `SITE_MAGIC_CONTROL_BUILD_WEBHOOK_URL` and
  `SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET` on the app, with the matching
  secret available to the worker.
- Confirm `SITE_MAGIC_API_BASE_URL` and `SITE_MAGIC_INTERNAL_API_KEY` are
  present on the worker.
- Confirm the publisher adapter is disabled or pointed at a non-public test
  sink during verification. There must be no automatic release path.
- Record the exact application commit/image and migration file hashes.

## Migration order

Apply the manual Postgres files in this order, one transaction or reviewed
step at a time:

1. `0023_site_magic_control_plane.sql`
2. `0024_site_magic_revision_builds.sql`
3. `0025_site_magic_build_failure.sql`
4. `0026_site_magic_build_correlation.sql`

After each file, verify the expected tables, columns, indexes, RLS settings,
policies, and immutability triggers before proceeding. Stop immediately on a
partial or unexpected result; do not improvise DDL in the production console.

## Verification

### Worker and source handoff

- Wrong control-plane webhook secret returns `401`.
- Correct secret accepts a build request and returns `202`.
- The worker fetches only the tenant-scoped approved source projection.
- Approval hash, plan version, fact snapshot, and tenant ID are revalidated
  before generation.
- A provider/build failure produces a bounded failure callback and no preview.

### Control plane

- Verified facts can be imported and listed only within their tenant.
- A safe starter plan contains no publishable unsupported claims.
- Build creation fails without the exact immutable approval.
- Preview evidence is tenant-scoped and rendered-gate based.
- Out-of-scope revision changes are rejected or blocked.
- A checkpoint can be accepted only from a passing preview.
- Release remains an explicit, separately authorized command.
- Event rows and approvals reject update/delete attempts.

### Rollout smoke test

Use one disposable tenant with a small verified fact set. Exercise:

`facts → safe starter plan → operator edit → approval → build → preview`

Stop after preview verification. Do not accept a checkpoint or publish during
the first rollout smoke test unless a separate release approval is given.

## Rollback and stop conditions

- If the worker cannot validate the approved source, stop the worker rollout
  and restore the previous worker image/configuration.
- If any migration fails or leaves an unexpected object, stop and restore from
  the recorded backup/restore point; do not run ad-hoc corrective SQL.
- If a rendered quality gate fails, preserve the blocked preview and diagnose
  the artifact/build path; do not bypass the gate.
- If any tenant-scope or release-gate assertion fails, disable the handoff and
  publisher adapters before further investigation.

## Evidence to attach to the approval record

- application commit/image digest;
- migration file hashes and database verification output;
- worker startup and webhook authentication checks;
- source-handoff and preview evidence IDs;
- confirmation that no release was published;
- operator and production-owner approvals.
