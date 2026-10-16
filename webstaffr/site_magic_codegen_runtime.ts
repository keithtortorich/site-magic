import path from "path";
import fs from "fs/promises";
import { redactSecrets } from "./site_maker_engine.ts";

/** OpenRouter applies its own (undocumented, model-dependent) default
 * completion cap when max_tokens is omitted. Reasoning-capable free-tier
 * models spend a large, non-optional share of that budget on hidden
 * chain-of-thought before ever emitting the requested JSON -- a real
 * production "direction" role response was cut off mid-string
 * (SyntaxError: Unterminated string in JSON) because reasoning tokens
 * consumed most of an unset/small default before the multi-file JSON
 * payload could finish. Set explicitly generous so both reasoning and a
 * full multi-file response fit. */
const MAX_COMPLETION_TOKENS = 16000;

// Builder sites are emitted as separate files so no single LLM response has
// to carry the whole page at once (see run()'s per-file split path). Order
// matters: index.html is produced first so the styles.css / main.js calls
// see it in their workspace context and stay coherent with the markup.
const BUILDER_SPLIT_FILES = ["index.html", "styles.css", "main.js"];

// ============================================================================
// Types & Interfaces
// ============================================================================

export interface CodegenRoleConfig {
  readonly mutatesFiles: boolean;
  readonly instructions: string;
}

export interface FileWrite {
  path: string;
  contents: string;
}

export interface CodegenResponse {
  files: FileWrite[];
  result: Record<string, unknown>;
}

/** Models frequently wrap JSON replies in a ```json ... ``` fence even when
 * told to return raw JSON. The first version of this only matched when the
 * ENTIRE trimmed response was one closed fence -- a production remediation
 * response (a large multi-file `builder` payload, more likely to brush a
 * completion token limit) came back with the closing ``` never written,
 * so the anchored regex didn't match and the raw fenced text reached
 * JSON.parse unstripped. Now finds a fence anywhere in the text rather
 * than requiring it to BE the whole text, and if no fence closes at all,
 * falls back to slicing from the first '{' to the last '}' -- every
 * CodegenResponse is a JSON object, so that boundary is always valid when
 * present, closed-fence or not. */
/** RFC 8259 requires literal control characters (raw newlines, tabs,
 * carriage returns) inside a JSON string to be escaped -- \n not a real
 * line break. Models routinely violate this when a string value contains
 * multi-line HTML/text content: the raw newline ends the string early as
 * far as a strict parser is concerned, and JSON.parse reports it as
 * "Unterminated string" (the closing quote it expected never arrives on
 * that same logical line). This is a no-op on already-valid JSON --
 * valid JSON never contains a raw control character inside a string in
 * the first place -- so it only ever helps, never corrupts. */
function sanitizeJsonControlChars(text: string): string {
  let result = "";
  let inString = false;
  let escaped = false;
  for (const ch of text) {
    if (!inString) {
      result += ch;
      if (ch === '"') inString = true;
      continue;
    }
    if (escaped) {
      result += ch;
      escaped = false;
      continue;
    }
    if (ch === "\\") {
      result += ch;
      escaped = true;
      continue;
    }
    if (ch === '"') {
      inString = false;
      result += ch;
      continue;
    }
    if (ch === "\n") { result += "\\n"; continue; }
    if (ch === "\r") { result += "\\r"; continue; }
    if (ch === "\t") { result += "\\t"; continue; }
    result += ch;
  }
  return result;
}

/** Last-resort repair for a response truncated exactly at the boundary
 * of its own structure -- a real production finish_reviewer response
 * ended "...engines."}]}" (964 of 964 chars): the findings array and
 * the "result" object both close correctly, but the outer
 * {"files":[],"result":{...}} wrapper's own closing brace never
 * arrived. max_tokens ran out one token short of a fully-formed
 * response. Rather than chase an ever-higher token ceiling against an
 * arbitrarily verbose model, walks the string tracking open {/[ (same
 * quote/escape-aware approach as sanitizeJsonControlChars) and appends
 * whatever closers are still outstanding at the end. Only ever adds
 * characters, never removes or reorders any -- a no-op on JSON that was
 * already balanced, so this is safe to always attempt as a fallback. */
