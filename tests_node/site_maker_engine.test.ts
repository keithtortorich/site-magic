import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import {
  normalizedScore, orderWeaknesses, releaseGatesPass, SiteMakerEngine,
  mergeDesignAssessment, InvalidDesignAssessmentError,
  generateImagesWithBoundedRetry, IMAGE_GENERATION_MAX_ATTEMPTS,
  MAX_REMEDIATION_ROUNDS,
  summarizeDeterministicEvidence,
  ensureImageCompsRendered, readImageDimensions,
  ensureMetaDescriptionPresent, extractMetaDescription,
  ensureStableResponsiveLayout,
  type QualityReport, type ImageGenerator, type WorkspaceWriter, type ImageComp,
  describeFailure,
  redactSecrets,
  buildEditorialImageBriefs,
} from "../webstaffr/site_maker_engine.ts";

// Real comps are `data:` URIs (see OpenAIImageGenerator/OpenRouterImageGenerator
// in site_magic_adapters.ts) -- writeImageComps() rejects anything else.
const TEST_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=";
const fakeComps = () => [TEST_PNG, TEST_PNG, TEST_PNG];

// Mirrors CodexRuntime's own fs-injection seam: a fake so tests don't need
// a real writable workspace directory on disk. Pre-seed `files` to
// simulate an entry HTML file the builder already wrote.
const fakeWorkspaceWriter = (
  files: Record<string, string> = {}
): WorkspaceWriter & { written: Map<string, Buffer> } => {
  const written = new Map<string, Buffer>();
  for (const [filePath, contents] of Object.entries(files)) {
    written.set(filePath, Buffer.from(contents, "utf-8"));
  }
  return {
    written,
    async mkdir() {},
    async writeFile(filePath, contents) { written.set(filePath, contents); },
    async readFile(filePath) {
      const contents = written.get(filePath);
      return contents === undefined ? null : contents.toString("utf-8");
    },
  };
};

const passing = (): QualityReport => ({
  designScore: 36, applicableMax: 40, findings: [], detectorFindings: 0,
  imageCompositionPassed: true,
  axeViolations: 0,
  lighthouse: { accessibility: 100, performance: 90, bestPractices: 95, seo: 95 },
  brokenLinks: 0, missingAssets: 0, consoleErrors: 0, failedRequests: 0,
  responsiveChecksPassed: true, functionalChecksPassed: true,
  contentIntegrityPassed: true, tenantIsolationPassed: true,
});

test("normalizes applicable heuristic maxima", () => {
  assert.equal(normalizedScore({ ...passing(), designScore: 29, applicableMax: 32 }), 29 / 32);
  assert.equal(normalizedScore({ ...passing(), designScore: 0, applicableMax: 0 }), 0);
});

test("buildEditorialImageBriefs creates distinct factual editorial roles", () => {
  const briefs = buildEditorialImageBriefs(
    {
      type: "intake", intakeId: "1",
      verifiedFacts: {
        biz_name: "Acme Climate", industry: "HVAC Contractor",
        service_area: "Washington, DC", services: ["AC Repair", "Maintenance"],
      },
    },
    { visualDirection: "documentary editorial" }
  );
  assert.deepEqual(briefs.map((brief) => brief.role), ["hero", "proof", "service"]);
  assert.deepEqual(briefs.map((brief) => brief.aspectRatio), ["16:9", "4:3", "4:3"]);
  assert.ok(briefs.every((brief) => brief.prompt.includes("Washington, DC")));
  assert.match(briefs[2].prompt, /AC Repair/);
  assert.ok(briefs.every((brief) => !/testimonial|award-winning/i.test(brief.prompt)));
});

test("orders the weakness ledger by priority then stable id", () => {
  const result = orderWeaknesses([
    { id: "b", priority: "P1", summary: "b" },
    { id: "z", priority: "P0", summary: "z" },
    { id: "a", priority: "P1", summary: "a" },
  ]);
  assert.deepEqual(result.map((item) => item.id), ["z", "a", "b"]);
});

