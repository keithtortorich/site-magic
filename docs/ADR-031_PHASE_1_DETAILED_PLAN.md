# ADR-031 Phase 1 — Detailed Implementation Plan
## Offline Structured Codegen Runtime (no credit spend)

**Objective:** Build `site_magic_codegen_runtime.ts` as a complete subsystem. No network calls, no OpenRouter spend. Prove path safety, schema validation, and role contracts. Ready to pass to Phase 2.

**Status:** Engineering Director approval. Depth: D2 (new surface, established pattern).

---

## 1. File Structure

### New File: `webstaffr/site_magic_codegen_runtime.ts`

Kept separate from `site_magic_adapters.ts` (which is already large) because this is a complete subsystem with:
- JSON schema definition (strict, for `response_format`)
- Role mutation/immutability declarations
- Path safety validation (critical for hostile input)
- Workspace context assembly (bounded strategy)
- Model agnostic adapter (works with any OpenRouter chat model)

### New Test File: `tests_node/site_magic_codegen_runtime.test.ts`

Unit tests with injected `fetch` and filesystem. No network. Schema validation, path rejection, role violation, multi-file write ordering.

### Docs: `docs/ADR-031_PHASE_1_ARCHITECTURE.md` (new)

Architecture decisions specific to Phase 1 — why this structure, validation order, context bounding strategy.

---

## 2. Core Types & Schema

```typescript
// Exported types
export interface CodegenRoleConfig {
  readonly mutatesFiles: boolean;      // 5 roles: yes; 2 roles: no
  readonly model?: string;             // e.g., "openrouter/gpt-4o"
  readonly instructions: string;       // role-specific prompt
}

export interface FileWrite {
  path: string;                         // workspace-relative
  contents: string;
}

export interface CodegenResponse {
  files: FileWrite[];
  result: Record<string, unknown>;     // role-specific JSON
}

// Role declarations (table, not runtime)
export const ROLE_CONFIG: Record<string, CodegenRoleConfig> = {
  product: { mutatesFiles: true, instructions: "..." },
  direction: { mutatesFiles: true, instructions: "..." },
  builder: { mutatesFiles: true, instructions: "..." },
  design_assessor: { mutatesFiles: false, instructions: "..." },
  remediator: { mutatesFiles: true, instructions: "..." },
  finish_reviewer: { mutatesFiles: false, instructions: "..." },
  documenter: { mutatesFiles: true, instructions: "..." },
};

// JSON Schema for structured output (OpenRouter response_format)
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
          path: { type: "string" },
          contents: { type: "string" },
        },
      },
    },
    result: { type: "object" },
  },
} as const;

// Error classes
export class WorkspacePathEscapeError extends Error {
  constructor(path: string, reason: string) {
    super(`Workspace path escape rejected: ${path} (${reason})`);
    this.name = "WorkspacePathEscapeError";
  }
}

export class ReadOnlyRoleFileModificationError extends Error {
  constructor(role: string, fileCount: number) {
    super(`Read-only role '${role}' attempted to modify ${fileCount} file(s)`);
    this.name = "ReadOnlyRoleFileModificationError";
  }
}

export class MalformedCodegenResponseError extends Error {
  constructor(message: string, originalError?: Error) {
    super(`Codegen response malformed: ${message}`);
    this.name = "MalformedCodegenResponseError";
    if (originalError) this.cause = originalError;
  }
}
```

---

## 3. Path Safety Validation

**Contract:** Every `path` in the response is validated before any write occurs. Rejects:
- Absolute paths (`/foo`, `C:\\foo`)
- Traversal attempts (`../../../etc/passwd`)
- Symlink escapes (resolved path outside workspace)
- Null bytes, control characters
- Reserved names (`.env`, `.git`, etc.)

**Implementation:**

