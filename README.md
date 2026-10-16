# site-magic

This repository is the standalone Site Magic corpus and source-of-truth layer.

The Site Magic implementation now lives here as well. The runtime is under
`webstaffr/`, the worker is TypeScript, and the shared rendering/control-plane
dependencies are kept with it so this repository is the canonical development
checkout. The original NetBuild.Pro checkout is no longer the source of truth.

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
```

The migrated runtime includes the existing Python and TypeScript tests, Site
Magic migrations, templates, worker, evidence runner, renderer, and control
plane. Credentials and local dependency caches are intentionally not copied.
