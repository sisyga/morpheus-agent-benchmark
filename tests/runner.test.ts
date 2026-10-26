/* node:coverage disable */
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, mkdtemp, open, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import test from "node:test";

import {
  BenchmarkRunner,
  canRerunInfrastructureFailure,
  codexServiceFailureKind,
  buildAgentWorkspaceSnapshotDir,
  buildAgentWorkspaceStageFiles,
  buildBenchmarkAgentWorkspaceDir,
  buildBenchmarkCodexEnv,
  buildBenchmarkCodexExecArgs,
  buildCodexExecProcessTreeCleanupPlan,
  buildBenchmarkCodexHomeDir,
  buildBenchmarkCodexHomeConfig,
  buildBenchmarkSkillConfigEntries,
  buildCodexHomeSnapshotDir,
  buildCodexConfig,
  buildBenchmarkComparison,
  combinePaperRunResults,
  buildPaperModeStatistics,
  buildBenchmarkThreadOptions,
  buildBenchmarkRunPaths,
  formatComparisonCsv,
  findLatestRunInfoForJob,
  resolveHostTechnicalEvaluationXmlPath,
  shouldPreflightCommandRunner,
  buildCommandRunnerPreflightPrompt,
  hasSuccessfulCommandExecution,
  shouldRunHostMorpheusBeforeTechnicalEvaluation,
  shouldTimeCommandAsMorpheusSimulation,
  harvestAttemptModelXmlVersions,
  buildMorpheusMcpServerConfig,
  collectCapabilityViolations,
  collectInfrastructureFailures,
  auditAgentMorpheusAttempts,
  reconcileStoredRunAudit,
  countModelRefinementArtifacts,
  expandBenchmarkJobs,
  emptyBenchmarkDiagnostics,
  ensureFailureReproductionReport,
  mergeTurnDiagnostics,
  isSystemicCommandRunnerInfrastructureFailure,
  modelRefinementCountFromManifest,
  mapWithConcurrency,
  normalizeBenchmarkCodexExecStdoutLine,
  prepareBenchmarkCodexHome,
  resolveBenchmarkMaxConcurrentJobs,
  runWithCleanInfrastructureReplacement,
  snapshotBenchmarkCodexHome,
  cleanupBenchmarkTempRunDirs,
  transcriptEventsForTurnError,
} from "../src/benchmark/runner.js";
import { ALL_BENCHMARK_MODES, BENCHMARK_MODE_DEFINITIONS } from "../src/benchmark/modes.js";
import { BENCHMARK_VERSION } from "../src/benchmark/types.js";
import type { BenchmarkConfig, BenchmarkSummary, ReproductionReport } from "../src/benchmark/types.js";
import type { PaperRunResult } from "../src/benchmark/types.js";
import {
  restoreAgentWorkspaceFromSnapshot,
  restoreBenchmarkCodexHomeFromSnapshot,
} from "../src/benchmark/workspace.js";

const flawlessReproduction = {
  source_coverage: { score: 2, evidence: ["paper page 1"], rationale: "Covered sources." },
  mechanism_mapping: { score: 2, evidence: ["model.xml"], rationale: "Mapped mechanisms." },
  observable_alignment: { score: 2, evidence: ["plot_00000.png"], rationale: "Matched outputs." },
  parameter_plausibility: { score: 2, evidence: ["model.xml"], rationale: "Plausible parameters." },
  total_score: 8,
  summary: "Flawless reproduction.",
} satisfies ReproductionReport;

function testBenchmarkConfig(root: string, overrides: Partial<BenchmarkConfig> = {}): BenchmarkConfig {
  return {
    papersDir: path.join(root, "papers"),
    resultsDir: root,
    benchmarkFocusDir: null,
    benchmarkModes: ["morpheus_mcp"],
    benchmarkRepetitions: 1,
    model: "gpt-5.5",
    reasoningEffort: "high",
    totalTimeLimitMs: 14_400_000,
    finalizationReserveMs: 600_000,
    maxConcurrentJobs: 1,
    codexQuotaJobCostPercent: 0,
    pageRenderDpi: 150,
    representativeOutputFrames: 5,
    codexApprovalPolicy: "never",
    codexAllowedEnvVars: [],
    biologicalScoringCriteriaPath: path.join(root, "biological_scoring_criteria.json"),
    biologicalScoringModel: "gpt-5.4-mini",
    biologicalScoringReasoningEffort: "low",
    biologicalScoringMaxConcurrentJobs: 1,
    biologicalScoringTurnTimeoutMs: 5_400_000,
    mcpCommand: ["python", "server.py"],
    mcpToolTimeoutMs: 1_000,
    bridgeToolTimeoutMs: 1_000,
    morpheusRunTimeoutMs: 1_000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: path.join(root, "MorpheusML.xsd"),
    skillPaths: [path.join(root, "skills", "morpheus", "SKILL.md")],
    ...overrides,
  };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function expectedLocalVenvBinDir(): string {
  return path.join(process.cwd(), ".venv", process.platform === "win32" ? "Scripts" : "bin");
}

function expectedLocalVenvPython(): string {
  return path.join(expectedLocalVenvBinDir(), process.platform === "win32" ? "python.exe" : "python");
}

test("buildBenchmarkRunPaths creates a timestamped benchmark master folder", () => {
  const paths = buildBenchmarkRunPaths("benchmark_runs", new Date(2026, 3, 27, 12, 34, 56, 789));

  assert.equal(paths.benchmarkId, "20260427_123456_benchmark");
  assert.equal(paths.benchmarkRunDir, path.join("benchmark_runs", "20260427_123456_benchmark"));
  assert.equal(paths.summaryPath, path.join(paths.benchmarkRunDir, "benchmark_summary.json"));
  assert.equal(paths.manifestPath, path.join(paths.benchmarkRunDir, "benchmark_manifest.json"));
});

test("combineRuns writes progress to the combined benchmark log", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-combine-log-"));
  const runA = path.join(root, "run_a");
  const runB = path.join(root, "run_b");
  const outputDir = path.join(root, "combined");
  const config = testBenchmarkConfig(root);
  const summaryFor = (runDir: string): BenchmarkSummary => ({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    config,
    benchmarkId: path.basename(runDir),
    benchmarkRunDir: runDir,
    comparisonJsonPath: path.join(runDir, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(runDir, "benchmark_comparison.csv"),
    startedAt: "2026-05-08T12:00:00.000Z",
    finishedAt: "2026-05-08T12:01:00.000Z",
    generatedAt: "2026-05-08T12:01:00.000Z",
    durationMs: 60_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    totalRuns: 0,
    uniquePapers: 0,
    benchmarkRepetitions: 1,
    totalPapers: 0,
    agentFinishedRuns: 0,
    timeLimitRuns: 0,
    infrastructureFailureRuns: 0,
    scoreableRuns: 0,
    replacementRuns: 0,
    totalModelRefinements: 0,
    averageModelRefinements: 0,
    averageTechnicalScore: 0,
    averageReproductionScore: 0,
    paperModeStatistics: [],
    results: [],
  });
  await mkdir(runA, { recursive: true });
  await mkdir(runB, { recursive: true });
  await writeFile(path.join(runA, "benchmark_summary.json"), JSON.stringify(summaryFor(runA)), "utf8");
  await writeFile(path.join(runB, "benchmark_summary.json"), JSON.stringify(summaryFor(runB)), "utf8");

  const progress: string[] = [];
  const runner = new BenchmarkRunner(config, { progress: (message) => progress.push(message) });
  await runner.combineRuns([runA, runB], outputDir);

  const benchmarkLog = await readFile(path.join(outputDir, "benchmark.log"), "utf8");
  assert.match(benchmarkLog, /Combining 2 benchmark runs/);
  assert.match(benchmarkLog, /Combined benchmark summary written/);
  assert.ok(progress.some((message) => /Combining 2 benchmark runs/.test(message)));
});

function combinedTestResult(paper: string, mode: PaperRunResult["mode"], repetition: number, runId: string): PaperRunResult {
  return {
    paper,
    pdfPath: `/papers/${paper}`,
    mode,
    modeLabel: BENCHMARK_MODE_DEFINITIONS[mode].label,
    capabilities: BENCHMARK_MODE_DEFINITIONS[mode].capabilities,
    capabilityViolations: [],
    runId,
    threadId: null,
    repetition,
    startedAt: null,
    finishedAt: null,
    durationMs: 0,
    diagnostics: emptyBenchmarkDiagnostics(),
    attempts: 0,
    modelRefinementCount: 0,
    technicalScore: 5,
    reproductionScore: 6,
    technicalEvaluationPath: null,
    reproductionReportPath: null,
    reproductionReportTextPath: null,
    runManifestPath: null,
    benchmarkFocus: null,
    summary: "",
    assignmentId: `${paper.replace(/\.pdf$/, "")}__${mode}__rep${String(repetition).padStart(2, "0")}`,
  };
}

test("combinePaperRunResults appends overlapping repetitions instead of overwriting them", () => {
  const combined = combinePaperRunResults([
    {
      sourceBenchmarkRunDir: "/runs/a",
      results: [
        combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "a_szabo_mcp_1"),
        combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 2, "a_szabo_mcp_2"),
        combinedTestResult("02_Thapa2024.pdf", "morpheus_mcp", 1, "a_thapa_mcp_1"),
      ],
    },
    {
      sourceBenchmarkRunDir: "/runs/b",
      results: [
        combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "b_szabo_mcp_1"),
        combinedTestResult("01_Szabo2010.pdf", "python_web", 1, "b_szabo_web_1"),
      ],
    },
  ]);

  assert.deepEqual(
    combined.map((result) => [result.runId, result.repetition, result.sourceRepetition, result.sourceBenchmarkRunDir]),
    [
      ["a_szabo_mcp_1", 1, 1, "/runs/a"],
      ["a_szabo_mcp_2", 2, 2, "/runs/a"],
      ["a_thapa_mcp_1", 1, 1, "/runs/a"],
      ["b_szabo_mcp_1", 3, 1, "/runs/b"],
      ["b_szabo_web_1", 1, 1, "/runs/b"],
    ],
  );
  assert.equal(combined[3].assignmentId, "01_Szabo2010__morpheus_mcp__rep03");
  assert.equal(combined[4].assignmentId, "01_Szabo2010__python_web__rep01");
});

test("combineRuns keeps both runs, reports the source cohort config, and rejects repeated folders", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-combine-cohort-"));
  const runA = path.join(root, "run_a");
  const runB = path.join(root, "run_b");
  const outputDir = path.join(root, "combined");
  const sourceConfig = testBenchmarkConfig(root, { model: "gpt-5.5", reasoningEffort: "xhigh" });
  const summaryFor = (runDir: string, result: PaperRunResult): BenchmarkSummary => ({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    biologicalScorerVersion: 8,
    config: sourceConfig,
    benchmarkId: path.basename(runDir),
    benchmarkRunDir: runDir,
    comparisonJsonPath: path.join(runDir, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(runDir, "benchmark_comparison.csv"),
    startedAt: "2026-05-08T12:00:00.000Z",
    finishedAt: "2026-05-08T12:01:00.000Z",
    generatedAt: "2026-05-08T12:01:00.000Z",
    durationMs: 60_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    totalRuns: 1,
    uniquePapers: 1,
    benchmarkRepetitions: 1,
    totalPapers: 1,
    agentFinishedRuns: 0,
    timeLimitRuns: 0,
    infrastructureFailureRuns: 0,
    scoreableRuns: 0,
    replacementRuns: 0,
    totalModelRefinements: 0,
    averageModelRefinements: 0,
    averageTechnicalScore: 0,
    averageReproductionScore: 0,
    paperModeStatistics: [],
    results: [result],
  });
  await mkdir(runA, { recursive: true });
  await mkdir(runB, { recursive: true });
  await writeFile(
    path.join(runA, "benchmark_summary.json"),
    JSON.stringify(summaryFor(runA, combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "run_a_szabo"))),
    "utf8",
  );
  await writeFile(
    path.join(runB, "benchmark_summary.json"),
    JSON.stringify(summaryFor(runB, combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "run_b_szabo"))),
    "utf8",
  );
  const runner = new BenchmarkRunner(testBenchmarkConfig(root, { model: "gpt-5.6-sol", reasoningEffort: "high" }));

  const summary = await runner.combineRuns([runA, runB], outputDir);

  assert.deepEqual(summary.results.map((result) => [result.runId, result.repetition]), [
    ["run_a_szabo", 1],
    ["run_b_szabo", 2],
  ]);
  assert.equal(summary.config.model, "gpt-5.5");
  assert.equal(summary.config.reasoningEffort, "xhigh");
  assert.equal(summary.config.benchmarkRepetitions, 2);
  assert.equal(summary.biologicalScorerVersion, 8);
  assert.equal(summary.paperModeStatistics[0].observedRepetitions, 2);
  await assert.rejects(runner.combineRuns([runA, `${runA}${path.sep}`], outputDir), /same benchmark run directory/);

  const runC = path.join(root, "run_c");
  await mkdir(runC, { recursive: true });
  await writeFile(
    path.join(runC, "benchmark_summary.json"),
    JSON.stringify({
      ...summaryFor(runC, combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "run_c_szabo")),
      benchmarkVersion: BENCHMARK_VERSION,
    }),
    "utf8",
  );
  await assert.rejects(runner.combineRuns([runA, runC], outputDir), /mixed benchmark cohorts/);

  const runD = path.join(root, "run_d");
  await mkdir(runD, { recursive: true });
  await writeFile(
    path.join(runD, "benchmark_summary.json"),
    JSON.stringify({
      ...summaryFor(runD, combinedTestResult("01_Szabo2010.pdf", "morpheus_mcp", 1, "run_d_szabo")),
      benchmarkVersion: BENCHMARK_VERSION,
      benchmarkProvenance: {
        prompts: { subjectPromptSourceSha256: "edited", mcpServerSha256: null, focusSha256: null },
      },
    }),
    "utf8",
  );
  await assert.rejects(runner.combineRuns([runC, runD], outputDir), /mixed benchmark cohorts/);
});

test("buildBenchmarkThreadOptions enables live web search for benchmark agents", () => {
  const runDir = path.join("benchmark_runs", "run_123");
  const agentWorkspaceDir = path.join("agent_workspaces", "run_123");
  const options = buildBenchmarkThreadOptions(
    {
      model: "gpt-5.5",
      reasoningEffort: "high",
      codexApprovalPolicy: "never",
    },
    runDir,
    agentWorkspaceDir,
  );

  assert.equal(options.model, "gpt-5.5");
  assert.equal(options.modelReasoningEffort, "high");
  assert.equal(options.approvalPolicy, "never");
  assert.equal(options.networkAccessEnabled, undefined);
  assert.equal(options.webSearchMode, "live");
  assert.equal(options.workingDirectory, path.resolve(agentWorkspaceDir));
  assert.equal(options.additionalDirectories, undefined);
  assert.equal(options.sandboxMode, undefined);
  assert.equal(options.skipGitRepoCheck, true);
});

test("buildBenchmarkThreadOptions disables internet access for docs-only CLI mode", () => {
  const options = buildBenchmarkThreadOptions(
    {
      model: "gpt-5.5",
      reasoningEffort: "high",
      codexApprovalPolicy: "never",
    },
    path.join("benchmark_runs", "run_docs"),
    path.join("agent_workspaces", "run_docs"),
    "morpheus_cli_docs",
  );

  assert.equal(options.networkAccessEnabled, undefined);
  assert.equal(options.webSearchMode, "disabled");
});

test("buildBenchmarkAgentWorkspaceDir keeps benchmark subjects outside the repo tree", () => {
  assert.equal(
    buildBenchmarkAgentWorkspaceDir(path.join("benchmark_runs", "20260430_170702_benchmark", "run_123")),
    path.join(tmpdir(), "morpheus-modeling-sessions", "20260430_170702_session", "run_123"),
  );
});

test("buildBenchmarkCodexHomeDir keeps subject Codex config outside the repo and host run directory", () => {
  assert.equal(
    buildBenchmarkCodexHomeDir(path.join("benchmark_runs", "20260430_170702_benchmark", "run_123")),
    path.join(tmpdir(), "morpheus-modeling-codex-home", "20260430_170702_session", "run_123"),
  );
});

test("cleanupBenchmarkTempRunDirs removes only benchmark subject temp directories", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-cleanup-safety-"));
  const uniqueSession = `${path.basename(root)}_session`;
  const agentWorkspaceDir = path.join(tmpdir(), "morpheus-modeling-sessions", uniqueSession, "run_123");
  const codexHomeDir = path.join(tmpdir(), "morpheus-modeling-codex-home", uniqueSession, "run_123");
  const unrelatedDir = path.join(root, "not-a-benchmark-temp-run");

  await mkdir(agentWorkspaceDir, { recursive: true });
  await mkdir(codexHomeDir, { recursive: true });
  await mkdir(unrelatedDir, { recursive: true });
  await writeFile(path.join(agentWorkspaceDir, "marker.txt"), "agent", "utf8");
  await writeFile(path.join(codexHomeDir, "marker.txt"), "codex", "utf8");
  await writeFile(path.join(unrelatedDir, "marker.txt"), "keep", "utf8");

  await cleanupBenchmarkTempRunDirs([agentWorkspaceDir, codexHomeDir, unrelatedDir]);

  await assert.rejects(() => readFile(path.join(agentWorkspaceDir, "marker.txt"), "utf8"));
  await assert.rejects(() => readFile(path.join(codexHomeDir, "marker.txt"), "utf8"));
  assert.equal(await readFile(path.join(unrelatedDir, "marker.txt"), "utf8"), "keep");

  await rm(root, { recursive: true, force: true });
});

