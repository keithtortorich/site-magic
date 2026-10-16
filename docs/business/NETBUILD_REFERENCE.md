# NetBuild.Pro Reference
**Companion to `docs/business/WEBSTAFFR_GOVERNANCE.md`  -  the minutiae, tables, and hex codes that don't belong in a prose governance document.**

This file is machine-checkable reference data: exact values, tables, current tiers, current stack. When the ideal state described in governance changes, this file's numbers should be checked against it. When only an implementation detail changes (a hex code, a vendor, a table row), only this file changes.

Live status, blockers, and session work belong in TASKS.md, not here.

Last Updated: 2026-08-06

---

## Brand Name

**NetBuild.Pro**  -  all customer-facing, marketing, investor, and brand surfaces.

Internal/technical contexts may use "WebStaffr" or "WS4" for code, package names, and repo history. Never in customer-facing copy.

---

## Color Palette

### Primary
| Color | Hex | Purpose |
|-------|-----|---------|
| Rust/Orange | #C85A28 | "NetBuild" wordmark, primary headlines, primary CTAs |
| Gold | #D4A574 | "Pro" wordmark, accents, premium indicators |

### Neutral & Background
| Color | Hex | Purpose |
|-------|-----|---------|
| Charcoal | #2B2B2B | Body copy, primary text on light backgrounds |
| Dark Navy | #1A1A2E | Dark backgrounds, hero sections, dark mode |
| Light Gray | #F5F5F5 | Page backgrounds, card fills, muted surfaces |
| White | #FFFFFF | Pure white sections, luxury emphasis |

### Interactive States
- Rust Hover: #A04620 (pressed) | #8B3A1A (dark mode)
- Gold Hover: #C09458 (pressed) | #A8823D (dark mode)
- Error: #D1434E | Success: #2E7D32 | Warning: #F57C00 | Info: #0288D1

### Logo Usage
- Light backgrounds: "NetBuild" #C85A28 (rust) + "Pro" #D4A574 (gold)
- Dark backgrounds (navy/charcoal): "NetBuild" #D4A574 (gold) + "Pro" #C85A28 (rust)  -  inverted for contrast
- Monochrome: full wordmark #C85A28 (rust)
- Font: bold sans-serif

**Note:** these colors belong to NetBuild.Pro's own surfaces (marketing site, dashboard, investor materials). Tenant-generated customer sites use their own visual direction, not this palette. See Site Magic docs.

Source of truth: NetBuild.Pro Logo (approved 2026-08-06), Google Drive folder "NetBuild.Pro". Supersedes ADR-021's navy/royal-blue/orange palette. See `docs/DECISIONS.md` ADR-022.

---

## Pricing Tiers (Current)

All tiers include a free generated website for 30 days before the contractor is offered a subscription.

| Tier | Monthly Price | Includes | Gross Profit |
|------|--------------|----------|---------------|
| Office Staff | $497/mo | Service Advisor, 24/7 Receptionist, Lead Coordinator, Reputation Manager, Website Ops Manager | $432/mo (87%) |

**MVP scope (2026-08): Single tier only.** Business Manager and White-Glove removed for launch. `intake.py`'s `VALID_PLANS` accepts only `office_staff`. Future tiers planned after initial market validation.

Delivery cost includes AI inference, voice infrastructure, integrations, and operational overhead.

---

## Unit Economics (Current Model)

- Organic CAC: $100-$200/customer
- Paid CAC (future, gated on data): likely $200-$400
- Average customer lifetime: 16.7 months
- Monthly churn: 6%
- LTV (Office Staff tier): $7,200
- LTV:CAC ratio: 36x-72x
- Payback period: <1 month

### Year One Projection (Phoenix HVAC beachhead)
Cash-positive by month 3. Year-end: ~44 customers, ~$261K ARR, ~$115K cumulative cash. Downside case (5% conversion instead of 10%): ~22 customers, ~$131K ARR, still cash-positive if CAC holds.

### Year Two Projection (Phoenix + Tampa, month 13 launch)
~108 customers, ~$646K ARR, ~$489K cumulative cash.

### Market Sizing
TAM $14.6B (approx. 2.5M US home-service businesses). SAM $2.9B (digitally active segment). Year-one SOM ~$440K (Phoenix HVAC beachhead).

---

## Acquisition Channels (Current)

**Active (Organic, Founder-Led):**
- Direct outreach to HVAC contractors in Phoenix
- Referrals from existing customers
- Organic search

**Planned (Paid, gated on first 50 free-build conversion data):**
- Google Local Services Ads
- Facebook/Instagram for contractors
- Industry-specific marketplaces
- Expected CAC $200-$400; only turned on if LTV holds or improves at that CAC

