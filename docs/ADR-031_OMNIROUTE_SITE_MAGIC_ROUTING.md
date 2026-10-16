# ADR-031: OmniRoute as a routing layer for Site Magic image generation

**Status:** Decided (local-dev approved, production deferred — D4 to adopt in prod)
**Date:** 2026-08-10
**Author:** Hermes (nbp-director)

## Context

OmniRoute (`diegosouzapw/OmniRoute`, release/v3.8.50) is a local-first AI gateway that
proxies 291 providers through one OpenAI-compatible endpoint (`http://localhost:20128/v1`)
with 4-tier auto-fallback (Subscription → API Key → Cheap → Free) and token compression
(RTK + Caveman, 15–95%). Zero-config: `model: "auto"` works out of the box via pre-wired
free providers (OpenCode Free, Felo).

Site Magic currently calls OpenRouter directly via `OpenRouterImageGenerator`
(`webstaffr/site_magic_adapters.ts`), wired in `buildProductionDependencies()` at
`webstaffr/site_magic_worker.ts:71`, backed by `OPENROUTER_API_KEY`. The free OpenRouter
key has limited credits (~9800) and 402s on large-token requests.

## Decision

**Local dev:** Point `OpenRouterImageGenerator`'s `base_url` at `http://localhost:20128/v1`
with `model: "auto"` on local/dev only. OmniRoute holds `OPENROUTER_API_KEY` (reads from its
own `.env`), routes to `gemini-2.5-flash-image`, and adds free-tier fallback + compression.
This is reversible and costs nothing.

**Production:** Keep calling OpenRouter **directly** (current `92ee022` wiring). Do NOT adopt
OmniRoute in production yet.

## Rationale

OmniRoute is a persistent **localhost daemon**. NetBuild.Pro runs on Vercel (stateless
serverless) — a Vercel function cannot spawn a localhost OmniRoute per request. To use
OmniRoute in prod we must stand up a persistent host (e.g. the broker box at
`/Users/doc/Desktop/.netbuild-agent-broker`, or a tiny always-on VM) and point Vercel's
image-gen at that host's internal URL. That is a new dependency + architecture change.

Prod adoption is gated (D4) until the first paying client justifies a persistent host. The
direct-OpenRouter path already degrades gracefully (bounded retry + `imagesMissing: true`),
so it is acceptable to keep for launch.

## Consequences

- Local image-gen builds get free-tier fallback + compression immediately (lowers cost while
  iterating on Site Magic).
- No production change required for Monday launch.
- If we later adopt in prod: new infra dependency, internal network egress from Vercel to the
  host, and a D4 approval + ADR update.

## Next step (when justified)

Write ADR update + provision persistent OmniRoute host, then flip `base_url` for prod via an
env var (`SITE_MAGIC_IMAGE_BASE_URL`), keeping `localhost:20128/v1` as the dev default.