test("buildBenchmarkCodexHomeConfig gives subjects a minimal permission profile and disables extension surfaces", () => {
  const codexHomeDir = path.resolve("codex_homes", "run_123");
  const deadlinePath = path.resolve("benchmark_runs", "run_123", "subject_deadline.json");
  const realMorpheusBin = path.resolve("host_tools", "morpheus");
  const pythonRuntimeAlias = path.resolve("uv_python", "cpython-3.12-linux-x86_64-gnu");
  const pythonRuntimeRoot = path.resolve("uv_python", "cpython-3.12.14-linux-x86_64-gnu");
  const systemPython = path.resolve("system", "bin", "python3.12");
  const systemStdlib = path.resolve("system", "lib", "python3.12");
  const config = buildBenchmarkCodexHomeConfig(
    path.join("agent_workspaces", "20260430_170702_benchmark", "run_123"),
    [],
    {
      mode: "python_web",
      codexHomeDir,
      benchmarkDeadlinePath: deadlinePath,
      realMorpheusBin,
      pythonRuntimeReadPaths: [pythonRuntimeAlias, pythonRuntimeRoot],
      systemPythonDenyPaths: [systemPython, systemStdlib],
    },
  );

  assert.match(config, /approval_policy = "never"/);
  assert.match(config, /default_permissions = "benchmark-subject"/);
  assert.doesNotMatch(config, /sandbox_mode =/);
  assert.match(config, /\[windows\]\nsandbox = "elevated"/);
  assert.match(config, /apps = false/);
  assert.match(config, /plugins = false/);
  assert.match(config, /remote_plugin = false/);
  assert.match(config, /\[permissions\.benchmark-subject\.filesystem\]/);
  assert.match(config, /":minimal" = "read"/);
  assert.match(
    config,
    new RegExp(
      `${escapeRegExp(JSON.stringify(path.resolve("agent_workspaces", "20260430_170702_benchmark", "run_123")))} = "write"`,
    ),
  );
  assert.match(
    config,
    new RegExp(`${escapeRegExp(JSON.stringify(path.join(codexHomeDir, "benchmark-tools")))} = "read"`),
  );
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(deadlinePath))} = "read"`));
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(path.resolve(".venv")))} = "read"`));
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(pythonRuntimeAlias))} = "read"`));
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(pythonRuntimeRoot))} = "read"`));
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(systemPython))} = "deny"`));
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(systemStdlib))} = "deny"`));
  assert.equal(config.match(/= "write"/g)?.length, 1, "only the agent workspace is writable");
  assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(realMorpheusBin))} = "deny"`));
  assert.doesNotMatch(
    config,
    new RegExp(escapeRegExp(JSON.stringify(path.join(codexHomeDir, "skills", "morpheus")))),
  );
  assert.match(config, /\[shell_environment_policy\]\ninherit = "all"/);
  assert.match(config, /ignore_default_excludes = false/);
  assert.doesNotMatch(config, /include_only = \[/);
  assert.match(
    config,
    new RegExp(escapeRegExp(`[projects.'${path.resolve("agent_workspaces", "20260430_170702_benchmark")}']`)),
  );
  assert.doesNotMatch(config, /\.agents/);
  assert.doesNotMatch(config, /skills\/\.system|skills\\\.system/i);
  assert.doesNotMatch(config, /superpowers/i);
});

test("buildBenchmarkCodexHomeConfig grants only intended staged skill and CLI resources by mode", () => {
  const agentWorkspaceDir = path.resolve("agent_workspaces", "run_123");
  const codexHomeDir = path.resolve("codex_homes", "run_123");
  const realMorpheusBin = path.resolve("host_tools", "morpheus");
  const deadlinePath = path.resolve("benchmark_runs", "run_123", "subject_deadline.json");

  for (const mode of ALL_BENCHMARK_MODES) {
    const config = buildBenchmarkCodexHomeConfig(agentWorkspaceDir, [], {
      mode,
      codexHomeDir,
      benchmarkDeadlinePath: deadlinePath,
      realMorpheusBin,
    });
    const capabilities = BENCHMARK_MODE_DEFINITIONS[mode].capabilities;
    const skillPath = JSON.stringify(path.join(codexHomeDir, "skills", "morpheus"));
    const binaryRule = `${JSON.stringify(realMorpheusBin)} = `;

    assert.equal(
      config.includes(`${skillPath} = "read"`),
      capabilities.morpheusSkill,
      `${mode} staged skill access`,
    );
    assert.equal(config.includes(`${binaryRule}"read"`), capabilities.morpheusCli, `${mode} CLI access`);
    assert.equal(config.includes(`${binaryRule}"deny"`), !capabilities.morpheusCli, `${mode} CLI denial`);
  }
});

test("buildBenchmarkCodexHomeConfig applies Morpheus access to every executable alias", () => {
  const aliases = [path.resolve("usr", "bin", "morpheus"), path.resolve("bin", "morpheus")];
  const config = buildBenchmarkCodexHomeConfig(
    path.resolve("agent_workspaces", "run_123"),
    [],
    {
      mode: "python_web",
      codexHomeDir: path.resolve("codex_homes", "run_123"),
      benchmarkDeadlinePath: path.resolve("benchmark_runs", "run_123", "subject_deadline.json"),
      realMorpheusBin: aliases[0],
      realMorpheusBinPaths: aliases,
    },
  );

  for (const alias of aliases) {
    assert.match(config, new RegExp(`${escapeRegExp(JSON.stringify(alias))} = "deny"`));
  }
});

test("buildBenchmarkCodexHomeConfig leaves explicit env filtering to the Codex process env", () => {
  const config = buildBenchmarkCodexHomeConfig(
    path.join("agent_workspaces", "20260430_170702_benchmark", "run_123"),
    ["BENCHMARK_SAFE_FLAG"],
  );

  assert.doesNotMatch(config, /BENCHMARK_SAFE_FLAG/);
  assert.doesNotMatch(config, /include_only = \[/);
});

test("buildBenchmarkSkillConfigEntries preserves source paths without isolated Codex home", () => {
  assert.deepEqual(
    buildBenchmarkSkillConfigEntries([
      path.join("repo", ".agents", "skills", "morpheus", "SKILL.md"),
    ]),
    [
      {
        path: path.join("repo", ".agents", "skills", "morpheus", "SKILL.md"),
        enabled: true,
      },
    ],
  );
});

test("buildBenchmarkSkillConfigEntries disables system skills in isolated Codex homes", () => {
  const codexHomeDir = path.join("tmp", "codex_home");
  const entries = buildBenchmarkSkillConfigEntries(
    [path.join("repo", ".agents", "skills", "morpheus", "SKILL.md")],
    codexHomeDir,
  );

  assert.ok(entries.some((entry) =>
    entry.enabled === false && entry.path === path.join(codexHomeDir, "skills", ".system", "skill-creator", "SKILL.md")
  ));
  assert.deepEqual(entries.at(-1), {
    path: path.join(codexHomeDir, "skills", "morpheus", "SKILL.md"),
    enabled: true,
  });
});

test("prepareBenchmarkCodexHome stages configured benchmark skills under the isolated home", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-codex-home-skills-"));
  const sourceSkillDir = path.join(root, ".agents", "skills", "morpheus");
  const codexHome = path.join(root, "codex_home");
  const agentWorkspaceDir = path.join(root, "agent_workspace");
  await mkdir(path.join(sourceSkillDir, "references"), { recursive: true });
  await mkdir(agentWorkspaceDir, { recursive: true });
  await mkdir(path.join(codexHome, "skills", "stale-skill"), { recursive: true });
  await writeFile(path.join(sourceSkillDir, "SKILL.md"), "---\nname: morpheus\n---\n# Morpheus\n", "utf8");
  await writeFile(path.join(sourceSkillDir, "references", "morpheusml-doc.md"), "# MorpheusML\n", "utf8");
  await writeFile(path.join(codexHome, "skills", "stale-skill", "SKILL.md"), "# Stale\n", "utf8");

  await prepareBenchmarkCodexHome(codexHome, agentWorkspaceDir, [path.join(sourceSkillDir, "SKILL.md")]);

  assert.equal(
    await readFile(path.join(codexHome, "skills", "morpheus", "SKILL.md"), "utf8"),
    "---\nname: morpheus\n---\n# Morpheus\n",
  );
  assert.equal(
    await readFile(path.join(codexHome, "skills", "morpheus", "references", "morpheusml-doc.md"), "utf8"),
    "# MorpheusML\n",
  );
  await assert.rejects(() => readFile(path.join(codexHome, "skills", "stale-skill", "SKILL.md"), "utf8"));
  assert.match(await readFile(path.join(codexHome, "config.toml"), "utf8"), /sandbox_mode = "workspace-write"/);
});

test("buildBenchmarkCodexExecArgs disables inherited exec-policy rules without hiding benchmark config", () => {
  const args = buildBenchmarkCodexExecArgs(
    {
      model: "gpt-5.5",
      sandboxMode: "workspace-write",
      windowsSandboxMode: "elevated",
      workingDirectory: path.resolve("agent_workspaces", "run_123"),
      skipGitRepoCheck: true,
      modelReasoningEffort: "high",
      networkAccessEnabled: true,
      webSearchMode: "live",
      approvalPolicy: "never",
      threadId: "thread_123",
    },
    { skills: { config: [] } },
  );

  assert.deepEqual(args.slice(0, 3), ["exec", "--experimental-json", "--ignore-rules"]);
  assert.equal(args.includes("--full-auto"), false);
  assert.equal(args.includes("--ignore-user-config"), false);
  assert.ok(args.includes('skills.config=[]'));
  assert.ok(args.includes('approval_policy="never"'));
  assert.ok(args.includes('windows.sandbox="elevated"'));
  assert.ok(args.indexOf("--ignore-rules") < args.indexOf("resume"));
});

test("buildBenchmarkCodexExecArgs serializes optional args and config overrides", () => {
  const args = buildBenchmarkCodexExecArgs(
    {
      baseUrl: "https://api.example.test/v1",
      model: "gpt-5.5",
      sandboxMode: "workspace-write",
      workingDirectory: "/work",
      additionalDirectories: ["/data", "/scratch"],
      outputSchemaFile: "/schema.json",
      networkAccessEnabled: false,
      webSearchEnabled: true,
      approvalPolicy: "never",
    },
    {
      nested: { enabled: true, count: 2, labels: ["a", "b"], empty: {}, skipped: undefined },
    },
  );

  assert.ok(args.includes("openai_base_url=\"https://api.example.test/v1\""));
  assert.ok(args.includes("--model"));
  assert.ok(args.includes("gpt-5.5"));
  assert.ok(args.includes("--cd"));
  assert.ok(args.includes("/work"));
  assert.equal(args.filter((value) => value === "--add-dir").length, 2);
  assert.ok(args.includes("/data"));
  assert.ok(args.includes("/scratch"));
  assert.ok(args.includes("--output-schema"));
  assert.ok(args.includes("/schema.json"));
  assert.ok(args.includes("sandbox_workspace_write.network_access=false"));
  assert.ok(args.includes('web_search="live"'));
  assert.ok(args.includes("nested.enabled=true"));
  assert.ok(args.includes("nested.count=2"));
  assert.ok(args.includes('nested.labels=["a", "b"]'));
  assert.ok(args.includes("nested.empty={}"));
  assert.equal(args.some((value) => value.includes("skipped")), false);
});

test("buildBenchmarkCodexExecArgs forwards local images like the SDK executor", () => {
  const args = buildBenchmarkCodexExecArgs({ threadId: "thread-1", images: ["/a.png", "/b.png"] });

  assert.deepEqual(args.slice(-6), ["resume", "thread-1", "--image", "/a.png", "--image", "/b.png"]);
  assert.equal(buildBenchmarkCodexExecArgs({}).includes("--image"), false);
});

test("buildBenchmarkCodexExecArgs handles disabled web search and empty config overrides", () => {
  const args = buildBenchmarkCodexExecArgs(
    {
      skipGitRepoCheck: true,
      outputSchemaFile: "schema.json",
      webSearchMode: "disabled",
    },
    {},
  );

  assert.ok(args.includes("--skip-git-repo-check"));
  assert.ok(args.includes("--output-schema"));
  assert.ok(args.includes("schema.json"));
  assert.ok(args.includes('web_search="disabled"'));
  assert.equal(args.filter((value) => value === "--config").length, 1);
});

test("buildBenchmarkCodexExecArgs validates config override shapes and TOML values", () => {
  assert.throws(
    () => buildBenchmarkCodexExecArgs({}, "bad" as any),
    /Codex config overrides must be a plain object/,
  );
  assert.throws(
    () => buildBenchmarkCodexExecArgs({}, { "": true }),
    /override keys must be non-empty strings/,
  );
  assert.throws(
    () => buildBenchmarkCodexExecArgs({}, { nested: { bad: Number.POSITIVE_INFINITY } }),
    /nested\.bad must be a finite number/,
  );
  assert.throws(
    () => buildBenchmarkCodexExecArgs({}, { nested: null as any }),
    /Unsupported Codex config override value at nested: null/,
  );

  const args = buildBenchmarkCodexExecArgs(
    {},
    { tools: [{ "quoted.key": "value", enabled: true }, { path: "plain" }] },
  );

  assert.ok(args.includes('tools=[{"quoted.key" = "value", enabled = true}, {path = "plain"}]'));
});

test("normalizeBenchmarkCodexExecStdoutLine drops Windows taskkill cleanup chatter", () => {
  const eventLine = '{"type":"turn.completed","usage":{"input_tokens":1}}';

  assert.equal(normalizeBenchmarkCodexExecStdoutLine(eventLine), eventLine);
  assert.equal(
    normalizeBenchmarkCodexExecStdoutLine(
      "SUCCESS: The process with PID 3840 (child process of PID 7612) has been terminated.",
    ),
    null,
  );
  assert.equal(
    normalizeBenchmarkCodexExecStdoutLine("SUCCESS: Sent termination signal to the process with PID 3840."),
    null,
  );
});

test("buildCodexExecProcessTreeCleanupPlan targets the whole subprocess tree", () => {
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(1234, "win32", "SIGTERM"), {
    kind: "taskkill",
    command: "taskkill.exe",
    args: ["/PID", "1234", "/T"],
  });
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(1234, "linux", "SIGTERM"), {
    kind: "process-group",
    pid: -1234,
    signal: "SIGTERM",
  });
});

test("buildCodexExecProcessTreeCleanupPlan force-kills Windows trees for SIGKILL", () => {
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(1234, "win32", "SIGKILL"), {
    kind: "taskkill",
    command: "taskkill.exe",
    args: ["/PID", "1234", "/T", "/F"],
  });
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(1234, "linux", "SIGKILL"), {
    kind: "process-group",
    pid: -1234,
    signal: "SIGKILL",
  });
});

test("buildAgentWorkspaceStageFiles resolves relative bridge artifacts against host run directory", () => {
  const hostRunDir = path.join("benchmark_runs", "run_123");
  const agentWorkspaceDir = path.join("agent_workspaces", "run_123");

  assert.deepEqual(
    buildAgentWorkspaceStageFiles({
      agentWorkspaceDir,
      runDir: hostRunDir,
      pdfPath: path.join("benchmark_papers", "paper.pdf"),
      paperTextPath: "paper.txt",
      visualManifestPath: "paper_visual_manifest.json",
    }),
    {
      sourcePdfPath: path.join("benchmark_papers", "paper.pdf"),
      sourcePaperTextPath: path.join(hostRunDir, "paper.txt"),
      sourceVisualManifestPath: path.join(hostRunDir, "paper_visual_manifest.json"),
      agentPdfPath: path.join(agentWorkspaceDir, "paper.pdf"),
      agentPaperTextPath: path.join(agentWorkspaceDir, "paper.txt"),
      agentVisualManifestPath: path.join(agentWorkspaceDir, "paper_visual_manifest.json"),
    },
  );
});

test("buildAgentWorkspaceStageFiles stages docs-only Morpheus references for the docs CLI mode", () => {
  const files = buildAgentWorkspaceStageFiles({
    agentWorkspaceDir: path.join("agent_workspaces", "run_docs"),
    runDir: path.join("benchmark_runs", "run_docs"),
    pdfPath: path.join("benchmark_papers", "paper.pdf"),
    paperTextPath: "paper.txt",
    visualManifestPath: "paper_visual_manifest.json",
    mode: "morpheus_cli_docs",
  });

  assert.ok("sourceMorpheusMlDocPath" in files);
  assert.equal(
    files.sourceMorpheusMlDocPath,
    path.resolve(process.cwd(), ".agents", "skills", "morpheus", "references", "morpheusml-doc.md"),
  );
  assert.equal(
    files.sourceModelTemplatePath,
    path.resolve(process.cwd(), ".agents", "skills", "morpheus", "references", "model-template.md"),
  );
  assert.equal(files.agentMorpheusMlDocPath, path.join("agent_workspaces", "run_docs", "morpheusml_doc.txt"));
  assert.equal(files.agentModelTemplatePath, path.join("agent_workspaces", "run_docs", "model_template.txt"));
});

test("restoreAgentWorkspaceFromSnapshot restores an existing workspace snapshot directory", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-agent-workspace-restore-"));
  const runDir = path.join(root, "run_123");
  const snapshotDir = buildAgentWorkspaceSnapshotDir(runDir);
  const agentWorkspaceDir = path.join(root, "agent_workspace_live");
  await mkdir(snapshotDir, { recursive: true });
  await writeFile(path.join(snapshotDir, "model.xml"), "<MorpheusModel/>", "utf8");

  await restoreAgentWorkspaceFromSnapshot(runDir, agentWorkspaceDir);

  assert.equal(await readFile(path.join(agentWorkspaceDir, "model.xml"), "utf8"), "<MorpheusModel/>");
});

test("buildBenchmarkCodexEnv isolates benchmark agents from host secrets while preserving required runtime env", () => {
  const venvBinDir = expectedLocalVenvBinDir();
  const codexHome = path.join(tmpdir(), "morpheus-modeling-codex-home", "run_123");
  const deadlinePath = path.join(tmpdir(), "morpheus-modeling-deadline", "subject_deadline.json");
  const baseEnv = {
    Path: [
      "C:\\Windows\\System32",
      "C:\\Program Files\\Morpheus\\bin",
      "C:\\Python312",
    ].join(path.delimiter),
    PATH: [
      "C:\\Windows\\System32",
      "C:\\Program Files\\Morpheus\\bin",
      "C:\\Python312",
    ].join(path.delimiter),
    MORPHEUS_HOME: "C:\\Program Files\\Morpheus",
    MORPHEUS_BIN: "C:\\Program Files\\Morpheus\\bin\\morpheus.exe",
    OPENAI_API_KEY: "test-key",
    GITHUB_TOKEN: "github-token",
    AWS_SECRET_ACCESS_KEY: "aws-secret",
    BENCHMARK_SAFE_FLAG: "1",
    SystemRoot: "C:\\Windows",
    ComSpec: "C:\\Windows\\System32\\cmd.exe",
    TEMP: "C:\\Users\\simon\\AppData\\Local\\Temp",
  };

  const env = buildBenchmarkCodexEnv(
    baseEnv,
    "morpheus_cli",
    codexHome,
    undefined,
    // Secret-looking names stay stripped even when someone allow-lists them.
    ["BENCHMARK_SAFE_FLAG", "OPENAI_API_KEY", "GITHUB_TOKEN"],
    null,
    deadlinePath,
  );

  assert.equal(env.CODEX_HOME, codexHome);
  assert.equal(env.BENCHMARK_DEADLINE_PATH, deadlinePath);
  assert.equal("CODEX_EXEC_TURN_TIMEOUT_MS" in env, false);
  assert.equal(env.VIRTUAL_ENV, path.join(process.cwd(), ".venv"));
  assert.equal(env.BENCHMARK_SAFE_FLAG, "1");
  assert.equal(env.MORPHEUS_BIN, baseEnv.MORPHEUS_BIN);
  assert.equal(env.SystemRoot, baseEnv.SystemRoot);
  assert.equal(env.ComSpec, baseEnv.ComSpec);
  assert.equal(env.TEMP, baseEnv.TEMP);
  assert.equal(env.Path, [venvBinDir, baseEnv.Path].join(path.delimiter));
  assert.equal(env.PATH, [venvBinDir, baseEnv.PATH].join(path.delimiter));
  assert.equal("OPENAI_API_KEY" in env, false);
  assert.equal("GITHUB_TOKEN" in env, false);
  assert.equal("AWS_SECRET_ACCESS_KEY" in env, false);
  assert.equal("MORPHEUS_HOME" in env, false);
});

test("buildBenchmarkCodexEnv hides Morpheus executables from python_web path without naming them in the prompt", () => {
  const venvBinDir = expectedLocalVenvBinDir();
  const codexHome = path.join(tmpdir(), "morpheus-modeling-codex-home", "run_123");
  const systemBinDir = path.join(tmpdir(), "system32");
  const morpheusBinDir = path.join(tmpdir(), "Morpheus", "bin");
  const pythonBinDir = path.join(tmpdir(), "python312");
  const baseEnv = {
    Path: [systemBinDir, morpheusBinDir, pythonBinDir].join(path.delimiter),
    PATH: [systemBinDir, morpheusBinDir, pythonBinDir].join(path.delimiter),
    MORPHEUS_BIN: path.join(morpheusBinDir, "morpheus"),
  };

  const env = buildBenchmarkCodexEnv(baseEnv, "python_web", codexHome, 123_000);

  assert.equal(env.Path, [venvBinDir, systemBinDir, pythonBinDir].join(path.delimiter));
  assert.equal(env.PATH, [venvBinDir, systemBinDir, pythonBinDir].join(path.delimiter));
  assert.equal("MORPHEUS_BIN" in env, false);
});

test("buildBenchmarkCodexEnv sets Morpheus thread env for Morpheus CLI modes", () => {
  const codexHome = path.join(tmpdir(), "morpheus-modeling-codex-home", "run_123");
  const env = buildBenchmarkCodexEnv(
    { PATH: "/usr/bin", MORPHEUS_BIN: "/usr/bin/morpheus" },
    "morpheus_cli",
    codexHome,
    123_000,
    [],
    4,
  );

  assert.equal(env.OMP_NUM_THREADS, "4");
  assert.equal(env.MORPHEUS_NUM_THREADS, "4");
});

test("buildMorpheusMcpServerConfig auto-approves only the Morpheus MCP server tools", () => {
  const deadlinePath = path.join("benchmark_runs", "run_123", "subject_deadline.json");
  const server = buildMorpheusMcpServerConfig(
    {
      mcpCommand: ["python", "server.py"],
      resultsDir: "benchmark_runs",
      mcpToolTimeoutMs: 3_600_000,
      morpheusRunTimeoutMs: 3_600_000,
      morpheusNumThreads: null,
      morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    },
    "run_123",
    undefined,
    deadlinePath,
    "/opt/morpheus/bin/morpheus",
  );

  assert.deepEqual(server, {
    command: expectedLocalVenvPython(),
    args: [path.resolve(process.cwd(), "server.py")],
    default_tools_approval_mode: "approve",
    tool_timeout_sec: 3600,
    env: {
      MORPHEUS_RUNS_DIR: "benchmark_runs",
      MORPHEUS_ACTIVE_RUN_ID: "run_123",
      MORPHEUS_RUN_TIMEOUT_MS: "3600000",
      MORPHEUS_BIN: "/opt/morpheus/bin/morpheus",
      BENCHMARK_DEADLINE_PATH: path.resolve(deadlinePath),
      MORPHEUS_XML_SCHEMA_PATH: path.resolve(process.cwd(), "src/benchmark/MorpheusML.xsd"),
    },
  });
});

test("buildMorpheusMcpServerConfig passes configured Morpheus thread count", () => {
  const server = buildMorpheusMcpServerConfig(
    {
      mcpCommand: ["python", "server.py"],
      resultsDir: "benchmark_runs",
      mcpToolTimeoutMs: 3_600_000,
      morpheusRunTimeoutMs: 3_600_000,
      morpheusNumThreads: 4,
      morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    },
    "run_123",
  );

  const env = server.env as Record<string, string>;
  assert.equal(env["MORPHEUS_NUM_THREADS"], "4");
  assert.equal(env["OMP_NUM_THREADS"], "4");
});

test("buildMorpheusMcpServerConfig can scope MCP tools to a neutral agent workspace", () => {
  const agentWorkspaceDir = path.join(
    tmpdir(),
    "morpheus-modeling-sessions",
    "20260508_120000_session",
    "20260508_140000_paper__morpheus_mcp",
  );
  const server = buildMorpheusMcpServerConfig(
    {
      mcpCommand: ["python", "server.py"],
      resultsDir: "benchmark_runs",
      mcpToolTimeoutMs: 3_600_000,
      morpheusRunTimeoutMs: 3_600_000,
      morpheusNumThreads: null,
      morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    },
    "20260508_140000_paper__morpheus_mcp",
    agentWorkspaceDir,
  );

  assert.equal(server.env.MORPHEUS_RUNS_DIR, path.dirname(agentWorkspaceDir));
  assert.equal(server.env.MORPHEUS_ACTIVE_RUN_ID, path.basename(agentWorkspaceDir));
});

test("buildCodexConfig enables only the requested mode capabilities", () => {
  const baseConfig = {
    mcpCommand: ["python", "server.py"],
    resultsDir: "benchmark_runs",
    mcpToolTimeoutMs: 3_600_000,
    morpheusRunTimeoutMs: 3_600_000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    skillPaths: ["C:/repo/.agents/skills/morpheus/SKILL.md"],
  };
  const codexHomeDir = path.join("C:/tmp", "codex_home");
  const windowsSandbox = {
    windows: {
      sandbox: "elevated",
    },
  };
  const disabledSystemSkills = buildBenchmarkSkillConfigEntries([], codexHomeDir);
  const morpheusSkill = {
    path: path.join(codexHomeDir, "skills", "morpheus", "SKILL.md"),
    enabled: true,
  };

  assert.deepEqual(buildCodexConfig(baseConfig, "python_web", "run_123", undefined, codexHomeDir), {
    ...windowsSandbox,
    skills: {
      config: disabledSystemSkills,
    },
  });
  assert.deepEqual(buildCodexConfig(baseConfig, "morpheus_cli", "run_123", undefined, codexHomeDir), {
    ...windowsSandbox,
    skills: {
      config: disabledSystemSkills,
    },
  });
  assert.deepEqual(buildCodexConfig(baseConfig, "morpheus_cli_docs", "run_123", undefined, codexHomeDir), {
    ...windowsSandbox,
    skills: {
      config: disabledSystemSkills,
    },
  });
  assert.deepEqual(buildCodexConfig(baseConfig, "morpheus_skill", "run_123", undefined, codexHomeDir), {
    ...windowsSandbox,
    skills: {
      config: [...disabledSystemSkills, morpheusSkill],
    },
  });
  assert.deepEqual(buildCodexConfig(baseConfig, "morpheus_mcp", "run_123", undefined, codexHomeDir), {
    ...windowsSandbox,
    mcp_servers: {
      morpheus: buildMorpheusMcpServerConfig(baseConfig, "run_123"),
    },
    skills: {
      config: [...disabledSystemSkills, morpheusSkill],
    },
  });
});

test("buildCodexConfig points Morpheus MCP at the agent workspace when one is provided", () => {
  const baseConfig = {
    mcpCommand: ["python", "server.py"],
    resultsDir: "benchmark_runs",
    mcpToolTimeoutMs: 3_600_000,
    morpheusRunTimeoutMs: 3_600_000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    skillPaths: ["C:/repo/.agents/skills/morpheus/SKILL.md"],
  };
  const agentWorkspaceDir = path.join(
    tmpdir(),
    "morpheus-modeling-sessions",
    "20260508_120000_session",
    "20260508_140000_paper__morpheus_mcp",
  );

  const config = buildCodexConfig(
    baseConfig,
    "morpheus_mcp",
    "20260508_140000_paper__morpheus_mcp",
    agentWorkspaceDir,
  );

  assert.equal(
    (config.mcp_servers as any).morpheus.env.MORPHEUS_RUNS_DIR,
    path.dirname(agentWorkspaceDir),
  );
  assert.equal(
    (config.mcp_servers as any).morpheus.env.MORPHEUS_ACTIVE_RUN_ID,
    path.basename(agentWorkspaceDir),
  );
});

test("benchmark mode sandbox contracts match declared capabilities", () => {
  const baseConfig = {
    mcpCommand: ["python", "server.py"],
    resultsDir: "benchmark_runs",
    mcpToolTimeoutMs: 3_600_000,
    morpheusRunTimeoutMs: 3_600_000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: "src/benchmark/MorpheusML.xsd",
    skillPaths: ["C:/repo/.agents/skills/morpheus/SKILL.md"],
  };
  const threadConfig = {
    model: "gpt-5.5",
    reasoningEffort: "high",
    codexApprovalPolicy: "never",
  } as const;
  const codexHomeDir = path.join(tmpdir(), "morpheus-contract-codex-home", "run_123");
  const activeRunDir = path.join("benchmark_runs", "run_123");
  const agentWorkspaceDir = path.join(tmpdir(), "morpheus-contract-workspace", "run_123");
  const baseEnv = {
    Path: ["C:\\Windows\\System32", "C:\\Program Files\\Morpheus\\bin"].join(path.delimiter),
    PATH: ["C:\\Windows\\System32", "C:\\Program Files\\Morpheus\\bin"].join(path.delimiter),
    MORPHEUS_HOME: "C:\\Program Files\\Morpheus",
    MORPHEUS_BIN: "C:\\Program Files\\Morpheus\\bin\\morpheus.exe",
    OPENAI_API_KEY: "test-key",
  };

  for (const mode of ALL_BENCHMARK_MODES) {
    const capabilities = BENCHMARK_MODE_DEFINITIONS[mode].capabilities;
    const threadOptions = buildBenchmarkThreadOptions(threadConfig, activeRunDir, agentWorkspaceDir, mode);
    const codexConfig = buildCodexConfig(baseConfig, mode, "run_123", agentWorkspaceDir, codexHomeDir);
    const stagedFiles = buildAgentWorkspaceStageFiles({
      agentWorkspaceDir,
      runDir: activeRunDir,
      pdfPath: path.join("benchmark_papers", "paper.pdf"),
      paperTextPath: path.join(activeRunDir, "paper.txt"),
      visualManifestPath: path.join(activeRunDir, "paper_visual_manifest.json"),
      mode,
    });
    const env = buildBenchmarkCodexEnv(baseEnv, mode, codexHomeDir, 123_000);
    const skillEntries = (codexConfig.skills?.config ?? []) as Array<{ path: string; enabled: boolean }>;
    const enabledSkillPaths = skillEntries.filter((entry) => entry.enabled).map((entry) => entry.path);

    assert.equal(threadOptions.sandboxMode, undefined, `${mode} defers sandboxing to its permission profile`);
    assert.equal(threadOptions.approvalPolicy, "never", `${mode} disables approvals inside benchmark agents`);
    assert.equal(threadOptions.workingDirectory, path.resolve(agentWorkspaceDir), `${mode} works in agent workspace`);
    assert.equal(threadOptions.additionalDirectories, undefined, `${mode} has no legacy writable roots`);
    assert.equal(threadOptions.networkAccessEnabled, undefined, `${mode} has no direct command network override`);
    assert.equal(
      threadOptions.webSearchMode,
      capabilities.webSearch ? "live" : "disabled",
      `${mode} web search follows mode`,
    );
    assert.equal(
      shouldPreflightCommandRunner(mode),
      capabilities.python || capabilities.morpheusCli,
      `${mode} preflights shell when Python or Morpheus CLI is an intended tool`,
    );
    assert.equal(Boolean(codexConfig.mcp_servers?.morpheus), capabilities.morpheusMcp, `${mode} MCP server exposure`);
    assert.equal(
      enabledSkillPaths.some((skillPath) => /skills[\\/]+morpheus[\\/]+SKILL\.md$/i.test(skillPath)),
      capabilities.morpheusSkill,
      `${mode} Morpheus skill exposure`,
    );
    assert.equal("CODEX_HOME" in env, true, `${mode} uses isolated Codex home`);
    assert.equal(
      env.CODEX_EXEC_TURN_TIMEOUT_MS,
      "123000",
      `${mode} propagates the host-side Codex turn watchdog`,
    );
    assert.equal(env.VIRTUAL_ENV, path.join(process.cwd(), ".venv"), `${mode} inherits benchmark Python venv`);

    if (mode === "python_web") {
      assert.equal("MORPHEUS_HOME" in env, false, "python_web hides Morpheus environment variables");
      assert.equal("MORPHEUS_BIN" in env, false, "python_web hides Morpheus executables");
      assert.equal(env.Path.includes("C:\\Program Files\\Morpheus\\bin"), false);
      assert.equal(env.PATH.includes("C:\\Program Files\\Morpheus\\bin"), false);
    } else {
      assert.equal("MORPHEUS_HOME" in env, false, `${mode} does not inherit broad Morpheus host variables`);
      assert.equal(env.MORPHEUS_BIN, baseEnv.MORPHEUS_BIN, `${mode} keeps explicit Morpheus binary access`);
    }
    assert.equal("OPENAI_API_KEY" in env, false, `${mode} strips host API keys`);

    assert.equal(
      "sourceMorpheusMlDocPath" in stagedFiles,
      mode === "morpheus_cli_docs",
      `${mode} stages docs-only MorpheusML reference files only when intended`,
    );
  }
});

test("expandBenchmarkJobs creates one job per paper, mode, and repetition, repetition-major", () => {
  assert.deepEqual(expandBenchmarkJobs(["paper_a.pdf", "paper_b.pdf"], ["python_web", "morpheus_mcp"], 2), [
    { pdfPath: "paper_a.pdf", mode: "python_web", repetition: 1 },
    { pdfPath: "paper_a.pdf", mode: "morpheus_mcp", repetition: 1 },
    { pdfPath: "paper_b.pdf", mode: "python_web", repetition: 1 },
    { pdfPath: "paper_b.pdf", mode: "morpheus_mcp", repetition: 1 },
    { pdfPath: "paper_a.pdf", mode: "python_web", repetition: 2 },
    { pdfPath: "paper_a.pdf", mode: "morpheus_mcp", repetition: 2 },
    { pdfPath: "paper_b.pdf", mode: "python_web", repetition: 2 },
    { pdfPath: "paper_b.pdf", mode: "morpheus_mcp", repetition: 2 },
  ]);
  for (const repetitions of [0, -2, Number.NaN, Number.POSITIVE_INFINITY]) {
    assert.equal(expandBenchmarkJobs(["paper_a.pdf"], ["python_web"], repetitions).length, 1);
  }
  assert.equal(expandBenchmarkJobs(["paper_a.pdf"], ["python_web"], 2.8).length, 2);
});

test("findLatestRunInfoForJob recovers the active run folder after an unhandled runner error", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-benchmark-runs-"));
  const olderRun = path.join(root, "20260508_120000_1_Szabo2010_clean__morpheus_mcp");
  const latestRun = path.join(root, "20260508_130000_1_Szabo2010_clean__morpheus_mcp");
  await mkdir(olderRun, { recursive: true });
  await mkdir(latestRun, { recursive: true });
  await writeFile(path.join(olderRun, "run_manifest.json"), JSON.stringify({ run_id: "older" }), "utf8");
  await writeFile(path.join(latestRun, "run_manifest.json"), JSON.stringify({ run_id: "latest" }), "utf8");

  const info = await findLatestRunInfoForJob(root, path.join(root, "papers", "1_Szabo2010_clean.pdf"), "morpheus_mcp");

  assert.equal(info?.runId, "latest");
  assert.equal(info?.runDir, latestRun);
  assert.equal(info?.runManifestPath, path.join(latestRun, "run_manifest.json"));
});

test("findLatestRunInfoForJob returns null for missing benchmark directories", async () => {
  const info = await findLatestRunInfoForJob(
    path.join(tmpdir(), "missing-morpheus-benchmark-run"),
    "1_Szabo2010_clean.pdf",
    "morpheus_mcp",
  );

  assert.equal(info, null);
});

test("findLatestRunInfoForJob handles empty directories and repetition suffixes", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-benchmark-runs-"));
  assert.equal(
    await findLatestRunInfoForJob(root, "1_Szabo2010_clean.pdf", "morpheus_mcp"),
    null,
  );

  const repeatedRun = path.join(root, "20260508_120000_1_Szabo2010_clean__morpheus_mcp__rep02");
  await mkdir(repeatedRun, { recursive: true });
  await writeFile(path.join(repeatedRun, "run_manifest.json"), JSON.stringify({ run_id: "repeat_two" }), "utf8");

  const info = await findLatestRunInfoForJob(root, "1_Szabo2010_clean.pdf", "morpheus_mcp", 2, 3);

  assert.equal(info?.runId, "repeat_two");
  assert.equal(info?.runDir, repeatedRun);
});

test("transcriptEventsForTurnError preserves partial events and appends the terminal error", () => {
  const partialEvent = { type: "thread.started", thread_id: "thread_123" };

  const events = transcriptEventsForTurnError(
    {
      finalResponse: "",
      usage: null,
      events: [partialEvent as any],
      items: [],
      error: "OpenAI backend disconnected while streaming.",
      durationMs: 25,
      morpheusSimulationMs: 0,
    },
    "fallback error",
  );

  assert.deepEqual(events, [
    partialEvent,
    { type: "error", message: "OpenAI backend disconnected while streaming." },
  ]);
});

test("run progress includes unhandled runner exception details", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-progress-error-"));
  const papersDir = path.join(root, "papers");
  await mkdir(papersDir, { recursive: true });
  await writeFile(path.join(papersDir, "01_Szabo2010.pdf"), "%PDF-1.4\n", "utf8");

  const progress: string[] = [];
  const runner = new BenchmarkRunner(testBenchmarkConfig(root), {
    progress: (message) => progress.push(message),
  });
  (runner as any).processPaper = async () => {
    throw new Error("ENOSPC: no space left on device while staging run");
  };

  await runner.run();

  assert.ok(progress.some((message) => /Unhandled runner error/.test(message) && /ENOSPC/.test(message)));
});

test("recoverRun rejects historical v1 execution artifacts", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v1-read-only-"));
  await writeFile(path.join(root, "benchmark_summary.json"), JSON.stringify({ results: [] }), "utf8");
  const runner = new BenchmarkRunner(testBenchmarkConfig(root));

  await assert.rejects(
    () => runner.recoverRun(root),
    /Historical max_cycles_v1 runs are read-only/,
  );
});

test("clean replacement is limited to subject infrastructure failures explicitly marked eligible", async () => {
  let setupCalls = 0;
  const setupFailure = await runWithCleanInfrastructureReplacement(async () => {
    setupCalls += 1;
    return {
      executionId: `setup-${setupCalls}`,
      stopReason: "infrastructure_failure" as const,
      replacementEligible: false,
    };
  });
  assert.equal(setupCalls, 1);
  assert.equal(setupFailure.executions.length, 1);

  let subjectCalls = 0;
  const subjectFailure = await runWithCleanInfrastructureReplacement(async (request) => {
    subjectCalls += 1;
    return subjectCalls === 1
      ? {
          executionId: "subject-1",
          stopReason: "infrastructure_failure" as const,
          replacementEligible: true,
        }
      : {
          executionId: "subject-2",
          stopReason: "agent_finished" as const,
          replacementEligible: false,
          replacementFor: request.replacementFor,
        };
  });
  assert.equal(subjectCalls, 2);
  assert.equal(subjectFailure.selected.executionId, "subject-2");
  assert.equal(subjectFailure.executions.length, 2);
});

test("recoverRun deterministically regenerates v2 aggregate artifacts without relaunching subjects", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-postprocess-"));
  const config = testBenchmarkConfig(root);
  const runDir = path.join(root, "run_1");
  const attemptDir = path.join(runDir, "agent_workspace", "attempts", "attempt_001");
  const diagnostics = emptyBenchmarkDiagnostics();
  diagnostics.attemptCount = 9;
  await mkdir(path.join(runDir, "transcripts"), { recursive: true });
  await mkdir(attemptDir, { recursive: true });
  await Promise.all([
    writeFile(path.join(runDir, "transcripts", "subject.jsonl"), ""),
    writeFile(path.join(attemptDir, "morpheus_command.json"), "{}"),
    writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel/>"),
    writeFile(path.join(attemptDir, "attempt_reproduction.json"), "{}"),
    writeFile(path.join(attemptDir, "stdout.log"), "done"),
    writeFile(path.join(attemptDir, "stderr.log"), ""),
  ]);
  const result = {
    paper: "paper.pdf",
    pdfPath: path.join(root, "paper.pdf"),
    mode: "morpheus_cli",
    modeLabel: BENCHMARK_MODE_DEFINITIONS.morpheus_cli.label,
    capabilities: BENCHMARK_MODE_DEFINITIONS.morpheus_cli.capabilities,
    capabilityViolations: [],
    runId: "run_1",
    threadId: "thread_1",
    repetition: 1,
    startedAt: "2026-08-20T00:00:00.000Z",
    finishedAt: "2026-08-20T00:01:00.000Z",
    durationMs: 60_000,
    diagnostics,
    attempts: 9,
    modelRefinementCount: 1,
    technicalScore: 5,
    reproductionScore: 7,
    technicalEvaluationPath: null,
    reproductionReportPath: null,
    reproductionReportTextPath: null,
    runManifestPath: path.join(runDir, "run_manifest.json"),
    benchmarkFocus: null,
    summary: "done",
    stopReason: "agent_finished",
    artifactStatus: "scoreable",
  } as unknown as PaperRunResult;
  const summary: BenchmarkSummary = {
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    config,
    benchmarkId: "benchmark",
    benchmarkRunDir: root,
    comparisonJsonPath: path.join(root, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(root, "benchmark_comparison.csv"),
    startedAt: "2026-08-20T00:00:00.000Z",
    finishedAt: "2026-08-20T00:01:00.000Z",
    generatedAt: "2026-08-20T00:01:00.000Z",
    durationMs: 60_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    totalRuns: 1,
    uniquePapers: 1,
    benchmarkRepetitions: 1,
    totalPapers: 1,
    agentFinishedRuns: 1,
    timeLimitRuns: 0,
    infrastructureFailureRuns: 0,
    scoreableRuns: 0,
    replacementRuns: 0,
    totalModelRefinements: 0,
    averageModelRefinements: 0,
    averageTechnicalScore: 0,
    averageReproductionScore: 0,
    paperModeStatistics: [],
    results: [result],
  };
  await writeFile(path.join(root, "benchmark_summary.json"), JSON.stringify(summary), "utf8");
  const runner = new BenchmarkRunner(config);
  (runner as any).processPaper = async () => {
    throw new Error("subject execution must not run during v2 postprocessing");
  };

  const recovered = await runner.recoverRun(root);

  assert.equal(recovered.benchmarkProtocol, "time_limit_v2");
  assert.equal(recovered.results[0].attempts, 1);
  assert.equal(recovered.diagnostics.attemptCount, 1);
  assert.equal(recovered.paperModeStatistics[0].metrics.diagnosticAttemptCount.sum, 1);
  assert.equal(await readFile(path.join(root, "benchmark_comparison.json"), "utf8").then(Boolean), true);
  await assert.rejects(() => readFile(path.join(root, ".benchmark-v2-recovery.lock"), "utf8"));
});

test("explicit recoverRun replaces a recorded infrastructure failure and preserves its execution audit", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-explicit-recovery-"));
  const config = testBenchmarkConfig(root, {
    benchmarkModes: ["morpheus_cli_docs"],
    maxConcurrentJobs: 5,
  });
  const pdfPath = path.join(root, "papers", "paper.pdf");
  const assignmentId = "paper__morpheus_cli_docs__rep01";
  await mkdir(path.dirname(pdfPath), { recursive: true });
  await writeFile(pdfPath, "%PDF-1.4\n", "utf8");
  await writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkId: "interrupted-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-08-20T00:00:00.000Z",
    config,
    jobs: [{ pdfPath, mode: "morpheus_cli_docs", repetition: 1 }],
  }), "utf8");

  const prior = {
    paper: "paper.pdf",
    pdfPath,
    mode: "morpheus_cli_docs",
    modeLabel: BENCHMARK_MODE_DEFINITIONS.morpheus_cli_docs.label,
    capabilities: BENCHMARK_MODE_DEFINITIONS.morpheus_cli_docs.capabilities,
    capabilityViolations: [],
    runId: "failed_run",
    threadId: "",
    repetition: 1,
    startedAt: "2026-08-20T00:00:00.000Z",
    finishedAt: "2026-08-20T00:00:25.000Z",
    durationMs: 25_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    attempts: 0,
    modelRefinementCount: 0,
    technicalScore: null,
    reproductionScore: null,
    technicalEvaluationPath: null,
    reproductionReportPath: path.join(root, "failed_run", "reproduction_report.json"),
    reproductionReportTextPath: path.join(root, "failed_run", "reproduction_report.txt"),
    runManifestPath: path.join(root, "failed_run", "run_manifest.json"),
    benchmarkFocus: null,
    summary:
      "Infrastructure failure before subject turn: Command-runner preflight failed after 3 attempts: Your access token could not be refreshed because your refresh token was already used.",
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId,
    executionId: `${assignmentId}__execution_01`,
    replacementFor: null,
    replacementCount: 0,
    replacementEligible: false,
    stopReason: "infrastructure_failure",
    artifactStatus: "missing",
    workspaceDir: path.join(root, "failed_run", "agent_workspace"),
    codexHomeDir: path.join(root, "failed_run", "codex_home"),
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    totalTimeLimitMs: config.totalTimeLimitMs,
    finalizationReserveMs: config.finalizationReserveMs,
    subjectExecutionMs: 0,
    morpheusSimulationMs: 0,
    totalJobMs: 25_000,
  } as PaperRunResult;
  const summary = {
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    config,
    benchmarkId: "interrupted-benchmark",
    benchmarkRunDir: root,
    comparisonJsonPath: path.join(root, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(root, "benchmark_comparison.csv"),
    startedAt: "2026-08-20T00:00:00.000Z",
    finishedAt: "2026-08-20T00:00:25.000Z",
    generatedAt: "2026-08-20T00:00:25.000Z",
    durationMs: 25_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    totalRuns: 1,
    uniquePapers: 1,
    benchmarkRepetitions: 1,
    totalPapers: 1,
    agentFinishedRuns: 0,
    timeLimitRuns: 0,
    infrastructureFailureRuns: 1,
    scoreableRuns: 0,
    replacementRuns: 0,
    totalModelRefinements: 0,
    averageModelRefinements: 0,
    averageTechnicalScore: 0,
    averageReproductionScore: 0,
    paperModeStatistics: [],
    results: [prior],
  } as BenchmarkSummary;
  await mkdir(path.join(root, "assignment_results"), { recursive: true });
  await writeFile(path.join(root, "benchmark_summary.json"), JSON.stringify(summary), "utf8");
  await writeFile(path.join(root, "assignment_results", `${assignmentId}.json`), JSON.stringify(prior), "utf8");

  let executionCalls = 0;
  const progress: string[] = [];
  const runner = new BenchmarkRunner(config, { progress: (message) => {
    progress.push(message);
  } });
  (runner as any).processExecution = async (
    _pdfPath: string,
    mode: "morpheus_cli_docs",
    _benchmarkRunDir: string,
    repetition: number,
    execution: { executionId: string; replacementFor: string | null; replacementCount: 0 | 1 },
  ) => {
    executionCalls += 1;
    return {
      ...prior,
      runId: "replacement_run",
      threadId: "fresh_thread",
      mode,
      repetition,
      technicalScore: 7,
      reproductionScore: 8,
      summary: "Recovered after login.",
      executionId: execution.executionId,
      replacementFor: execution.replacementFor,
      replacementCount: execution.replacementCount,
      replacementEligible: false,
      stopReason: "agent_finished",
      artifactStatus: "scoreable",
      attempts: 1,
    } satisfies PaperRunResult;
  };

  const recovered = await (runner.recoverRun as any)(root, { rerunInfrastructureFailures: true });

  assert.equal(executionCalls, 1);
  assert.equal(recovered.results[0].runId, "replacement_run");
  assert.equal(recovered.results[0].replacementCount, 1);
  assert.equal(recovered.results[0].executions?.length, 2);
  assert.equal(recovered.results[0].executions?.[0].runId, "failed_run");
  assert.equal(recovered.config.maxConcurrentJobs, process.platform === "win32" ? 1 : 5);
  if (process.platform === "win32") {
    assert.ok(progress.some((message) => message.endsWith(
      "Native Windows uses serial recovery; requested concurrency=5 was reduced to concurrency=1. Use Linux or WSL2 for parallel jobs.",
    )));
  }
});

test("recoverRun rejects concurrent postprocessing of the same v2 run", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-postprocess-lock-"));
  await writeFile(path.join(root, ".benchmark-v2-recovery.lock"), "active\n", "utf8");
  const runner = new BenchmarkRunner(testBenchmarkConfig(root));

  await assert.rejects(
    () => runner.recoverRun(root),
    /already being postprocessed/i,
  );
});

test("recoverRun uses persisted v2 state and a clean replacement for ambiguous subject state", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-crash-recovery-"));
  const config = testBenchmarkConfig(root, { benchmarkModes: ["morpheus_mcp"] });
  const pdfPath = path.join(root, "papers", "paper.pdf");
  await mkdir(path.dirname(pdfPath), { recursive: true });
  await writeFile(pdfPath, "%PDF-1.4\n", "utf8");
  await writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkId: "crashed-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-08-20T00:00:00.000Z",
    config,
    jobs: [{ pdfPath, mode: "morpheus_mcp", repetition: 1 }],
  }), "utf8");
  const invalidRunDir = path.join(root, "20260820_000000_paper__morpheus_mcp");
  await mkdir(invalidRunDir, { recursive: true });
  await writeFile(path.join(invalidRunDir, "run_manifest.json"), JSON.stringify({ run_id: "invalid_run" }), "utf8");
  await writeFile(path.join(invalidRunDir, "subject_deadline.json"), JSON.stringify({
    subjectStartedAt: "2026-08-20T00:00:01.000Z",
    softCutoffAt: "2026-08-20T03:50:01.000Z",
    hardCutoffAt: "2026-08-20T04:00:01.000Z",
  }), "utf8");

  const runner = new BenchmarkRunner(config);
  (runner as any).processExecution = async (
    _pdfPath: string,
    mode: "morpheus_mcp",
    _benchmarkRunDir: string,
    repetition: number,
    execution: { executionId: string; replacementFor: string | null; replacementCount: 0 | 1 },
  ) => ({
    paper: "paper.pdf",
    pdfPath,
    mode,
    modeLabel: BENCHMARK_MODE_DEFINITIONS[mode].label,
    capabilities: BENCHMARK_MODE_DEFINITIONS[mode].capabilities,
    capabilityViolations: [],
    runId: "replacement_run",
    threadId: "fresh_thread",
    repetition,
    startedAt: "2026-08-20T04:01:00.000Z",
    finishedAt: "2026-08-20T04:02:00.000Z",
    durationMs: 60_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    attempts: 1,
    modelRefinementCount: 1,
    technicalScore: 7,
    reproductionScore: 8,
    technicalEvaluationPath: "technical.json",
    reproductionReportPath: "reproduction.json",
    reproductionReportTextPath: "reproduction.txt",
    runManifestPath: path.join(root, "replacement", "run_manifest.json"),
    benchmarkFocus: null,
    summary: "Recovered with a clean execution.",
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId: "paper__morpheus_mcp__rep01",
    executionId: execution.executionId,
    replacementFor: execution.replacementFor,
    replacementCount: execution.replacementCount,
    stopReason: "agent_finished",
    artifactStatus: "scoreable",
    workspaceDir: path.join(root, "replacement", "agent_workspace"),
    codexHomeDir: path.join(root, "replacement", "codex_home"),
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    totalTimeLimitMs: config.totalTimeLimitMs,
    finalizationReserveMs: config.finalizationReserveMs,
    subjectExecutionMs: 60_000,
    morpheusSimulationMs: 30_000,
    totalJobMs: 60_000,
  } satisfies PaperRunResult);

  const recovered = await runner.recoverRun(root);

  assert.equal(recovered.results[0].runId, "replacement_run");
  assert.equal(recovered.results[0].replacementCount, 1);
  assert.equal(recovered.results[0].executions?.length, 2);
  assert.equal(recovered.results[0].executions?.[0].runId, "invalid_run");
  assert.equal(recovered.results[0].executions?.[0].stopReason, "infrastructure_failure");
  assert.equal(recovered.results[0].selectedExecutionId, "paper__morpheus_mcp__rep01__execution_02");
});

test("recoverRun uses persisted concurrency for missing assignments", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-concurrent-recovery-"));
  const config = testBenchmarkConfig(root, {
    benchmarkModes: ["morpheus_mcp"],
    benchmarkRepetitions: 3,
    maxConcurrentJobs: 2,
  });
  const pdfPath = path.join(root, "papers", "paper.pdf");
  const jobs = [1, 2, 3].map((repetition) => ({
    pdfPath,
    mode: "morpheus_mcp" as const,
    repetition,
  }));
  await mkdir(path.dirname(pdfPath), { recursive: true });
  await writeFile(pdfPath, "%PDF-1.4\n", "utf8");
  await writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkId: "concurrent-recovery-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-08-20T00:00:00.000Z",
    config,
    jobs,
  }), "utf8");

  let active = 0;
  let maxActive = 0;
  const runner = new BenchmarkRunner(config);
  (runner as any).processPaper = async (
    jobPdfPath: string,
    mode: "morpheus_mcp",
    _benchmarkRunDir: string,
    repetition: number,
  ) => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    await delay(20);
    active -= 1;
    return {
      paper: path.basename(jobPdfPath),
      pdfPath: jobPdfPath,
      mode,
      modeLabel: BENCHMARK_MODE_DEFINITIONS[mode].label,
      capabilities: BENCHMARK_MODE_DEFINITIONS[mode].capabilities,
      capabilityViolations: [],
      runId: `recovered_${repetition}`,
      threadId: `thread_${repetition}`,
      repetition,
      startedAt: "2026-08-20T04:01:00.000Z",
      finishedAt: "2026-08-20T04:02:00.000Z",
      durationMs: 60_000,
      diagnostics: emptyBenchmarkDiagnostics(),
      attempts: 1,
      modelRefinementCount: 1,
      technicalScore: 7,
      reproductionScore: 8,
      technicalEvaluationPath: null,
      reproductionReportPath: null,
      reproductionReportTextPath: null,
      runManifestPath: null,
      benchmarkFocus: null,
      summary: "Recovered missing assignment.",
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      assignmentId: `paper__morpheus_mcp__rep${String(repetition).padStart(2, "0")}`,
      executionId: `paper__morpheus_mcp__rep${String(repetition).padStart(2, "0")}__execution_01`,
      replacementFor: null,
      replacementCount: 0,
      replacementEligible: false,
      stopReason: "agent_finished",
      artifactStatus: "scoreable",
      workspaceDir: path.join(root, `workspace_${repetition}`),
      codexHomeDir: path.join(root, `codex_home_${repetition}`),
      model: config.model,
      reasoningEffort: config.reasoningEffort,
      totalTimeLimitMs: config.totalTimeLimitMs,
      finalizationReserveMs: config.finalizationReserveMs,
      subjectExecutionMs: 60_000,
      morpheusSimulationMs: 30_000,
      totalJobMs: 60_000,
    } as PaperRunResult;
  };

  const recovered = await runner.recoverRun(root);

  assert.equal(recovered.results.length, 3);
  assert.equal(recovered.benchmarkVersion, BENCHMARK_VERSION);
  assert.equal(maxActive, process.platform === "win32" ? 1 : 2);
});

test("recoverRun refuses to launch subjects for a run from another benchmark version or skill", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-version-recovery-"));
  const config = testBenchmarkConfig(root);
  const pdfPath = path.join(root, "papers", "paper.pdf");
  await mkdir(path.dirname(pdfPath), { recursive: true });
  await writeFile(pdfPath, "%PDF-1.4\n", "utf8");
  await mkdir(path.dirname(config.skillPaths[0]), { recursive: true });
  await writeFile(config.skillPaths[0], "---\nname: morpheus\n---\n", "utf8");
  const writeState = (extra: Record<string, unknown>) => writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkId: "versioned-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-08-20T00:00:00.000Z",
    config,
    jobs: [{ pdfPath, mode: "morpheus_mcp", repetition: 1 }],
    ...extra,
  }), "utf8");
  let launched = 0;
  const runner = new BenchmarkRunner(config);
  (runner as any).processPaper = async () => {
    launched += 1;
    throw new Error("processPaper must not run");
  };

  await writeState({});
  await assert.rejects(runner.recoverRun(root), /benchmark v2.*Check out tag benchmark-v2/);

  await writeState({
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkProvenance: {
      benchmarkVersion: BENCHMARK_VERSION,
      gitCommit: null,
      gitTag: null,
      gitDirty: null,
      skills: [{ name: "morpheus", sha256: "0".repeat(64) }],
      docsReferences: { morpheusMlDocSha256: null, modelTemplateSha256: null },
    },
  });
  await assert.rejects(runner.recoverRun(root), /Skill "morpheus" changed since this run started/);
  assert.equal(launched, 0);
});

test("snapshotBenchmarkCodexHome preserves persisted Codex sessions for recovery resume", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-codex-home-snapshot-"));
  const codexHome = path.join(root, "codex_home_source");
  const runDir = path.join(root, "run_123");
  await mkdir(path.join(codexHome, "sessions", "2026", "05", "13"), { recursive: true });
  await writeFile(path.join(codexHome, "config.toml"), "model = \"gpt-5.5\"", "utf8");
  await writeFile(path.join(codexHome, "session_index.jsonl"), "{\"id\":\"thread_123\"}\n", "utf8");
  await mkdir(path.join(codexHome, "skills", "morpheus"), { recursive: true });
  await mkdir(path.join(codexHome, "skills", ".system", "imagegen"), { recursive: true });
  await writeFile(path.join(codexHome, "skills", "morpheus", "SKILL.md"), "# Morpheus\n", "utf8");
  await writeFile(path.join(codexHome, "skills", ".system", "imagegen", "SKILL.md"), "# Imagegen\n", "utf8");
  await writeFile(
    path.join(codexHome, "sessions", "2026", "05", "13", "rollout.jsonl"),
    "{\"type\":\"thread.started\",\"thread_id\":\"thread_123\"}\n",
    "utf8",
  );

  await snapshotBenchmarkCodexHome(codexHome, runDir);

  const snapshotRoot = buildCodexHomeSnapshotDir(runDir);
  assert.equal(
    await readFile(path.join(snapshotRoot, "sessions", "2026", "05", "13", "rollout.jsonl"), "utf8"),
    "{\"type\":\"thread.started\",\"thread_id\":\"thread_123\"}\n",
  );
  assert.equal(await readFile(path.join(snapshotRoot, "session_index.jsonl"), "utf8"), "{\"id\":\"thread_123\"}\n");
  assert.equal(await readFile(path.join(snapshotRoot, "skills", "morpheus", "SKILL.md"), "utf8"), "# Morpheus\n");
  await assert.rejects(() => readFile(path.join(snapshotRoot, "skills", ".system", "imagegen", "SKILL.md"), "utf8"));
});

test("restoreBenchmarkCodexHomeFromSnapshot restores an existing Codex home snapshot directory", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-codex-home-restore-"));
  const runDir = path.join(root, "run_123");
  const snapshotDir = buildCodexHomeSnapshotDir(runDir);
  const codexHomeDir = path.join(root, "codex_home_live");
  await mkdir(snapshotDir, { recursive: true });
  await writeFile(path.join(snapshotDir, "config.toml"), "model = \"gpt-5.5\"", "utf8");

  await restoreBenchmarkCodexHomeFromSnapshot(runDir, codexHomeDir);

  assert.equal(await readFile(path.join(codexHomeDir, "config.toml"), "utf8"), "model = \"gpt-5.5\"");
});

test("countModelRefinementArtifacts counts agent CLI attempt directories beyond captured snapshots", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-refinement-artifacts-"));
  const runDir = path.join(root, "run_cli_docs");
  await mkdir(path.join(runDir, "agent_workspace", "agent_runs", "cli_attempts"), { recursive: true });
  await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ xml_version_count: 2 }), "utf8");

  for (let index = 1; index <= 8; index += 1) {
    const suffix = index === 8 ? "_final_analysis" : "";
    await mkdir(
      path.join(
        runDir,
        "agent_workspace",
        "agent_runs",
        "cli_attempts",
        `attempt_${String(index).padStart(2, "0")}${suffix}`,
      ),
      { recursive: true },
    );
  }

  assert.equal(await countModelRefinementArtifacts(runDir), 8);
});

test("auditAgentMorpheusAttempts counts executed attempts and missing contract artifacts", async () => {
  const runDir = await mkdtemp(path.join(tmpdir(), "morpheus-attempt-audit-"));
  const attemptsDir = path.join(runDir, "agent_workspace", "attempts");
  const complete = path.join(attemptsDir, "attempt_001");
  const incomplete = path.join(attemptsDir, "attempt_002");
  const scratch = path.join(attemptsDir, "attempt_003");
  const nested = path.join(runDir, "agent_workspace", "agent_runs", "cli_attempts", "attempt_004_final");
  await mkdir(path.join(incomplete, "output"), { recursive: true });
  await mkdir(complete, { recursive: true });
  await mkdir(scratch, { recursive: true });
  await mkdir(nested, { recursive: true });
  await Promise.all([
    writeFile(path.join(complete, "morpheus_command.json"), "{}"),
    writeFile(path.join(complete, "model.xml"), "<MorpheusModel/>"),
    writeFile(path.join(complete, "attempt_reproduction.json"), "{}"),
    writeFile(path.join(complete, "stdout.log"), "done"),
    writeFile(path.join(incomplete, "output", "morpheus_command.json"), "{}"),
    writeFile(path.join(scratch, "notes.txt"), "not executed"),
    writeFile(path.join(nested, "morpheus_command.json"), "{}"),
    writeFile(path.join(nested, "model.xml"), "<MorpheusModel/>"),
    writeFile(path.join(nested, "attempt_reproduction.json"), "{}"),
    writeFile(path.join(nested, "stdout.log"), "done"),
    writeFile(path.join(nested, "stderr.log"), ""),
  ]);

  assert.deepEqual(await auditAgentMorpheusAttempts(runDir), {
    executedAttempts: 3,
    missingModelXml: 1,
    missingReproductionReport: 1,
    missingLogs: 2,
  });
});

test("reconcileStoredRunAudit replaces host attempt counts with subject execution counts", async () => {
  const runDir = await mkdtemp(path.join(tmpdir(), "morpheus-stored-run-audit-"));
  const attemptDir = path.join(runDir, "agent_workspace", "attempts", "attempt_001");
  await mkdir(attemptDir, { recursive: true });
  await Promise.all([
    writeFile(path.join(attemptDir, "morpheus_command.json"), "{}"),
    writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel/>"),
    writeFile(path.join(attemptDir, "attempt_reproduction.json"), "{}"),
    writeFile(path.join(attemptDir, "stderr.log"), ""),
  ]);
  const diagnostics = emptyBenchmarkDiagnostics();
  diagnostics.attemptCount = 9;
  const result = {
    mode: "morpheus_cli",
    runId: "run_123",
    capabilityViolations: [],
    diagnostics,
    attempts: 9,
  } as unknown as PaperRunResult;

  const audited = await reconcileStoredRunAudit(result, [], runDir);

  assert.equal(audited.attempts, 1);
  assert.equal(audited.diagnostics.attemptCount, 1);
  assert.deepEqual(audited.attemptArtifactAudit, {
    executedAttempts: 1,
    missingModelXml: 0,
    missingReproductionReport: 0,
    missingLogs: 1,
  });
});

test("countModelRefinementArtifacts uses agent workspace MCP version and attempt history", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-refinement-mcp-"));
  const runDir = path.join(root, "run_mcp");
  await mkdir(path.join(runDir, "xml_versions"), { recursive: true });
  await mkdir(path.join(runDir, "agent_workspace", "xml_versions"), { recursive: true });
  await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ xml_version_count: 2 }), "utf8");
  await writeFile(
    path.join(runDir, "agent_workspace", "run_manifest.json"),
    JSON.stringify({
      xml_version_count: 6,
      attempt_history: Array.from({ length: 6 }, (_, index) => ({ attempt_id: `attempt_${index + 1}` })),
    }),
    "utf8",
  );

  for (let index = 1; index <= 2; index += 1) {
    await writeFile(path.join(runDir, "xml_versions", `model_v${String(index).padStart(3, "0")}.xml`), "<root/>", "utf8");
  }
  for (let index = 1; index <= 6; index += 1) {
    await writeFile(
      path.join(runDir, "agent_workspace", "xml_versions", `model_v${String(index).padStart(3, "0")}.xml`),
      "<root/>",
      "utf8",
    );
  }

  assert.equal(await countModelRefinementArtifacts(runDir), 6);
});

test("countModelRefinementArtifacts counts unique and anonymous manifest attempts", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-refinement-history-"));
  const runDir = path.join(root, "run_history");
  await mkdir(runDir, { recursive: true });
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      attempt_history: [
        { attempt_id: "attempt_001" },
        { attempt_id: "attempt_001" },
        { attempt_id: "attempt_002" },
        { summary: "anonymous retry" },
        null,
        "bad",
        { attempt_id: "" },
      ],
    }),
    "utf8",
  );

  assert.equal(await countModelRefinementArtifacts(runDir), 4);
});

test("harvestAttemptModelXmlVersions copies unique attempt model XMLs into xml_versions", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-attempt-xml-harvest-"));
  const runDir = path.join(root, "run_123");
  await mkdir(path.join(runDir, "xml_versions"), { recursive: true });
  await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ xml_version_count: 1 }), "utf8");
  await writeFile(path.join(runDir, "xml_versions", "model_v001.xml"), "<model>A</model>", "utf8");

  const cliAttemptOne = path.join(runDir, "agent_workspace", "agent_runs", "cli_attempts", "attempt_001");
  const cliAttemptTwo = path.join(runDir, "agent_workspace", "agent_runs", "cli_attempts", "attempt_002");
  const mcpAttempt = path.join(runDir, "attempts", "attempt_003");
  await mkdir(cliAttemptOne, { recursive: true });
  await mkdir(cliAttemptTwo, { recursive: true });
  await mkdir(mcpAttempt, { recursive: true });
  await writeFile(path.join(cliAttemptOne, "model.xml"), "<model>A</model>", "utf8");
  await writeFile(path.join(cliAttemptTwo, "model.xml"), "<model>B</model>", "utf8");
  await writeFile(path.join(mcpAttempt, "model.xml"), "<model>C</model>", "utf8");

  const result = await harvestAttemptModelXmlVersions(runDir);

  assert.equal(result.harvestedCount, 2);
  assert.equal(result.xmlVersionCount, 3);
  assert.equal(await readFile(path.join(runDir, "xml_versions", "model_v002.xml"), "utf8"), "<model>B</model>");
  assert.equal(await readFile(path.join(runDir, "xml_versions", "model_v003.xml"), "utf8"), "<model>C</model>");
  const manifest = JSON.parse(await readFile(path.join(runDir, "run_manifest.json"), "utf8"));
  assert.equal(manifest.xml_version_count, 3);
  assert.equal(manifest.host_harvested_attempt_xml_versions.length, 2);
});

test("modelRefinementCountFromManifest uses explicit and captured XML version counts", () => {
  assert.equal(modelRefinementCountFromManifest(null), 0);
  assert.equal(modelRefinementCountFromManifest({ xml_version_count: 3.9 }), 3);
  assert.equal(modelRefinementCountFromManifest({ xml_version_count: -4 }), 0);
  assert.equal(
    modelRefinementCountFromManifest({
      host_captured_xml_versions: [
        { version_path: "xml_versions/model_v001.xml" },
        { version_path: "xml_versions/model_v001.xml" },
        { version_path: "xml_versions/model_v002.xml" },
        { reason: "anonymous" },
        "malformed",
      ],
    }),
    3,
  );
});

test("shouldPreflightCommandRunner warms every mode with Python or Morpheus CLI access", () => {
  assert.equal(shouldPreflightCommandRunner("python_web"), true);
  assert.equal(shouldPreflightCommandRunner("morpheus_cli"), true);
  assert.equal(shouldPreflightCommandRunner("morpheus_cli_docs"), true);
  assert.equal(shouldPreflightCommandRunner("morpheus_skill"), true);
  assert.equal(shouldPreflightCommandRunner("morpheus_mcp"), true);
});

test("resolveBenchmarkMaxConcurrentJobs serializes native Windows and normalizes other platforms", () => {
  assert.equal(resolveBenchmarkMaxConcurrentJobs(5, "win32"), 1);
  assert.equal(resolveBenchmarkMaxConcurrentJobs(5, "linux"), 5);
  assert.equal(resolveBenchmarkMaxConcurrentJobs(0, "linux"), 1);
  assert.equal(resolveBenchmarkMaxConcurrentJobs(2.9, "linux"), 2);
  assert.equal(resolveBenchmarkMaxConcurrentJobs(Number.NaN, "linux"), 1);
});

test("command-runner preflight fails fast for the unsupported Windows unelevated permission profile", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-windows-preflight-"));
  const codexHomeDir = path.join(root, "codex_home");
  const runDir = path.join(root, "run");
  await mkdir(codexHomeDir, { recursive: true });
  let startThreadCalls = 0;
  const rawError =
    "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed";
  const codex = {
    startThread: () => {
      startThreadCalls += 1;
      return {
        runStreamed: async () => ({
          events: (async function* () {
            yield { type: "error", message: rawError };
          })(),
        }),
      };
    },
  };

  const result = await (new BenchmarkRunner(testBenchmarkConfig(root)) as any).ensureCommandRunnerReady({
    codex,
    threadOptions: {},
    codexHomeDir,
    runDir,
  });

  assert.equal(startThreadCalls, 1);
  assert.deepEqual(result, {
    ok: false,
    error:
      "Command-runner preflight failed after 1 attempt: Native Windows benchmark command execution requires the elevated Codex sandbox because the unelevated sandbox cannot enforce the benchmark filesystem permission profile.",
  });
});

test("buildCommandRunnerPreflightPrompt asks for a neutral single-command workspace check", () => {
  const prompt = buildCommandRunnerPreflightPrompt();

  assert.match(prompt, /one shell command/i);
  assert.match(prompt, /pwd/i);
  assert.doesNotMatch(prompt, /benchmark|harness|score|mode/i);
});

test("hasSuccessfulCommandExecution detects a completed command", () => {
  assert.equal(
    hasSuccessfulCommandExecution([
      {
        type: "command_execution",
        command: "powershell -Command pwd",
        status: "completed",
        exit_code: 0,
      },
    ] as any),
    true,
  );
  assert.equal(
    hasSuccessfulCommandExecution([
      {
        type: "command_execution",
        command: "powershell -Command pwd",
        status: "failed",
        exit_code: -1,
      },
    ] as any),
    false,
  );
});

test("host technical evaluation runs a canonical Morpheus attempt for every benchmark mode", () => {
  assert.equal(shouldRunHostMorpheusBeforeTechnicalEvaluation("python_web"), true);
  assert.equal(shouldRunHostMorpheusBeforeTechnicalEvaluation("morpheus_cli"), true);
  assert.equal(shouldRunHostMorpheusBeforeTechnicalEvaluation("morpheus_skill"), true);
  assert.equal(shouldRunHostMorpheusBeforeTechnicalEvaluation("morpheus_mcp"), true);
});

test("host technical evaluation passes configured Morpheus thread count", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-host-threads-"));
  const runDir = path.join(root, "run_123");
  await mkdir(runDir, { recursive: true });
  const runner = new BenchmarkRunner(testBenchmarkConfig(root, { morpheusNumThreads: 4 }));
  const calls: Array<{ command: string; payload: Record<string, unknown> }> = [];
  (runner as any).bridge = {
    async invoke(command: string, payload: Record<string, unknown>) {
      calls.push({ command, payload });
      if (command === "run_morpheus_model") {
        return { ok: true, attempt_id: "attempt_001" };
      }
      return { ok: true, total_score: 7, evaluation_json_path: path.join(runDir, "evaluation.json") };
    },
  };

  await (runner as any).runHostTechnicalEvaluation("morpheus_mcp", "run_123", runDir, emptyBenchmarkDiagnostics());

  assert.equal(calls[0].command, "run_morpheus_model");
  assert.equal(calls[0].payload.threads, 4);
});

test("host technical evaluation inherits threads from the matching successful agent attempt", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-host-agent-threads-"));
  const runDir = path.join(root, "run_123");
  const agentWorkspaceDir = path.join(runDir, "agent_workspace");
  const matchingAttemptDir = path.join(agentWorkspaceDir, "attempts", "attempt_002");
  const newerAttemptDir = path.join(agentWorkspaceDir, "attempts", "attempt_003");
  await mkdir(matchingAttemptDir, { recursive: true });
  await mkdir(newerAttemptDir, { recursive: true });
  const modelXml = '<MorpheusModel version="4"><Time><RandomSeed value="42"/></Time></MorpheusModel>';
  await writeFile(path.join(agentWorkspaceDir, "model.xml"), modelXml, "utf8");
  await writeFile(path.join(matchingAttemptDir, "model.xml"), modelXml, "utf8");
  await writeFile(
    path.join(newerAttemptDir, "model.xml"),
    '<MorpheusModel version="4"><Time><RandomSeed value="99"/></Time></MorpheusModel>',
    "utf8",
  );
  await writeFile(
    path.join(agentWorkspaceDir, "run_manifest.json"),
    JSON.stringify({
      attempt_history: [
        {
          attempt_id: "attempt_002",
          command: ["morpheus", "-f", "model.xml", "--num-threads", "2"],
          returncode: 0,
        },
        {
          attempt_id: "attempt_003",
          command: ["morpheus", "-f", "model.xml", "--num-threads", "8"],
          returncode: 0,
          timed_out: false,
        },
      ],
    }),
    "utf8",
  );
  const runner = new BenchmarkRunner(testBenchmarkConfig(root, { morpheusNumThreads: null }));
  const calls: Array<{ command: string; payload: Record<string, unknown> }> = [];
  (runner as any).bridge = {
    async invoke(command: string, payload: Record<string, unknown>) {
      calls.push({ command, payload });
      if (command === "run_morpheus_model") {
        return { ok: true, attempt_id: "attempt_001" };
      }
      return { ok: true, total_score: 7, evaluation_json_path: path.join(runDir, "evaluation.json") };
    },
  };

  await (runner as any).runHostTechnicalEvaluation("morpheus_mcp", "run_123", runDir, emptyBenchmarkDiagnostics());

  assert.equal(calls[0].command, "run_morpheus_model");
  assert.equal(calls[0].payload.threads, 2);
});

test("resolveHostTechnicalEvaluationXmlPath prefers copied agent workspace model for relative assets", async () => {
  const tempDir = await mkdtemp(path.join(tmpdir(), "morpheus-host-eval-"));
  const runDir = path.join(tempDir, "run_123");
  await mkdir(path.join(runDir, "agent_workspace"), { recursive: true });
  await writeFile(path.join(runDir, "model.xml"), "<root/>", "utf8");
  await writeFile(path.join(runDir, "agent_workspace", "model.xml"), "<workspace/>", "utf8");

  assert.equal(
    await resolveHostTechnicalEvaluationXmlPath(runDir),
    path.join(runDir, "agent_workspace", "model.xml"),
  );
});

test("resolveHostTechnicalEvaluationXmlPath falls back to run model when no snapshot exists", async () => {
  const tempDir = await mkdtemp(path.join(tmpdir(), "morpheus-host-eval-"));
  const runDir = path.join(tempDir, "run_123");

  assert.equal(await resolveHostTechnicalEvaluationXmlPath(runDir), path.join(runDir, "model.xml"));
});

test("collectCapabilityViolations detects restricted local resources and Morpheus execution", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          "powershell -Command \"Get-Content E:\\PycharmProjects\\Morpheus.AI\\.agents\\skills\\morpheus\\SKILL.md\"",
      },
      {
        type: "command_execution",
        command:
          "powershell -Command \"Get-Content E:\\PycharmProjects\\Morpheus.AI\\.agents\\skills\\morpheus\\references\\model-template.md\"",
      },
      {
        type: "command_execution",
        command: "powershell -Command \"morpheus -f model.xml -o morpheus_smoke\"",
      },
      {
        type: "command_execution",
        command: "& 'C:\\Program Files\\Morpheus\\morpheus.exe' --file model.xml",
      },
      {
        type: "command_execution",
        command: "powershell -Command \"Get-Content E:\\PycharmProjects\\Morpheus.AI\\AGENTS.md\"",
      },
      {
        type: "command_execution",
        command:
          "powershell -Command \"Get-Content C:\\Users\\Administrator\\.codex\\plugins\\cache\\openai-curated\\superpowers\\6807e4de\\skills\\using-superpowers\\SKILL.md\"",
      },
      {
        type: "command_execution",
        command:
          "powershell -Command \"Get-Content C:\\Users\\Administrator\\AppData\\Local\\Temp\\2\\morpheus-modeling-sessions\\20260429_152140_1_Szabo2010_clean__python_web\\model.xml\"",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(new Set(violations), new Set([
    "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
    "Read local Morpheus skill files in a mode where the Morpheus skill is disabled.",
    "Read local Morpheus reference files in a mode where local Morpheus references are disabled.",
    "Read repository AGENTS.md instructions that are reserved for benchmark harness development.",
    "Used inherited Codex plugins or skills in a subject run.",
    "Read artifacts from another isolated modeling session.",
  ]));
});

test("collectCapabilityViolations allows AGENTS.md discovery without reading it", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "rg --files -g 'paper.txt' -g 'AGENTS.md' . && test -f AGENTS.md",
        aggregated_output: "paper.txt\n",
        exit_code: 1,
        status: "failed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations detects an AGENTS.md read after an existence guard", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "if [ -f AGENTS.md ]; then sed -n '1,80p' AGENTS.md; fi",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, [
    "Read repository AGENTS.md instructions that are reserved for benchmark harness development.",
  ]);
});

test("collectCapabilityViolations allows a guarded AGENTS.md read after discovery proves it absent", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "rg --files -g 'AGENTS.md' -g 'paper.txt' .",
        aggregated_output: "paper.txt\n",
        exit_code: 0,
        status: "completed",
      },
      {
        type: "command_execution",
        command: "if [ -f AGENTS.md ]; then sed -n '1,80p' AGENTS.md; fi",
        aggregated_output: "",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations ignores the modeling session parent in git errors", () => {
  const activeRunId = "20260825_001755_01_Szabo2010__morpheus_cli__rep02";
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "git status --short",
        aggregated_output:
          "fatal: not a git repository (or any parent up to mount point /tmp/morpheus-modeling-sessions/20260825_001126_session)\n",
        exit_code: 128,
        status: "failed",
      },
    ] as any,
    "morpheus_cli",
    activeRunId,
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations ignores quoted Morpheus search terms and heredoc prose", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          `/bin/bash -lc "rg --files . | rg -i '(\\\\.xml$|schema|template|Morpheus)' || true\npython - <<'PY'\nprint('Morpheus runtime unavailable')\nPY"`,
        aggregated_output: "paper.txt\nMorpheus runtime unavailable\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations ignores shell-requoted Morpheus search terms", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          `/bin/bash -lc "rg -n -i '"'^(abstract|results)|Berkhout|Morpheus|simulation|model'"' paper.txt | sed -n '1,260p'"`,
        aggregated_output: "21:I/YouCom_for_MorpheusML/BenchmarkPapers/model.xml\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations ignores Codex-requoted alternation in rg patterns", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: Buffer.from(
          "L2Jpbi9iYXNoIC1sYyAid2MgLWwgcGFwZXIudHh0ICYmIHNlZCAtbiAnMSw4MHAnIHBhcGVyLnR4dCAmJiByZyAtbiBcIiInXihBYnN0cmFjdHwxIEludHJvZHVjdGlvbnwxJyJcXC4xfFRhYmxlIDF8RmlnXFwuIDJ8RmlnXFwuIDN8RmlnXFwuIDR8Y3V0fEN1dHziiIJ0fHBhcnRpYWxfdHxoID18zrd8cHMgPXxMID18Z2FtbWF8TW9ycGhldXN8c291cmNlfGNvZGV8c2ltdWxhdGlvbnxtb2RlbClcIiBwYXBlci50eHQgfCBzZWQgLW4gJzEsMjYwcCciCg==",
          "base64",
        ).toString("utf8").trimEnd(),
        aggregated_output: "812 paper.txt\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations does not mistake the Morpheus.AI repo path for a CLI call", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          "powershell -Command \"Get-Content E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\run_123\\paper.txt\"",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations does not mistake command discovery for Morpheus CLI execution", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          '"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "Get-Command morpheus, morpheus-gui, morpheus-console -ErrorAction SilentlyContinue"',
      },
      {
        type: "command_execution",
        command: 'powershell -Command "where.exe morpheus"',
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations does not report a Morpheus command rejected by the unavailable shim", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "morpheus -f model.xml --outdir attempt_001",
        aggregated_output: "morpheus: command not found\n",
        exit_code: 127,
        status: "failed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations does not mistake inspecting the unavailable shim for executing Morpheus", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          "/bin/bash -lc \"sed -n '1,80p' /tmp/morpheus-modeling-codex-home/session/run/benchmark-tools/morpheus\"",
        aggregated_output: "#!/bin/sh\nprintf '%s\\n' 'morpheus: command not found' >&2\\nexit 127\\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations still detects Morpheus execution after a harmless pipeline command", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "echo model.xml | morpheus -f model.xml",
        aggregated_output: "simulation started\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, [
    "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
  ]);
});

test("collectCapabilityViolations requires a Morpheus reference path rather than matching prose", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          "/bin/bash -lc \"echo '--- local morpheus references ---' && rg --files benchmark-tools\"",
        aggregated_output: "benchmark-tools/benchmark-time-left\\n",
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations allows a parent-session search that returns only active-run artifacts", () => {
  const activeRunId = "20260822_021954_paper__morpheus_skill__rep01";
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command: "find /tmp/morpheus-modeling-sessions -type f -name logger.csv",
        aggregated_output:
          `/tmp/morpheus-modeling-sessions/benchmark_session/${activeRunId}/attempts/attempt_001/logger.csv\\n`,
        exit_code: 0,
        status: "completed",
      },
    ] as any,
    "morpheus_skill",
    activeRunId,
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations ignores malformed paths that still belong to the active run", () => {
  const activeRunId = "20260824_094656_11_Anlas2024__morpheus_cli_docs__rep01__replacement01";
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          `/bin/bash -lc "morpheus -f model.xml --outdir /tmp/morpheus-modeling-sessions/20260821_231928_session/20260821_231928_session/${activeRunId}/attempts/attempt_003"`,
      },
      {
        type: "command_execution",
        command:
          "/bin/bash -lc \"morpheus -f model.xml --outdir /tmp/morpheus-modeling-sessions/20260821_231928_session/20260824_094656_11_Anlas2024__Anlas2024__morpheus_cli_docs__rep01__replacement01/attempts/attempt_003\"",
      },
      {
        type: "command_execution",
        command:
          "/bin/bash -lc \"morpheus -f model.xml > /tmp/morpheus-modeling-sessions/20260821_231928_session/20260821_231928_benchmark.log\"",
      },
      {
        type: "command_execution",
        command:
          `/bin/bash -lc "cat /tmp/morpheus-modeling-sessions/20260821_231928_session/${activeRunId}/attempts/20260824_111303_99_output__morpheus_skill__rep05/model.xml"`,
      },
    ] as any,
    "morpheus_cli_docs",
    activeRunId,
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations still detects foreign run paths", () => {
  const activeRunId = "20260824_094656_11_Anlas2024__morpheus_cli_docs__rep01__replacement01";
  const commands = [
    "/bin/bash -lc \"cat /tmp/morpheus-modeling-sessions/20260821_231928_session/20260824_111303_11_Anlas2024__morpheus_skill__rep05__replacement01/model.xml\"",
    "/bin/bash -lc \"cat /tmp/morpheus-modeling-sessions/20260821_231928_session/20260821_231928_session/20260824_111303_11_Anlas2024__morpheus_skill__rep05__replacement01/model.xml\"",
    "/bin/bash -lc \"cat /tmp/morpheus-modeling-sessions/20260821_231928_session/20260824_094656_11_Anlas2024__extra__morpheus_cli_docs__rep01__replacement01/model.xml\"",
  ];

  for (const command of commands) {
    const violations = collectCapabilityViolations(
      [{ type: "command_execution", command }] as any,
      "morpheus_cli_docs",
      activeRunId,
    );
    assert.deepEqual(violations, [
      "Read artifacts from another isolated modeling session.",
    ]);
  }
});

test("reconcileCapabilityViolationAudit removes a stored false positive and its derived error", async () => {
  const runnerModule = await import("../src/benchmark/runner.js");
  const reconcileCapabilityViolationAudit = (
    runnerModule as unknown as {
      reconcileCapabilityViolationAudit: (
        result: PaperRunResult,
        items: Array<Record<string, unknown>>,
      ) => PaperRunResult;
    }
  ).reconcileCapabilityViolationAudit;
  const result = {
    mode: "python_web",
    runId: "active_run",
    capabilityViolations: [
      "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
    ],
    error: "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
    executions: [
      {
        runId: "active_run",
        error: "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
      },
    ] as any,
  } as PaperRunResult;

  const reconciled = reconcileCapabilityViolationAudit(result, [
    {
      type: "command_execution",
      command: "sed -n '1,80p' /tmp/codex-home/benchmark-tools/morpheus",
      aggregated_output: "morpheus: command not found\n",
      exit_code: 0,
      status: "completed",
    },
  ]);

  assert.deepEqual(reconciled.capabilityViolations, []);
  assert.equal(reconciled.error, undefined);
  assert.equal(reconciled.executions?.[0].error, null);

  const repeated = reconcileCapabilityViolationAudit({
    ...result,
    capabilityViolations: [],
    error: undefined,
  }, []);
  assert.equal(repeated.executions?.[0].error, null);
});

test("collectCapabilityViolations does not mistake quoted Morpheus text for CLI execution", () => {
  const violations = collectCapabilityViolations(
    [
      {
        type: "command_execution",
        command:
          `"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command "@'\nterms=['computational','model','simulation','Morpheus','implantation']\nprint(terms)\n'@ | python -"`,
      },
    ] as any,
    "python_web",
  );

  assert.deepEqual(violations, []);
});

