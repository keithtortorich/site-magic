import test from "node:test";
import assert from "node:assert/strict";
import {
  OpenRouterCodegenRuntime,
  callReadOnlyRole,
  stripJsonFence,
  WorkspacePathEscapeError,
  ReadOnlyRoleFileModificationError,
  MalformedCodegenResponseError,
  CodexRuntimeNotConfiguredError,
} from "../webstaffr/site_magic_codegen_runtime.ts";

// ============================================================================
// Mock Setup
// ============================================================================

function createFakeFs(overrides?: any): any {
  const files = new Map<string, string>();
  const links = new Map<string, string>();

  const defaultFs: WorkspaceFs = {
    exists: async (p: string) => {
      if (files.has(p) || links.has(p)) return true;
      // "/tmp" is every test's workspace root -- mkdtemp guarantees it
      // exists in production before any write, same as a real directory.
      if (p === "/tmp") return true;
      return Array.from(files.keys()).some((key) => key.startsWith(p + "/"));
    },
    readFile: async (p: string) => {
      if (files.has(p)) return files.get(p)!;
      throw new Error(`ENOENT: ${p}`);
    },
    writeFile: async (p: string, contents: string) => {
      files.set(p, contents);
    },
    isSymlink: async (p: string) => links.has(p),
    realpath: async (p: string) => {
      if (links.has(p)) {
        return links.get(p)!;
      }
      // Real fs.realpath throws ENOENT for a target that doesn't exist --
      // the earlier version of this mock always succeeded, which is
      // exactly what let PathValidator's realpath-on-a-not-yet-written-file
      // bug ship to production undetected by any test.
      if (p === "/tmp" || files.has(p) || Array.from(files.keys()).some((k) => k.startsWith(p + "/"))) {
        return p;
      }
      throw Object.assign(new Error(`ENOENT: no such file or directory, realpath '${p}'`), { code: "ENOENT" });
    },
    stat: async (p: string) => {
      const content = files.get(p);
      if (content !== undefined) {
        return {
          isDirectory: () => false,
          size: content.length,
        };
      }
      const isDirContent = Array.from(files.keys()).some((key) =>
        key.startsWith(p + "/")
      );
      if (isDirContent) {
        return {
          isDirectory: () => true,
          size: 0,
        };
      }
      throw new Error(`ENOENT: ${p}`);
    },
    readdir: async (p: string) => {
      const prefix = p.endsWith("/") ? p : p + "/";
      const entries = new Set<string>();
      for (const key of files.keys()) {
        if (key.startsWith(prefix)) {
          const rel = key.slice(prefix.length);
          const parts = rel.split("/");
          if (parts.length > 0) {
            entries.add(parts[0]);
          }
        }
      }
      return Array.from(entries);
    },
  };

  return { ...defaultFs, ...overrides };
}

// ============================================================================
// Constructor Tests
// ============================================================================

test("constructor: throws if OPENROUTER_API_KEY not set", () => {
  const oldEnv = process.env.OPENROUTER_API_KEY;
  delete process.env.OPENROUTER_API_KEY;

  try {
    assert.throws(
      () => new OpenRouterCodegenRuntime({ fetchImpl: async () => ({}) as any }),
      CodexRuntimeNotConfiguredError
    );
  } finally {
    process.env.OPENROUTER_API_KEY = oldEnv;
  }
});

test("constructor: accepts apiKey via constructor option", () => {
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: async () => ({}) as any,
  });
  assert.ok(runtime instanceof OpenRouterCodegenRuntime);
});

test("constructor: uses SITE_MAGIC_DESIGN_MODEL env var if set", async () => {
  const oldEnv = process.env.SITE_MAGIC_DESIGN_MODEL;
  process.env.SITE_MAGIC_DESIGN_MODEL = "test-model";

  try {
    let capturedModel = "";
    const mockFetch = async (url: string, opts: any) => {
      const body = JSON.parse(opts.body);
      capturedModel = body.model;
      return {
        ok: true,
        json: async () => ({
          choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
        }),
      };
    };

    const runtime = new OpenRouterCodegenRuntime({
      apiKey: "test-key",
      fetchImpl: mockFetch,
      fs: createFakeFs(),
    });

    await runtime.run({
      role: "product",
      workspace: "/tmp",
      instructions: "test",
    });

    assert.equal(capturedModel, "test-model");
  } finally {
    process.env.SITE_MAGIC_DESIGN_MODEL = oldEnv;
  }
});