test("enforces every deterministic release gate", () => {
  const finish = { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
  assert.equal(releaseGatesPass(passing(), finish), true);
  assert.equal(releaseGatesPass({ ...passing(), axeViolations: 1 }, finish), false);
  assert.equal(releaseGatesPass({ ...passing(), imageCompositionPassed: false }, finish), false);
  assert.equal(releaseGatesPass({ ...passing(), designScore: 28 }, finish), false);
});

test("happy path reveals only a sealed final build", async () => {
  const states: string[] = [];
  const roles: string[] = [];
  let assessorImages: string[] | undefined;
  const engine = new SiteMakerEngine({
    states: { async transition(_job, _tenant, state) { states.push(state); } },
    codex: { async run(args) {
      roles.push(args.role);
      if (args.role === "design_assessor") assessorImages = args.imageDataUrls;
      if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
      if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
      return {};
    } },
    images: { async generate() { return fakeComps(); } },
    evidence: {
      async assess() { return passing(); },
      getVisualEvidence() { return [{ width: 390, dataUrl: "data:image/jpeg;base64,MOBILE" }]; },
    },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-1" }; } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  const result = await engine.run({
    jobId: "job-1", tenantId: "tenant-1", workspace: "/private/job-1",
    source: { type: "intake", intakeId: "intake-1", verifiedFacts: { company: "Acme" } },
  });
  assert.deepEqual(result, { status: "ready_for_review", buildId: "build-1" });
  assert.equal(states.at(-1), "ready_for_review");
  assert.deepEqual(roles, ["product", "direction", "builder", "design_assessor", "finish_reviewer", "documenter"]);
  assert.deepEqual(assessorImages, ["data:image/jpeg;base64,MOBILE"]);
});

test("control-plane builds carry the approved plan guardrail into generation", async () => {
  let productInstructions = "";
  let builderInstructions = "";
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: { async run(args) {
      if (args.role === "product") productInstructions = args.instructions;
      if (args.role === "builder") builderInstructions = args.instructions;
      if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
      if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
      return {};
    } },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "control-provider-build" }; } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  const result = await engine.run({
    jobId: "control-build-1", tenantId: "tenant-1", workspace: "/private/control-build-1",
    source: {
      type: "control_plane", buildId: "control-build-1", planHash: "sha256:approved-plan",
      factSnapshotHash: "sha256:approved-facts",
      revisionId: "revision-1", revisionScope: ["home.hero"],
      plan: {
        pages: [{ page_id: "home", sections: [{ section_id: "hero" }] }],
        claims: [{ claim_id: "service", text: "Verified service", status: "supported", fact_ids: ["fact-1"] }],
        ctas: [{ cta_id: "call", label: "Call", target: "tel:+15551212" }],
        imagery_requirements: [], visual_direction: { mood: "clear" },
      },
      facts: [{ fact_id: "fact-1", kind: "service", value: "Electrical", status: "verified" }],
    },
  });
  assert.deepEqual(result, { status: "ready_for_review", buildId: "control-provider-build" });
  assert.match(productInstructions, /sha256:approved-plan/);
  assert.match(productInstructions, /Do not add pages, sections, claims, CTAs, or proof/);
  assert.match(productInstructions, /REVISION BOUNDARY revision-1/);
  assert.match(builderInstructions, /Preserve every approved section outside that revision scope/);
  assert.match(builderInstructions, /Verified service/);
});

