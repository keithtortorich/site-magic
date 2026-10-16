/**
 * Real (non-Null) implementations of the CodexRuntime, ImageGenerator, and
 * ArtifactStore interfaces from site_maker_engine.ts. Same Protocol/Null
 * real-implementation shape as the Python integrations in this repo (see
 * webstaffr/integrations/design_critique/client.py) -- env-driven
 * constructors that raise a *NotConfiguredError eagerly rather than
 * failing later, silently.
 *
 * None of these have been run against live credentials: no OPENAI_API_KEY
 * exists yet and GPT Image organization access is unapproved (see
 * docs/STANDUP_2026-08-09_IMPECCABLE_PHASE_1.md). They're unit-tested
 * against fakes only.
 *
 * OpenRouterImageGenerator uses OpenRouter's dedicated Image API with the
 * existing OPENROUTER_API_KEY. Each editorial role can request its own
 * aspect ratio and prompt; the response is the stable b64_json image shape.
 */

import { randomUUID } from "node:crypto";
import OpenAI from "openai";
import { Codex } from "@openai/codex-sdk";
import type {
  ArtifactStore,
  CodexRuntime,
  ImageGenerator,
  ImageBrief,
  JobState,
  JobStateSink,
} from "./site_maker_engine.ts";

export class CodexRuntimeNotConfiguredError extends Error {}
export class ImageGeneratorNotConfiguredError extends Error {}
export class ArtifactStoreNotConfiguredError extends Error {}
export class JobStateSinkNotConfiguredError extends Error {}

/**
 * Wraps @openai/codex-sdk. One thread per role invocation -- each
 * CodexRuntime.run() call in SiteMakerEngine is a self-contained step
 * (product, direction, builder, ...), not a multi-turn conversation, so a
 * fresh thread per call keeps steps isolated rather than accumulating
 * unrelated context across roles.
 */
export class OpenAICodexRuntime implements CodexRuntime {
  private readonly codex: Codex;

  constructor(apiKey?: string) {
    const key = apiKey ?? process.env.OPENAI_API_KEY;
    if (!key) {
      throw new CodexRuntimeNotConfiguredError(
        "OpenAICodexRuntime requires OPENAI_API_KEY (env var or constructor arg)."
      );
    }
    this.codex = new Codex({ apiKey: key });
  }

  async run(args: {
    role: string;
    model: string;
    workspace: string;
    instructions: string;
    imageDataUrls?: string[];
  }): Promise<Record<string, unknown>> {
    const thread = this.codex.startThread({
      model: args.model,
      workingDirectory: args.workspace,
      sandboxMode: "workspace-write",
      // The worker's own container/network policy is the actual SSRF/exfil
      // boundary (see docs/site_magic security posture) -- this flag only
      // controls whether Codex's sandbox permits outbound network calls at
      // all, and a design/build step never needs the internet.
      networkAccessEnabled: false,
    });
    const turn = await thread.run(args.instructions);
    return { role: args.role, finalResponse: turn.finalResponse, items: turn.items };
  }
}

/**
 * Wraps the openai Node SDK's Images API for gpt-image-* models. Returns
 * each comp as a self-contained data: URI (gpt-image-* responses are
 * b64_json, not hosted URLs) -- the caller doesn't need a second fetch or
 * a place to host an intermediate file to use the result.
 */
export class OpenAIImageGenerator implements ImageGenerator {
  private readonly client: OpenAI;

  constructor(apiKey?: string, fetchImpl?: typeof fetch) {
    const key = apiKey ?? process.env.OPENAI_API_KEY;
    if (!key) {
      throw new ImageGeneratorNotConfiguredError(
        "OpenAIImageGenerator requires OPENAI_API_KEY (env var or constructor arg)."
      );
    }
    // fetchImpl is a test seam (the SDK captures whatever fetch it's given
    // at construction time, so a global monkeypatch after construction
    // wouldn't affect it) -- production callers never pass it.
    this.client = new OpenAI({ apiKey: key, fetch: fetchImpl });
  }

  async generate(args: { model: string; brief: string; count: 3; briefs?: readonly ImageBrief[] }): Promise<string[]> {
    const response = await this.client.images.generate({
      model: args.model,
      prompt: args.brief,
      n: args.count,
      size: "1536x1024",
    });
    const data = response.data ?? [];
    if (data.length !== args.count) {
      throw new Error(
        `Expected ${args.count} image comps from ${args.model}, got ${data.length}`
      );
    }
    return data.map((item) => {
      if (!item.b64_json) {
        throw new Error(`${args.model} response item missing b64_json`);
      }
      return `data:image/png;base64,${item.b64_json}`;
    });
  }
}