```typescript
export interface WorkspaceFs {
  // Test seam — same pattern as fetchImpl
  readonly exists: (path: string) => Promise<boolean>;
  readonly readFile: (path: string) => Promise<string>;
  readonly writeFile: (path: string, contents: string) => Promise<void>;
  readonly isSymlink: (path: string) => Promise<boolean>;
  readonly realpath: (path: string) => Promise<string>;
}

class PathValidator {
  /**
   * Validates a workspace-relative path. Throws WorkspacePathEscapeError if:
   * - Absolute path
   * - Contains .. traversal
   * - Symlink resolves outside workspace
   * - Reserved name
   * - Contains null bytes or control chars
   *
   * Returns the validated workspace-absolute path.
   */
  async validatePath(
    relativePath: string,
    workspaceRoot: string
  ): Promise<string> {
    // 1. Reject if absolute
    if (path.isAbsolute(relativePath)) {
      throw new WorkspacePathEscapeError(relativePath, "absolute path");
    }

    // 2. Reject if contains ..
    if (relativePath.includes("..")) {
      throw new WorkspacePathEscapeError(relativePath, "contains traversal");
    }

    // 3. Reject reserved names
    const basename = path.basename(relativePath);
    if ([".env", ".git", ".gitignore", ".impeccable"].includes(basename)) {
      throw new WorkspacePathEscapeError(relativePath, `reserved name: ${basename}`);
    }

    // 4. Reject control characters, null bytes
    if (/[\x00-\x1f]/.test(relativePath)) {
      throw new WorkspacePathEscapeError(relativePath, "contains control characters");
    }

    // 5. Resolve and check still inside workspace
    const fullPath = path.join(workspaceRoot, relativePath);
    const realPath = await fs.realpath(fullPath);
    const realWorkspace = await fs.realpath(workspaceRoot);

    if (!realPath.startsWith(realWorkspace + path.sep) && realPath !== realWorkspace) {
      throw new WorkspacePathEscapeError(
        relativePath,
        `symlink escapes workspace (${realPath})`
      );
    }

    return fullPath;
  }
}
```

**Test coverage:**
- ✓ Absolute path rejected
- ✓ `..` traversal rejected
- ✓ Symlink escape rejected
- ✓ Reserved names blocked
- ✓ Valid paths pass through

---

## 4. OpenRouterCodegenRuntime Implementation