test("quarantines after MAX_REMEDIATION_ROUNDS unsuccessful remediation rounds", async () => {
  const states: string[] = [];
  const quarantineMetadata: Array<Record<string, unknown> | undefined> = [];
  let remediations = 0;
  const codexFinding = [{ id: "p1", priority: "P1" as const, summary: "weak" }];
  const engine = new SiteMakerEngine({
    states: { async transition(_job, _tenant, state, metadata) {
      states.push(state);
      if (state === "quarantined") quarantineMetadata.push(metadata);
    } },
    codex: { async run(args) {
      if (args.role === "remediator") remediations += 1;
      if (args.role === "design_assessor") return { designScore: 20, applicableMax: 40, findings: codexFinding };
      return {};
    } },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { throw new Error("must not seal"); } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  const result = await engine.run({
    jobId: "job-2", tenantId: "tenant-1", workspace: "/private/job-2",
    source: { type: "url", url: "https://example.com/", ownershipAttested: true },
  });
  assert.equal(result.status, "quarantined");
  assert.equal(remediations, MAX_REMEDIATION_ROUNDS);
  assert.equal(states.at(-1), "quarantined");
  // Regression: quality_summary_json stayed null on every real quarantined
  // job because the quality report was only ever console.error'd, never
  // handed to the states sink -- confirmed against two live jobs on
  // 2026-08-15 before this fix.
  assert.equal(quarantineMetadata.length, 1);
  const report = quarantineMetadata[0]?.report as { designScore: number; findings: unknown };
  assert.equal(report?.designScore, 20);
  assert.deepEqual(report?.findings, codexFinding);
});

test("remediator instructions carry deterministic gate evidence, not just the design assessor's subjective findings", async () => {
  const failing: QualityReport = {
    ...passing(), designScore: 20, applicableMax: 40,
    detectorFindings: 1,
    detectorDiagnostics: [{ antipattern: "side-tab", name: "Side tab", description: "remove it", severity: "warning", file: "about.html", line: 4, snippet: "border-left:3px" }],
    missingAssets: 3, consoleErrors: 3, responsiveChecksPassed: false,
  };
  const remediatorInstructions: string[] = [];
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: { async run(args) {
      if (args.role === "remediator") remediatorInstructions.push(args.instructions);
      if (args.role === "design_assessor") return { designScore: 20, applicableMax: 40, findings: [] };
      return {};
    } },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return failing; } },
    artifacts: { async sealPrivateImmutable() { throw new Error("must not seal"); } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  await engine.run({
    jobId: "job-det-evidence", tenantId: "tenant-1", workspace: "/private/job-det-evidence",
    source: { type: "url", url: "https://example.com/", ownershipAttested: true },
  });
  assert.ok(remediatorInstructions.length > 0);
  for (const instructions of remediatorInstructions) {
    assert.match(instructions, /"missingAssets":3/);
    assert.match(instructions, /"consoleErrors":3/);
    assert.match(instructions, /"responsiveChecksPassed":false/);
    assert.match(instructions, /"antipattern":"side-tab"/);
    assert.match(instructions, /detectorFindings must reach zero/);
    assert.match(instructions, /edit every affected source file/);
  }
});

test("summarizeDeterministicEvidence surfaces every deterministicGatesPass field", () => {
  const evidence = summarizeDeterministicEvidence(passing());
  assert.deepEqual(evidence, {
    detectorFindings: 0, detectorDiagnostics: [], imageCompositionPassed: true, imageDiagnostics: [], axeViolations: 0, axeDiagnostics: [],
    lighthouse: { accessibility: 100, performance: 90, bestPractices: 95, seo: 95 },
    brokenLinks: 0, missingAssets: 0, consoleErrors: 0, failedRequests: 0,
    responsiveChecksPassed: true, functionalChecksPassed: true,
    contentIntegrityPassed: true, tenantIsolationPassed: true,
  });
});

test("mergeDesignAssessment splices designScore/applicableMax/findings from the design_assessor role", () => {
  const merged = mergeDesignAssessment(passing(), {
    designScore: 18, applicableMax: 20, findings: [{ id: "f1", priority: "P2", summary: "minor" }],
  });
  assert.equal(merged.designScore, 18);
  assert.equal(merged.applicableMax, 20);
  assert.deepEqual(merged.findings, [{ id: "f1", priority: "P2", summary: "minor" }]);
  // every other field is untouched -- evidence.assess()'s deterministic
  // findings are not something the design_assessor role gets to overwrite
  assert.equal(merged.axeViolations, passing().axeViolations);
});

test("mergeDesignAssessment throws on a malformed design_assessor response instead of defaulting to a passing shape", () => {
  assert.throws(() => mergeDesignAssessment(passing(), {}), InvalidDesignAssessmentError);
  assert.throws(() => mergeDesignAssessment(passing(), { designScore: "36", applicableMax: 40, findings: [] }), InvalidDesignAssessmentError);
  assert.throws(() => mergeDesignAssessment(passing(), { designScore: 36, applicableMax: 40, findings: "none" }), InvalidDesignAssessmentError);
});

test("a malformed design_assessor response fails the job closed instead of silently passing the gate", async () => {
  const states: string[] = [];
  const engine = new SiteMakerEngine({
    states: { async transition(_job, _tenant, state) { states.push(state); } },
    codex: { async run(args) { if (args.role === "design_assessor") return { oops: true }; return {}; } },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { throw new Error("must not seal"); } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  const result = await engine.run({
    jobId: "job-4", tenantId: "tenant-1", workspace: "/private/job-4",
    source: { type: "url", url: "https://example.com/", ownershipAttested: true },
  });
  assert.equal(result.status, "failed");
  assert.equal(states.at(-1), "failed");
});

test("generateImagesWithBoundedRetry returns on first success without retrying", async () => {
  let calls = 0;
  const images: ImageGenerator = { async generate() { calls += 1; return ["a", "b", "c"]; } };
  const slept: number[] = [];
  const result = await generateImagesWithBoundedRetry(
    images, { model: "m", brief: "b", count: 3 }, async (ms) => { slept.push(ms); }
  );
  assert.deepEqual(result, ["a", "b", "c"]);
  assert.equal(calls, 1);
  assert.deepEqual(slept, []);
});

test("generateImagesWithBoundedRetry retries on failure and returns the first later success", async () => {
  let calls = 0;
  const images: ImageGenerator = {
    async generate() {
      calls += 1;
      if (calls < 3) throw new Error("transient provider error");
      return ["a", "b", "c"];
    },
  };
  const slept: number[] = [];
  const result = await generateImagesWithBoundedRetry(
    images, { model: "m", brief: "b", count: 3 }, async (ms) => { slept.push(ms); }
  );
  assert.deepEqual(result, ["a", "b", "c"]);
  assert.equal(calls, 3);
  // backoff delays are recorded between attempts, not after the final success
  assert.equal(slept.length, 2);
});

test("generateImagesWithBoundedRetry returns null (not a throw) after exhausting all attempts", async () => {
  let calls = 0;
  const images: ImageGenerator = { async generate() { calls += 1; throw new Error("persistent provider outage"); } };
  const slept: number[] = [];
  const result = await generateImagesWithBoundedRetry(
    images, { model: "m", brief: "b", count: 3 }, async (ms) => { slept.push(ms); }
  );
  assert.equal(result, null);
  assert.equal(calls, IMAGE_GENERATION_MAX_ATTEMPTS);
  // one fewer sleep than attempts -- no backoff wait after the final failed attempt
  assert.equal(slept.length, IMAGE_GENERATION_MAX_ATTEMPTS - 1);
});

test("a persistently failing image generator quarantines the build without fabricating imagery", async () => {
  const states: Array<{ state: string; metadata?: Record<string, unknown> }> = [];
  const builderInstructions: string[] = [];
  const engine = new SiteMakerEngine({
    states: { async transition(_job, _tenant, state, metadata) { states.push({ state, metadata }); } },
    codex: {
      async run(args) {
        if (args.role === "builder") builderInstructions.push(args.instructions);
        if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
        if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
        return {};
      },
    },
    images: { async generate() { throw new Error("image vendor outage"); } },
    evidence: { async assess() { return {
      ...passing(), imageCompositionPassed: false,
      imageDiagnostics: ["required editorial imagery is missing"],
    }; } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-missing-images" }; } },
  });
  const result = await engine.run({
    jobId: "job-images-missing", tenantId: "tenant-1", workspace: "/private/job-images-missing",
    source: { type: "intake", intakeId: "intake-1", verifiedFacts: { company: "Acme" } },
  });
  assert.equal(result.status, "quarantined");
  const buildingTransition = states.find((entry) => entry.state === "building");
  assert.equal(buildingTransition?.metadata?.imagesMissing, true);
  // the builder role is told images are unavailable and must not fabricate
  // or reference placeholders -- never a silent gap the visitor discovers
  assert.match(builderInstructions[0], /No image comps are available/);
  assert.match(builderInstructions[0], /Never fabricate, reference, or leave placeholders for missing images/);
});

test("a no-image fallback is assessed as a material visual failure without inviting fabricated claims", async () => {
  const calls: Array<{ role: string; instructions: string }> = [];
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: { async run(args) {
      calls.push({ role: args.role, instructions: args.instructions });
      if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
      if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
      return {};
    } },
    images: { async generate() { throw new Error("image vendor outage"); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-no-image" }; } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  await engine.run({
    jobId: "job-no-image-assessment", tenantId: "tenant-1", workspace: "/tmp/no-image-assessment",
    source: { type: "intake", intakeId: "1", verifiedFacts: {} },
  });
  const assessment = calls.find((call) => call.role === "design_assessor");
  assert.match(String(assessment?.instructions), /fails the mandatory image composition requirement; record that as a material finding/);
  assert.match(String(assessment?.instructions), /Do not demand fabricated testimonials, awards, ratings, or customer claims/);
});

test("generated image comps are written to the workspace and the builder is told their exact paths", async () => {
  // Regression for 2026-08-15: comps were generated but never written to
  // disk or mentioned in the builder's instructions, so the builder
  // invented image paths that never existed -- every real job quarantined
  // with missingAssets/consoleErrors as a multiple of 3 (one per comp,
  // times 3 viewport widths). Confirmed against a real quarantined job's
  // Evidence Runner report (missingAssets: 9, consoleErrors: 9).
  const builderInstructions: string[] = [];
  const writer = fakeWorkspaceWriter();
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: {
      async run(args) {
        if (args.role === "builder") builderInstructions.push(args.instructions);
        if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
        if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
        return {};
      },
    },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-with-images" }; } },
    workspaceWriter: writer,
  });
  const result = await engine.run({
    jobId: "job-images-present", tenantId: "tenant-1", workspace: "/private/job-images-present",
    source: { type: "intake", intakeId: "intake-1", verifiedFacts: { company: "Acme" } },
  });
  assert.deepEqual(result, { status: "ready_for_review", buildId: "build-with-images" });
  assert.deepEqual(
    [...writer.written.keys()].sort(),
    [
      "/private/job-images-present/images/comp-1.webp",
      "/private/job-images-present/images/comp-2.webp",
      "/private/job-images-present/images/comp-3.webp",
    ]
  );
  assert.match(builderInstructions[0], /hero=images\/comp-1\.webp/);
  assert.match(builderInstructions[0], /proof=images\/comp-2\.webp/);
  assert.match(builderInstructions[0], /service=images\/comp-3\.webp/);
  assert.match(builderInstructions[0], /hero image prominently above the fold/);
  assert.match(builderInstructions[0], /Do not invent, rename, or reference any other image path/);
  assert.equal(writer.written.get("/private/job-images-present/images/comp-1.webp")?.subarray(0, 4).toString("ascii"), "RIFF");
});

// width/height 0 means "unknown" -- ensureImageCompsRendered omits the
// attributes rather than emitting a bogus 0x0.
const comp = (relativePath: string, width = 0, height = 0): ImageComp => ({
  relativePath, role: "hero", altText: "HVAC service environment", width, height,
});

test("ensureImageCompsRendered injects any comp the entry file doesn't already reference", async () => {
  // Regression for 2026-08-15: telling the builder the exact paths was
  // necessary but not sufficient -- confirmed against a real job that
  // reverted to missingAssets: 9 with no code change from a run that had
  // scored 0. Prompt compliance is probabilistic; this makes it
  // deterministic by patching the audited entry file directly.
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": "<html><body><h1>Hi</h1><img src=\"images/comp-2.png\"></body></html>",
  });
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png"), comp("images/comp-2.png"), comp("images/comp-3.png")]);

  const patched = (await writer.readFile("/ws/index.html"))!;
  assert.match(patched, /<img src="images\/comp-1\.png"/);
  assert.match(patched, /<img src="images\/comp-3\.png"/);
  // already-referenced comp is untouched, not duplicated
  assert.equal(patched.match(/comp-2\.png/g)?.length, 1);
  // injected before the closing tag, not after it
  assert.ok(patched.indexOf("comp-1.png") < patched.indexOf("</body>"));
});

