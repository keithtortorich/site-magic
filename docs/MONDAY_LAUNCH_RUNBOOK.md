# Monday Launch Runbook — Memphis HVAC, $0 Start

**Built:** 2026-08-09. **Updated:** 2026-08-10 (post-OpenRouter verification).
**Target launch:** Monday 2026-08-10.

**Verified 2026-08-10 before this update:**
- Production: `GET /health` on `https://netbuild.pro` (aliased to
  `https://netbuild.pro`) returns `{"status":"ok","release":"92ee022..."}`.
- Landing page renders with current NetBuild.Pro copy.
- **`OPENROUTER_API_KEY` is now live in Vercel Production** (added + redeployed
  2026-08-10). A real OpenRouter image call (`google/gemini-2.5-flash-image`)
  returned a valid `data:` URI via the adapter's assumed path
  (`choices[0].message.images[0].image_url.url`). The `OpenRouterImageGenerator`
  is wired into `buildProductionDependencies()` (`site_magic_worker.ts:71`), so
  Site Magic image comps work without OpenAI's GPT Image org-approval.
- Node suite: 51/51 passing.

**Live in Vercel Production today:** `OPENROUTER_API_KEY`, `GROK_API_KEY`,
`BOOK_API_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
`CUSTOMER_ALLOWED_ORIGINS`.
**NOT yet set in Vercel (the real gap between "code exists" and "voice line
rings"):** `STRIPE_WEBHOOK_SECRET`, `RETELL_WEBHOOK_SECRET`, `GHL_API_KEY`,
`GHL_LOCATION_ID`, `GHL_WEBHOOK_SECRET`. Also `SITE_MAGIC_WORKER_WEBHOOK_URL` /
`SITE_MAGIC_WORKER_WEBHOOK_SECRET` are not set, so the Site Magic worker is not
yet connected to a running worker process (intake auto-enqueues a job, but no
worker consumes it until those are set AND a worker is deployed).

---

## What "zero dollars" actually means here

Two things are already free and live, no action needed:
- The generated website + tracking-style tenant site + text-based Angel chat
  (Grok-backed).
- Hosting (Vercel) and DB (Supabase) — already provisioned and paid for from a
  prior session, not a new cost you're taking on Monday.

Two things need a free-tier signup before a client can be **delivered**, not
before you can **sell**:
- **Retell AI** (voice) — new accounts get $10 free credit, no time-limited
  trial, pay per minute after that (~$0.11–0.15/min blended). No credit card
  charge until you spend past the credit.
- **GoHighLevel** (calendar/CRM sync) — 14-day free trial, card required for
  verification but not charged during the trial. Starter plan is $97/mo after.

Without these two, `/book` still works — appointments get recorded by the app's
own `NullGHLClient` in memory — but nothing shows up in the client's actual
calendar. **Do not sell "live calendar sync" until GHL is actually configured.**
Sell the site + text receptionist first; layer in voice once you've signed up for
Retell (takes ~10 minutes, same day as your first client call).

**Real first-dollar spend, in order:**
1. $0 — everything through first client conversation and demo site.
2. $0 — Retell signup (free credit covers dozens of demo/onboarding calls).
3. $0 for 14 days — GHL trial once you have a client who wants calendar sync.
4. First real spend is the GHL renewal (~$97/mo) or Retell minutes past $10 —
   both should land *after* the first $497 payment, not before.

---

## Automation toolkit (use these, don't do it by hand)

These are real, committed scripts in `scripts/`. They keep you honest on launch
day so you're never guessing whether production is healthy.

### 1. Production smoke test (read-only, no data written)
Confirms health JSON, release SHA, security headers, landing page, and an
optional tenant site.
```bash
cd /Users/doc/Desktop/NetBuild.Pro
.venv/bin/python scripts/production_smoke.py \
  --base-url https://netbuild.pro \
  --expected-sha 92ee022        # omit --expected-sha to skip the SHA pin
# Optional: also check a generated tenant site renders:
.venv/bin/python scripts/production_smoke.py \
  --base-url https://netbuild.pro --tenant-id <tenant_id>