/**
 * Wraps OpenRouter's dedicated Image API for image-output-capable models.
 * Same OPENROUTER_API_KEY as design_critique/client.py -- no separate
 * vendor account, and unblocked by OpenAI's GPT Image org-approval gate.
 *
 * The model supports n=1, so the adapter issues one request per editorial
 * role. SiteMakerEngine normalizes each returned raster to bounded WebP.
 */
export class OpenRouterImageGenerator implements ImageGenerator {
  private readonly apiKey: string;
  private readonly fetchImpl: typeof fetch;

  static readonly API_URL = "https://openrouter.ai/api/v1/images";

  constructor(apiKey?: string, fetchImpl?: typeof fetch) {
    const key = apiKey ?? process.env.OPENROUTER_API_KEY;
    if (!key) {
      throw new ImageGeneratorNotConfiguredError(
        "OpenRouterImageGenerator requires OPENROUTER_API_KEY (env var or constructor arg)."
      );
    }
    this.apiKey = key;
    this.fetchImpl = fetchImpl ?? fetch;
  }

  async generate(args: { model: string; brief: string; count: 3; briefs?: readonly ImageBrief[] }): Promise<string[]> {
    const images: string[] = [];
    const briefs = args.briefs ?? Array.from({ length: args.count }, (_, index) => ({
      role: index === 0 ? "hero" : index === 1 ? "proof" : "service",
      aspectRatio: index === 0 ? "16:9" : "4:3",
      prompt: args.brief,
      altText: "",
    }));
    for (let i = 0; i < args.count; i += 1) {
      const brief = briefs[i];
      const response = await this.fetchImpl(OpenRouterImageGenerator.API_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "https://netbuild.pro",
          "X-Title": "NetBuild.Pro Site Magic",
        },
        body: JSON.stringify({
          model: args.model,
          prompt: brief.prompt,
          n: 1,
          aspect_ratio: brief.aspectRatio,
        }),
      });
      if (!response.ok) {
        throw new Error(
          `OpenRouter image call ${i + 1}/${args.count} failed: ${response.status} ${await response.text()}`
        );
      }
      const data = (await response.json()) as { data?: Array<{ b64_json?: string; media_type?: string }> };
      const image = data.data?.[0];
      if (!image?.b64_json) {
        throw new Error(
          `OpenRouter image call ${i + 1}/${args.count} for ${args.model} returned no b64_json image`
        );
      }
      images.push(`data:${image.media_type ?? "image/png"};base64,${image.b64_json}`);
    }
    return images;
  }
}

/**
 * Seals a job's workspace into Supabase Storage's private bucket.
 *
 * Storage layout: `{tenantId}/{jobId}/{buildId}.tar` under the configured
 * bucket, uploaded via Supabase Storage's REST API directly (no supabase-js
 * dependency -- this repo's convention throughout is a bare httpx/fetch
 * call per external service rather than a client SDK; see
 * design_critique/client.py's module docstring for the same reasoning
 * applied to OpenRouter).
 *
 * This seals bytes; it does not decide what "publish" means for a live
 * site (custom domain routing, CDN, etc.) -- that's
 * webstaffr/site_magic_adapters.py's SupabaseArtifactStorage.publish(),
 * a separate, Python-side concern since it's driven by the tenant-scoped
 * control-plane API, not the worker.
 */
export class SupabaseArtifactStore implements ArtifactStore {
  private readonly baseUrl: string;
  private readonly serviceKey: string;
  private readonly bucket: string;

  constructor(options?: { baseUrl?: string; serviceKey?: string; bucket?: string }) {
    const baseUrl = options?.baseUrl ?? process.env.SUPABASE_URL;
    const serviceKey = options?.serviceKey ?? process.env.SITE_MAGIC_STORAGE_SERVICE_KEY;
    if (!baseUrl || !serviceKey) {
      throw new ArtifactStoreNotConfiguredError(
        "SupabaseArtifactStore requires SUPABASE_URL and SITE_MAGIC_STORAGE_SERVICE_KEY."
      );
    }
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.serviceKey = serviceKey;
    this.bucket = options?.bucket ?? process.env.SITE_MAGIC_STORAGE_BUCKET ?? "site-magic-builds";
  }