test("ensureImageCompsRendered sets width/height when known, to avoid layout shift", async () => {
  // Regression for 2026-08-15: a real quarantined job whose only comp
  // reference came from this fallback gallery failed cumulative-layout-shift
  // (0.578 against a 0.1 gate) -- images with no reserved layout space
  // shift content as they load. Explicit dimensions fix that.
  const writer = fakeWorkspaceWriter({ "/ws/index.html": "<html><body></body></html>" });
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png", 1536, 1024)]);
  const patched = (await writer.readFile("/ws/index.html"))!;
  assert.match(patched, /<img src="images\/comp-1\.png" width="1536" height="1024"/);
});

test("ensureImageCompsRendered omits width/height when dimensions are unknown", async () => {
  const writer = fakeWorkspaceWriter({ "/ws/index.html": "<html><body></body></html>" });
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png")]);
  const patched = (await writer.readFile("/ws/index.html"))!;
  assert.match(patched, /<img src="images\/comp-1\.png" alt="HVAC service environment" data-image-role="hero"/);
  assert.doesNotMatch(patched, /width=/);
});

test("ensureImageCompsRendered hardens a referenced hero for LCP and layout stability", async () => {
  const html = "<html><body><img src=\"images/comp-1.png\" loading=\"lazy\"></body></html>";
  const writer = fakeWorkspaceWriter({ "/ws/index.html": html });
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png", 512, 512)]);
  const patched = (await writer.readFile("/ws/index.html"))!;
  assert.match(patched, /width="512"/);
  assert.match(patched, /height="512"/);
  assert.match(patched, /loading="eager"/);
  assert.match(patched, /fetchpriority="high"/);
  assert.doesNotMatch(patched, /loading="lazy"/);
});

