import test from "node:test";
import assert from "node:assert/strict";
import {
  CodexRuntimeNotConfiguredError,
  ImageGeneratorNotConfiguredError,
  ArtifactStoreNotConfiguredError,
  JobStateSinkNotConfiguredError,
  OpenAICodexRuntime,
  OpenAIImageGenerator,
  OpenRouterImageGenerator,
  SupabaseArtifactStore,
  HTTPJobStateSink,
} from "../webstaffr/site_magic_adapters.ts";

test("OpenAICodexRuntime throws CodexRuntimeNotConfiguredError with no api key", () => {
  const previous = process.env.OPENAI_API_KEY;
  delete process.env.OPENAI_API_KEY;
  try {
    assert.throws(() => new OpenAICodexRuntime(), CodexRuntimeNotConfiguredError);
  } finally {
    if (previous !== undefined) process.env.OPENAI_API_KEY = previous;
  }
});

test("OpenAICodexRuntime accepts an explicit api key without touching env", () => {
  const previous = process.env.OPENAI_API_KEY;
  delete process.env.OPENAI_API_KEY;
  try {
    assert.doesNotThrow(() => new OpenAICodexRuntime("explicit-key"));
  } finally {
    if (previous !== undefined) process.env.OPENAI_API_KEY = previous;
  }
});

test("OpenAIImageGenerator throws ImageGeneratorNotConfiguredError with no api key", () => {
  const previous = process.env.OPENAI_API_KEY;
  delete process.env.OPENAI_API_KEY;
  try {
    assert.throws(() => new OpenAIImageGenerator(), ImageGeneratorNotConfiguredError);
  } finally {
    if (previous !== undefined) process.env.OPENAI_API_KEY = previous;
  }
});

