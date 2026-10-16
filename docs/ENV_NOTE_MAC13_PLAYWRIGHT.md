# Environment Note: Playwright Chromium is unavailable on macOS 13

**Date:** 2026-10-11
**Host:** macOS 13.7.8 (x64), system Python 3.9.6, Node v24.21.0

## Symptom

`node --test tests_node/site_magic_evidence_runner.test.ts` reports 7 failures, all identical:

```
browserType.launch: Executable doesn't exist at .../chromium_headless_shell-1234/...
```

Attempting to install the browser binary fails at the source:

```
npx playwright install chromium
→ ERROR: Playwright does not support chromium on mac13
```

## Cause

Playwright 1.62.1 does not ship a Chromium build for macOS 13. This is an
environmental limitation, **not a code regression**. The 7 affected tests are
the browser-based `PlaywrightEvidenceRunner` checks (clean-site pass,
lighthouse diagnostics, broken-site detection, tenant-path leakage,
entry-file resolution, static-asset resolution). The 5 non-browser tests in
the same file pass.

## Verified status on this host (2026-10-11)

- `python scripts/health_check.py` — 14/14 PASS (HEALTHY)
- `python -m pytest` — 824 passed
- Node builder suites — engine 46, adapters 21, codegen runtime 43, worker 17:
  all PASS
- `site_magic_evidence_runner.test.ts` — 5 pass / 7 fail (browser missing, per above)

## Local setup notes

- Repo targets Python 3.10+ but this host only has system Python 3.9.6.
  Deps were installed with relaxed pins + `eval_type_backport`
  (see `requirements-relaxed.txt`, untracked).
- `node_modules` must be present: run `npm ci` before Node tests.

## Path forward

Run the browser-based evidence tests on CI (Linux runners bundle Chromium
fine) or any host with a supported OS. Until then, treat those 7 failures on
macOS 13 as expected-and-diagnosed, not a regression to fix.