test("collectCapabilityViolations detects disabled MCP use and allows active session artifacts", () => {
  const violations = collectCapabilityViolations(
    [
      { type: "mcp_tool_call", server: "morpheus", tool: "write_model_xml" },
      {
        type: "command_execution",
        command: "ls /tmp/morpheus-modeling-sessions/active_run_123/attempts",
        status: "completed",
        exit_code: 0,
      },
    ] as any,
    "python_web",
    "active_run_123",
  );

  assert.deepEqual(violations, ["Used Morpheus MCP tools in a mode where Morpheus MCP is disabled."]);
});

test("collectInfrastructureFailures detects unrecovered Windows sandbox command-runner launch failures", () => {
  const failures = collectInfrastructureFailures([
    {
      type: "command_execution",
      command: "powershell -Command Get-Content paper.txt",
      status: "failed",
      exit_code: -1,
      aggregated_output:
        'execution error: Io(Custom { kind: Other, error: "windows sandbox: CreateProcessWithLogonW failed: 1326" })',
    },
    {
      type: "file_change",
      changes: [{ path: "model.xml", kind: "add" }],
      status: "completed",
    },
  ] as any);

  assert.deepEqual(failures, [
    "Windows sandbox command execution was unavailable because Codex could not launch its command runner (CreateProcessWithLogonW error 1326).",
  ]);
});