function closeUnbalancedJson(text: string): string {
  const stack: string[] = [];
  let inString = false;
  let escaped = false;
  for (const ch of text) {
    if (inString) {
      if (escaped) { escaped = false; continue; }
      if (ch === "\\") { escaped = true; continue; }
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') { inString = true; continue; }
    if (ch === "{" || ch === "[") { stack.push(ch === "{" ? "}" : "]"); continue; }
    if (ch === "}" || ch === "]") { stack.pop(); continue; }
  }
  // Truncation frequently lands mid-string (a real production remediation
  // response cut off 200 chars into an unfinished CSS rule inside a file's
  // "contents" value) -- the loop above correctly ignores braces/brackets
  // while inString, but previously left the string itself unterminated:
  // appending closers after raw, unquoted content is still invalid JSON,
  // so this repair silently failed exactly when it mattered most. Close
  // the open string first. A trailing unescaped backslash (the last
  // character consumed was itself starting an escape sequence) would
  // otherwise combine with an appended closing quote into an escaped
  // quote character rather than a terminator, so neutralize it with a
  // matching backslash first -- an escaped backslash, valid JSON, and
  // semantically the closest thing to "whatever was being escaped never
  // arrived" without inventing content.
  let suffix = "";
  if (inString) {
    if (escaped) suffix += "\\";
    suffix += '"';
  }
  if (stack.length === 0 && suffix === "") return text;
  return text + suffix + stack.reverse().join("");
}

/** Third JSON-repair tier. Handles literal, unescaped double quotes that
 * appear *inside* a JSON string value -- e.g. a findings summary quoting UI
 * copy like "Our Services" without escaping the inner quotes. This is the
 * malformation that hits the `directing`/`design_assessor`/`finish_reviewer`
 * roles (any role that writes free-text prose into a JSON string field): the
 * model emits `..."reflecting the "fast, reliable" aspect..."` and V8 reports
 * `Expected ',' or '}' after property value in JSON at position N`. It is
 * distinct from the two earlier repairs: sanitizeJsonControlChars fixes raw
 * control chars (unescaped newline), closeUnbalancedJson fixes truncation
 * (missing outer closers). This one fixes interior quotes.
 *
 * Detection rule: walk the string tracking inString/escaped exactly like the
 * other repairs. When an unescaped `"` is found while already inside a string,
 * peek past any trailing whitespace at the next significant character. If it
 * is a JSON structural delimiter (`, } ] :`) or end-of-input, the quote
 * terminates the string (a genuine closing quote). Otherwise it is an embedded
 * quote inside the string's prose and is escaped as `\"`.
 *
 * This is a no-op on already-valid JSON: valid JSON never carries an
 * unescaped interior quote, so the only `"` seen while inString is a real
 * terminator followed by `, } ] :` or end, which the rule leaves untouched --
 * so it only ever helps, never corrupts. Worst case it still fails to parse
 * and the caller falls through to the next repair tier, so it cannot silently
 * corrupt an otherwise-good response. */
function escapeEmbeddedQuotes(text: string): string {
  let result = "";
  let inString = false;
  let escaped = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (!inString) {
      result += ch;
      if (ch === '"') inString = true;
      continue;
    }
    if (escaped) {
      result += ch;
      escaped = false;
      continue;
    }
    if (ch === "\\") {
      result += ch;
      escaped = true;
      continue;
    }
    if (ch === '"') {
      // Peek past trailing whitespace to the next significant character.
      let j = i + 1;
      while (
        j < text.length &&
        (text[j] === " " || text[j] === "\t" || text[j] === "\n" || text[j] === "\r")
      ) {
        j += 1;
      }
      const next = j < text.length ? text[j] : "";
      const terminates =
        next === "" || next === "," || next === "}" || next === "]" || next === ":";
      if (terminates) {
        result += ch;
        inString = false;
      } else {
        result += '\\"';
      }
      continue;
    }
    result += ch;
  }
  return result;
}

/** Some reasoning models emit a small planning/placeholder envelope and then
 * the real CodegenResponse as a second top-level JSON object. JSON.parse
 * correctly rejects the concatenation, but both objects are individually
 * valid. Extract complete top-level objects without interpreting string
 * contents; callers deliberately prefer the last schema-valid object because
 * the model's final answer follows its placeholder. */
function extractTopLevelJsonObjects(text: string): string[] {
  const objects: string[] = [];
  let start = -1;
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = 0; index < text.length; index += 1) {
    const ch = text[index];
    if (inString) {
      if (escaped) { escaped = false; continue; }
      if (ch === "\\") { escaped = true; continue; }
      if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') { inString = true; continue; }
    if (ch === "{") {
      if (depth === 0) start = index;
      depth += 1;
      continue;
    }
    if (ch === "}" && depth > 0) {
      depth -= 1;
      if (depth === 0 && start >= 0) {
        objects.push(text.slice(start, index + 1));
        start = -1;
      }
    }
  }
  return objects;
}

