# ADR-031 — Executive Summary

## The Problem

Demo sites promised on the landing page and in Monday's pitch hang forever on "Building..." because `OpenAICodexRuntime` requires `OPENAI_API_KEY`, which **OpenAI Platform rejected outright.** No path to resolution, no dated approval.

**Consequence:** The 10 demo sites (9 industries + agency) cannot build. Site Magic has a hard OpenAI dependency that is structurally blocked.

## The Solution

Replace OpenAI with OpenRouter using a **vendor-independent structured codegen runtime** that:

1. **Reuses existing credentials** — `OPENROUTER_API_KEY` already in Vercel Production (2026-08-10)
2. **Improves security** — We perform file writes, not a vendor sandbox
3. **Removes vendor lock-in** — Model choice becomes an env var, not code
4. **Keeps the engine unchanged** — `CodexRuntime` interface stays same

## Why This is Hard (and Why We're Ready)

### The Constraint
`OpenAICodexRuntime` is an agentic loop — the model reads, writes, iterates across turns. OpenRouter is just a chat API; it has no agent harness. **We must build the harness ourselves.**

### The Insight
The `SiteMakerEngine` *already is* the outer loop. It orchestrates evidence → gates → remediation → seal. The model doesn't need to explore; it needs to reason about workspace state and emit the next file set. Our loop handles convergence.

### The Trade-Off
OpenRouter has an output-token ceiling. A full multi-page site in one response will likely exceed it. **Mitigation:** chunk the builder role per surface (one API call per page/component). This is implementable because:
- The `direction` role already produces a "surface brief"
- `SiteMakerEngine` already has the surfaces available
- Each call stays context-bounded

## Phased Execution

| Phase | What | Cost | Approval Gate |
|-------|------|------|---|
| **1** | Build offline runtime + tests | None | Engineering Dir |
| **2** | Live probe (2 API calls on HVAC) | ~$0.05 | Founder (spend limit) |
| **3** | Builder chunking per surface | None | Engineering Dir |
| **4** | Full pilot `_demo_hvac` build | ~$2–5 | Founder (material spend) |
| **5** | Wire prod + run 9 demos | ~$15–20 | Founder (deploy) |

**Total estimated spend: $20–30** to build all 10 demos once (then cached, served).

## Fallback (Option B)

If Phase 3 or 4 shows output quality cannot clear the gates, escalate to **Claude Agent SDK** (`@anthropic-ai/claude-agent-sdk`):
- Same `CodexRuntime` interface (drop-in swap)
- Native agent loop + full tool harness
- No output ceiling
- Trade-off: new vendor (`ANTHROPIC_API_KEY`), new key request (D4)

The interface discipline means this is a one-line change in `buildProductionDependencies()` if needed.

## Founder Decisions

### For Phase 1 Approval:
1. **Architecture sound?** (path safety, schema validation, role contracts)
2. **Proceed to Phase 2?** (spend limit for live probe)

### For Phase 2–4:
1. **OpenRouter spend ceiling** before stopping and reporting?
2. **Option B trigger:** If quality gates fail, escalate to Claude Agent SDK or pause and report?

### Scope for Monday:
- **HVAC-only proof-of-concept** (your Monday call list is 100% HVAC)
- Or all 10 demos (more ambitious, same timeline if phases run parallel)

## Downstream Impact

**If accepted:**
- Landing page promise "10 ready-to-use demo sites" becomes real
- Monday script "Click a demo and see your site in 60 seconds" works
- No OpenAI dependency in Site Magic at all
- Model swaps are env-var changes, not code changes

**If rejected:**
- Demos stay on "Building..." forever
- Landing page and script refer to non-existent features
- Site Magic is blocked until OpenAI Platform approves a key (no dated path)

## Timeline

- **Phase 1 (now):** Build runtime offline (~4–6 hours)
- **Phase 2 (Monday?):** Live probe + decision (~1 hour)
- **Phase 3–5 (by Wed):** Chunking + full builds + wire + demo run-out (~8–12 hours)

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Output ceiling | Chunk per surface; fallback to Option B |
| Quality gates fail | Fallback to Option B (same interface) |
| OpenRouter downtime | Temporary; Phase 2 confirms API reliability |
| Token cost overrun | Phases 2 and 4 have approval gates; ceiling is founder's call |

## Detailed Plan

See `docs/ADR-031_PHASE_1_DETAILED_PLAN.md` for:
- Complete type and schema definitions
- Path safety validation strategy
- Workspace context bounding
- Unit test suite (50+ tests, offline)
- Role declarations and constraints
- Read-only role plain-chat path

---

**Status:** Awaiting founder approval to proceed with Phase 1.

**Next:** "Approved, proceed" → Engineering Director begins Phase 1 implementation (~4–6 hours, complete offline).
