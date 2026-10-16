# Standup: Agency Site at Root, Demo Sites Through the Real Renderer

**Date:** 2026-08-09
**Session scope:** Monday launch prep. Root-route swap, demo site rebuild, Lovable scrub.
**Commit state:** All work is local and uncommitted. Nothing pushed, nothing deployed.

---

## Verification state, read this first

The last full-suite run (782 passed, 1277 subtests, health 14/14 HEALTHY) was taken
**before** the final three changes: the demo static-asset routes, the strengthened
link test, and the `/_vercel/` exclusion in that test. The confirming run was
interrupted and has not been re-run.

**Current honest status: unverified.** The next action in this repo should be
`python3 -m pytest -q` plus `python3 scripts/health_check.py`, and the numbers below
should be treated as stale until that passes.

Last known-good full run: 782/782, health 14/14.
Last observed partial run after the static-route change: 68 failed / 22 passed, every
failure being `/_vercel/speed-insights/script.js`, which the hosting platform injects
at the edge and this app never serves. The exclusion for it is written but unproven.

---

## What shipped

### 1. Agency site is now the front door

`/` was serving the old marketing landing page. It now serves the agency site.
The agency pages moved off the `/agency/*` prefix onto root paths:

| Was | Now |
|---|---|
| `/agency` | `/` |
| `/agency/how-it-works` | `/how-it-works` |
| `/agency/pricing` | `/pricing` |
| `/agency/faq` | `/faq` |
| `/agency/about` | `/about` |
| `/agency/contact` | `/contact` |

The old landing route is commented out rather than deleted, and its HTML
(`templates/netbuild_pro.html`) plus the static twin (`site/index.html`) are still on
disk. That was deliberate: retiring a marketing page is a product call, not an
engineering one. See the open question at the bottom.

### 2. Demo sites are now rendered by the real site renderer

This was the substantive piece. The nine demos were hand-authored static HTML served
straight off disk. They had drifted from the product and were showing prospects things
the product does not do and the repo's own governance forbids.

What the old static demos actually contained:

- An em-dash in all nine `<title>` tags. `NETBUILD_GOVERNANCE.md` bans em-dashes
  unconditionally, no exceptions, and these bypassed the linter because nothing tested
  them.
- Fabricated customer testimonials under headings like "What Customers Say", on
  businesses that do not exist. Direct violation of the no-fabrication invariant.
- Unsupported default claims that `tests/test_site_render_router.py` already bans on
  real tenant sites: "24/7", "Free Estimates", "Licensed & Insured", "Upfront Pricing",
  "100% Satisfaction Guarantee", "Guaranteed Results".

Replaced with `webstaffr/demo_sites.py` (fixtures) plus `webstaffr/demo_router.py`
(routes). Every demo page now goes through the same templates and the same
`build_page_context` that serve a paying tenant. A template change reaches the demos in
the same deploy it reaches customers, so a demo cannot drift from the product again.

Nine demos live at `/demos/{slug}`, each with home, about, contact, and one page per
service, plus a gallery index at `/demos`:

`hvac`, `plumbing`, `roofing`, `water-restoration`, `garage-door`, `pest-control`,
`landscaping`, `tree-service`, `cleaning`

Content rules the fixtures follow:

- No `rating_value`, `review_count`, or `testimonials`. A demo business has no
  customers, so it gets no review data, no AggregateRating JSON-LD, and `/reviews`
  returns 404.
- No `certifications`. Those are credentials, not illustrative copy.
- Phone numbers from the 555-0100 to 555-0199 block reserved for fictional use, so a
  prospect tapping "call" on a sample can never reach a real stranger. The previous
  demos used numbers like 503-555-9012, outside the reserved range.
- Emails on the reserved `example.com` domain.
- No em-dashes.

Every demo page carries a banner naming it a sample and linking to `/demos` and
`/start`. The banner is gated on a context flag that is absent on every real tenant
page, and there is a test asserting a real tenant site never renders it.