/** V8's JSON.parse SyntaxError includes "at position N" for most failure
 * modes. A flat prefix snippet is useless when the malformation is deep
 * into a large multi-finding response -- a 300-char prefix missed the
 * actual error entirely on a real production failure (error at position
 * 894, snippet only covered 0-300). Centers a window on the reported
 * position when available; falls back to a longer flat prefix otherwise. */
function buildParseErrorSnippet(text: string, error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const match = message.match(/position (\d+)/);
  if (!match) return text.slice(0, 1000);
  const pos = Number(match[1]);
  const start = Math.max(0, pos - 200);
  const end = Math.min(text.length, pos + 200);
  return `[chars ${start}-${end} of ${text.length}] ${text.slice(start, end)}`;
}

export function stripJsonFence(content: string): string {
  const trimmed = content.trim();

  // Non-destructive fast path: if the trimmed response is already valid
  // JSON, return it verbatim. sanitizeJsonControlChars *unescapes* the
  // model's own valid escapes (\\n -> n), which corrupts good responses, so
  // we must not run it on content that already parses. Earlier versions
  // did, which could mangle otherwise-valid JSON and send the parser down a
  // repair tier that invented the very malformation we were trying to fix.
  try {
    JSON.parse(trimmed);
    return trimmed;
  } catch {
    // fall through to sanitized extraction
  }

  const fenced = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)```/);
  if (fenced) return sanitizeJsonControlChars(fenced[1].trim());

  const start = trimmed.indexOf("{");
  const end = trimmed.lastIndexOf("}");
  if (start !== -1 && end > start) return sanitizeJsonControlChars(trimmed.slice(start, end + 1));

  return sanitizeJsonControlChars(trimmed);
}

export interface WorkspaceFs {
  exists: (path: string) => Promise<boolean>;
  readFile: (path: string) => Promise<string>;
  writeFile: (path: string, contents: string) => Promise<void>;
  isSymlink: (path: string) => Promise<boolean>;
  realpath: (path: string) => Promise<string>;
  stat: (path: string) => Promise<{ isDirectory: () => boolean; size: number }>;
  readdir: (path: string) => Promise<string[]>;
}

// ============================================================================
// Role Configuration
// ============================================================================

export const ROLE_CONFIG: Record<string, CodegenRoleConfig> = {
  product: {
    mutatesFiles: true,
    instructions: "Define product intent, features, and user flows for the site.",
  },
  direction: {
    mutatesFiles: true,
    instructions: "Create visual direction, brand intent, and design decisions.",
  },
  builder: {
    mutatesFiles: true,
    instructions: "Generate HTML, CSS, and JavaScript for the site.",
  },
  design_assessor: {
    mutatesFiles: false,
    instructions: "Assess design quality, critique, and scores.",
  },
  remediator: {
    mutatesFiles: true,
    instructions: "Fix quality issues and improve the build.",
  },
  finish_reviewer: {
    mutatesFiles: false,
    instructions: "Final review and verdict on site readiness.",
  },
  documenter: {
    mutatesFiles: true,
    instructions: "Generate documentation for the site build.",
  },
};

// ============================================================================
// JSON Schema for Structured Output
// ============================================================================

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

// One structured finding, matching site_maker_engine.ts's `Finding` type.
// The design_assessor / finish_reviewer findings used to be free `string[]`
// prose, which is exactly the shape that spawned the embedded-quote /
// truncation repair tiers (a summary quoting UI copy like "Book Now"
// broke JSON.parse). Constraining findings to this object form at the
// provider is what ends that loop for the assessor/reviewer roles.
const FINDING_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["id", "priority", "summary"],
  properties: {
    id: { type: "string" },
    priority: { enum: ["P0", "P1", "P2", "P3"] },
    summary: { type: "string" },
  },
} as const;

// Read-only roles return no files; their entire payload is the
// role-specific `result`. Both are fully known shapes, so we pin them
// with a strict schema (findings/materialFindings constrained to
// FINDING_SCHEMA) instead of the open-ended FILE_WRITE_SCHEMA. The
// `files: []` wrapper is kept only so the response still matches the
// generic CodegenResponse parser in `run()`.
const READ_ONLY_RESPONSE_SCHEMAS: Record<string, unknown> = {
  design_assessor: {
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
          properties: { path: { type: "string" }, contents: { type: "string" } },
        },
      },
      result: {
        type: "object",
        additionalProperties: false,
        required: ["designScore", "applicableMax", "findings"],
        properties: {
          designScore: { type: "number" },
          applicableMax: { type: "number" },
          findings: { type: "array", items: FINDING_SCHEMA },
        },
      },
    },
  },
  finish_reviewer: {
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
          properties: { path: { type: "string" }, contents: { type: "string" } },
        },
      },
      result: {
        type: "object",
        additionalProperties: false,
        required: ["verdict", "authoredNotInterchangeable", "materialFindings"],
        properties: {
          verdict: { enum: ["PASS", "REBUILD", "REMEDIATE"] },
          authoredNotInterchangeable: { type: "boolean" },
          materialFindings: { type: "array", items: FINDING_SCHEMA },
        },
      },
    },
  },
};

// Mutating roles stay on FILE_WRITE_SCHEMA (strict: false, so the
// role-specific `result` object remains flexible). Read-only roles get
// their fully-constrained, strict schema so the model cannot drift the
// findings shape.
function resolveResponseSchema(role: string): unknown {
  return ROLE_CONFIG[role]?.mutatesFiles
    ? FILE_WRITE_SCHEMA
    : (READ_ONLY_RESPONSE_SCHEMAS[role] ?? FILE_WRITE_SCHEMA);
}

// ============================================================================
// Error Classes
// ============================================================================

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

export class CodexRuntimeNotConfiguredError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CodexRuntimeNotConfiguredError";
  }
}

// ============================================================================
// Path Validator
// ============================================================================

class PathValidator {
  private fs: WorkspaceFs;

  constructor(fs: WorkspaceFs) {
    this.fs = fs;
  }

  async validatePath(relativePath: string, workspaceRoot: string): Promise<string> {
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
    const reserved = [".env", ".git", ".gitignore", ".impeccable"];
    if (reserved.includes(basename)) {
      throw new WorkspacePathEscapeError(relativePath, `reserved name: ${basename}`);
    }

    // 4. Reject control characters, null bytes
    if (/[\x00-\x1f]/.test(relativePath)) {
      throw new WorkspacePathEscapeError(relativePath, "contains control characters");
    }

    // 5. Resolve and check still inside workspace. realpath requires its
    // target to exist, but this validates paths for files codegen is about
    // to *create* -- a brand-new file has never existed on disk, so
    // realpath(fullPath) throws ENOENT before the escape check even runs.
    // Walk up to the nearest existing ancestor instead (workspaceRoot is
    // the guaranteed base case, created by mkdtemp before any write) and
    // realpath that -- anything written under a workspace-contained
    // ancestor is itself workspace-contained.
    const fullPath = path.join(workspaceRoot, relativePath);
    const realWorkspace = await this.fs.realpath(workspaceRoot);

    let ancestor = fullPath;
    while (!(await this.fs.exists(ancestor))) {
      const parent = path.dirname(ancestor);
      if (parent === ancestor) break;
      ancestor = parent;
    }
    const realAncestor = await this.fs.realpath(ancestor);

    const sep = path.sep;
    if (!realAncestor.startsWith(realWorkspace + sep) && realAncestor !== realWorkspace) {
      throw new WorkspacePathEscapeError(
        relativePath,
        `symlink escapes workspace (${realAncestor})`
      );
    }

    return fullPath;
  }
}

// ============================================================================
// Default Workspace FS Implementation
// ============================================================================

function createDefaultWorkspaceFs(): WorkspaceFs {
  return {
    exists: (p: string) => fs.access(p).then(() => true).catch(() => false),
    readFile: (p: string) => fs.readFile(p, "utf-8"),
    writeFile: async (p: string, contents: string) => {
      // Models routinely emit nested paths (e.g. images/hero.jpg) for a
      // fresh workspace where that subdirectory doesn't exist yet --
      // fs.writeFile doesn't create parent dirs, so this threw ENOENT on
      // every such write. Found 2026-08-14 once gpt-4o started producing
      // paths that gpt-4o-mini's outputs happened never to use.
      await fs.mkdir(path.dirname(p), { recursive: true });
      await fs.writeFile(p, contents, "utf-8");
    },
    isSymlink: async (p: string) => {
      const stat = await fs.lstat(p);
      return stat.isSymbolicLink();
    },
    realpath: (p: string) => fs.realpath(p),
    stat: async (p: string) => {
      const s = await fs.stat(p);
      return {
        isDirectory: () => s.isDirectory(),
        size: s.size,
      };
    },
    readdir: (p: string) => fs.readdir(p),
  };
}

// ============================================================================
// OpenRouterCodegenRuntime
// ============================================================================

export class OpenRouterCodegenRuntime {
  private apiKey: string;
  private model: string;
  private baseUrl: string;
  private fetch: typeof global.fetch;
  private fs: WorkspaceFs;
  private pathValidator: PathValidator;

  constructor(opts?: {
    apiKey?: string;
    model?: string;
    baseUrl?: string;
    fetchImpl?: typeof global.fetch;
    fs?: WorkspaceFs;
  }) {
    this.apiKey = opts?.apiKey ?? process.env.OPENROUTER_API_KEY ?? "";
    this.model = opts?.model ?? process.env.SITE_MAGIC_DESIGN_MODEL ?? "openai/gpt-5.6-terra";
    // SITE_MAGIC_CODEGEN_BASE_URL, not SITE_MAGIC_API_BASE_URL: this is an
    // OpenAI-compatible LLM endpoint (a `/chat/completions` gets appended),
    // whereas SITE_MAGIC_API_BASE_URL is this repo's own control-plane URL
    // that HTTPJobStateSink/fetchJobRecord append `/site-magic/internal/...`
    // to. They were the same var until 2026-08-11, which meant the
    // production worker (SITE_MAGIC_API_BASE_URL=https://netbuild.pro) would
    // have sent every codegen call to https://netbuild.pro/chat/completions.
    this.baseUrl =
      opts?.baseUrl ??
      process.env.SITE_MAGIC_CODEGEN_BASE_URL ??
      "https://openrouter.ai/api/v1";
    this.fetch = opts?.fetchImpl ?? global.fetch;
    this.fs = opts?.fs ?? createDefaultWorkspaceFs();
    this.pathValidator = new PathValidator(this.fs);

    if (!this.apiKey && !this.baseUrl.includes("localhost")) {
      throw new CodexRuntimeNotConfiguredError("OPENROUTER_API_KEY not set");
    }
  }

  async run(args: {
    role: string;
    workspace: string;
    instructions: string;
    model?: string;
    imageDataUrls?: string[];
    splitFiles?: boolean;
  }): Promise<Record<string, unknown>> {
    const { role, workspace, instructions } = args;
    const model = args.model ?? this.model;

    // Validate role exists
    if (!ROLE_CONFIG[role]) {
      throw new Error(`Unknown role: ${role}`);
    }

    const roleConfig = ROLE_CONFIG[role];

    // Per-file codegen: builder payloads can grow past the provider's
    // completion budget and truncate mid-response, severing the required
    // `result` field (real production failure 2026-08-16: a ~57 KB builder
    // response cut at 57,648 chars, `result` gone, job failed). Splitting
    // into one small call per file keeps each response well under budget
    // and keeps `result` intact -- preferred over blindly raising max_tokens.
    if (args.splitFiles && roleConfig.mutatesFiles) {
      let lastResult: Record<string, unknown> = {};
      for (const file of BUILDER_SPLIT_FILES) {
        const override = `${instructions}\n\nYou are emitting this site ONE FILE AT A TIME. For THIS call, emit ONLY the file "${file}" as the single entry in the "files" array. Do not emit any other file. If "${file}" is not needed for this site, respond with {"files":[],"result":{"status":"skipped"}}. Keep "result" minimal (e.g. {"status":"ok"}). The other site files are produced in separate calls and will already be present in your workspace context.`;
        lastResult = await this.run({ ...args, splitFiles: false, instructions: override });
      }
      return lastResult;
    }

    // 1. Assemble workspace context
    const workspaceContext = await this.assembleWorkspaceContext(workspace);

    // 2. Build prompt
    const prompt = this.buildPrompt(role, instructions, workspaceContext);

    // 3. Call OpenRouter
    const response = await this.callOpenRouter(model, role, prompt, args.imageDataUrls ?? [], resolveResponseSchema(role));

    // 4. Validate response shape
    const stripped = stripJsonFence(response);
    let parsed: CodegenResponse;

    // One attempt = parse + validate. Any failure throws immediately with
    // the genuine cause (parse error OR schema error like "Response.result
    // must be an object"), so a truncated payload that drops `result` is
    // reported as exactly that, never silently returned.
    const attempt = (text: string): CodegenResponse => {
      const value = JSON.parse(text);
      this.validateCodegenResponse(value);
      return value;
    };

    try {
      parsed = attempt(stripped);
      } catch (firstError) {
        let lastError: unknown = firstError;
        try {
          const candidates = extractTopLevelJsonObjects(response);
          let recovered: CodegenResponse | undefined;
          for (const candidate of candidates) {
            try {
              recovered = attempt(sanitizeJsonControlChars(candidate));
              // keep scanning: the FINAL schema-valid envelope is authoritative
              // (a model may emit a planning placeholder before its real answer).
            } catch (candErr) {
              lastError = candErr;
            }
          }
          if (recovered === undefined) {
            try {
              // Third repair tier: literal unescaped quotes embedded inside a
              // JSON string value (e.g. a findings summary that quotes UI copy
              // like "Our Services"). Distinct from raw-control-char and
              // truncation repairs; a no-op on already-valid JSON.
              recovered = attempt(escapeEmbeddedQuotes(stripped));
            } catch (escErr) {
              lastError = escErr;
              try {
                recovered = attempt(closeUnbalancedJson(stripped));
              } catch (closeErr) {
                lastError = closeErr;
              }
            }
          }
          if (recovered === undefined) throw lastError;
          parsed = recovered;
        } catch (e) {
          // Repair didn't help -- report the most informative error, which
          // carries the real diagnostic snippet.
          const snippet = redactSecrets(buildParseErrorSnippet(stripped, e));
          // The 200-char-radius snippet above is what reaches the thrown
          // error (and from there the ledger/founder-facing path) -- deliberately
          // bounded. It wasn't enough to tell a truncated response apart from
          // an embedded-quote one on 2026-08-15/16's production failures: the
          // snippet only shows what's near the parse-error position, not
          // whether the response actually continues past it. Full response is
          // never persisted anywhere else once this function returns, so once
          // it's gone it's gone -- the next occurrence should not repeat that.
          // Same split SiteMakerEngine.run()'s own catch already draws between
          // the bounded ledger code and the unbounded container log: log the
          // complete raw response here, redacted, with no length cap.
          console.error(
            `[site-magic-codegen-runtime] unrecoverable parse failure, full response (${stripped.length} chars):`,
            redactSecrets(stripped)
          );
          // Classify the failure so the container log is actionable instead
          // of masking the real cause. A truncated response that drops `result`
          // (closeUnbalancedJson structurally closed it) surfaces as
          // "Response.result must be an object" -- report THAT, not the
          // original "Unterminated string" parse error, which the repair
          // already mitigated. Otherwise surface the real parse error.
          const firstMsg = e instanceof Error ? e.message : String(e);
          const resultMissing =
            /Response\.result must be an object|Response must be an object|Cannot read|undefined/.test(
              firstMsg
            );
          const diag = resultMissing
            ? `response truncated and missing required "result" envelope (recovered ${stripped.length} chars but schema validation failed -- the model likely hit its completion budget mid-response). Underlying: ${firstMsg}`
            : `failed to parse or validate response: ${firstMsg}`;
          throw new MalformedCodegenResponseError(
            `${diag} | response snippet: ${snippet}`,
            e instanceof Error ? e : undefined
          );
        }
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

    // 8. Return result
    return parsed.result;
  }

  private async assembleWorkspaceContext(workspace: string): Promise<string> {
    const files: Array<{ path: string; size: number; contents?: string }> = [];

    const walk = async (dir: string, depth: number = 0) => {
      if (depth > 5) return;

      try {
        const entries = await this.fs.readdir(dir);
        for (const entry of entries) {
          const fullPath = path.join(dir, entry);
          const stat = await this.fs.stat(fullPath);

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
      } catch {
        // Skip directories we can't read
      }
    };

    await walk(workspace);

    // Sort for deterministic output
    files.sort((a, b) => a.path.localeCompare(b.path));

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

    let prompt = `You are a structured code generator role: "${role}".

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
3. Do NOT create files outside the workspace.`;

    if (!roleConfig.mutatesFiles) {
      prompt += `