test("OpenAIImageGenerator.generate returns exactly the requested count as data URIs", async () => {
  const stubFetch = (async () =>
    new Response(
      JSON.stringify({
        created: 1,
        data: [{ b64_json: "AAA" }, { b64_json: "BBB" }, { b64_json: "CCC" }],
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    )) as typeof fetch;
  const generator = new OpenAIImageGenerator("test-key", stubFetch);
  const comps = await generator.generate({ model: "gpt-image-2", brief: "a plumbing brand", count: 3 });
  assert.equal(comps.length, 3);
  for (const comp of comps) {
    assert.match(comp, /^data:image\/png;base64,/);
  }
});

test("OpenAIImageGenerator.generate rejects a response with the wrong comp count", async () => {
  const stubFetch = (async () =>
    new Response(
      JSON.stringify({ created: 1, data: [{ b64_json: "AAA" }] }),
      { status: 200, headers: { "content-type": "application/json" } }
    )) as typeof fetch;
  const generator = new OpenAIImageGenerator("test-key", stubFetch);
  await assert.rejects(() =>
    generator.generate({ model: "gpt-image-2", brief: "a plumbing brand", count: 3 })
  );
});

test("OpenRouterImageGenerator throws ImageGeneratorNotConfiguredError with no api key", () => {
  const previous = process.env.OPENROUTER_API_KEY;
  delete process.env.OPENROUTER_API_KEY;
  try {
    assert.throws(() => new OpenRouterImageGenerator(), ImageGeneratorNotConfiguredError);
  } finally {
    if (previous !== undefined) process.env.OPENROUTER_API_KEY = previous;
  }
});

test("OpenRouterImageGenerator.generate returns exactly the requested count as data URIs, one call per comp", async () => {
  let calls = 0;
  const stubFetch = (async () => {
    calls += 1;
    return new Response(
      JSON.stringify({
        data: [{ b64_json: `COMP${calls}` }],
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  }) as typeof fetch;
  const generator = new OpenRouterImageGenerator("test-key", stubFetch);
  const comps = await generator.generate({
    model: "google/gemini-2.5-flash-image",
    brief: "a plumbing brand",
    count: 3,
  });
  assert.equal(comps.length, 3);
  assert.equal(calls, 3);
  for (const comp of comps) {
    assert.match(comp, /^data:image\/png;base64,/);
  }
});

test("OpenRouterImageGenerator.generate uses the dedicated Image API and editorial aspect ratios", async () => {
  const bodies: string[] = [];
  const stubFetch = (async (_url: string, init: RequestInit) => {
    bodies.push(init.body as string);
    return new Response(
      JSON.stringify({ data: [{ b64_json: "X" }] }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  }) as typeof fetch;
  const generator = new OpenRouterImageGenerator("test-key", stubFetch);
  await generator.generate({
    model: "google/gemini-2.5-flash-image", brief: "a plumbing brand", count: 3,
    briefs: [
      { role: "hero", aspectRatio: "16:9", prompt: "wide hero", altText: "hero" },
      { role: "proof", aspectRatio: "4:3", prompt: "proof detail", altText: "proof" },
      { role: "service", aspectRatio: "4:3", prompt: "service detail", altText: "service" },
    ],
  });

  assert.deepEqual(bodies.map((raw) => JSON.parse(raw).aspect_ratio), ["16:9", "4:3", "4:3"]);
  assert.deepEqual(bodies.map((raw) => JSON.parse(raw).prompt), ["wide hero", "proof detail", "service detail"]);
  assert.ok(bodies.every((raw) => JSON.parse(raw).n === 1));
});

test("OpenRouterImageGenerator.generate rejects when a response has no image part", async () => {
  const stubFetch = (async () =>
    new Response(
      JSON.stringify({ data: [{}] }),
      { status: 200, headers: { "content-type": "application/json" } }
    )) as typeof fetch;
  const generator = new OpenRouterImageGenerator("test-key", stubFetch);
  await assert.rejects(() =>
    generator.generate({ model: "google/gemini-2.5-flash-image", brief: "a plumbing brand", count: 3 })
  );
});

test("OpenRouterImageGenerator.generate rejects on a non-ok HTTP response", async () => {
  const stubFetch = (async () =>
    new Response("rate limited", { status: 429 })) as typeof fetch;
  const generator = new OpenRouterImageGenerator("test-key", stubFetch);
  await assert.rejects(() =>
    generator.generate({ model: "google/gemini-2.5-flash-image", brief: "a plumbing brand", count: 3 })
  );
});

test("SupabaseArtifactStore throws ArtifactStoreNotConfiguredError with no credentials", () => {
  const prevUrl = process.env.SUPABASE_URL;
  const prevKey = process.env.SITE_MAGIC_STORAGE_SERVICE_KEY;
  delete process.env.SUPABASE_URL;
  delete process.env.SITE_MAGIC_STORAGE_SERVICE_KEY;
  try {
    assert.throws(() => new SupabaseArtifactStore(), ArtifactStoreNotConfiguredError);
  } finally {
    if (prevUrl !== undefined) process.env.SUPABASE_URL = prevUrl;
    if (prevKey !== undefined) process.env.SITE_MAGIC_STORAGE_SERVICE_KEY = prevKey;
  }
});

test("SupabaseArtifactStore.sealPrivateImmutable uploads a tar and returns a build id derived from the manifest hash", async () => {
  const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const workspace = await mkdtemp(join(tmpdir(), "site-magic-test-"));
  await writeFile(join(workspace, "index.html"), "<html></html>");

  const store = new SupabaseArtifactStore({
    baseUrl: "https://example.supabase.co",
    serviceKey: "service-role-key",
    bucket: "site-magic-builds",
  });

  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init: RequestInit }> = [];
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response("", { status: 200 });
  }) as typeof fetch;

  try {
    const result = await store.sealPrivateImmutable({
      jobId: "job_1",
      tenantId: "acme_hvac",
      workspace,
      manifestSha256: "a".repeat(64),
    });
    assert.equal(result.buildId, "a".repeat(32));
    assert.equal(calls.length, 1);
    assert.match(calls[0].url, /^https:\/\/example\.supabase\.co\/storage\/v1\/object\/site-magic-builds\/acme_hvac\/job_1\/a{32}\.tar$/);
    assert.equal((calls[0].init.headers as Record<string, string>)["x-upsert"], "false");
  } finally {
    globalThis.fetch = originalFetch;
    await rm(workspace, { recursive: true, force: true });
  }
});

test("SupabaseArtifactStore.sealPrivateImmutable throws on a failed upload", async () => {
  const { mkdtemp, writeFile, rm } = await import("node:fs/promises");
  const { tmpdir } = await import("node:os");
  const { join } = await import("node:path");

  const workspace = await mkdtemp(join(tmpdir(), "site-magic-test-"));
  await writeFile(join(workspace, "index.html"), "<html></html>");

  const store = new SupabaseArtifactStore({
    baseUrl: "https://example.supabase.co",
    serviceKey: "service-role-key",
  });

  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response("conflict", { status: 409 })) as typeof fetch;

  try {
    await assert.rejects(() =>
      store.sealPrivateImmutable({
        jobId: "job_1", tenantId: "acme_hvac", workspace, manifestSha256: "b".repeat(64),
      })
    );
  } finally {
    globalThis.fetch = originalFetch;
    await rm(workspace, { recursive: true, force: true });
  }
});

test("HTTPJobStateSink throws JobStateSinkNotConfiguredError with no config", () => {
  const prevUrl = process.env.SITE_MAGIC_API_BASE_URL;
  const prevKey = process.env.SITE_MAGIC_INTERNAL_API_KEY;
  delete process.env.SITE_MAGIC_API_BASE_URL;
  delete process.env.SITE_MAGIC_INTERNAL_API_KEY;
  try {
    assert.throws(() => new HTTPJobStateSink(), JobStateSinkNotConfiguredError);
  } finally {
    if (prevUrl !== undefined) process.env.SITE_MAGIC_API_BASE_URL = prevUrl;
    if (prevKey !== undefined) process.env.SITE_MAGIC_INTERNAL_API_KEY = prevKey;
  }
});

test("HTTPJobStateSink.transition posts target and api key header", async () => {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchImpl = (async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({
    baseUrl: "https://api.netbuild.pro",
    apiKey: "internal-key",
    fetchImpl,
  });
  await sink.transition("job_1", "acme_hvac", "ingesting");

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://api.netbuild.pro/site-magic/internal/jobs/job_1/transition");
  assert.equal((calls[0].init.headers as Record<string, string>)["X-API-Key"], "internal-key");
  const body = JSON.parse(calls[0].init.body as string);
  assert.equal(body.tenant_id, "acme_hvac");
  assert.equal(body.target, "ingesting");
});

test("HTTPJobStateSink.transition maps remediationRounds/rebuilds/reason metadata", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls.push(init.body as string);
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  await sink.transition("job_1", "acme_hvac", "quarantined", { reason: "remediation_limit", remediationRounds: 2 });

  const body = JSON.parse(calls[0]);
  assert.equal(body.failure_code, "remediation_limit");
  assert.equal(body.remediation_rounds, 2);
});

test("HTTPJobStateSink.transition forwards the report as quality_summary", async () => {
  // Regression: quality_summary_json stayed null on every quarantined job
  // -- the DB column and API both accepted it, but nothing ever mapped a
  // metadata field to body.quality_summary, so SiteMakerEngine's full
  // QualityReport never left the container log. Confirmed against two
  // real quarantined jobs on 2026-08-15 (quality_summary_json: null on
  // both) before this fix.
  const calls: string[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls.push(init.body as string);
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  const report = { designScore: 16, applicableMax: 24, findings: [], lighthouse: { performance: 72 } };
  await sink.transition("job_1", "acme_hvac", "quarantined", { reason: "remediation_limit", report });

  const body = JSON.parse(calls[0]);
  assert.deepEqual(body.quality_summary, report);
});

test("HTTPJobStateSink.transition expands buildId into build_id/preview_locator/artifact_manifest", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls.push(init.body as string);
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  await sink.transition("job_1", "acme_hvac", "ready_for_review", { buildId: "build_abc", remediationRounds: 1, rebuilds: 0 });

  const body = JSON.parse(calls[0]);
  assert.equal(body.build_id, "build_abc");
  assert.equal(body.preview_locator, "acme_hvac/job_1/build_abc.tar");
  assert.deepEqual(body.artifact_manifest, { jobId: "job_1", tenantId: "acme_hvac", buildId: "build_abc" });
  assert.equal(body.remediation_rounds, 1);
  assert.equal(body.rebuild_count, 0);
});

test("HTTPJobStateSink.transition throws on a failed HTTP response", async () => {
  const fetchImpl = (async () => new Response("conflict", { status: 409 })) as typeof fetch;
  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  await assert.rejects(() => sink.transition("job_1", "acme_hvac", "ingesting"));
});

test("HTTPJobStateSink.transition includes a generated event_id when none is passed", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls.push(init.body as string);
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  await sink.transition("job_1", "acme_hvac", "ingesting");
  await sink.transition("job_1", "acme_hvac", "directing");

  const first = JSON.parse(calls[0]).event_id;
  const second = JSON.parse(calls[1]).event_id;
  assert.equal(typeof first, "string");
  assert.ok(first.length > 0);
  assert.notEqual(first, second);
});

test("HTTPJobStateSink.transition uses the explicit event_id when a retry wrapper supplies one", async () => {
  const calls: string[] = [];
  const fetchImpl = (async (_url: string, init: RequestInit) => {
    calls.push(init.body as string);
    return new Response("", { status: 200 });
  }) as typeof fetch;

  const sink = new HTTPJobStateSink({ baseUrl: "https://api.netbuild.pro", apiKey: "k", fetchImpl });
  await sink.transition("job_1", "acme_hvac", "ingesting", undefined, "evt_fixed");
  await sink.transition("job_1", "acme_hvac", "ingesting", undefined, "evt_fixed");

  assert.equal(JSON.parse(calls[0]).event_id, "evt_fixed");
  assert.equal(JSON.parse(calls[1]).event_id, "evt_fixed");
});
