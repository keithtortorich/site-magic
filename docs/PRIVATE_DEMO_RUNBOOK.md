# Private synthetic demo runbook

This runbook ends at a private checkpoint. It does not publish, contact a
business, submit a form, or use real tenant data.

## Local setup

```text
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
npm ci
npx playwright install chromium
```

## Artifact validation

```text
.venv/bin/python scripts/validate_demo_artifacts.py \
  --facts demo/facts/demo-hvac-a.json \
  --facts demo/facts/demo-hvac-b.json \
  --site-spec demo/site-specs/demo-hvac-a.json \
  --site-spec demo/site-specs/demo-hvac-b.json
```

Public research is a separate gated step. It requires DataForSEO credentials
and exact location codes; without them, do not create a corpus substitute.

For open-source discovery only, a private SearXNG instance may be queried:

```text
python3 scripts/discover_searxng.py \
  --base-url http://127.0.0.1:8080 \
  --query "HVAC contractor Phoenix" \
  --output private-research/searxng-discovery.json
```

That output is not authoritative SERP evidence and cannot replace the
DataForSEO-backed corpus. After collecting raw DataForSEO candidates, apply a
human-reviewed manifest before validation:

```text
python3 scripts/select_corpus.py \
  --raw private-research/dataforseo-raw.json \
  --manifest private-research/corpus-selection.json \
  --output private-research/corpus.json
python3 scripts/validate_corpus.py --corpus private-research/corpus.json
```

## Synthetic control-plane flow

Run the executable harness from the repository root:

```text
npm run demo:site-magic
```

It uses two isolated synthetic tenants and exercises facts → editable plan →
approval → local build → private preview → bounded presentation revision →
revised preview → checkpoint. It also asserts duplicate callback replay and
cross-tenant denial. The publisher must remain a null or private sink. Do not
call the release endpoint for this VRE demo.

## Acceptance evidence

Retain local test output, private screenshots, deterministic quality reports,
claim traces, tenant-isolation results, and the final checkpoint identifier.
Label all pages and screenshots as illustrative synthetic demos.

The research commands above are deferred support tooling. They are not part of
the MVD acceptance path and must not be run as a substitute for authoritative
geo-qualified evidence.

