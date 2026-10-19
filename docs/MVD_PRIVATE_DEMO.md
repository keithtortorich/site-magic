# Site Magic private MVD

The runnable demonstration is deliberately local and synthetic:

```sh
npm run demo:site-magic
```

It drives both `demo-hvac-a` and `demo-hvac-b` through:

`facts → editable proposal → explicit approval → local build request → private preview → bounded presentation revision → revised preview → checkpoint`

The harness proves tenant-scoped reads/build sources are denied across tenants
and duplicate preview callbacks replay idempotently. It never publishes, calls
a hosted provider, submits a lead, or uses customer data.

The `mvd` quality profile keeps accessibility at least 90, zero axe findings,
zero broken assets, zero console errors, provenance/content integrity, and
tenant isolation as blocking gates. Lighthouse performance, SEO, best practices,
and perfection-oriented review metrics are recorded but do not block this
private checkpoint. The strict `production` profile remains available.

Deferred until separately approved: DataForSEO/SearXNG research, the
12–15-site corpus, multi-model critics and handoffs, hosted storage and
credentials, publishing, and client-facing work.