4. Do NOT modify any files. Leave the "files" array empty.
5. Return ONLY JSON data containing analysis/review results, no file modifications.`;
    }

    prompt += `

Return ONLY the JSON object, nothing else.`;

    return prompt.trim();
  }

  private async callOpenRouter(model: string, role: string, prompt: string, imageDataUrls: string[], schema?: unknown): Promise<string> {
    const endpoint = `${this.baseUrl}/chat/completions`;
    const content = imageDataUrls.length === 0
      ? prompt
      : [
          { type: "text", text: prompt },
          ...imageDataUrls.map((url) => ({ type: "image_url", image_url: { url } })),
        ];
    // Schema-constrained output at the provider. `json_object` mode only
    // nudges the model to *emit* valid JSON; it does not guarantee it, and
    // Terra in particular still produced a structural delimiter error
    // (`Expected ',' or '}'`) mid-payload under json_object. OpenRouter's
    // json_schema mode constrains the decoder to the role's schema, so the
    // wrapper `files` array and `result` object are guaranteed well-formed
    // at the source -- which is what ends the tail-chase of post-hoc JSON
    // repair tiers. `strict` is set per schema: read-only roles use a
    // fully-specified schema (findings constrained to the Finding shape) and
    // run strict: true; mutating roles keep strict: false so the
    // role-specific `result` object remains flexible (it is intentionally
    // open-ended and consumed only as Record<string, unknown>), while the
    // `files` array is still hard-constrained so file writes are always
    // `{ path, contents }`. The repair engine remains as a fallback.
    const activeSchema = schema ?? FILE_WRITE_SCHEMA;
    const strict = activeSchema === FILE_WRITE_SCHEMA ? false : true;
    const response = await this.fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [{ role: "user", content }],
        response_format: {
          type: "json_schema",
          json_schema: {
            name: `site_magic_${role}`,
            strict,
            schema: activeSchema,
          },
        },
        stream: false,
        max_tokens: MAX_COMPLETION_TOKENS,
      }),
    });

    if (!response.ok) {
      throw new Error(
        `OpenRouter API error: ${response.status} ${response.statusText}`
      );
    }

    const data = (await response.json()) as any;
    return data.choices?.[0]?.message?.content ?? "";
  }

  private validateCodegenResponse(obj: any): void {
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

// ============================================================================
// Read-Only Roles (Plain Chat Path)
// ============================================================================

export async function callReadOnlyRole(opts: {
  role: "design_assessor" | "finish_reviewer";
  instructions: string;
  workspaceContext?: string;
  fetch?: typeof global.fetch;
  apiKey?: string;
  model?: string;
  baseUrl?: string;
}): Promise<Record<string, unknown>> {
  const { role, instructions, workspaceContext = "" } = opts;
  const fetchImpl = opts.fetch ?? global.fetch;
  const apiKey = opts.apiKey ?? process.env.OPENROUTER_API_KEY ?? "";
  const model = opts.model ?? process.env.SITE_MAGIC_DESIGN_MODEL ?? "openai/gpt-5.6-terra";
  const baseUrl =
    opts.baseUrl ?? process.env.SITE_MAGIC_CODEGEN_BASE_URL ?? "https://openrouter.ai/api/v1";

  if (!apiKey) {
    throw new CodexRuntimeNotConfiguredError("OPENROUTER_API_KEY not set");
  }

  const roleInstructions =
    role === "design_assessor"
      ? "Provide a design critique with a quality score."
      : "Provide a final review verdict.";

  const prompt = `You are a read-only analysis role: "${role}".