test("ensureImageCompsRendered is a no-op when no entry file exists yet", async () => {
  const writer = fakeWorkspaceWriter();
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png")]);
  assert.equal(writer.written.size, 0);
});

test("ensureImageCompsRendered falls back to home.html when index.html doesn't exist", async () => {
  const writer = fakeWorkspaceWriter({ "/ws/home.html": "<html><body></body></html>" });
  await ensureImageCompsRendered(writer, "/ws", [comp("images/comp-1.png")]);
  assert.match((await writer.readFile("/ws/home.html"))!, /comp-1\.png/);
});

test("readImageDimensions parses a real PNG's IHDR chunk", () => {
  // A minimal valid 1x1 transparent PNG.
  const onePixelPng = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64"
  );
  assert.deepEqual(readImageDimensions(onePixelPng, "png"), { width: 1, height: 1 });
});

test("readImageDimensions returns null for a format it doesn't recognize", () => {
  assert.equal(readImageDimensions(Buffer.from("not an image"), "webp"), null);
  assert.equal(readImageDimensions(Buffer.from([0x89, 0x50]), "png"), null);
});

test("extractMetaDescription pulls real body text, not invented copy", () => {
  const html = "<html><body><h1>Acme HVAC</h1><p>Licensed heating and cooling in the metro area.</p></body></html>";
  assert.equal(extractMetaDescription(html), "Acme HVAC Licensed heating and cooling in the metro area.");
});

test("extractMetaDescription truncates at a word boundary, never mid-word", () => {
  const longText = "word ".repeat(60).trim(); // well over 155 chars
  const html = `<html><body><p>${longText}</p></body></html>`;
  const description = extractMetaDescription(html, 155)!;
  assert.ok(description.length <= 156, "truncated length within bound plus ellipsis");
  assert.ok(description.endsWith("…"));
  assert.doesNotMatch(description, /\bwor…$|\bwo…$|\bw…$/, "cut on a word boundary, not mid-word");
});

test("extractMetaDescription returns null when there's no real text to summarize", () => {
  assert.equal(extractMetaDescription("<html><body></body></html>"), null);
});

test("ensureMetaDescriptionPresent injects a description derived from the page's own text", async () => {
  // Regression: confirmed live against three separate production jobs
  // on 2026-08-15 -- every real SEO-gate miss traced to the same
  // Lighthouse audit, "meta-description: Document does not have a meta
  // description". A run where the builder happened to include one
  // scored SEO 100, proving it's the single blocker, not remediation
  // noise.
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": "<html><head><title>Acme HVAC</title></head><body><p>Licensed HVAC contractor in the metro area.</p></body></html>",
  });
  await ensureMetaDescriptionPresent(writer, "/ws");
  const patched = (await writer.readFile("/ws/index.html"))!;
  assert.match(patched, /<meta name="description" content="Licensed HVAC contractor in the metro area\.">/);
});

test("ensureMetaDescriptionPresent is a no-op when a description already exists", async () => {
  const html = "<html><head><meta name=\"description\" content=\"Already here.\"></head><body></body></html>";
  const writer = fakeWorkspaceWriter({ "/ws/index.html": html });
  await ensureMetaDescriptionPresent(writer, "/ws");
  assert.equal(await writer.readFile("/ws/index.html"), html);
});

test("ensureMetaDescriptionPresent doesn't fabricate a description for an empty page", async () => {
  const html = "<html><head><title>Acme</title></head><body></body></html>";
  const writer = fakeWorkspaceWriter({ "/ws/index.html": html });
  await ensureMetaDescriptionPresent(writer, "/ws");
  assert.equal(await writer.readFile("/ws/index.html"), html);
});

