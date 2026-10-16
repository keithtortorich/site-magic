# In-Repo Customer Site Renderer — Build Plan

**Status: approved direction (founder, 2026-07-27), not yet built.** Supersedes Lovable's
Site Weaver project as the generation mechanism for customer/tenant sites. Site Weaver's
Lovable project stays untouched as a fallback until this renderer is verified live; retiring
it is a separate, later decision. The NetBuild.Pro Agency Site (company marketing site) is
unaffected — it stays on Lovable.

**Why (decision summary — full ADR to be added to `docs/DECISIONS.md` at build completion):**
Lovable's credit-based pricing repeatedly stalled work mid-task (see TASKS.md 2026-07-27
entries), and the founder directed a free generation method. Site Weaver's actual job —
intake data in, tenant site out, no human in the loop — is deterministic templating, not
interactive AI building. Rendering server-side in this repo costs $0 incremental (rides the
existing Vercel deployment), removes a vendor from the critical path, and is *better* for
local SEO than a client-rendered React site: crawlers get complete HTML instantly, schema
markup is in the initial response, and page weight drops to near nothing.

---

## Architecture

- **Rendering:** server-side Jinja2 templates (new dependency, approved as part of this
  plan's sign-off; MIT license, no service/account, pure Python). Rendered per-request —
  stateless, fully compatible with the Vercel-serverless invariant. No build step, no
  generated-files storage.
- **Data source:** `build_public_site_data()` in `site_data.py`, unchanged. The renderer is
  a *consumer* of the existing public projection — it adds no new fields and therefore
  cannot leak anything the projection doesn't already expose. Never-leak list untouched.
- **Routes** (all GET, browser-facing, added in `create_app()` per the composition-root rule):
  - `/sites/{tenant_id}` — **unchanged**, keeps returning JSON (Site Weaver fallback and the
    Angel widget config both consume it; breaking it is not acceptable).
  - `/sites/{tenant_id}/web` — rendered homepage (HTML).
  - `/sites/{tenant_id}/web/services/{service_slug}` — one page per intake service.
  - `/sites/{tenant_id}/web/about`, `/web/reviews`, `/web/contact` — per the SEO blueprint's
    page architecture. Reviews page only exists when real testimonials/ratings are on file.
  - `/sites/{tenant_id}/web/sitemap.xml` and `/web/robots.txt` — generated per tenant.
  - CORS: these are top-level browser navigations, not cross-origin fetches — no CORS
    headers needed; the existing `/sites/` prefix scoping already covers the JSON route.
- **Phase 2 (post-verification): custom domains.** Vercel supports multiple domains on one
  project; a middleware resolves tenant by `Host` header (domain → tenant_id lookup, new
  nullable `custom_domain` column — schema change, will be proposed separately per the
  approval rules) so `desertcooling.com` serves that tenant's pages at clean root URLs.
  Until then, sites live at the `/web` paths above. Not in this build's scope.

## Template design

One base template + page templates, one shared CSS file (no framework, no JS beyond the
Angel widget embed). Per `docs/SITE_WEAVER_SEO_BLUEPRINT.md`:

- **Head:** title/meta-description patterns (`[Service] in [Service Area] | [Biz Name]`),
  canonical tag, viewport, OpenGraph basics.
- **Schema markup (JSON-LD):** LocalBusiness (typed by industry where a schema.org subtype
  exists, e.g. HVACBusiness/Plumber/Electrician, falling back to LocalBusiness), Service
  per service page, FAQPage where intake data supports real answers.
  **AggregateRating/Review schema renders only from real `rating_value`/`review_count`/
  `testimonials` fields and is omitted entirely when absent** — the blueprint's hardcoded
  example values are never used (no-fabrication invariant; flag already recorded in the
  blueprint doc).
- **Body:** H1/H2 keyword structure, services grid linking to service pages, service-area
  list, differentiator section, tel: CTAs, emergency-service banner when
  `emergency_service` is set, testimonials section (real ones only, omitted otherwise),
  certifications/social links when present. Every optional section follows `site_data.py`'s
  existing contract: key absent → section absent, never filler.
- **Brand governance:** no "AI" in copy, no emojis, no em-dashes (Governance Manual rule,
  default per CLAUDE.md until the founder reconciles the two source docs), "NetBuild.Pro"
  spelling in any footer attribution.
- **Angel widget:** embedded on every page exactly as on the current Site Weaver build,
  pointed at the same backend.

Design polish path: the first template ships clean-and-professional from the blueprint's
structure. If the founder wants a specific look, a Silex/Mobirise mockup can be handed over
any time and folded into the template — a restyle, not a rebuild.

## Build sequence (each step keeps the suite green)

1. Add `jinja2` to `requirements.txt`/`requirements-dev.txt`; update `README.md` (no
   credentials involved, so `CREDENTIALS.md` is untouched).
2. `webstaffr/site_renderer.py` — pure functions: slugify services, choose schema.org
   business type, assemble per-page template context from the public projection. No DB
   access of its own.
3. `webstaffr/templates/` + static CSS; render routes wired in `create_app()`.
4. Tests: route round-trips per page; **never-leak assertion against rendered HTML**
   (none of `lead_routing`/`approver`/`competitors`/`license_number` appear in any page);
   no-fabrication assertions (no rating/review markup when fields absent; no em-dashes,
   no "AI", no emoji in template-authored copy); sitemap/robots correctness; 404 for
   unknown tenant and unknown service slug; tenant isolation (tenant A's page never
   contains tenant B's data).
5. `health_check.py`: add a rendered-page smoke check alongside the existing site-data
   never-leak check.
6. Verification gate: full suite green + health HEALTHY locally, then founder eyeballs a
   real tenant's rendered pages (the e2e verification tenant) on a preview deploy before
   any production traffic decision. Rich-results/schema validation run against the preview.

## Rollout / rollback

- Additive only: no existing route changes, so deploying it dark is safe — the new pages
  simply exist alongside everything else.
- Cutover (later, founder decision): point customer-facing links/domains at the rendered
  pages. Rollback is "point them back at the Lovable preview" — both consume the same
  backend, so no data migration in either direction.
- Retire Site Weaver's Lovable project only after at least one real tenant runs on the
  rendered site without issue.

## Explicitly out of scope for this build

- Custom-domain resolution (Phase 2, needs a schema-change approval).
- Blog/location-page generation from the SEO blueprint's optional sections — the blueprint's
  core page set ships first; location pages beyond the service-area list need content that
  intake doesn't collect yet.
- Any change to intake fields, `site_data.py`, or the Agency Site.
- Deleting/altering the Lovable Site Weaver project.

## Approvals ledger

- Architecture (sites rendered in-repo, Lovable Site Weaver to fallback): **approved
  2026-07-27** ("best decision based on best practices" — this plan).
- Dependency `jinja2`: covered by the same sign-off; recorded here as the specific-choice
  approval CLAUDE.md's security baseline requires.
- Git push / deploy of the built feature: **not yet approved** — will be requested with the
  usual "Completed X. Tests: N/N. Health: HEALTHY. Ready for push?" summary.
- Custom-domain schema change: **not approved, not requested yet.**