```typescript
export class OpenRouterCodegenRuntime implements CodexRuntime {
  private apiKey: string;
  private model: string;
  private fetch: typeof global.fetch;
  private fs: WorkspaceFs;
  private pathValidator: PathValidator;

  constructor(opts?: {
    apiKey?: string;
    model?: string;
    fetchImpl?: typeof fetch;
    fs?: WorkspaceFs;
  }) {
    this.apiKey = opts?.apiKey ?? process.env.OPENROUTER_API_KEY ?? "";
    this.model = opts?.model ?? process.env.SITE_MAGIC_DESIGN_MODEL ?? "openai/gpt-4o-mini";
    this.fetch = opts?.fetchImpl ?? global.fetch;
    this.fs = opts?.fs ?? createDefaultWorkspaceFs();
    this.pathValidator = new PathValidator();

    if (!this.apiKey) {
      throw new CodexRuntimeNotConfiguredError("OPENROUTER_API_KEY not set");
    }
  }

  async run(args: {
    role: string;
    model?: string;
    workspace: string;
    instructions: string;
  }): Promise<Record<string, unknown>> {
    const { role, workspace, instructions } = args;
    const model = args.model ?? this.model;

    // Validate role exists
    if (!ROLE_CONFIG[role]) {
      throw new Error(`Unknown role: ${role}`);
    }

    const roleConfig = ROLE_CONFIG[role];

    // 1. Assemble workspace context (current state)
    const workspaceContext = await this.assembleWorkspaceContext(workspace);

    // 2. Build the prompt
    const prompt = this.buildPrompt(role, instructions, workspaceContext);

    // 3. Call OpenRouter with structured output
    const response = await this.callOpenRouter(model, prompt);

    // 4. Validate response shape
    let parsed: CodegenResponse;
    try {
      parsed = JSON.parse(response);
      this.validateCodegenResponse(parsed);
    } catch (e) {
      throw new MalformedCodegenResponseError(
        `Failed to parse or validate response: ${e instanceof Error ? e.message : String(e)}`,
        e instanceof Error ? e : undefined
      );
    }

    // 5. Check read-only role constraint
    if (!roleConfig.mutatesFiles && parsed.files.length > 0) {
      throw new ReadOnlyRoleFileModificationError(role, parsed.files.length);
    }

    // 6. Validate all paths before writing any
    const validatedWrites = await Promise.all(
      parsed.files.map(async (write) => ({
        fullPath: await this.pathValidator.validatePath(write.path, workspace),
        contents: write.contents,
      }))
    );

    // 7. Write files (no partial writes)
    for (const { fullPath, contents } of validatedWrites) {
      await this.fs.writeFile(fullPath, contents);
    }

    // 8. Return role-specific result
    return parsed.result;
  }

  private async assembleWorkspaceContext(workspace: string): Promise<string> {
    // Bounded manifest + contents strategy
    // 1. List all files in workspace
    // 2. For files < 10KB, include full contents
    // 3. For files >= 10KB, include path + size only
    // 4. Prefix with "Current workspace state:"
    //
    // This keeps context bounded while allowing the model to reason about
    // what already exists and what needs to be changed.

    const files: Array<{ path: string; size: number; contents?: string }> = [];

    // Recursive walk (bounded depth, e.g., 5 levels)
    const walk = async (dir: string, depth: number = 0) => {
      if (depth > 5) return; // Don't recurse too deep

      const entries = await fs.readdir(dir);
      for (const entry of entries) {
        const fullPath = path.join(dir, entry);
        const stat = await fs.stat(fullPath);

        if (stat.isDirectory()) {
          if (![".git", "node_modules", ".impeccable"].includes(entry)) {
            await walk(fullPath, depth + 1);
          }
        } else {
          const relativePath = path.relative(workspace, fullPath);
          const size = stat.size;

          if (size < 10 * 1024) {
            const contents = await this.fs.readFile(fullPath);
            files.push({ path: relativePath, size, contents });
          } else {
            files.push({ path: relativePath, size });
          }
        }
      }
    };

    await walk(workspace);

    // Format as text block for the model
    let context = "## Current workspace state:\n\n";
    for (const file of files) {
      if (file.contents !== undefined) {
        context += `### ${file.path} (${file.size} bytes)\n\`\`\`\n${file.contents}\n\`\`\`\n\n`;
      } else {
        context += `- ${file.path} (${file.size} bytes, not shown)\n`;
      }
    }

    return context;
  }

  private buildPrompt(
    role: string,
    instructions: string,
    workspaceContext: string
  ): string {
    const roleConfig = ROLE_CONFIG[role];

    return `
You are a structured code generator role: "${role}".

${workspaceContext}

## Your task:

${instructions}

## Output format:

You MUST respond with valid JSON matching this schema:
\`\`\`json
{
  "files": [
    {"path": "relative/path/to/file.html", "contents": "..."},
    ...
  ],
  "result": { /* role-specific JSON */ }
}
\`\`\`

## Constraints:

1. All paths must be relative to the workspace root.
2. Do NOT use absolute paths or ".." traversal.
3. Do NOT create files outside the workspace.
${!roleConfig.mutatesFiles ? `4. Do NOT modify any files. Leave the "files" array empty.` : ""}

${!roleConfig.mutatesFiles ? `
Result should contain only JSON data, no file modifications.
` : ""}

Return ONLY the JSON object, nothing else.
    `.trim();
  }

  private async callOpenRouter(model: string, prompt: string): Promise<string> {
    // In Phase 1, this is mocked. In Phase 2, it hits the real API.
    //
    // Signature (for testing):
    //   POST https://openrouter.ai/api/v1/chat/completions
    //   {
    //     "model": model,
    //     "messages": [{"role": "user", "content": prompt}],
    //     "response_format": {
    //       "type": "json_schema",
    //       "json_schema": {
    //         "name": "CodegenResponse",
    //         "strict": true,
    //         "schema": FILE_WRITE_SCHEMA
    //       }
    //     }
    //   }
    //
    // Returns: response.choices[0].message.content (should be valid JSON)

    const response = await this.fetch("https://openrouter.ai/api/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content: prompt }],
        response_format: {
          type: "json_schema",
          json_schema: {
            name: "CodegenResponse",
            strict: true,
            schema: FILE_WRITE_SCHEMA,
          },
        },
      }),
    });

    if (!response.ok) {
      throw new Error(
        `OpenRouter API error: ${response.status} ${response.statusText}`
      );
    }

    const data = await response.json() as any;
    return data.choices[0]?.message?.content ?? "";
  }

  private validateCodegenResponse(obj: any): void {
    // Validate against FILE_WRITE_SCHEMA
    if (typeof obj !== "object" || obj === null) {
      throw new Error("Response must be an object");
    }

    if (!Array.isArray(obj.files)) {
      throw new Error("Response.files must be an array");
    }

    for (const file of obj.files) {
      if (typeof file !== "object" || file === null) {
        throw new Error("Each file must be an object");
      }
      if (typeof file.path !== "string") {
        throw new Error("Each file must have a string path");
      }
      if (typeof file.contents !== "string") {
        throw new Error("Each file must have string contents");
      }
    }

    if (typeof obj.result !== "object" || obj.result === null) {
      throw new Error("Response.result must be an object");
    }
  }
}
```

---

## 5. Read-Only Roles → Plain Chat Path

For `design_assessor` and `finish_reviewer`, skip the runtime entirely. Call OpenRouter chat-completions directly, no file harness:

```typescript
export async function callReadOnlyRole(opts: {
  role: "design_assessor" | "finish_reviewer";
  instructions: string;
  workspaceContext?: string;
  fetch?: typeof global.fetch;
  apiKey?: string;
  model?: string;
}): Promise<Record<string, unknown>> {
  const { role, instructions, workspaceContext = "", fetch: fetchImpl = global.fetch } = opts;
  const apiKey = opts.apiKey ?? process.env.OPENROUTER_API_KEY ?? "";
  const model = opts.model ?? process.env.SITE_MAGIC_DESIGN_MODEL ?? "openai/gpt-4o-mini";

  if (!apiKey) {
    throw new CodexRuntimeNotConfiguredError("OPENROUTER_API_KEY not set");
  }

  const prompt = `
You are a read-only analysis role: "${role}".

${workspaceContext}

## Your task:

${instructions}

## Output format:

Respond with valid JSON. Do NOT modify any files.

${role === "design_assessor"
  ? `Return: {"designScore": number, "applicableMax": number, "findings": string[]}`
  : ""}

${role === "finish_reviewer"
  ? `Return: {"verdict": "PASS"|"REBUILD"|"REMEDIATE", "authoredNotInterchangeable": boolean, "materialFindings": string[]}`
  : ""}

Return ONLY the JSON object, nothing else.
  `.trim();

  const response = await fetchImpl("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages: [{ role: "user", content: prompt }],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "AnalysisResponse",
          strict: true,
          schema: {
            type: "object",
            ...(role === "design_assessor" && {
              required: ["designScore", "applicableMax", "findings"],
              properties: {
                designScore: { type: "number" },
                applicableMax: { type: "number" },
                findings: { type: "array", items: { type: "string" } },
              },
            }),
            ...(role === "finish_reviewer" && {
              required: ["verdict", "authoredNotInterchangeable", "materialFindings"],
              properties: {
                verdict: { enum: ["PASS", "REBUILD", "REMEDIATE"] },
                authoredNotInterchangeable: { type: "boolean" },
                materialFindings: { type: "array", items: { type: "string" } },
              },
            }),
          },
        },
      },
    }),
  });

  if (!response.ok) {
    throw new Error(
      `OpenRouter API error: ${response.status} ${response.statusText}`
    );
  }

  const data = await response.json() as any;
  const content = data.choices[0]?.message?.content ?? "";

  try {
    return JSON.parse(content);
  } catch {
    throw new MalformedCodegenResponseError(`Invalid JSON in response: ${content}`);
  }
}
```

---

## 6. Unit Tests

**File:** `tests_node/site_magic_codegen_runtime.test.ts`

### Test Suite Structure

```typescript
describe("OpenRouterCodegenRuntime", () => {
  // Construction
  describe("constructor", () => {
    test("throws CodexRuntimeNotConfiguredError if OPENROUTER_API_KEY missing");
    test("uses SITE_MAGIC_DESIGN_MODEL env var if set");
    test("accepts injected fetch and fs for testing");
  });

  // Path validation
  describe("path validation", () => {
    test("accepts valid relative paths");
    test("rejects absolute paths");
    test("rejects paths with ..");
    test("rejects symlinks that escape workspace");
    test("rejects reserved names (.env, .git, etc.)");
    test("rejects paths with control characters");
    test("rejects null bytes");
  });

  // Schema validation
  describe("response validation", () => {
    test("accepts valid CodegenResponse");
    test("rejects response missing 'files' key");
    test("rejects response missing 'result' key");
    test("rejects files not an array");
    test("rejects file without path");
    test("rejects file without contents");
  });

  // Role constraints
  describe("role constraints", () => {
    test("mutating role can write files");
    test("read-only role throws if attempts to write");
    test("unknown role throws");
  });

  // Multi-file writes
  describe("file writes", () => {
    test("writes all validated files");
    test("validates all paths before writing any (no partial)");
    test("writes in order (deterministic)");
    test("includes workspace context with current state");
  });

  // Workspace context
  describe("workspace context assembly", () => {
    test("includes all files under 10KB with full contents");
    test("includes large files (10KB+) as path+size only");
    test("skips .git, node_modules, .impeccable directories");
    test("limits recursion depth to prevent huge contexts");
  });

  // Mock OpenRouter calls
  describe("mocked OpenRouter calls", () => {
    test("builds correct POST payload");
    test("includes FILE_WRITE_SCHEMA in response_format");
    test("sets strict: true for structured output");
    test("parses JSON response correctly");
  });
});

