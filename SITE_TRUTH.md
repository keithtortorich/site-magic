# Site Magic truth: Apex Comfort Solutions

Status: canonical HVAC reference direction  
Scope: single-page, mobile-first HVAC lead-generation site  
Last updated: 2026-10-15

This is the design and composition truth for Site Magic's premium HVAC output.
It defines what the page should feel like and how it should guide a visitor to
contact the business. It does not create business facts. Tenant facts,
verified proof, and company brand constraints override this reference wherever
they differ.

## Product promise

Make an urgent or considered HVAC visitor feel that the next step is obvious,
safe, and fast: call now, or submit a short service request without leaving the
page.

## Visual direction

Use a modern, ultra-professional, high-trust system:

| Role | Reference token | Usage |
| --- | --- | --- |
| Deep slate | `#101B2C` | page background, primary text on light surfaces |
| Slate surface | `#1D2D45` | cards and secondary dark surfaces |
| Crisp white | `#F7FBFF` | primary text on dark surfaces |
| Electric blue | `#54C7F7` | primary CTA, links, trust accents |
| Amber | `#FFB33E` | urgent CTA and high-attention action accents |
| Cool neutral | `#F5F8FC` | light sections and form backgrounds |

Use the tenant's supplied brand colors when available. Preserve contrast and
readability over a literal palette match. Every interactive target must remain
visibly distinct in keyboard focus and on small screens.

Typography is bold, clean sans-serif for headings and highly readable sans-serif
for body copy. Headings are compact and confident; body copy is short enough to
scan during an emergency search.

## Canonical page structure

Render these sections in this order:

1. **Navigation** — logo placeholder, `Services`, `Reviews`, `Contact`, and a
   prominent `Call Now` action. The phone action must remain easy to reach on
   mobile.
2. **Hero** — exact headline: “Experience True Climate Control. Fast, Reliable
   HVAC Services.” Include a short supporting value proposition, a
   `Schedule Service Online` CTA, a direct-call CTA, a striking HVAC imagery
   placeholder, and an immediate form with `Zip Code`, `Service Needed`,
   `Name`, and `Phone`.
3. **Trust badges** — `Emergency 24/7 Service`, `Licensed & Insured`, and
   `Google 5-Star Rated`. Show only the badges supported by tenant facts. A
   missing fact is omitted or rendered as a clearly marked demo placeholder;
   it is never silently invented.
4. **Core services** — three hover-capable cards: `AC Installation & Repair`,
   `Heating System Maintenance`, and `Indoor Air Quality Solutions`.
5. **Why choose us** — four quick-read icon layouts: `Upfront Pricing`,
   `Certified Technicians`, `100% Satisfaction Guarantee`, and `Local &
   Family-Owned`. Render each claim only when it is supplied or approved as
   non-factual authored positioning.
6. **Social proof** — a three-card review grid or accessible carousel with
   five-star treatment. Reviews, names, ratings, and review counts must come
   from verified tenant facts. For demos, label the content as illustrative
   and “replace with verified customer proof.”
7. **Footer** — copyright, navigation links, and the active phone number with
   emergency availability visible.

## Conversion rules

- The primary action is the short schedule form; the secondary action is a
  `tel:` link.
- Keep the form visible beside the hero imagery on desktop and immediately
  after the headline on mobile.
- Use one clear CTA label consistently: `Schedule Service Online`.
- Preserve high-intent anchors: `#services`, `#reviews`, and `#contact`.
- Use a reassuring, specific microcopy style: clear next step, response
  expectation only when supplied, and no invented guarantees.

## Responsive contract

- Mobile is the default priority because emergency HVAC searches are
  predominantly mobile.
- Collapse the navigation links while keeping `Call Now` visible.
- Stack the hero copy, form, and imagery without hiding the form behind an
  interaction.
- Use one-column service and review cards below the mobile breakpoint.
- Keep controls at least 44px tall, use readable 16px input text, and preserve
  visible focus states.
- Avoid horizontal scrolling, autoplay-only carousels, and decorative imagery
  that competes with the call or form action.

## Evidence and compatibility gates

This reference is compatible with the corpus validator and Site Magic's
fact-bound rendering model:

- `Google 5-Star Rated`, certifications, service areas, years in business,
  phone numbers, and testimonials are factual claims and require tenant
  provenance before publication.
- Placeholder imagery and composition may be authored without tenant proof,
  but must be visually distinguishable from a verified customer claim.
- Tenant brand colors override the reference colors only when they meet the
  contrast requirement; otherwise use the nearest accessible contrast-safe
  treatment and keep the tenant accent in secondary UI.
- Do not add arbitrary HTML, arbitrary CSS, invented sections, or unsupported
  review content to satisfy the visual direction.