```
Run this at 7:15 AM Monday and any time you redeploy.

### 2. Activation preflight (env presence, no secret values printed)
Fails closed and prints only which vars are present/missing — never the values.
```bash
.venv/bin/python scripts/activation_preflight.py        # reads os.environ
.venv/bin/python scripts/activation_preflight.py --json # machine-readable
```
Run this before relying on any vendor integration live. Today it will show
`GHL_*` and `RETELL_WEBHOOK_SECRET` as missing — that's expected until you
configure them.

### 3. One-shot test intake (prove the pipeline before you promise it)
Submit a fake business end-to-end and confirm the tenant + site render:
```bash
curl -s -X POST https://netbuild.pro/intake \
  -H "Content-Type: application/json" \
  -d '{"biz_name":"Smoke Test HVAC","phone":"(901) 555-0100",
       "email":"smoke@example.com","industry":"hvac",
       "service_area":"Memphis, TN","plan":"office_staff"}' \
  | python3 -m json.tool
```
The response returns `tenant_id`. Open `https://netbuild.pro/sites/<tenant_id>/web`
to confirm the site renders. Do this Monday morning before dialing.

### 4. Customer provisioning (after a client signs + pays)
`scripts/provision_customer.py` grants an existing Supabase Auth user access to
a tenant. It fails closed (no partial writes) and needs a configured DB
connection. Typical use: after intake creates the tenant, provision the client's
login. Not needed for the first call — intake alone creates the tenant and site.

### 5. Health check (full in-repo gate suite)
```bash
.venv/bin/python scripts/health_check.py
```
Runs the embedded verification gates (intake round-trip, tenant scoping,
rendered-site smoke, Angel prompt load, etc.). Use post-deploy to confirm
nothing regressed.

**Note on what is NOT yet automated (by design, not a gap):**
- Voice calls — needs a Retell account + a phone number attached to Angel's
  prompt (`webstaffr/workers/angel/angel_prompt.md` has the approved system
  prompt; you wire the number, not the AI). Set `RETELL_WEBHOOK_SECRET` in
  Vercel after.
- Calendar sync — needs GHL configured (`GHL_API_KEY`, `GHL_LOCATION_ID`,
  `GHL_WEBHOOK_SECRET`). Until then, bookings record locally only.
- Payment collection — Stripe webhook code is shipped and wired, but
  `STRIPE_WEBHOOK_SECRET` is not yet set in Vercel. Until it is, take payment
  via a Stripe Payment Link as a same-day fallback and reconcile manually.

---

## Hour-by-hour, Monday 2026-08-10

**7:00 AM** — Sign up for Retell AI (retellai.com), verify email, note the $10
credit is live. Do not build the agent yet — just confirm the account exists.

**7:15 AM** — Confirm production is still healthy:
`.venv/bin/python scripts/production_smoke.py --base-url https://netbuild.pro`
Confirm the landing page and one demo site load in a browser.

