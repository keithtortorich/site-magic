# Site Weaver — Local SEO / ASO Optimization Blueprint

**Status: reference spec, not implemented anywhere.** Site Weaver is the Lovable project that
renders customer/tenant sites from `/sites/{tenant_id}` (see `docs/DECISIONS.md`, 2026-07-27
entries). Per `CLAUDE.md`'s MVP Scope, frontend/site generation is delegated to Lovable — this
repo's job is the backend data (`site_data.py`'s projection) that feeds it, not the SEO/markup
implementation itself. This doc is saved here so the spec isn't lost between sessions and so it's
available to hand to the Lovable agent when SEO work on Site Weaver is scheduled.

**Founder note:** SEO and ASO are to be treated as tantamount (equal priority) to the rest of the
Site Weaver build, not an afterthought.

**Provenance:** provided by founder 2026-07-27, verbatim content below except for this header and
the flag noted immediately after.

## Flag before use — one conflict with this repo's invariants

Section 3's "Review Schema" example hardcodes a specific fabricated review (author "Mike R.",
`ratingValue: 4.9`, `reviewCount: 127`, an invented quote) as boilerplate JSON-LD. Taken literally,
that's exactly the no-fabrication problem already found and logged live on the WebStaffr Agency
Site preview (`docs/DECISIONS.md`, 2026-07-27: "fabricated-looking stats... presented as if real").

When this blueprint is handed to Lovable for implementation: the *schema structure* (the
`AggregateRating`/`Review` JSON-LD shape) is reusable, but the **values must always be populated
from real tenant data** (`site_data.py`'s actual testimonials/ratings) — never from this example's
placeholder numbers, and the Review/AggregateRating blocks should be omitted entirely for a tenant
with no real reviews on file, per this repo's no-fabrication invariant and the never-leak/no-filler
rule in `CLAUDE.md`.

Everything else below is otherwise implementable as written.

---

## Objective
Generate trade websites that rank #1–#3 in local search results for high-intent keywords like "AC repair [city]," "plumber near me," and "emergency electrician [city]."

---

## 1. Local SEO Architecture for Site Weaver Output

### URL Structure
```
https://[business-name].webstaffr.com/
├── /                    # Homepage (primary keyword: [service] + [city])
├── /services/           # Service listing page
│   ├── /ac-repair/      # Individual service page
│   ├── /ac-installation/
│   └── /maintenance-plans/
├── /about/              # Founder story, team, credentials
├── /reviews/            # Review aggregation page
├── /contact/            # Contact form, phone, map
└── /blog/               # (Optional) Local content
    ├── /5-signs-your-ac-needs-repair/
    └── /why-phoenix-homeowners-choose-heat-pumps/
```

### URL Naming Convention
| Page | URL Pattern | Example |
|------|-------------|---------|
| Homepage | `/[business-slug]/` | `/desert-cooling/` |
| Service Page | `/[business-slug]/[service-slug]/` | `/desert-cooling/ac-repair/` |
| Location Page | `/[business-slug]/[service-slug]/[city-slug]/` | `/desert-cooling/ac-repair/phoenix/` |
| About Page | `/[business-slug]/about/` | `/desert-cooling/about/` |
| Review Page | `/[business-slug]/reviews/` | `/desert-cooling/reviews/` |

---

## 2. On-Page SEO Elements

### Homepage
```html
<!-- Title Tag -->
<title>AC Repair & HVAC Services in Phoenix | Desert Cooling | 24/7 Emergency</title>

<!-- Meta Description -->
<meta name="description" content="Desert Cooling provides expert AC repair, installation, and maintenance in Phoenix. 24/7 emergency service. Licensed & insured. Free estimates." />

<!-- H1 -->
<h1>AC Repair & HVAC Services in Phoenix — Desert Cooling</h1>

<!-- H2s -->
<h2>Why Phoenix Homeowners Choose Desert Cooling</h2>
<h2>Our HVAC Services</h2>
<h2>What Our Customers Say</h2>
<h2>Serving Phoenix and Surrounding Areas</h2>
<h2>24/7 Emergency AC Repair in Phoenix</h2>

<!-- Body Copy (500+ words) -->
<p>Desert Cooling has been keeping Phoenix homes cool since 2008. We specialize in AC repair, installation, and maintenance for residential and commercial properties. Our licensed technicians respond to emergency calls 24/7—even at 2 a.m. when your AC dies in July.</p>
<p>As a locally-owned HVAC company, we understand Phoenix's unique climate challenges. Our team is trained in the latest HVAC technology and uses only manufacturer-approved parts. We offer transparent pricing, free estimates, and a satisfaction guarantee on every job.</p>
```

### Service Page (AC Repair)
```html
<!-- Title Tag -->
<title>AC Repair in Phoenix — Fast & Reliable HVAC Service | Desert Cooling</title>

<!-- Meta Description -->
<meta name="description" content="Desert Cooling provides expert AC repair in Phoenix. Fast response, transparent pricing, and 100% satisfaction guaranteed. Call now for emergency service." />

<!-- H1 -->
<h1>AC Repair in Phoenix — Fast & Reliable Service</h1>

<!-- Body Copy -->
<p>When your AC breaks in Phoenix, you need a repair company that responds fast. Desert Cooling offers same-day AC repair service throughout the Phoenix metro area.</p>

<!-- Service Area List -->
<h2>We Serve These Phoenix-Area Communities</h2>
<ul>
  <li>Phoenix</li>
  <li>Scottsdale</li>
  <li>Tempe</li>
  <li>Mesa</li>
  <li>Chandler</li>
  <li>Gilbert</li>
  <li>Glendale</li>
  <li>Peoria</li>
</ul>
```

---

## 3. Schema Markup (Local SEO)

### LocalBusiness Schema
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "HVACBusiness",
  "name": "Desert Cooling",
  "description": "AC repair, installation, and maintenance services in Phoenix.",
  "image": "https://desertcooling.webstaffr.com/images/logo.png",
  "url": "https://desertcooling.webstaffr.com/",
  "telephone": "+1-602-555-1234",
  "email": "info@desertcooling.com",
  "priceRange": "$$",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "1234 E Main St",
    "addressLocality": "Phoenix",
    "addressRegion": "AZ",
    "postalCode": "85001",
    "addressCountry": "US"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": 33.4484,
    "longitude": -112.0740
  },
  "openingHours": "Mo-Su 00:00-23:59",
  "openingHoursSpecification": [
    {
      "@type": "OpeningHoursSpecification",
      "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
      "opens": "00:00",
      "closes": "23:59"
    }
  ],
  "sameAs": [
    "https://facebook.com/desertcooling",
    "https://instagram.com/desertcooling"
  ],
  "areaServed": {
    "@type": "City",
    "name": "Phoenix"
  },
  "hasMap": "https://maps.google.com/maps?q=1234+E+Main+St+Phoenix+AZ"
}
</script>
```

### Service Schema
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Service",
  "serviceType": "AC Repair",
  "provider": {
    "@type": "HVACBusiness",
    "name": "Desert Cooling"
  },
  "areaServed": {
    "@type": "City",
    "name": "Phoenix"
  },
  "description": "Expert AC repair services in Phoenix. Fast response, transparent pricing, and 100% satisfaction guaranteed.",
  "offers": {
    "@type": "Offer",
    "price": "49",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock",
    "url": "https://desertcooling.webstaffr.com/ac-repair/"
  }
}
</script>
```

