/**
 * Executable worker entrypoint. Receives the webhook
 * HTTPWebhookSiteMagicQueue (site_magic_adapters.py) sends, pulls the full
 * job via the internal control-plane endpoint, and runs SiteMakerEngine
 * end to end, reporting every transition back through JobStateSink.
 *
 * Fail-closed like the rest of this repo: buildProductionDependencies()
 * throws a *NotConfiguredError immediately for anything missing rather
 * than degrading silently.
 *
 * Dependencies are built per job, not once at server startup:
 * PlaywrightEvidenceRunner (site_magic_evidence_runner.ts) needs the
 * job's own tenantId at construction (tenantIsolationPassed checks for a
 * hardcoded *other*-tenant path, which requires knowing which tenant is
 * "self"), so there is no single WorkerDependencies value that's valid
 * across jobs for different tenants. buildDeps is a factory, called once
 * per incoming webhook after the tenant_id is known.
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { Server } from "node:http";
import { timingSafeEqual } from "node:crypto";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SiteMakerEngine,
  type SiteMagicJobInput,
  type SiteSource,
  type CodexRuntime,
  type ImageGenerator,
  type ImageContentVerifier,
  type EvidenceRunner,
  type ArtifactStore,
  type JobStateSink,
} from "./site_maker_engine.ts";
import {
  OpenAICodexRuntime,
  OpenRouterImageGenerator,
  SupabaseArtifactStore,
  HTTPJobStateSink,
} from "./site_magic_adapters.ts";
import { OpenRouterCodegenRuntime, verifyImageContent } from "./site_magic_codegen_runtime.ts";
import {
  OpenAICompatibleCodegenRuntime,
  OpenAICompatibleImageGenerator,
  resolveOpenAICompatibleChatConfig,
} from "./site_magic_ai_compatible.ts";
import { LocalArtifactStore, SyntheticImageGenerator } from "./site_magic_local.ts";
import { PlaywrightEvidenceRunner } from "./site_magic_evidence_runner.ts";

/** Rendered pages reference /static/site.css and /static/angel-widget.js,
 * served by site_render_router.py from this same directory (dedicated
 * routes, not a StaticFiles mount -- see that file's module docstring).
 * Without this, PlaywrightEvidenceRunner's standalone workspace server
 * knows nothing about /static/ and every job reports those assets missing. */
const APP_STATIC_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "templates", "site", "static");

export class WorkerNotConfiguredError extends Error {}
export class UnresolvableSourceError extends Error {}

export interface WorkerDependencies {
  states: JobStateSink;
  codex: CodexRuntime;
  images: ImageGenerator;
  imageVerifier: ImageContentVerifier;
  evidence: EvidenceRunner;
  artifacts: ArtifactStore;
}

export type DependencyFactory = (tenantId: string) => WorkerDependencies;

/** Real adapters wired from env, built fresh per job -- see module
 * docstring for why `evidence` can't be a single shared instance.
 *
 * Vendor priority:
 * 1. SITE_MAGIC_USE_AI_COMPATIBLE=true → OpenAI-compatible endpoint (Ollama, NVIDIA, vLLM)
 *    configured via OPENAI_COMPATIBLE_BASE_URL, OPENAI_COMPATIBLE_API_KEY, OPENAI_COMPATIBLE_MODEL
 * 2. SITE_MAGIC_USE_OMNIROUTE=true (default) → OpenRouter via OmniRoute (ADR-031)
 * 3. SITE_MAGIC_USE_OMNIROUTE=false → OpenAI Codex runtime
 *
 * Images use the matching OpenAI-compatible endpoint when explicitly
 * selected; otherwise they remain on the established OpenRouter adapter.
 */
