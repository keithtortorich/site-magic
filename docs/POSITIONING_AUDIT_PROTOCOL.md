# Positioning Audit Protocol

Purpose: a systematic, repeatable research protocol for auditing a prospect's online presence (reviews, website, social, competitors) to surface concrete positioning gaps. Output is used as a sales hook: show a business owner exactly where their marketing is weak and what a stronger position would look like, grounded in real customer sentiment and competitive data, not generic claims.

Status: reference protocol, not yet built into a runnable tool. Saved here for the future marketing/prospecting system; not wired into any WebStaffr backend code.

---

## Part 1: Company Strengths Assessment

### 1.1 Review Sentiment Analysis

Sources: Google Reviews, Yelp, Angie's List, HomeAdvisor, service-specific directories.

Search queries:
- `[business name] reviews`
- `[service type] [city/zip] reviews`
- `[business name] [competing business] comparison`

Extract:
- Rating average and how it compares to competitors
- Review volume (signal of scale and trust)
- Recurring themes in positive reviews: speed, quality, reliability, customer service, pricing, safety/credentials

A theme counts as a strength when it's mentioned in 3+ reviews, shows up as the stated reason a customer chose the business, and isn't something competitors are also credited for.

Example output:

```
REVIEW SENTIMENT ANALYSIS
Avg rating: 4.7/5 (67 reviews, Google + Yelp)

Top strength: Speed (28% of reviews)
  "Showed up in 3 hours, emergency fixed same day"
  "Fastest response of any plumber I've tried"
  Competitor avg: 24-hour response, positioned as "quick"
  -> Differentiation opportunity: "same-day" or "2-hour response guarantee"

Second strength: Pricing transparency (18% of reviews)
  "No hidden fees, quoted price is what you pay"
  Competitor messaging: generic "competitive pricing"
  -> Differentiation opportunity: "upfront pricing, no surprises"

Weakness: Communication delays (8% of reviews)
  "Took 2 days to hear back about scheduling"
  -> Opportunity: "respond within 2 hours" as a stated commitment
```

### 1.2 Website Analysis

Extract:
- Current positioning statement (homepage headline)
- Services/pricing offered, and whether pricing is transparent or hidden
- Credentials displayed (license, insurance, certifications, awards)
- Trust signals (testimonials, case studies, years in business, team photos)
- Call-to-action style: urgent, consultative, or transactional

Weakness signals: no visible pricing, no visible license/credentials, no recent testimonials or proof of active business, a vague CTA ("contact us") instead of an action-oriented one ("schedule a free inspection").

Strength signals: transparent pricing and packages, clear credentials, recent specific testimonials, action-oriented CTA with frictionless booking.

Example output:

```
WEBSITE AUDIT
Positioning: "Trusted HVAC experts since 1998" -- generic, common in the industry
Pricing visibility: none (red flag) -- 2 of 3 competitors show price ranges
Credentials: license #45XXX, 25 years, some testimonials -- solid but not unique
CTA: "Contact us for a free quote", phone-only
  -> Opportunity: "schedule online in 60 seconds" to reduce friction
```

### 1.3 Social Media Presence

Platforms: Facebook, Instagram, LinkedIn (if B2B), Google Business Profile.

Extract: posting frequency, content mix (project showcase / educational / customer spotlight / promotional), engagement level, tone, and whether customer comments reflect satisfaction.

Strength: posting 2x/week or more, a real content mix, meaningful engagement, professional but approachable tone.

Weakness: abandoned accounts (3+ months since last post), all-promotional content, minimal engagement, or a mismatch between the brand's claimed tone and what's actually posted.

---

## Part 2: Competitive Landscape Mapping

### 2.1 Competitor Discovery

Search queries: `[service type] [city]`, `[service type] near me`, `[service type] [city] reviews`.

For the top 5-10 local competitors, capture: positioning headline, rating and review volume, visible services/pricing, and paid advertising presence.

### 2.2 Messaging Pattern Analysis

Tally how many competitors claim each common theme (24/7 available, licensed and insured, fast response, family-owned/local, transparent pricing, warranty/guarantee, same-day service). Anything only 0-1 competitors claim is white space: a message no one owns yet, such as transparent pricing, a real warranty, online booking, or a satisfaction guarantee.

---

## Part 3: Customer Pain Point & Intent Research

Search forums and Reddit for real customer language: `[service type] [city] help`, `r/[city]` plus the service type, `[service type] problems`.

Extract: what triggers urgency (emergency vs. maintenance vs. a home sale contingency), common frustrations (long wait times, hidden fees, unprofessional behavior, no-shows, poor communication), and what customers explicitly say they value (speed, upfront pricing, professionalism, respect for the home, warranties).

---

## Part 4: Positioning Recommendation Logic

### 4.1 The Intersection

The recommended position sits at the intersection of three things:
1. A company strength the business actually delivers on (per reviews/ops, not aspiration)
2. Competitor white space (a claim no one else credibly makes)
3. A real, urgent customer need or frustration

Example:
```
Strength: 28% of reviews mention speed ("same-day", "fast")
White space: no competitor credibly claims a "2-hour response guarantee"
Customer need: "can't reach anyone fast" is the #1 complaint
-> Recommended positioning: "2-hour response guarantee, always"
```

### 4.2 Positioning Statement

One or two sentences. It should own a single, defensible, ownable claim tied to a real operational capability (not just a marketing line), and it should be hard for competitors to copy because it's backed by how the business actually operates.

- Weak: "We're the best electrician in town" (everyone says this)
- Strong: "Emergency electrician, 2-hour response time, guaranteed" (specific, ownable, credible)

If the business serves more than one segment (e.g. homeowners and contractors), a secondary positioning statement can address the second segment separately.

### 4.3 Messaging Pillars

Three supporting claims that reinforce the primary positioning, each grounded in something real:

- Good: "Licensed, insured, certified" (trust), "Upfront quote before work starts" (transparency), "Warranty on all work" (confidence)
- Bad: "We've been around 20 years" (company-centric, not a customer benefit), "Friendly staff" (expected, not differentiated), "We love what we do" (a claim with no proof behind it)

---

## Part 5: Quality Assurance Checklist

Before finalizing any audit output, confirm:
- At least 3 sources checked (reviews, own website, competitor sites, social media)
- The positioning claim is defensible: grounded in real reviews/ops (not invented), different from at least 70% of competitors, and addresses a real customer pain point
- White space is actually white: not already owned by a stronger competitor, and something the business can actually deliver on
- Customer language is pulled from real sources (reviews, forums, search terms), not assumed

Reject the output if: every claim is generic ("fast, reliable, professional"), the claimed white space is already occupied by competitors, the recommended positioning contradicts what the company's own reviews say about it, or there's no real customer validation behind the pain point being targeted.

Accept the output if: at least 2 of 3 messaging pillars have specific, customer-quoted validation, the positioning is genuinely differentiated within the competitive set, and the customer pain point it addresses is real and urgent.