test("callOpenRouter: sets an explicit generous max_tokens", async () => {
  // Regression: a real production "direction" role response on a
  // reasoning-capable free-tier model got cut off mid-string
  // (SyntaxError: Unterminated string in JSON). Reasoning-capable models
  // spend a large, non-optional share of the completion budget on hidden
  // chain-of-thought before the requested JSON, and without max_tokens
  // set, OpenRouter applies its own small/unpredictable default.
  let capturedMaxTokens: number | undefined;
  const mockFetch = async (url: string, opts: any) => {
    capturedMaxTokens = JSON.parse(opts.body).max_tokens;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
      }),
    };
  };

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await runtime.run({ role: "product", workspace: "/tmp", instructions: "test" });

  assert.ok(typeof capturedMaxTokens === "number" && capturedMaxTokens >= 8000);
});

test("callOpenRouter: enforces schema-constrained JSON output at the provider", async () => {
  // Regression: `json_object` mode only nudges the model to emit valid JSON
  // and still produced a structural `Expected ',' or '}'` error mid-payload
  // in production. Schema-constrained mode constrains the decoder to
  // FILE_WRITE_SCHEMA at the source, which is what ends the JSON-repair
  // tail-chase. strict:false keeps the role-specific `result` object
  // flexible while hard-constraining the `files` array.
  let capturedResponseFormat: any;
  const mockFetch = async (_url: string, opts: any) => {
    capturedResponseFormat = JSON.parse(opts.body).response_format;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
      }),
    };
  };

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await runtime.run({ role: "product", workspace: "/tmp", instructions: "test" });

  assert.equal(capturedResponseFormat?.type, "json_schema");
  assert.equal(capturedResponseFormat?.json_schema?.strict, false);
  assert.equal(capturedResponseFormat?.json_schema?.name, "site_magic_product");
  assert.ok(capturedResponseFormat?.json_schema?.schema?.properties?.files);
  assert.ok(capturedResponseFormat?.json_schema?.schema?.properties?.result);
});

test("stripJsonFence: returns valid JSON verbatim (non-destructive)", () => {
  // Regression: an earlier version ran sanitizeJsonControlChars on every
  // input, which *unescapes* the model's own valid escapes (\\n -> n) and
  // can corrupt already-valid JSON. stripJsonFence must now return valid
  // JSON unchanged so the parser never "repairs" something that wasn't
  // broken -- which previously sent it down a tier that invented the very
  // malformation it was trying to fix.
  const valid = JSON.stringify({ files: [{ path: "a.html", contents: "line1\nline2" }], result: { score: 1 } });
  assert.equal(stripJsonFence(valid), valid);
});

test("stripJsonFence: still extracts a fenced payload when present", () => {
  const fenced = "```json\n" + JSON.stringify({ files: [], result: {} }) + "\n```";
  const parsed = JSON.parse(stripJsonFence(fenced));
  assert.deepEqual(parsed, { files: [], result: {} });
});

test("callOpenRouter: sends responsive screenshots as multimodal image inputs", async () => {
  let capturedContent: any;
  const mockFetch = async (_url: string, opts: any) => {
    capturedContent = JSON.parse(opts.body).messages[0].content;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
      }),
    };
  };
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key", fetchImpl: mockFetch, fs: createFakeFs(),
  });

  await runtime.run({
    role: "design_assessor", workspace: "/tmp", instructions: "judge screenshots",
    imageDataUrls: ["data:image/jpeg;base64,MOBILE", "data:image/jpeg;base64,DESKTOP"],
  });

  assert.equal(capturedContent[0].type, "text");
  assert.deepEqual(capturedContent.slice(1), [
    { type: "image_url", image_url: { url: "data:image/jpeg;base64,MOBILE" } },
    { type: "image_url", image_url: { url: "data:image/jpeg;base64,DESKTOP" } },
  ]);
});

test("constructor: accepts injected fetch and fs", () => {
  const mockFetch = async () => ({});
  const mockFs = createFakeFs();

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: mockFs,
  });

  assert.ok(runtime instanceof OpenRouterCodegenRuntime);
});