test("ensureStableResponsiveLayout injects deterministic mobile and load-stability guards once", async () => {
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": '<html><head><title>Acme</title></head><body><img src="hero.png"></body></html>',
  });
  await ensureStableResponsiveLayout(writer, "/ws");
  await ensureStableResponsiveLayout(writer, "/ws");
  const html = (await writer.readFile("/ws/index.html"))!;
  assert.match(html, /data-site-magic-stability/);
  assert.match(html, /overflow-x:hidden/);
  assert.match(html, /body>\*\{min-width:0;max-width:100%\}/);
  assert.match(html, /class\*="contour"/);
  assert.match(html, /animation:none!important/);
  assert.match(html, /opacity:1!important/);
  assert.match(html, /<main><img/);
  assert.match(html, /background:#0b3b5a!important;color:#fff!important/);
  assert.match(html, /nav a\{min-height:44px/);
  assert.match(html, /nav,.menu-toggle,.cta-banner/);
  assert.match(html, /nav a\[data-view\]/);
  assert.match(html, /\.service-row,\.service-row \*/);
  assert.equal(html.match(/data-site-magic-stability/g)?.length, 1);
});

test("ensureStableResponsiveLayout keeps header and footer outside the injected main landmark", async () => {
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": "<html><body><header><nav>Links</nav></header><section>Content</section><footer>Footer</footer></body></html>",
  });
  await ensureStableResponsiveLayout(writer, "/ws");
  const html = (await writer.readFile("/ws/index.html"))!;
  assert.match(html, /<\/header><main><section>Content<\/section><\/main><footer>/);
});

test("ensureStableResponsiveLayout wraps standalone mobile navigation in a header landmark", async () => {
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": '<html><body><button class="menu-toggle">Menu</button><nav>Links</nav><section>Content</section></body></html>',
  });
  await ensureStableResponsiveLayout(writer, "/ws");
  const html = (await writer.readFile("/ws/index.html"))!;
  assert.match(html, /<header><button class="menu-toggle">Menu<\/button><nav>Links<\/nav><\/header><main>/);
});

test("ensureStableResponsiveLayout labels utility regions and the initial SPA page", async () => {
  const writer = fakeWorkspaceWriter({
    "/ws/index.html": '<html><body><div class="utility">Call us</div><nav><a data-view="home">Home</a></nav><section>Content</section></body></html>',
  });
  await ensureStableResponsiveLayout(writer, "/ws");
  const html = (await writer.readFile("/ws/index.html"))!;
  assert.match(html, /class="utility" role="region" aria-label="Utility information"/);
  assert.match(html, /data-view="home" aria-current="page"/);
});

test("a builder that ignores the image-path instructions still ends up with every comp on the audited page", async () => {
  const writer = fakeWorkspaceWriter();
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: {
      async run(args) {
        if (args.role === "builder") {
          // simulates a non-compliant builder: writes an entry file with
          // no reference to any of the given comp paths
          writer.written.set("/private/job-noncompliant/index.html", Buffer.from("<html><body></body></html>", "utf-8"));
        }
        if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
        if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
        return {};
      },
    },
    images: { async generate() { return fakeComps(); } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-1" }; } },
    workspaceWriter: writer,
  });
  const result = await engine.run({
    jobId: "job-noncompliant", tenantId: "tenant-1", workspace: "/private/job-noncompliant",
    source: { type: "intake", intakeId: "intake-1", verifiedFacts: { company: "Acme" } },
  });
  assert.deepEqual(result, { status: "ready_for_review", buildId: "build-1" });
  const entry = (await writer.readFile("/private/job-noncompliant/index.html"))!;
  assert.match(entry, /comp-1\.webp/);
  assert.match(entry, /comp-2\.webp/);
  assert.match(entry, /comp-3\.webp/);
});

test("adapter failure fails closed", async () => {
  const states: string[] = [];
  const engine = new SiteMakerEngine({
    states: { async transition(_job, _tenant, state) { states.push(state); } },
    codex: { async run() { throw new Error("not configured"); } },
    images: { async generate() { return []; } },
    evidence: { async assess() { return passing(); } },
    artifacts: { async sealPrivateImmutable() { return { buildId: "never" }; } },
  });
  const result = await engine.run({
    jobId: "job-3", tenantId: "tenant-1", workspace: "/private/job-3",
    source: { type: "intake", intakeId: "intake-3", verifiedFacts: {} },
  });
  assert.equal(result.status, "failed");
  assert.equal(states.at(-1), "failed");
});

test("DESIGN_MODEL picks up SITE_MAGIC_DESIGN_MODEL, not just the runtime's own default", () => {
  // Regression: DESIGN_MODEL was a hardcoded literal, and every codex.run()
  // call in this file passes it explicitly as `model`, which overrides
  // OpenRouterCodegenRuntime's own env-var-aware default entirely. Setting
  // SITE_MAGIC_DESIGN_MODEL in production Railway env had zero effect on
  // any real call -- discovered when a 402-driven free-tier-model swap
  // still 402'd, because the constant never read the env var at all.
  // Spawns a fresh process (mirrors a real container restart, where env
  // vars are set before the process -- and this module -- ever starts).
  const withEnv = execFileSync(
    process.execPath,
    ["--input-type=module", "-e", "import { DESIGN_MODEL } from './webstaffr/site_maker_engine.ts'; console.log(DESIGN_MODEL);"],
    { encoding: "utf-8", env: { ...process.env, SITE_MAGIC_DESIGN_MODEL: "openai/gpt-oss-20b:free" } }
  ).trim();
  assert.equal(withEnv, "openai/gpt-oss-20b:free");

  const envWithoutModel = { ...process.env };
  delete envWithoutModel.SITE_MAGIC_DESIGN_MODEL;
  const withoutEnv = execFileSync(
    process.execPath,
    ["--input-type=module", "-e", "import { DESIGN_MODEL } from './webstaffr/site_maker_engine.ts'; console.log(DESIGN_MODEL);"],
    { encoding: "utf-8", env: envWithoutModel }
  ).trim();
  assert.equal(withoutEnv, "openai/gpt-5.6-terra");
});