### Review Schema
> **See flag above — values in this example are illustrative only. Populate from real tenant
> data; omit the block entirely if the tenant has no real reviews on file.**
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "HVACBusiness",
  "name": "Desert Cooling",
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.9",
    "reviewCount": "127",
    "bestRating": "5",
    "worstRating": "1"
  },
  "review": [
    {
      "@type": "Review",
      "author": {
        "@type": "Person",
        "name": "Mike R."
      },
      "reviewRating": {
        "@type": "Rating",
        "ratingValue": "5",
        "bestRating": "5"
      },
      "reviewBody": "Desert Cooling saved us on a 115-degree day. They arrived within 2 hours and fixed our AC fast. Fair price, great service.",
      "datePublished": "2026-07-20"
    }
  ]
}
</script>
```

### FAQ Schema
```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "How much does AC repair cost in Phoenix?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "AC repair costs in Phoenix typically range from $150–$800 depending on the issue. Desert Cooling provides free estimates and transparent pricing before any work begins."
      }
    },
    {
      "@type": "Question",
      "name": "Do you offer emergency AC repair in Phoenix?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "Yes. Desert Cooling offers 24/7 emergency AC repair in Phoenix. Call us anytime—we respond within 2 hours."
      }
    }
  ]
}
</script>
```

---

## 4. Content Generation from Intake Data

### Mapping Intake Fields to SEO Content
| Intake Field | SEO Output |
|--------------|------------|
| **Business Name** | Used in title, H1, meta description, schema |
| **Industry / Trade** | Determines primary keyword (e.g., "HVAC" → "AC repair") |
| **Service Area** | Used in location pages, service area list, schema |
| **Services** | Used for individual service pages (e.g., "AC Repair," "Furnace Installation") |
| **Mission** | Used in "About Us" section and body copy |
| **#1 Reason Customers Choose You** | Used as H2 ("Why Customers Choose [Business Name]") and body copy |
| **Competitors** | Used for differentiation and competitive keyword research |
| **Tagline** | Used in meta description and hero section |
| **Testimonials** | Used in review schema and trust section |
| **License #s** | Used in footer, schema, and trust bar |
| **Photos** | Used for image alt text and visual content |

### Content Generation Rules
| Page | Content Source | SEO Priority |
|------|---------------|--------------|
| **Homepage** | Mission + Tagline + #1 Reason + Services | High (primary keywords) |
| **Service Pages** | Services list + Service Area | High (long-tail keywords) |
| **Location Pages** | Service Area + City names | High (city-specific keywords) |
| **About Page** | Mission + Founder Story + License #s | Medium (brand keywords) |
| **Reviews Page** | Testimonials + Review link | Medium (trust signals) |
| **Contact Page** | Address + Phone + Map | Low (conversion focus) |

### Homepage Content Template
```html
<h1>[Business Name] — [Primary Service] in [City]</h1>
<p>[Business Name] has been serving [City] since [Year]. We specialize in [Service 1], [Service 2], and [Service 3] for [Industry] customers. Our licensed technicians respond to emergency calls 24/7.</p>