export function buildProductionDependencies(tenantId: string): WorkerDependencies {
  // Vendor priority: OpenAI-compatible (Ollama/NVIDIA/vLLM) → OpenRouter/OmniRoute → OpenAI
  const useAICompatible = process.env.SITE_MAGIC_USE_AI_COMPATIBLE === "true";
  const useOmniRoute = process.env.SITE_MAGIC_USE_OMNIROUTE !== "false";
  const useSyntheticAssets = process.env.SITE_MAGIC_USE_SYNTHETIC_ASSETS === "true";
  const codegenBaseUrl = process.env.SITE_MAGIC_CODEGEN_BASE_URL;
  const viaLocalGateway = Boolean(codegenBaseUrl?.includes("localhost"));

  let codexRuntime: CodexRuntime;
  let imageGenerator: ImageGenerator;
  let imageVerifier: ImageContentVerifier = verifyImageContent;

  if (useAICompatible) {
    // Use generic OpenAI-compatible implementations (Ollama, NVIDIA, vLLM, etc.)
    codexRuntime = new OpenAICompatibleCodegenRuntime();
    imageGenerator = useSyntheticAssets ? new SyntheticImageGenerator() : new OpenAICompatibleImageGenerator();
    const compatibleChat = resolveOpenAICompatibleChatConfig();
    const compatibleVerifyModel =
      process.env.SITE_MAGIC_IMAGE_VERIFY_MODEL ??
      compatibleChat.model;
    imageVerifier = (args) => verifyImageContent({
      ...args,
      apiKey: compatibleChat.apiKey,
      baseUrl: compatibleChat.baseUrl,
      model: compatibleVerifyModel,
    });
  } else if (useOmniRoute) {
    // Vendor-independent CodexRuntime via OmniRoute (ADR-031): 290 providers,
    // auto-fallback, free tiers.
    //
    // The endpoint comes from SITE_MAGIC_CODEGEN_BASE_URL, NOT
    // SITE_MAGIC_API_BASE_URL -- the latter is this repo's own control plane
    // (HTTPJobStateSink/fetchJobRecord post to it), and in production it is
    // https://netbuild.pro, which is not an OpenAI-compatible LLM endpoint.
    // Unset means openrouter.ai directly, authenticated with
    // OPENROUTER_API_KEY. Point it at a local OmniRoute gateway
    // (http://localhost:20128/v1) to route through that instead.
    codexRuntime = new OpenRouterCodegenRuntime(
      viaLocalGateway
        ? {
            apiKey: "dummy",
            model: process.env.SITE_MAGIC_DESIGN_MODEL ?? "openai/gpt-5.6-terra",
            baseUrl: codegenBaseUrl,
          }
        : { baseUrl: codegenBaseUrl }
    );
    imageGenerator = useSyntheticAssets ? new SyntheticImageGenerator() : new OpenRouterImageGenerator();
  } else {
    // Fallback to OpenAI's Codex runtime while retaining the approved
    // OpenRouter image path (GPT Image org access remains unapproved).
    codexRuntime = new OpenAICodexRuntime();
    imageGenerator = useSyntheticAssets ? new SyntheticImageGenerator() : new OpenRouterImageGenerator();
  }

  return {
    states: new HTTPJobStateSink(),
    codex: codexRuntime,
    images: imageGenerator,
    imageVerifier,
    evidence: new PlaywrightEvidenceRunner({ tenantId, staticRoot: APP_STATIC_ROOT }),
    artifacts: process.env.SITE_MAGIC_USE_LOCAL_ARTIFACTS === "true"
      ? new LocalArtifactStore()
      : new SupabaseArtifactStore(),
  };
}

export interface JobRecord {
  job_id: string;
  tenant_id: string;
  source_type: string;
  source_payload: Record<string, unknown>;
  status: string;
}

export interface ControlPlaneBuildSource {
  build: {
    build_id: string;
    tenant_id: string;
    approval_id: string;
    plan_id: string;
    plan_version: number;
    plan_hash: string;
    fact_snapshot_hash: string;
    correlation_id?: string;
    revision_id?: string | null;
    revision_scope?: string[];
  };
  approval: Record<string, unknown>;
  plan: {
    plan_id: string;
    tenant_id: string;
    version: number;
    status: string;
    plan_hash: string;
    fact_snapshot_hash: string;
    content: Record<string, unknown>;
    fact_snapshot: Array<Record<string, unknown>>;
  };
  facts: Array<Record<string, unknown>>;
}