describe("readOnlyRole", () => {
  test("design_assessor returns designScore/applicableMax/findings");
  test("finish_reviewer returns verdict/authoredNotInterchangeable/materialFindings");
  test("throws if no OPENROUTER_API_KEY");
  test("mocks fetch for testing");
});
```

### Key Tests (Examples)

```typescript
test("path validation: rejects traversal", async () => {
  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch, // returns FILE_WRITE_SCHEMA-matching response
    fs: createFakeFs(),
  });

  const response = {
    files: [{ path: "../../../etc/passwd", contents: "bad" }],
    result: {},
  };

  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ choices: [{ message: { content: JSON.stringify(response) } }] }),
  });

  await expect(
    runtime.run({
      role: "product",
      workspace: "/tmp/workspace",
      instructions: "test",
    })
  ).rejects.toThrow(WorkspacePathEscapeError);
});

test("read-only role: finish_reviewer cannot write", async () => {
  const response = {
    files: [{ path: "bad.html", contents: "should fail" }],
    result: { verdict: "PASS" },
  };

  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ choices: [{ message: { content: JSON.stringify(response) } }] }),
  });

  await expect(
    runtime.run({
      role: "finish_reviewer",
      workspace: "/tmp/workspace",
      instructions: "review",
    })
  ).rejects.toThrow(ReadOnlyRoleFileModificationError);
});

