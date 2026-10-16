# NetBuild.Pro Agency Site — Design Direction & Visual Identity

**Status:** Phase 1 Complete (Hero + Section Pattern Extended)  
**Last updated:** 2026-08-03  
**Applies to:** NetBuild.Pro Agency Site  
**Problem:** Current site is visually generic (dark-mode SaaS template), lacks brand personality, doesn't communicate the *recurring* nature of the service or the "we stay, not disappear" ethos.

---

## Current State (What's Broken)

The existing site uses a safe, forgettable aesthetic:
- **Dark navy + gold** — common SaaS default
- **Serif + sans-serif typography** — no personality, just hierarchy
- **Grid demo cards** — static, feel like portfolio pieces, not "live" ongoing relationships
- **Pricing cards** — transactional, don't communicate "recurring excellence"
- **No motion/personality** — feels like a template, not a deliberate brand

**Core problem:** Nothing here *feels* like recurring staffing. It feels like a website builder (which is ironic, since that's what we are). The visual language doesn't communicate "Angel is with you every day" or "we're not a one-time build."

---

## Design Direction: "Recurring Motion"

**Thesis:** NetBuild.Pro is not a one-time transaction. Angel is recurring. The site should *feel* like motion, persistence, and daily presence — not a static brochure.

### Color Palette

Abandon the safe dark-mode template. Adopt a palette that **communicates aliveness and continuity:**

**Primary (Recurring):**
- **Deep teal/peacock** (#1a4d5e or similar) — evokes "24/7," continuity, ocean/flow
- **Warm gold/amber** (#d4a574 or similar) — energy, human touch, warmth

**Secondary:**
- **Cream/off-white** (#f5f1e8 or similar) — approachability, not sterile
- **Dark slate** (#2a3a42 or similar) — for contrast text

**Accent (Motion):**
- **Bright copper/rust** (#c85a3a or similar) — small accent for CTAs, highlights (not the primary gold)
- **Soft green** (#6b9e7f or similar) — life, growth, "business thriving"

**Why this works:**
- Teal is "24/7" without being cold
- Gold is "premium" and "warm"
- The palette avoids the generic dark-SaaS look entirely
- Copper accent = motion, energy, differentiates CTAs

### Typography

**Do not:** Mix serif + sans-serif passively. **Do:** Use typography to show personality.

**Headings (Display):**
- **Font:** A confident, slightly geometric sans-serif (e.g., Poppins Bold, Inter Bold, or custom sans with character)
- **Style:** All-caps or Title-case, with deliberate letter spacing
- **Color:** Teal primary, with gold accents on key words (e.g., "Your business **deserves a website**" with "website" in gold, not italic)
- **Size:** Hero H1 could be 4–5rem on desktop (massive, bold)

**Body/UI:**
- **Font:** Clean sans-serif (Poppins, Inter, or equivalent)
- **Color:** Dark slate for primary copy, teal for emphasis
- **Line height:** Generous (1.6–1.8) for readability

**No serif headings.** Serif feels "established" and "editorial," not "built in 48 hours." Go geometric and confident.

### Layout & Spacing

**Hero Section (NEW PATTERN — IMPLEMENTED 2026-08-03):**
- **Icon badge on right** (wrench, briefcase, mail, or service icon — 56px)
- **Text on left:** eyebrow + headline + body + badges (if applicable) + CTAs
- **Grid layout** ensures alignment and visual balance across all pages
- **Applied to:** `home.html` (2026-07-29), `service.html`, `about.html`, `contact.html` (2026-08-03)

**Demo Gallery:**
- **Grid → scrollable carousel or stacked cards** (show 1–2 at a time on desktop, swipeable)
- **Each card shows a *live* agency site in real time** (iframe preview, if possible, not a static screenshot)
- **Remove the fabricated testimonial overlays** — just show the site itself
- **Label:** "Built for [Industry]. Recurring Angel. Real Results."

**Pricing Section:**
- **Shift from "three boxes" to a visual story:** 
  - "Start free" (Site alone, $0 for 30 days)
  - "Add Angel" (Site + Office Staff, $497/mo) — **highlight this as "the real value"**
  - "Scale up" (Full Front Office, custom) — de-emphasize the $97 tier as introductory
- **Use teal borders, not gold**, and copper accents on "Add Angel"
- **Tagline on middle card:** "This is where it all clicks."

**"Why WebStaffr" Section:**
- **Replace generic benefits** with a narrative about recurrence:
  - "Angel doesn't take vacations. Your receptionist does."
  - "Every month, your site stays sharp. Every call, Angel answers."
  - "No contracts = no trap. We earn your business every 30 days."

### Motion & Interaction

**Bring the site *alive* — not animation overkill, but strategic motion that communicates continuity:**

1. **Subtle scroll animations:**
   - As the user scrolls past the hero, a thin teal line grows from left to right at the top of the screen (representing time, daily continuity)
   - Demo cards slide in from the left on scroll (representing flow, motion)

2. **Angel widget behavior:**
   - If Angel chat is embedded on the page, have it show an incoming message every 5–10 seconds from different industries (e.g., "Plumber's customer just booked," "Electrician got a new lead") — reinforces "24/7 working"
   - Message bubbles appear from the right (incoming), reinforcing that Angel is *active*

3. **Pricing card interaction:**
   - "Add Angel" card has a subtle pulse or glow effect (copper accent pulsing) to draw eye to the recommended tier
   - On hover, the teal border brightens slightly

4. **Hero CTA button:**
   - Copper button with a subtle interior glow or gradient
   - On hover, it expands slightly or the background dims to make the button "pop"

5. **Testimonial/Review carousel:**
   - Auto-rotates through real customer testimonials (not fabricated) every 5–8 seconds
   - Reinforces ongoing satisfaction, not a one-time win

### Visual Hierarchy

**Prioritize:**
1. "Get started" CTA (copper, bold)
2. "Add Angel" pricing card (teal border, copper accent)
3. Demo gallery (show what the recurring relationship looks like)
4. Testimonials (show it *works* over time)
5. FAQ/fine print (teal links, not buried)

**De-emphasize:**
- The $97 "Site only" tier (it's a loss leader; doesn't communicate value)
- "Full Front Office" (it's custom; don't make it a prominent option)
- Generic "Why WebStaffr" benefit list (replace with recurring-focused narrative)

---

## Hero Copy Rewrite

**Current (Generic):**
> "Your business deserves a website. Built in 48 hours. Free for 30 days."

**New (Recurring-Focused):**

### Headline
"Your business runs every day. So does your website."

**Why:** Immediately communicates the *ongoing* nature. Not "we'll build you a site," but "your site keeps working, every day."

### Subheadline
"Angel works while you sleep. Your website works while you're booked. One flat rate, no surprises."

**Why:** Emphasizes the two-part value: website + AI receptionist, both working 24/7. "One flat rate" communicates pricing simplicity. "No surprises" differentiates from agencies that tack on fees.

### Hero CTA

**Primary:** "Get Started — Free 30 Days"  
**Secondary:** "See It Live — Live Demo"

---

## "Why WebStaffr" Rewrite

**Don't list features. Tell a story about recurrence.**

### Original (Feature-Driven)
- "A website that pays for itself"
- "No contracts, no lock-in"
- "Recurring office staff, not a one-time build"

### Revised (Recurrence-Focused)

**Headline:** "Built for every day."

1. **"Angel doesn't take vacations. Your receptionist does."**
   - Contrast: human receptionists need time off, Angel doesn't. Emphasizes 24/7 reliability.
   - Not a feature list, a philosophy.

2. **"Every month, your website stays sharp. Every call, Angel answers."**
   - "Stays sharp" = we update it, keep it fresh (not "build once and abandon")
   - "Every call" = Angel is *active*, working, not passive

3. **"No contracts. No trap. We earn your business every 30 days."**
   - Invert the "no contracts" feature into a philosophy: *we* have to earn it
   - "No trap" speaks to the fear of lock-in (common for agency-skeptical small businesses)

4. **"Speed meets substance. 48 hours to live, forever to stay sharp."**
   - "Speed meets substance" = we're fast *and* thoughtful, not just a template factory
   - "Forever to stay sharp" = the recurrence promise

---

## Implementation Roadmap

**Phase 1 (Design Update) — COMPLETE (2026-08-03):**
1. ✅ Applied new hero pattern (icon badge + grid layout) to all pages
2. ✅ Rewrite templates with new hero structure: `service.html`, `about.html`, `contact.html`
3. ✅ Updated hero copy to emphasize service/trust signals
4. ✅ Added eyebrow taglines and trust bars where applicable
5. ✅ Updated design direction doc to reflect completion

**Phase 2 (Motion & Interaction):**
1. Add scroll animations (teal progress line, slide-in cards)
2. Implement Angel activity ticker (incoming lead notifications)
3. Add pricing card pulse animation
4. Implement testimonial auto-rotate carousel

**Phase 3 (Demo Gallery Upgrade):**
1. Convert static cards to live site previews (iframe embeds if possible)
2. Remove fabricated testimonial overlays
3. Add "live" indicator to each preview (e.g., green dot + "Live")
4. Show *actual* customer sites, not generic demos

**Phase 4 (Governance Fixes):**
1. Remove all em-dashes from copy
2. Remove fabricated stats from demo cards
3. Update pricing to match Governance Manual ($497/$2,497/$5,000+)
4. Add disclaimers to demo gallery ("Illustrative examples" if using stock data)

---

## Design Principles

1. **Recurrence first:** Every visual choice should communicate "Angel is with you, every day"
2. **Warmth over sterility:** Teal + gold + cream, not dark navy + cold silver
3. **Motion over static:** Animation should feel like activity, not decoration
4. **Copy drives design:** The words come first; design amplifies them
5. **Real over fabricated:** Show actual customer wins, not generic testimonials
6. **Personality over template:** We're not a generic SaaS; design reflects that

---

## Competitive Differentiation

**Why this matters visually:**

- **vs. traditional agencies** (Wix, Squarespace sites): Our palette, motion, and copy all scream "AI-powered, 24/7, modern" — not "static brochure"
- **vs. other AI SaaS** (generic dark templates): Teal + gold + copper + serif-less typography = distinctive, ownable brand
- **vs. competitors who position as "build once"**: Our design language emphasizes recurrence, motion, daily activity — not a one-time transaction

---

## Tone & Voice

The site copy should reflect **founder voice** (Keith Tortorich), not corporate-speak:

- **Conversational, not marketing-ese:** "Angel doesn't take vacations" vs. "24/7 AI-powered virtual reception"
- **Confident, not overselling:** "Built for every day" vs. "The only solution you'll ever need"
- **Problem-first, solution-second:** Lead with the pain (missed calls, booked phones) before the fix
- **Specific over abstract:** "Your plumber gets 3 calls at 2 AM" vs. "We handle after-hours inquiries"

---

## Success Metrics

After redesign, measure:
1. **Click-through rate on "Get Started"** (should increase from current)
2. **Pricing tier selection:** "Add Angel" should be 70%+ of new signups (vs. Site-only)
3. **Time on page:** Longer = more engagement (current design is low-engagement)
4. **Demo preview clicks:** Should increase if gallery feels "live" and interactive
5. **Testimonial engagement:** Auto-rotate carousel should be watched (can measure via scroll depth)

---

## Summary: From "Generic Dark Template" to "Recurring Velocity"

**Current site:** Safe, forgettable, generic SaaS template.  
**Redesigned site:** Distinctive, warm, communicates "Angel is with you every day," Feels like a founder-led brand.

The visual identity shifts from "we build websites" to "we're your recurring team." The hero copy, color palette, and motion all reinforce that core promise.

---

**Document owner:** Claude  
**Target audience:** Design team (to implement) + founder (to approve direction)  
**Next step:** Phase 2 (motion & interaction work) when ready; Phase 3/4 deferred to later restyle passes.