**7:30 AM** — Run the one-shot test intake (toolkit #3) to personally see a
tenant + rendered site before you promise it to a stranger.

**7:30 AM – 8:00 AM** — Read the call script below twice out loud. Have the
prospect list open next to your phone.

**8:00 AM – 11:30 AM** — Call block 1. Goal: 15-20 dials, 3-5 real
conversations, 1 verbal yes.

**11:30 AM – 12:00 PM** — If you got a yes, send the intake link immediately.
If not, log every "call back" and "send me something" — those become your 1 PM
list.

**12:00 PM – 1:00 PM** — Lunch / breathing room. Prep the intake submission for
your best lead.

**1:00 PM – 4:00 PM** — Call block 2: callbacks, voicemail follow-ups via text,
next 10-15 names.

**4:00 PM – 5:00 PM** — Close-out window. Owners who said "call me at end of
day" pick up here.

**The moment someone says yes (any time):**
1. Get their business name, phone, city/service area, hours, and 2-3 services on
   the call — don't make them fill a form while you're on the phone.
2. Submit `POST /intake` yourself (or walk them through it) — auto-creates the
   tenant, renders their site, returns `tenant_id` in the same request.
3. Text them their live site URL (`/sites/<tenant_id>/web`) within 5 minutes.
   That speed *is* the pitch.
4. If they want voice same-day: log into Retell, attach a number to Angel's
   existing prompt, set `RETELL_WEBHOOK_SECRET` in Vercel env. Same-day task,
   not a blocker to the yes.
5. Collect payment. Stripe webhook code is shipped but `STRIPE_WEBHOOK_SECRET`
   is not yet set in Vercel — use a Stripe Payment Link as same-day fallback
   and reconcile manually until it is.

---

## Exact businesses to call (Memphis HVAC, verified 2026-08-09)

Pulled from public directories and each business's own website. Ordered by
strongest pitch (weakest digital presence first).

| # | Business | Phone | Why this one | Angle |
|---|---|---|---|---|
| 1 | **Waller Heat & Air** | (901) 331-6589 | 30 years in business, GoDaddy builder site, no online booking, no AI answering, static contact form only | "You've been here 30 years — is your website matching that, or costing you calls after hours?" |
| 2 | **Tiger Paws HVAC** | (901) 330-1473 | One-person/family shop, single-page site, no CRM visible, 24/7 claim but no way to prove it | "You say 24/7 — does anything actually answer at 2 AM, or does it ring out?" |
| 3 | **Al Britt Air & Heat** | (901) 324-6213 | 116 reviews, real reputation, but office hours Mon-Fri 8-5 only — after-hours calls ring out | "Your reviews are great. What happens to the guy who calls Saturday at 7 PM?" |
| 4 | **Comfortable LLC** | (901) 262-5931 | 638 reviews, volume leader in Collierville — high call volume means high odds some are missed right now | "At your call volume, even a 5% missed-call rate is real jobs walking to a competitor." |

**Full callable list (call in this order after the top 4):**

| Business | Phone | City |
|---|---|---|
| Comfort Dynamics Cooling, Heating, Plumbing & Electrical | (901) 688-2665 | Cordova |
| Gold Standard Heating and Air | (901) 552-5590 | Memphis |
| Automatic Air Conditioning, Heating & Plumbing | (901) 810-8964 | Memphis |
| Choate's Air Conditioning, Heating And Plumbing | (901) 347-8078 | Collierville |
| OPACHS AC & Heating Services | (901) 443-5153 | Memphis |
| Memphis Air Conditioning & Heating | (901) 621-7027 | Memphis |
| AirMasters Air Conditioning & Heating | (901) 295-4434 | Memphis |
| Best Care Plumbing, Heating And Air | (901) 624-1401 | Bartlett |
| Conway Services | (901) 677-0797 | Cordova |
| Solace Plumbing, Heating & Air | (901) 613-5178 | Memphis |
| Arctic Heating Cooling & Plumbing Inc | (901) 380-9800 | Cordova |
| Crowe Services / Heating & Air | (901) 413-5361 | Memphis |
| Al Britt Air & Heat | (901) 324-6213 | Memphis |
| At Home Heating and Air | (901) 848-6618 | Collierville |
| Hensley Heating & Air Conditioning Co | (901) 794-3074 | Memphis |
| Precision Air Conditioning & Heating | (901) 372-0036 | Memphis |
| Cannon Bros AC & Heat | (901) 794-2250 | Memphis |
| HR Ferrell & Company | (901) 382-3100 | Memphis |
| Nance Services | (901) 867-1527 | Memphis |
| Professional Plumbing, Heating, & Cooling | (901) 221-2626 | Memphis |
| Tiger Paws HVAC | (901) 330-1473 | Memphis |
| Mister Greenway AC Repair, Heating, Plumbing & Electrical | (901) 692-9380 | Bartlett |
| Waller Heat & Air | (901) 331-6589 | Memphis |
| Larry's AC & Heating | (901) 649-8744 | Memphis |
| Gentry's Heating & Cooling | (901) 601-9701 | Memphis (svc: Collierville/Cordova/Germantown) |
| Comfortable LLC | (901) 262-5931 | Collierville |

**Extension list (pulled 2026-08-10 to round the callable list out to 50):**

| Business | Phone | City |
|---|---|---|
| HVAC Firm of Memphis | (901) 509-3535 | Memphis |
| M&N HVAC Service | (901) 351-8419 | Memphis |
| A J Refrigeration, Inc. | (901) 881-2317 | Memphis |
| Absolute Comfort | (901) 375-0998 | Memphis |
| Infinity Heating and Air Conditioning | (901) 622-4822 | Memphis |
| Memphis Heat and Air | (901) 299-9566 | Memphis |
| Chillax Heating and Air Conditioning | (901) 598-1471 | Millington |
| Premier Heating and Air | (901) 323-3222 | Memphis |
| Yates Services of Memphis | (901) 277-7877 | Memphis |
| Prime HVAC and Electrical | (901) 676-7756 | Memphis |
| Smith Heat and Air | (901) 827-9192 | Memphis |
| Smith's Plumbing, Heating & Air | (901) 413-9509 | Memphis |
| Memphis HVAC Plus | (901) 310-8309 | Memphis |
| Blackwell's Heat & Air | (901) 653-8752 | Memphis |
| Memphis Air Care | (901) 365-2848 | Southaven, MS |
| Renfrow Heating, Air & Plumbing | (901) 356-2242 | Olive Branch, MS |
| C&K Air and Heating Inc | (901) 744-4000 | Olive Branch, MS |
| Mitch Wright Plumbing, Heating & Air | (901) 795-9044 | Southaven, MS |
| Air Doctors of Memphis | (901) 598-4822 | Millington |
| AirTek LLC | (901) 896-6279 | Southaven, MS |
| Five Star Cooling | (901) 244-4557 | Memphis |
| Muse Heating & Air Conditioning | (662) 280-0710 | Horn Lake, MS |
| MaxAir Heating and Cooling LLC | (901) 334-1921 | Memphis |
| Southern Comfort Air, Heating & Plumbing | (901) 381-2665 | Arlington |

**Skip for a cold call** (big regional/national brands, longer sale): Aire Serv
of Memphis, Service Experts, One Hour Heating & Air Conditioning, Hiller
Plumbing Heating Cooling & Electrical.

**Data freshness:** top-4 numbers re-verified 2026-08-09 against each business's
own site. The extension list was pulled 2026-08-10 from public directories
(name/phone/city only, no per-business angle verified) -- unlike the top 4,
none of these 24 have a confirmed specific hook (review count, site quality,
after-hours gap). The shared reason to call all 50 is structural, not
business-specific: HVAC techs are in trucks all day, so most small/independent
shops have no one answering the phone when it rings after-hours or mid-job,
and every missed call is a missed job. Before dialing anyone on the extension
list, a 10-second Google of "[business name] Memphis phone" catches anything
changed and may surface a sharper angle to open with.

---

## The call script (60 seconds past the front desk)

Lead with the problem they already feel, not "AI."

> "Hi, is this [Owner Name]? This is [Your Name], I work with HVAC companies in
> Memphis. Quick question — when your phone rings and your techs are on a job,
> what happens to that call?"

*(Let them answer. Almost always: voicemail, rings out, or a tired dispatcher
between jobs.)*

> "Yeah, that's what I figured. I build a system that answers every call and
> text instantly — even at 2 AM — captures the job details, and gets it on your
> calendar before the customer even hangs up. I can show you exactly what it'd
> look like for [Business Name] in about 5 minutes, no cost to look. You got 5
> minutes right now, or should I call back this afternoon?"

**If yes right now:** walk the intake form live, read back their site URL before
hanging up.
**If "send me info":** text them `https://netbuild.pro/` immediately,
follow up in 2 hours.
**If price comes up:** "$497 a month, no setup fee, no contract — cancel
anytime. Most guys make that back on the first missed call it catches."

---

## Where the first $497 goes

Per `docs/business/WEBSTAFFR_GOVERNANCE.md`: Office Staff delivery cost is about
$65/mo (voice minutes, SMS, hosting share), leaving ~$432/mo gross profit per
tenant.

1. **~$65 held back** — covers that client's Retell minutes and GHL once the
   trial ends, so delivery never lapses.
2. **Remainder banked**, not spent — zero fixed costs today (Vercel/Supabase
   provisioned, Retell/GHL start free). Spend only appears when GHL's 14-day
   trial expires on your first signed client (~2 weeks after Monday).

Don't prepay for ads, lead lists, or tools this week. The 26-name list above is
free and enough for a full week of dialing.

---

## Verification before the first call

- [x] `GET /health` → `200 {"status":"ok"}` on production — confirmed 2026-08-10
  (release `92ee022`).
- [x] Landing page renders with current NetBuild.Pro copy — confirmed.
- [x] `OPENROUTER_API_KEY` live in Vercel Production; live image call verified —
  Site Magic image comps unblocked (no OpenAI org-approval needed).
- [ ] **Monday morning:** run toolkit #3 (test intake) and open the generated
  site, so you've personally seen the exact thing you're about to promise.
- [ ] Set `STRIPE_WEBHOOK_SECRET` in Vercel (or plan to use a Stripe Payment Link
  fallback) before relying on live charge capture.
- [ ] Sign up Retell (free) before first client call; attach number same-day on
  a yes.
