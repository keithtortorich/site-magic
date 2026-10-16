# ADR-031: Vendor-Independent CodexRuntime (replace OpenAI Codex SDK)

**Status:** Proposed, awaiting founder approval (D3, architecture).
**Date:** 2026-08-10.
**Supersedes nothing.** Builds on ADR-030 (demo sites via Site Magic) and the
2026-08-10 OpenRouter image-generator swap.

---

## Problem

`OpenAICodexRuntime` (`webstaffr/site_magic_adapters.ts:51`) is the only
remaining hard OpenAI dependency in Site Magic. It is blocked, not merely
unconfigured: per `CREDENTIALS.md` section 12, OpenAI Platform **rejected**
the `OPENAI_API_KEY` request outright, and GPT Image org access is
unapproved. This is not a config gate we can open from our side.

Consequence today: `/demos/{slug}` enqueues a Site Magic job that can never
build. Every demo sits on the "Building..." refresh page forever. The 10
demo sites promised on the landing page and in the Monday call script do not
exist as real Site Magic output.

The founder's instruction is to do what we did for image generation: swap
the vendor, avoid OpenAI entirely, prefer the `OPENROUTER_API_KEY` already
in Vercel Production.

## Why this is not the same swap

The image swap was one afternoon because `ImageGenerator` is a **pure
function**:

```
generate({model, brief, count}) -> string[]        // data: URIs, no side effects
```

Both `OpenAIImageGenerator` and `OpenRouterImageGenerator` are HTTP calls
that transform a prompt into bytes. Swapping them changed nothing the
engine could observe.

`CodexRuntime` is **not a pure function**. Its declared signature hides
that:

```
run({role, model, workspace, instructions}) -> Record<string, unknown>
```

The returned record is largely incidental. The load-bearing output is
**filesystem mutation inside `workspace`**. `OpenAICodexRuntime.run()` opens
an agentic thread (`sandboxMode: "workspace-write"`) and lets the model
read, write, and iterate over files across many turns until it decides it
is done.

OpenRouter has no equivalent. It is a chat-completions proxy. It has no
agent loop, no tool harness, no filesystem. "Point the adapter at
OpenRouter" is not an available move. Something has to supply the agentic
behavior that the Codex SDK is currently supplying.

### What each role actually does

Read from `site_maker_engine.ts` lines 245 to 332. Five of seven roles
mutate the workspace; two are read-only and only return JSON.

| Role | Mutates files | Output consumed by engine |
|---|---|---|
| `product` | yes (PRODUCT.md) | passed to `direction` |
| `direction` | yes (DESIGN.md, surface brief) | passed to images + `builder` |
| `builder` | yes (the entire site) | ignored |
| `design_assessor` | **no** | `{designScore, applicableMax, findings}`, validated by `mergeDesignAssessment()` |
| `remediator` | yes | ignored |
| `finish_reviewer` | **no** (instructions say "Do not modify files") | `{verdict, authoredNotInterchangeable, materialFindings}`, read by `releaseGatesPass()` |
| `documenter` | yes (DESIGN.md, .impeccable/design.json) | ignored |

The two read-only roles are already pure functions in everything but type.
They can move to plain OpenRouter chat-completions with no harness at all.

---

## Key insight: the engine is already the agent

The reason a full agentic inner loop may not be load-bearing here is that
`SiteMakerEngine.run()` already implements the outer loop, in code we own:

```
ingesting -> directing -> building
                            |
                            v
              +---> evaluating (deterministic evidence + LLM assessment)
              |         |
              |         +--> gates fail --> remediating (max 2) --+
              |                                                   |
              +---------------------------------------------------+
                        |
                        v
                  final_review
                        |
        +---------------+---------------+
        |               |               |
     REBUILD        REMEDIATE          PASS
    (max 1)         (max 2)             |
        |               |               v
        +-------+-------+         documenter -> seal -> ready_for_review
```

Evidence is real and deterministic (`PlaywrightEvidenceRunner`: Chromium at
3 widths, axe-core, Lighthouse, Impeccable detect). Gates are hard-coded
thresholds in `deterministicGatesPass()`. Iteration is bounded and
explicit.

So the model does not need to run its own exploratory loop to converge.
It needs to reason about a given workspace state and emit the next set of
file contents. The convergence loop already exists one level up.

---

## Options considered

### Option A: Structured codegen runtime (recommended)