test("describeFailure carries the provider's reason, not just the class name", () => {
  // Regression: the first real production job died on an OpenRouter 401 and
  // recorded failure_code "Error" -- diagnosing it required probing the
  // provider by hand.
  const err = new Error("OpenRouter API error: 401 Unauthorized");
  assert.equal(describeFailure(err), "Error: OpenRouter API error: 401 Unauthorized");
});

test("describeFailure falls back to the class name when there is no message", () => {
  assert.equal(describeFailure(new Error("")), "Error");
  assert.equal(describeFailure("not an error"), "UnknownError");
});

test("describeFailure bounds a runaway message to the control plane's 64-char failure_code limit", () => {
  // Regression: a 130-char message made describeFailure return a string
  // over the API's max_length=64, so the state-transition write recording
  // the failure itself 422'd -- the job never got marked failed at all.
  const described = describeFailure(new Error("x".repeat(5000)));
  assert.ok(described.length <= 64, `expected <=64 chars, got ${described.length}`);
  assert.ok(described.startsWith("Error: "));
});

test("describeFailure redacts credentials that a provider echoed back", () => {
  const cases = [
    "auth failed for sk-or-v1-abcdef0123456789abcdef0123456789",
    "bad key " + "sb_" + "secret_" + "Zfo5SHwPqUJlmpc3vnnb4w_6NalamsD",
    "rejected Bearer sk-or-v1-deadbeefdeadbeefdeadbeef",
    "token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123def456",
  ];
  for (const raw of cases) {
    const described = describeFailure(new Error(raw));
    assert.ok(!/sk-or-v1-[A-Za-z0-9]/.test(described), `leaked openrouter key: ${described}`);
    assert.ok(!/sb_secret_[A-Za-z0-9]/.test(described), `leaked supabase key: ${described}`);
    assert.ok(!/eyJ[A-Za-z0-9_-]{10,}\./.test(described), `leaked jwt: ${described}`);
  }
});

test("a failed run returns the reason so the worker can log it", async () => {
  const states: Array<{ state: string; metadata?: Record<string, unknown> }> = [];
  const engine = new SiteMakerEngine({
    states: { async transition(_j, _t, state, metadata) { states.push({ state, metadata }); } },
    codex: { async run() { throw new Error("OpenRouter API error: 401 Unauthorized"); } },
    images: { async generate() { return ["a", "b", "c"]; } },
    evidence: { async assess() { throw new Error("unreachable"); } },
    artifacts: { async sealPrivateImmutable() { throw new Error("unreachable"); } },
  });

  const result = await engine.run({
    jobId: "job-1", tenantId: "tenant-1", workspace: "/tmp/nope",
    source: { type: "intake", intakeId: "1", verifiedFacts: {} },
  });

  assert.equal(result.status, "failed");
  assert.equal(result.failureCode, "Error: OpenRouter API error: 401 Unauthorized");
  const failed = states.find((s) => s.state === "failed");
  assert.equal(failed?.metadata?.errorType, "Error: OpenRouter API error: 401 Unauthorized");
});

test("ADR-030 image gate is dead code when SITE_MAGIC_IMAGE_VERIFY is unset", async () => {
  delete process.env.SITE_MAGIC_IMAGE_VERIFY;
  const roles: string[] = [];
  let imagesGenerateCalls = 0;
  const engine = new SiteMakerEngine({
    states: { async transition() {} },
    codex: { async run(args) {
      roles.push(args.role);
      if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
      if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
      return {};
    } },
    images: { async generate() { imagesGenerateCalls += 1; return fakeComps(); } },
    evidence: {
      async assess() { return passing(); },
      getVisualEvidence() { return [{ width: 390, dataUrl: "data:image/jpeg;base64,MOBILE" }]; },
    },
    artifacts: { async sealPrivateImmutable() { return { buildId: "build-1" }; } },
    workspaceWriter: fakeWorkspaceWriter(),
  });
  const result = await engine.run({
    jobId: "job-gate-off", tenantId: "tenant-1", workspace: "/tmp/gate-off",
    source: { type: "intake", intakeId: "1", verifiedFacts: {} },
  });
  assert.equal(result.status, "ready_for_review");
  // Gate off: image generation called exactly once (no regen), count passed through as 3.
  assert.equal(imagesGenerateCalls, 1);
});