// ============================================================================
// Path Validation Tests
// ============================================================================

test("path validation: accepts valid relative paths", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "index.html", contents: "ok" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.equal(await fs.readFile("/tmp/index.html"), "ok");
});

test("path validation: accepts a brand-new file in a not-yet-existing subdirectory", async () => {
  // Regression: the first real production codegen call wrote PRODUCT.md
  // into a freshly mkdtemp'd, otherwise-empty workspace. validatePath
  // called fs.realpath on that not-yet-written file directly, and
  // realpath requires its target to exist -- every write of a genuinely
  // new file threw ENOENT. Every local test passed because the old fake
  // fs's realpath never threw for a nonexistent path.
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "docs/PRODUCT.md", contents: "# Product" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.equal(await fs.readFile("/tmp/docs/PRODUCT.md"), "# Product");
});

test("path validation: rejects absolute paths", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "/etc/passwd", contents: "bad" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    WorkspacePathEscapeError
  );
});

test("path validation: rejects paths with ..", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "../../etc/passwd", contents: "bad" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    WorkspacePathEscapeError
  );
});

test("path validation: rejects reserved names", async () => {
  const reserved = [".env", ".git", ".gitignore", ".impeccable"];

  for (const name of reserved) {
    const mockFetch = async () => ({
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({
                files: [{ path: name, contents: "bad" }],
                result: {},
              }),
            },
          },
        ],
      }),
    });

    const runtime = new OpenRouterCodegenRuntime({
      apiKey: "test-key",
      fetchImpl: mockFetch,
      fs: createFakeFs(),
    });

    await assert.rejects(
      () =>
        runtime.run({
          role: "builder",
          workspace: "/tmp",
          instructions: "test",
        }),
      WorkspacePathEscapeError
    );
  }
});

test("path validation: rejects paths with control characters", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "file\x00null.html", contents: "bad" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    WorkspacePathEscapeError
  );
});

// ============================================================================
// Response Validation Tests
// ============================================================================

test("response validation: accepts valid CodegenResponse", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "index.html", contents: "hello" }],
              result: { custom: "data" },
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, { custom: "data" });
});

test("response validation: strips a markdown code fence OpenRouter wraps JSON in", async () => {
  // Regression: the first real production codegen call returned
  // "```json\n{...}\n```" instead of raw JSON, and JSON.parse threw on the
  // fence -- MalformedCodegenResponseError with no code path that ever
  // handled it.
  const fenced = "```json\n" + JSON.stringify({
    files: [{ path: "index.html", contents: "hello" }],
    result: { custom: "data" },
  }) + "\n```";
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: fenced } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, { custom: "data" });
});

test("response validation: recovers a JSON object from a fence that never closes", async () => {
  // Regression: a real production remediation response (a large multi-file
  // builder payload, more likely to brush a completion token limit) came
  // back as "```json\n{...}" with no closing fence. The first stripJsonFence
  // required the entire response to BE one closed fence, so this fell
  // through unstripped and JSON.parse threw on the leading backticks.
  const unclosed = "```json\n" + JSON.stringify({
    files: [{ path: "index.html", contents: "hello" }],
    result: { custom: "data" },
  });
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: unclosed } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, { custom: "data" });
});

test("response validation: recovers from a raw unescaped newline inside a string value", async () => {
  // Regression: a real production "direction" response died with
  // "SyntaxError: Unterminated string in JSON" at a position far short of
  // the 16000-token completion budget -- not a truncation, a genuinely
  // malformed string. RFC 8259 requires a literal newline inside a JSON
  // string to be escaped (\n), and models routinely emit a real line
  // break instead when a string value carries multi-line content.
  const rawContent = `{"files":[{"path":"index.html","contents":"line one\nline two"}],"result":{}}`;
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: rawContent } }],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, {});
  assert.equal(await fs.readFile("/tmp/index.html"), "line one\nline two");
});