  async sealPrivateImmutable(args: {
    jobId: string;
    tenantId: string;
    workspace: string;
    manifestSha256: string;
  }): Promise<{ buildId: string }> {
    const buildId = args.manifestSha256.slice(0, 32);
    const objectPath = `${args.tenantId}/${args.jobId}/${buildId}.tar`;
    const { readFile } = await import("node:fs/promises");
    const { spawnSync } = await import("node:child_process");
    const { join } = await import("node:path");
    const tarPath = join(args.workspace, `.${buildId}.tar`);
    // tar the workspace rather than shipping a directory tree over HTTP one
    // file at a time -- one PUT, one object, matches "immutable bundle".
    const tarResult = spawnSync("tar", ["-cf", tarPath, "-C", args.workspace, "."]);
    if (tarResult.status !== 0) {
      throw new Error(`tar failed sealing workspace: ${tarResult.stderr?.toString()}`);
    }
    const bytes = await readFile(tarPath);

    const response = await fetch(
      `${this.baseUrl}/storage/v1/object/${this.bucket}/${objectPath}`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.serviceKey}`,
          apikey: this.serviceKey,
          "Content-Type": "application/x-tar",
          "x-upsert": "false", // immutable: never overwrite an existing build
        },
        body: bytes,
      }
    );
    if (!response.ok) {
      throw new Error(
        `Supabase Storage upload failed: ${response.status} ${await response.text()}`
      );
    }
    return { buildId };
  }
}

/**
 * Reports SiteMakerEngine's state-machine transitions back to the Python
 * control plane (site_magic_router.py's POST
 * /site-magic/internal/jobs/{jobId}/transition), authenticated the same
 * way as every other internal-to-internal call in this repo (X-API-Key,
 * SharedSecretVerifier -- see webstaffr/workers/angel/api_auth.py).
 *
 * Idempotency / staleness: this class does not itself dedupe retried
 * calls -- it relies entirely on the server's optimistic-concurrency guard
 * (SiteMagicRepository.transition()'s `WHERE status = <expected prior
 * status>`, which the server derives from its own current row, not from
 * anything this client sends). A retried call for a transition that
 * already landed will get back the *current* status, which now
 * disagrees with the expected prior status, and the server correctly
 * rejects it as "changed concurrently" (409) rather than double-applying
 * it. What this class does NOT yet have, and should before this runs
 * against a real worker queue with real retries: a per-attempt
 * correlation ID and monotonic event sequence so a caller can tell "already
 * applied, no-op" apart from "genuinely stale, reject" instead of both
 * surfacing as the same 409. Tracked as a known gap, not silently assumed
 * solved.
 *
 * ready_for_review is special-cased: metadata.buildId (all
 * SiteMakerEngine ever has -- see sealPrivateImmutable()'s return type)
 * is expanded into the build_id/artifact_manifest/preview_locator triple
 * the server's seal_build_and_advance() needs, using the exact same
 * `{tenantId}/{jobId}/{buildId}.tar` object-path convention
 * SupabaseArtifactStore uses to write it. If that convention ever
 * changes, it has to change in both places.
 */
export class HTTPJobStateSink implements JobStateSink {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly callbackUrl?: string;
  private readonly callbackSecret?: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options?: {
    baseUrl?: string;
    apiKey?: string;
    callbackUrl?: string;
    callbackSecret?: string;
    fetchImpl?: typeof fetch;
  }) {
    const baseUrl = options?.baseUrl ?? process.env.SITE_MAGIC_API_BASE_URL;
    const apiKey = options?.apiKey ?? process.env.SITE_MAGIC_INTERNAL_API_KEY;
    if (!baseUrl || !apiKey) {
      throw new JobStateSinkNotConfiguredError(
        "HTTPJobStateSink requires SITE_MAGIC_API_BASE_URL and SITE_MAGIC_INTERNAL_API_KEY."
      );
    }
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.apiKey = apiKey;
    this.callbackUrl = options?.callbackUrl ?? process.env.SITE_MAGIC_CALLBACK_WEBHOOK_URL;
    this.callbackSecret = options?.callbackSecret ?? process.env.SITE_MAGIC_CALLBACK_SECRET;
    this.fetchImpl = options?.fetchImpl ?? fetch;
  }

  async transition(
    jobId: string,
    tenantId: string,
    state: JobState,
    metadata?: Record<string, unknown>,
    eventId?: string
  ): Promise<void> {
    // eventId defaults to a fresh UUID per call. It's an optional 5th
    // param (not part of the JobStateSink interface -- SiteMakerEngine
    // never passes one) so a *retry wrapper* around this call can supply
    // the same eventId on a resend and get idempotent replay from the
    // server instead of a stale-state 409. This method itself does not
    // retry -- the site_magic_job_events ledger is only as useful as
    // whatever retries with the same ID.
    const body: Record<string, unknown> = {
      tenant_id: tenantId, target: state, event_id: eventId ?? randomUUID(),
    };
    if (metadata?.remediationRounds !== undefined) body.remediation_rounds = metadata.remediationRounds;
    if (metadata?.rebuilds !== undefined) body.rebuild_count = metadata.rebuilds;
    if (typeof metadata?.reason === "string") body.failure_code = metadata.reason;
    if (typeof metadata?.errorType === "string") body.failure_code = metadata.errorType;
    if (typeof metadata?.buildId === "string") {
      const buildId = metadata.buildId;
      body.build_id = buildId;
      body.preview_locator = `${tenantId}/${jobId}/${buildId}.tar`;
      body.artifact_manifest = { jobId, tenantId, buildId };
    }
    if (metadata?.report && typeof metadata.report === "object") {
      body.quality_summary = metadata.report;
    }

    const response = await this.fetchImpl(`${this.baseUrl}/site-magic/internal/jobs/${jobId}/transition`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": this.apiKey },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(
        `Site Magic state transition failed: ${response.status} ${await response.text()}`
      );
    }

    // Fire webhook callback to SMMM listener (non-blocking, best-effort)
    // ADR-027: Worker callback protocol for SMMM to track job progress
    if (this.callbackUrl && this.callbackSecret) {
      const eventId = body.event_id as string;
      const callbackPayload: Record<string, unknown> = {
        eventId,
        jobId,
        status: state,
        timestamp: new Date().toISOString(),
      };

      // Add optional fields based on state and metadata
      if (state === "ready_for_review" || state === "shipped") {
        if (typeof metadata?.buildId === "string") {
          callbackPayload.buildId = metadata.buildId;
        }
        callbackPayload.previewUrl = `https://sites.${process.env.SITE_DOMAIN ?? "netbuild.pro"}/${tenantId}/`;
      }

