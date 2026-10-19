import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { LocalArtifactStore, SyntheticImageGenerator } from "../webstaffr/site_magic_local.ts";
import { buildProductionDependencies } from "../webstaffr/site_magic_worker.ts";

test("SyntheticImageGenerator returns labeled private PNG data URIs", async () => {
  const images = await new SyntheticImageGenerator().generate({
    model: "local-synthetic",
    brief: "not used as a factual source",
    count: 3,
    briefs: [
      { role: "hero", aspectRatio: "16:9", prompt: "ignored", altText: "demo" },
      { role: "proof", aspectRatio: "4:3", prompt: "ignored", altText: "demo" },
      { role: "service", aspectRatio: "4:3", prompt: "ignored", altText: "demo" },
    ],
  });
  assert.equal(images.length, 3);
  assert.ok(images.every((image) => image.startsWith("data:image/png;base64,")));
});

test("LocalArtifactStore writes tenant-scoped immutable archives", async () => {
  const root = await mkdtemp(join(tmpdir(), "site-magic-artifacts-"));
  const workspace = await mkdtemp(join(tmpdir(), "site-magic-workspace-"));
  await writeFile(join(workspace, "index.html"), "<main>synthetic demo</main>");
  try {
    const store = new LocalArtifactStore(root);
    const args = { jobId: "job-1", tenantId: "demo-hvac-a", workspace, manifestSha256: "a".repeat(64) };
    const first = await store.sealPrivateImmutable(args);
    const archive = join(root, "demo-hvac-a", "job-1", `${first.buildId}.tar`);
    const before = await readFile(archive);
    await writeFile(join(workspace, "changed.txt"), "must not overwrite prior archive");
    const second = await store.sealPrivateImmutable(args);
    const after = await readFile(archive);
    assert.deepEqual(second, first);
    assert.deepEqual(after, before);
  } finally {
    await rm(root, { recursive: true, force: true });
    await rm(workspace, { recursive: true, force: true });
  }
});

test("LocalArtifactStore rejects path traversal segments", async () => {
  const root = await mkdtemp(join(tmpdir(), "site-magic-artifacts-"));
  const workspace = await mkdtemp(join(tmpdir(), "site-magic-workspace-"));
  try {
    await assert.rejects(() => new LocalArtifactStore(root).sealPrivateImmutable({
      jobId: "job-1", tenantId: "../other", workspace, manifestSha256: "a".repeat(64),
    }), /unsafe tenant id/);
  } finally {
    await rm(root, { recursive: true, force: true });
    await rm(workspace, { recursive: true, force: true });
  }
});

test("private demo flags select local artifacts and synthetic images", () => {
  const keys = [
    "SITE_MAGIC_USE_AI_COMPATIBLE", "SITE_MAGIC_USE_SYNTHETIC_ASSETS",
    "SITE_MAGIC_USE_LOCAL_ARTIFACTS", "SITE_MAGIC_API_BASE_URL", "SITE_MAGIC_INTERNAL_API_KEY",
  ];
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  Object.assign(process.env, {
    SITE_MAGIC_USE_AI_COMPATIBLE: "true",
    SITE_MAGIC_USE_SYNTHETIC_ASSETS: "true",
    SITE_MAGIC_USE_LOCAL_ARTIFACTS: "true",
    SITE_MAGIC_API_BASE_URL: "http://127.0.0.1:8000",
    SITE_MAGIC_INTERNAL_API_KEY: "local-demo-only",
  });
  try {
    const deps = buildProductionDependencies("demo-hvac-a");
    assert.ok(deps.images instanceof SyntheticImageGenerator);
    assert.ok(deps.artifacts instanceof LocalArtifactStore);
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
});