${workspaceContext}

## Your task:

${instructions}

## Output format:

Respond with valid JSON. Do NOT modify any files.

${
  role === "design_assessor"
    ? 'Return: {"designScore": number (0-100), "applicableMax": number, "findings": string[]}'
    : 'Return: {"verdict": "PASS"|"REBUILD"|"REMEDIATE", "authoredNotInterchangeable": boolean, "materialFindings": string[]}'
}

Return ONLY the JSON object, nothing else.`;

  const responseSchema =
    role === "design_assessor"
      ? {
          type: "object",
          additionalProperties: false,
          required: ["designScore", "applicableMax", "findings"],
          properties: {
            designScore: { type: "number" },
            applicableMax: { type: "number" },
            findings: { type: "array", items: FINDING_SCHEMA },
          },
        }
      : {
          type: "object",
          additionalProperties: false,
          required: ["verdict", "authoredNotInterchangeable", "materialFindings"],
          properties: {
            verdict: { enum: ["PASS", "REBUILD", "REMEDIATE"] },
            authoredNotInterchangeable: { type: "boolean" },
            materialFindings: { type: "array", items: FINDING_SCHEMA },
          },
        };

  const endpoint = `${baseUrl}/chat/completions`;
  const response = await fetchImpl(endpoint, {
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
          name: `site_magic_${role}`,
          strict: true,
          schema: responseSchema,
        },
      },
      stream: false,
      max_tokens: MAX_COMPLETION_TOKENS,
    }),
  });

  if (!response.ok) {
    throw new Error(`OpenRouter API error: ${response.status} ${response.statusText}`);
  }

  const data = (await response.json()) as any;
  const content = data.choices?.[0]?.message?.content ?? "";

  const strippedContent = stripJsonFence(content);
  try {
    return JSON.parse(strippedContent);
  } catch (firstError) {
    try {
      // Third repair tier: literal unescaped quotes inside a free-text
      // string field (e.g. a findings summary quoting UI copy). No-op on
      // already-valid JSON; falls through to truncation repair otherwise.
      return JSON.parse(escapeEmbeddedQuotes(strippedContent));
    } catch {
      try {
        return JSON.parse(closeUnbalancedJson(strippedContent));
      } catch {
        // Repair didn't help -- report the original error.
      }
    }
    const e = firstError;
    const snippet = redactSecrets(buildParseErrorSnippet(strippedContent, e));
    throw new MalformedCodegenResponseError(
      `Invalid JSON in response: ${e instanceof Error ? e.message : String(e)} | response snippet: ${snippet}`
    );
  }
}

// ============================================================================
// Image-Content Verification (ADR-030 pre-build gate)
// ============================================================================

/**
 * Binary content-match check for one generated comp: does the picture
 * actually depict the subject its brief asked for? The brief text
 * (`role` + `altText`) is the acceptance criterion -- no score, no
 * aesthetics. Returns `{ match, reason? }`.
 *
 * This is the cheap pre-build vision gate from ADR-030: it runs once per
 * comp right after the comps are written, before the build phase, so a
 * wrong-content comp (the loop can never regenerate one -- image
 * generation is one-shot up front) is caught and (bounded-)regenerated at
 * the only point in the pipeline where comp content is mutable.
 *
 * Standalone on purpose: it does NOT route through `codex.run` /
 * `ROLE_CONFIG` / `validateCodegenResponse` (that path requires a fixed
 * role union and a `files` envelope). It speaks OpenRouter's multimodal
 * chat path directly, the same way `callReadOnlyRole` does, with a strict
 * json_schema so the `match` boolean is well-formed at the source. Any
 * failure (network, parse, malformed shape) is treated as "match" so the
 * gate can never block a job -- the gate is additive and fail-open by
 * design; the remediation loop and evidence runner remain the authoritative
 * quality backstop.
 */
export async function verifyImageContent(opts: {
  imageDataUrl: string;
  role: string;
  altText: string;
  /** Optional injected deps for tests; production reads env. */
  apiKey?: string;
  model?: string;
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}): Promise<{ match: boolean; reason?: string }> {
  const { imageDataUrl, role, altText } = opts;
  const apiKey = opts.apiKey ?? process.env.OPENROUTER_API_KEY ?? "";
  const model =
    opts.model ?? process.env.SITE_MAGIC_IMAGE_VERIFY_MODEL ?? "openai/gpt-5.6-terra";
  const baseUrl =
    opts.baseUrl ?? process.env.SITE_MAGIC_CODEGEN_BASE_URL ?? "https://openrouter.ai/api/v1";
  const fetchImpl = opts.fetchImpl ?? global.fetch;

  if (!apiKey) {
    // No credential: gate cannot run. Fail open -- log and skip, never block.
    return { match: true, reason: "verifyImageContent skipped: no OPENROUTER_API_KEY" };
  }

  const prompt = `You are a strict image-content verifier. The attached image is an AI-generated marketing photo for a local service-business website. It was supposed to show: role "${role}", described as "${altText}". Judge ONLY whether the image's actual subject matter plausibly matches that description. Ignore style, quality, lighting, and composition. Answer match: true only if the depicted subject is consistent with the brief; false if the image shows something unrelated (e.g. the brief asked for ductwork but the image shows a person's hands on an outdoor air conditioner). Return strict JSON: {"match": boolean, "reason": string}.`;

  const schema = {
    type: "object",
    additionalProperties: false,
    required: ["match", "reason"],
    properties: {
      match: { type: "boolean" },
      reason: { type: "string" },
    },
  } as const;

  try {
    const response = await fetchImpl(`${baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model,
        messages: [
          {
            role: "user",
            content: [
              { type: "text", text: prompt },
              { type: "image_url", image_url: { url: imageDataUrl } },
            ],
          },
        ],
        response_format: {
          type: "json_schema",
          json_schema: { name: "site_magic_image_verify", strict: true, schema },
        },
        stream: false,
        max_tokens: 512,
      }),
    });

    if (!response.ok) {
      return { match: true, reason: `verifyImageContent skipped: API ${response.status}` };
    }

    const data = (await response.json()) as any;
    const content = data?.choices?.[0]?.message?.content ?? "";
    const parsed = JSON.parse(stripJsonFence(content)) as { match?: unknown; reason?: unknown };
    if (typeof parsed.match !== "boolean") {
      return { match: true, reason: "verifyImageContent skipped: malformed verdict" };
    }
    return {
      match: parsed.match,
      reason: typeof parsed.reason === "string" ? parsed.reason : undefined,
    };
  } catch {
    // Fail open: never block the job because the verifier itself errored.
    return { match: true, reason: "verifyImageContent skipped: exception" };
  }
}