test("response validation: error snippet windows around the actual parse-error position, not just a prefix", async () => {
  // Regression: a real production failure had its malformation at
  // JSON.parse position 894, but the snippet was a flat 0-300 prefix --
  // useless, the actual bad content was never visible in the log. The
  // snippet must center on wherever V8 reports the error, however deep.
  // Uses an unrecoverable shape (an unquoted value token, not embedded
  // quotes): the embedded-quote repair tier now resolves "... \"ok\" \"trailing\""
  // to a valid string, so a quote-based input no longer reaches this error
  // path. This keeps the snippet-windowing guard alive against a malformation
  // none of the repair tiers can fix.
  const padding = "x".repeat(850);
  const malformed = `{"files":[],"result":{"padding":"${padding}","bad": ok "trailing"}}`;
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: malformed } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  try {
    await runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" });
    assert.fail("expected MalformedCodegenResponseError");
  } catch (e) {
    assert.ok(e instanceof MalformedCodegenResponseError);
    assert.ok((e as Error).message.includes("trailing"), `expected the actual malformed region in: ${(e as Error).message}`);
  }
});

test("response validation: recovers a response truncated exactly at its own closing brace", async () => {
  // Regression: a real production finish_reviewer response ended
  // "...engines.\"}]}" -- the findings array and the "result" object
  // both close correctly, but the outer {"files":[],"result":{...}}
  // wrapper's own closing brace never arrived. max_tokens ran out one
  // token short. closeUnbalancedJson should append exactly the missing
  // closer and let this parse successfully instead of failing the job.
  const truncated = `{"files":[],"result":{"designScore":30,"applicableMax":40,"findings":[{"id":"f1","priority":"P1","summary":"ok"}]}`; // missing final }
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: truncated } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({ role: "design_assessor", workspace: "/tmp", instructions: "test" });
  assert.deepEqual(result, { designScore: 30, applicableMax: 40, findings: [{ id: "f1", priority: "P1", summary: "ok" }] });
});

test("response validation: recovers a response truncated mid-string inside result", async () => {
  // Regression: a real production remediation-round `builder` response cut
  // off 15545 of 15545 chars into an unfinished CSS rule inside a file's
  // "contents" value -- "Unterminated string in JSON at position 15545".
  // closeUnbalancedJson correctly ignored the CSS's own literal { and }
  // while walking inString, but never closed the dangling string itself
  // before appending the outer closers -- appending "}]}" right after raw,
  // unquoted content is still invalid JSON, so the "repair" silently did
  // nothing useful and the job failed anyway. This pins that an open
  // string gets a closing quote before the outer closers. (Truncation
  // strictly inside "files" before "result" is ever reached is a
  // different, token-budget problem this JSON-level repair cannot fix --
  // this test targets the case the repair is actually meant to cover:
  // truncation mid-string in a field that's otherwise complete enough to
  // recover. (Deliberately keeps "files" empty: a closed file object
  // ahead of the truncated string would give stripJsonFence's own naive
  // "slice to the last }" fallback an earlier, wrong brace to latch onto
  // -- a separate, narrower limitation in that function, not exercised or
  // fixed here.)
  const truncated =
    `{"files":[],` +
    `"result":{"status":"complete","note":"Updated the CTA hover state to #2A5C8E`; // cut mid-string
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: truncated } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" });
  assert.deepEqual(result, {
    status: "complete",
    note: "Updated the CTA hover state to #2A5C8E",
  });
});

test("response validation: closes a string truncated on a trailing escape character", async () => {
  // Edge case the fix has to get right: if the very last character
  // consumed before truncation was itself an unescaped backslash (mid
  // escape sequence), appending a bare closing quote produces `\"`, which
  // JSON reads as an escaped quote INSIDE the string, not a terminator --
  // the string stays open and parsing still fails. The repair must
  // neutralize the dangling escape with a matching backslash first.
  const truncated = `{"files":[],"result":{"note":"line one\\`; // ends on a lone backslash
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: truncated } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" });
  assert.deepEqual(result, { note: "line one\\" });
});

test("response validation: uses the final envelope after a planning placeholder", async () => {
  // Regression: Terra emitted a valid placeholder CodegenResponse, then the
  // real 24 KB response. JSON.parse rejected the concatenation at the first
  // character after the placeholder and production failed on remediation 3.
  const placeholder = JSON.stringify({
    files: [{ path: "index.html", contents: "" }],
    result: { status: "placeholder" },
  });
  const final = JSON.stringify({
    files: [{ path: "index.html", contents: "<main>Finished</main>" }],
    result: { status: "complete" },
  });
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: async () => ({
      ok: true,
      json: async () => ({ choices: [{ message: { content: `${placeholder}\n${final}` } }] }),
    }) as any,
    fs: createFakeFs(),
  });

  const result = await runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" });

  assert.deepEqual(result, { status: "complete" });
});