Keep the `CodexRuntime` interface. Replace the agentic harness with a
runtime that does file I/O in our own Node code and asks any
chat-completions endpoint for a **structured JSON description of the
writes**.

```
OpenRouterCodegenRuntime.run()
  1. read relevant workspace files ourselves (Node fs, deterministic)
  2. POST to OpenRouter with response_format:
       {type: "json_schema", strict: true, json_schema: FILE_WRITE_SCHEMA}
  3. parse {files: [{path, contents}], result: {...}}
  4. validate every path against the workspace root, then write
  5. return `result` as the Record<string, unknown> the engine expects
```

OpenRouter supports `response_format: {type: "json_schema", strict: true}`
today, and structured outputs are documented as a constrained subset of
tool calling.

**Pros**
- Zero new vendors. Reuses `OPENROUTER_API_KEY`, already live in Vercel
  Production and verified working 2026-08-10.
- Security improvement. Today we trust the Codex SDK's `workspace-write`
  sandbox to contain writes. Under Option A **we** perform every write, so
  path traversal outside the job workspace becomes structurally impossible
  rather than vendor-enforced. That matters more than usual here: Site
  Magic ingests hostile third-party site content (see
  `hostileSourceEnvelope()`).
- Testable as a pure function of (workspace state, instructions) with an
  injected `fetch`, matching every other adapter in this file.
- Model-agnostic within OpenRouter. Swapping to a cheaper or newer model
  becomes an env var, not a code change.

**Cons and the honest risks**
- **Output token ceiling.** A complete multi-page responsive site in one
  structured response will exceed practical output limits. Mitigation
  below; this is the single biggest execution risk and the pilot must
  prove it.
- Loses in-role iteration. The model cannot run a command, look at the
  result, and adjust within one `run()` call. The outer loop compensates,
  but "compensates" is a hypothesis until the pilot runs.
- We own the prompt scaffolding that the Codex SDK currently owns for
  free.

**Mitigation for the output ceiling:** the `direction` role already
produces a "surface brief." Chunk `builder` per surface: one call per page
or component, each returning a bounded file set, accumulated into the
workspace. This is a loop we write, over data the engine already has. It
also keeps each call's context small enough to include the current
workspace state.

### Option B: Claude Agent SDK (documented fallback)

`@anthropic-ai/claude-agent-sdk` is the closest structural match to the
Codex SDK: same agent loop, built-in Read/Write/Edit/Bash/Glob/Grep,
workspace-scoped. `OpenAICodexRuntime` becomes `ClaudeAgentRuntime` with
substantially the same body.

**Pros:** near drop-in, preserves in-role agentic iteration, no output
ceiling problem, mature harness.

**Cons:** new vendor and a new key (`ANTHROPIC_API_KEY`), which is a D4
decision the founder owns. Trades OpenAI lock-in for Anthropic lock-in
rather than removing lock-in. Does not use the OpenRouter key the founder
specifically pointed at.

### Option C: Do nothing, wait on OpenAI

Rejected. Platform already rejected the key request. There is no dated
path to resolution and Monday's pitch references demos that cannot build.

### Recommendation

**Option A, with Option B held as a named fallback.** Both satisfy the same
`CodexRuntime` interface, so if Option A's output quality cannot clear
`deterministicGatesPass()` after the pilot, swapping to Option B is a
one-line change in `buildProductionDependencies()` and no engine change at
all. That is the whole point of keeping the interface fixed.

---

## Design

### New file: `webstaffr/site_magic_codegen_runtime.ts`

Kept out of `site_magic_adapters.ts`, which is already large and is a thin
wrapper file; this is a real subsystem with prompt construction, schema
validation, and path safety.

```typescript
export const FILE_WRITE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["files", "result"],
  properties: {
    files: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["path", "contents"],
        properties: {
          path:     { type: "string" },   // workspace-relative, validated
          contents: { type: "string" },
        },
      },
    },
    result: { type: "object" },           // role-specific JSON the engine reads
  },
} as const;

export class WorkspacePathEscapeError extends Error {}
export class MalformedCodegenResponseError extends Error {}

export class OpenRouterCodegenRuntime implements CodexRuntime {
  constructor(opts?: {
    apiKey?: string;
    model?: string;
    fetchImpl?: typeof fetch;
    fs?: WorkspaceFs;          // test seam, same posture as fetchImpl
  });
  run(args: {role; model; workspace; instructions}): Promise<Record<string, unknown>>;
}
```

