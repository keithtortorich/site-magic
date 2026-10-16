# Production Readiness Audit

Audit date: 2026-08-05
Supabase project: `ntbnenymyqiautaqhyhe`
Mode: read-only; no schema, data, Auth, credential, or deployment mutation

## Verified live state

Direct Supabase queries and metadata calls confirm:

| Evidence | Live result |
|---|---:|
| Supabase Auth users | 1 |
| Tenants | 1 |
| Customer users | 1 |
| Tenant memberships | 1 |
| Intake submissions | 1 |
| Appointments | 0 |
| Call events | 0 |
| Website leads table | Not yet applied |

The earlier zero-Auth-user blocker is resolved. The identity is provider-issued
and linked through the approved provisioning path. This audit intentionally
does not retrieve or record the user's email, UUID, token, or other identity
data.

The applied Supabase migration history currently ends at:

- `0016_customer_auth`
- `0017_customer_auth_rls`

Local PostgreSQL migration `0018_website_leads.sql` is therefore the next
pending production schema action.

The local candidate separates GHL CRM/booking activation from Leo outbound
messaging. General GHL credentials no longer implicitly enable automated SMS
or email; `LEO_OUTREACH_ENABLED=true` is required separately. Keep that flag
off for the MVP until the documented TCPA/DNC gate and outbound guardrails are
cleared.

## Supabase advisor result

Security advisors report no error-level findings. Informational notices for
RLS-enabled tables with no public policies match the intentional architecture:
FastAPI uses the trusted direct connection and the Data API is default-deny.

One warning reports leaked-password protection disabled. Before enabling any
email/password sign-in method, enable this Auth protection and verify the
customer login flow. If production remains provider-only, record that Auth
policy explicitly during activation.

Performance advisors report two unindexed foreign keys and unused indexes.
With one tenant and no live operational rows, these are not MVP blockers.
Reassess after real traffic rather than deleting indexes based on an empty
database.

Advisor remediation references:

- [RLS enabled without policy](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy)
- [Leaked password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)
- [Unindexed foreign keys](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys)

## Drift and remaining proof

Production still contains empty legacy `workflow_definitions` and
`execution_records` tables. Fresh local databases intentionally omit them.
They are RLS-enabled and empty, so this is cleanup drift rather than an MVP
runtime blocker. Any future removal is a separate reviewed, destructive schema
change.

The exact deployed SHA cannot yet be attested by the current production
`/health` payload because production predates the local release-attestation
change. The candidate adds `release` from `VERCEL_GIT_COMMIT_SHA`, and
`scripts/production_smoke.py --expected-sha` fails on absence or mismatch.

GitHub evidence confirms remote `main` is `6c57eafd89f458b6ea6229f2fd3ad4584ac81ac4`,
CI run `30942512004` passed on that exact SHA, and its Vercel deployment status
is successful. The read-only production smoke passes the current health,
security-header, and canonical-brand checks. Exact-SHA HTTP attestation begins
with the next candidate because the current production health payload predates
that feature.

MVP completion still requires live evidence from the approved activation
sequence:

1. Apply reviewed migration `0018_website_leads.sql`.
2. Push and deploy the exact CI-passing candidate SHA to preview.
3. Run the read-only SHA-attested smoke checks.
4. Submit one designated tenant website request and verify its local row, GHL
   contact, tenant-attributed note, and status.
5. Place one designated Retell call and verify the tenant-scoped call event,
   GHL note, appointment, and booking outcome.
6. Promote the same SHA and repeat the read-only production smoke check.

No step above should manufacture an Auth identity, expose a credential, revive
Hermes commit `0d9b5ba`, or infer success from a Null integration.
