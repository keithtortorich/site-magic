# Claude Product/UX/Coherence Plan

**Status:** Proposed for founder approval before execution
**Date:** 2026-08-04
**Depth:** D3, multi-session product/content architecture
**Owner:** Claude (product spec + copy). Codex validates technical feasibility of anything spec'd here before it's built.

## Why this doc exists

A "three-agent execution split" doc (`menage a trois.md`, Desktop) assigns Claude Code a product-director/UX-architect/copy role parallel to Codex's engineering lane. Codex's matching lane already has a scoped, approved-in-progress plan (`docs/CODEX_SECURITY_EXECUTION_PLAN.md`). This doc is the equivalent scoping pass for the product/UX lane — it did not exist before today.

This plan does not write final copy or screens yet. It defines what has to be *decided* before that work can start, and in what order, so nothing gets built twice or contradicts governance already locked in `DECISIONS.md`.

## Verified current state (checked before writing this)

- **Naming conflict is real and partially resolved.** `NETBUILD_GOVERNANCE.md` (Drive, canonical per founder 2026-07-30) uses NetBuild.Pro. The repo's Python package name, `intake.py`'s internal identifiers, and some older docs still say WebStaffr. TASKS.md 2026-08-04 records a brand rename pass already executed across docs/templates/tests, keeping the Python package name `webstaffr` intact on purpose (avoids import breakage). **Not fully resolved:** no single doc states which surfaces are still allowed to say "WebStaffr" (internal/package-level) vs. must say "NetBuild.Pro" (all customer-facing).
- **Launch tier is resolved.** Initial launch uses only Office Staff at $497/month with slug `office_staff` (ADR-026).
- **Which workers are real, checked directly:** Angel (chat, Retell voice, GHL, booking, intake), Sam (`workers/sam/router.py` — quotes), Rita (`workers/rita/router.py`), Leo (`workers/leo/router.py`) all exist as registered routers in the composition root. `AGENT_TEAM_PLAN.md` (2026-07-28) additionally proposes Reputation Manager, Marketing Coordinator, Growth Manager, Sales/Service Advisor extensions, Front Office Manager — none of those are built. Any product copy or dashboard spec must not describe unbuilt workers as available.
- **Owner dashboard does not exist yet.** No dashboard router, no dashboard API, no dashboard UI in the repo. Phase 3 below (Specify the owner dashboard) is pure spec work against nothing currently running — flag this to the founder explicitly so expectations match: this phase produces a spec Codex then implements, not a working feature.
- **Angel's conversation policy currently lives in `angel_prompt.md`** (health-checked, present, loaded). Phase 5 below (Perfect Angel's behavior) is a revision/extension of that file, not a from-scratch write.
- **Pricing conflict**: this doc's Phase 6 recommends a single $997/mo "WebStaffr Complete" tier. That directly conflicts with the existing three-tier model (Essentials/Pro/Growth in code, Office Staff/Business Manager/White-Glove in `AGENT_TEAM_PLAN.md`) which ADR-024 already builds on (customer portal tied to Business Manager tier). **This is a founder pricing/product decision, not something Claude decides unilaterally** — flagged as an open question below, not pre-resolved in this plan.

## Execution sequence

### Phase 1: Lock the product (blocks everything else)

Cannot proceed until the founder resolves, in order:

1. **Brand name surface rule — RESOLVED 2026-08-04.** NetBuild.Pro is the single canonical brand name, everywhere: all customer-facing copy, all docs, all internal references going forward. No surface is exempt. The one carve-out: the Python package name `webstaffr` and internal code identifiers stay as-is — not customer-visible, renaming risks import breakage, no product value in touching it. This matches the rename pass already executed 2026-08-04 (TASKS.md). Any doc, template, or string still saying "WebStaffr" outside the package/code-identifier layer is stale and should be corrected on next touch, not left as an accepted exception.
2. **Tier name and price reconciliation — RESOLVED 2026-08-09.** Office Staff at $497/month is the only initial-launch tier and uses slug `office_staff`. See ADR-026.
3. **Single-tier launch.** Business Manager, White-Glove, and legacy Essentials/Pro/Growth packaging are deferred until after initial market validation.
4. **ICP, included/excluded services, supported trades, fair-use boundaries.** Not yet written anywhere in the repo. New content, needs founder input on scope (which trades WebStaffr/NetBuild.Pro actually supports today vs. roadmap).