Roles are declared read-only or mutating in one table in this file. A
read-only role that returns a non-empty `files` array is a **hard error**,
not a silent ignore. `finish_reviewer` is explicitly told not to modify
files; if the model tries, the run fails closed rather than letting an
unreviewed edit slip past the final gate.

### Path safety

Every `path` is resolved against the job workspace root and rejected unless
the resolved absolute path is still inside it. Rejects `..` traversal,
absolute paths, and symlink escapes. Throws `WorkspacePathEscapeError`,
which fails the job. No partial writes: validate the entire file set first,
then write.

### Workspace context

Each call includes the current workspace state so the model can reason
about what already exists. Bounded by a manifest-plus-contents strategy:
full contents for files under a size threshold, path-and-size only for the
rest, with the role's instructions naming which files matter. The
`hostileSourceEnvelope()` treatment of untrusted source data carries over
unchanged.

### Model constants

`DESIGN_MODEL = "gpt-5.6-sol"` in `site_maker_engine.ts:3` is an OpenAI
model string. It becomes an OpenRouter model slug, overridable by env var
(`SITE_MAGIC_DESIGN_MODEL`) the same way `DESIGN_CRITIQUE_MODEL` already
works for `design_critique/client.py`. Exact slug chosen during Phase 1
against live pricing, not guessed here.

### What does not change

- `SiteMakerEngine` -- not one line. That is the acceptance criterion.
- `CodexRuntime` interface, `NullCodexRuntime`,
  `CodexRuntimeNotConfiguredError`.
- Evidence runner, gates, state machine, artifact sealing, callbacks.
- `OpenRouterImageGenerator` (already swapped and verified).

---

## Phased plan

**Phase 1 -- Runtime, offline (D2, self-approvable)**
`site_magic_codegen_runtime.ts` plus tests against injected `fetch`/`fs`,
no network. Covers: schema validation, path-escape rejection, read-only
role violation, malformed response fail-closed, multi-file write ordering,
workspace context assembly. Also strip the two read-only roles onto a plain
chat-completions path. Node suite stays green. Nothing wired in.

**Phase 2 -- Live single-role probe (needs founder go, spends OpenRouter credit)**
Run `product` and `direction` against the real OpenRouter endpoint on one
demo fixture. Confirms the response shape assumption against reality,
exactly as the OpenRouter image call was verified 2026-08-10 before being
trusted. Cheap, two calls.

**Phase 3 -- Builder chunking (D2/D3 boundary)**
Per-surface chunking. This is where the output-ceiling risk is either
resolved or proven fatal. If fatal, escalate to Option B rather than
piling on complexity.

**Phase 4 -- Full pilot on one demo (needs founder go)**
End-to-end `_demo_hvac` build through the real engine: evidence runner,
gates, remediation loop, seal. Success is defined as
`deterministicGatesPass()` returning true on real output, not as "it
produced something."

**Phase 5 -- Wire and run the other nine (D4, deploy gate)**
`buildProductionDependencies()` constructs the new runtime.
`create_app()` gets a real `site_magic_queue` (currently defaults to
`NullSiteMagicQueue`, which is why demos hang today). Confirm migration
`0019_site_magic.sql` is applied to Supabase, still unverified. Run the
remaining nine demo builds. Each publishes once and is then served from
cache, so no permanently running worker is required.

---

## Open questions for the founder

1. **OpenRouter spend.** Phases 2 and 4 spend real credit. A full build is
   roughly 10 to 20 model calls plus remediation rounds. Ceiling before I
   stop and report?
2. **Option B trigger.** If Phase 3 or 4 shows quality cannot clear the
   gates, do I escalate to the Claude Agent SDK (new vendor, new key), or
   stop and report?
3. **Demo scope for Monday.** All ten demos, or HVAC first (the Monday
   call list is 100 percent HVAC) with the rest after?

## Consequences

**If accepted:** Site Magic has no OpenAI dependency at all. Demo sites
become real pipeline output, which is the claim the landing page and the
Monday script already make. Write-path security improves. Model choice
becomes an env var.

**If rejected:** demos stay unbuildable until OpenAI approves a key, with
no dated path. The landing page continues advertising ten demos that render
a permanent "Building..." page.

**Revisit when:** a paying tenant's site runs through this path. Demo
fixtures are small and uniform; a real crawled site is neither. The
output-ceiling and context-window strategy should be re-examined against
real intake data before the first customer build, not assumed to carry over
from demos.
