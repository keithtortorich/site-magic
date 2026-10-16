# Lead Engine: AOKAI + Phoenix HVAC Beachhead Integration (Superseded)

**Superseded 2026-07-27 by [`LEAD_ENGINE.md`](LEAD_ENGINE.md)**, which merges this doc and `LEAD_ENGINE_ARCHITECTURE.md` into one consolidated design. Kept here verbatim for history only — read `LEAD_ENGINE.md` for current reference.

Status: reference plan for NetBuild.Pro's own outbound GTM motion. Builds on [`LEAD_ENGINE_ARCHITECTURE.md`](LEAD_ENGINE_ARCHITECTURE.md)'s fail-proof infrastructure, adding a concrete lead-scoring rubric and a Phoenix HVAC beachhead rollout. Not built, not wired into any code, and not part of NetBuild.Pro4.0's MVP scope.

## Open Items Before Executing

1. **"Proven" is the wrong word.** The source material calls the AOKAI scoring system "a proven lead-scoring and outreach system" in the same sentence it admits is "documented but unexecuted." Those two things can't both be true — nothing here has been field-tested yet. Treat every rate/target below (35% answer rate, 25% demo-booking rate, 3-5 new customers/week, etc.) as a hypothesis to validate in Week 1, not an expected outcome.
2. **Same SMS/vendor conflict as the base Lead Engine doc.** Twilio + MessageBird as primary/backup SMS still conflicts with CLAUDE.md's GHL-native default. This plan adds Privyr (WhatsApp), Zapier, and HubSpot Free on top — more vendor decisions stacking up, none approved yet.
3. **This is a real financial and time commitment**, not just infrastructure: 200 calls/week, 50 calls + 50 emails on Mondays alone, all owned by "Founder" in the rollout table. Worth confirming that's actually the intended owner before treating the 4-week plan as a schedule.

## Executive Summary

Two components combine into one GTM motion: the AOKAI lead-scoring rubric (a 100-point scoring system for prioritizing which leads to call first) and the fail-proof infrastructure from `LEAD_ENGINE_ARCHITECTURE.md` (redundant sourcing, escalation, monitoring). Phoenix HVAC is the proposed beachhead market to launch and validate this in before expanding to other cities/trades.

## Pipeline

Sourcing (Grape Leads primary, Outscraper backup, manual enrichment) feeds the AOKAI scoring engine, which tiers each lead (call immediately / same day / nurture / skip). Outreach runs cold calls (Retell AI), SMS, and WhatsApp in sequence, escalating to a human after 48 hours with no contact. Converted leads move through demo booking, a 30-day trial (intake to Site Weaver), and into the $497/mo Office Staff plan, then a retention track (30-day onboarding, monthly ROI check-ins, annual review/upsell).

## 1. Lead Scoring (AOKAI, Phoenix-focused)

### Target Filter

| Factor | Criteria |
|---|---|
| Industry | HVAC (primary) |
| Location | Phoenix metro |
| Size | 3-15 employees |
| Google rating | 4.5+ stars |
| Website | None (highest-priority signal) |
| Hiring signals | Active job postings |

### 100-Point Rubric

| Category | Max points | Key signals |
|---|---|---|
| Accessibility | 35 | Phone answered by a human (+15), owner answers (+10), text-enabled (+5) |
| Business size | 20 | 3-20 employees (+8), 2-8 vehicles (+5), currently hiring (+3) |
| Digital maturity | 20 | No website (+8), DIY platform (+6), no booking system (+5) |
| Revenue potential | 15 | HVAC (+15), Water Damage (+14), Roofing (+13) |
| Buying signals | 10 | Hiring office staff (+3), active reviews (+2), offers financing (+2) |

### Tiers

| Score | Action | Timeline |
|---|---|---|
| 85-100 | Call immediately | Within 1 hour |
| 70-84 | Same day | Within 4 hours |
| 55-69 | Nurture sequence | Weekly check-in |
| <55 | Skip | Remove from active list |

## 2. Master Tracker (Google Sheets)

Columns A-AD: Lead ID, City, Niche, Business Name, Owner Name, Phone, Email, Website, Has Website?, Franchise?, Reviews, Est. Employees, Est. Trucks/Crews, Source, Scraped Date, Phone Verified?, then the five AOKAI sub-scores (Accessibility, Size, Digital, Revenue, Buying Signals), Total Score, Tier, Status, Attempts, Last Contact, Next Follow-up, Call Disposition, Notes, Outcome.