test("collectInfrastructureFailures detects managed Windows PowerShell preflight load failures", () => {
  const powerShellFailure = "Internal Windows PowerShell error. Loading managed Windows PowerShell failed with error 8009001d.";
  const failures = collectInfrastructureFailures([
    {
      type: "command_execution",
      command: "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -Command pwd",
      status: "failed",
      exit_code: -65536,
      aggregated_output: powerShellFailure.split("").join("\u0000"),
    },
  ] as any);

  assert.deepEqual(failures, [
    "Windows PowerShell command execution was unavailable because managed Windows PowerShell failed to initialize (error 8009001d / NTE_PROVIDER_DLL_FAIL).",
  ]);
});

test("isSystemicCommandRunnerInfrastructureFailure detects preflight sandbox launch failures", () => {
  assert.equal(
    isSystemicCommandRunnerInfrastructureFailure({
      stopReason: "infrastructure_failure",
      summary:
        "Infrastructure failure before subject turn: Command-runner preflight failed after 1 attempt: windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed",
    }),
    true,
  );
  assert.equal(
    isSystemicCommandRunnerInfrastructureFailure({
      stopReason: "infrastructure_failure",
      summary:
        "Infrastructure failure before subject turn: Command-runner preflight failed after 3 attempts: Windows sandbox command execution was unavailable because Codex could not launch its command runner (CreateProcessWithLogonW error 1326).",
    }),
    true,
  );
  assert.equal(
    isSystemicCommandRunnerInfrastructureFailure({
      stopReason: "infrastructure_failure",
      summary:
        "Infrastructure failure before subject turn: Command-runner preflight failed after 3 attempts: Windows PowerShell command execution was unavailable because managed Windows PowerShell failed to initialize (error 8009001d / NTE_PROVIDER_DLL_FAIL).",
    }),
    true,
  );
  assert.equal(
    isSystemicCommandRunnerInfrastructureFailure({
      stopReason: "infrastructure_failure",
      summary:
        "Infrastructure failure before subject turn: Command-runner preflight failed after 3 attempts: Your access token could not be refreshed because your refresh token was already used. Please log out and sign in again.",
    }),
    true,
  );
  assert.equal(
    isSystemicCommandRunnerInfrastructureFailure({
      stopReason: "infrastructure_failure",
      summary: "Morpheus simulation failed because the XML was invalid.",
    }),
    false,
  );
});