test("response validation: rejects response missing 'files' key", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              result: { custom: "data" },
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    MalformedCodegenResponseError
  );
});

test("response validation: rejects response missing 'result' key", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [],
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    MalformedCodegenResponseError
  );
});

// ============================================================================
// Role Constraint Tests
// ============================================================================

test("role constraints: mutating role can write files", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "index.html", contents: "ok" }],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.ok(true);
});

test("role constraints: read-only role throws if attempts to write", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [{ path: "bad.html", contents: "should fail" }],
              result: { verdict: "PASS" },
            }),
          },
        },
      ],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "finish_reviewer",
        workspace: "/tmp",
        instructions: "review",
      }),
    ReadOnlyRoleFileModificationError
  );
});

test("role constraints: unknown role throws", async () => {
  const mockFetch = async () => ({});
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "nonexistent",
        workspace: "/tmp",
        instructions: "test",
      }),
    /Unknown role/
  );
});

// ============================================================================
// File Write Tests
// ============================================================================

test("file writes: writes all validated files", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [
                { path: "a.html", contents: "a" },
                { path: "b.css", contents: "b" },
              ],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.equal(await fs.readFile("/tmp/a.html"), "a");
  assert.equal(await fs.readFile("/tmp/b.css"), "b");
});

test("file writes: validates all paths before writing any (no partial writes)", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              files: [
                { path: "valid.html", contents: "ok" },
                { path: "../bad.js", contents: "nope" },
              ],
              result: {},
            }),
          },
        },
      ],
    }),
  });

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await assert.rejects(
    () =>
      runtime.run({
        role: "builder",
        workspace: "/tmp",
        instructions: "test",
      }),
    WorkspacePathEscapeError
  );

  await assert.rejects(() => fs.readFile("/tmp/valid.html"), /ENOENT/);
});

// ============================================================================
// Workspace Context Tests
// ============================================================================

test("workspace context: includes small files with full contents", async () => {
  let capturedPrompt = "";

  const mockFetch = async (url: string, opts: any) => {
    capturedPrompt = JSON.parse(opts.body).messages[0].content;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
      }),
    };
  };

  const fs = createFakeFs({
    ...createFakeFs(),
    readFile: async (p: string) => {
      if (p === "/tmp/small.html") return "small file";
      if (p === "/tmp/index.js") return "js code";
      throw new Error(`ENOENT: ${p}`);
    },
    stat: async (p: string) => {
      if (p === "/tmp/small.html" || p === "/tmp/index.js") {
        return { isDirectory: () => false, size: 100 };
      }
      throw new Error(`ENOENT: ${p}`);
    },
    readdir: async (p: string) => (p === "/tmp" ? ["small.html", "index.js"] : []),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  await runtime.run({
    role: "product",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.ok(capturedPrompt.includes("small.html"));
  assert.ok(capturedPrompt.includes("small file"));
  assert.ok(capturedPrompt.includes("index.js"));
  assert.ok(capturedPrompt.includes("js code"));
});

// ============================================================================
// Read-Only Role Tests
// ============================================================================

test("callReadOnlyRole: sets an explicit generous max_tokens", async () => {
  let capturedMaxTokens: number | undefined;
  const mockFetch = async (url: string, opts: any) => {
    capturedMaxTokens = JSON.parse(opts.body).max_tokens;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ designScore: 1, applicableMax: 1, findings: [] }) } }],
      }),
    };
  };

  await callReadOnlyRole({
    role: "design_assessor",
    instructions: "assess this design",
    fetch: mockFetch,
    apiKey: "test-key",
  });

  assert.ok(typeof capturedMaxTokens === "number" && capturedMaxTokens >= 8000);
});

test("readOnlyRole: design_assessor returns expected structure", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              designScore: 85,
              applicableMax: 100,
              findings: [
                { id: "f1", priority: "P1", summary: "Missing alt text" },
                { id: "f2", priority: "P2", summary: "Low contrast" },
              ],
            }),
          },
        },
      ],
    }),
  });

  const result = await callReadOnlyRole({
    role: "design_assessor",
    instructions: "assess this design",
    fetch: mockFetch,
    apiKey: "test-key",
  });

  assert.deepEqual(result, {
    designScore: 85,
    applicableMax: 100,
    findings: [
      { id: "f1", priority: "P1", summary: "Missing alt text" },
      { id: "f2", priority: "P2", summary: "Low contrast" },
    ],
  });
});

