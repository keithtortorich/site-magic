# Gemini and Grok work assignments

These assignments are deliberately bounded. Neither model is an authority for
SERP rank, tenant facts, plan approval, quality gates, checkpoint acceptance,
or publication.

## Gemini: visual corpus analyst

Input: validated public-corpus screenshots and short DOM excerpts only.

Return JSON matching `schemas/model-analysis.schema.json` with
`worker=gemini-visual`, `tenantMode=public-research`, and findings for:

- section order and hierarchy;
- mobile/desktop layout relationships;
- CTA visibility and form friction;
- trust-signal presentation;
- visible accessibility issues;
- image and spacing patterns.

Every finding needs a screenshot or DOM evidence reference. Do not state that a
business is licensed, rated, available, or trustworthy unless the observation
is explicitly framed as a page pattern rather than a business fact.

## Grok: text and SEO analyst

Input: cleaned text, headings, forms, metadata, and structured-data excerpts
from the same validated public corpus.

Return JSON matching `schemas/model-analysis.schema.json` with
`worker=grok-text-seo`, `tenantMode=public-research`, and findings for:

- service taxonomy;
- heading and CTA patterns;
- copy-length and information hierarchy patterns;
- metadata and schema patterns;
- form fields and conversion friction.

Do not infer rankings, business facts, legal claims, or recommended customer
copy. Use null or omit unavailable observations.

## Critics

Gemini reviews only synthetic preview screenshots. Grok reviews only generated
synthetic copy against the synthetic fact pack. Their findings are advisory;
the local validator and deterministic evidence gates decide acceptance.
