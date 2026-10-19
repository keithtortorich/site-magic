# VRE-safe Site Magic demonstration boundary

**Status:** active engineering constraint  
**Scope:** local/private demo only  
**Last reviewed:** 2026-10-18

This repository may be used to build and verify a private Site Magic
demonstration while the VRE restriction is active. It is not authorized for
sales, client work, production traffic, or customer data.

## Allowed

- Reading public web pages for bounded research, subject to robots.txt and
  applicable site terms.
- Using DataForSEO for geo-qualified public SERP research when credentials are
  separately available and approved.
- Using synthetic tenants `demo-hvac-a` and `demo-hvac-b`.
- Running local or private previews and saving screenshots outside the product
  repository.
- Using Gemini and Grok as bounded research/critique workers with structured
  outputs and evidence references.

## Prohibited

- Sales, outreach, calls, meetings, lead generation, quote requests, or form
  submissions to real businesses.
- Client accounts, client credentials, client contact data, or real tenant
  facts.
- Production migrations, production credential activation, public release, or
  customer traffic.
- Representing Apex Comfort Solutions or any researched business as a Site
  Magic customer.
- Treating model output as authoritative evidence, approval, checkpoint, or
  publication authority.

## Synthetic data rules

Synthetic facts must use the `demo-only` provenance marker. Contact values use
reserved `.invalid` domains and documentation-only phone numbers. Demo pages
must label illustrative content and must not contain real testimonials,
ratings, licenses, guarantees, service areas, or business contact details.

## Release boundary

The VRE-safe finish line ends at a verified private checkpoint. A release,
production deployment, real tenant onboarding, or customer interaction needs a
separate post-VRE approval and must not be inferred from passing local tests.

