# NetBuild.Pro: Growth, Retention, and Investment Strategy

**Status**: Reference document, not investor-facing. **Source-aligned** with `STRATEGY.md`'s reconciled churn/CAC positions and the investment summary's stated caveats. **Written**: 2026-07-24.

**Confidence key**: Figures and framing below are illustrative planning inputs, not measured results, unless stated otherwise. See `STRATEGY.md` for the underlying reconciliation history.

---

### 1\. Executive Summary and Overall Assessment

Solid foundation. Problem and market stats are well supported by industry data. Product positioning and the Phoenix HVAC beachhead are logical. Technical status (platform live, automated tests passing) is credible.

Unit economics are attractive **if assumptions hold**, but carry material execution risk given the early stage: no paying customer has been confirmed anywhere in this repo's history as of this writing.

**Key caveats, source-aligned**:

- CAC is founder-led and organic, explicitly unproven past the first 50 free builds.  
- Churn planning is reconciled internally to **8% monthly** until real retention data exists; 5 to 6% is a target to earn, not a base case.  
- Financial ramps and the accelerated growth scenario are illustrative curve shapes between modeled milestones, not monthly forecasts.

**Investment thesis**: A high-upside SAFE opportunity at a $150,000 valuation cap, but success hinges on disciplined validation of the first 50 to 100 customers. Prioritize de-risking churn, CAC, and conversion before aggressive scaling.

---

### 2\. Market and Product Validation

Problem stats (27% of home service calls unanswered daily, etc.) align with the figures already cited in the investor proposal and investment summary. ServiceTitan, Jobber, and Housecall Pro as baseline qualification signals (not upgrade paths) is a sound positioning choice already reflected in `STRATEGY.md` Section 2b.

Early-stage reality: limited (zero confirmed) paying customers. Beachhead execution in Phoenix HVAC must be proven before Tampa or any further multi-city expansion is treated as more than illustrative.

---

### 3\. Unit Economics and Financial Targets, Revised for Conservatism

**87% gross margin** and a sub-30-day payback period (if the underlying assumptions hold) are compelling.

**CAC**: The $100 to $200 range reflects the founder-led organic funnel only. Treat any paid-acquisition CAC benchmark as not yet established. Do not present this range as a steady-state paid acquisition figure.

**Churn**: The planning assumption is **8% monthly** until 3 or more months of real retention data exist, per `STRATEGY.md` Section 4\. 5 to 6% is the target to earn, not the base case. Where 6% churn appears in existing investor materials, it should be read as an optimistic, unproven best case, not the planning base.

**Recommendations**:

- Prioritize real cohort tracking once trials begin.  
- Maintain 8% churn as the conservative internal planning base for both internal planning and investor communications.  
- Segment all metrics rigorously (trial vs. paid, contractor size, vertical) once there is enough volume.

**Revised Churn Sensitivity** (net LTV at $497/mo revenue, $150 CAC midpoint):

| Churn | Net LTV | LTV:CAC | Framing |
| :---- | :---- | :---- | :---- |
| 8% (Planning Base) | \~$5,400 | \~36x | Conservative planning assumption until real data exists |
| 6% (Target to Earn) | $7,200 | \~48x | Aspirational, not yet demonstrated |
| 5% (Stretch) | $8,640 | \~58x | Elite case, unproven |
| 10%+ (Risk Case) | ≤$4,320 | Compressed | Material pressure on unit economics if realized |

---

### 4\. Churn Reduction and Retention, Forward-Looking

No paying customers exist yet. Every protocol below is preparatory, not validated, and should not be described to investors or internally as current practice.

**Recommended Sequencing**:

- Use the first 50 trials primarily to gather real retention data.  
- Build only a lightweight onboarding checklist and basic usage reporting at this stage, informed by what the first cohort actually does.  
- Defer full Quarterly Business Review templates, formal win-back sequences, and any dedicated customer success hire until real data justifies the investment.

**Useful Future Elements** (once trials run and justify them):

- Structured onboarding sequence.  
- Usage monitoring with proactive outreach.  
- Emphasis on maintenance agreements as a retention lever.  
- NPS \+ exit-survey feedback loops.

Do not present detailed retention templates as current practice. Frame them explicitly as scaffolding to implement after initial validation.

---

### 5\. ServiceTitan Integration Strategy

Confirmed aligned with the actual codebase. The integration package (read-first Python layer over ServiceTitan V2 API using OAuth2) is code-complete and test-covered but not yet live-activated against a real tenant.

