import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertProvenanceAllowsSubjectExecution,
  collectBenchmarkProvenance,
  describeSoftwareDifferences,
  hashDirectoryTree,
  npmInstallMatchesLock,
  resolveBenchmarkVersion,
} from "../src/benchmark/provenance.js";
import { BENCHMARK_VERSION, type BenchmarkProvenance, type BenchmarkSoftware } from "../src/benchmark/types.js";

async function writeSkill(root: string, skillText: string, referenceText = "# Doc\n"): Promise<string> {
  await mkdir(path.join(root, "references"), { recursive: true });
  await writeFile(path.join(root, "SKILL.md"), skillText, "utf8");
  await writeFile(path.join(root, "references", "morpheusml-doc.md"), referenceText, "utf8");
  return path.join(root, "SKILL.md");
}

function softwareWith(overrides: Partial<BenchmarkSoftware> = {}): BenchmarkSoftware {
  return {
    node: "v18.19.1",
    platform: "linux-x64 6.0",
    codexSdk: "0.149.1",
    codexSdkLocked: "0.149.1",
    codexCli: "0.149.1",
    morpheus: "2.4.1",
    morpheusRevision: "19.05.2026",
    gnuplot: "gnuplot 6.0 patchlevel 0",
    python: "3.12.14",
    packageLockSha256: null,
    uvLockSha256: null,
    npmInstalledMatchesLock: true,
    pythonInstalledMatchesLock: true,
    ...overrides,
  };
}

function provenanceWith(overrides: Partial<BenchmarkProvenance> = {}): BenchmarkProvenance {
  return {
    benchmarkVersion: BENCHMARK_VERSION,
    gitCommit: null,
    gitTag: null,
    gitDirty: null,
    skills: [{ name: "morpheus", sha256: "a".repeat(64) }],
    docsReferences: { morpheusMlDocSha256: null, modelTemplateSha256: null },
    prompts: { subjectPromptSourceSha256: "p".repeat(64), mcpServerSha256: null, focusSha256: null },
    software: softwareWith(),
    ...overrides,
  };
}

test("hashDirectoryTree ignores line endings but tracks content and file names", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-skill-hash-"));
  await writeSkill(path.join(root, "lf"), "---\nname: morpheus\n---\n");
  await writeSkill(path.join(root, "crlf"), "---\r\nname: morpheus\r\n---\r\n");
  await writeSkill(path.join(root, "edited"), "---\nname: morpheus\n---\nnew rule\n");
  await writeSkill(path.join(root, "renamed"), "---\nname: morpheus\n---\n");
  await writeFile(path.join(root, "renamed", "references", "extra.md"), "", "utf8");

  const lf = await hashDirectoryTree(path.join(root, "lf"));
  assert.match(lf, /^[0-9a-f]{64}$/);
  assert.equal(await hashDirectoryTree(path.join(root, "crlf")), lf);
  assert.notEqual(await hashDirectoryTree(path.join(root, "edited")), lf);
  assert.notEqual(await hashDirectoryTree(path.join(root, "renamed")), lf);
});

test("collectBenchmarkProvenance stamps version, skill, prompt, and software provenance outside a git checkout", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-provenance-"));
  const skillPath = await writeSkill(path.join(root, "skills", "morpheus"), "---\nname: morpheus\n---\n");
  await mkdir(path.join(root, "src", "benchmark"), { recursive: true });
  await writeFile(path.join(root, "src", "benchmark", "prompt.ts"), "export const prompt = 1;\n", "utf8");
  await mkdir(path.join(root, "focus"), { recursive: true });
  await writeFile(path.join(root, "focus", "01_Paper.txt"), "Focus on stripes.\n", "utf8");
  await mkdir(path.join(root, "node_modules", "@openai", "codex-sdk"), { recursive: true });
  await writeFile(path.join(root, "node_modules", "@openai", "codex-sdk", "package.json"), '{"version":"0.147.0"}', "utf8");
  await writeFile(
    path.join(root, "package-lock.json"),
    '{"packages":{"node_modules/@openai/codex-sdk":{"version":"0.149.1"}}}',
    "utf8",
  );
  const fakeMorpheus = path.join(root, "fake-morpheus.sh");
  await writeFile(
    fakeMorpheus,
    [
      "#!/bin/sh",
      'case "$1" in',
      '  --version) echo "Version: 2.4.1" ;;',
      '  --revision) echo "Revision: 19.05.2026" ;;',
      '  --gnuplot-version) echo "gnuplot 6.0 patchlevel 0" ;;',
      "esac",
      "",
    ].join("\n"),
    "utf8",
  );
  await chmod(fakeMorpheus, 0o755);
  const fakeUv = path.join(root, "fake-uv.sh");
  await writeFile(fakeUv, "#!/bin/sh\nexit 1\n", "utf8");
  await chmod(fakeUv, 0o755);

  const provenance = await collectBenchmarkProvenance(
    {
      skillPaths: [skillPath, path.join(root, "skills", "missing", "SKILL.md")],
      benchmarkFocusDir: path.join(root, "focus"),
    },
    root,
    { morpheus: fakeMorpheus, python: path.join(root, "missing-python"), uv: fakeUv },
  );

  assert.equal(provenance.benchmarkVersion, BENCHMARK_VERSION);
  assert.equal(provenance.gitCommit, null);
  assert.equal(provenance.gitDirty, null);
  assert.deepEqual(provenance.skills, [
    { name: "morpheus", sha256: await hashDirectoryTree(path.dirname(skillPath)) },
    { name: "missing", sha256: null },
  ]);
  assert.match(provenance.prompts.subjectPromptSourceSha256 ?? "", /^[0-9a-f]{64}$/);
  assert.equal(provenance.prompts.mcpServerSha256, null);
  assert.equal(provenance.prompts.focusSha256, await hashDirectoryTree(path.join(root, "focus")));
  assert.equal(provenance.software.node, process.version);
  assert.equal(provenance.software.codexSdk, "0.147.0");
  assert.equal(provenance.software.codexSdkLocked, "0.149.1");
  assert.equal(provenance.software.codexCli, null);
  if (process.platform !== "win32") {
    assert.equal(provenance.software.morpheus, "2.4.1");
    assert.equal(provenance.software.morpheusRevision, "19.05.2026");
    assert.equal(provenance.software.gnuplot, "gnuplot 6.0 patchlevel 0");
  }
  assert.equal(provenance.software.python, null);
  assert.equal(provenance.software.npmInstalledMatchesLock, false);
  if (process.platform !== "win32") {
    assert.equal(provenance.software.pythonInstalledMatchesLock, false);
  }
});