test("collectInfrastructureFailures ignores transient sandbox launch failures once commands recover", () => {
  const failures = collectInfrastructureFailures([
    {
      type: "command_execution",
      command: "powershell -Command Get-Content paper.txt",
      status: "failed",
      exit_code: -1,
      aggregated_output: "runner launch failed before process start: error=1326",
    },
    {
      type: "command_execution",
      command: "powershell -Command Get-ChildItem",
      status: "completed",
      exit_code: 0,
      aggregated_output: "paper.txt\r\nmodel.xml\r\n",
    },
  ] as any);

  assert.deepEqual(failures, []);
});

test("collectInfrastructureFailures reports command-runner launch failures even when MCP tools succeed", () => {
  const failures = collectInfrastructureFailures([
    {
      type: "command_execution",
      command: "powershell -Command Get-Content paper.txt",
      status: "failed",
      exit_code: -1,
      aggregated_output:
        'execution error: Io(Custom { kind: Other, error: "windows sandbox: CreateProcessWithLogonW failed: 1326" })',
    },
    {
      type: "mcp_tool_call",
      server: "morpheus",
      tool: "run_morpheus_model",
      status: "completed",
      result: { structured_content: { result: { ok: true } } },
    },
  ] as any);

  assert.deepEqual(failures, [
    "Windows sandbox command execution was unavailable because Codex could not launch its command runner (CreateProcessWithLogonW error 1326).",
  ]);
});