Once (1)-(4) are answered, Claude writes a single locked-product reference doc (`docs/PRODUCT_LOCK.md`) that Phases 2-6 below cite instead of re-deciding.

### Phase 2: Onboarding experience spec

Spec every screen listed in the source doc (account creation through final launch approval) against the *actual* intake fields already defined in `intake.py` and `INTAKE_FORM_PHASE2_CANONICAL.md` — not a hypothetical new form. Where the source doc's 14-screen flow doesn't match the current intake schema, reconcile against the existing schema rather than inventing new fields Codex would then have to build from scratch.

Deliverable: `docs/ONBOARDING_SPEC.md`, one section per screen, each field with label/explanation/required-optional/validation/default/error message/consuming worker.

### Phase 3: Owner dashboard spec

Spec only — no dashboard exists to audit yet. Deliverable: `docs/DASHBOARD_SPEC.md` covering the sections in the source doc (Today, Conversations, Leads, Appointments, Quotes, Website performance, Reviews, Integrations, Team notifications, Billing, Settings, Support), each with information hierarchy, empty/loading/error states, and which backend router/data each section reads from (Codex confirms feasibility per section before this is marked ready-to-build).

### Phase 4: Customer website copy rules

Extends work already partially done (2026-08-01 site renderer polish pass, 2026-07-29 debunked-stat removal, governance-linter runs). Deliverable: `docs/SITE_COPY_RULES.md` — codifies the no-fabrication rule already in CLAUDE.md, extends it to specific rules for hero messaging, CTAs, trust signals, emergency messaging, financing, Angel disclosure. Does not re-litigate governance already locked (em-dash ban, no placeholders) — cites `NETBUILD_GOVERNANCE.md` and ADR-020/021 instead of restating them.

### Phase 5: Angel conversation policy

Revises `angel_prompt.md` and the underlying policy logic. Deliverable: `docs/ANGEL_CONVERSATION_POLICY.md` covering each scenario in the source doc (new leads, emergencies, booking, angry callers, human-transfer, unsupported work, integration failures) with explicit "may say / may never say / must escalate" rules. Any rule requiring new backend logic (e.g., structured escalation triggers) gets flagged to Codex as a feasibility check, not assumed buildable.

### Phase 6: Offer and sales materials

Blocked on Phase 1's pricing-model decision. Once resolved, deliverable is `docs/OFFER_AND_SALES.md` (homepage offer, pricing page copy, demo/discovery scripts, objection responses, guarantee terms) built on whichever tier structure the founder confirmed.

## Completion standard

This plan is complete when Phase 1's product-lock doc exists and is founder-approved, and Phases 2-6 each have a founder-reviewed spec doc that Codex has feasibility-checked. It does not include writing final on-site copy or building the dashboard — those are separate D2/D3 execution passes that cite these specs.

## What this plan does not do

- Does not decide the pricing model (Phase 1, item 3) — founder call.
- Does not build the dashboard, onboarding flow, or any UI — spec only; Codex builds.
- Does not restate or override governance already locked in `DECISIONS.md` or `NETBUILD_GOVERNANCE.md`.
- Does not claim any unbuilt worker (Reputation Manager, Marketing Coordinator, etc.) is available in product copy.

## Required approval to begin

Approve Phase 1 only. Phases 2-6 are sequenced behind Phase 1's answers and get their own go-ahead once Phase 1's lock doc is drafted for review.
