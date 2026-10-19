# site-magic

This repository is the standalone Site Magic source-of-truth layer and the
canonical checkout for the private synthetic Minimum Viable Demonstration
(MVD). It is not a production website builder or a public publishing system.

The MVD proves one controlled loop:

```text
facts → editable plan → explicit approval → local build → private preview
→ bounded revision → checkpoint → tenant-isolation proof
```

The runtime is under `webstaffr/`, the worker is TypeScript, and the shared
rendering/control-plane dependencies are kept here. The original NetBuild.Pro
checkout is no longer the source of truth.

## Private MVD

Only the synthetic tenants `demo-hvac-a` and `demo-hvac-b` are in scope. The
demo ends at a local/private checkpoint: it does not publish, contact a real
business, submit leads, use customer data, or activate production credentials.

Run the acceptance harness with:

```text
npm run demo:site-magic
```

The harness proves both tenants complete the full loop, duplicate preview
callbacks are idempotent, cross-tenant reads/build sources are denied, and no
release is requested. See [docs/MVD_PRIVATE_DEMO.md](docs/MVD_PRIVATE_DEMO.md)
and [docs/PRIVATE_DEMO_RUNBOOK.md](docs/PRIVATE_DEMO_RUNBOOK.md).

## Deferred work

The following remain preserved but are explicitly deferred and must not block
the MVD: DataForSEO research, SearXNG discovery, the multi-metro corpus,
multi-model research/critique, hosted storage, production credentials,
publishing, and client-facing work. Their validators and adapters remain
fail-closed; passing them is not evidence of production readiness.

## Current site truth

The canonical HVAC reference direction is [Apex Comfort Solutions](SITE_TRUTH.md).
It defines the premium single-page structure, responsive behavior, design tokens,
CTA hierarchy, and evidence rules for generated HVAC sites. It is a direction
and composition contract, not a claim that Apex is a real customer or that the
illustrative reviews, ratings, certifications, phone number, or service facts
are verified.

When real tenant facts are supplied, they replace the marked demo content. The
direction may be reused across HVAC tenants, but tenant-specific colors and
verified proof always win where the two conflict.

## Verification

```text
python3 -m unittest discover -s tests
npm run check:site-magic
npm run demo:site-magic
```

The migrated runtime includes the existing Python and TypeScript tests, Site
Magic migrations, templates, worker, evidence runner, renderer, and control
plane. Credentials and local dependency caches are intentionally not copied.