test("readOnlyRole: strips a markdown code fence OpenRouter wraps JSON in", async () => {
  const fenced = "```json\n" + JSON.stringify({
    designScore: 85,
    applicableMax: 100,
    findings: [{ id: "f1", priority: "P1", summary: "Missing alt text" }],
  }) + "\n```";
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: fenced } }],
    }),
  });

  const result = await callReadOnlyRole({
    role: "design_assessor",
    instructions: "assess this design",
    fetch: mockFetch,
    apiKey: "test-key",
  });

  assert.deepEqual(result, {
    designScore: 85,
    applicableMax: 100,
    findings: [{ id: "f1", priority: "P1", summary: "Missing alt text" }],
  });
});

test("readOnlyRole: finish_reviewer returns expected structure", async () => {
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [
        {
          message: {
            content: JSON.stringify({
              verdict: "PASS",
              authoredNotInterchangeable: true,
              materialFindings: [],
            }),
          },
        },
      ],
    }),
  });

  const result = await callReadOnlyRole({
    role: "finish_reviewer",
    instructions: "review this",
    fetch: mockFetch,
    apiKey: "test-key",
  });

  assert.deepEqual(result, {
    verdict: "PASS",
    authoredNotInterchangeable: true,
    materialFindings: [],
  });
});

test("readOnlyRole: throws if no OPENROUTER_API_KEY", async () => {
  const oldEnv = process.env.OPENROUTER_API_KEY;
  delete process.env.OPENROUTER_API_KEY;

  try {
    await assert.rejects(
      () =>
        callReadOnlyRole({
          role: "design_assessor",
          instructions: "test",
          fetch: async () => ({}) as any,
        }),
      CodexRuntimeNotConfiguredError
    );
  } finally {
    process.env.OPENROUTER_API_KEY = oldEnv;
  }
});

test("response validation: repairs literal unescaped quotes embedded inside a string value (directing/design_assessor shape)", async () => {
  // Regression: a real production `directing` response died with
  // `Expected ',' or '}' after property value in JSON at position 2196`,
  // because a free-text string field carried embedded, unescaped double
  // quotes (`..."reflecting the "fast, reliable" aspect..."`). This is the
  // third distinct malformation after raw-control-char and truncation -- it
  // is interior quotes, not missing outer closers, so neither prior repair
  // caught it. The third tier escapes only quotes whose following
  // significant char is NOT a structural delimiter, leaving already-valid
  // JSON untouched.
  const malformed =
    '{"files":[],"result":{"direction":"Build a site reflecting the "fast, reliable" aspect of their service, with "24/7 support" highlighted."}}';
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: malformed } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({
    role: "direction",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, {
    direction:
      'Build a site reflecting the "fast, reliable" aspect of their service, with "24/7 support" highlighted.',
  });
});


test("readOnlyRole: repairs embedded unescaped quotes inside a free-text findings string (design_assessor/finish_reviewer shape)", async () => {
  // Same malformation, on the read-only path that powers design_assessor /
  // finish_reviewer -- a findings summary quoting UI copy like "Our Services"
  // without escaping the inner quotes. The third repair tier must recover it
  // instead of throwing MalformedCodegenResponseError.
  const malformed =
    '{"designScore":36,"applicableMax":40,"findings":[{"id":"f1","priority":"P1","summary":"The hero CTA should mirror the "Book Now" button used on the services page."}]}';
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: malformed } }],
    }),
  });

  const result = await callReadOnlyRole({
    role: "design_assessor",
    instructions: "assess this design",
    fetch: mockFetch,
    apiKey: "test-key",
  });

  assert.deepEqual(result, {
    designScore: 36,
    applicableMax: 40,
    findings: [{ id: "f1", priority: "P1", summary: 'The hero CTA should mirror the "Book Now" button used on the services page.' }],
  });
});