test("collectInfrastructureFailures does not let unrelated MCP tools mask command-runner failures", () => {
  const failures = collectInfrastructureFailures([
    {
      type: "command_execution",
      command: "powershell -Command Get-Content paper.txt",
      status: "failed",
      exit_code: -1,
      aggregated_output:
        'execution error: Io(Custom { kind: Other, error: "windows sandbox: CreateProcessWithLogonW failed: 1326" })',
    },
    {
      type: "mcp_tool_call",
      server: "codex",
      tool: "list_mcp_resources",
      status: "completed",
      result: { structured_content: { ok: true } },
    },
  ] as any);

  assert.deepEqual(failures, [
    "Windows sandbox command execution was unavailable because Codex could not launch its command runner (CreateProcessWithLogonW error 1326).",
  ]);
});

test("ensureFailureReproductionReport writes report files for early failed runs", async () => {
  const runDir = await mkdtemp(path.join(tmpdir(), "morpheus-failed-report-"));
  const result: PaperRunResult = {
    paper: "paper.pdf",
    pdfPath: "benchmark_papers/paper.pdf",
    mode: "morpheus_mcp",
    modeLabel: "Full Morpheus MCP harness",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: true,
      morpheusSkill: true,
      morpheusMcp: true,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
    capabilityViolations: ["Read artifacts from another isolated modeling session."],
    runId: "run_123",
    threadId: "thread_123",
    repetition: 1,
    startedAt: "2026-05-07T12:00:00.000Z",
    finishedAt: "2026-05-07T12:00:05.000Z",
    durationMs: 5_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    stopReason: "infrastructure_failure",
    artifactStatus: "missing",
    attempts: 0,
    modelRefinementCount: 0,
    technicalScore: null,
    reproductionScore: null,
    technicalEvaluationPath: null,
    reproductionReportPath: null,
    reproductionReportTextPath: null,
    runManifestPath: path.join(runDir, "run_manifest.json"),
    benchmarkFocus: "focus",
    summary: "Capability violation: Read artifacts from another isolated modeling session.",
    error: "Capability violation: Read artifacts from another isolated modeling session.",
  };

  const withReport = await ensureFailureReproductionReport(result);

  assert.equal(withReport.reproductionReportPath, path.join(runDir, "reproduction_report.json"));
  assert.equal(withReport.reproductionReportTextPath, path.join(runDir, "reproduction_report.txt"));
  const text = await readFile(withReport.reproductionReportTextPath!, "utf8");
  assert.match(text, /MORPHEUS REPRODUCTION REPORT/);
  assert.match(text, /Stop Reason: infrastructure_failure/);
  assert.match(text, /Artifact Status: missing/);
  assert.match(text, /Wall Time: 5s/);
  assert.match(text, /Tokens: 0 total/);
  assert.match(text, /Capability Violations: 1/);
  assert.match(text, /No reproduction rubric was returned/);
});