test("npmInstallMatchesLock compares installed versions and tolerates absent optional packages", () => {
  const lock = {
    packages: {
      "": { name: "morpheus-ai" },
      "node_modules/@openai/codex-sdk": { version: "0.160.0" },
      "node_modules/@openai/codex-darwin-arm64": { version: "0.160.0", optional: true },
    },
  };
  const installed = (version: string) => ({ packages: { "node_modules/@openai/codex-sdk": { version } } });

  assert.equal(npmInstallMatchesLock(lock, installed("0.160.0")), true);
  assert.equal(npmInstallMatchesLock(lock, installed("0.147.0")), false);
  assert.equal(npmInstallMatchesLock(lock, null), false);
  assert.equal(npmInstallMatchesLock(null, installed("0.160.0")), null);
});

test("describeSoftwareDifferences lists changed software fields", () => {
  assert.deepEqual(describeSoftwareDifferences(softwareWith(), softwareWith()), []);
  assert.deepEqual(
    describeSoftwareDifferences(softwareWith(), softwareWith({ morpheus: "2.5.0", python: null })),
    ["morpheus: 2.4.1 -> 2.5.0", "python: 3.12.14 -> unknown"],
  );
  assert.deepEqual(describeSoftwareDifferences(undefined, softwareWith()), []);
});

test("resolveBenchmarkVersion infers versions for runs written before stamping", () => {
  assert.equal(resolveBenchmarkVersion({ benchmarkVersion: 7, benchmarkProtocol: "time_limit_v2" }), 7);
  assert.equal(resolveBenchmarkVersion({ benchmarkProtocol: "time_limit_v2" }), 2);
  assert.equal(resolveBenchmarkVersion({}), 1);
});

test("assertProvenanceAllowsSubjectExecution accepts matching runs and rejects version or skill drift", () => {
  const current = provenanceWith();
  assert.doesNotThrow(() => assertProvenanceAllowsSubjectExecution(
    { benchmarkVersion: BENCHMARK_VERSION, benchmarkProvenance: provenanceWith() },
    current,
  ));
  assert.throws(
    () => assertProvenanceAllowsSubjectExecution({ benchmarkProtocol: "time_limit_v2" }, current),
    /benchmark-v2/,
  );
  assert.throws(
    () => assertProvenanceAllowsSubjectExecution(
      {
        benchmarkVersion: BENCHMARK_VERSION,
        benchmarkProvenance: provenanceWith({ skills: [{ name: "morpheus", sha256: "b".repeat(64) }] }),
      },
      current,
    ),
    /Skill "morpheus" changed/,
  );
  assert.throws(
    () => assertProvenanceAllowsSubjectExecution(
      { benchmarkVersion: BENCHMARK_VERSION, benchmarkProvenance: provenanceWith() },
      provenanceWith({ skills: [{ name: "morpheus", sha256: null }] }),
    ),
    /current missing/,
  );
  assert.throws(
    () => assertProvenanceAllowsSubjectExecution(
      { benchmarkVersion: BENCHMARK_VERSION, benchmarkProvenance: provenanceWith() },
      provenanceWith({ prompts: { subjectPromptSourceSha256: "q".repeat(64), mcpServerSha256: null, focusSha256: null } }),
    ),
    /prompts changed since this run started \(subjectPromptSourceSha256\)/,
  );
  assert.doesNotThrow(() => assertProvenanceAllowsSubjectExecution(
    { benchmarkVersion: BENCHMARK_VERSION, benchmarkProvenance: provenanceWith() },
    provenanceWith({ software: softwareWith({ morpheus: "2.5.0" }) }),
  ));
});
