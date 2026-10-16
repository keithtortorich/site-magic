# NetBuild.Pro Deployment Checklist

Status: mechanically ready; no push, schema application, environment change,
or deployment is authorized by this document.

## Candidate evidence

1. Record the candidate commit SHA and confirm the production composition root
   is `index.py` exporting `webstaffr.app:app`.
2. Run `.venv/bin/python -m pytest -q` and
   `.venv/bin/python scripts/health_check.py` from the exact candidate tree.
3. Run `git diff --check`. Review all untracked and modified files explicitly;
   never use blanket staging in a shared or dirty checkout.
4. Confirm no `.env`, key, token, database URL, customer contact data, or
   generated credential appears in the diff.
5. Review every SQLite migration together with its PostgreSQL manual companion.
   For `website_leads`, PostgreSQL migration `0018` must retain RLS, revoke
   `anon` and `authenticated`, and define no public policy.

## Authorized activation order

Each numbered mutation requires its applicable approval before execution.

1. Apply reviewed, pending PostgreSQL migrations to the intended Supabase
   project. Record the migration names and advisor output.
2. Configure the already-selected GHL and Retell environment variables in the
   intended Vercel environment without printing their values. Leave
   `LEO_OUTREACH_ENABLED` absent or false for the MVP. Setting general GHL
   credentials must not activate automated SMS or email. Enable Leo outreach
   only after the separate TCPA/DNC approval and operational guardrails.
   Run `scripts/activation_preflight.py` inside an environment populated with
   the candidate configuration. It checks presence only and never prints
   values. The MVP profile requires database, Supabase customer Auth, allowed
   origins, Grok chat, GHL, Retell webhook, and booking API configuration.
3. Push the reviewed candidate and allow CI to pass on that exact SHA.
4. Deploy that exact SHA to preview first. Do not route customer traffic yet.
5. Run the read-only smoke command:

   ```text
   .venv/bin/python scripts/production_smoke.py \
     --base-url https://PREVIEW_HOST \
     --tenant-id VERIFIED_TENANT_ID \
     --expected-sha CANDIDATE_COMMIT_SHA
   ```

   The smoke command verifies the application security-header contract:
   `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
   `Permissions-Policy`, and HTTPS `Strict-Transport-Security`. A CSP is not
   part of the current middleware contract and is not inferred by this check.

6. Exercise the preview-only write path with designated test data: submit one
   website request, verify its tenant-scoped `website_leads` row, GHL contact,
   attributed note, and safe status. Remove test data only through an approved,
   auditable cleanup procedure.
7. Place one designated Retell test call and verify the call event, tenant,
   transcript/summary handling, GHL note, and booking record end to end.
8. Promote the same verified SHA to production. Run the read-only smoke command
   again against production with `--expected-sha` and record its output. The
   health endpoint derives this value from Vercel's `VERCEL_GIT_COMMIT_SHA`;
   absence or mismatch fails the release check.

## Stop and rollback conditions

- Stop promotion if CI, health, migration advisors, tenant isolation, public
  CORS, authentication, lead persistence, GHL attribution, or Retell verification
  fails.
- Roll back application code to the last known-good deployment. Do not attempt
  an automatic destructive database rollback.
- Preserve locally captured leads if GHL fails. Use `status`,
  `last_forward_error_code`, and any retained `ghl_contact_id` to reconcile;
  background retry remains post-MVP.
- Never manufacture a Supabase Auth identity. Provision only an existing
  provider-issued Auth user through `scripts/provision_customer.py`.

## Release evidence to retain

- Candidate and deployed SHA
- Full pytest and health-check output
- Migration list and Supabase advisor output, with secrets removed
- Preview and production read-only smoke output
- Designated tenant ID and opaque lead/call/booking identifiers
- CI and deployment URLs
- Any rollback or reconciliation action taken