function controlPlaneSectionIds(content: Record<string, unknown>): string[] {
  const pages = Array.isArray(content.pages) ? content.pages : [];
  const ids: string[] = [];
  for (const page of pages) {
    if (!page || typeof page !== "object" || Array.isArray(page)) continue;
    const pageRecord = page as Record<string, unknown>;
    if (typeof pageRecord.page_id !== "string") continue;
    const sections = Array.isArray(pageRecord.sections) ? pageRecord.sections : [];
    if (sections.length === 0) {
      ids.push(pageRecord.page_id);
      continue;
    }
    for (const section of sections) {
      if (!section || typeof section !== "object" || Array.isArray(section)) continue;
      const sectionId = (section as Record<string, unknown>).section_id;
      if (typeof sectionId === "string") ids.push(`${pageRecord.page_id}.${sectionId}`);
    }
  }
  return ids;
}

class HTTPControlPlaneBuildSink implements JobStateSink {
  private readonly source: ControlPlaneBuildSource;
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;

  constructor(
    source: ControlPlaneBuildSource,
    options: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch },
  ) {
    this.source = source;
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.apiKey = options.apiKey;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  async transition(
    _jobId: string,
    tenantId: string,
    state: string,
    metadata?: Record<string, unknown>,
  ): Promise<void> {
    if (tenantId !== this.source.build.tenant_id) {
      throw new Error("control-plane callback tenant does not match the approved build");
    }
    if (state === "failed" || state === "quarantined") {
      const failureCode = typeof metadata?.errorType === "string"
        ? metadata.errorType
        : typeof metadata?.reason === "string" ? metadata.reason : "build_failed";
      await this.post(
        `/v1/internal/builds/${this.source.build.build_id}/failed`,
        { tenant_id: tenantId, failure_code: failureCode.slice(0, 128) },
        `${this.source.build.build_id}:failed`,
      );
      return;
    }
    if (state !== "ready_for_review") return;
    const providerBuildId = typeof metadata?.buildId === "string" ? metadata.buildId : "";
    const qualityReport = metadata?.report;
    if (!providerBuildId || !qualityReport || typeof qualityReport !== "object") {
      throw new Error("control-plane build completion did not include artifact and quality evidence");
    }
    const factIds = this.source.plan.fact_snapshot
      .map((fact) => fact.fact_id)
      .filter((factId): factId is string => typeof factId === "string");
    const claimIds = Array.isArray(this.source.plan.content.claims)
      ? this.source.plan.content.claims
          .filter((claim) => claim && typeof claim === "object" && !Array.isArray(claim))
          .filter((claim) => (claim as Record<string, unknown>).status === "supported")
          .map((claim) => (claim as Record<string, unknown>).claim_id)
          .filter((claimId): claimId is string => typeof claimId === "string")
      : [];
    const revisionScope = this.source.build.revision_scope ?? [];
    const allSections = controlPlaneSectionIds(this.source.plan.content);
    const traceManifest: Record<string, unknown> = {
      plan_hash: this.source.build.plan_hash,
      fact_snapshot_hash: this.source.build.fact_snapshot_hash,
      artifacts: [{ artifact_id: providerBuildId, fact_ids: factIds, claim_ids: claimIds }],
    };
    if (this.source.build.revision_id) {
      traceManifest.revision_id = this.source.build.revision_id;
      traceManifest.changed_scope = revisionScope;
      traceManifest.unchanged_scope = allSections.filter((section) => !revisionScope.includes(section));
    }
    await this.post(
      `/v1/internal/builds/${this.source.build.build_id}/preview`,
      {
        tenant_id: tenantId,
        preview_locator: `${tenantId}/${this.source.build.build_id}/${providerBuildId}.tar`,
        artifact_manifest: {
          locator: `${tenantId}/${this.source.build.build_id}/${providerBuildId}.tar`,
          provider_build_id: providerBuildId,
          control_build_id: this.source.build.build_id,
        },
        rendered_evidence: {
          verifier: "SiteMakerEngine",
          rendered_site_quality_report: true,
          control_build_id: this.source.build.build_id,
        },
        trace_manifest: traceManifest,
        quality_report: qualityReport,
      },
      `${this.source.build.build_id}:preview`,
    );
  }

  private async post(path: string, body: Record<string, unknown>, idempotencyKey: string): Promise<void> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": this.apiKey,
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(`Control-plane callback failed: ${response.status} ${await response.text()}`);
    }
  }
}