test("mapWithConcurrency limits concurrent work while preserving result order", async () => {
  let active = 0;
  let maxActive = 0;
  const results = await mapWithConcurrency([1, 2, 3, 4], 2, async (value) => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    await new Promise((resolve) => setTimeout(resolve, 5));
    active -= 1;
    return value * 10;
  });

  assert.deepEqual(results, [10, 20, 30, 40]);
  assert.equal(maxActive, 2);
});

test("mapWithConcurrency stops launching queued work when the start predicate closes", async () => {
  const started: number[] = [];
  let shouldStart = true;

  const results = await mapWithConcurrency(
    [1, 2, 3, 4],
    1,
    async (value) => {
      started.push(value);
      shouldStart = false;
      return value * 2;
    },
    () => shouldStart,
  );

  assert.deepEqual(started, [1]);
  assert.deepEqual(results, [2]);
});

test("mapWithConcurrency handles empty input and clamps concurrency", async () => {
  const empty = await mapWithConcurrency([], 0, async () => "never");
  const started: number[] = [];
  const results = await mapWithConcurrency([1, 2], 0, async (value) => {
    started.push(value);
    return value * 3;
  });

  assert.deepEqual(empty, []);
  assert.deepEqual(started, [1, 2]);
  assert.deepEqual(results, [3, 6]);
});

test("mergeTurnDiagnostics separates Morpheus simulation time from agent analysis time", () => {
  const diagnostics = emptyBenchmarkDiagnostics();
  mergeTurnDiagnostics(diagnostics, {
    durationMs: 10_000,
    morpheusSimulationMs: 3_000,
    usage: {
      input_tokens: 100,
      cached_input_tokens: 40,
      cache_write_input_tokens: 12,
      output_tokens: 25,
      reasoning_output_tokens: 10,
    },
  });
  mergeTurnDiagnostics(diagnostics, {
    durationMs: 2_000,
    morpheusSimulationMs: 0,
    usage: null,
  });

  assert.equal(diagnostics.agentWallTimeMs, 12_000);
  assert.equal(diagnostics.morpheusSimulationTimeMs, 3_000);
  assert.equal(diagnostics.agentAnalysisTimeMs, 9_000);
  assert.equal(diagnostics.turnCount, 2);
  assert.equal(diagnostics.attemptCount, 0);
  assert.equal(diagnostics.hostMorpheusRunTimeMs, 0);
  assert.equal(diagnostics.hostTechnicalEvaluationTimeMs, 0);
  assert.deepEqual(diagnostics.tokens, {
    input: 100,
    cachedInput: 40,
    cacheWriteInput: 12,
    output: 25,
    reasoningOutput: 10,
    total: 125,
  });
});

test("mergeTurnDiagnostics clamps analysis time when simulation exceeds wall time", () => {
  const diagnostics = emptyBenchmarkDiagnostics();

  mergeTurnDiagnostics(diagnostics, {
    durationMs: 1_000,
    morpheusSimulationMs: 2_500,
    usage: null,
  });

  assert.equal(diagnostics.agentWallTimeMs, 1_000);
  assert.equal(diagnostics.morpheusSimulationTimeMs, 2_500);
  assert.equal(diagnostics.agentAnalysisTimeMs, 0);
});

test("buildBenchmarkComparison reports timing and token diagnostics per mode", () => {
  const pythonDiagnostics = emptyBenchmarkDiagnostics();
  pythonDiagnostics.turnCount = 1;
  pythonDiagnostics.agentWallTimeMs = 4_000;
  pythonDiagnostics.agentAnalysisTimeMs = 4_000;
  pythonDiagnostics.hostMorpheusRunTimeMs = 1_000;
  pythonDiagnostics.hostTechnicalEvaluationTimeMs = 250;
  pythonDiagnostics.tokens = {
    input: 100,
    cachedInput: 40,
    cacheWriteInput: 11,
    output: 23,
    reasoningOutput: 7,
    total: 123,
  };

  const mcpDiagnostics = emptyBenchmarkDiagnostics();
  mcpDiagnostics.turnCount = 3;
  mcpDiagnostics.attemptCount = 2;
  mcpDiagnostics.agentWallTimeMs = 10_000;
  mcpDiagnostics.morpheusSimulationTimeMs = 3_000;
  mcpDiagnostics.agentAnalysisTimeMs = 7_000;
  mcpDiagnostics.tokens = {
    input: 500,
    cachedInput: 400,
    cacheWriteInput: 22,
    output: 50,
    reasoningOutput: 20,
    total: 550,
  };

  const baseResult = {
    paper: "paper.pdf",
    pdfPath: "benchmark_papers/paper.pdf",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: false,
      morpheusSkill: false,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: false,
    },
    capabilityViolations: [],
    threadId: "thread_123",
    repetition: 1,
    startedAt: "2026-05-07T12:00:00.000Z",
    finishedAt: "2026-05-07T12:00:01.000Z",
    attempts: 1,
    modelRefinementCount: 0,
    technicalScore: 7,
    reproductionScore: 8,
    technicalEvaluationPath: "technical.json",
    reproductionReportPath: "reproduction.json",
    reproductionReportTextPath: "reproduction.txt",
    runManifestPath: "run_manifest.json",
    benchmarkFocus: null,
    summary: "Done.",
  } satisfies Omit<PaperRunResult, "mode" | "modeLabel" | "runId" | "durationMs" | "diagnostics">;

  const summary = {
    generatedAt: "2026-05-07T12:00:00.000Z",
    config: { benchmarkModes: ["python_web", "morpheus_mcp"] },
    results: [
      {
        ...baseResult,
        mode: "python_web",
        modeLabel: "Python + web search",
        runId: "run_python",
        durationMs: 5_000,
        diagnostics: pythonDiagnostics,
        modelRefinementCount: 2,
      },
      {
        ...baseResult,
        mode: "morpheus_mcp",
        modeLabel: "Full Morpheus MCP harness",
        runId: "run_mcp",
        durationMs: 12_000,
        diagnostics: mcpDiagnostics,
        modelRefinementCount: 5,
      },
    ],
  } as unknown as BenchmarkSummary;

  const comparison = buildBenchmarkComparison(summary);
  assert.equal((comparison.modes[0] as any).totalModelRefinements, 2);
  assert.equal((comparison.modes[0] as any).averageModelRefinements, 2);
  assert.equal((comparison.modes[1] as any).totalModelRefinements, 5);
  assert.equal((comparison.modes[1] as any).averageModelRefinements, 5);
  assert.equal(comparison.modes[0].totalDurationMs, 5_000);
  assert.equal(comparison.modes[0].averageDurationMs, 5_000);
  assert.equal(comparison.modes[0].diagnostics.tokens.total, 123);
  assert.equal(comparison.modes[1].diagnostics.turnCount, 3);
  assert.equal(comparison.modes[1].diagnostics.morpheusSimulationTimeMs, 3_000);
  assert.equal(comparison.modes[0].averageBiologicalScore, null);

  const csv = formatComparisonCsv(comparison);
  assert.match(csv.split("\n")[0], /totalModelRefinements,averageModelRefinements,totalDurationMs,averageDurationMs,turnCount/);
  assert.match(csv.split("\n")[0], /inputTokens,cachedInputTokens,cacheWriteInputTokens,outputTokens,reasoningOutputTokens,totalTokens/);
  assert.match(csv, /python_web,Python \+ web search,1,/);
});

test("formatComparisonCsv escapes commas quotes and newlines", () => {
  const diagnostics = emptyBenchmarkDiagnostics();
  const csv = formatComparisonCsv({
    generatedAt: "2026-05-01T00:00:00.000Z",
    modes: [
      {
        mode: "python_web",
        modeLabel: 'Python, "web"\nmode',
        totalRuns: 1,
        totalPapers: 1,
        agentFinishedRuns: 1,
        timeLimitRuns: 0,
        infrastructureFailureRuns: 0,
        scoreableRuns: 1,
        replacementRuns: 0,
        totalModelRefinements: 0,
        averageModelRefinements: 0,
        totalDurationMs: 0,
        averageDurationMs: 0,
        diagnostics,
        averageTechnicalScore: 0,
        averageReproductionScore: 0,
        averageBiologicalScore: 0,
        capabilityViolationCount: 0,
      },
    ],
    paperModes: [],
  } as any);

  assert.match(csv, /python_web,"Python, ""web""\nmode",1,1/);
});

test("buildBenchmarkComparison distinguishes repeated runs from unique papers", () => {
  const makeResult = (paper: string, repetition: number) => ({
    paper,
    mode: "python_web",
    repetition,
    durationMs: 1_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    technicalScore: 7,
    reproductionScore: 8,
    biologicalScore: null,
    modelRefinementCount: 0,
    capabilityViolations: [],
  });
  const comparison = buildBenchmarkComparison({
    generatedAt: "2026-05-01T00:00:00.000Z",
    config: { benchmarkModes: ["python_web"] },
    results: [makeResult("paper_a.pdf", 1), makeResult("paper_a.pdf", 2), makeResult("paper_b.pdf", 1)],
  } as unknown as BenchmarkSummary);

  assert.equal(comparison.modes[0].totalRuns, 3);
  assert.equal(comparison.modes[0].totalPapers, 2);
  assert.match(formatComparisonCsv(comparison), /^mode,modeLabel,totalRuns,totalPapers/m);
});

test("formatComparisonCsv emits only the header for empty comparison modes", () => {
  const csv = formatComparisonCsv({
    generatedAt: "2026-05-01T00:00:00.000Z",
    modes: [],
  } as any);

  assert.deepEqual(csv.trimEnd().split("\n"), [csv.trimEnd()]);
  assert.match(csv, /^mode,modeLabel,totalRuns,totalPapers/);
});

test("buildPaperModeStatistics summarizes repeated runs by paper and mode", () => {
  const makeDiagnostics = (totalTokens: number) => {
    const diagnostics = emptyBenchmarkDiagnostics();
    diagnostics.turnCount = totalTokens / 100;
    diagnostics.agentWallTimeMs = totalTokens * 10;
    diagnostics.tokens = {
      input: totalTokens,
      cachedInput: totalTokens / 2,
      cacheWriteInput: totalTokens / 4,
      output: totalTokens / 10,
      reasoningOutput: totalTokens / 20,
      total: totalTokens,
    };
    return diagnostics;
  };
  const baseResult = {
    paper: "paper.pdf",
    pdfPath: "benchmark_papers/paper.pdf",
    mode: "morpheus_mcp",
    modeLabel: "Full Morpheus MCP harness",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: false,
      morpheusSkill: false,
      morpheusMcp: true,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
    capabilityViolations: [],
    threadId: "thread_123",
    startedAt: "2026-05-07T12:00:00.000Z",
    finishedAt: "2026-05-07T12:00:01.000Z",
    stopReason: "agent_finished",
    artifactStatus: "scoreable",
    replacementCount: 0,
    attempts: 1,
    modelRefinementCount: 1,
    technicalScore: 4,
    reproductionScore: 6,
    technicalEvaluationPath: "technical.json",
    reproductionReportPath: "reproduction.json",
    reproductionReportTextPath: "reproduction.txt",
    runManifestPath: "run_manifest.json",
    benchmarkFocus: null,
    summary: "Done.",
  } satisfies Omit<PaperRunResult, "runId" | "repetition" | "durationMs" | "diagnostics">;

  const [stats] = buildPaperModeStatistics([
    {
      ...baseResult,
      runId: "run_1",
      repetition: 1,
      durationMs: 1_000,
      diagnostics: makeDiagnostics(100),
    },
    {
      ...baseResult,
      runId: "run_2",
      repetition: 2,
      stopReason: "time_limit",
      attempts: 2,
      modelRefinementCount: 3,
      technicalScore: 6,
      reproductionScore: 7,
      durationMs: 2_000,
      diagnostics: makeDiagnostics(200),
    },
    {
      ...baseResult,
      runId: "run_3",
      repetition: 3,
      attempts: 3,
      modelRefinementCount: 5,
      technicalScore: 8,
      reproductionScore: 8,
      durationMs: 3_000,
      diagnostics: makeDiagnostics(300),
    },
  ], 3);

  assert.equal(stats.paper, "paper.pdf");
  assert.equal(stats.mode, "morpheus_mcp");
  assert.equal(stats.expectedRepetitions, 3);
  assert.equal(stats.observedRepetitions, 3);
  assert.deepEqual(stats.repetitions, [1, 2, 3]);
  assert.deepEqual(stats.runIds, ["run_1", "run_2", "run_3"]);
  assert.equal(stats.agentFinishedRuns, 2);
  assert.equal(stats.timeLimitRuns, 1);
  assert.equal(stats.infrastructureFailureRuns, 0);
  assert.equal(stats.scoreableRuns, 3);
  assert.deepEqual(stats.metrics.technicalScore, { count: 3, mean: 6, stdDev: 2, min: 4, max: 8, sum: 18 });
  assert.deepEqual(stats.metrics.reproductionScore, { count: 3, mean: 7, stdDev: 1, min: 6, max: 8, sum: 21 });
  assert.deepEqual(stats.metrics.modelRefinementCount, { count: 3, mean: 3, stdDev: 2, min: 1, max: 5, sum: 9 });
  assert.deepEqual(stats.metrics.durationMs, { count: 3, mean: 2000, stdDev: 1000, min: 1000, max: 3000, sum: 6000 });
  assert.deepEqual(stats.metrics.totalTokens, { count: 3, mean: 200, stdDev: 100, min: 100, max: 300, sum: 600 });
});

