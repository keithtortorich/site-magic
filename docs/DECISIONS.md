# Architecture Decisions

## [ADR-001] Brand Color Customization for Rendered Sites

**Date:** 2026-08-01  
**Status:** Approved  
**Affects:** `site_data.py` (public projection), `site_render_router.py` (rendering), `site.css` (template)  
**Effort:** D3 (implementation 2-3 days)

### Problem

All customer sites render with a hardcoded blue palette (#2a6df5 primary, #101826 header). The intake form collects `brand_colors` (primary hex from business logo/brand), but this field is intentionally excluded from the public projection (internal use only).

- **User expectation:** Sites should reflect the business's brand colors.
- **Current reality:** All sites look identical in palette.
- **Tradeoff:** Adding brand_colors to the projection expands attack surface; omitting it keeps the projection minimal.

### Decision

**Expose `brand_colors` to the public projection and inject a dynamic palette at render time.**

1. Add `brand_colors` (nullable hex string) to `build_public_site_data()` output.
2. In `site_render_router.py`, generate a 5-color palette from the brand primary (primary, darker, lighter, neutrals).
3. Inject palette as CSS custom properties into an inline `<style>` block on every page.
4. Validate contrast ratios; log warnings if AA fails, but render anyway (don't block).
5. Test: contrast edge cases, mobile rendering, XSS prevention.

### Rationale

**Why expose it:**
- Direct customer-facing content (not internal ops data).
- Hex color string is low-risk (#rrggbb, no code injection).
- Personalization benefit outweighs minimal risk.

**Why inject dynamically:**
- Stateless rendering (no per-tenant CSS files).
- Fits Vercel serverless model.
- Contrast validation at render time catches bad brand choices.

**Why deterministic algorithm:**
- One primary → automatic palette (HSL-based darkening/lightening).
- Zero designer cost per tenant.
- Fallback to default if brand_colors is null.

### Implementation Stages

**Stage 1:** Add `brand_colors` to public projection + hex validation  
**Stage 2:** Palette generation function (primary → 5-color dict via HSL)  
**Stage 3:** Contrast validation (warn, don't block)  
**Stage 4:** Template injection (CSS vars in `<style>` block)  
**Stage 5:** Tests + docs  

### Trade-offs

| Choice | Benefit | Risk | Mitigation |
|--------|---------|------|-----------|
| Expose brand_colors | Personalization | Slight surface expansion | Hex validation only |
| Deterministic palette | No cost, consistent | May not match intent | Log warnings, manual override in phase 3 |
| Warn on contrast fail | Respects business choice | Poor contrast rendering | Log prominently, email founder weekly |

### Rollout

1. Ship stages 1-4 together.
2. Feature flag: `ENABLE_BRAND_COLORS=true` env var (off by default).
3. Verify on preview deploy with test tenants.
4. Flip to default-on after verification.
5. Monitor contrast warnings weekly.

### Rollback

- Client: override CSS vars in console.
- Server: set `brand_colors = null` for tenant (revert to default).
- Kill switch: `ENABLE_BRAND_COLORS=false` (all sites → default palette).

### Questions for Founder

1. **Contrast enforcement:** Block sites with contrast < 4.5:1, or warn + render?  
   *Current plan: Warn + render.*
2. **Premium design:** Hand-tuned palettes for premium tiers?  
   *Current plan: All deterministic, premium override in phase 3.*

---

## [ADR-002] Custom Domains for Rendered Sites (Phase 2)

**Date:** 2026-08-01  
**Status:** Approved  
**Affects:** `tenants` table, `app.py` (middleware), `site_render_router.py` (documentation)  
**Effort:** D2 (implemented in 1 session)

### Problem

Tenants want to serve sites at custom domains (e.g., `desertcooling.com`) instead of the default `/sites/{tenant_id}/web` path. Presently, all sites live under WebStaffr's path structure with no custom domain support.

### Decision

**Add a `custom_domain` column to tenants and implement path-rewriting middleware to transparently route custom domains to the internal path-based handler.**

### Implementation

1. **Database:** Add `custom_domain` (nullable TEXT, non-unique) column to tenants table.
2. **Resolver:** `resolve_tenant_from_host()` function queries custom_domain column, handles port stripping and case normalization.
3. **Middleware:** `CustomDomainMiddleware` intercepts all requests, checks Host header, resolves tenant_id, rewrites path before FastAPI routing.
   - Custom domain request: `desertcooling.com/about` → internally routed as `/sites/{tenant_id}/web/about`
   - Path-based request: unchanged, routes normally.
   - Non-matching Host: passthrough (no-op).
4. **Routes:** Reuse existing path-based handlers; no route duplication.

### Why Middleware vs Duplicate Routes

- **Avoids routing conflicts:** Identical paths can't have multiple handlers in FastAPI.
- **Centralizes logic:** One place to manage custom domain resolution.
- **Reuses handlers:** Existing path-based rendering pipeline unchanged.
- **Transparent:** Tenant code sees no difference; all routing logic in middleware.

### Trade-offs

| Choice | Benefit | Risk | Mitigation |
|--------|---------|------|-----------|
| Middleware-based | Clean routing, no duplication | Harder to debug | Log Host header and rewritten path on dispatch |
| Nullable column (no unique constraint) | Avoid SQLite migration issues | Application must prevent duplicates | Single query per request (negligible cost) |
| Host header lookup | Automatic domain → tenant resolution | Port parsing complexity | Handle `:` stripping, lowercase normalization |

### Testing

- 12 new unit tests for middleware path rewriting, resolution, isolation.
- All 381 existing tests still pass (zero regressions).
- Tests cover: empty hosts, port stripping, subpaths (services, sitemap, robots), passthrough, state tracking.

### Rollout

1. Ship with brand colors (ADR-001).
2. Feature flag optional (`ENABLE_CUSTOM_DOMAINS=true` env var, off by default).
3. Verify on preview with test tenant pointing to custom domain via DNS.
4. Flip to default-on after validation.

### Rollback

- Remove `custom_domain` value for tenant (revert to path-based).
- Kill switch: stop including `CustomDomainMiddleware` in app.py.

### Future (Phase 3+)

- SSL provisioning for custom domains (Let's Encrypt via Vercel, zero-trust model).
- CNAME validation endpoint (/domain-verification/{token}).
- Dashboard UI for domain management (intake redesign).

---

## [ADR-003] Premium Design Variations (Phase 3)

**Date:** 2026-08-01  
**Status:** Backlog

Design variations (modern, minimal, bold) from Silex/Mobirise mockups.

**Defer until founder provides design direction.**

---

## [ADR-021] WebStaffr Brand Color Doctrine (Locked)

**Date:** 2026-08-03
**Status:** Approved (founder-locked)
**Affects:** `WEBSTAFFR_GOVERNANCE.md` (Visual Identity), Site Magic's default direction, all future WebStaffr-owned marketing surfaces
**Effort:** D1 (doc update, no code change)

### Problem

`WEBSTAFFR_GOVERNANCE.md`'s Visual Identity section (last updated 2026-07-18) specified an approximate two-color logo treatment (gray/gold split, deep blue `#1f4d78` unified) with no defined marketing-site palette. The founder has since built and approved a full landing page (`webstaffr-standalone.html`) with a complete four-color system, dark mode, and a refined logo treatment. That page is now the reference implementation for WebStaffr's own brand identity, and is the basis Site Magic's generator should draw its default direction from.

### Decision

**Lock the following as WebStaffr's canonical color doctrine, superseding the prior approximate values:**

| Token | Hex | Role |
|---|---|---|
| Navy | `#000080` | Primary brand color. Headlines, primary text, unified-logo mark, primary CTA on light backgrounds, hero gradient base. |
| Royal Blue | `#4169E1` | Secondary accent. Links, secondary CTAs, icon accents, focus/interactive states. |
| Orange | `#FF6600` | Highlight/energy accent. Primary CTA fill, "Staffr" wordmark color (both logo variants), focus-visible outline color. |
| Gray | `#E0E0E0` | Neutral surface. Page background, card fills, muted section backgrounds. |

**Supporting tones (extracted from the locked implementation, not independently chosen):**
- Navy scale (light-to-dark UI depth, all four used across surfaces/dark mode): `#000080` -> `#000066` -> `#00005A` -> `#000055` -> `#000040`. Footer: `#00004D`.
- Orange tint (icon backgrounds, light mode): `#FFE0CC`.
- Royal blue pressed state: `#2E4FC9`.
- Muted body text: `#5d6880` (light), standard slate grays in dark mode.
- Success/error states use standard semantic colors (emerald/red), not brand colors -- these were never part of brand identity and stay unchanged.

**Logo (Garamond Bold Italic, one size larger than surrounding text):**
- Split (default, light backgrounds): "Web" `#999999`, "Staffr" `#FF6600`.
- Dark (on navy backgrounds): "Web" `#cccccc`, "Staffr" `#FF6600`.
- Unified (monochrome contexts): both words `#000080`.

This corrects two values in the prior doctrine: "Staffr" moves from gold `#bf9000` to orange `#FF6600`, and the unified variant moves from deep blue `#1f4d78` to navy `#000080`. The gray split color (`#999999`) is unchanged.

**Typography:** Garamond (logo only, italic bold) + Manrope (all UI text, weights 400-800).

### Rationale

The founder built and explicitly locked this palette by reviewing the finished landing page, not by picking hex values in the abstract -- the doctrine here is a transcription of an approved artifact, not a new design decision made by Claude. Recording it as an ADR (rather than only updating the governance doc) preserves the "why" for whoever builds Site Magic's default direction: the palette isn't arbitrary, it's traceable to one approved reference implementation.

### Consequences

- `WEBSTAFFR_GOVERNANCE.md`'s Visual Identity section is updated to match (this ADR is the record of why).
- Site Magic's direction engine, when generating a default/fallback direction (no per-tenant brand override), should treat this four-color system as WebStaffr's own house style -- distinct from the dynamic per-tenant `brand_colors` palette system in `DESIGN.md`, which remains customer-brand-driven and unaffected by this decision.
- Any future WebStaffr-owned marketing surface (investor site, agency site, this landing page) should be checked against this table rather than eyeballed.

### Known gap (logged, not fixed here)

`ADR-020` (em-dash governance rule, 2026-07-30) is referenced in `TASKS.md` and `CLAUDE.md` but was never written into this file. Backfilling it is a separate, trivial doc task -- flagged in `TASKS.md`, not done inline here to keep this ADR scoped to the color decision.

---

**Last updated:** 2026-08-03

---

## [ADR-022] Engineering Director Operating Rule (Locked)

**Date:** 2026-08-04
**Status:** Approved (founder-locked)
**Affects:** All WebStaffr project work, `AGENTS.md`, `CLAUDE.md`

### Decision

All WebStaffr engineering work follows the Engineering Director operating rule in `AGENTS.md`:

- Exhaust available capabilities before asking the founder for mechanical work or information a tool can retrieve.
- Classify work D0-D4 by reversibility, precedent, and blast radius.
- Make routine engineering decisions directly; do not hand equivalent implementation choices back to the founder.
- Reserve founder approval for product direction, customer experience, cost, legal, vendors, credentials, production data, schema changes, pushes, and deploys.
- Use assessment -> decision -> action -> report, with depth-calibrated compression and specific verification evidence.
- Verify the production checkout and GitHub repository before building.
- Record a concise delta-only handoff when the founder closes a session.

### Rationale

The founder is the product owner, not the engineering referee. Mechanical questions and implementation menus waste founder context and increase the chance of work landing in the wrong repository or at the wrong process depth. The rule preserves founder authority over consequential decisions while making the engineering function accountable for execution.

### Consequences

- `AGENTS.md` is the operational source for this process.
- `CLAUDE.md` points to it and removes conflicting single-agent wording.
- Existing security, tenant isolation, testing, credential, git, and deployment approval rules remain in force.
- Higher-priority platform and safety requirements continue to override repository instructions where applicable.

---

**Last updated:** 2026-08-04

---

## ADR-023: Workers Send Automatically; Customer Intervenes, Does Not Pre-Approve

**Date:** 2026-08-04
**Status:** Accepted (founder decision)
**Depth:** D4 (product direction, customer experience)

### Decision

Rita's review responses and Sam's quotes send automatically on their trigger. The customer can override, amend, configure, and stop them, but does not approve each send in advance.

### Rationale

The product promise is staff that works, not a queue that waits for the owner. An approval gate on every send reintroduces the owner's attention as the bottleneck, which is the exact cost WebStaffr exists to remove. A home-service owner on a roof is not clearing an approval queue.

### Consequences

- TCPA/DNC compliance review becomes a hard gate on any automated outbound rather than a review step. Nothing sends until it clears.
- The never-fabricate invariant becomes load-bearing rather than advisory: auto-sent copy may not invent remedies, discounts, timelines, or facts absent from the tenant record.
- Negative reviews (1 to 2 star) escalate to a human with a suggested draft instead of auto-responding.
- Every tenant gets a per-worker kill switch that takes effect immediately without support contact.
- Every auto-send is logged as a reversible event: content, timestamp, trigger.
- Rate ceilings are required to contain webhook-loop failure modes.
- The portal's Reviews and Quotes screens become audit trails plus controls, not approval queues.

---

## ADR-024: Customer Portal Is Business Manager Tier

**Date:** 2026-08-04
**Status:** Accepted (founder decision)
**Depth:** D4 (pricing, product packaging)

### Decision

The customer portal ships in the Business Manager tier ($2,497/mo). Office Staff ($497/mo) does not include it.

### Rationale

The portal is the clearest visible difference between the tiers and the strongest upgrade lever available. Bundling it at $497 spends that leverage for nothing.

### Consequences

- Tier gating requires resolving the plan-name drift first: `webstaffr/intake.py`'s `VALID_PLANS` is `{essentials, pro, growth}` while pricing surfaces use Office Staff / Business Manager / White-Glove. No mapping exists between them. A tier check cannot be written against a tier name the code does not have. This becomes a Phase 3 prerequisite.
- Office Staff tenants need a non-portal proof-of-value surface. A weekly summary email built on the same `activity_events` data covers it and doubles as the upgrade pitch.
- Office Staff tenants see the Overview screen with their real numbers and deeper screens visibly gated, rather than a 403. The portal is a conversion surface for them, not a locked door.

---

## ADR-026: Single Office Staff Tier for Initial Launch

**Date:** 2026-08-09
**Status:** Accepted (founder decision)
**Depth:** D4 (product packaging and pricing)

### Decision

NetBuild.Pro launches with one tier only: Office Staff at $497/month. Its canonical application slug is `office_staff`. Legacy `essentials`, `pro`, and `growth` slugs are not accepted as aliases. Business Manager and White-Glove are deferred until after initial market validation.

### Consequences

- Public pricing and intake expose only Office Staff.
- Tests, health checks, current documentation, and new persisted intake records use `office_staff`.
- Historical records and archived documents may retain old names for provenance, but active product surfaces may not advertise or submit them.
- Future tier expansion requires a new founder-approved packaging decision and migration plan.

---

## ADR-027: Site Magic Worker Callback Protocol (SMMM Listener Contract)

**Date:** 2026-08-09
**Status:** Approved (founder, 2026-08-09)
**Depth:** D3 (integration contract, no precedent)
**Affects:** `webstaffr/site_magic_adapters.py` (`HTTPJobStateSink`), worker webhook listener (external SMMM repo)

### Problem

Site Magic generates beautiful tenant websites end-to-end. The orchestration loop (`site_maker_engine.ts`) runs job state transitions (`queued` → `generating` → `reviewing` → `ready_for_review` → `shipped`). These transitions need to flow back to the external SMMM worker queue so it can track job progress and handle retries.

Current state: `HTTPWebhookSiteMagicQueue` adapter sends jobs *to* SMMM via webhook; `HTTPJobStateSink` is a placeholder that returns to a control-plane API endpoint (internal routing in this repo), not back to SMMM. SMMM has no visibility into whether a job succeeded, failed, or is mid-build.

Decision needed: Specify the HTTP contract for SMMM's listener endpoint so it can hook into the callback.

### Decision

**Define a webhook callback protocol for Site Magic state transitions.**

#### Request Format

```
POST {SITE_MAGIC_CALLBACK_WEBHOOK_URL}
X-Site-Magic-Secret: {constant-time-compare SITE_MAGIC_CALLBACK_SECRET}
Content-Type: application/json

{
  "eventId": "uuid v4, unique per transition attempt (for idempotency)",
  "jobId": "site-magic job id (uuid)",
  "status": "queued | generating | reviewing | ready_for_review | shipped | failed",
  "timestamp": "ISO 8601 UTC",
  "buildId": "uuid (present when status=ready_for_review or shipped, absent otherwise)",
  "errorCode": "string (present only when status=failed)",
  "errorMessage": "string (present only when status=failed, human-readable)",
  "qualityMetrics": {
    "critiqueScore": "number 0-100 (present when status=reviewing or later)",
    "p0Issues": "number (present when status=reviewing or later)",
    "selfHealIterations": "number (present when status=ready_for_review or shipped)"
  },
  "previewUrl": "https://sites.{domain}/{tenant_id} (present when status=ready_for_review or shipped)"
}
```

#### Response Contract

- **202 Accepted** — callback acknowledged, SMMM will process asynchronously
- **401 Unauthorized** — secret mismatch or missing header
- **400 Bad Request** — malformed payload
- **5xx** — Server error; Site Magic retries up to 3 times with exponential backoff

#### Idempotency

- `eventId` uniquely identifies this transition attempt.
- SMMM's listener must be idempotent: duplicate `eventId` → same 202, no duplicate processing.
- Site Magic retries failed webhooks; SMMM dedupes via `eventId`.

#### Environment Variables

```
SITE_MAGIC_CALLBACK_WEBHOOK_URL=https://smmm.example.com/webhooks/site-magic
SITE_MAGIC_CALLBACK_SECRET=<secret, 32+ bytes, base64 recommended>
```

If either is unset, callbacks are disabled (no-op) and the job transitions silently within Site Magic.

### Rationale

**Why webhook:** Asynchronous, decoupled, fire-and-forget from Site Magic's perspective. Fits Vercel serverless (no persistent connections).

**Why eventId:** Enables retry logic and idempotent listener without the caller tracking state. Survives job restarts.

**Why constant-time secret compare:** Standard HMAC-style verification (see `webstaffr/workers/angel/stripe_webhook.py` for precedent in this repo).

**Why 202, not 200:** Signals that SMMM is accepting the callback for async processing, not that processing is complete.

**Why qualityMetrics optional:** Early transitions (queued, generating) don't have metrics yet; later ones do. Allows a single schema to represent all transitions.

**Why previewUrl:** SMMM can link back to the live preview for manual review gates.

### Implementation Notes

- `HTTPJobStateSink` in `webstaffr/site_magic_adapters.ts` gains a `callbackUrl` + `callbackSecret` constructor params.
- Before each state transition, `HTTPJobStateSink.transition()` fires the webhook to `SITE_MAGIC_CALLBACK_WEBHOOK_URL`.
- Webhook firing is **non-blocking** — if it fails, log the error and continue (Site Magic's state is already persisted, callback is best-effort).
- Tests: mock the webhook endpoint, verify payload structure, verify idempotency via duplicate `eventId`.

### Consequences

- SMMM owns implementing its own listener at `SITE_MAGIC_CALLBACK_WEBHOOK_URL`.
- Site Magic does not retry failed callbacks beyond the 3-attempt limit (keeping retry logic simple in Vercel).
- If the callback webhook is down, SMMM loses visibility until Site Magic pushes another state change (e.g., an error occurs and the job fails, then the failure callback goes out).

---

## ADR-028: Crawler SSRF Protection Strategy (Egress Proxy vs. httpx Connection Pinning)

**Date:** 2026-08-09
**Status:** Approved (founder, 2026-08-09)
**Depth:** D3 (network security, bounded by infrastructure)
**Affects:** `webstaffr/site_magic_adapters.py` (`HttpxSiteCrawler`), deployment configuration

### Problem

Site Magic generates a tenant website on a loopback server, then crawls it to collect evidence (screenshots, links, console errors, 4xx responses, etc.). The crawler must fetch URLs like `http://localhost:3000/sites/{tenant_id}/index.html`.

Risk: DNS rebind / TOCTOU attack. If an attacker controls the hostname, they could:
1. First lookup: resolve to `127.0.0.1` (passes validation).
2. Request fires: attacker's DNS redirects to internal IP (e.g., `10.0.0.50`, metadata endpoint, admin server).
3. Crawler leaks data from internal service.

Current implementation in `HttpxSiteCrawler`: re-validate the DNS lookup immediately before each request, narrowing the TOCTOU window. Known limitation documented in class docstring.

Decision needed: Is TOCTOU re-validation sufficient, or do we need connection-level IP pinning?

### Options Evaluated

**Option A: httpx Connection-Level IP Pinning** (Preferred, if feasible)
- Resolve hostname once, pin IP at connection pool level.
- httpx has no public API for this; would require subclassing `httpx.HTTPTransport` or using `httpcore` directly.
- Implementation effort: ~200 lines, one new class.
- Protection: Eliminates TOCTOU entirely.
- Tradeoff: **Higher complexity, lower dependency on httpx's API stability.**

**Option B: Pre-Request DNS Re-Validation** (Current)
- Resolve before each request; reject if IP changes.
- Current implementation: `resolveHostname()` called inside `_fetch()` right before `session.get()`.
- Protection: Narrows TOCTOU window, but doesn't eliminate it (millisecond race).
- Tradeoff: **Simple, but imperfect. Known limitation.**

**Option C: Proxy Egress (Outbound Proxy)**
- Route all crawler requests through a fixed proxy that validates IPs on its end.
- Protection: Closed-loop; proxy is the only source of truth for DNS + IP.
- Tradeoff: **Requires separate infrastructure (egress proxy), operational overhead.**

### Decision

**Use Option B (pre-request DNS re-validation) for MVP; document as known limitation; escalate Option A (connection pinning) to Phase 3 post-launch.**

Rationale:
- **Phase 1 MVP goal:** Ship with evidence runner, not perfect SSRF defense. Tenant websites are low-risk (intentional, customer-owned content).
- **Narrow TOCTOU window:** Re-validation reduces the attack surface from "any DNS resolver under attacker control" to "a subsecond race condition after each validation."
- **Option A complexity:** Connection pinning requires httpx internals knowledge; risk of breaking on httpx version bump.
- **Option C infrastructure:** Egress proxy adds operational surface not needed for MVP.

#### Implementation

**Crawler behavior (no change from current):**
```python
class HttpxSiteCrawler(SiteCrawler):
    async def fetch(self, url: str) -> str:
        # Re-validate DNS immediately before request
        hostname = URL(url).host
        validated_ip = await self._resolve_and_validate(hostname)
        # Fail if IP changed since last lookup
        if validated_ip != self._cached_ips.get(hostname):
            raise SSRFDetectedError(f"DNS rebind for {hostname}: {validated_ip}")
        # Safe to fetch
        response = await self._session.get(url)
        return response.text
```

**Class docstring includes:**
```
Known limitation: TOCTOU window exists between DNS validation and
actual request (milliseconds). Not suitable for defense against
highly determined attackers. Sufficient for MVP tenant-website
crawling. Phase 3: consider connection-level IP pinning if threat
model changes.
```

### Consequences

- **Phase 1:** Ship with documented limitation, MVP-grade protection.
- **Phase 2:** Monitor for any SSRF exploitation attempts; flag to founder if needed.
- **Phase 3:** If threat model changes (e.g., multi-tenant DNS rebinding discovered), implement Option A.
- **Testing:** Unit tests verify that DNS rebind attempts are rejected; integration tests (real DNS) skipped to avoid flakiness.

---

## ADR-029: Site Magic Build Publishing Route (10-Year Signed URL → Shared CDN)

**Date:** 2026-08-09
**Status:** Approved (founder, 2026-08-09)
**Depth:** D3 (affects public site availability, caching, deployment model)
**Affects:** `webstaffr/site_magic_adapters.py` (`SupabaseArtifactStorage.publish()`), deployment, DNS

### Problem

Site Magic generates beautiful websites. Once a build reaches `shipped` status, it needs a stable public URL for the tenant to see their live site:

```
https://sites.netbuild.pro/{tenant_id}/
```

Current implementation: `SupabaseArtifactStorage.publish()` returns a 10-year signed Supabase Storage URL. Limitations:

- **Long URLs:** Contains auth token; ugly when shared.
- **Not customizable:** Hard-wired to Supabase domain.
- **No caching layer:** Every request hits Supabase Storage directly.
- **Scaling question:** Does Supabase Storage scale for concurrent user browsing of tenant sites?
- **Placeholder status:** Explicitly documented as MVP-grade.

Decision needed: Replace 10-year signed URL with a real public-serving design.

### Options Evaluated

**Option A: Supabase CDN (if available)**
- Supabase offers a managed CDN for Storage buckets.
- Pros: Integrated, no new infrastructure.
- Cons: Plan-dependent; may not be available.

**Option B: CloudFront or Cloudflare (public CDN)**
- Use standard CDN to cache builds.
- Pros: Industry-standard, global edge caching.
- Cons: New infrastructure, new vendor, cost (small).

**Option C: Build publishing to Vercel static hosting**
- Publish builds to Vercel's own static hosting.
- Pros: Integrated; fast edge serving.
- Cons: Requires per-tenant Vercel project setup.

**Option D: S3 + CloudFront (self-managed)**
- Upload builds to AWS S3, cache via CloudFront.
- Pros: Full control, scalable, industry-standard.
- Cons: Requires AWS account, setup, cost (small).

### Decision

**Implement Option B (Cloudflare Workers + R2) for Phase 3; use Supabase Storage public URLs (no signed tokens) for Phase 1 MVP.**

Rationale:

#### Phase 1 MVP (Now)

- **Use Supabase Storage bucket public URLs (no signed tokens).**
  - Make the bucket (or tenant-sites prefix) publicly readable via Supabase bucket policies.
  - Serve from `https://storage.supabase.co/object/public/{bucket}/{tenant_id}/index.html`.
  - **Trade-off:** Long URLs, but works immediately, no new infrastructure.
  - **Assumption:** Supabase Storage can handle concurrent user browsing (we monitor; escalate if CDN needed sooner).

#### Phase 3+ (Post-MVP)

- **Migrate to Cloudflare Workers + R2:**
  - Cloudflare Workers: serverless functions at the edge.
  - Cloudflare R2: S3-compatible object storage, cheaper than S3.
  - **Route:** `https://sites.netbuild.pro/{tenant_id}/` → Cloudflare Worker → fetch from R2 → cache at edge.
  - **Build publishing:** After Site Magic ships a build, also upload to R2 (or add `R2ArtifactStorage` adapter in production).
  - **Benefits:** Custom domain, global caching, better UX, cheaper egress.

#### Environment Variables (Phase 1)

```
# Use Supabase Storage directly; no signed URLs
SUPABASE_SITE_STORAGE_BUCKET=site-builds  # publicly readable
# Later (Phase 3): add Cloudflare R2 credentials
```

#### Implementation (Phase 1)

```python
class SupabaseArtifactStorage(ArtifactStorage):
    def publish(self) -> str:
        # Return a public bucket URL instead of signed URL
        bucket_url = f"{self.supabase_url}/object/public/{self.bucket_id}/{job_id}/"
        return bucket_url
```

### Consequences

- **Phase 1:** Public URLs are long (Supabase domain + path), but stable and immediate.
- **Monitoring:** Watch Storage performance; escalate to Phase 3 CDN if needed.
- **Phase 3:** Cloudflare setup requires domain (`netbuild.pro`), new vendor account, DNS CNAME, `R2ArtifactStorage` adapter.
- **No migration needed:** Public URLs work; just change from signed to public (same length).

---

## ADR-030: Image-Content Verification Gate After Generation (APPROVED — implemented behind flag)

**Date:** 2026-08-16
**Status:** Approved and implemented (2026-08-16), shipped dark behind `SITE_MAGIC_IMAGE_VERIFY=1`
**Depth:** D3 (design before code — architectural change to the Site Magic pipeline shape)
**Affects:** `webstaffr/site_maker_engine.ts` image-generation + remediation flow, `webstaffr/site_magic_codegen_runtime.ts` (new `verifyImageContent`)

**Implementation note (2026-08-16):** The `ImageGenerator.generate` contract is all-or-nothing
`count: 3` (no single-comp regen). The gate therefore does one bounded regen of the whole set,
re-verifies only the indices that originally mismatched, and drops any still-mismatched comp
(splicing both the data URI and its `ImageBrief`). `verifyImageContent` is a standalone multimodal
helper mirroring `callReadOnlyRole` (strict `json_schema`, fail-open on any error) so it does not
touch `ROLE_CONFIG`/`validateCodegenResponse`. The pre-gate `comps.length !== 3` throw was relaxed
to accept a 1-2 partial set; the builder instructions now report the actual comp count and forbid
fabricating missing images.

### Problem

Site Magic generates exactly three comps (`hero`, `proof`, `service`) once, up front,
in `generateImagesWithBoundedRetry` (engine line ~806), before the build/remediation
loop. The remediation loop (lines ~826–895) calls `evidence.assess` and builder rebuilds
but **never** calls `images.generate` again — confirmed: zero `images.*` calls inside the loop.

Consequence: if a generated comp does not match its brief, the mismatch is invisible until
evidence assessment flags it, typically deep inside remediation. By then there is no path
back to image generation, so remediation can only edit HTML/CSS and can never fix image
*content*. The job then burns all `MAX_REMEDIATION_ROUNDS` (4) rounds failing to converge,
or ships a wrong-but-clean-looking image with alt text that contradicts the picture.

**Observed real instance (2026-08-16):** job `local-1786857894432`, comp-3 (`service`,
brief "duct cleaning") came back as a technician's hands doing electrical diagnostics on an
outdoor AC condenser. `index.html` wires it in with alt text "Close view of metal ductwork
and vent grille." Four remediation rounds could not close the finding because the loop
cannot regenerate the comp.

### Decision (proposed)

Add a **post-generation image-content verification gate** immediately after the comps are
written to the workspace, before the build phase starts:

1. For each comp, run one cheap vision check: "Does this image actually depict the subject
   its brief asked for?" The brief text (`ImageBrief.role` + `ImageBrief.altText`) is the
   acceptance criterion. No score, no aesthetics — binary content-match only.
2. If a comp fails the check, attempt **one bounded regen** of that specific comp through
   the existing `images.generate` path (retry already bounded by `IMAGE_GENERATION_MAX_ATTEMPTS`).
3. If the regen also fails the check (or generation is exhausted), **drop that comp** and
   proceed without it. **Correction (2026-08-16, verified against the real engine before
   implementation):** the engine does *not* already handle this. `site_maker_engine.ts:811`
   (`if (!imagesMissing && comps.length !== 3) throw`) only tolerates `comps === null` (all
   three missing) or exactly 3 — a dropped-to-2 set trips that throw before `writeImageComps`
   ever runs. There is also no `ensureCompsReferenced` function; the real one is
   `ensureImageCompsRendered`, which does handle any comp-array length fine — it's the earlier
   guard that's the blocker, not that function. The gate's implementation must (a) relax the
   line-811 guard to route any non-empty partial set through the same path as the full set
   (only `comps === null` should trigger the no-image build instructions), and (b) splice the
   matching `ImageBrief` out of `imageBriefs` when a comp is dropped, so remaining comps keep
   their correct role/alt text instead of shifting (e.g. dropping `hero` must not leave the old
   `proof` comp built against `briefs[0]`'s hero alt text). Do **not** fabricate alt text for a
   comp that isn't there.
4. The gate is a pure pre-build step. It does **not** alter the remediation loop contract,
   the fail-closed `isValidFinding` guard, or the `MAX_*` constants.

### Rationale

- The cost of discovering a wrong comp in round 3 of remediation is: 3+ evidence runs +
  N builder rebuilds already spent, plus a job that either fails or ships a wrong image.
  A single cheap vision check up front costs one model call per comp and prevents all of it.
- Regenerating at generation time (when the `images` adapter is already in scope) is the only
  point in the pipeline where comp content is mutable. After the loop starts, it is not.
- Bounding to one regen + drop-otherwise keeps the gate's worst case cost fixed and prevents
  an infinite image-generation loop. Dropping a non-conforming comp is strictly safer than
  shipping a contradicted alt text (never-fabricate invariant).

### Implementation Stages (proposed, not started)

1. Add `verifyImageContent({ imagePath, brief })` adapter method (or a thin wrapper in the
   engine) returning `{ match: boolean, reason?: string }`. Reuse the existing vision
   capability if present; otherwise the cheapest available vision model.
2. In `run()`, after `writeImageComps(...)` and before the `while(true)` build loop, iterate
   comps, call `verifyImageContent`, and on mismatch call `images.generate` once for that
   brief; replace the comp in place if the regen matches.
3. On persistent mismatch, remove the comp from the set passed to the builder **and** splice
   its `ImageBrief` from `imageBriefs` at the same index, so role/alt-text assignment for the
   surviving comps doesn't shift. Relax the `comps.length !== 3` guard (`site_maker_engine.ts:811`)
   to accept any non-empty partial set via the existing full-set build path; only a fully-null
   `comps` should route to the no-image build instructions. Do not leave a dangling
   `relativePath` or contradicted alt text.
4. Add a `job_events` row / metric for "image regen" and "image dropped" so the gate's
   behavior is observable in `site_magic_jobs` history.

### Trade-offs

- **Added latency/cost:** one vision call per comp per job (3 calls), plus up to 3 one-shot
  regens in the failure case. Small relative to the evidence-assessment cost already paid
  per remediation round.
- **New failure mode:** a flaky vision checker could drop a perfectly good comp. Mitigated by
  keeping the check binary and content-only, and by the graceful no-image build path.
- **Scope:** intentionally does not fix already-shipped jobs or historical comps; it is
  forward-looking. The `local-1786857894432` comp-3 remains wrong until a fresh run.

### Rollout

- Ship behind a boolean env flag (`SITE_MAGIC_IMAGE_VERIFY=1`) so it can be disabled without
  a code change if the vision checker misbehaves in production.
- First real-world validation is the Phase 0 production intake (already approved for spend),
  watched via `site_magic_jobs` state transitions.

### Rollback

- Set `SITE_MAGIC_IMAGE_VERIFY=0`. No schema change, no migration, no control-flow dependency
  elsewhere — the gate is additive and isolated to the pre-build phase.

### Open questions for founder

- None blocking. Cost is bounded and small; the founder's only live lever is the env flag
  and whether to keep the gate on by default after validation.

### Verification (2026-08-16, before founder sign-off)

Reviewed the implementation against this ADR line by line rather than trusting the diff's own
summary. Two things worth recording:

- **Real gap found and closed:** the only two existing tests (`ADR-030 image gate is dead code
  when unset`, `...fails open when no credential`) both exercise the *gate-does-nothing* paths.
  Neither exercised the actual mismatch → regen → drop → splice logic this ADR exists for — the
  highest-risk part of the change (an index bug here silently mislabels a surviving comp's role/alt
  text, which is exactly the failure class ADR-030 was written to prevent). Added
  `tests_node/site_maker_engine.test.ts`: "ADR-030 image gate drops a persistently-mismatched comp
  and splices its brief, leaving the survivors' roles/paths correct" — mocks `fetch` so
  `verifyImageContent` fails closed only for the `service` role (mirrors the real
  `local-1786857894432` instance), runs the real engine end-to-end, and asserts the builder is told
  about exactly 2 comps with hero/proof's correct re-numbered paths, correct alt text, and no
  `service=` or stale `comp-3.webp` reference. Passes against the real (non-mocked) splice logic.
- **Known gap, not fixed here:** Implementation Stage 4 (`job_events` row / metric for "image
  regen" / "image dropped") was not built — the gate only `console.error`s. Observable via Railway
  logs today, same as everything else in this pipeline, but not queryable from `site_magic_jobs`
  history. Logged in TASKS.md as a follow-up, not blocking the dark-behind-flag ship.

**Test status:** `npm run test:site-magic` (Node built-in test runner) 129/129 passing on every
suite unrelated to the local Playwright Chromium binary being absent from this sandbox (7 failures,
all `browserType.launch: Executable doesn't exist`, pre-existing environment gap, unrelated to this
change — confirmed by reading the failure stack, not assumed). `npm run check:site-magic` (syntax
check across all Site Magic engine files) clean.

---

## ADR-032: Customer Auth Bootstrap From Verified Intake Email (APPROVED — direction only, not implemented)

**Date:** 2026-08-16
**Status:** Approved direction, implementation explicitly deferred by founder to post-publish-path
**Depth:** D3 (design before code — touches auth architecture, no precedent in codebase)
**Affects:** `webstaffr/customer_auth.py` (`CustomerAuthorizer.start_session()`), `webstaffr/intake_router.py`, `customer_users`/`tenant_memberships` tables

### Problem

`intake_router.py`'s `submit_intake()` creates a `tenants` row (and a tracking number) but never
a `customer_users` row. `CustomerAuthorizer.start_session()` ([customer_auth.py:143](../webstaffr/customer_auth.py)) requires a
`customer_users` row to already exist for the verified Supabase identity and 403s if not — it
never bootstraps one. There is currently no working path for a real customer to end up in
`customer_users`/`tenant_memberships` at all. The dashboard/attribution/site-magic-control auth
routes (`auth_router.py`, `attribution_router.py`, `site_magic_router.py`) are wired but
unreachable for any tenant created via intake. Does not block the MVP path (intake → generated
site → Angel widget never touches auth), but blocks a customer from ever managing their own site
post-publish.

### Decision (approved, not yet built)

When a Supabase-verified identity calls `POST /auth/session` and no `customer_users` row exists
yet for that `user_id`, look up the most recent `intake_submissions` row whose captured email
matches the verified identity's email (case-insensitive), and if found:

1. Create a `customer_users` row for the verified identity (`status='active'`).
2. Create an `owner` `tenant_memberships` row linking that user to the tenant from the matched
   intake submission.
3. Continue the session as normal (existing `start_session()` behavior from that point on).

Trust boundary: the email being matched against is the verified Supabase identity's own email
(already authenticated by `SupabaseIdentityVerifier`), not user-supplied input — the only new
data being trusted is that it matches an intake row's email string. Must be **idempotent**: a
second `/auth/session` call for the same user must not create a duplicate `customer_users` row or
a duplicate/conflicting membership (`ON CONFLICT` on `user_id`, membership existence check before
insert).

### Explicitly not decided / not in scope for the approval

- What happens when an intake email matches **zero** or **multiple** `intake_submissions` rows.
- Whether a bootstrapped membership should default to `owner` unconditionally or need
  confirmation for shared/agency-submitted intakes.
- Whether this needs a DB migration (new column, index on `intake_submissions.email` for the
  lookup) — not yet checked against the real schema.

These need the D3 design pass this ADR's "not implemented yet" status is holding open for.

### Status

Direction approved by founder 2026-08-16. **Explicitly not to be implemented yet** — logged here
as a post-publish-path item per founder instruction, tracked in TASKS.md's backlog. Revisit once
the core intake → site → Angel MVP flow has shipped and a customer-facing dashboard is actually
on the roadmap.

---
