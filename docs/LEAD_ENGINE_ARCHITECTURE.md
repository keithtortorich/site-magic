# NetBuild.Pro Lead Engine — Architecture Reference (Superseded)

**Superseded 2026-07-27 by [`LEAD_ENGINE.md`](LEAD_ENGINE.md)**, which merges this doc and `LEAD_ENGINE_PHOENIX_INTEGRATION.md` into one consolidated design (single scoring system, single sequence, GHL-native stack). Kept here verbatim for history only — read `LEAD_ENGINE.md` for current reference.

Status: reference design for NetBuild.Pro's own outbound lead-gen/follow-up system (a sales tool for finding and converting NetBuild.Pro customers). Not built, not wired into any code, and not part of the NetBuild.Pro4.0 backend's MVP scope. Saved here as a design record for when this gets built.

## Open Items Before Building Anything

1. **The referenced compiled spreadsheet is unverified.** The source material claims a finished file at `city_niche_final_compiled.xlsx` in another tool's working directory. That path isn't accessible here and the claim hasn't been independently confirmed — treat "ready" as unverified until someone actually opens the file.
2. **SMS/voice vendor choice conflicts with this repo's documented default.** CLAUDE.md's Telephony/SMS default is GHL-native call events and the GHL Conversations API, with Twilio/Telnyx introduced only when explicitly required. This design specs Twilio as primary SMS with MessageBird as backup. That may be the right call for an internal sales tool (separate from the customer-facing product), but it should be a deliberate decision, not an inherited default.
3. **This design specs 7+ new paid vendors** (Grape Leads, Outscraper, Instantly, SmartLead, Twilio, MessageBird, Streamlit/Tableau, on top of the already-used GoHighLevel and Retell AI). Each is a real vendor-selection decision and recurring cost — founder approval territory before any of them get connected.

## Core Philosophy

The system is built to not rely on human memory, motivation, or manual follow-through. It relies on automation, redundancy, and time/score-based escalation, so it can handle high volume without dropping leads or requiring full-time babysitting.

## Pipeline Overview

Lead generation (multiple sources) feeds a deduplication/scoring queue, which feeds a follow-up engine (status tracking + multi-channel outreach automation), which feeds an escalation protocol (human review, founder alerts, weekly reports), which feeds a dashboard.

## 1. Lead Generation

| Source | Tool | Volume | Cost | Best for |
|---|---|---|---|---|
| Google Maps | Grape Leads | 50-100/city | $35-90/city | No-website contractors |
| Google Maps | Outscraper | 100-200/city | $45-120/city | Volume + extra data |
| CRM enrichment | HubSpot/LinkedIn | Variable | Low | Warm leads |
| Referrals | Manual | Variable | $0 | Highest conversion |
| Cold email | Instantly/SmartLead | 1,000+/week | ~$100/mo | Scalable outreach |

Redundancy: if Grape Leads is down, fall back to Outscraper; if Outscraper is down, fall back to manual Google Maps scraping; if an API limit is hit, queue and retry with exponential backoff; if the no-website filter misses cases, run a manual 10% sample review.

### Lead Scoring (concept)

Points awarded for: no website (highest priority) or a basic/outdated one; a review count in a healthy established-business range (15-180, with diminishing weight above that); 2+ years in business (more for 5+); emergency-service offerings; and suburb-type service areas over dense downtown ones. This is a scoring *concept* from the source material, not tested or implemented code.

## 2. Follow-Up Engine

### 7-Touch Sequence