test("multi-file write: validates all before writing any", async () => {
  const fs = createFakeFs();
  const writeFileSpy = jest.spyOn(fs, "writeFile");

  const response = {
    files: [
      { path: "valid1.html", contents: "ok" },
      { path: "valid2.css", contents: "ok" },
      { path: "../bad.js", contents: "nope" }, // Path escape
    ],
    result: {},
  };

  mockFetch.mockResolvedValueOnce({ /* ... */ });

  await expect(
    runtime.run({ role: "builder", workspace: "/tmp", instructions: "test" })
  ).rejects.toThrow(WorkspacePathEscapeError);

  // No partial writes
  expect(writeFileSpy).not.toHaveBeenCalled();
});

test("workspace context: includes small files, excludes large", async () => {
  const fs = createFakeFs({
    files: {
      "index.html": "a".repeat(5000), // 5KB, should be included
      "large.js": "b".repeat(15000), // 15KB, path+size only
      ".git/config": "ignored",
    },
  });

  const runtime = new OpenRouterCodegenRuntime({
    apiKey: "test-key",
    fetchImpl: mockFetch,
    fs,
  });

  let capturedPrompt = "";
  mockFetch.mockImplementation(async (url, opts) => {
    capturedPrompt = JSON.parse(opts.body as string).messages[0].content;
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ files: [], result: {} }) } }],
      }),
    };
  });

  await runtime.run({
    role: "product",
    workspace: "/tmp",
    instructions: "test",
  });

  expect(capturedPrompt).toContain("index.html");
  expect(capturedPrompt).toContain("a".repeat(5000));
  expect(capturedPrompt).toContain("large.js");
  expect(capturedPrompt).toContain("15000");
  expect(capturedPrompt).not.toContain("b".repeat(15000));
  expect(capturedPrompt).not.toContain(".git");
});
```

---

## 7. Acceptance Criteria

✓ All tests pass (no network)
✓ Path validation comprehensive and fail-closed
✓ Role read-only/mutating declarations enforced
✓ Schema validation against FILE_WRITE_SCHEMA
✓ Multi-file writes are atomic (validate before write)
✓ Workspace context assembly bounded
✓ Read-only roles use plain chat path
✓ Integration with `SiteMakerEngine` unchanged (interface contract holds)
✓ Node suite stays green (44+ tests existing)

---

## 8. Open Questions for Founder

**Answered by directive in ADR-031:**
1. Option A (structured codegen runtime) selected
2. OpenRouter reused, no new vendor
3. HVAC-only proof-of-concept for Monday

**For Phase 1 sign-off:**
- Review architecture and path safety approach?
- Approve proceeding to Phase 2 (live probe, spends $X credit)?

---

## 9. Handoff to Phase 2

Once Phase 1 is complete and green:

1. **Phase 2 is a live probe:** Two real OpenRouter calls (product + direction) on `_demo_hvac`
2. **Founder approval gate:** Spend limit + proceed-or-escalate decision
3. **Success criterion:** Response shape holds, cost is acceptable
4. **Fallback ready:** Option B (Claude Agent SDK) documented and approved if output ceiling breaks Phase 3

---

**Next:** Engineering Director approval on this plan, then begin Phase 1 implementation.
