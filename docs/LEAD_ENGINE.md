# NetBuild.Pro Lead Engine (Merged Reference Design)

Status: single consolidated reference design for NetBuild.Pro's own outbound lead-gen, scoring, and follow-up system (a sales tool for finding and converting NetBuild.Pro customers). Supersedes and merges `LEAD_ENGINE_ARCHITECTURE.md` and `LEAD_ENGINE_PHOENIX_INTEGRATION.md` (2026-07-27). Not built, not wired into any code, and not part of NetBuild.Pro4.0's MVP scope. Saved as a design record for when this gets built.

## What Changed in the Merge

- One outreach sequence instead of two conflicting ones: call-led for high-score tiers, email-led nurture for the low tier.
- One scoring system: the 100-point AOKAI rubric. The base doc's looser scoring concept used the same signals and is folded in, not kept separately.
- One CRM: GoHighLevel, the repo's documented default. HubSpot Free (duplicate CRM) is dropped.
- Stack re-baselined GHL-native per CLAUDE.md: GHL handles SMS, email sequences, pipelines, and reporting. Twilio, MessageBird, Instantly, SmartLead, Privyr, Zapier, and Streamlit/Tableau move from "the stack" to "escalation options, each requiring its own founder approval if GHL proves insufficient."
- Duplicated escalation, redundancy, monitoring, and reporting sections unified.
- All epistemic flags from both source docs carried forward, plus one new one (compliance).

## Open Items Before Building Anything

1. **Nothing here is proven.** The source material called AOKAI "proven" in the same sentence it admitted the system is "documented but unexecuted." Every rate and target below (35% answer rate, 25% demo-booking rate, 3-5 new customers/week) is a hypothesis to validate in Week 1, not an expected outcome.
2. **The referenced compiled spreadsheet is unverified.** The claimed `city_niche_final_compiled.xlsx` has never been opened from this repo's tooling. Treat "ready" as unverified.
3. **Vendor approvals still required, now only two core ones:** a lead-sourcing vendor (Grape Leads or Outscraper, pay-per-use) and Retell AI outbound calling (Retell is already a product vendor, but outbound cold-calling is a new use with new per-minute spend). Anything in the escalation-options list is a further separate approval.
4. **[New] Compliance is unaddressed.** Outbound AI voice calls and cold SMS to US numbers carry TCPA, DNC-registry, and state-level obligations (consent, disclosure of automated calling, opt-out handling, calling-hour windows). Neither source doc mentioned this. Must be resolved before the first automated call or text is sent.
5. **Founder time commitment.** The rollout plan assigns 200 calls/week, with 50 calls + 50 emails on Mondays alone, all to "Founder." Confirm that is the intended owner before treating the 4-week plan as a schedule.

## Core Philosophy

The system must not rely on human memory, motivation, or manual follow-through. It relies on automation, redundancy, and time/score-based escalation, so it can handle volume without dropping leads or requiring full-time babysitting.

**The one hard rule:** if a lead has not been contacted within 48 hours, it escalates to human review, regardless of score, source, or anything else.

## Pipeline

Sourcing feeds a dedup/scoring queue (AOKAI). Scoring tiers each lead: call immediately, same day, nurture, or skip. Outreach runs the tiered sequence below through GHL + Retell. No contact in 48 hours escalates to a human. Converted leads move through demo booking, a 30-day trial (intake to site), and into the $497/mo Office Staff plan, then a retention track (30-day onboarding, monthly ROI check-ins, annual review/upsell).

## 1. Targeting & Sourcing

### Target Filter (beachhead profile)

| Factor | Criteria |
|---|---|
| Industry | HVAC (primary), then the repo's priority trade list |
| Location | Phoenix metro (beachhead), expansion cities after Week 4 review |
| Size | 3-15 employees |
| Google rating | 4.5+ stars |
| Website | None (highest-priority signal) |
| Hiring signals | Active job postings |

### Sources

