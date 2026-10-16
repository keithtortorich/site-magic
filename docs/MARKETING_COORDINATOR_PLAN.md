# Marketing Coordinator — Combination Plan

**Status: plan only. No implementation.** Execution is post-MVP gated per `CLAUDE.md` scope.
Drafted 2026-07-25 against WS3.3, carried forward unchanged in substance into WebStaffr 4.0's
`docs/` -- only file paths and migration numbers below were updated to match this repo's
renumbered migrations (see `docs/DECISIONS.md`'s WebStaffr 4.0 rebuild entries). The founder
decisions and phase plan below are still the live plan; nothing here has been re-litigated.

## What this is

One AI-employee role — the **Marketing Coordinator** — built by combining two proven pieces
already in hand, employed inside WebStaffr. It is the crux of the upgrade path to the
Business Manager Tier.

- **`marketing-director-gtm`** (Cowork skill; canonical copy: `~/Desktop/marketing-director-gtm.skill`,
  a single `SKILL.md`) — the **strategy brain**. Intake → live competitor/market research →
  positioning recommendation → 3–5 ad copy variants → platform-specific ad assembly
  (Meta / Google / LinkedIn) → weekly KPI monitoring with an optimization protocol.
  Human approval gate on ad copy only.
- **`social-media-marketing-machine`** (SMMM; its own repo — github.com/keithtortorich/Marketing-Coordinator,
  not carried into this repo, see `docs/DECISIONS.md` ADR-012) — the **execution body**.
  Campaigns, posts with immutable version history, approval state machine (structurally
  enforced), calendar/scheduling, publishing adapters for 9 organic platforms, analytics
  snapshots with DB-enforced dedup, audit log, multi-tenant orgs, Celery background workers,
  a multi-provider AI layer, and an execution-trace graph.
- **WebStaffr 4.0** (this repo) — the **employer**. Tenant identity, the customer intake
  record, Angel, attribution, and the already-built integration bridge
  (`social_media_mounts` / `social_media_intents` + `execution_nodes` -- see
  `webstaffr/migrations/0006_social_media.sql`, `0007_execution_nodes.sql`, and
  `webstaffr/workers/angel/social_media_router.py`).

## Why combining beats either piece alone

- The skill produces strategy and copy but **publishes nothing and measures manually**.
- SMMM publishes and measures but has **no strategy brain** deciding what to say.
- WebStaffr owns the two things neither has: **intake data** to seed strategy without
  re-interviewing the customer, and **attribution** to measure booked jobs — not clicks —
  so the weekly report can speak actual ROI. That closed loop is the Business Manager Tier
  value proposition.

## What already exists (verified in-repo, not assumed)

| Capability | Where | Status |
|---|---|---|
| Customer business data | `webstaffr/intake.py` | Covers most of the GTM skill's required intake (biz_name, industry, service_area, services, differentiator, tagline; optional competitors, tone, brand words/colors, years in biz, GBP link). Missing only: target customer profile, marketing budget, timeline. |
| Tenant ↔ SMMM-org bridge | `webstaffr/workers/angel/social_media_router.py`, migrations 0006/0007 | Built, auth hardened, tested. |
| Approval workflow | SMMM `ApprovalStateMachine` + `Post` guard | Built; state changes are structurally enforced. |
| Organic publishing | SMMM `social/platforms/` | 9 adapters: facebook, instagram, linkedin, x, threads, tiktok, pinterest, youtube, google_business. |
| AI provider layer | SMMM `ai/providers/` | claude, openai, gemini, grok, ollama, hermes. |
| Long-running jobs | SMMM Celery workers | Built. |
| Execution trace | Both sides (`execution_nodes`) | Built both sides; recovery is deterministic from the graph. |
| Analytics snapshots | SMMM `analytics` | Built, dedup enforced by DB constraint. |
| Booked-job attribution | `webstaffr/attribution.py` | Built. |
| **Live web research** | — | **Not built anywhere yet; vendor decided (D1) — SearXNG.** See below. |
| **Paid-ads platform APIs** | — | **Not built anywhere.** Deliberately deferred (Phase 4). |
| **Two-way client comms channel** (SMS + email) | — | **Not built anywhere.** No re-contact mechanism exists in this repo today. Founder-directed shared infrastructure (see below); vendor choice (D4) recommended 2026-07-27 (Twilio + Postmark, see Founder decisions), awaiting sign-off. |

## Architecture (recommendation — approve at build start)

**Placement rule: WebStaffr 4.0 stays the source of truth for tenants, workflow, and approval
routing; SMMM runs everything long-running.**

Why: WebStaffr 4.0 is Vercel serverless — its own invariant forbids assuming a persistent process,
and the GTM research pipeline is a ~30–45 minute multi-stage job. SMMM already has exactly
the machinery that job needs (Celery, AI providers, agent/task/prompt-template models). So
the Marketing Coordinator's engine is an **SMMM agent pipeline**; WebStaffr 4.0 triggers it through
the existing mount/intent bridge and both sides record the trace. Identity models stay
separate per SMMM's own `INTEGRATION_PLAN.md` — the mount binds
tenant ↔ org once; no Clerk retrofit into WebStaffr 4.0.

Per-customer flow:

```
1. Mount once            WebStaffr tenant -> SMMM org        (existing bridge)
2. Kickoff               WebStaffr intake + tier questionnaire (below) -> intent (existing endpoint)
3. Strategy run          SMMM pipeline: research -> positioning -> 5 copy variants
   3a. Gap hit            missing field -> WebStaffr re-interview request -> client (email/SMS,
                          per their preferred_contact_channel) -> field filled or omitted
4. Approval gate         SMMM approval workflow (human, copy only — matches the skill)
5a. Organic path         approved posts -> schedule -> publish via adapters (automated)
5b. Paid path            assembled ad packages, ready for manual posting (skill's own model)
6. Weekly loop           SMMM analytics + WebStaffr attribution -> weekly report + optimization
                         memo; autonomous pause/boost only post-approval, per skill protocol
```

The GTM `SKILL.md` stages become **versioned prompt templates** inside SMMM (the
`prompt_template` model exists for this). At build start the skill file is vendored into the
repo verbatim as the canonical prompt source — same treatment `angel_prompt.md` got.

### Research vendor: SearXNG (decided 2026-07-25 — open source, per founder direction)

**SearXNG** — a self-hosted, open-source metasearch engine (aggregates Google, Bing,
DuckDuckGo, Brave, and others behind one query, JSON output, no per-query API fee, no
usage tied to a third party's commercial terms). It runs as one more container next to the
ones SMMM already defines in `docker-compose.yml` (`postgres`, `redis`, `minio`, `backend`,
`celery_worker`) — no new hosting platform, just a new service in infrastructure that
already exists. The Phase 1 research module calls it the way it'd call any other internal
service.

Honest tradeoff, stated plainly: it's self-hosted, so it's WebStaffr's instance to run —
occasional tuning against upstream engines' own rate limits, no vendor support line to
call. That's the cost of open source over a paid search API; worth it given the founder's
explicit steer and the very small, controlled query volume a kickoff research run needs.

## Business Manager Tier kickoff questionnaire (decided 2026-07-25)

When a client chooses (or upgrades to) the Business Manager Tier, a marketing kickoff
questionnaire fires — separate from the base site intake, which stays unburdened. It
collects, per client:

- **Social presence audit** — for each major platform (Facebook, Instagram, LinkedIn,
  Google Business, plus the rest of SMMM's adapters as applicable): do they have an
  account, and what's their handle/page name on it?
- **Setup service opt-in** — for platforms they *don't* have: would they like WebStaffr to
  set the account up for them? (Connecting existing accounts happens via OAuth through
  SMMM's `platform_account` flow — credentials are never collected in a form or in chat,
  per the security baseline. Setup of brand-new accounts is an assisted onboarding
  service, scoped at build time.)
- **Google Business Profile** — URL and access status (base intake already collects
  `has_gbp`/`gbp_url`; the questionnaire confirms and fills gaps rather than re-asking).
- **Marketing fields the GTM engine needs** — target customer profile, marketing budget,
  timeline.
- **`preferred_contact_channel`** — `email` / `sms` / `either`, used by the comms channel
  below.

Answers land in WebStaffr through the same validated intake path (extending the existing
intake machinery, not a parallel store) and seed both the mount (which platforms) and the
strategy run (budget, audience, timeline).

## Phases (all post-MVP)

- **Phase 0 — Gate & prep.** MVP ships (hard gate). Founder approves the two open vendor
  choices (D1, D4-vendor). No Marketing Coordinator code before this clears. *Note:* the
  comms channel itself is exempt from this gate per the founder's D4 timing decision — it's
  MVP-adjacent shared infrastructure and can be built as soon as its vendors are approved.
  *Size: S.*
- **Phase 1 — Strategy engine.** GTM stages 1–3 as an SMMM pipeline: intake mapper
  (WebStaffr intake → GTM intake form), research module (needs D1), assessment report,
  5 copy variants stored as campaign drafts wired to the approval workflow.
  *Done =* a real tenant's intake produces an assessment + variants awaiting approval, every
  step traced in `execution_nodes`. *Size: L — the largest phase.* See "Phase 1 detailed
  breakdown" below for the piece-by-piece build sequence and risk ranking.
- **Phase 2 — Organic execution end-to-end.** Approved variants → schedule → publish via
  adapters → visible in calendar; trace on both sides; per-tenant weekly cadence config.
  *Done =* one approved post reaches a test platform account with a full trace. *Size: M.*
  *Sequencing note (2026-07-27 review):* consider standing this phase up first, with
  placeholder/dummy strategy content, ahead of finishing Phase 1's research module — it
  validates the approval/publish/trace plumbing (already mostly built) at far lower cost
  than debugging it simultaneously with a brand-new research pipeline. See risk review below.
- **Phase 3 — Ads assembly + measurement loop.** GTM stage 4 (platform-specific paid-ad
  packages with manual-posting instructions) and stage 5 (weekly KPI report joining SMMM
  analytics with WebStaffr attribution; optimization memos; autonomous optimization strictly
  post-approval). *Done =* a weekly report generates for a live tenant with real numbers or
  explicit "unavailable" markers — never invented ones. *Size: M.*
- **Phase 4 — Business Manager Tier packaging.** Tier gating/billing, productized
  white-label report path, optional paid-ads API automation (each ads API is its own vendor
  decision). Deliberately not designed in detail here.

### Phase 1 detailed breakdown (added 2026-07-27, subagent-researched)

Sequenced by realistic complexity, smallest to largest. Grounded in the actual `intake.py`
inventory, the live `marketing-director-gtm` `SKILL.md` content, and the existing
`execution_nodes` schema — not just the summary above.

1. **Intake mapper — smallest, mostly data plumbing.** Most fields already exist per the
   "what already exists" table; only budget, timeline, and target-customer-profile are
   genuinely new, landing through the existing validated intake path. Real wrinkle:
   reconciling the skill's fixed business-type enum against this repo's freer-text
   `industry` field, and making sure `competitors`/`license_number` stay usable internally
   for strategy without ever reaching generated output (never-leak list).
2. **Assessment report + 5-variant copy generation — moderate.** Reuses SMMM's existing
   multi-provider AI layer; new work is templating the skill's prompt content into SMMM's
   existing `prompt_template` model, not new infrastructure. Main risk is rule-compliance
   (never inventing social proof, always labeling benchmarks as benchmarks) — needs careful
   template design and a validation pass on generated output, not just a good prompt.
3. **Approval workflow wiring — small in code, high-stakes.** The state machine already
   exists and is structurally enforced; the new work is making sure every draft campaign
   the pipeline writes carries the correct tenant/org scope. This is exactly the shape of
   bug flagged in "Landmines" below (publish task, no org filter) — write the tenant-scoping
   test *before* the write path, not after.
4. **Execution tracing — small, easy to under-build.** The table exists on both sides
   already; the work is making sure every distinct step (mapped, query issued, result
   retrieved, assessment generated, each variant generated, draft created) actually writes
   a correctly-parented node, so "every step traced" is verifiable by querying the graph,
   not just claimed.
5. **Re-interview trigger within Phase 1 — small, currently ambiguous.** Given D4 (vendor,
   now resolved below) still needs the comms channel itself built, Phase 1's honest scope
   is: log the gap, omit the field, queue the re-interview request as a record — without
   necessarily sending it yet if the comms channel isn't live. State this explicitly at
   build time so nobody builds a stub that silently drops the field forever instead of a
   real, if not-yet-delivered, queued request.
6. **The research module — by far the largest single unknown, and the true critical path.**
   The only piece with no existing code to lean on anywhere in either repo. Two problems
   live inside it: standing up SearXNG itself (comparatively mechanical — config, health
   checks, network wiring into SMMM's existing `docker-compose.yml`), and the actual
   research logic — constructing search queries from intake data, deciding which results
   are worth retrieving in full, fetching and parsing real page content, and turning that
   into a structured report where every claim traces back to something actually retrieved
   (making the "cite only reviews actually retrieved" rule real, not just stated). Most
   likely piece to blow the phase's timeline: rate-limiting or blocking by the upstream
   engines SearXNG aggregates, review/competitor sites blocking content retrieval, or
   output that's technically well-sourced but still thin.

**Build-order recommendation:** prove the research module works in isolation, on one real
business profile, before writing a line of the copy-generation prompts — everything
downstream (assessment, variants, approval writes, trace) depends on it producing real,
sourced output, so testing those pieces against fixtures first just defers the real risk
rather than retiring it. Build the intake mapper and tracing scaffolding in parallel with
that, since both are small and well-understood regardless of how research turns out.

## Rules that override the skill

The GTM `SKILL.md` contains fallback behaviors that violate this repo's no-fabrication
invariant. **Where they conflict, `CLAUDE.md` wins:**

| `SKILL.md` says | This build does |
|---|---|
| No customer wins → invent social proof ("Trusted by 5,000+ homeowners") | Never invent. Trigger a re-interview request instead (below). Omit the claim only while the answer is still outstanding. |
| Ad matrix includes "estimated reach / estimated CTR" | Label as industry benchmark, never present as measured. |
| Research mines reviews for themes | Cite only reviews actually retrieved; no invented ratings or quotes. |
| Budget "not specified" → assume $500–2,000/month | Never assume. Same re-interview trigger as above. |

Also: `license_number`, `lead_routing`, `approver`, `competitors` remain on the never-leak
list — they may inform strategy internally but never appear in generated copy or reports.

### Client comms channel: two-way, shared, tenant-aware (founder-directed 2026-07-25)

Not just a re-interview mechanism — a **general two-way communication channel** between
each client and WebStaffr, covering everything: site-generator issues, ad-service issues,
missing-data questions, any problem whatsoever. Built once in this repo as shared
infrastructure; the site generator, the Marketing Coordinator, and general support all use
the same channel.

**Outbound — re-interview instead of fabrication or silent omission.** Omission (this repo's
existing default) is the right *interim* state but not the end state — a client with a
real testimonial or a real budget shouldn't have that fact permanently missing because it
wasn't captured on the first pass:

1. A generation step hits a missing field it needs (no customer wins for social-proof
   copy, no budget for spend recommendations, no differentiator for positioning).
2. WebStaffr queues a **re-interview request** for that specific field — short, targeted, not
   a full re-intake — sent over the client's chosen channel (**email and/or SMS**, via a
   `preferred_contact_channel` field: `email` / `sms` / `either`).
3. Until answered, generation proceeds with the field omitted (never invented) — the
   no-fabrication default holds as the safe fallback; it's just no longer permanent.
4. The answer updates the intake record through the same validated path as the original
   intake, and anything already generated that depended on the field is flagged for
   regeneration or re-approval — never silently patched in.

**Inbound — a number they can just text.** A dedicated SMS number the client texts
directly, any time, about anything. WebStaffr recognizes the sender: the inbound `From` number
is matched against the tenant's intake `phone` (a required intake field, so every tenant
has one on record). Recognized → the message is logged as a problem/request against that
tenant and routed (and can answer an outstanding re-interview question if one is pending).
Unrecognized number → held in a general triage queue, never guessed into a tenant. Email
replies work the same way, keyed by sender address against the intake `email`.

**Implementation shape (for the build session, not decided in detail here):** an
intake-adjacent capability — outbound message record + inbound message record, keyed
to `tenant_id`/`submission_id`, raw-SQL per this repo's persistence idiom, vendor client
behind the usual `Protocol` + `Null*` + `*NotConfiguredError` pattern so everything stays
testable unconfigured. Webhook endpoints for inbound (server-to-server, no CORS, verified
sender — same treatment as `/webhooks/ghl`).

## Landmines carried forward (from SMMM's own `HANDOFF.md` — binding on all build sessions)

- Enum labels in SMMM's DB are UPPERCASE member names. SMMM's `docs/sql/smm_gtm_bridge.sql`
  is design-intent only with known-wrong literals — never copy from it.
- A green SMMM suite proves less than you think — test the symptom, not the code just written.
- Each repo keeps its own persistence idiom (WebStaffr raw SQL, SMMM async ORM); the bridge API
  is the only crossing point. Neither idiom crosses over.
- Tenant/org scoping is enforced at the repository layer on both sides — the worst prior bug
  was a publish task looking up rows by primary key with no org filter.

## Founder decisions

**Decided 2026-07-25 (not re-litigated):**

- **D2 — Launch platforms: the majors, all of them.** Facebook, Instagram, LinkedIn,
  Google Business as the covered set; the remaining SMMM adapters (X, TikTok, Pinterest,
  Threads, YouTube) available per-client where the questionnaire shows they have or want
  them. Supersedes the earlier LinkedIn-only-if-B2B recommendation.
- **D3 — Tier kickoff questionnaire.** A separate marketing questionnaire at Business
  Manager Tier selection/upgrade, per the section above — not added to the base site
  intake. Scope grew from "3 missing fields" to the full social-presence audit +
  setup-service opt-in.
- **D4 (scope + timing) — Two-way client comms channel.** Founder-directed: a dedicated
  SMS number clients text directly (plus email), tenant-recognized, handling any problem
  or question across all WebStaffr services — including the site generator, which needs it
  already. Shared infrastructure, not gated behind the Marketing Coordinator build.
- **D1 — Web-research vendor: SearXNG.** Open source per founder direction; see rationale
  above. This approval (open-source category, self-hosted, no per-query fee) is the
  specific-choice sign-off `CLAUDE.md`'s security baseline requires for a new dependency.

**D4 (vendor) — SMS + email provider — RECOMMENDED 2026-07-27, awaiting founder sign-off:**

- **SMS: Twilio.** Compared against Telnyx, Plivo, and Vonage — pricing is close enough
  across all four at this repo's expected volume (single digits to low dozens of Business
  Manager Tier customers; likely under $20-50/month total either way) that it shouldn't
  drive the choice. Twilio wins on reliability and support maturity, which matters most for
  a channel real customers depend on for support — unlike D1/SearXNG, this is not a place
  to optimize for lowest cost over proven reliability. Matching inbound texts to a stored
  `phone` field is simple string comparison once numbers are normalized to E.164 on the way
  into the database — that normalization has to happen at intake, not just at the webhook.
  One customer-side edge case, not a vendor problem: VOIP-only business lines (Google Voice
  etc.) sometimes can't send SMS at all; those customers would fall back to email.
  **Real friction, not paperwork theater:** US carriers require one-time "10DLC" business
  registration before a number can send/receive business texts (~$4-15 one-time + small
  monthly fee, basic business info required, a few business days to clear). This applies to
  any SMS vendor, not just Twilio, so it isn't avoided by picking a different one — start
  registration as soon as this choice is approved, since it has real lead time.
- **Email: Postmark.** SendGrid is worth actively avoiding — independent reviews flag real
  deliverability problems (mail landing in spam) since its acquisition by Twilio, a serious
  risk for a channel where "did the re-interview request even arrive" matters. Resend is a
  reasonable outbound-only alternative but its inbound-email parsing (required here, since
  replies get matched by sender address) is newer and less complete than needed out of the
  box. Postmark is built specifically around transactional deliverability (refuses bulk
  marketing mail to protect its sending reputation) and its inbound parsing hands over a
  fully parsed email in one webhook — a direct match for this repo's requirement. ~$15/month
  to start; no special registration needed beyond a verified sending domain (standard DNS).
- Both are pay-as-you-go, no contract — low migration risk if volume grows. This is still a
  new-dependency approval per `CLAUDE.md`'s security baseline and needs explicit founder
  sign-off before either is wired in behind the `Protocol`/`Null*`/`*NotConfiguredError`
  pattern described above.
- Deferred to Phase 4: pricing/tier definition, paid-ads API vendors.

## Success criteria (adapted from the skill, made checkable)

- Assessment report identifies ≥1 genuine positioning gap vs. researched competitors, with
  sources cited.
- 5 copy variants generated per campaign; ≥2 meet service-industry benchmark CTR once live
  (>1.5% Meta, >3% Google Search).
- Organic posts flow intake → approval → published with zero manual steps besides approval.
- Weekly report ties spend to attributed calls/bookings via WebStaffr attribution, and every
  number in it is real or explicitly marked unavailable.
- Paid-ad packages pass platform validation (character limits, image specs) without edits.
- No generated copy or report ever contains an invented fact — a missing field either
  triggers a re-interview request or is omitted; it is never filled with plausible filler.
- A client texting the dedicated number from their intake phone number is recognized and
  their message logged against the right tenant; an unrecognized sender lands in triage,
  never mis-attributed.

## Risk review (2026-07-27, subagent pressure-test — not yet actioned)

A deliberate adversarial review of this plan surfaced the following, ranked by real
production severity rather than by section order. Nothing here has changed the plan above;
these are flags for the founder and the eventual build session to weigh.

**Most severe — no described failure mode for a dead pipeline.** The plan states execution
tracing is "built both sides" and recovery is "deterministic from the graph," but nowhere
does it describe what actually happens when the trace desyncs — e.g. SMMM's Celery worker
dies mid-pipeline, or a webhook confirming a step never lands. A customer mid-kickoff-
questionnaire would have no visible status and, per the plan as written, neither would
WebStaffr's own operator. The plan's own landmine note ("a green SMMM suite proves less
than you think") is an implicit admission this boundary has already caused trouble once.
Worth a stated reconciliation/timeout mechanism before Phase 1 ships, not just before Phase 4.

**High — no cost ceiling on the AI layer.** A 30-45 minute multi-stage research+generation
run per customer, across a multi-provider AI layer, has no stated per-run token/cost cap,
retry limit, or budget alarm anywhere in this plan. A stuck loop or bad prompt template
could produce a surprise bill with nothing described to stop it.

**Medium-high — D4 is a hidden hard dependency of Phase 1, not a parallel track.** Phase
1's anti-fabrication guarantee ("omitted, never invented... just no longer permanent")
depends on the re-interview mechanism actually being able to send, which depends on the
comms channel being live, which depends on D4. Until the comms channel itself is built
(not just the vendor chosen), "no longer permanent" is, in practice, still permanent. This
doesn't change the design — omit-don't-fabricate is still correct — but it means the comms
channel build should not lag Phase 1 by much, despite being scoped as separate/parallel
infrastructure.

**Medium — Phase 1 before Phase 2 is a risk-ordering choice, not a technical necessity.**
Building the largest, least-proven piece (research, from scratch) before validating the
smaller, mostly-already-built piece (approval → publish, per the "what already exists"
table) means integration bugs in the approval/trace/scoping plumbing surface at the same
time as a brand-new research pipeline is also being debugged. See the Phase 2 sequencing
note above for the mitigation already folded into the phase list.

**Medium — incomplete-questionnaire behavior is unstated.** The plan doesn't say what
happens to a client who starts the Business Manager Tier questionnaire but never finishes
it — whether they're nudged, stuck indefinitely with a gap-heavy strategy, or something
else. Worth an explicit decision before Phase 1, not a default that emerges by accident.

**Lower — CTR success criteria conflate build completion with market response.** The
Phase 3 bullet ">1.5% Meta / >3% Google Search" ties a build milestone to ad performance
the software can't control (creative quality, targeting, vertical, seasonality). Recommend
reframing as a metric to *track* post-launch, not a gate on Phase 3 being "done" — the
process-oriented criteria elsewhere in that bullet (packages pass validation, weekly report
ties real spend to real attribution) are the actual completion criteria.

**Reviewed and found sound, not overblown:** the two-repo split itself (WebStaffr
serverless / SMMM stateful) and the "combining beats either piece alone" thesis both hold
up — the real risk lives in the missing operational details around the split (reconciliation,
cost caps, incomplete-questionnaire handling), not in the split's existence.

## What this plan deliberately does not do

- No implementation now — the post-MVP gate holds.
- No detailed Phase 4 (billing/tier) design.
- No dependency choices made beyond D1 (SearXNG) — D4's SMS/email vendor stays open.
- No identity-model merge — the deliberate seam from SMMM's `INTEGRATION_PLAN.md` stands.