test("ADR-030 image gate fails open when the verifier has no credential", async () => {
  // verifyImageContent is fail-open: with no OPENROUTER_API_KEY it returns
  // {match:true}, so the gate must NOT drop or regenerate comps and the job
  // must still reach ready_for_review. This protects the default-off posture.
  const prevKey = process.env.OPENROUTER_API_KEY;
  delete process.env.OPENROUTER_API_KEY;
  process.env.SITE_MAGIC_IMAGE_VERIFY = "1";
  const roles: string[] = [];
  let imagesGenerateCalls = 0;
  try {
    const engine = new SiteMakerEngine({
      states: { async transition() {} },
      codex: { async run(args) {
        roles.push(args.role);
        if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
        if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
        return {};
      } },
      images: { async generate() { imagesGenerateCalls += 1; return fakeComps(); } },
      evidence: {
        async assess() { return passing(); },
        getVisualEvidence() { return [{ width: 390, dataUrl: "data:image/jpeg;base64,MOBILE" }]; },
      },
      artifacts: { async sealPrivateImmutable() { return { buildId: "build-1" }; } },
      workspaceWriter: fakeWorkspaceWriter(),
    });
    const result = await engine.run({
      jobId: "job-gate-open-nokey", tenantId: "tenant-1", workspace: "/tmp/gate-open-nokey",
      source: { type: "intake", intakeId: "1", verifiedFacts: {} },
    });
    assert.equal(result.status, "ready_for_review");
    // Fail-open: gate ran (flag on) but with no credential it must not regenerate.
    assert.equal(imagesGenerateCalls, 1);
  } finally {
    if (prevKey !== undefined) process.env.OPENROUTER_API_KEY = prevKey;
    delete process.env.SITE_MAGIC_IMAGE_VERIFY;
  }
});

test("ADR-030 image gate drops a persistently-mismatched comp and splices its brief, leaving the survivors' roles/paths correct", async () => {
  // Mirrors the real production instance the ADR was written from: comp
  // index 2 ("service") never matches its brief, even after the one bounded
  // regen, while hero/proof always match. Verifies the end-to-end outcome
  // that unit tests on verifyImageContent() alone cannot: that the engine
  // actually drops the right comp, splices the matching ImageBrief out (not
  // just the data URI), and the builder is told about exactly 2 comps with
  // hero/proof's original roles and alt text -- not shifted or fabricated.
  const prevKey = process.env.OPENROUTER_API_KEY;
  process.env.OPENROUTER_API_KEY = "test-key";
  process.env.SITE_MAGIC_IMAGE_VERIFY = "1";
  const prevFetch = global.fetch;
  let verifyCalls = 0;
  // @ts-expect-error test stub, narrower than the real fetch signature
  global.fetch = async (_url: string, init: { body: string }) => {
    verifyCalls += 1;
    const body = JSON.parse(init.body);
    const promptText = body.messages[0].content[0].text as string;
    const roleMatch = /role "([^"]+)"/.exec(promptText);
    const role = roleMatch ? roleMatch[1] : "";
    const match = role !== "service"; // service never matches, initial or regen
    return {
      ok: true,
      json: async () => ({
        choices: [{ message: { content: JSON.stringify({ match, reason: match ? "ok" : "wrong subject" }) } }],
      }),
    } as Response;
  };
  let builderInstructions = "";
  let imagesGenerateCalls = 0;
  try {
    const engine = new SiteMakerEngine({
      states: { async transition() {} },
      codex: {
        async run(args) {
          if (args.role === "builder") builderInstructions = args.instructions;
          if (args.role === "finish_reviewer") return { verdict: "PASS", authoredNotInterchangeable: true, materialFindings: [] };
          if (args.role === "design_assessor") return { designScore: 36, applicableMax: 40, findings: [] };
          return {};
        },
      },
      images: { async generate() { imagesGenerateCalls += 1; return fakeComps(); } },
      evidence: {
        async assess() { return passing(); },
        getVisualEvidence() { return [{ width: 390, dataUrl: "data:image/jpeg;base64,MOBILE" }]; },
      },
      artifacts: { async sealPrivateImmutable() { return { buildId: "build-1" }; } },
      workspaceWriter: fakeWorkspaceWriter(),
    });
    const result = await engine.run({
      jobId: "job-gate-drop", tenantId: "tenant-1", workspace: "/tmp/gate-drop",
      source: {
        type: "intake", intakeId: "1",
        verifiedFacts: { biz_name: "Acme HVAC", industry: "HVAC Contractor", service_area: "Denver, CO", services: ["Duct Cleaning"] },
      },
    });
    assert.equal(result.status, "ready_for_review");
    // Initial generate (3 comps) + exactly one bounded regen of the whole set.
    assert.equal(imagesGenerateCalls, 2);
    // 3 initial verify calls + 1 re-verify of the still-mismatched index only.
    assert.equal(verifyCalls, 4);
    // Builder was told about exactly 2 comps, with hero/proof's real roles,
    // alt text, and re-numbered (not stale) relative paths -- not 3, and not
    // a service comp smuggled through.
    assert.match(builderInstructions, /2 pre-generated editorial image/);
    assert.match(builderInstructions, /hero=images\/comp-1\.webp \(alt: HVAC Contractor service environment in Denver, CO\)/);
    assert.match(builderInstructions, /proof=images\/comp-2\.webp \(alt: HVAC Contractor tools and process detail\)/);
    assert.doesNotMatch(builderInstructions, /service=/);
    assert.doesNotMatch(builderInstructions, /comp-3\.webp/);
  } finally {
    global.fetch = prevFetch;
    if (prevKey !== undefined) process.env.OPENROUTER_API_KEY = prevKey; else delete process.env.OPENROUTER_API_KEY;
    delete process.env.SITE_MAGIC_IMAGE_VERIFY;
  }
});
