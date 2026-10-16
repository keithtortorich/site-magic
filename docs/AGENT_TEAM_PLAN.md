# AGENT_TEAM_PLAN.md : Building the NetBuild.Pro Virtual Team

Status: Draft for founder review (2026-07-28). Doc-only; no code changes.
Supersedes nothing; complements `docs/MARKETING_COORDINATOR_PLAN.md` and `docs/LEAD_ENGINE.md`.

## 1. First-principles analysis of the "Virtual Team Implementation Package"

The founder supplied a 9-agent no-code blueprint (Voiceflow + Make.com + Airtable + Twilio + OpenAI). Verdict, from first principles:

**What the package gets right (keep):**
- The role taxonomy. Nine front-office roles (Receptionist, Lead Coordinator, Reputation Manager, Sales Consultant, Service Advisor, Marketing Coordinator, Growth Manager, Website Ops, Front Office Manager) is a sound decomposition of what a home-service business actually needs. It maps almost one-to-one onto NetBuild.Pro's own AI-employee product vision.
- The sequencing logic. Receptionist first (answer every call), then speed-to-lead, then revenue roles (reviews, quotes), then marketing, then orchestration last. Revenue-nearest first is correct.
- The operating discipline. Launch checklists, one-agent-at-a-time, green-light metrics before moving on, daily/weekly/monthly maintenance cadence. Worth adopting as process.
- The metrics. Missed-call rate, sub-2-minute lead response, 100% review response, escalation rate under 10%. These become NetBuild.Pro's per-tenant success metrics.

**What the package gets wrong for NetBuild.Pro (discard):**
1. **Wrong premise.** The package assumes a founder with nothing built, wiring up rented tools for one business. NetBuild.Pro already has a production backend that IS the receptionist: Angel (chat live with real Grok replies, Retell voice path, GHL sync, booking, intake, tenant-scoped Postgres, deployed on Vercel, 189/189 tests, 9/9 health checks). Following the package means rebuilding a worse copy of what already runs.
2. **Wrong architecture: single-tenant vs. product.** The package builds one team for one business. NetBuild.Pro is a multi-tenant product that sells this team to many businesses. Every agent must be tenant-scoped, repeatable, and provisioned from intake -- a Voiceflow flow hand-built per customer cannot be.
3. **Duplicate, competing stack.** Voiceflow duplicates Angel. Twilio duplicates Retell (the chosen voice vendor). Airtable duplicates GHL (sole CRM per `docs/LEAD_ENGINE.md`). Make.com duplicates backend routes and GHL workflows. Adopting any of these violates the new-dependency approval rule, splits the data model, breaks tenant isolation, and adds ~$335/mo of redundant spend.
4. **Governance violations throughout.** The package's scripts and copy contain emojis, em-dashes, and "AI receptionist" framing -- all banned in NetBuild.Pro customer-facing surfaces. Its budget numbers and its "9 agents in 90 days" timeline are marketing fiction, not engineering estimates.
5. **Some roles are already moot.** "Website Ops Manager" (uptime, backups, security) is mostly absorbed by Vercel + Supabase managed infrastructure plus `health_check.py`. "Growth Manager" (SEO, schema, listings) is substantially built into the in-repo site renderer already.

**Core conclusion:** adopt the org chart, reject the tool stack. Each agent becomes a sibling worker router in `create_app()` next to Angel's -- exactly what the composition-root rebuild was designed for -- and each maps to a pricing tier (Office Staff $497/mo, Business Manager $2,497/mo, White-Glove $5,000+/mo custom).

## 2. Role mapping: package agent → WebStaffr reality

