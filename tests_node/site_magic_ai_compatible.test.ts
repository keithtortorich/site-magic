import test from "node:test";
import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import { mkdtemp, rm } from "node:fs/promises";
import {
  CodexRuntimeNotConfiguredError,
  ImageGeneratorNotConfiguredError,
  OpenAICompatibleCodegenRuntime,
  OpenAICompatibleImageGenerator,
} from "../webstaffr/site_magic_ai_compatible.ts";

function withCleanCompatibleEnv<T>(run: () => T): T {
  const keys = [
    "OPENAI_COMPATIBLE_API_KEY",
    "OPENAI_COMPATIBLE_BASE_URL",
    "OPENAI_COMPATIBLE_MODEL",
    "OPENAI_COMPATIBLE_IMAGE_MODEL",
  ];
  const originals = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  for (const key of keys) delete process.env[key];
  try {
    return run();
  } finally {
    for (const [key, value] of Object.entries(originals)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

test("codegen adapter rejects a non-local endpoint without a credential", () => {
  withCleanCompatibleEnv(() => {
    assert.throws(
      () => new OpenAICompatibleCodegenRuntime({ baseUrl: "https://inference.example/v1" }),
      CodexRuntimeNotConfiguredError,
    );
  });
});

test("compatible adapters do not treat localhost text in a remote URL as loopback", () => {
  withCleanCompatibleEnv(() => {
    for (const baseUrl of [
      "https://localhost.example.com/v1",
      "https://localhost@provider.example/v1",
      "https://127.provider.example/v1",
    ]) {
      assert.throws(
        () => new OpenAICompatibleCodegenRuntime({ baseUrl }),
        CodexRuntimeNotConfiguredError,
      );
      assert.throws(
        () => new OpenAICompatibleImageGenerator({ baseUrl }),
        ImageGeneratorNotConfiguredError,
      );
    }
  });
});

test("codegen adapter maps compatible endpoint settings onto the hardened runtime", () => {
  withCleanCompatibleEnv(() => {
    const runtime = new OpenAICompatibleCodegenRuntime({
      baseUrl: "http://localhost:11434/v1/",
      model: "local-model",
    }) as unknown as { baseUrl: string; apiKey: string; model: string };
    assert.equal(runtime.baseUrl, "http://localhost:11434/v1");
    assert.equal(runtime.apiKey, "dummy");
    assert.equal(runtime.model, "local-model");
  });
});

test("codegen adapter uses the compatible model instead of the engine default", async () => {
  const calls: Array<Record<string, unknown>> = [];
  const fetchImpl = (async (_url: string | URL, init?: RequestInit) => {
    calls.push(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify({
      choices: [{ message: { content: '{"files":[],"result":{"status":"ok"}}' } }],
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;
  const workspace = await mkdtemp(path.join(os.tmpdir(), "site-magic-compatible-"));

  try {
    const runtime = new OpenAICompatibleCodegenRuntime({
      baseUrl: "http://127.0.0.1:11434/v1",
      model: "local-model",
      fetchImpl,
    });
    await runtime.run({
      role: "product",
      workspace,
      instructions: "Return a product brief.",
      model: "openai/gpt-5.6-terra",
    });
  } finally {
    await rm(workspace, { recursive: true, force: true });
  }

  assert.equal(calls.length, 1);
  assert.equal(calls[0].model, "local-model");
});

test("image adapter rejects a non-local endpoint without a credential", () => {
  withCleanCompatibleEnv(() => {
    assert.throws(
      () => new OpenAICompatibleImageGenerator({ baseUrl: "https://inference.example/v1" }),
      ImageGeneratorNotConfiguredError,
    );
  });
});

test("image adapter requires an explicit compatible image model", () => {
  withCleanCompatibleEnv(() => {
    assert.throws(
      () => new OpenAICompatibleImageGenerator({ baseUrl: "http://localhost:11434/v1" }),
      (error: unknown) =>
        error instanceof ImageGeneratorNotConfiguredError &&
        error.message.includes("OPENAI_COMPATIBLE_IMAGE_MODEL"),
    );
  });
});

test("image adapter requests one inline image per editorial brief", async () => {
  const calls: Array<{ url: string; authorization: string; body: Record<string, unknown> }> = [];
  const fetchImpl = (async (url: string | URL, init?: RequestInit) => {
    calls.push({
      url: url.toString(),
      authorization: (init?.headers as Record<string, string>).Authorization,
      body: JSON.parse(String(init?.body)),
    });
    return new Response(JSON.stringify({ data: [{ b64_json: "aW1hZ2U=" }] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;

  const generator = new OpenAICompatibleImageGenerator({
    apiKey: "test-key",
    baseUrl: "https://inference.example/v1/",
    model: "image-model",
    fetchImpl,
  });
  const images = await generator.generate({
    model: "engine-default",
    brief: "fallback",
    count: 3,
    briefs: [
      { role: "hero", aspectRatio: "16:9", prompt: "hero prompt", altText: "Hero" },
      { role: "proof", aspectRatio: "4:3", prompt: "proof prompt", altText: "Proof" },
      { role: "service", aspectRatio: "4:3", prompt: "service prompt", altText: "Service" },
    ],
  });

  assert.deepEqual(images, Array(3).fill("data:image/png;base64,aW1hZ2U="));
  assert.equal(calls.length, 3);
  assert.ok(calls.every((call) => call.url === "https://inference.example/v1/images/generations"));
  assert.ok(calls.every((call) => call.authorization === "Bearer test-key"));
  assert.deepEqual(calls.map((call) => call.body.model), ["image-model", "image-model", "image-model"]);
  assert.deepEqual(calls.map((call) => call.body.prompt), ["hero prompt", "proof prompt", "service prompt"]);
  assert.deepEqual(calls.map((call) => call.body.size), ["1536x1024", "1024x1024", "1024x1024"]);
});