### Metrics That Matter
Phone answer rate, demo booking and attendance rate, trial activation rate, free-to-paid conversion rate, monthly churn, net revenue retention.

### Metrics That Don't Move Decisions
Email sends, website visits, total signups (only paid conversions count).

---

## Team (Current)

| Name | Role |
|------|------|
| K. Michael Tortorich, MD | Founder  -  vision, strategy, go-to-market, approves all irreversible changes |
| Patrick Bukowski | Operations and client success, as needed |
| Wenjie Tong | Product architecture and engineering, as needed |

Engineering agents (Claude, Codex, Hermes) operate per `AGENT_COORDINATION.md` and `HERMES_CLAUDE_WORK_PLAN.md`; current lane assignments live in TASKS.md, not here.

---

## Technical Stack (Current)

- Backend: FastAPI (Python), hosted on Vercel (serverless)
- Database: Supabase Postgres (production), SQLite (local dev/tests)
- Voice: Retell AI
- AI reasoning/chat: Grok (xAI)
- CRM: GoHighLevel
- Field-service integrations: ServiceTitan, Jobber, Housecall Pro
- Canonical customer site frontend: Lovable "Site Weaver" (React, Vite, shadcn/ui)
- Multi-tenant model: every row scoped to `tenant_id`, no cross-tenant queries
- Public endpoints: `GET /sites/{tenant_id}`, `GET /intake/presets`
- Customer-facing: `POST /intake`, `POST /chat`
- Webhooks: `POST /book`, `POST /webhooks/ghl`, `POST /retell/webhook`
- Health: `GET /health`
- Integration pattern: Protocol interface + Null implementation + Real implementation + dependency injection at `webstaffr/app.py`

---

## Decision Authority (Current Process)

| Decision Type | Authority | Gate |
|--------------|-----------|------|
| Reversible code changes | Engineering (self-approve) | None |
| Deployment to production | Founder | Explicit approval before push |
| New dependencies | Founder | Explicit approval before merge |
| Schema or data model changes | Founder | Explicit approval before merge |
| Credential configuration | Founder | Direct action |
| Go-to-market direction | Founder | Strategic |
| Customer acquisition spending | Founder | Gated on conversion data |
| Pricing or tier changes | Founder | Strategic |

Full process detail (capability ladder, depth ladder, drift watch) lives in `AGENTS.md` and `CLAUDE.md`, not here.

---

## Risk Register (Current)

| Risk | Mitigation |
|------|-----------|
| Free-to-paid conversion below 10% | Gate paid spend on first 50 builds |
| Organic CAC doesn't hold at $100-$200 | Conservative modeling; paid spend only after proving organic conversion |
| Voice unproven on live call | Retell integration unit-tested; live phone test tracked in TASKS.md |
| Churn above 6% | Structured onboarding at day 1, 7, 30 |
| Regulatory exposure (calling/texting) | Email-first outreach; consent-based contact; do-not-call scrubbing |
| Competition from single-feature tools | Compete on full handoff chain, not one feature |
| Supabase availability incident | Dual-backend strategy; graceful 503s on DB failure |

---

## AI Agent Implementation Status

Live status belongs in TASKS.md. This table is the roster only, not a progress tracker.

| Agent | Tier |
|-------|------|
| Service Advisor | Office Staff |
| 24/7 Receptionist | Office Staff |
| Lead Coordinator | Office Staff |
| Reputation Manager | Office Staff |
| Website Operations Manager | Office Staff |

Future roles and packages are intentionally omitted until post-launch validation.

---

## Voice Rules (Mechanical)

- No em-dashes anywhere in NetBuild.Pro copy, internal or external. Hyphens or rewrite instead.
- Executive voice: formal contexts, use full "NetBuild.Pro."
- Commercial voice: customer-facing, "NetBuild.Pro" or "NetBuild."

---

## Where Things Live

- Governance (ideal state, prose, no minutiae): `docs/business/WEBSTAFFR_GOVERNANCE.md`
- This reference (exact values, tables): `docs/business/NETBUILD_REFERENCE.md`
- Decisions and rationale (ADRs): `docs/DECISIONS.md`
- Live status, blockers, current work: `TASKS.md`
- Session/operational history: `CLAUDE.md` addenda
- Site generator architecture: `docs/SITE_RENDERER_PLAN.md`
- System design: `docs/ARCHITECTURE.md`
- Agent coordination / worktree rules: `AGENT_COORDINATION.md`
- Training manual, founder's note, investor materials: `docs/business/`