**Phased Strategy** (unchanged and matching reality):

- **Near-term**: Webhooks \+ basic V2 API surface (jobs, appointments, customers) against the developer sandbox.  
- **Interim**: Zapier or Pipedream as a faster bridge.  
- **Medium-term**: Full bidirectional sync \+ ServiceTitan Marketplace certification.

**Integration Priorities**: Lead/call activity to booking flow, bidirectional customer/job data, automated handoffs, shared ROI reporting.

This directly supports churn reduction through increased stickiness.

---

### 6\. Capital Tiers and Use of Funds

Aligned with the investment summary. Recommendation: tie fund releases (internally) to validated metrics such as real conversion and early retention data, rather than assumed ramps.

**Open Question on Maximum Capacity Allocation**: The additional $25,000 added at the Maximum Capacity tier (bringing the round to $50,000) is split, for planning purposes, into approximately $12,000 accelerated paid marketing spend, $7,000 toward a partial-year second acquisition hire, $4,500 extended runway, and $1,500 operational buffer. This split has no costed basis: every CAC figure elsewhere in this document and in the investment summary reflects the organic, founder-led channel, not a paid-acquisition cost per lead or per market. Whether $12,000 is actually sufficient to compress Tampa's launch by 5 to 7 months and stand up a third city cannot be verified until a real paid-channel CAC exists. Revisit this allocation once the first 50 free trials establish real numbers, rather than treating it as settled.

---

### 7\. Growth Trajectory and Financial Projections

- Baseline model (225 trials in month 1, 115 per month after, 10% conversion, 8% churn for planning purposes) is illustrative and unproven past the first 50 free trials.  
- The accelerated scenario (Tampa at Month 6 to 8, a third city around Month 18 to 20, ending near 400 customers and $2.39M ARR by Month 24\) is a proportional scale-up of the baseline model's shape, not an independently built cohort model. Treat the third city's timing and the \~160/\~400 customer figures as illustrative curve points between modeled milestones, not monthly forecasts.

**Revised Framing**:

- Short-term: Validate the Phoenix beachhead and the first 50 to 100 customers.  
- Medium-term: Tampa expansion only once real unit economics and retention data support it, not on a fixed calendar assumption.  
- Long-term: Multi-city scaling remains aspirational and illustrative, dependent on real conversion, churn, and CAC data that does not yet exist.

**Universal Disclaimer**: All ramps, customer counts, and ARR figures in both the baseline and accelerated scenarios are illustrative curve shapes between modeled milestones, not monthly forecasts. Actual results depend on real funnel data not yet collected.

---

### 8\. Return Scenarios and Risk Mitigation

Return multiples in the deck (2.0x to 13.4x on a $25,000 investment at various trigger valuations) remain relevant as illustrations only, with the summary's existing disclaimers.

**Primary Risks**:

- Churn higher than the 8% planning base.  
- CAC inflation once paid acquisition channels are tested.  
- Slower than modeled free-to-paid conversion.

**Mitigation Priorities**:

1. Ruthless focus on the first 50 trials and real cohort analysis before any further claims are made.  
2. Conservative planning at 8% churn, with CAC treated as founder-led-only until proven otherwise.  
3. Rapid iteration on the ServiceTitan integration to support the stickiness assumptions above.  
4. Transparent reporting to any investor on variance from these deck assumptions as real data arrives.

---

### 9\. Investor-Facing Recommendations

**Strengths**: Live, tested product; strong gross margins if assumptions hold; real, well-documented market problem; sensible, already-built integration path with ServiceTitan.

**Honest Positioning**: Describe the company as early stage, high potential, with material execution risk. Lead with the already-reconciled conservative assumptions, an 8% churn planning rate foremost among them, rather than the more optimistic figures that appear elsewhere in planning history.

**Suggested Updates to Materials**:

- Rework any churn or CAC language to match the caveats in this document rather than restating the more optimistic figures without qualification.  
- Add explicit "illustrative only" language to any growth chart or projection, matching what the investment summary's Financial Targets section already does.  
- Sequence any mention of retention tooling as planned, not operating.

**Next Actions for the Founder**:

- Run and document the first 50 trials with rigorous, real metrics before any of the above assumptions are firmed up.  
- Finalize the near-term ServiceTitan webhook and API integration against a real sandbox.  
- Use the 8% churn planning base, not 5 to 6%, in any near-term investor discussion.