test("buildBenchmarkComparison reports v2 stop, artifact, and replacement outcomes", () => {
  const diagnostics = emptyBenchmarkDiagnostics();
  const baseResult = {
    paper: "paper.pdf",
    pdfPath: "benchmark_papers/paper.pdf",
    mode: "python_web",
    modeLabel: "Python + web search",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: false,
      morpheusSkill: false,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: false,
    },
    capabilityViolations: [],
    threadId: "thread_123",
    repetition: 1,
    startedAt: "2026-05-07T12:00:00.000Z",
    finishedAt: "2026-05-07T12:00:01.000Z",
    durationMs: 1_000,
    attempts: 1,
    modelRefinementCount: 0,
    technicalScore: 7,
    reproductionScore: 7,
    technicalEvaluationPath: "technical.json",
    reproductionReportPath: "reproduction.json",
    reproductionReportTextPath: "reproduction.txt",
    runManifestPath: "run_manifest.json",
    benchmarkFocus: null,
    diagnostics,
  } satisfies Omit<PaperRunResult, "runId" | "summary">;

  const summary = {
    generatedAt: "2026-05-07T12:00:00.000Z",
    config: { benchmarkModes: ["python_web"] },
    results: [
      { ...baseResult, runId: "run_completed", stopReason: "agent_finished", artifactStatus: "scoreable", replacementCount: 0, summary: "Done." },
      { ...baseResult, runId: "run_time_limit", stopReason: "time_limit", artifactStatus: "scoreable", replacementCount: 0, summary: "Useful output." },
      { ...baseResult, runId: "run_failed", stopReason: "infrastructure_failure", artifactStatus: "missing", replacementCount: 1, summary: "Failed.", error: "Failed." },
    ],
  } as unknown as BenchmarkSummary;

  const comparison = buildBenchmarkComparison(summary);

  assert.equal(comparison.modes[0].agentFinishedRuns, 1);
  assert.equal(comparison.modes[0].timeLimitRuns, 1);
  assert.equal(comparison.modes[0].infrastructureFailureRuns, 1);
  assert.equal(comparison.modes[0].scoreableRuns, 2);
  assert.equal(comparison.modes[0].replacementRuns, 1);
});

test("shouldTimeCommandAsMorpheusSimulation detects real Morpheus CLI execution only", () => {
  assert.equal(
    shouldTimeCommandAsMorpheusSimulation('powershell -Command "morpheus -f model.xml --outdir agent_runs/attempt_001"'),
    true,
  );
  assert.equal(shouldTimeCommandAsMorpheusSimulation("timeout 60 morpheus -f model.xml"), true);
  assert.equal(shouldTimeCommandAsMorpheusSimulation("env FOO=x morpheus -f model.xml"), true);
  assert.equal(shouldTimeCommandAsMorpheusSimulation("command morpheus -f model.xml"), true);
  assert.equal(
    shouldTimeCommandAsMorpheusSimulation("/bin/bash --noprofile -lc 'morpheus -f model.xml'"),
    true,
  );
  assert.equal(shouldTimeCommandAsMorpheusSimulation('powershell -Command "Get-Command morpheus"'), false);
  assert.equal(shouldTimeCommandAsMorpheusSimulation('powershell -Command "Get-Content paper.txt"'), false);
});

const QUOTA_ERROR =
  "You’ve hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Oct 14th, 2026 9:30 AM.";

function quotaFailedExecution(executionId: string, replacementFor: string | null, error: string) {
  return {
    executionId,
    runId: `${executionId}_run`,
    replacementFor,
    replacementCount: replacementFor === null ? 0 : 1,
    stopReason: "infrastructure_failure",
    workspaceDir: "",
    codexHomeDir: "",
    model: "gpt-5.5",
    reasoningEffort: "high",
    totalTimeLimitMs: 14_400_000,
    finalizationReserveMs: 600_000,
    subjectExecutionMs: 0,
    morpheusSimulationMs: 0,
    totalJobMs: 1_000,
    artifactStatus: "missing",
    startedAt: null,
    finishedAt: null,
    error,
  } as NonNullable<PaperRunResult["executions"]>[number];
}

function testInfrastructureFailure(
  pdfPath: string,
  repetition: number,
  error: string,
  overrides: Partial<PaperRunResult> = {},
): PaperRunResult {
  const assignmentId = `paper__morpheus_mcp__rep${String(repetition).padStart(2, "0")}`;
  return {
    paper: path.basename(pdfPath),
    pdfPath,
    mode: "morpheus_mcp",
    modeLabel: BENCHMARK_MODE_DEFINITIONS.morpheus_mcp.label,
    capabilities: BENCHMARK_MODE_DEFINITIONS.morpheus_mcp.capabilities,
    capabilityViolations: [],
    runId: "failed_run",
    threadId: null,
    repetition,
    startedAt: "2026-10-08T00:00:00.000Z",
    finishedAt: "2026-10-08T00:00:20.000Z",
    durationMs: 20_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    attempts: 0,
    modelRefinementCount: 0,
    technicalScore: null,
    reproductionScore: null,
    technicalEvaluationPath: null,
    reproductionReportPath: null,
    reproductionReportTextPath: null,
    runManifestPath: null,
    benchmarkFocus: null,
    summary: error,
    error,
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId,
    executionId: `${assignmentId}__execution_01`,
    replacementFor: null,
    replacementCount: 0,
    replacementEligible: false,
    stopReason: "infrastructure_failure",
    artifactStatus: "missing",
    workspaceDir: "",
    codexHomeDir: "",
    model: "gpt-5.5",
    reasoningEffort: "high",
    totalTimeLimitMs: 14_400_000,
    finalizationReserveMs: 600_000,
    subjectExecutionMs: 0,
    morpheusSimulationMs: 0,
    totalJobMs: 20_000,
    ...overrides,
  } as PaperRunResult;
}

test("codexServiceFailureKind recognizes Codex quota and capacity refusals", () => {
  assert.equal(codexServiceFailureKind(QUOTA_ERROR), "quota_exhausted");
  assert.equal(
    codexServiceFailureKind(`Infrastructure failure before subject turn: Command-runner preflight failed after 1 attempt: ${QUOTA_ERROR}`),
    "quota_exhausted",
  );
  assert.equal(
    codexServiceFailureKind("Error running remote compact task: Selected model is at capacity. Please try a different model."),
    "model_at_capacity",
  );
  assert.equal(codexServiceFailureKind("Subject process failed."), null);
  assert.equal(codexServiceFailureKind(null), null);
});

test("Codex quota and capacity failures do not use up an assignment's clean replacement", () => {
  const generic = "Infrastructure failure: ENOSPC";
  const withExecutions = (errors: string[]) => ({
    stopReason: "infrastructure_failure" as const,
    replacementCount: 1 as const,
    error: errors.at(-1),
    summary: errors.at(-1) ?? "",
    executions: errors.map((error, index) =>
      quotaFailedExecution(`e${index + 1}`, index === 0 ? null : `e${index}`, error)
    ),
  });

  assert.equal(canRerunInfrastructureFailure(withExecutions([QUOTA_ERROR, QUOTA_ERROR])), true);
  assert.equal(canRerunInfrastructureFailure(withExecutions([QUOTA_ERROR, QUOTA_ERROR, QUOTA_ERROR])), true);
  assert.equal(canRerunInfrastructureFailure(withExecutions([generic, QUOTA_ERROR])), true);
  assert.equal(canRerunInfrastructureFailure(withExecutions([QUOTA_ERROR, generic])), true);
  assert.equal(canRerunInfrastructureFailure(withExecutions([generic, generic])), false);
  assert.equal(canRerunInfrastructureFailure(withExecutions([generic, QUOTA_ERROR, generic])), false);
  assert.equal(
    canRerunInfrastructureFailure({ ...withExecutions([QUOTA_ERROR]), stopReason: "agent_finished" }),
    false,
  );
});

test("explicit recoverRun reruns quota-exhausted assignments and launches never-started ones", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-quota-recovery-"));
  const config = testBenchmarkConfig(root, { benchmarkRepetitions: 2 });
  const pdfPath = path.join(root, "papers", "paper.pdf");
  await mkdir(path.dirname(pdfPath), { recursive: true });
  await writeFile(pdfPath, "%PDF-1.4\n", "utf8");
  const jobs = [1, 2].map((repetition) => ({ pdfPath, mode: "morpheus_mcp", repetition }));
  await writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkId: "quota-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-10-08T00:00:00.000Z",
    config,
    jobs,
  }), "utf8");
  const assignmentId = "paper__morpheus_mcp__rep01";
  const prior = testInfrastructureFailure(pdfPath, 1, QUOTA_ERROR, {
    executionId: `${assignmentId}__execution_02`,
    replacementFor: `${assignmentId}__execution_01`,
    replacementCount: 1,
    selectedExecutionId: `${assignmentId}__execution_02`,
    executions: [
      quotaFailedExecution(`${assignmentId}__execution_01`, null, QUOTA_ERROR),
      quotaFailedExecution(`${assignmentId}__execution_02`, `${assignmentId}__execution_01`, QUOTA_ERROR),
    ],
  });
  await mkdir(path.join(root, "assignment_results"), { recursive: true });
  await writeFile(path.join(root, "assignment_results", `${assignmentId}.json`), JSON.stringify(prior), "utf8");
  await writeFile(path.join(root, "benchmark_summary.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    config,
    benchmarkId: "quota-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-10-08T00:00:00.000Z",
    finishedAt: "2026-10-08T00:00:20.000Z",
    generatedAt: "2026-10-08T00:00:20.000Z",
    durationMs: 20_000,
    diagnostics: emptyBenchmarkDiagnostics(),
    benchmarkRepetitions: 2,
    paperModeStatistics: [],
    results: [prior],
  }), "utf8");

  const executions: Array<{ executionId: string; replacementFor: string | null; runNameSuffix: string }> = [];
  const runner = new BenchmarkRunner(config);
  (runner as any).processExecution = async (
    _pdfPath: string,
    _mode: "morpheus_mcp",
    _benchmarkRunDir: string,
    repetition: number,
    execution: { executionId: string; replacementFor: string | null; replacementCount: 0 | 1; runNameSuffix: string },
  ) => {
    executions.push(execution);
    return {
      ...testInfrastructureFailure(pdfPath, repetition, ""),
      runId: `run_${execution.executionId}`,
      summary: "Finished.",
      error: undefined,
      executionId: execution.executionId,
      replacementFor: execution.replacementFor,
      replacementCount: execution.replacementCount,
      stopReason: "agent_finished",
      artifactStatus: "scoreable",
      technicalScore: 7,
    } satisfies PaperRunResult;
  };

  const recovered = await runner.recoverRun(root, { rerunInfrastructureFailures: true });

  assert.deepEqual(executions.map((execution) => execution.executionId).sort(), [
    `${assignmentId}__execution_03`,
    "paper__morpheus_mcp__rep02__execution_01",
  ]);
  const rerun = executions.find((execution) => execution.executionId.endsWith("execution_03"))!;
  assert.equal(rerun.replacementFor, `${assignmentId}__execution_02`);
  assert.equal(rerun.runNameSuffix, "__replacement02");
  const [first, second] = recovered.results;
  assert.equal(first.stopReason, "agent_finished");
  assert.deepEqual(first.executions?.map((execution) => execution.executionId), [
    `${assignmentId}__execution_01`,
    `${assignmentId}__execution_02`,
    `${assignmentId}__execution_03`,
  ]);
  assert.equal(second.repetition, 2);
  assert.equal(second.stopReason, "agent_finished");
});

test("run stops the queue on an exhausted Codex quota without a clean replacement", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-quota-stop-"));
  const papersDir = path.join(root, "papers");
  await mkdir(papersDir, { recursive: true });
  for (const name of ["01_a.pdf", "02_b.pdf", "03_c.pdf"]) {
    await writeFile(path.join(papersDir, name), "%PDF-1.4\n", "utf8");
  }
  const progress: string[] = [];
  const runner = new BenchmarkRunner(testBenchmarkConfig(root), {
    progress: (message) => progress.push(message),
  });
  let executionCalls = 0;
  (runner as any).processExecution = async (
    pdfPath: string,
    _mode: "morpheus_mcp",
    _benchmarkRunDir: string,
    repetition: number,
    execution: { executionId: string },
  ) => {
    executionCalls += 1;
    return testInfrastructureFailure(pdfPath, repetition, QUOTA_ERROR, {
      executionId: execution.executionId,
      replacementEligible: false,
    });
  };

  const summary = await runner.run();

  assert.equal(executionCalls, 1);
  assert.equal(summary.results.length, 1);
  assert.ok(progress.some((message) => /Codex usage quota is exhausted/.test(message)));
});

test("command-runner preflight stops retrying once the Codex quota is exhausted", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-quota-preflight-"));
  const codexHomeDir = path.join(root, "codex_home");
  await mkdir(codexHomeDir, { recursive: true });
  let startThreadCalls = 0;
  const codex = {
    startThread: () => {
      startThreadCalls += 1;
      return {
        runStreamed: async () => ({
          events: (async function* () {
            yield { type: "error", message: QUOTA_ERROR };
          })(),
        }),
      };
    },
  };

  const result = await (new BenchmarkRunner(testBenchmarkConfig(root)) as any).ensureCommandRunnerReady({
    codex,
    threadOptions: {},
    codexHomeDir,
    runDir: path.join(root, "run"),
  });

  assert.equal(startThreadCalls, 1);
  assert.deepEqual(result, {
    ok: false,
    error: `Command-runner preflight failed after 1 attempt: ${QUOTA_ERROR}`,
  });
});

test("recoverRun launches remaining jobs in repetition-major order", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-v2-recovery-order-"));
  const config = testBenchmarkConfig(root, { benchmarkModes: ["python_web", "morpheus_mcp"], benchmarkRepetitions: 2 });
  const papers = ["a.pdf", "b.pdf"].map((name) => path.join(root, "papers", name));
  await mkdir(path.join(root, "papers"), { recursive: true });
  // Recorded in the old paper-major order.
  const jobs = papers.flatMap((pdfPath) => (["python_web", "morpheus_mcp"] as const).flatMap((mode) =>
    [1, 2].map((repetition) => ({ pdfPath, mode, repetition }))
  ));
  await writeFile(path.join(root, "benchmark_recovery.json"), JSON.stringify({
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    benchmarkVersion: BENCHMARK_VERSION,
    benchmarkId: "order-benchmark",
    benchmarkRunDir: root,
    startedAt: "2026-10-08T00:00:00.000Z",
    config,
    jobs,
  }), "utf8");
  const started: string[] = [];
  const runner = new BenchmarkRunner(config);
  (runner as any).processPaper = async (pdfPath: string, mode: "morpheus_mcp", _dir: string, repetition: number) => {
    started.push(`${path.basename(pdfPath)}:${mode}:${repetition}`);
    return {
      ...testInfrastructureFailure(pdfPath, repetition, ""),
      mode,
      assignmentId: `${path.basename(pdfPath, ".pdf")}__${mode}__rep0${repetition}`,
      stopReason: "agent_finished",
      error: undefined,
    } as PaperRunResult;
  };

  await runner.recoverRun(root);

  assert.deepEqual(started, [
    "a.pdf:python_web:1", "a.pdf:morpheus_mcp:1", "b.pdf:python_web:1", "b.pdf:morpheus_mcp:1",
    "a.pdf:python_web:2", "a.pdf:morpheus_mcp:2", "b.pdf:python_web:2", "b.pdf:morpheus_mcp:2",
  ]);
});

test("run stops starting jobs when the quota guard cannot cover another one", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-quota-guard-run-"));
  const papersDir = path.join(root, "papers");
  await mkdir(papersDir, { recursive: true });
  for (const name of ["01_a.pdf", "02_b.pdf", "03_c.pdf"]) {
    await writeFile(path.join(papersDir, name), "%PDF-1.4\n", "utf8");
  }
  const progress: string[] = [];
  const runner = new BenchmarkRunner(testBenchmarkConfig(root, { codexQuotaJobCostPercent: 10 }), {
    progress: (message) => progress.push(message),
  });
  let executions = 0;
  (runner as any).processExecution = async (pdfPath: string, _mode: string, benchmarkRunDir: string, repetition: number) => {
    executions += 1;
    // The job's Codex session reports a nearly exhausted weekly quota.
    const sessions = path.join(benchmarkRunDir, `job_${executions}`, "codex_home", "sessions");
    await mkdir(sessions, { recursive: true });
    await writeFile(path.join(sessions, "rollout-test.jsonl"), `${quotaEvent(new Date().toISOString(), 95)}\n`, "utf8");
    return { ...testInfrastructureFailure(pdfPath, repetition, ""), stopReason: "agent_finished", error: undefined };
  };

  const summary = await runner.run();

  assert.equal(executions, 1);
  assert.equal(summary.results.length, 1);
  assert.ok(progress.some((message) => /quota guard: not starting another job; weekly quota is at 95\.0%/.test(message)));
  assert.ok(progress.some((message) => /remaining Codex quota cannot cover another job/.test(message)));
});

function quotaEvent(timestamp: string, usedPercent: number, limitId = "codex"): string {
  return JSON.stringify({
    timestamp,
    type: "event_msg",
    payload: {
      type: "token_count",
      rate_limits: {
        limit_id: limitId,
        primary: { used_percent: usedPercent, window_minutes: 10080, resets_at: 1791963035 },
        secondary: null,
      },
    },
  });
}