      if (state === "failed") {
        if (typeof metadata?.reason === "string") {
          callbackPayload.errorCode = metadata.reason;
          callbackPayload.errorMessage = `Build failed: ${metadata.reason}`;
        }
      }

      if (typeof metadata?.critiqueScore === "number" || typeof metadata?.p0Issues === "number") {
        callbackPayload.qualityMetrics = {
          critiqueScore: metadata?.critiqueScore,
          p0Issues: metadata?.p0Issues,
          selfHealIterations: metadata?.rebuilds ?? 0,
        };
      }

      // Fire webhook asynchronously (non-blocking)
      this.fireWebhook(jobId, callbackPayload).catch((err) => {
        console.error(`Site Magic callback webhook failed for job ${jobId}:`, err);
      });
    }
  }

  private async fireWebhook(jobId: string, payload: Record<string, unknown>): Promise<void> {
    if (!this.callbackUrl || !this.callbackSecret) {
      return;
    }

    // Constant-time comparison of the secret (prevent timing attacks)
    const bodyStr = JSON.stringify(payload);
    const bodyBytes = new TextEncoder().encode(bodyStr);
    const secretBytes = new TextEncoder().encode(this.callbackSecret);

    // Simple HMAC-SHA256 signature (follow Stripe webhook pattern)
    const crypto = await import("node:crypto");
    const hmac = crypto.createHmac("sha256", secretBytes);
    hmac.update(bodyBytes);
    const signature = hmac.digest("hex");

    try {
      const response = await this.fetchImpl(this.callbackUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Site-Magic-Secret": signature,
        },
        body: bodyStr,
      });

      if (!response.ok) {
        console.warn(
          `Site Magic callback returned ${response.status} for job ${jobId}: ${await response.text()}`
        );
      }
    } catch (err) {
      console.error(`Site Magic callback network error for job ${jobId}:`, err);
      // Do not throw; callback is best-effort
    }
  }
}