<h2>Why [City] Homeowners Choose [Business Name]</h2>
<p>[Reason 1]. [Reason 2]. [Reason 3].</p>

<h2>Our [Industry] Services</h2>
<ul>
  <li><a href="/[service-1-slug]/">[Service 1]</a></li>
  <li><a href="/[service-2-slug]/">[Service 2]</a></li>
  <li><a href="/[service-3-slug]/">[Service 3]</a></li>
</ul>

<h2>What Our Customers Say</h2>
<p>"[Testimonial 1]" — [Customer Name]</p>
<p>"[Testimonial 2]" — [Customer Name]</p>

<h2>Serving [City] and Surrounding Areas</h2>
<ul>
  <li>[City 1]</li>
  <li>[City 2]</li>
  <li>[City 3]</li>
</ul>

<h2>24/7 Emergency [Service] in [City]</h2>
<p>Call us anytime: <a href="tel:[Phone]">[Phone]</a></p>
```

---

## 5. Local SEO Checklist

### Technical SEO
- [ ] SSL certificate installed (HTTPS)
- [ ] XML sitemap submitted to Google Search Console
- [ ] robots.txt file configured
- [ ] Page speed < 3s (mobile & desktop)
- [ ] Mobile-responsive design
- [ ] Schema markup implemented (LocalBusiness, Service, Review, FAQ)
- [ ] Canonical tags on all pages
- [ ] Structured data testing passed (Google Rich Results Test)

### Content SEO
- [ ] Title tag contains primary keyword + city + business name
- [ ] Meta description contains primary keyword + city + call to action
- [ ] H1 contains primary keyword + city
- [ ] Body copy 500+ words
- [ ] Service pages for each top service
- [ ] Location pages for each city served
- [ ] NAP (Name, Address, Phone) consistent across all pages
- [ ] Google Maps embed on contact page

### Local SEO
- [ ] Google Business Profile claimed and verified
- [ ] NAP matches Google Business Profile exactly
- [ ] Local citations (Yelp, Yellow Pages, etc.) consistent
- [ ] Reviews actively gathered and displayed
- [ ] Local schema implemented
- [ ] City-specific service pages

---

## 6. Performance Dashboard (Site Weaver)

Add a local SEO performance section to the dashboard:

| Metric | Goal | Tracking Method |
|--------|------|-----------------|
| **Organic Traffic** | Monthly visitors from search | Google Analytics |
| **Local Pack Visibility** | Appear in Google's 3-pack | Google Search Console |
| **Keyword Rankings** | Top 3 for [service] + [city] | SEMrush / Ahrefs |
| **Click-Through Rate** | >5% from search results | Google Search Console |
| **Conversion Rate** | Visitors → calls/bookings | Call tracking + analytics |
| **Review Growth** | 4.8+ average, 10+ reviews/mo | Google Business Profile |

---

## 7. Competitive Keyword Research via RespectASO

Use RespectASO to find high-value keywords for Site Weaver customer sites:

### Keyword Research Workflow
1. **Identify Service Keywords** — From intake form (e.g., "AC repair," "plumber," "electrician")
2. **Add Location Keywords** — Service area cities (e.g., "Phoenix," "Scottsdale")
3. **Research in RespectASO** — For each [service] + [city] combination
4. **Score Keywords** — Prioritize by search volume and competition
5. **Generate Content** — Use keyword data to write SEO-optimized service pages

### Keyword Research Example
| Keyword | Search Volume | Competition | Priority |
|---------|---------------|-------------|----------|
| "AC repair Phoenix" | 1,200 | High | High |
| "emergency HVAC Phoenix" | 450 | Medium | High |
| "furnace repair Phoenix" | 320 | Medium | Medium |
| "AC installation Scottsdale" | 280 | Low | High |

---

## 8. Summary

| Element | SEO Impact |
|---------|------------|
| **URL Structure** | [service] + [city] = high-intent keyword targeting |
| **Title Tags** | Primary keyword + city + business name |
| **H1s** | Primary keyword + city |
| **Service Pages** | Long-tail keyword targeting for each service |
| **Location Pages** | City-specific landing pages |
| **Schema Markup** | Rich snippets in search results (stars, reviews, hours) |
| **GBP Integration** | Local pack visibility |
| **Reviews** | Trust signals + review schema |
| **Page Speed** | Core Web Vitals for ranking |
| **Mobile Responsiveness** | Mobile-first indexing |

The Site Weaver output is now optimized to rank #1–#3 in local search results, driving high-intent traffic to customer websites.