type RendererBaseline = { path: string; pages: string[] };

function resolveRendererBaseline(payload: Record<string, unknown>): RendererBaseline | undefined {
  const value = payload.renderer_baseline;
  if (value === undefined) return undefined;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new UnresolvableSourceError("intake renderer_baseline must be an object");
  }
  const path = (value as Record<string, unknown>).path;
  const pages = (value as Record<string, unknown>).pages;
  if (typeof path !== "string" || !path.startsWith("/sites/") || !path.endsWith("/web")) {
    throw new UnresolvableSourceError("intake renderer_baseline.path is invalid");
  }
  if (!Array.isArray(pages) || pages.some((page) => typeof page !== "string")) {
    throw new UnresolvableSourceError("intake renderer_baseline.pages is invalid");
  }
  return { path, pages: pages as string[] };
}

async function materializeRendererBaseline(
  baseline: RendererBaseline,
  workspace: string,
  controlPlane: { baseUrl: string; fetchImpl?: typeof fetch },
): Promise<string> {
  const fetchImpl = controlPlane.fetchImpl ?? fetch;
  const url = `${controlPlane.baseUrl.replace(/\/+$/, "")}${baseline.path}`;
  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new UnresolvableSourceError(`renderer baseline fetch failed: ${response.status}`);
  }
  const dir = join(workspace, "renderer-baseline");
  await mkdir(dir, { recursive: true });
  const target = join(dir, "index.html");
  const html = await response.text();
  await writeFile(target, html, "utf8");
  // Seed the audited entry with the deterministic renderer output. The
  // builder normally replaces this file with its authored design, but a
  // malformed/truncated provider response must never leave Lighthouse
  // requesting a nonexistent document (a real production 404 on job 53).
  await writeFile(join(workspace, "index.html"), html, "utf8");
  await writeFile(join(dir, "manifest.json"), JSON.stringify({ sourceUrl: url, pages: baseline.pages }, null, 2), "utf8");
  return "renderer-baseline/index.html";
}