The lead capture form renders exactly as a customer's does, but has nowhere real to
post. Submitting it answers "This is a sample site, so nothing was sent. On your site,
this request reaches you right away." rather than firing a request that fails with an
error a prospect would read as the product being broken.

No database read anywhere in the demo path. Demos work on a cold serverless boot, need
no seeding step before a sales call, and cannot be broken by tenant data drift.

### 3. Old demo URLs still work

Nothing already handed to a prospect 404s:

- `/demo-sites/hvac.html` and the other eight files return 301 to their rendered
  replacement.
- Retired slugs (`/demos/arbor`, `/demos/waterrestore`, `/demos/roof`, and the rest)
  return 301 to the canonical slug.
- The old `/demo-sites/{file_name}` route read files off disk by name. It is now a
  fixed lookup table, which removes the path-traversal surface entirely rather than
  guarding it.

### 4. Lovable scrubbed

Per direction this session. Removed from module docstrings and comments in `app.py`,
`site_renderer.py`, `site_render_router.py`, `site_router.py`, `site_data.py`,
`intake.py`, `intake_router.py`, `trade_presets.py`, `attribution_router.py`. These
were all descriptive comments referring to a hosting plan that is dead. No behavior
changed.

Still present in docs and historical records, deliberately: `docs/DECISIONS.md`,
`docs/SITE_RENDERER_PLAN.md`, `TASKS.md` session summaries, and similar. Those are
dated records of decisions that were true when written. Rewriting history to hide a
retired plan makes the record less useful, not more. Say the word and they go too.

---

## Bugs found and fixed

**I broke the agency nav and caught it late.** Moving the agency routes to root left
all eight nav and footer links in `templates/agency/base.html` pointing at `/agency/*`,
which no longer existed. Every link on the agency site was dead. The existing tests did
not catch it because they assert status codes and page content, never that an emitted
href resolves. Fixed, and `test_demo_sites.py` now has a test that walks every href and
src a demo page emits and asserts each one returns 200.

**The demo stylesheet 404'd on every page.** Found by looking at a rendered demo in a
browser, not by a test. The templates build asset URLs from `site_root`, so a demo
asked for `/demos/{slug}/static/site.css`, and only `/static/...` and
`/sites/{tenant_id}/web/static/...` had routes. Every demo rendered completely unstyled.
Added the routes, delegating to the existing tenant handlers so the two can never serve
different bytes.

The link test as originally written would not have caught this either: it matched only
root-relative hrefs, and the templates emit absolute URLs for assets. Rewritten to
match both, and to cover src as well as href, across every demo page rather than just
the home page. The lesson is worth keeping: a test that only checks what you thought to
emit will pass while the page is visibly broken.

---

## Not done, and why

- **Nothing committed or pushed.** Approval gate.
- **`webstaffr/templates/netbuild_demos/*.html` still on disk.** The nine static demo
  files are dead code now, no route serves them, but the sandbox mount is read-only for
  deletes. They need `git rm` on your machine.
- **Full suite not re-run after the last change.** See the verification section at the
  top. This is the first thing to do next session.
- **Old landing page not deleted.** Product call, see below.

---

## One open question for you

The agency home is a much thinner page than the one it replaced.

The old landing page had a hero, a live call desk mock, the demo carousel, results,
pricing, and an FAQ. The agency home has a headline, a two-line paragraph, one CTA, and
a workflow box. Both are governance-clean. The agency site is the one you asked to put
up, and it is up.

For Monday, every prospect who types the domain lands on that page. Two options:

1. Ship as is. It is honest, clean, and loads fast. It sells less hard.
2. Move the selling content from the retired landing page into the agency home, keeping
   the agency chrome and the governance rules.

Option 2 is maybe an hour of copy work and is reversible. I did not do it unasked
because what goes on the front page is a positioning decision, not an engineering one.

Related: the demo gallery is now linked in the agency nav and footer, which is how the
demos become "attached to the agency site". If you would rather demos stay unlinked and
be sent directly to prospects on a call, that is a one line change.