| Touch | Channel | Timing | Content |
|---|---|---|---|
| 1 | Email | Day 0 | Hook: value left on the table |
| 2 | SMS | Day 1 | Short check-in |
| 3 | Email | Day 3 | Case study (a competitor's site) |
| 4 | Voice (Retell) | Day 5 | AI call, voicemail if unanswered |
| 5 | Email | Day 7 | Demo offer |
| 6 | SMS | Day 10 | Final check-in |
| 7 | Email | Day 14 | Breakup email |

State machine: each touch triggers the next after a fixed delay; the sequence ends in an "archive" state. If there's no response by day 14, the lead is flagged for human review.

### Response Handling

| Response | Action |
|---|---|
| "Yes, interested" | Demo booking link |
| "Maybe, send info" | Case study + scheduling link |
| "Not now" | Tag warm, re-engage in 30 days |
| "No" | Tag cold, archive after 30 days |
| No response | Continue sequence, then escalate to human |

## 3. Fail-Proof Mechanisms

### Redundancy Layer

| Component | Primary | Backup |
|---|---|---|
| Email | Instantly | SmartLead |
| SMS | Twilio | MessageBird |
| Voice | Retell AI | Human call (escalation) |
| CRM sync | GoHighLevel | Manual CSV export |
| Lead scoring | Algorithm | Manual review batch |

### Monitoring Thresholds

| Metric | Threshold | Action |
|---|---|---|
| Lead volume < 50% of expected | 2 days | Check data source |
| Response rate < 5% | 1 week | Review messaging |
| Demo conversion < 2% | 1 week | Review qualification |
| System error count > 0 | Immediate | Alert engineering |
| Queue backlog > 100 leads | 24 hours | Increase processing |

### Escalation Levels

| Level | Trigger | Action |
|---|---|---|
| 1 | Lead score > 80 | Human outreach within 4 hours |
| 2 | Lead score > 60 | Founder notification |
| 3 | Lead volume drops > 30% | Weekly review |
| 4 | Response rate < 5% | Copy review |

**The one hard rule:** if a lead hasn't been contacted within 48 hours, it escalates to human review, regardless of anything else.

## 4. Dashboard & Reporting

Daily view: leads today, response rate, demos booked, revenue recovered, a status breakdown (new/warm/hot/cold/demo/closed), top-performing cities, and active alerts (e.g. leads pending over 48 hours).

Weekly report (to founder): total leads and week-over-week change, top city/niche, channel-level response rates (email open/click, SMS response, voice connect), conversions (demos, sites built, subscriptions, revenue recovered), pipeline totals by stage, alerts on underperforming segments, and next week's priorities.

## 5. Tools & Stack (as designed, not yet approved)

| Category | Tool | Cost | Purpose |
|---|---|---|---|
| Lead generation | Grape Leads | Pay-per-use | Primary source |
| Lead generation | Outscraper | Pay-per-use | Backup/volume |
| Email outreach | Instantly | ~$100/mo | Sequences |
| SMS | Twilio | ~$0.0075/msg | Follow-ups (see Open Item 2) |
| Voice | Retell AI | ~$0.13-0.31/min | AI calling |
| CRM | GoHighLevel | ~$97/mo | Lead management |
| Dashboard | Streamlit/Tableau | $0-50/mo | Reporting |
| Dedup/scoring | Python + SQLite | $0 | In-house |

## 6. Manual Override Protocol

| Scenario | Manual action | Owner |
|---|---|---|
| Lead score > 80 | Personal email from founder | Founder |
| "No" but business is 5+ years old | Re-engagement email | Ops |
| Sequence stalled at step 3 | Manual call | Sales |
| New city launch | First 10 leads manually vetted | Ops |

### Weekly Review Cadence

| Day | Review | Owner |
|---|---|---|
| Monday | Lead volume and quality | Ops |
| Wednesday | Sequence performance | Ops + Founder |
| Friday | Weekly report + next week's plan | Founder |
| End of month | Pipeline review + budget | Founder |

## Summary

Lead generation is redundant across sources with a dedup/scoring queue. Follow-up runs a 7-touch sequence across 4 channels. Escalation is both time-based (48-hour rule) and score-based. Monitoring is a daily dashboard plus a weekly founder report. Cost is pay-per-use plus fixed monthly, intended to stay predictable. The founder is meant to be alerted only when something breaks or a high-value lead needs a personal touch.