test("response validation: does not double-escape already-valid JSON containing internal quotes", async () => {
  // No-false-positive guard: a correctly-escaped string with internal quotes
  // must pass through unchanged. The repair must leave the genuine closing
  // quote (followed by a structural delimiter) untouched, so the parsed value
  // keeps exactly the intended prose.
  const valid = JSON.stringify({
    files: [],
    result: {
      note: 'keep the "fast, reliable" promise and the "24/7 support" badge',
    },
  });
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({
      choices: [{ message: { content: valid } }],
    }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "test",
  });

  assert.deepEqual(result, {
    note: 'keep the "fast, reliable" promise and the "24/7 support" badge',
  });
});

// ============================================================================
// Per-file builder split (truncation-safe codegen)
// ============================================================================

test("builder: splitFiles makes one call per file and writes all of them", async () => {
  // Regression: a real production ~57 KB builder response truncated at
  // 57,648 chars dropped the required `result` field and failed the job.
  // Splitting into one small call per file keeps each response under the
  // completion budget so `result` survives.
  const emitted: string[] = [];
  const mockFetch = async (_url: string, opts: any) => {
    const body = JSON.parse(opts.body);
    const content = body.messages[0].content as string;
    const file = ["index.html", "styles.css", "main.js"].find((f) =>
      content.includes(`emit ONLY the file "${f}"`)
    );
    assert.ok(file, `expected a per-file instruction, got: ${content.slice(-120)}`);
    emitted.push(file!);
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({
                files: [{ path: file, contents: `<${file}>ok</${file}>` }],
                result: { status: "ok", file },
              }),
            },
          },
        ],
      }),
    };
  };

  const fs = createFakeFs();
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "***",
    fetchImpl: mockFetch,
    fs,
  });

  const result = await runtime.run({
    role: "builder",
    workspace: "/tmp",
    instructions: "build the site",
    splitFiles: true,
  });

  // Three distinct per-file calls, in order.
  assert.deepEqual(emitted, ["index.html", "styles.css", "main.js"]);
  // All three files actually written.
  assert.equal(await fs.readFile("/tmp/index.html"), "<index.html>ok</index.html>");
  assert.equal(await fs.readFile("/tmp/styles.css"), "<styles.css>ok</styles.css>");
  assert.equal(await fs.readFile("/tmp/main.js"), "<main.js>ok</main.js>");
  // Last call's result returned.
  assert.deepEqual(result, { status: "ok", file: "main.js" });
});

test("builder: splitFiles does NOT apply to read-only roles", async () => {
  let callCount = 0;
  const mockFetch = async () => {
    callCount += 1;
    return {
      ok: true,
      json: async () => ({
        choices: [
          {
            message: {
              content: JSON.stringify({ files: [], result: { verdict: "PASS" } }),
            },
          },
        ],
      }),
    };
  };

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "***",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  const result = await runtime.run({
    role: "finish_reviewer",
    workspace: "/tmp",
    instructions: "review",
    splitFiles: true,
  });

  assert.equal(callCount, 1);
  assert.deepEqual(result, { verdict: "PASS" });
});

// ============================================================================
// Misleading error when `result` is missing after truncation
// ============================================================================

test("response validation: truncated response missing 'result' reports the real cause, not the original parse error", async () => {
  // Regression: closeUnbalancedJson structurally closes a truncated
  // response, but validateCodegenResponse then rejects it with
  // "Response.result must be an object" because the truncation dropped the
  // `result` field entirely. The thrown error must surface THAT cause
  // (truncation severed `result`), not the now-mitigated "Unterminated
  // string" parse error.
  const truncated = `{"files":[]`; // `result` never starts -- closes nothing useful
  const mockFetch = async () => ({
    ok: true,
    json: async () => ({ choices: [{ message: { content: truncated } }] }),
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "***",
    fetchImpl: mockFetch,
    fs: createFakeFs(),
  });

  try {
    await runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" });
    assert.fail("expected MalformedCodegenResponseError");
  } catch (e) {
    assert.ok(e instanceof MalformedCodegenResponseError);
    const msg = (e as Error).message;
    assert.ok(
      msg.includes('missing required "result" envelope') ||
        msg.includes("Response.result must be an object"),
      `expected the real truncation/result cause in: ${msg}`
    );
    assert.ok(
      !msg.startsWith("Failed to parse or validate response: Unterminated string"),
      `error should not mask the cause as a generic parse failure: ${msg}`
    );
  }
});