| Source | Tool | Volume | Cost | Best for |
|---|---|---|---|---|
| Google Maps | Grape Leads | 50-100/city | $35-90/city | No-website contractors |
| Google Maps | Outscraper | 100-200/city | $45-120/city | Volume + extra data |
| Referrals | Manual | Variable | $0 | Highest conversion |
| Warm/CRM enrichment | Manual | Variable | Low | Existing contacts |

Redundancy: primary source down falls back to the secondary; both down falls back to manual Google Maps work; API limits queue and retry with backoff; the no-website filter gets a 10% manual sample review.

## 2. Scoring (AOKAI, 100 points)

| Category | Max | Key signals |
|---|---|---|
| Accessibility | 35 | Phone answered by a human (+15), owner answers (+10), text-enabled (+5) |
| Business size | 20 | 3-20 employees (+8), 2-8 vehicles (+5), currently hiring (+3) |
| Digital maturity | 20 | No website (+8), DIY platform (+6), no booking system (+5) |
| Revenue potential | 15 | HVAC (+15), Water Damage (+14), Roofing (+13) |
| Buying signals | 10 | Hiring office staff (+3), active reviews (+2), offers financing (+2) |

| Score | Tier | Action |
|---|---|---|
| 85-100 | 1 | Call within 1 hour |
| 70-84 | 2 | Call same day, within 4 hours |
| 55-69 | 3 | Nurture sequence, weekly check-in |
| <55 | 4 | Skip, remove from active list |