| # | Package agent | NetBuild.Pro equivalent | State | Tier |
|---|---|---|---|---|
| 1 | 24/7 Receptionist | **Angel** (chat + Retell voice + booking + intake) | Built; blocked only on GHL/Retell credentials | Office Staff |
| 2 | Lead Coordinator | GHL workflows + Angel follow-up + AOKAI scoring (`docs/LEAD_ENGINE.md`) | Sync code built, no-op until `GHL_API_KEY` set | Office Staff |
| 3 | Reputation Manager | New worker: review requests + response drafting via GHL SMS/email | Not started | Business Manager |
| 4 | Marketing Coordinator | Planned in `docs/MARKETING_COORDINATOR_PLAN.md` | Planned; D4 vendor decision open | Business Manager |
| 5 | Growth Manager | Site renderer SEO/schema (built) + GBP/listings management (later) | Partially built | Business Manager |
| 6 | Website Ops | Vercel/Supabase managed + `health_check.py` + external uptime ping | Effectively done | All tiers (invisible) |
| 7 | Sales Consultant | `/book` (built) + quote generation from trade presets | Booking built; quotes not started | Business Manager |
| 8 | Service Advisor | Angel prompt/intent extension: pre-diagnosis questions, urgency escalation | Not started; no new worker needed | Business Manager |
| 9 | Front Office Manager | Orchestration layer across workers in the composition root | Last; by design | White-Glove |

## 3. Build plan (phased, revenue-first)

**Phase 0 -- Ship the MVP (now; everything else waits per CLAUDE.md).**
Angel end-to-end live for a real tenant: set `GHL_API_KEY`/`GHL_LOCATION_ID`/`GHL_WEBHOOK_SECRET`/`RETELL_WEBHOOK_SECRET` (founder decision -- paid vendors, currently deferred), run the onboarding smoke test, verify voice via Retell, fix the 3 queued Agency Site issues when Lovable credits are added. Exit: one paying-tier flow works intake → site → Angel → booked job in GHL.

**Phase 1 -- Lead Coordinator (first post-MVP; highest ROI, least new code).**
Mostly configuration, not code: GHL workflows for instant SMS/email acknowledgment, follow-up sequences, appointment reminders; AOKAI-tiered routing per `docs/LEAD_ENGINE.md`. Backend work limited to webhook handling already in scope. Precondition: TCPA/DNC compliance review before any automated outbound (open flag in LEAD_ENGINE.md).
Metric: every lead acknowledged in under 2 minutes.

**Phase 2 -- Reputation Manager (first new sibling worker; proves the pattern).**
`workers/reputation/` with its own router in `create_app()`: job-completion trigger (GHL webhook) → review request via GHL messaging → founder-approved response drafts for incoming reviews. Follows all invariants: Protocol + Null default + `*NotConfiguredError`, tenant-scoped queries, no CORS on server-to-server routes, no fabricated review content ever.
Metric: request within 24h of job completion; 100% of reviews get a response draft.

**Phase 3 -- Sales Consultant + Service Advisor (Angel capability extensions, not new workers).**
Quote generation from trade presets + intake data (ranges only, never fabricated specifics); pre-diagnosis question sets per trade feeding the booking payload; urgency detection → escalation. Extends Angel's prompt assets and `/book` flow.
Metric: technician arrives with structured pre-diagnosis info; quote turnaround same-day.

**Phase 4 -- Marketing Coordinator (per existing plan).**
Execute `docs/MARKETING_COORDINATOR_PLAN.md` as written: new sibling worker, D4 SMS/email vendor decision required first (founder). Social media bridge code already exists in `integrations/social_media/`.

**Phase 5 -- Growth Manager completion + Front Office Manager.**
Growth: GBP/listings sync, per-tenant SEO reporting on top of the renderer's existing schema work. Front Office Manager: cross-worker orchestration (handoffs, escalation routing, per-tenant reporting) -- built last, in the composition root, once there are multiple workers worth orchestrating. This is the White-Glove tier's backbone.

## 4. What to salvage from the package verbatim

- Launch checklist + green-light/red-flag gates → adapt into `DEPLOYMENT_CHECKLIST.md` per-worker sections as each worker ships.
- Maintenance cadence (daily log review, weekly metrics, monthly ROI) → becomes the ops runbook per tenant.
- Conversation scripts → usable as raw input for Angel prompt assets ONLY after a governance pass (strip emojis, em-dashes, "AI" language; verify any statistic independently -- the package cites none).
- CRM field mapping → cross-check against the existing intake schema; likely already covered.

## 5. Founder decisions this plan needs (nothing else blocks)

1. Timing of GHL + Retell paid credentials (already tracked in TASKS.md Pending) -- gates Phase 0 exit.
2. D4 SMS/email vendor -- gates Phase 4 only.
3. Confirmation of tier-to-role mapping in Section 2 (product/pricing call, not engineering).

Everything else is self-approvable engineering inside existing invariants.