export async function fetchJobRecord(
  jobId: string,
  tenantId: string,
  options: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch }
): Promise<JobRecord> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = `${options.baseUrl.replace(/\/+$/, "")}/site-magic/internal/jobs/${jobId}?tenant_id=${encodeURIComponent(tenantId)}`;
  const response = await fetchImpl(url, { headers: { "X-API-Key": options.apiKey } });
  if (!response.ok) {
    throw new Error(`Fetching Site Magic job ${jobId} failed: ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as JobRecord;
}

export async function fetchControlPlaneBuildSource(
  buildId: string,
  tenantId: string,
  options: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch }
): Promise<ControlPlaneBuildSource> {
  const fetchImpl = options.fetchImpl ?? fetch;
  const url = `${options.baseUrl.replace(/\/+$/, "")}/v1/internal/builds/${encodeURIComponent(buildId)}/source?tenant_id=${encodeURIComponent(tenantId)}`;
  const response = await fetchImpl(url, { headers: { "X-API-Key": options.apiKey } });
  if (!response.ok) {
    throw new Error(`Fetching control-plane build ${buildId} source failed: ${response.status} ${await response.text()}`);
  }
  const source = (await response.json()) as ControlPlaneBuildSource;
  if (
    !source?.build || source.build.build_id !== buildId || source.build.tenant_id !== tenantId ||
    source.plan?.status !== "approved" || source.plan.plan_hash !== source.build.plan_hash ||
    source.plan.fact_snapshot_hash !== source.build.fact_snapshot_hash || !Array.isArray(source.facts)
  ) {
    throw new UnresolvableSourceError("control-plane build source failed approval/hash validation");
  }
  const snapshot = source.plan.fact_snapshot;
  if (!Array.isArray(snapshot) || snapshot.some((item) => (
    !item || typeof item !== "object" || Array.isArray(item) ||
    typeof (item as Record<string, unknown>).fact_id !== "string" ||
    typeof (item as Record<string, unknown>).content_hash !== "string" ||
    (item as Record<string, unknown>).status !== "verified"
  ))) {
    throw new UnresolvableSourceError("control-plane plan fact snapshot is invalid");
  }
  const snapshotById = new Map(snapshot.map((item) => [item.fact_id as string, item]));
  if (snapshotById.size !== snapshot.length || source.facts.length !== snapshot.length || source.facts.some((fact) => {
    if (!fact || typeof fact !== "object" || Array.isArray(fact)) return true;
    const factId = fact.fact_id;
    const expected = typeof factId === "string" ? snapshotById.get(factId) : undefined;
    return !expected || fact.tenant_id !== tenantId || fact.status !== "verified" ||
      fact.content_hash !== expected.content_hash;
  })) {
    throw new UnresolvableSourceError("control-plane facts do not match the approved fact snapshot");
  }
  return source;
}

export function resolveControlPlaneSource(source: ControlPlaneBuildSource): SiteSource {
  if (
    source.plan.plan_id !== source.build.plan_id ||
    source.plan.version !== source.build.plan_version ||
    source.plan.tenant_id !== source.build.tenant_id
  ) {
    throw new UnresolvableSourceError("control-plane plan does not match the approved build envelope");
  }
  return {
    type: "control_plane",
    buildId: source.build.build_id,
    planHash: source.build.plan_hash,
    factSnapshotHash: source.build.fact_snapshot_hash,
    revisionId: source.build.revision_id ?? undefined,
    revisionScope: source.build.revision_scope ?? undefined,
    plan: source.plan.content,
    facts: source.facts,
  };
}

/**
 * Maps the control-plane's generic source_payload into SiteMakerEngine's
 * discriminated SiteSource. "url" and "repository" follow directly from
 * the payload shape SiteSource already defines. "intake" carries
 * verified_facts alongside intake_id -- intake_router.py's
 * _enqueue_site_magic_job_if_configured() writes
 * build_public_site_data(submission)'s output there (the same
 * internal-fields-stripped projection GET /sites/{tenant_id} serves), so
 * this is the vetted public-safe view, not a raw intake_submissions dump.
 * A job enqueued before that field existed (or any malformed payload)
 * throws rather than silently treating an empty object as "no facts" --
 * SiteSource.verifiedFacts feeding PRODUCT.md is exactly where a
 * fabricated or wrong fact would become public site content.
 */
export function resolveSource(record: Pick<JobRecord, "source_type" | "source_payload">): SiteSource {
  switch (record.source_type) {
    case "url": {
      const url = record.source_payload.url;
      if (typeof url !== "string") throw new UnresolvableSourceError("url source_payload missing 'url'");
      return { type: "url", url, ownershipAttested: true };
    }
    case "repository": {
      const surface = record.source_payload.surface;
      if (typeof surface !== "string") throw new UnresolvableSourceError("repository source_payload missing 'surface'");
      return { type: "repository", surface, internalAuthorization: true };
    }
    case "intake": {
      const intakeId = record.source_payload.intake_id;
      const verifiedFacts = record.source_payload.verified_facts;
      if (typeof intakeId !== "string") {
        throw new UnresolvableSourceError("intake source_payload missing 'intake_id'");
      }
      if (typeof verifiedFacts !== "object" || verifiedFacts === null || Array.isArray(verifiedFacts)) {
        throw new UnresolvableSourceError(
          "intake source_payload missing 'verified_facts' -- job was likely enqueued before intake_router.py started writing it"
        );
      }
      return { type: "intake", intakeId, verifiedFacts: verifiedFacts as Record<string, unknown> };
    }
    default:
      throw new UnresolvableSourceError(`Unknown Site Magic source_type: ${record.source_type}`);
  }
}

export async function runJob(
  input: SiteMagicJobInput,
  deps: WorkerDependencies
): Promise<{ status: "ready_for_review" | "failed" | "quarantined"; buildId?: string }> {
  return new SiteMakerEngine(deps).run(input);
}

export async function processJob(
  jobId: string,
  tenantId: string,
  buildDeps: DependencyFactory,
  controlPlane: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch }
): Promise<{ status: "ready_for_review" | "failed" | "quarantined"; buildId?: string }> {
  const record = await fetchJobRecord(jobId, tenantId, controlPlane);
  let source = resolveSource(record);
  const workspace = await mkdtemp(join(tmpdir(), `site-magic-${jobId}-`));
  if (source.type === "intake") {
    const baseline = resolveRendererBaseline(record.source_payload);
    if (baseline) {
      const baselinePath = await materializeRendererBaseline(baseline, workspace, controlPlane);
      source = { ...source, rendererBaselinePath: baselinePath };
    }
  }
  return runJob({ jobId, tenantId, workspace, source }, buildDeps(tenantId));
}

export async function processControlPlaneBuild(
  buildId: string,
  tenantId: string,
  buildDeps: DependencyFactory,
  controlPlane: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch }
): Promise<{ status: "ready_for_review" | "failed" | "quarantined"; buildId?: string }> {
  const sourceRecord = await fetchControlPlaneBuildSource(buildId, tenantId, controlPlane);
  const workspace = await mkdtemp(join(tmpdir(), `site-magic-control-${buildId}-`));
  const source = resolveControlPlaneSource(sourceRecord);
  const deps = buildDeps(tenantId);
  return runJob(
    { jobId: buildId, tenantId, workspace, source },
    { ...deps, states: new HTTPControlPlaneBuildSink(sourceRecord, controlPlane) },
  );
}

function verifySecret(provided: string | undefined, expected: string): boolean {
  if (!provided) return false;
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

async function reportControlPlaneBuildFailure(
  buildId: string,
  tenantId: string,
  controlPlane: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch },
  failureCode: string,
): Promise<void> {
  const fetchImpl = controlPlane.fetchImpl ?? fetch;
  const response = await fetchImpl(
    `${controlPlane.baseUrl.replace(/\/+$/, "")}/v1/internal/builds/${encodeURIComponent(buildId)}/failed`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": controlPlane.apiKey,
        "Idempotency-Key": `${buildId}:failed`,
      },
      body: JSON.stringify({ tenant_id: tenantId, failure_code: failureCode.slice(0, 128) }),
    },
  );
  if (!response.ok) {
    throw new Error(`Control-plane failure callback failed: ${response.status} ${await response.text()}`);
  }
}

/**
 * HTTP receiver for HTTPWebhookSiteMagicQueue's POST {job_id, tenant_id}
 * (site_magic_adapters.py:28-68), authenticated the same way that class
 * documents on its own side: X-Site-Magic-Secret, constant-time compare.
 * The webhook contract is fire-and-forget -- responds 202 immediately,
 * then pulls and runs the job asynchronously -- so a slow SiteMakerEngine
 * run never holds the HTTP connection open.
 */
export function startWebhookServer(options: {
  port: number;
  secret: string;
  controlPlaneBuildSecret?: string;
  buildDeps: DependencyFactory;
  controlPlane: { baseUrl: string; apiKey: string; fetchImpl?: typeof fetch };
  onJobSettled?: (
    jobId: string,
    result: { status: "ready_for_review" | "failed" | "quarantined"; buildId?: string } | { error: unknown }
  ) => void;
  onControlBuildSettled?: (
    buildId: string,
    result: { status: "ready_for_review" | "failed" | "quarantined"; buildId?: string } | { error: unknown }
  ) => void;
}): Server {
  const server = createServer((req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "POST") {
      res.writeHead(405).end();
      return;
    }
    const isControlPlaneBuild = (req.url ?? "").split("?", 1)[0] === "/control-plane/builds";
    const provided = req.headers["x-site-magic-secret"];
    const expectedSecret = isControlPlaneBuild ? options.controlPlaneBuildSecret : options.secret;
    if (!expectedSecret || !verifySecret(typeof provided === "string" ? provided : undefined, expectedSecret)) {
      res.writeHead(401).end();
      return;
    }
    let body = "";
    req.on("data", (chunk) => { body += chunk; });
    req.on("end", () => {
      let payload: { job_id?: unknown; build_id?: unknown; tenant_id?: unknown };
      try {
        payload = JSON.parse(body || "{}");
      } catch {
        res.writeHead(400).end();
        return;
      }
      const identifier = isControlPlaneBuild ? payload.build_id : payload.job_id;
      if (typeof identifier !== "string" || typeof payload.tenant_id !== "string") {
        res.writeHead(422).end();
        return;
      }
      res.writeHead(202).end();
      const jobId = identifier;
      const tenantId = payload.tenant_id;
      if (isControlPlaneBuild) {
        processControlPlaneBuild(jobId, tenantId, options.buildDeps, options.controlPlane)
          .then((result) => options.onControlBuildSettled?.(jobId, result))
          .catch(async (error) => {
            try {
              await reportControlPlaneBuildFailure(jobId, tenantId, options.controlPlane, "engine_dispatch_failed");
            } catch (callbackError) {
              console.error("[site-magic-worker] control-plane failure callback failed", callbackError);
            }
            options.onControlBuildSettled?.(jobId, { error });
          });
      } else {
        processJob(jobId, tenantId, options.buildDeps, options.controlPlane)
          .then((result) => options.onJobSettled?.(jobId, result))
          .catch((error) => options.onJobSettled?.(jobId, { error }));
      }
    });
  });
  server.listen(options.port);
  return server;
}

const isMainModule = process.argv[1] !== undefined && fileURLToPath(import.meta.url) === process.argv[1];
if (isMainModule) {
  const port = Number(process.env.SITE_MAGIC_WORKER_PORT ?? "8090");
  const secret = process.env.SITE_MAGIC_WORKER_WEBHOOK_SECRET;
  const controlPlaneBuildSecret = process.env.SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET;
  const baseUrl = process.env.SITE_MAGIC_API_BASE_URL;
  const apiKey = process.env.SITE_MAGIC_INTERNAL_API_KEY;
  if ((!secret && !controlPlaneBuildSecret) || !baseUrl || !apiKey) {
    throw new WorkerNotConfiguredError(
      "SITE_MAGIC_WORKER_WEBHOOK_SECRET or SITE_MAGIC_CONTROL_BUILD_WEBHOOK_SECRET, plus SITE_MAGIC_API_BASE_URL and SITE_MAGIC_INTERNAL_API_KEY, are required to start the worker."
    );
  }
  startWebhookServer({
    port,
    // The legacy route remains fail-closed when only the standalone
    // control-plane contract is configured. This lets the standalone worker
    // deploy without requiring an unrelated legacy job credential.
    secret: secret ?? "",
    controlPlaneBuildSecret,
    buildDeps: buildProductionDependencies,
    controlPlane: { baseUrl, apiKey },
    onJobSettled: (jobId, result) => {
      // `settled { status: 'failed' }` on its own is unactionable -- it was
      // all the worker said about the first real production job, which had
      // died on an OpenRouter 401. The engine now puts a redacted reason in
      // failure_code; surface it here too so the Railway log alone is enough.
      console.log(`[site-magic-worker] job ${jobId} settled`, result);
      if (result?.status === "failed" || result?.status === "quarantined") {
        console.error(
          `[site-magic-worker] job ${jobId} did not ship: ${result.failureCode ?? "no reason recorded"}`
        );
      }
    },
  });
  console.log(`[site-magic-worker] listening on :${port}`);
}