Scoring runs in-house (Python + SQLite, matching this repo's patterns) with a 10% manual review sample. A Google Sheets tracker is acceptable for Week 1 manual validation only; it is a scaffold, not the system.

## 3. Outreach Sequences

### Tiers 1-2: call-led (7 touches)

| Touch | Day | Channel | Content |
|---|---|---|---|
| 1 | 0 | Call (Retell) | Intro + demo ask; voicemail if unanswered |
| 2 | 1 AM | SMS (GHL) | Missed-you follow-up, reply YES for demo link |
| 3 | 1 PM | Call (human) | Follow-up if SMS unanswered |
| 4 | 2 | Email (GHL) | "You left money on the table last Tuesday" |
| 5 | 3 | SMS (GHL) | Demo ask |
| 6 | 5 | Call (human) | Final attempt |
| 7 | 7 | SMS (GHL) | Last check-in with demo link |

### Tier 3: nurture, email-led (5 touches)

| Touch | Day | Channel | Content |
|---|---|---|---|
| 1 | 0 | Email | Hook: value left on the table |
| 2 | 3 | Email | Case study |
| 3 | 7 | Email | Demo offer |
| 4 | 10 | SMS | Short check-in |
| 5 | 14 | Email | Breakup |

### Response handling (all tiers)

| Response | Action |
|---|---|
| "Yes, interested" | Demo booking link |
| "Maybe, send info" | Case study + scheduling link |
| "Not now" | Tag warm, re-engage in 30 days |
| "No" | Tag cold, archive after 30 days |
| No response | Finish sequence, then human review |

3 failed call attempts tags the lead Nurture for a 30-day re-engage.

### Call scripts

Cold call (60-90 sec): opens by asking how many calls they missed this week, positions WebStaffr as recovering those missed calls with a 24/7 receptionist, closes with a low-pressure 10-minute demo ask. Voicemail (20 sec): same positioning, shorter, asks for a callback. SMS: same positioning, asks for a YES reply to get a demo link.

## 4. Escalation & Fail-Proof

| Level | Trigger | Action |
|---|---|---|
| Hard rule | No contact within 48 hours | Human review, no exceptions |
| Score | AOKAI > 80 | Founder notified; personal outreach within 4 hours |
| Volume | Lead volume drops > 30% | Weekly review of sources |
| Quality | Response rate < 5% for a week | Copy/script review |

### Redundancy

| Component | Primary | Backup |
|---|---|---|
| Sourcing | Grape Leads | Outscraper, then manual |
| Voice | Retell AI | Human call |
| SMS + Email | GHL-native | Dedicated senders (Twilio/Instantly), only if GHL deliverability or volume proves insufficient; separate approval |
| CRM | GoHighLevel | Manual CSV export |
| Scoring | In-house algorithm | 10% manual review batch |
| Reporting | GHL dashboards | Weekly manual report |

## 5. Tracking & Reporting

Tracker fields (Sheets for Week 1, then GHL/in-house): Lead ID, City, Niche, Business Name, Owner Name, Phone, Email, Website, Has Website?, Franchise?, Reviews, Est. Employees, Est. Trucks, Source, Scraped Date, Phone Verified?, five AOKAI sub-scores, Total Score, Tier, Status (New, Contacted, Demo Booked, Demo Done, Pilot, Lost, Nurture, DNC), Attempts, Last Contact, Next Follow-up, Call Disposition, Notes, Outcome.

Daily view: leads today, response rate, demos booked, revenue recovered, status breakdown, top cities, active alerts (leads pending over 48 hours). Weekly founder report: totals and week-over-week change, top city/niche, channel-level response rates, conversions, pipeline by stage, underperforming segments, next week's priorities.

## 6. Targets & Alerts (hypotheses, no historical data)

| KPI | Target | Alert if |
|---|---|---|
| Leads imported/week | 200+ | <100: increase search |
| Calls attempted/week | 200 | Volume < 50% expected for 2 days: check source |
| Phone answer rate | 35%+ | <25%: check data quality |
| Owner conversations | 25% of answered | <15%: re-record opener |
| Demos booked | 25% of conversations | <10%: review script |
| Demo show rate | 75%+ | <50%: improve confirmation |
| Pilot close rate | 25% of demos | <10%: review demo process |
| New customers | 3-5/week | Review at Week 4 |
| Payback period | <2 months | >3 months: review pricing |
| System errors | 0 | Any: alert immediately |
| Queue backlog | <100 leads | >100 for 24h: increase processing |

## 7. Stack (streamlined; nothing approved yet)

| Category | Tool | Cost | Status |
|---|---|---|---|
| Lead sourcing | Grape Leads (or Outscraper) | Pay-per-use | New vendor, needs approval |
| Voice | Retell AI | ~$0.13-0.31/min | Existing vendor, new outbound use, needs approval + compliance check |
| CRM, SMS, email, reporting | GoHighLevel | Existing ~$97/mo | Repo default, already planned |
| Dedup/scoring | Python + SQLite | $0 | In-house |
| Week-1 tracker | Google Sheets | $0 | Scaffold only |

Escalation options, each a separate future approval only if a GHL-native piece proves insufficient: Instantly/SmartLead (email volume), Twilio/MessageBird (SMS), Privyr (WhatsApp), Zapier (glue), Streamlit/Tableau (dashboards), HubSpot (not planned; duplicate CRM).

## 8. Phoenix HVAC Beachhead Rollout

Weekly cadence: Monday 50 calls + 50 emails; Tuesday SMS follow-up; Wednesday 50 calls + email #2; Thursday follow-ups; Friday demos + weekly report.

| Week | Focus | Expected leads |
|---|---|---|
| 1 | Foundation: tracker, source Phoenix HVAC, call top 50 | 100-150 |
| 2 | Scale: add Phoenix Plumbing + Electrical, full sequence, refine scripts | 200-300 |
| 3 | Expand: add Huntsville AL, test Knoxville TN, build case studies | 300-400 |
| 4 | Optimize: review conversion data, scale winning cities, add referral loop | 400-500 |

Candidate expansion cities from source material: Huntsville, Knoxville, Greenville, Colorado Springs, Boise, Des Moines, Charleston, Madison. City scale/hold/drop decision at end of Week 4, based on data that does not exist yet.

## 9. Immediate Next Steps (in order, each gated)

1. Founder decisions: sourcing vendor, Retell outbound approval, rollout owner (Open Items 3 and 5).
2. Resolve the compliance question (Open Item 4) before any automated outbound.
3. Week-1 manual validation: set up the tracker, source Phoenix HVAC, score, call the top 10 by hand.
4. Review Week-1 metrics against the hypotheses before committing to the 4-week plan or any automation build.
