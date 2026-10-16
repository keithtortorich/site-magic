/**
 * OpenAI-compatible Site Magic adapters.
 *
 * Code generation deliberately delegates to the established OpenRouter
 * runtime because that runtime already implements role constraints, safe
 * workspace writes, response repair, and split-file generation. Only the
 * endpoint, credential, and model defaults differ here.
 */

import type { ImageBrief, ImageGenerator } from "./site_maker_engine.ts";
import { isIP } from "node:net";
import {
  CodexRuntimeNotConfiguredError,
  OpenRouterCodegenRuntime,
  type WorkspaceFs,
} from "./site_magic_codegen_runtime.ts";

export { CodexRuntimeNotConfiguredError };
export class ImageGeneratorNotConfiguredError extends Error {}

function isLoopbackEndpoint(baseUrl: string): boolean {
  try {
    const hostname = new URL(baseUrl).hostname.toLowerCase();
    const unwrappedHostname = hostname.replace(/^\[|\]$/g, "");
    return (
      hostname === "localhost" ||
      hostname.endsWith(".localhost") ||
      (isIP(unwrappedHostname) === 4 && unwrappedHostname.split(".")[0] === "127") ||
      unwrappedHostname === "::1"
    );
  } catch {
    return false;
  }
}

export function resolveOpenAICompatibleChatConfig(opts?: {
  apiKey?: string;
  model?: string;
  baseUrl?: string;
}): { apiKey: string; model: string; baseUrl: string } {
  const baseUrl = (
    opts?.baseUrl ??
    process.env.OPENAI_COMPATIBLE_BASE_URL ??
    "http://localhost:11434/v1"
  ).replace(/\/+$/, "");
  const configuredKey = opts?.apiKey ?? process.env.OPENAI_COMPATIBLE_API_KEY;
  const apiKey = configuredKey ?? (isLoopbackEndpoint(baseUrl) ? "dummy" : "");
  const model = opts?.model ?? process.env.OPENAI_COMPATIBLE_MODEL ?? "llama3.1:8b";

  if (!apiKey) {
    throw new CodexRuntimeNotConfiguredError(
      "OpenAICompatibleCodegenRuntime requires OPENAI_COMPATIBLE_API_KEY for non-local endpoints."
    );
  }
  return { apiKey, model, baseUrl };
}

export class OpenAICompatibleCodegenRuntime extends OpenRouterCodegenRuntime {
  private readonly compatibleModel: string;

  constructor(opts?: {
    apiKey?: string;
    model?: string;
    baseUrl?: string;
    fetchImpl?: typeof global.fetch;
    fs?: WorkspaceFs;
  }) {
    const { apiKey, model, baseUrl } = resolveOpenAICompatibleChatConfig(opts);

    super({
      apiKey,
      model,
      baseUrl,
      fetchImpl: opts?.fetchImpl,
      fs: opts?.fs,
    });
    this.compatibleModel = model;
  }

  async run(args: {
    role: string;
    workspace: string;
    instructions: string;
    model?: string;
    imageDataUrls?: string[];
    splitFiles?: boolean;
  }): Promise<Record<string, unknown>> {
    return super.run({ ...args, model: this.compatibleModel });
  }
}

/**
 * Image adapter for endpoints implementing OpenAI's images/generations
 * response shape. It accepts only inline b64_json results so private build
 * inputs never depend on a provider-hosted URL remaining available.
 */
export class OpenAICompatibleImageGenerator implements ImageGenerator {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly model: string;
  private readonly fetchImpl: typeof fetch;

  constructor(opts?: {
    apiKey?: string;
    baseUrl?: string;
    model?: string;
    fetchImpl?: typeof fetch;
  }) {
    this.baseUrl = (
      opts?.baseUrl ??
      process.env.OPENAI_COMPATIBLE_BASE_URL ??
      "http://localhost:11434/v1"
    ).replace(/\/+$/, "");
    const configuredKey = opts?.apiKey ?? process.env.OPENAI_COMPATIBLE_API_KEY;
    this.apiKey = configuredKey ?? (isLoopbackEndpoint(this.baseUrl) ? "dummy" : "");
    this.fetchImpl = opts?.fetchImpl ?? fetch;

    if (!this.apiKey) {
      throw new ImageGeneratorNotConfiguredError(
        "OpenAICompatibleImageGenerator requires OPENAI_COMPATIBLE_API_KEY for non-local endpoints."
      );
    }
    const configuredModel = opts?.model ?? process.env.OPENAI_COMPATIBLE_IMAGE_MODEL;
    if (!configuredModel?.trim()) {
      throw new ImageGeneratorNotConfiguredError(
        "OpenAICompatibleImageGenerator requires OPENAI_COMPATIBLE_IMAGE_MODEL."
      );
    }
    this.model = configuredModel.trim();
  }

  async generate(args: {
    model: string;
    brief: string;
    count: 3;
    briefs?: readonly ImageBrief[];
  }): Promise<string[]> {
    const endpoint = `${this.baseUrl}/images/generations`;
    const images: string[] = [];

    for (let i = 0; i < args.count; i += 1) {
      const brief = args.briefs?.[i] ?? {
        role: i === 0 ? "hero" : "service",
        aspectRatio: i === 0 ? "16:9" : "4:3",
        prompt: args.brief,
        altText: "",
      };
      const response = await this.fetchImpl(endpoint, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model: this.model,
          prompt: brief.prompt,
          n: 1,
          size: brief.aspectRatio === "16:9" ? "1536x1024" : "1024x1024",
          response_format: "b64_json",
        }),
      });

      if (!response.ok) {
        throw new Error(
          `OpenAI-compatible image generation failed: ${response.status} ${await response.text()}`
        );
      }

      const data = (await response.json()) as { data?: Array<{ b64_json?: string }> };
      const encoded = data.data?.[0]?.b64_json;
      if (!encoded) {
        throw new Error("OpenAI-compatible image generation returned no b64_json");
      }
      images.push(`data:image/png;base64,${encoded}`);
    }

    return images;
  }
}
