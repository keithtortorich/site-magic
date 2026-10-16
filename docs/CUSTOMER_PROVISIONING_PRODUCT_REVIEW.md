# Customer Provisioning Product Review

**Accepted by:** Codex under the standing autonomy provision
**Date:** 2026-08-05
**Verdict:** The older provisioning specification is superseded where it accepts an arbitrary user UUID without proving that the user exists in Supabase Auth.

## Canonical Product Contract

1. Provisioning is an admin-only CLI. It is not a public endpoint and does not run from intake.
2. Required inputs are customer email, tenant ID, and role. Supported roles are exactly `owner`, `manager`, `dispatcher`, and `viewer`.
3. The CLI resolves the email to exactly one existing Supabase Auth user and uses that provider-issued UUID. It never creates or generates an auth user ID.
4. Zero or ambiguous Auth matches fail closed without local writes. User invitation and self-serve signup remain out of scope.
5. Tenant existence and role validity are checked before writes. The `customer_users` and `tenant_memberships` changes occur in one transaction.
6. Repeating an identical active membership is a successful no-op with no duplicate. A different role or non-active status is an explicit conflict, not a silent privilege or status change.
7. Success requires an active user row, exactly one active membership at the requested role, successful `/auth/session`, allowed access to the assigned tenant, denied access to another tenant, and audit evidence for the authorization checks.
8. Operator output may show the customer email, tenant, role, and outcome, but never tokens, keys, credentials, or connection strings.

## Acceptance Matrix

| Scenario | Required outcome |
|---|---|
| Existing Auth user, valid tenant, valid role | Create one active membership; authenticated assigned-tenant access succeeds |
| Repeated identical request | Successful no-op; no duplicate membership |
| Unknown or ambiguous Auth user | Fail closed; no writes; actionable operator message |
| Unknown tenant | Fail closed; no partial records |
| Invalid role | Fail closed; list only the four supported roles |
| Assigned tenant access | Allowed according to role |
| Different tenant access | Denied with a recorded authorization audit event |
| Existing different role or status | Fail closed; no silent privilege or status mutation |

## Approved Operator Language

- Unknown user: `No Supabase Auth user found for <email>. Invite or create the user, then retry.`
- Unknown tenant: `Tenant <tenant_id> was not found. No changes were made.`
- Invalid role: `Role must be one of: owner, manager, dispatcher, viewer.`
- Conflict: `Membership already exists with role or status <value>. No changes were made.`
- Success: `Access provisioned for <email> as <role> on tenant <tenant_id>. Verify sign-in and tenant access before sending account-ready confirmation.`

## Customer-Facing Constraints

- Do not claim an owner dashboard exists or that an account is ready until the real token, session, and tenant-access checks pass.
- Do not claim the site or Angel widget is live, being deployed, or ready within a stated time unless a real status check supports it.
- Do not publish a `/dashboard/{tenant_id}` route or Lovable customization claim unless those capabilities exist.
- Use NetBuild.Pro in customer-facing URLs and copy. Keep `webstaffr` only for internal package and code identifiers.

## Codex Implementation Handoff

- Build `scripts/provision_customer.py` around email-to-verified-Auth-UUID resolution, tenant and role prevalidation, one transaction, identical-request no-op behavior, and fail-closed conflicts.
- Add tests for every acceptance row, atomic rollback, duplicate prevention, absence of random UUID generation, and different-role or status conflicts.
- Verify `/auth/session`, assigned-tenant access, cross-tenant denial, and audit evidence end to end.
- Do not implement self-serve signup, intake auto-provisioning, role management, email invitation, dashboard UI, or unsupported readiness copy.