Dropdown fields: City (Phoenix, Huntsville, Knoxville, Greenville, Colorado Springs, Boise, Des Moines, Charleston, Madison), Niche (HVAC, Water Damage, Roofing, Plumbing, Garage Doors), Status (New, Contacted, Demo Booked, Demo Done, Pilot, Lost, Nurture, DNC), Call Disposition (Answered-Owner, Answered-Staff, Voicemail-Left, Voicemail-Full, Wrong Number, No Answer, DNC, Callback Requested, Demo Booked).

## 3. Outreach Sequence (Phoenix HVAC)

| Touch | Day | Channel | Content |
|---|---|---|---|
| 1 | 0 | Call (Retell AI) | Intro + demo ask |
| 2 | 1 AM | SMS | Missed-you follow-up, reply YES for demo link |
| 3 | 1 PM | Call | Human follow-up if SMS unanswered |
| 4 | 2 | Email | "You left money on the table last Tuesday" |
| 5 | 3 | WhatsApp (Privyr) | Demo ask |
| 6 | 5 | Call | Final human attempt |
| 7 | 7 | SMS | Last check-in with demo link |

Escalation: no contact in 48 hours triggers human review; AOKAI score above 80 triggers a founder email; 3 failed attempts tags the lead "Nurture" for a 30-day re-engage.

## 4. Weekly Cadence & Targets

Monday: 50 calls + 50 emails. Tuesday: SMS follow-up. Wednesday: 50 calls + email #2. Thursday: WhatsApp follow-up. Friday: demos + weekly report.

| Metric | Target |
|---|---|
| Calls attempted | 200/week |
| Answer rate | 35% |
| Owner conversations | 25% of answered |
| Demos booked | 25% of conversations |
| Demo show rate | 75% |
| Pilot close rate | 25% of demos |
| New customers | 3-5/week |

These are targets to validate, not historical results (see Open Item 1).

## 5. Automation Stack (as designed, not yet approved)

| Tool | Purpose |
|---|---|
| Grape Leads | Lead sourcing |
| Google Sheets | Master tracker + scoring formulas |
| HubSpot (Free) | CRM: status, notes, follow-ups |
| Twilio | SMS automation (see Open Item 2) |
| Privyr | WhatsApp auto-responder |
| Retell AI | Outbound voice + qualification |
| Zapier | Sheet-to-SMS-to-follow-up automation |

## 6. Call Scripts

**Cold call (60-90 sec):** opens by asking how many calls they missed this week, positions NetBuild.Pro as recovering those missed calls with a 24/7 AI receptionist, closes with a low-pressure 10-minute demo ask.

**Voicemail (20 sec):** same positioning, shorter, asks for a callback or says you'll try again tomorrow.

**Follow-up SMS:** same positioning, asks for a "YES" reply to get a demo link.

## 7. 4-Week Rollout Plan

| Week | Focus | Expected leads |
|---|---|---|
| 1 | Foundation: set up sheet, run Grape Leads for Phoenix HVAC, call top 50 | 100-150 |
| 2 | Scale: add Phoenix Plumbing + Electrical, full sequence, refine scripts | 200-300 |
| 3 | Expand: add Huntsville AL, test Knoxville TN, build case studies | 300-400 |
| 4 | Optimize: review conversion data, scale winning cities, add referral loop | 400-500 |

All tasks in the source material are owned by "Founder" (see Open Item 3).

## 8. Success Metrics & Alerts

| KPI | Target | Alert if |
|---|---|---|
| Leads imported/week | 200+ | <100: increase search |
| Phone answer rate | 35%+ | <25%: check data quality |
| Owner conversations | 25%+ | <15%: re-record opener |
| Demos booked | 25%+ | <10%: review script |
| Demo show rate | 75%+ | <50%: improve confirmation |
| Pilot close rate | 25%+ | <10%: review demo process |
| Payback period | <2 months | >3 months: review pricing |

City performance (Phoenix vs. Huntsville vs. Knoxville) is meant to be reviewed at the end of Week 4 to decide scale/hold/drop per city — no data exists yet since nothing has run.

## 9. Fail-Proof Mechanisms

Lead sourcing: Grape Leads primary, Outscraper backup, manual enrichment. Scoring: Sheets automation plus a 10% manual review sample. Outreach: Retell AI automated, human calls as escalation. SMS: Twilio primary, MessageBird backup. CRM: HubSpot primary, Sheets backup. Escalation: the 48-hour rule. Monitoring: daily dashboard plus weekly report.

## 10. The One Rule

If a lead hasn't been contacted within 48 hours, it escalates to human review — regardless of score, source, or anything else.

## 11. Immediate Next Steps

Set up the Google Sheet with AOKAI formulas, run Grape Leads for Phoenix HVAC, call the top 10 leads, set up Twilio + Zapier automations, complete the first 50 calls, then review metrics at end of Week 1 — before committing to the full 4-week plan.
