/** Local-only adapters for the VRE synthetic demo.
 *
 * These adapters intentionally do not publish or call a hosted provider:
 * local model inference remains OpenAI-compatible (Ollama/llama.cpp/vLLM),
 * images are deterministic illustrative assets, and build bundles are sealed
 * beneath a tenant-scoped private directory.
 */
import { access, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import sharp from "sharp";
import type { ArtifactStore, ImageBrief, ImageGenerator } from "./site_maker_engine.ts";

function safeSegment(value: string, label: string): string {
  if (!/^[a-zA-Z0-9._-]+$/.test(value) || value === "." || value === "..") {
    throw new Error(`unsafe ${label}`);
  }
  return value;
}

/** Seals build output to local storage using the same tenant/job/build layout
 * as the hosted artifact adapter. Existing archives are never overwritten. */
export class LocalArtifactStore implements ArtifactStore {
  private readonly root: string;

  constructor(root = process.env.SITE_MAGIC_LOCAL_ARTIFACT_DIR ?? join(process.cwd(), "artifacts", "runtime")) {
    this.root = root;
  }

  async sealPrivateImmutable(args: {
    jobId: string;
    tenantId: string;
    workspace: string;
    manifestSha256: string;
  }): Promise<{ buildId: string }> {
    const tenantId = safeSegment(args.tenantId, "tenant id");
    const jobId = safeSegment(args.jobId, "job id");
    const buildId = args.manifestSha256.slice(0, 32);
    if (!/^[a-f0-9]{32}$/.test(buildId)) throw new Error("manifestSha256 must produce a hexadecimal build id");
    const directory = join(this.root, tenantId, jobId);
    const archive = join(directory, `${buildId}.tar`);
    await mkdir(directory, { recursive: true });
    try {
      await access(archive);
      return { buildId };
    } catch {
      // The immutable archive does not exist yet.
    }
    const result = spawnSync("tar", ["-cf", archive, "-C", args.workspace, "."], { encoding: "utf-8" });
    if (result.status !== 0) throw new Error(`local tar failed: ${result.stderr || "unknown error"}`);
    return { buildId };
  }
}

function escapeXml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;",
  }[character] ?? character));
}

/** Generates clearly labeled deterministic artwork for private synthetic
 * previews. It removes the image-provider dependency without pretending that
 * a generated asset is a real customer photograph or proof point. */
export class SyntheticImageGenerator implements ImageGenerator {
  async generate(args: {
    model: string;
    brief: string;
    count: 3;
    briefs?: readonly ImageBrief[];
  }): Promise<string[]> {
    const images: string[] = [];
    for (let index = 0; index < args.count; index += 1) {
      const role = args.briefs?.[index]?.role ?? (index === 0 ? "hero" : index === 1 ? "proof" : "service");
      const width = role === "hero" ? 1536 : 1200;
      const height = role === "hero" ? 1024 : 900;
      const label = escapeXml(`ILLUSTRATIVE DEMO · ${role.toUpperCase()}`);
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#123c52"/><stop offset="1" stop-color="#d28b4d"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><circle cx="${Math.round(width * 0.72)}" cy="${Math.round(height * 0.32)}" r="${Math.round(Math.min(width, height) * 0.2)}" fill="#f5d6a5" opacity=".25"/><path d="M0 ${Math.round(height * 0.78)} C ${Math.round(width * 0.26)} ${Math.round(height * 0.62)}, ${Math.round(width * 0.58)} ${Math.round(height * 0.94)}, ${width} ${Math.round(height * 0.58)} L ${width} ${height} L0 ${height}Z" fill="#071f2b" opacity=".55"/><text x="64" y="${height - 76}" fill="#fff" font-family="Arial,sans-serif" font-size="32" letter-spacing="2">${label}</text></svg>`;
      const png = await sharp(Buffer.from(svg)).png().toBuffer();
      images.push(`data:image/png;base64,${png.toString("base64")}`);
    }
    return images;
  }
}

