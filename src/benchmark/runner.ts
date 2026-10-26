import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { setTimeout as sleep } from "node:timers/promises";

import { Codex, type Thread, type ThreadEvent, type ThreadItem, type ThreadOptions, type UserInput } from "@openai/codex-sdk";

import {
  installBenchmarkCodexExecRulesIsolation,
  type BenchmarkSubjectBudget,
} from "./codex-exec.js";
import {
  CAPABILITY_VIOLATION_MESSAGES,
  codexServiceFailureKind,
  collectCapabilityViolations,
  collectInfrastructureFailures,
  hasSuccessfulCommandExecution,
  isCodexQuotaExhaustedFailure,
  isUnrecoverableCommandRunnerPreflightError,
  isSystemicCommandRunnerInfrastructureFailure,
  normalizeCommandRunnerPreflightError,
  shouldTimeCommandAsMorpheusSimulation,
} from "./guardrails.js";
import {
  buildBenchmarkPrompt,
  parseAgentRunResponse,
} from "./prompt.js";
import { loadPaperFocus } from "./focus.js";
import { BENCHMARK_MODE_DEFINITIONS } from "./modes.js";
import { PaperArtifactCache } from "./paper-artifacts.js";
import { PythonBridge } from "./python-bridge.js";
import { benchmarkCodexSessionRoots, CodexQuotaGuard, readLatestCodexQuota } from "./quota.js";
import {
  resolveBenchmarkPythonExecutable,
  resolveBenchmarkPythonRuntimeReadPaths,
  resolveSystemPythonDenyPaths,
} from "./python-env.js";
import { buildCodexConfig } from "./codex-config.js";
import { appendProgressLog } from "./progress-log.js";
import {
  assertProvenanceAllowsSubjectExecution,
  collectBenchmarkProvenance,
  describeSoftwareDifferences,
  resolveBenchmarkVersion,
  skillSha256ByName,
} from "./provenance.js";
import {
  average,
  buildBenchmarkComparison,
  buildBenchmarkManifest,
  buildPaperModeStatistics,
  cloneBenchmarkDiagnostics,
  countV2Outcomes,
  emptyBenchmarkDiagnostics,
  formatComparisonCsv,
  formatPaperRunProgress,
  formatScore,
  maxObservedRepetition,
  mergeBenchmarkDiagnostics,
  mergeTurnDiagnostics,
  modelRefinementCountValue,
  repetitionValue,
  resultRepetition,
  summarizeModelRefinements,
} from "./summary.js";
import type {
  AgentRunResponse,
  AttemptArtifactAudit,
  BenchmarkConfig,
  BenchmarkDiagnostics,
  BenchmarkModeId,
  BenchmarkProvenance,
  BenchmarkSummary,
  PaperRunResult,
  ToolResult,
} from "./types.js";
import {
  collectCommandRunnerPreflightTurn,
  collectSubjectTurn,
  readCodexSessionTokenUsage,
  transcriptEventsForTurnError,
  type CollectedTurn,
} from "./turns.js";
import {
  applyMorpheusThreadEnv,
  buildAgentWorkspaceSnapshotDir,
  buildAgentWorkspaceStageFiles,
  buildBenchmarkAgentWorkspaceDir,
  buildBenchmarkCodexEnv,
  buildBenchmarkCodexHomeDir,
  buildBenchmarkThreadOptions,
  cleanupBenchmarkTempRunDirs,
  getBenchmarkSkillPathsForMode,
  prepareBenchmarkCodexHome,
  snapshotAgentWorkspace,
  snapshotBenchmarkCodexHome,
  stageBenchmarkAgentWorkspace,
  stageBenchmarkCommands,
  type StagedBenchmarkCommands,
  syncAgentModelXml,
} from "./workspace.js";

export {
  buildBenchmarkCodexExecArgs,
  buildCodexExecProcessTreeCleanupPlan,
  normalizeBenchmarkCodexExecStdoutLine,
} from "./codex-exec.js";

export type {
  BenchmarkCodexExecArgs,
  CodexExecProcessTreeCleanupPlan,
} from "./codex-exec.js";

export {
  buildBenchmarkSkillConfigEntries,
  buildCodexConfig,
  buildMorpheusMcpServerConfig,
} from "./codex-config.js";

export {
  codexServiceFailureKind,
  collectCapabilityViolations,
  collectInfrastructureFailures,
  hasSuccessfulCommandExecution,
  isCodexQuotaExhaustedFailure,
  isSystemicCommandRunnerInfrastructureFailure,
  shouldTimeCommandAsMorpheusSimulation,
} from "./guardrails.js";

export {
  buildBenchmarkComparison,
  buildPaperModeStatistics,
  emptyBenchmarkDiagnostics,
  formatComparisonCsv,
  mergeTurnDiagnostics,
} from "./summary.js";

export {
  buildCommandRunnerPreflightPrompt,
  transcriptEventsForTurnError,
} from "./turns.js";

export {
  buildAgentWorkspaceSnapshotDir,
  buildAgentWorkspaceStageFiles,
  buildBenchmarkAgentWorkspaceDir,
  buildBenchmarkCodexEnv,
  buildBenchmarkCodexHomeConfig,
  buildBenchmarkCodexHomeDir,
  buildBenchmarkThreadOptions,
  buildCodexHomeSnapshotDir,
  cleanupBenchmarkTempRunDirs,
  prepareBenchmarkCodexHome,
  snapshotBenchmarkCodexHome,
} from "./workspace.js";

type CreateRunResult = ToolResult<{
  run_id: string;
  run_dir: string;
  run_manifest_path: string;
}>;

type ExtractPaperResult = ToolResult<{
  run_id: string;
  run_dir: string;
  text_path: string;
}>;

type VisualManifestResult = ToolResult<{
  figure_pages: number[];
  table_pages: number[];
  visual_pages: number[];
  items?: Array<{
    kind: string;
    label: string;
    page: number;
    caption_snippet?: string;
    detection_method?: string;
    confidence?: string;
  }>;
  detection_method?: string;
  warnings?: string[];
  item_count?: number;
  manifest_path: string;
}>;

export type TechnicalResult = ToolResult<{
  total_score: number;
  max_possible_score?: number;
  evaluation_json_path: string;
  attempt_id?: string;
  attempt_dir?: string;
  attempt_count?: number;
  warnings?: string[];
  breakdown?: {
    model_graph_matches_xml?: boolean;
    latest_primary_plot_within_last_time?: boolean;
    latest_logger_plot_within_last_time?: boolean;
    latest_primary_plot?: string | null;
    latest_logger_plot?: string | null;
    last_time_value?: number | null;
  };
}>;

type CaptureModelVersionResult = ToolResult<{
  model_present: boolean;
  snapshot_created: boolean;
  version_path?: string;
  xml_version_count?: number;
  run_manifest_path?: string;
}>;

type RunMorpheusResult = ToolResult<{
  attempt_id?: string;
  attempt_dir?: string;
  returncode?: number;
  timed_out?: boolean;
  stdout_path?: string;
  stderr_path?: string;
}>;

type CommandRunnerPreflightResult =
  | { ok: true }
  | { ok: false; error: string };

type BenchmarkRunOptions = {
  startAtPaper?: string;
};

export type BenchmarkRecoveryOptions = {
  rerunInfrastructureFailures?: boolean;
};

type BenchmarkJob = {
  pdfPath: string;
  mode: BenchmarkModeId;
  repetition: number;
};

export type BenchmarkProgressReporter = (message: string) => void;

type BenchmarkRunnerOptions = {
  progress?: BenchmarkProgressReporter;
};

const COMMAND_RUNNER_PREFLIGHT_MAX_ATTEMPTS = 3;
const COMMAND_RUNNER_PREFLIGHT_RETRY_DELAY_MS = 5_000;
/* node:coverage enable */

export function buildBenchmarkRunPaths(resultsDir: string, startedAt: Date = new Date()) {
  const benchmarkId = `${formatTimestamp(startedAt)}_benchmark`;
  const benchmarkRunDir = path.join(resultsDir, benchmarkId);
  return {
    benchmarkId,
    benchmarkRunDir,
    summaryPath: path.join(benchmarkRunDir, "benchmark_summary.json"),
    manifestPath: path.join(benchmarkRunDir, "benchmark_manifest.json"),
    comparisonJsonPath: path.join(benchmarkRunDir, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(benchmarkRunDir, "benchmark_comparison.csv"),
  };
}

/* node:coverage disable */
export class BenchmarkRunner {
  private readonly bridge: PythonBridge;
  private readonly paperArtifactCache: PaperArtifactCache;
  private readonly config: BenchmarkConfig;
  private readonly progress?: BenchmarkProgressReporter;
  private progressLogPath: string | null = null;
  private pythonSandboxPaths: { runtimeReadPaths: string[]; systemDenyPaths: string[] } | null = null;

  constructor(config: BenchmarkConfig, options: BenchmarkRunnerOptions = {}) {
    this.config = config;
    this.progress = options.progress;
    this.bridge = new PythonBridge({ timeoutMs: config.bridgeToolTimeoutMs });
    this.paperArtifactCache = new PaperArtifactCache(this.bridge);
  }

  // Validates the uv-built .venv once and caches which interpreters the subject sandbox may read or must deny.
  private resolvePythonSandboxPaths(): { runtimeReadPaths: string[]; systemDenyPaths: string[] } {
    if (!this.pythonSandboxPaths) {
      const runtimeReadPaths = resolveBenchmarkPythonRuntimeReadPaths();
      const systemDenyPaths = resolveSystemPythonDenyPaths({
        searchPath: process.env.PATH ?? "",
        allowedRoots: [path.resolve(".venv"), ...runtimeReadPaths],
      });
      this.pythonSandboxPaths = { runtimeReadPaths, systemDenyPaths };
    }
    return this.pythonSandboxPaths;
  }

  private async assertSubjectExecutionAllowed(
    recorded: Pick<BenchmarkSummary, "benchmarkVersion" | "benchmarkProtocol" | "benchmarkProvenance">,
  ): Promise<void> {
    const current = await collectBenchmarkProvenance(this.config);
    assertProvenanceAllowsSubjectExecution(recorded, current);
    const differences = describeSoftwareDifferences(recorded.benchmarkProvenance?.software, current.software);
    if (differences.length > 0) {
      this.reportProgress(`Warning: recovery executions use different software than the run (${differences.join("; ")}).`);
    }
  }

  private reportProgress(message: string): void {
    const formatted = `[benchmark ${formatLocalTimestamp(new Date(), "-")}] ${message}`;
    this.progress?.(formatted);
    if (this.progressLogPath) {
      appendProgressLog(this.progressLogPath, formatted);
    }
  }

  private createCodex(
    runsRoot: string,
    mode: BenchmarkModeId,
    activeRunId?: string,
    codexHomeDir?: string,
    agentWorkspaceDir?: string,
    budget?: BenchmarkSubjectBudget,
    stagedCommands?: StagedBenchmarkCommands,
  ): Codex {
    const codex = new Codex({
      config: buildCodexConfig(
        { ...this.config, resultsDir: runsRoot },
        mode,
        activeRunId,
        agentWorkspaceDir,
        codexHomeDir,
        budget?.deadlinePath,
        stagedCommands?.realMorpheusBin ?? undefined,
      ),
      env: buildBenchmarkCodexEnv(
        process.env,
        mode,
        codexHomeDir,
        undefined,
        this.config.codexAllowedEnvVars,
        this.config.morpheusNumThreads,
        budget?.deadlinePath,
        stagedCommands,
      ),
    });
    installBenchmarkCodexExecRulesIsolation(codex, budget);
    return codex;
  }

  private async ensureCommandRunnerReady(params: {
    codex: Codex;
    threadOptions: ThreadOptions;
    codexHomeDir: string;
    runDir: string;
  }): Promise<CommandRunnerPreflightResult> {
    let lastError = "Command-runner preflight did not complete.";
    let attempts = 0;

    for (let attempt = 1; attempt <= COMMAND_RUNNER_PREFLIGHT_MAX_ATTEMPTS; attempt += 1) {
      attempts = attempt;
      const thread = params.codex.startThread(params.threadOptions);
      const turn = await collectCommandRunnerPreflightTurn(thread);
      const transcriptEvents =
        turn.events.length > 0 || !turn.error
          ? turn.events
          : [{ type: "error", message: turn.error } as ThreadEvent];
      await writeTranscript(
        path.join(
          params.runDir,
          "transcripts",
          `preflight_command_runner_${String(attempt).padStart(2, "0")}.jsonl`,
        ),
        transcriptEvents,
      );
      await snapshotBenchmarkCodexHome(params.codexHomeDir, params.runDir);

      if (hasSuccessfulCommandExecution(turn.items)) {
        return { ok: true };
      }

      const infrastructureFailures = collectInfrastructureFailures(turn.items);
      lastError = normalizeCommandRunnerPreflightError(
        turn.error ??
        (infrastructureFailures.length > 0
          ? infrastructureFailures.join(" ")
          : "Command-runner preflight completed without a successful shell command."),
      );

      if (
        isUnrecoverableCommandRunnerPreflightError(lastError) ||
        codexServiceFailureKind(lastError) === "quota_exhausted"
      ) {
        break;
      }

      if (attempt < COMMAND_RUNNER_PREFLIGHT_MAX_ATTEMPTS) {
        await sleep(COMMAND_RUNNER_PREFLIGHT_RETRY_DELAY_MS);
      }
    }

    return {
      ok: false,
      error: `Command-runner preflight failed after ${attempts} ${attempts === 1 ? "attempt" : "attempts"}: ${lastError}`,
    };
  }

  private createQuotaGuard(benchmarkRunDir: string): CodexQuotaGuard | null {
    if (this.config.codexQuotaJobCostPercent <= 0) {
      return null;
    }
    const since = new Date();
    const cache = new Map();
    const tempCodexHomeRoot = path.dirname(buildBenchmarkCodexHomeDir(path.join(benchmarkRunDir, "quota")));
    return new CodexQuotaGuard({
      initialJobCostPercent: this.config.codexQuotaJobCostPercent,
      readLatest: async () => readLatestCodexQuota(
        await benchmarkCodexSessionRoots(benchmarkRunDir, tempCodexHomeRoot),
        since,
        cache,
      ),
      report: (message) => this.reportProgress(message),
    });
  }

  /** Returns why the remaining queue should not start, reporting it, or null to keep going. */
  private queueStopReason(result: PaperRunResult, queueLabel: string): string | null {
    if (isSystemicCommandRunnerInfrastructureFailure(result)) {
      this.reportProgress(`Stopping ${queueLabel} after systemic command-runner infrastructure failure: ${result.summary}`);
      return result.summary;
    }
    if (isCodexQuotaExhaustedFailure(result)) {
      this.reportProgress(
        `Stopping ${queueLabel} because the Codex usage quota is exhausted: ${result.error ?? result.summary} `
        + "Rerun with --recover-run once the quota resets; quota failures do not use up an assignment's clean replacement.",
      );
      return result.error ?? result.summary;
    }
    return null;
  }

  private captureCanonicalModelVersion(runId: string, reason: string): Promise<CaptureModelVersionResult> {
    return this.bridge.invoke("capture_model_xml_version", {
      run_id: runId,
      reason,
    }) as Promise<CaptureModelVersionResult>;
  }

  async run(maxPapers?: number, options: BenchmarkRunOptions = {}): Promise<BenchmarkSummary> {
    this.resolvePythonSandboxPaths();
    const startedAt = new Date();
    const benchmarkPaths = buildBenchmarkRunPaths(this.config.resultsDir, startedAt);
    const diagnostics = emptyBenchmarkDiagnostics();
    await mkdir(benchmarkPaths.benchmarkRunDir, { recursive: true });
    this.progressLogPath = path.join(benchmarkPaths.benchmarkRunDir, "benchmark.log");
    process.env.MORPHEUS_RUNS_DIR = benchmarkPaths.benchmarkRunDir;
    process.env.MORPHEUS_RUN_TIMEOUT_MS = String(this.config.morpheusRunTimeoutMs);
    process.env.MORPHEUS_XML_SCHEMA_PATH = this.config.morpheusXmlSchemaPath;
    applyMorpheusThreadEnv(process.env, this.config.morpheusNumThreads);

    const papers = await this.discoverPapers(maxPapers, options.startAtPaper);
    const jobs = expandBenchmarkJobs(papers, this.config.benchmarkModes, this.config.benchmarkRepetitions);
    const maxConcurrentJobs = resolveBenchmarkMaxConcurrentJobs(
      this.config.maxConcurrentJobs,
      process.platform,
    );
    if (maxConcurrentJobs < this.config.maxConcurrentJobs) {
      this.reportProgress(
        `Native Windows supports serial benchmark execution only; requested concurrency=${this.config.maxConcurrentJobs} was reduced to concurrency=${maxConcurrentJobs}. Use Linux or WSL2 for parallel jobs.`,
      );
    }
    const effectiveConfig = maxConcurrentJobs === this.config.maxConcurrentJobs
      ? this.config
      : { ...this.config, maxConcurrentJobs };
    const provenance = await collectBenchmarkProvenance(this.config);
    if (provenance.gitDirty) {
      this.reportProgress(
        `Warning: benchmark v${provenance.benchmarkVersion} is starting from a working tree with uncommitted changes; commit ${provenance.gitCommit ?? "unknown"} does not fully describe this run.`,
      );
    }
    if (provenance.software.npmInstalledMatchesLock === false) {
      this.reportProgress(
        `Warning: node_modules does not match package-lock.json (installed @openai/codex-sdk ${provenance.software.codexSdk ?? "unknown"}, locked ${provenance.software.codexSdkLocked ?? "unknown"}); run npm ci.`,
      );
    }
    if (provenance.software.pythonInstalledMatchesLock === false) {
      this.reportProgress("Warning: .venv does not match uv.lock; run uv sync --locked.");
    }
    await writeJson(path.join(benchmarkPaths.benchmarkRunDir, "benchmark_recovery.json"), {
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      benchmarkVersion: provenance.benchmarkVersion,
      benchmarkProvenance: provenance,
      benchmarkId: benchmarkPaths.benchmarkId,
      benchmarkRunDir: benchmarkPaths.benchmarkRunDir,
      startedAt: startedAt.toISOString(),
      config: effectiveConfig,
      jobs,
    });
    this.reportProgress(
      `Starting benchmark ${benchmarkPaths.benchmarkId}: ${jobs.length} paper/mode job(s), concurrency=${maxConcurrentJobs}.`,
    );
    let infrastructureAbortReason: string | null = null;
    const quotaGuard = this.createQuotaGuard(benchmarkPaths.benchmarkRunDir);
    const stopForQuota = () => {
      infrastructureAbortReason ??= "the remaining Codex quota cannot cover another job.";
    };
    const rawResults = await mapWithConcurrency(jobs, maxConcurrentJobs, quotaGuardedWorker(quotaGuard, stopForQuota, async (job, index) => {
      const jobStartedAt = new Date();
      const repetitionLabel = this.config.benchmarkRepetitions > 1 ? ` rep=${job.repetition}` : "";
      const jobLabel = `${path.basename(job.pdfPath)} [${job.mode}${repetitionLabel}]`;
      this.reportProgress(`Starting job ${index + 1}/${jobs.length}: ${jobLabel}.`);
      try {
        const result = await this.processPaper(
          job.pdfPath,
          job.mode,
          benchmarkPaths.benchmarkRunDir,
          job.repetition,
        );
        const reportedResult = await ensureFailureReproductionReport(await normalizePaperRunResult(result));
        await writeAssignmentRecoveryResult(benchmarkPaths.benchmarkRunDir, reportedResult);
        this.reportProgress(`Finished job ${index + 1}/${jobs.length}: ${formatPaperRunProgress(reportedResult)}.`);
        infrastructureAbortReason ??= this.queueStopReason(reportedResult, "queued jobs");
        return reportedResult;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        this.reportProgress(`Unhandled runner error in job ${index + 1}/${jobs.length}: ${message}`);
        const runInfo = await findLatestRunInfoForJob(
          benchmarkPaths.benchmarkRunDir,
          job.pdfPath,
          job.mode,
          job.repetition,
          this.config.benchmarkRepetitions,
        );
        const failed = failedResult(
          path.basename(job.pdfPath),
          job.pdfPath,
          job.mode,
          `Unhandled runner error: ${message}`,
          runInfo?.runId ?? "",
          runInfo?.runDir ?? "",
          runInfo?.runManifestPath ?? null,
          null,
          null,
          [],
          job.repetition,
        );
        const jobFinishedAt = new Date();
        const reportedResult = await ensureFailureReproductionReport(
          await normalizePaperRunResult({
            ...failed,
            startedAt: jobStartedAt.toISOString(),
            finishedAt: jobFinishedAt.toISOString(),
            durationMs: jobFinishedAt.getTime() - jobStartedAt.getTime(),
          }),
        );
        await writeAssignmentRecoveryResult(benchmarkPaths.benchmarkRunDir, reportedResult);
        this.reportProgress(`Failed job ${index + 1}/${jobs.length}: ${formatPaperRunProgress(reportedResult)}.`);
        infrastructureAbortReason ??= this.queueStopReason(reportedResult, "queued jobs");
        return reportedResult;
      }
    }), () => infrastructureAbortReason === null);
    if (infrastructureAbortReason) {
      this.reportProgress(`Benchmark stopped before launching all jobs: ${infrastructureAbortReason}`);
    }
    const results = await Promise.all(
      rawResults.filter((result): result is PaperRunResult => result !== null)
        .map((result) => normalizePaperRunResult(result)),
    );
    for (const result of results) {
      mergeBenchmarkDiagnostics(diagnostics, result.diagnostics);
    }

    const outcomeCounts = countV2Outcomes(results);
    const modelRefinementStats = summarizeModelRefinements(results);
    const summaryRepetitions = Math.max(this.config.benchmarkRepetitions, maxObservedRepetition(results));
    const paperModeStatistics = buildPaperModeStatistics(results, summaryRepetitions);
    const technicalScores = results.flatMap((result) =>
      result.technicalScore === null ? [] : [result.technicalScore],
    );
    const reproductionScores = results.flatMap((result) =>
      result.reproductionScore === null ? [] : [result.reproductionScore],
    );
    const finishedAt = new Date();
    const durationMs = finishedAt.getTime() - startedAt.getTime();

    const summary: BenchmarkSummary = {
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      benchmarkVersion: provenance.benchmarkVersion,
      benchmarkProvenance: provenance,
      config: effectiveConfig,
      benchmarkId: benchmarkPaths.benchmarkId,
      benchmarkRunDir: benchmarkPaths.benchmarkRunDir,
      comparisonJsonPath: benchmarkPaths.comparisonJsonPath,
      comparisonCsvPath: benchmarkPaths.comparisonCsvPath,
      startedAt: startedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      generatedAt: finishedAt.toISOString(),
      durationMs,
      diagnostics,
      ...benchmarkCardinality(results),
      benchmarkRepetitions: summaryRepetitions,
      ...outcomeCounts,
      totalModelRefinements: modelRefinementStats.total,
      averageModelRefinements: modelRefinementStats.average,
      averageTechnicalScore: average(technicalScores),
      averageTechnicalScoreValidOnly: average(technicalScores),
      averageTechnicalScoreItt: average(results.map((result) => result.technicalScore ?? 0)),
      averageReproductionScore: average(reproductionScores),
      averageReproductionScoreValidOnly: average(reproductionScores),
      averageReproductionScoreItt: average(results.map((result) => result.reproductionScore ?? 0)),
      paperModeStatistics,
      results,
    };

    const comparison = buildBenchmarkComparison(summary);
    await writeJson(benchmarkPaths.summaryPath, summary);
    await writeJson(benchmarkPaths.manifestPath, buildBenchmarkManifest(summary));
    await writeJson(benchmarkPaths.comparisonJsonPath, comparison);
    await writeText(benchmarkPaths.comparisonCsvPath, formatComparisonCsv(comparison));
    this.reportProgress(`Benchmark summary written to ${benchmarkPaths.summaryPath}.`);
    return summary;
  }

  async recoverRun(
    benchmarkRunDir: string,
    options: BenchmarkRecoveryOptions = {},
  ): Promise<BenchmarkSummary> {
    this.resolvePythonSandboxPaths();
    const v2RunDir = path.resolve(benchmarkRunDir);
    this.progressLogPath = path.join(v2RunDir, "benchmark.log");
    process.env.MORPHEUS_RUNS_DIR = v2RunDir;
    process.env.MORPHEUS_RUN_TIMEOUT_MS = String(this.config.morpheusRunTimeoutMs);
    process.env.MORPHEUS_XML_SCHEMA_PATH = this.config.morpheusXmlSchemaPath;
    applyMorpheusThreadEnv(process.env, this.config.morpheusNumThreads);
    const maxConcurrentJobs = resolveBenchmarkMaxConcurrentJobs(this.config.maxConcurrentJobs, process.platform);
    const effectiveConfig = maxConcurrentJobs === this.config.maxConcurrentJobs
      ? this.config
      : { ...this.config, maxConcurrentJobs };
    if (maxConcurrentJobs < this.config.maxConcurrentJobs) {
      this.reportProgress(
        `Native Windows uses serial recovery; requested concurrency=${this.config.maxConcurrentJobs} was reduced to concurrency=${maxConcurrentJobs}. Use Linux or WSL2 for parallel jobs.`,
      );
    }
    const recoveryLockPath = path.join(v2RunDir, ".benchmark-v2-recovery.lock");
    await acquireRecoveryLock(recoveryLockPath);
    try {
      const v2SummaryPath = path.join(v2RunDir, "benchmark_summary.json");
      let v2Summary: BenchmarkSummary | null = null;
      if (await fileExists(v2SummaryPath)) {
        const v2Value = await readJson(v2SummaryPath);
        if (!isRecord(v2Value) || v2Value.benchmarkProtocol !== "time_limit_v2" || v2Value.artifactSchemaVersion !== 2) {
          throw new Error(
            "Historical max_cycles_v1 runs are read-only; use the original release to execute or continue them.",
          );
        }
        v2Summary = v2Value as unknown as BenchmarkSummary;
      } else {
        const stateValue = await readJson(path.join(v2RunDir, "benchmark_recovery.json"));
        if (!isRecord(stateValue) || stateValue.benchmarkProtocol !== "time_limit_v2" || !Array.isArray(stateValue.jobs)) {
          throw new Error("No recoverable time_limit_v2 state was found in the benchmark directory.");
        }
        const jobs = stateValue.jobs.flatMap((value) => isBenchmarkJob(value) ? [value] : []);
        if (jobs.length !== stateValue.jobs.length) {
          throw new Error("The v2 recovery job list is malformed.");
        }
        const resultsByAssignment = await readAssignmentRecoveryResults(v2RunDir);
        const missingJobs = byRepetition(jobs).filter((job) => !resultsByAssignment.has(
          benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition),
        ));
        const recordedProvenance = recordedProvenanceFromState(stateValue);
        if (missingJobs.length > 0) {
          await this.assertSubjectExecutionAllowed(recordedProvenance);
        }
        let missingJobsAbortReason: string | null = null;
        const missingJobsQuotaGuard = missingJobs.length > 0 ? this.createQuotaGuard(v2RunDir) : null;
        const stopMissingJobsForQuota = () => {
          missingJobsAbortReason ??= "the remaining Codex quota cannot cover another job.";
        };
        await mapWithConcurrency(missingJobs, maxConcurrentJobs, quotaGuardedWorker(missingJobsQuotaGuard, stopMissingJobsForQuota, async (job) => {
          const assignmentId = benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition);
          const runInfo = await findLatestRunInfoForJob(
            v2RunDir,
            job.pdfPath,
            job.mode,
            job.repetition,
            this.config.benchmarkRepetitions,
          );
          const prior = runInfo && await fileExists(path.join(runInfo.runDir, "subject_deadline.json"))
            ? await buildAmbiguousRecoveryExecution(
                job,
                assignmentId,
                runInfo,
                this.config,
              )
            : null;
          const recoveredResult = await ensureFailureReproductionReport(
            await normalizePaperRunResult(
              await this.processPaper(job.pdfPath, job.mode, v2RunDir, job.repetition, prior),
            ),
          );
          await writeAssignmentRecoveryResult(v2RunDir, recoveredResult);
          resultsByAssignment.set(assignmentId, recoveredResult);
          missingJobsAbortReason ??= this.queueStopReason(recoveredResult, "missing recovery jobs");
        }), () => missingJobsAbortReason === null);
        const results = jobs.map((job) => resultsByAssignment.get(
          benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition),
        )).filter((value): value is PaperRunResult => value !== undefined);
        v2Summary = buildRecoveredV2Summary({
          benchmarkRunDir: v2RunDir,
          benchmarkId: stringValue(stateValue.benchmarkId) ?? path.basename(v2RunDir),
          startedAt: stringValue(stateValue.startedAt) ?? new Date().toISOString(),
          config: effectiveConfig,
          results,
          ...recordedProvenance,
        });
      }
      if (options.rerunInfrastructureFailures) {
        const stateValue = await readJson(path.join(v2RunDir, "benchmark_recovery.json"));
        if (!isRecord(stateValue) || stateValue.benchmarkProtocol !== "time_limit_v2" || !Array.isArray(stateValue.jobs)) {
          throw new Error("No recoverable time_limit_v2 state was found in the benchmark directory.");
        }
        const jobs = stateValue.jobs.flatMap((value) => isBenchmarkJob(value) ? [value] : []);
        if (jobs.length !== stateValue.jobs.length) {
          throw new Error("The v2 recovery job list is malformed.");
        }
        const resultsByAssignment = await readAssignmentRecoveryResults(v2RunDir);
        for (const result of v2Summary.results) {
          const assignmentId = result.assignmentId
            ?? benchmarkAssignmentId(result.pdfPath, result.mode, result.repetition);
          if (!resultsByAssignment.has(assignmentId)) {
            resultsByAssignment.set(assignmentId, result);
          }
        }
        // Jobs never launched because the queue stopped (systemic failure or exhausted quota) have no result yet.
        const retryJobs = byRepetition(jobs).filter((job) => {
          const prior = resultsByAssignment.get(benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition));
          return prior === undefined || canRerunInfrastructureFailure(prior);
        });
        const unlaunchedCount = retryJobs.filter((job) =>
          !resultsByAssignment.has(benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition))
        ).length;
        this.reportProgress(
          `Explicit recovery found ${retryJobs.length - unlaunchedCount} eligible infrastructure failure(s) to rerun`
          + ` and ${unlaunchedCount} never-launched assignment(s).`,
        );
        if (retryJobs.length > 0) {
          await this.assertSubjectExecutionAllowed(v2Summary);
        }
        let infrastructureAbortReason: string | null = null;
        const quotaGuard = retryJobs.length > 0 ? this.createQuotaGuard(v2RunDir) : null;
        const stopForQuota = () => {
          infrastructureAbortReason ??= "the remaining Codex quota cannot cover another job.";
        };
        await mapWithConcurrency(retryJobs, maxConcurrentJobs, quotaGuardedWorker(quotaGuard, stopForQuota, async (job, index) => {
          const assignmentId = benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition);
          const prior = resultsByAssignment.get(assignmentId) ?? null;
          this.reportProgress(
            `Starting recovery job ${index + 1}/${retryJobs.length}: ${path.basename(job.pdfPath)} [${job.mode} rep=${job.repetition}].`,
          );
          const recoveredResult = await ensureFailureReproductionReport(
            await normalizePaperRunResult(
              await this.processPaper(job.pdfPath, job.mode, v2RunDir, job.repetition, prior),
            ),
          );
          await writeAssignmentRecoveryResult(v2RunDir, recoveredResult);
          resultsByAssignment.set(assignmentId, recoveredResult);
          this.reportProgress(
            `Finished recovery job ${index + 1}/${retryJobs.length}: ${formatPaperRunProgress(recoveredResult)}.`,
          );
          infrastructureAbortReason ??= this.queueStopReason(recoveredResult, "queued recovery jobs");
          return recoveredResult;
        }), () => infrastructureAbortReason === null);
        if (infrastructureAbortReason) {
          this.reportProgress(`Recovery stopped before launching all jobs: ${infrastructureAbortReason}`);
        }
        const results = jobs.map((job) => resultsByAssignment.get(
          benchmarkAssignmentId(job.pdfPath, job.mode, job.repetition),
        )).filter((value): value is PaperRunResult => value !== undefined);
        v2Summary = buildRecoveredV2Summary({
          benchmarkRunDir: v2RunDir,
          benchmarkId: stringValue(stateValue.benchmarkId) ?? path.basename(v2RunDir),
          startedAt: stringValue(stateValue.startedAt) ?? v2Summary.startedAt,
          config: effectiveConfig,
          results,
          benchmarkVersion: v2Summary.benchmarkVersion,
          benchmarkProvenance: v2Summary.benchmarkProvenance,
        });
      }
      const v2Results = await Promise.all(
        v2Summary.results.map(async (result) => {
          const normalized = await normalizePaperRunResult(result);
          const audited = await reauditRecoveredCapabilityViolations(v2RunDir, normalized);
          const reported = await ensureFailureReproductionReport(audited);
          await writeAssignmentRecoveryResult(v2RunDir, reported);
          return reported;
        }),
      );
      const recoveredDiagnostics = emptyBenchmarkDiagnostics();
      for (const result of v2Results) {
        mergeBenchmarkDiagnostics(recoveredDiagnostics, result.diagnostics);
      }
      const recoveredV2 = {
        ...v2Summary,
        config: effectiveConfig,
        generatedAt: new Date().toISOString(),
        diagnostics: recoveredDiagnostics,
        paperModeStatistics: buildPaperModeStatistics(v2Results, v2Summary.benchmarkRepetitions),
        results: v2Results,
      };
      const v2Comparison = buildBenchmarkComparison(recoveredV2);
      await writeJson(v2SummaryPath, recoveredV2);
      await writeJson(path.join(v2RunDir, "benchmark_manifest.json"), buildBenchmarkManifest(recoveredV2));
      await writeJson(path.join(v2RunDir, "benchmark_comparison.json"), v2Comparison);
      await writeText(path.join(v2RunDir, "benchmark_comparison.csv"), formatComparisonCsv(v2Comparison));
      return recoveredV2;
    } finally {
      await rm(recoveryLockPath, { force: true });
    }
  }

  async combineRuns(benchmarkRunDirs: string[], outputDir = this.config.resultsDir): Promise<BenchmarkSummary> {
    if (benchmarkRunDirs.length < 2) {
      throw new Error("combineRuns requires at least two benchmark run directories.");
    }
    const outputRoot = path.resolve(outputDir);
    const sourceRunDirs = benchmarkRunDirs.map((runDir) => path.resolve(runDir));
    if (new Set(sourceRunDirs).size !== sourceRunDirs.length) {
      throw new Error("combineRuns received the same benchmark run directory more than once.");
    }
    this.progressLogPath = path.join(outputRoot, "benchmark.log");
    this.reportProgress(`Combining ${benchmarkRunDirs.length} benchmark runs into ${outputRoot}.`);

    const summaries = await Promise.all(
      sourceRunDirs.map(async (runDir) => {
        const summaryPath = path.join(runDir, "benchmark_summary.json");
        const summary = (await readJson(summaryPath)) as BenchmarkSummary;
        if (!Array.isArray(summary.results)) {
          throw new Error(`Could not read benchmark summary results from ${summaryPath}`);
        }
        return summary;
      }),
    );
    const cohortKey = (summary: BenchmarkSummary) => JSON.stringify({
      artifactSchemaVersion: summary.artifactSchemaVersion,
      benchmarkProtocol: summary.benchmarkProtocol,
      benchmarkVersion: resolveBenchmarkVersion(summary),
      skills: skillSha256ByName(summary.benchmarkProvenance),
      prompts: summary.benchmarkProvenance?.prompts ?? null,
      totalTimeLimitMs: summary.config.totalTimeLimitMs,
      finalizationReserveMs: summary.config.finalizationReserveMs,
      model: summary.config.model,
      reasoningEffort: summary.config.reasoningEffort,
      biologicalScoringModel: summary.config.biologicalScoringModel,
      biologicalScoringReasoningEffort: summary.config.biologicalScoringReasoningEffort,
      biologicalScorerVersion: summary.biologicalScorerVersion ?? null,
      maxConcurrentJobs: summary.config.maxConcurrentJobs,
      morpheusNumThreads: summary.config.morpheusNumThreads,
    });
    const expectedCohortKey = cohortKey(summaries[0]);
    const incompatible = summaries.find((summary) => cohortKey(summary) !== expectedCohortKey);
    if (incompatible) {
      throw new Error(
        `Cannot combine mixed benchmark cohorts. Expected ${expectedCohortKey}; received ${cohortKey(incompatible)}. Analyze these runs as separate strata.`,
      );
    }

    for (const source of summaries.slice(1)) {
      const differences = describeSoftwareDifferences(
        summaries[0].benchmarkProvenance?.software,
        source.benchmarkProvenance?.software,
      );
      if (differences.length > 0) {
        this.reportProgress(`Warning: ${source.benchmarkId} ran with different software (${differences.join("; ")}).`);
      }
    }
    const results = combinePaperRunResults(await Promise.all(summaries.map(async (summary, index) => ({
      sourceBenchmarkRunDir: sourceRunDirs[index],
      results: await Promise.all(summary.results.map((result) => normalizePaperRunResult(result))),
    }))));
    const renumberedCount = results.filter((result) => result.repetition !== result.sourceRepetition).length;
    if (renumberedCount > 0) {
      this.reportProgress(
        `Appended ${renumberedCount} result(s) whose paper/mode repetitions overlapped an earlier run as additional repetitions.`,
      );
    }

    const diagnostics = emptyBenchmarkDiagnostics();
    for (const result of results) {
      mergeBenchmarkDiagnostics(diagnostics, result.diagnostics);
    }
    const outcomeCounts = countV2Outcomes(results);
    const modelRefinementStats = summarizeModelRefinements(results);
    const technicalScores = results.flatMap((result) =>
      result.technicalScore === null ? [] : [result.technicalScore],
    );
    const reproductionScores = results.flatMap((result) =>
      result.reproductionScore === null ? [] : [result.reproductionScore],
    );
    const startedAt = earliestIsoString(summaries.map((summary) => summary.startedAt)) ?? new Date().toISOString();
    const finishedAt =
      latestIsoString(summaries.map((summary) => summary.finishedAt)) ?? new Date().toISOString();
    const generatedAt = new Date().toISOString();
    const modes = recoverBenchmarkModes(results);
    const summaryRepetitions = Math.max(
      maxObservedRepetition(results),
      ...summaries.map((summary) => summary.config.benchmarkRepetitions ?? 1),
    );
    // The cohort check guarantees the source runs agree; describe them, not the combining CLI invocation.
    const summaryConfig = {
      ...this.config,
      ...summaries[0].config,
      benchmarkModes: modes,
      benchmarkRepetitions: summaryRepetitions,
    };
    const paperModeStatistics = buildPaperModeStatistics(results, summaryRepetitions);
    const summary: BenchmarkSummary = {
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      ...(summaries[0].benchmarkVersion === undefined ? {} : { benchmarkVersion: summaries[0].benchmarkVersion }),
      ...(summaries[0].benchmarkProvenance === undefined
        ? {}
        : { benchmarkProvenance: combineBenchmarkProvenance(summaries.map((source) => source.benchmarkProvenance!)) }),
      ...(summaries[0].biologicalScorerVersion === undefined
        ? {}
        : { biologicalScorerVersion: summaries[0].biologicalScorerVersion }),
      config: summaryConfig,
      benchmarkId: path.basename(outputRoot),
      benchmarkRunDir: outputRoot,
      comparisonJsonPath: path.join(outputRoot, "benchmark_comparison.json"),
      comparisonCsvPath: path.join(outputRoot, "benchmark_comparison.csv"),
      startedAt,
      finishedAt,
      generatedAt,
      durationMs: durationBetweenIsoStrings(startedAt, finishedAt) ?? 0,
      diagnostics,
      ...benchmarkCardinality(results),
      benchmarkRepetitions: summaryRepetitions,
      ...outcomeCounts,
      totalModelRefinements: modelRefinementStats.total,
      averageModelRefinements: modelRefinementStats.average,
      averageTechnicalScore: average(technicalScores),
      averageTechnicalScoreValidOnly: average(technicalScores),
      averageTechnicalScoreItt: average(results.map((result) => result.technicalScore ?? 0)),
      averageReproductionScore: average(reproductionScores),
      averageReproductionScoreValidOnly: average(reproductionScores),
      averageReproductionScoreItt: average(results.map((result) => result.reproductionScore ?? 0)),
      paperModeStatistics,
      results,
    };

    const comparison = buildBenchmarkComparison(summary);
    await writeJson(path.join(outputRoot, "benchmark_summary.json"), summary);
    await writeJson(path.join(outputRoot, "benchmark_manifest.json"), buildBenchmarkManifest(summary));
    await writeJson(summary.comparisonJsonPath, comparison);
    await writeText(summary.comparisonCsvPath, formatComparisonCsv(comparison));
    this.reportProgress(`Combined benchmark summary written to ${path.join(outputRoot, "benchmark_summary.json")}.`);
    return summary;
  }

  async discoverPapers(maxPapers?: number, startAtPaper?: string): Promise<string[]> {
    const entries = await readdir(this.config.papersDir, { withFileTypes: true });
    let pdfs = entries
      .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".pdf"))
      .map((entry) => path.join(this.config.papersDir, entry.name))
      .sort();
    if (startAtPaper) {
      const startIndex = findStartPaperIndex(pdfs, startAtPaper);
      if (startIndex < 0) {
        throw new Error(`Could not find --start-at-paper target: ${startAtPaper}`);
      }
      pdfs = pdfs.slice(startIndex);
    }
    return typeof maxPapers === "number" ? pdfs.slice(0, maxPapers) : pdfs;
  }

  private async processPaper(
    pdfPath: string,
    mode: BenchmarkModeId,
    benchmarkRunDir: string,
    repetition = 1,
    priorInfrastructureExecution: PaperRunResult | null = null,
  ): Promise<PaperRunResult> {
    const assignmentId = `${sanitizeStem(path.basename(pdfPath, path.extname(pdfPath)))}__${mode}__rep${String(repetition).padStart(2, "0")}`;
    const toExecutionAudit = (execution: PaperRunResult): NonNullable<PaperRunResult["executions"]>[number] => ({
      executionId: execution.executionId ?? execution.runId,
      runId: execution.runId,
      replacementFor: execution.replacementFor ?? null,
      replacementCount: execution.replacementCount ?? 0,
      stopReason: execution.stopReason ?? "infrastructure_failure",
      workspaceDir: execution.workspaceDir ?? "",
      codexHomeDir: execution.codexHomeDir ?? "",
      model: execution.model ?? this.config.model,
      reasoningEffort: execution.reasoningEffort ?? this.config.reasoningEffort,
      totalTimeLimitMs: execution.totalTimeLimitMs ?? this.config.totalTimeLimitMs,
      finalizationReserveMs: execution.finalizationReserveMs ?? this.config.finalizationReserveMs,
      subjectExecutionMs: execution.subjectExecutionMs ?? 0,
      morpheusSimulationMs: execution.morpheusSimulationMs ?? 0,
      totalJobMs: execution.totalJobMs ?? execution.durationMs ?? 0,
      artifactStatus: execution.artifactStatus ?? "missing",
      startedAt: execution.startedAt ?? null,
      finishedAt: execution.finishedAt ?? null,
      error: execution.error ?? null,
    });
    // Quota failures can be rerun more than once, so earlier executions keep their full audit trail.
    const priorAudits = priorInfrastructureExecution
      ? priorInfrastructureExecution.executions?.length
        ? priorInfrastructureExecution.executions
        : [toExecutionAudit(priorInfrastructureExecution)]
      : [];
    const execute = async (replacement: {
      replacementFor: string | null;
      replacementCount: 0 | 1;
    }) => {
      const executionNumber = priorAudits.length > 0
        ? priorAudits.length + 1
        : replacement.replacementCount + 1;
      const executionId = `${assignmentId}__execution_${String(executionNumber).padStart(2, "0")}`;
      try {
        return await this.processExecution(pdfPath, mode, benchmarkRunDir, repetition, {
          assignmentId,
          executionId,
          replacementFor: replacement.replacementFor,
          replacementCount: replacement.replacementCount,
          runNameSuffix: executionNumber === 1 ? "" : `__replacement${String(executionNumber - 1).padStart(2, "0")}`,
        }) as PaperRunResult & {
          executionId: string;
          stopReason: "agent_finished" | "time_limit" | "infrastructure_failure";
        };
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        return {
          ...failedResult(
            path.basename(pdfPath),
            pdfPath,
            mode,
            `Infrastructure failure: ${message}`,
            "",
            "",
            null,
            null,
            null,
            [],
            repetition,
          ),
          artifactSchemaVersion: 2 as const,
          benchmarkProtocol: "time_limit_v2" as const,
          assignmentId,
          executionId,
          replacementFor: replacement.replacementFor,
          replacementCount: replacement.replacementCount,
          stopReason: "infrastructure_failure" as const,
          artifactStatus: "missing" as const,
          workspaceDir: "",
          codexHomeDir: "",
          model: this.config.model,
          reasoningEffort: this.config.reasoningEffort,
          totalTimeLimitMs: this.config.totalTimeLimitMs,
          finalizationReserveMs: this.config.finalizationReserveMs,
          subjectExecutionMs: 0,
        };
      }
    };
    let outcome: { selected: PaperRunResult; executions: PaperRunResult[] };
    if (priorInfrastructureExecution) {
      const selected = await execute({
        replacementFor: priorAudits[priorAudits.length - 1].executionId,
        replacementCount: 1,
      });
      outcome = { selected, executions: [selected] };
    } else {
      outcome = await runWithCleanInfrastructureReplacement(execute);
    }
    return {
      ...outcome.selected,
      assignmentId,
      selectedExecutionId: outcome.selected.executionId,
      executions: [...priorAudits, ...outcome.executions.map(toExecutionAudit)],
    };
  }

  private async processExecution(
    pdfPath: string,
    mode: BenchmarkModeId,
    benchmarkRunDir: string,
    repetition: number,
    execution?: {
      assignmentId: string;
      executionId: string;
      replacementFor: string | null;
      replacementCount: 0 | 1;
      runNameSuffix: string;
    },
  ): Promise<PaperRunResult> {
    const runStartedAt = new Date();
    const runDiagnostics = emptyBenchmarkDiagnostics();
    let activeAgentWorkspaceDir: string | null = null;
    let activeCodexHomeDir: string | null = null;
    let activeRunId = "";
    let activeRunDir = "";
    let activeRunManifestPath: string | null = null;
    let subjectStarted = false;
    let tempCleanupDone = false;
    const cleanupActiveTempRunDirs = async () => {
      if (tempCleanupDone) {
        return;
      }
      tempCleanupDone = true;
      const tempRunDirs = [activeAgentWorkspaceDir, activeCodexHomeDir].filter(
        (value): value is string => typeof value === "string" && value.length > 0,
      );
      if (tempRunDirs.length === 0) {
        return;
      }
      try {
        await cleanupBenchmarkTempRunDirs(tempRunDirs);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        this.reportProgress(`Run temporary workspace cleanup failed: ${message}`);
      }
    };
    const finalizeResult = (result: PaperRunResult): PaperRunResult => {
      const finishedAt = new Date();
      return {
        ...result,
        artifactSchemaVersion: 2,
        benchmarkProtocol: "time_limit_v2",
        assignmentId: execution?.assignmentId,
        executionId: execution?.executionId ?? result.runId,
        replacementFor: execution?.replacementFor ?? null,
        replacementCount: execution?.replacementCount ?? 0,
        stopReason: result.stopReason ?? (result.error ? "infrastructure_failure" : "agent_finished"),
        artifactStatus: result.artifactStatus ?? (result.technicalScore === null ? "unscoreable" : "scoreable"),
        workspaceDir: result.workspaceDir ?? (result.runManifestPath ? path.join(path.dirname(result.runManifestPath), "agent_workspace") : ""),
        codexHomeDir: result.codexHomeDir ?? (result.runManifestPath ? path.join(path.dirname(result.runManifestPath), "codex_home") : ""),
        model: this.config.model,
        reasoningEffort: this.config.reasoningEffort,
        totalTimeLimitMs: this.config.totalTimeLimitMs,
        finalizationReserveMs: this.config.finalizationReserveMs,
        repetition,
        startedAt: result.startedAt ?? runStartedAt.toISOString(),
        finishedAt: result.finishedAt ?? finishedAt.toISOString(),
        durationMs: result.durationMs || finishedAt.getTime() - runStartedAt.getTime(),
        reproductionScore: result.reproductionScore,
        technicalEvaluationPath: result.technicalEvaluationPath,
        diagnostics: cloneBenchmarkDiagnostics(runDiagnostics),
      };
    };
    const paper = path.basename(pdfPath);
    const benchmarkFocus = await loadPaperFocus(this.config.benchmarkFocusDir, pdfPath);
    try {
    const paperStem = sanitizeStem(path.basename(pdfPath, path.extname(pdfPath)));
    const modeDefinition = BENCHMARK_MODE_DEFINITIONS[mode];

    const runName = buildBenchmarkRunName(
      paperStem,
      mode,
      repetition,
      this.config.benchmarkRepetitions,
    ) + (execution?.runNameSuffix ?? "");
    const createRun = (await this.bridge.invoke<{
      run_id: string;
      run_dir: string;
      run_manifest_path: string;
    }>("create_run", { name: runName })) as CreateRunResult;
    if (!createRun.ok) {
      return finalizeResult(failedResult(
        paper,
        pdfPath,
        mode,
        `Failed to create run: ${createRun.error ?? "unknown error"}`,
        "",
        "",
        null,
        null,
        benchmarkFocus,
      ));
    }
    const runId = createRun.run_id;
    const runDir = createRun.run_dir;
    const runManifestPath = createRun.run_manifest_path;
    activeRunId = runId;
    activeRunDir = runDir;
    activeRunManifestPath = runManifestPath;
    await updateRunManifestMetadata(runManifestPath, {
      paper_pdf_path: pdfPath,
      mode,
      repetition,
      configured_repetitions: this.config.benchmarkRepetitions,
    });
    this.reportProgress(`Created run ${runId}: paper=${paper}, mode=${mode}.`);

    await mkdir(path.join(runDir, "transcripts"), { recursive: true });

    const paperArtifacts = await this.paperArtifactCache.prepareForRun({
      benchmarkRunDir,
      pdfPath,
      runId,
      runDir,
    });
    const extract = paperArtifacts.extract as ExtractPaperResult;
    const visualManifest = paperArtifacts.visualManifest as VisualManifestResult;
    if (!extract.ok) {
      return finalizeResult(failedResult(
        paper,
        pdfPath,
        mode,
        `Failed to extract paper text: ${extract.error ?? "unknown error"}`,
        runId,
        runDir,
        runManifestPath,
        null,
        benchmarkFocus,
      ));
    }

    if (!visualManifest.ok) {
      return finalizeResult(failedResult(
        paper,
        pdfPath,
        mode,
        `Failed to list PDF visuals: ${visualManifest.error ?? "unknown error"}`,
        runId,
        runDir,
        runManifestPath,
        null,
        benchmarkFocus,
      ));
    }
    await updateRunManifestMetadata(runManifestPath, {
      paper_text_path: extract.text_path,
      paper_visual_manifest_path: visualManifest.manifest_path,
      paper_visual_item_count: visualManifest.item_count,
      paper_visual_pages: visualManifest.visual_pages,
      paper_table_pages: visualManifest.table_pages,
      paper_figure_pages: visualManifest.figure_pages,
      paper_visual_warnings: visualManifest.warnings ?? [],
    });

    const agentWorkspaceDir = buildBenchmarkAgentWorkspaceDir(runDir);
    activeAgentWorkspaceDir = agentWorkspaceDir;
    const stagedAgentFiles = buildAgentWorkspaceStageFiles({
      agentWorkspaceDir,
      runDir,
      pdfPath,
      paperTextPath: extract.text_path,
      visualManifestPath: visualManifest.manifest_path,
      mode,
    });
    await mkdir(agentWorkspaceDir, { recursive: true });
    await stageBenchmarkAgentWorkspace(stagedAgentFiles);
    const codexHomeDir = buildBenchmarkCodexHomeDir(runDir);
    activeCodexHomeDir = codexHomeDir;
    const deadlinePath = path.join(runDir, "subject_deadline.json");
    const executionTimingPath = path.join(runDir, "subject_execution.json");
    const stagedCommands = await stageBenchmarkCommands({
      agentWorkspaceDir,
      trustedCommandDir: path.join(codexHomeDir, "benchmark-tools"),
      mode,
      realMorpheusBin: process.env.MORPHEUS_BIN ?? "morpheus",
      deadlinePath,
      morpheusRunTimeoutMs: this.config.morpheusRunTimeoutMs,
      pythonExecutable: resolveBenchmarkPythonExecutable(),
    });
    await prepareBenchmarkCodexHome(
      codexHomeDir,
      agentWorkspaceDir,
      getBenchmarkSkillPathsForMode(this.config, mode),
      this.config.codexAllowedEnvVars,
      {
        mode,
        benchmarkDeadlinePath: deadlinePath,
        realMorpheusBin: stagedCommands.realMorpheusBin,
        realMorpheusBinPaths: stagedCommands.realMorpheusBinPaths,
        pythonRuntimeReadPaths: this.resolvePythonSandboxPaths().runtimeReadPaths,
        systemPythonDenyPaths: this.resolvePythonSandboxPaths().systemDenyPaths,
      },
    );
    await snapshotBenchmarkCodexHome(codexHomeDir, runDir);
    const threadOptions: ThreadOptions = {
      ...buildBenchmarkThreadOptions(this.config, runDir, agentWorkspaceDir, mode),
    };
    const capabilityViolations = new Set<string>();

    if (shouldPreflightCommandRunner(mode)) {
      const preflightCodex = this.createCodex(
        benchmarkRunDir,
        mode,
        runId,
        codexHomeDir,
        agentWorkspaceDir,
        undefined,
        stagedCommands,
      );
      const preflight = await this.ensureCommandRunnerReady({
        codex: preflightCodex,
        threadOptions,
        codexHomeDir,
        runDir,
      });
      if (!preflight.ok) {
        await snapshotAgentWorkspace(agentWorkspaceDir, runDir);
        const preflightFailure = failedResult(
          paper,
          pdfPath,
          mode,
          `Infrastructure failure before subject turn: ${preflight.error}`,
          runId,
          runDir,
          runManifestPath,
          null,
          benchmarkFocus,
          [...capabilityViolations],
        );
        return finalizeResult({
          ...preflightFailure,
          // A systemic command-runner failure or an exhausted quota would fail the replacement identically.
          replacementEligible: !isSystemicCommandRunnerInfrastructureFailure(preflightFailure)
            && !isCodexQuotaExhaustedFailure(preflightFailure),
        });
      }
    }

    const subjectBudget: BenchmarkSubjectBudget = {
      totalTimeLimitMs: this.config.totalTimeLimitMs,
      finalizationReserveMs: this.config.finalizationReserveMs,
      morpheusRunTimeoutMs: this.config.morpheusRunTimeoutMs,
      deadlinePath,
      executionTimingPath,
    };
    const codex = this.createCodex(
      benchmarkRunDir,
      mode,
      runId,
      codexHomeDir,
      agentWorkspaceDir,
      subjectBudget,
      stagedCommands,
    );

    const prompt = buildBenchmarkPrompt({
      mode,
      paperName: paper,
      focusText: benchmarkFocus,
      runId,
      pageRenderDpi: this.config.pageRenderDpi,
      representativeOutputFrames: this.config.representativeOutputFrames,
      likelyFigurePages: visualManifest.visual_pages,
      totalTimeLimitMs: this.config.totalTimeLimitMs,
      finalizationReserveMs: this.config.finalizationReserveMs,
      morpheusRunTimeoutMs: this.config.morpheusRunTimeoutMs,
    });
    await writeText(path.join(runDir, "subject_prompt.txt"), prompt);
    this.reportProgress(`Run ${runId}: starting subject execution.`);
    subjectStarted = true;
    const subject = await runOneSubjectProcess({
      codex,
      threadOptions,
      input: [{ type: "text", text: prompt }],
      transcriptPath: path.join(runDir, "transcripts", "subject.jsonl"),
    });
    const { thread, turn } = subject;
    // Time-limited or killed subjects never emit turn.completed; recover usage from the session rollout.
    const turnUsage = turn.usage ?? await readCodexSessionTokenUsage(codexHomeDir, thread.id);
    mergeTurnDiagnostics(runDiagnostics, { ...turn, usage: turnUsage });
    await snapshotBenchmarkCodexHome(codexHomeDir, runDir);

    addCapabilityViolations(capabilityViolations, collectCapabilityViolations(turn.items, mode, runId));
    await syncAgentModelXml(agentWorkspaceDir, runDir);
    await snapshotAgentWorkspace(agentWorkspaceDir, runDir);
    await harvestAttemptModelXmlVersions(runDir);
    await this.captureCanonicalModelVersion(runId, "subject_execution");

    const timingValue = await readJson(executionTimingPath);
    const timing = isRecord(timingValue) ? timingValue : {};
    const deadlineValue = await readJson(deadlinePath);
    const deadline = isRecord(deadlineValue) ? deadlineValue : {};
    const subjectStopReason = stringValue(timing.stopReason) ?? (turn.error ? "infrastructure_failure" : "agent_finished");
    const infrastructureFailures = collectInfrastructureFailures(turn.items);
    const infrastructureError = subjectStopReason === "infrastructure_failure"
      ? turn.error ?? (infrastructureFailures.join(" ") || "Subject process failed.")
      : null;

    let finalResponse: AgentRunResponse | null = null;
    let responseError: string | null = null;
    if (turn.finalResponse.trim()) {
      try {
        finalResponse = parseAgentRunResponse(turn.finalResponse);
        if (finalResponse.runId !== runId) {
          throw new Error(`response runId ${finalResponse.runId} does not match ${runId}`);
        }
      } catch (error) {
        responseError = `Invalid final response: ${(error as Error).message}`;
      }
    } else if (subjectStopReason !== "time_limit") {
      responseError = "No final response was produced.";
    }

    await ensureCanonicalModelFromExecutionArtifacts({
      bridge: this.bridge,
      runDir,
      agentWorkspaceDir,
    });

    const technical = await this.runHostTechnicalEvaluation(mode, runId, runDir, runDiagnostics);
    await snapshotAgentWorkspace(agentWorkspaceDir, runDir);
    await harvestAttemptModelXmlVersions(runDir);
    const attemptArtifactAudit = await auditAgentMorpheusAttempts(runDir);
    runDiagnostics.attemptCount = attemptArtifactAudit.executedAttempts;
    const runFailed = Boolean(infrastructureError) || capabilityViolations.size > 0;
    const stopReason: NonNullable<PaperRunResult["stopReason"]> = subjectStopReason === "time_limit"
      ? "time_limit"
      : subjectStopReason === "infrastructure_failure"
        ? "infrastructure_failure"
        : "agent_finished";
    const artifactStatus: NonNullable<PaperRunResult["artifactStatus"]> = technical.ok
      ? "scoreable"
      : (await fileExists(path.join(runDir, "model.xml")) ? "unscoreable" : "missing");
    const technicalScore = technical.ok ? technical.total_score : null;
    const technicalPath = technical.ok ? technical.evaluation_json_path : null;
    const attemptCount = attemptArtifactAudit.executedAttempts;

    const reproductionScore = finalResponse?.reproduction?.total_score ?? null;
    const finishedAt = new Date();
    const durationMs = finishedAt.getTime() - runStartedAt.getTime();
    const resultDiagnostics = cloneBenchmarkDiagnostics(runDiagnostics);
    const modelRefinementCount = await readModelRefinementCount(runManifestPath);
    this.reportProgress(
      `Run ${runId}: subject stop=${subjectStopReason}, technical=${technical.ok ? formatScore(technicalScore, technical.max_possible_score ?? 7) : "failed"}, reproduction=${formatScore(reproductionScore, 8)}, modelRefinements=${modelRefinementCount}.`,
    );
    const reproductionPayload = {
      paper,
      pdfPath,
      mode,
      modeLabel: modeDefinition.label,
      capabilities: modeDefinition.capabilities,
      capabilityViolations: [...capabilityViolations],
      runId,
      repetition,
      benchmarkFocus,
      generatedAt: new Date().toISOString(),
      stopReason,
      artifactStatus,
      reproduction: finalResponse?.reproduction ?? null,
      summary: finalResponse?.summary ?? responseError ?? infrastructureError ?? "No final summary available.",
      technicalScore,
      technicalEvaluationPath: technicalPath ?? null,
      attempts: attemptCount,
      attemptArtifactAudit,
      modelRefinementCount,
      startedAt: runStartedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      durationMs,
      diagnostics: resultDiagnostics,
    };
    const primaryReportDir = technicalPath ? path.dirname(technicalPath) : runDir;
    const reportDirectories = uniquePaths([primaryReportDir, runDir]);
    for (const reportDir of reportDirectories) {
      await writeJson(path.join(reportDir, "reproduction_report.json"), reproductionPayload);
      await writeText(
        path.join(reportDir, "reproduction_report.txt"),
        formatReproductionReportText(reproductionPayload),
      );
    }
    const reproductionPath = path.join(primaryReportDir, "reproduction_report.json");
    const reproductionTextPath = path.join(primaryReportDir, "reproduction_report.txt");

    const result: PaperRunResult = {
      paper,
      pdfPath,
      mode,
      modeLabel: modeDefinition.label,
      capabilities: modeDefinition.capabilities,
      capabilityViolations: [...capabilityViolations],
      runId,
      threadId: thread.id,
      repetition,
      startedAt: runStartedAt.toISOString(),
      finishedAt: finishedAt.toISOString(),
      durationMs,
      diagnostics: resultDiagnostics,
      attempts: attemptCount,
      attemptArtifactAudit,
      modelRefinementCount,
      technicalScore,
      reproductionScore,
      technicalEvaluationPath: technicalPath ?? null,
      reproductionReportPath: reproductionPath,
      reproductionReportTextPath: reproductionTextPath,
      runManifestPath,
      benchmarkFocus,
      summary: finalResponse?.summary ?? responseError ?? infrastructureError ?? "No final summary available.",
      error: runFailed ? infrastructureError ?? [...capabilityViolations].join(" ") : undefined,
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      assignmentId: execution?.assignmentId,
      executionId: execution?.executionId ?? runId,
      replacementFor: execution?.replacementFor ?? null,
      replacementCount: execution?.replacementCount ?? 0,
      stopReason,
      artifactStatus,
      workspaceDir: path.join(runDir, "agent_workspace"),
      codexHomeDir: path.join(runDir, "codex_home"),
      model: this.config.model,
      reasoningEffort: this.config.reasoningEffort,
      totalTimeLimitMs: this.config.totalTimeLimitMs,
      finalizationReserveMs: this.config.finalizationReserveMs,
      subjectStartedAt: stringValue(timing.subjectStartedAt),
      subjectFinishedAt: stringValue(timing.subjectFinishedAt),
      softCutoffAt: stringValue(deadline.softCutoffAt),
      hardCutoffAt: stringValue(deadline.hardCutoffAt),
      subjectExecutionMs: numberValue(timing.subjectExecutionMs) ?? turn.durationMs,
      morpheusSimulationMs: runDiagnostics.morpheusSimulationTimeMs,
      totalJobMs: durationMs,
      budgetFraction: (numberValue(timing.subjectExecutionMs) ?? turn.durationMs) / this.config.totalTimeLimitMs,
      replacementEligible: stopReason === "infrastructure_failure"
        && codexServiceFailureKind(infrastructureError) !== "quota_exhausted",
    };
    return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      return finalizeResult({
        ...failedResult(
          paper,
          pdfPath,
          mode,
          `Infrastructure failure: ${message}`,
          activeRunId,
          activeRunDir,
          activeRunManifestPath,
          null,
          benchmarkFocus,
          [],
          repetition,
        ),
        // Before the subject starts nothing is lost by a clean replacement; afterwards a
        // host-side error must not discard (or re-roll) a subject execution.
        replacementEligible: !subjectStarted,
      });
    } finally {
      if (activeAgentWorkspaceDir && activeRunDir) {
        try {
          await snapshotAgentWorkspace(activeAgentWorkspaceDir, activeRunDir);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          this.reportProgress(`Run ${activeRunId || "unknown"}: final workspace snapshot failed: ${message}`);
        }
      }
      if (activeCodexHomeDir && activeRunDir) {
        try {
          await snapshotBenchmarkCodexHome(activeCodexHomeDir, activeRunDir);
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          this.reportProgress(`Run ${activeRunId || "unknown"}: final Codex-home snapshot failed: ${message}`);
        }
      }
      await cleanupActiveTempRunDirs();
    }
  }

  private async runHostTechnicalEvaluation(
    mode: BenchmarkModeId,
    runId: string,
    runDir: string,
    diagnostics: BenchmarkDiagnostics,
  ): Promise<TechnicalResult> {
    if (shouldRunHostMorpheusBeforeTechnicalEvaluation(mode)) {
      const xmlPath = await resolveHostTechnicalEvaluationXmlPath(runDir);
      const threads = await resolveHostTechnicalEvaluationThreads(
        runDir,
        xmlPath,
        this.config.morpheusNumThreads,
      );
      const hostRunStarted = Date.now();
      const run = (await this.bridge.invoke("run_morpheus_model", {
        run_id: runId,
        xml_path: xmlPath,
        timeout_ms: this.config.morpheusRunTimeoutMs,
        ...(threads === null ? {} : { threads }),
      })) as RunMorpheusResult;
      diagnostics.hostMorpheusRunTimeMs += Date.now() - hostRunStarted;
      if (!run.ok && !run.attempt_id) {
        return {
          ok: false,
          total_score: 0,
          evaluation_json_path: "",
          error: run.error ?? `Host Morpheus run failed before creating an attempt for ${xmlPath}.`,
        };
      }
    }

    const evaluationStarted = Date.now();
    const technical = (await this.bridge.invoke("evaluate_technical_run", {
      run_id: runId,
    })) as TechnicalResult;
    diagnostics.hostTechnicalEvaluationTimeMs += Date.now() - evaluationStarted;
    return technical;
  }
}
/* node:coverage enable */

/**
 * Merge results from several benchmark runs without dropping overlapping assignments.
 *
 * Results whose paper/mode repetition already exists in an earlier run are appended as
 * the next repetitions, so combining two single-repetition runs yields two repetitions.
 */
export function combinePaperRunResults(
  sources: Array<{ sourceBenchmarkRunDir: string; results: PaperRunResult[] }>,
): PaperRunResult[] {
  const highestRepetitionByPaperMode = new Map<string, number>();
  const combined: PaperRunResult[] = [];
  for (const source of sources) {
    const offsets = new Map(highestRepetitionByPaperMode);
    for (const result of source.results) {
      const paperModeKey = `${result.paper}__${result.mode}`;
      const sourceRepetition = resultRepetition(result);
      const repetition = (offsets.get(paperModeKey) ?? 0) + sourceRepetition;
      highestRepetitionByPaperMode.set(
        paperModeKey,
        Math.max(highestRepetitionByPaperMode.get(paperModeKey) ?? 0, repetition),
      );
      combined.push({
        ...result,
        repetition,
        sourceBenchmarkRunDir: source.sourceBenchmarkRunDir,
        sourceRepetition,
        ...(repetition === sourceRepetition
          ? {}
          : { assignmentId: benchmarkAssignmentId(result.pdfPath || result.paper, result.mode, repetition) }),
      });
    }
  }
  return combined;
}

export function shouldRunHostMorpheusBeforeTechnicalEvaluation(_mode: BenchmarkModeId): boolean {
  return true;
}

export async function resolveHostTechnicalEvaluationXmlPath(runDir: string): Promise<string> {
  const agentModelPath = path.join(buildAgentWorkspaceSnapshotDir(runDir), "model.xml");
  if (await fileExists(agentModelPath)) {
    return agentModelPath;
  }
  return path.join(runDir, "model.xml");
}

async function resolveHostTechnicalEvaluationThreads(
  runDir: string,
  xmlPath: string,
  configuredThreads: number | null,
): Promise<number | null> {
  const agentWorkspaceDir = buildAgentWorkspaceSnapshotDir(runDir);
  const manifestPath = path.join(agentWorkspaceDir, "run_manifest.json");
  if (!(await fileExists(manifestPath))) {
    return configuredThreads;
  }

  const manifest = await readJson(manifestPath);
  if (!isRecord(manifest) || !Array.isArray(manifest.attempt_history)) {
    return configuredThreads;
  }

  const canonicalXml = await readFile(xmlPath, "utf8");
  for (const attempt of [...manifest.attempt_history].reverse()) {
    if (
      !isRecord(attempt)
      || attempt.returncode !== 0
      || attempt.timed_out === true
    ) {
      continue;
    }
    const attemptId = stringValue(attempt.attempt_id);
    if (!attemptId) {
      continue;
    }
    const attemptXmlPath = path.join(agentWorkspaceDir, "attempts", attemptId, "model.xml");
    if (!(await fileExists(attemptXmlPath)) || await readFile(attemptXmlPath, "utf8") !== canonicalXml) {
      continue;
    }
    const threads = morpheusThreadsFromCommand(attempt.command);
    if (threads !== null) {
      return threads;
    }
  }
  return configuredThreads;
}

function morpheusThreadsFromCommand(command: unknown): number | null {
  if (!Array.isArray(command) || !command.every((part) => typeof part === "string")) {
    return null;
  }
  for (let index = 0; index < command.length; index += 1) {
    const part = command[index];
    const value = part === "--num-threads" || part === "-j"
      ? command[index + 1]
      : part.startsWith("--num-threads=")
        ? part.slice("--num-threads=".length)
        : null;
    if (value !== null && /^\d+$/.test(value)) {
      const threads = Number(value);
      return threads >= 1 ? threads : null;
    }
  }
  return null;
}

export function expandBenchmarkJobs(
  papers: string[],
  modes: BenchmarkModeId[],
  repetitions = 1,
): BenchmarkJob[] {
  const count = Math.max(1, Math.floor(nonNegativeNumber(repetitions)));
  // Repetition-major order: if the queue stops early (e.g. on quota), every paper and mode
  // still has the same number of completed repetitions.
  return Array.from({ length: count }, (_, index) => index + 1).flatMap((repetition) =>
    papers.flatMap((pdfPath) => modes.map((mode) => ({ pdfPath, mode, repetition }))),
  );
}

/** Stable repetition-major order for jobs recorded in any order. */
function byRepetition<T extends Pick<BenchmarkJob, "repetition">>(jobs: T[]): T[] {
  return jobs.map((job, index) => ({ job, index }))
    .sort((left, right) => left.job.repetition - right.job.repetition || left.index - right.index)
    .map(({ job }) => job);
}

/** Wraps a queue worker so each job first passes the quota guard; a refusal stops the queue. */
function quotaGuardedWorker<T, U>(
  guard: CodexQuotaGuard | null,
  stop: () => void,
  worker: (item: T, index: number) => Promise<U>,
): (item: T, index: number) => Promise<U | null> {
  return async (item, index) => {
    if (guard && !(await guard.admit())) {
      stop();
      return null;
    }
    try {
      return await worker(item, index);
    } finally {
      guard?.finish();
    }
  };
}

export async function findLatestRunInfoForJob(
  benchmarkRunDir: string,
  pdfPath: string,
  mode: BenchmarkModeId,
  repetition = 1,
  configuredRepetitions = 1,
): Promise<{ runId: string; runDir: string; runManifestPath: string } | null> {
  const paperStem = sanitizeStem(path.basename(pdfPath, path.extname(pdfPath))).toLowerCase();
  const suffix = buildBenchmarkRunName(
    paperStem,
    mode,
    repetition,
    configuredRepetitions,
  ).toLowerCase();
  let entries;
  try {
    entries = await readdir(benchmarkRunDir, { withFileTypes: true });
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return null;
    }
    throw error;
  }

  const candidates = entries
    .filter((entry) => entry.isDirectory() && entry.name.toLowerCase().endsWith(suffix))
    .map((entry) => entry.name)
    .sort()
    .reverse();

  for (const candidate of candidates) {
    const runDir = path.join(benchmarkRunDir, candidate);
    const runManifestPath = path.join(runDir, "run_manifest.json");
    const manifest = (await readJson(runManifestPath)) as Record<string, unknown>;
    if (typeof manifest.run_id === "string" && manifest.run_id.length > 0) {
      return {
        runId: manifest.run_id,
        runDir,
        runManifestPath,
      };
    }
  }

  return null;
}

function benchmarkJobKey(job: Pick<BenchmarkJob, "pdfPath" | "mode" | "repetition">): string {
  const paperStem = sanitizeStem(path.basename(job.pdfPath, path.extname(job.pdfPath))).toLowerCase();
  return `${paperStem}__${job.mode}__rep${Math.max(1, Math.floor(nonNegativeNumber(job.repetition)))}`;
}

function paperRunResultJobKey(result: Pick<PaperRunResult, "pdfPath" | "paper" | "mode" | "repetition">): string {
  const source = result.pdfPath || result.paper;
  return benchmarkJobKey({
    pdfPath: source,
    mode: result.mode,
    repetition: result.repetition,
  });
}

export function shouldPreflightCommandRunner(mode: BenchmarkModeId): boolean {
  const capabilities = BENCHMARK_MODE_DEFINITIONS[mode].capabilities;
  return capabilities.python || capabilities.morpheusCli;
}

export function resolveBenchmarkMaxConcurrentJobs(
  requestedConcurrency: number,
  platform: string = process.platform,
): number {
  const requested = Math.max(1, Math.floor(nonNegativeNumber(requestedConcurrency)));
  return platform === "win32" ? 1 : requested;
}

export async function mapWithConcurrency<T, U>(
  items: readonly T[],
  concurrency: number,
  worker: (item: T, index: number) => Promise<U>,
  shouldStart: () => boolean = () => true,
): Promise<U[]> {
  const limit = Math.max(1, Math.floor(concurrency));
  const results = new Array<U | undefined>(items.length);
  const completed = new Array<boolean>(items.length).fill(false);
  let nextIndex = 0;

  async function runNext(): Promise<void> {
    while (nextIndex < items.length) {
      if (!shouldStart()) {
        return;
      }
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await worker(items[index], index);
      completed[index] = true;
    }
  }

  const workers = Array.from({ length: Math.min(limit, items.length) }, () => runNext());
  await Promise.all(workers);
  return results.filter((_, index) => completed[index]) as U[];
}

function isFileNotFoundError(error: unknown): boolean {
  return error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT";
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    const info = await stat(filePath);
    return info.isFile() && info.size > 0;
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return false;
    }
    throw error;
  }
}

function sanitizeStem(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "_");
}

function buildBenchmarkRunName(
  paperStem: string,
  mode: BenchmarkModeId,
  repetition: number,
  configuredRepetitions: number,
): string {
  const baseName = `${paperStem}__${mode}`;
  if (configuredRepetitions <= 1 && repetition <= 1) {
    return baseName;
  }
  return `${baseName}__rep${String(repetition).padStart(2, "0")}`;
}

function formatTimestamp(date: Date): string {
  return formatLocalTimestamp(date, "");
}

function formatLocalTimestamp(date: Date, separator: "" | "-"): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  const dateParts = [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ];
  const timeParts = [
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ];
  if (separator === "-") {
    return `${dateParts.join("-")} ${timeParts.join(":")}`;
  }
  return [
    ...dateParts,
    "_",
    ...timeParts,
  ].join("");
}

function nonNegativeNumber(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.ceil(nonNegativeNumber(milliseconds) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (minutes > 0 || hours > 0) {
    parts.push(`${minutes}m`);
  }
  parts.push(`${seconds}s`);
  return parts.join(" ");
}

export function modelRefinementCountFromManifest(manifest: unknown): number {
  if (!isRecord(manifest)) {
    return 0;
  }
  const explicitCount = modelRefinementCountValue(manifest.xml_version_count);
  if (explicitCount !== null) {
    return explicitCount;
  }
  const capturedVersions = Array.isArray(manifest.host_captured_xml_versions)
    ? manifest.host_captured_xml_versions
    : [];
  let anonymousVersionCount = 0;
  const versionPaths = new Set<string>();
  for (const captured of capturedVersions) {
    if (!isRecord(captured)) {
      continue;
    }
    const versionPath = stringValue(captured.version_path);
    if (versionPath) {
      versionPaths.add(versionPath);
    } else {
      anonymousVersionCount += 1;
    }
  }
  return versionPaths.size + anonymousVersionCount;
}

export async function readModelRefinementCount(runManifestPath: string | null): Promise<number> {
  if (!runManifestPath) {
    return 0;
  }
  const runDir = path.dirname(runManifestPath);
  const manifestCount = modelRefinementCountFromManifest(await readJson(runManifestPath));
  const artifactCount = await countModelRefinementArtifacts(runDir);
  return Math.max(manifestCount, artifactCount);
}

export async function normalizePaperRunResult(result: PaperRunResult): Promise<PaperRunResult> {
  const existingCount = modelRefinementCountValue((result as { modelRefinementCount?: unknown }).modelRefinementCount) ?? 0;
  const manifestCount = await readModelRefinementCount(result.runManifestPath);
  return {
    ...result,
    repetition: resultRepetition(result),
    modelRefinementCount: Math.max(existingCount, manifestCount),
  };
}

export async function harvestAttemptModelXmlVersions(runDir: string): Promise<{
  harvestedCount: number;
  xmlVersionCount: number;
  versionPaths: string[];
}> {
  const versionDir = path.join(runDir, "xml_versions");
  await mkdir(versionDir, { recursive: true });

  const existingVersionFiles = await readXmlVersionFiles(versionDir);
  const knownXml = new Set<string>();
  let nextVersionIndex = 1;
  for (const versionFile of existingVersionFiles) {
    const match = path.basename(versionFile).match(/^model_v(\d+)\.xml$/i);
    if (match) {
      nextVersionIndex = Math.max(nextVersionIndex, Number(match[1]) + 1);
    }
    knownXml.add(await readFile(versionFile, "utf8"));
  }

  const harvested: Array<Record<string, unknown>> = [];
  const attemptModelPaths = await findAttemptModelXmlPaths(runDir);
  for (const attemptModelPath of attemptModelPaths) {
    const xml = await readFile(attemptModelPath, "utf8");
    if (knownXml.has(xml)) {
      continue;
    }
    const versionPath = path.join(versionDir, `model_v${String(nextVersionIndex).padStart(3, "0")}.xml`);
    nextVersionIndex += 1;
    await writeFile(versionPath, xml, "utf8");
    knownXml.add(xml);
    harvested.push({
      timestamp: new Date().toISOString(),
      source_path: attemptModelPath,
      version_path: versionPath,
    });
  }

  const versionPaths = await readXmlVersionFiles(versionDir);
  const manifestPath = path.join(runDir, "run_manifest.json");
  if (await fileExists(manifestPath)) {
    const manifest = (await readJson(manifestPath)) as Record<string, unknown>;
    const existingHarvested = Array.isArray(manifest.host_harvested_attempt_xml_versions)
      ? (manifest.host_harvested_attempt_xml_versions as Array<Record<string, unknown>>)
      : [];
    await writeJson(manifestPath, {
      ...manifest,
      xml_version_count: versionPaths.length,
      latest_xml_version_path: versionPaths[versionPaths.length - 1] ?? manifest.latest_xml_version_path,
      host_harvested_attempt_xml_versions: [...existingHarvested, ...harvested],
    });
  }

  return {
    harvestedCount: harvested.length,
    xmlVersionCount: versionPaths.length,
    versionPaths,
  };
}

async function readXmlVersionFiles(versionDir: string): Promise<string[]> {
  const entries = await readDirectorySafe(versionDir);
  return entries
    .filter((entry) => entry.isFile() && /^model_v\d+\.xml$/i.test(entry.name))
    .map((entry) => path.join(versionDir, entry.name))
    .sort(compareXmlVersionPaths);
}

async function findAttemptModelXmlPaths(runDir: string): Promise<string[]> {
  const roots = [path.join(runDir, "attempts"), path.join(runDir, "agent_workspace")];
  const attemptModelPaths = new Set<string>();
  for (const root of roots) {
    await visitDirectories(root, async (directoryPath, name) => {
      if (!isAttemptDirectoryName(name)) {
        return;
      }
      const modelPath = path.join(directoryPath, "model.xml");
      if (await fileExists(modelPath)) {
        attemptModelPaths.add(path.resolve(modelPath));
      }
    });
  }
  return [...attemptModelPaths].sort(compareAttemptModelXmlPaths);
}

export type CanonicalModelCandidate = {
  path: string;
  valid: boolean;
  inspected: boolean;
  reproductionScore: number | null;
  attemptNumber: number;
};

export function selectCanonicalModelCandidate(
  candidates: CanonicalModelCandidate[],
): CanonicalModelCandidate | null {
  return [...candidates]
    .filter((candidate) => candidate.valid)
    .sort((left, right) =>
      Number(right.inspected) - Number(left.inspected)
      || (right.reproductionScore ?? -1) - (left.reproductionScore ?? -1)
      || right.attemptNumber - left.attemptNumber
      || right.path.localeCompare(left.path)
    )[0] ?? null;
}

export async function ensureCanonicalModelFromExecutionArtifacts(params: {
  bridge: PythonBridge;
  runDir: string;
  agentWorkspaceDir: string;
}): Promise<void> {
  const agentRootModel = path.join(params.agentWorkspaceDir, "model.xml");
  if (await fileExists(agentRootModel)) {
    // The root model.xml is the deliverable even when invalid, e.g. mid-edit at the time limit.
    await persistCanonicalSelection(params.runDir, agentRootModel, "canonical root model", {});
    return;
  }

  const candidates: CanonicalModelCandidate[] = [];
  for (const modelPath of await findAttemptModelXmlPaths(params.runDir)) {
    const xml = await readFile(modelPath, "utf8");
    const validation = await params.bridge.invoke<{ valid?: boolean }>("validate_model_xml", {
      xml_content: xml,
    });
    const reportValue = await readJson(path.join(path.dirname(modelPath), "attempt_reproduction.json"));
    const reproduction = isRecord(reportValue) && isRecord(reportValue.reproduction)
      ? reportValue.reproduction
      : isRecord(reportValue)
        ? reportValue
        : {};
    const observable = isRecord(reproduction.observable_alignment)
      ? reproduction.observable_alignment
      : {};
    candidates.push({
      path: modelPath,
      valid: validation.ok === true,
      inspected: Array.isArray(observable.evidence) && observable.evidence.length > 0,
      reproductionScore: numberValue(reproduction.total_score),
      attemptNumber: attemptNumberFromPath(modelPath),
    });
  }
  const selected = selectCanonicalModelCandidate(candidates);
  if (!selected) {
    return;
  }
  await copyFile(selected.path, agentRootModel);
  await copyFile(selected.path, path.join(params.runDir, "model.xml"));
  // The host rerun reads the workspace snapshot so relative model assets resolve.
  await copyFile(selected.path, path.join(buildAgentWorkspaceSnapshotDir(params.runDir), "model.xml"));
  await persistCanonicalSelection(
    params.runDir,
    selected.path,
    "canonical root was missing; selected the strongest valid attempt",
    {
      valid: selected.valid,
      inspected: selected.inspected,
      reproductionScore: selected.reproductionScore,
      attemptNumber: selected.attemptNumber,
    },
  );
}

async function persistCanonicalSelection(
  runDir: string,
  selectedPath: string,
  reason: string,
  details: Record<string, unknown>,
): Promise<void> {
  const contents = await readFile(selectedPath);
  await writeJson(path.join(runDir, "canonical_selection.json"), {
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    selectedPath,
    selectedSha256: createHash("sha256").update(contents).digest("hex"),
    selectionReason: reason,
    ...details,
  });
}

function isAttemptDirectoryName(name: string): boolean {
  return /^attempt[_-]?\d+/i.test(name);
}

function compareAttemptModelXmlPaths(left: string, right: string): number {
  const leftAttempt = attemptNumberFromPath(left);
  const rightAttempt = attemptNumberFromPath(right);
  if (leftAttempt !== rightAttempt) {
    return leftAttempt - rightAttempt;
  }
  return left.localeCompare(right);
}

function attemptNumberFromPath(inputPath: string): number {
  const match = inputPath.match(/attempt[_-]?(\d+)/i);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

function compareXmlVersionPaths(left: string, right: string): number {
  return xmlVersionNumberFromPath(left) - xmlVersionNumberFromPath(right) || left.localeCompare(right);
}

function xmlVersionNumberFromPath(inputPath: string): number {
  const match = path.basename(inputPath).match(/^model_v(\d+)\.xml$/i);
  return match ? Number(match[1]) : Number.MAX_SAFE_INTEGER;
}

export async function countModelRefinementArtifacts(runDir: string): Promise<number> {
  const candidates = [
    await countManifestRefinements(path.join(runDir, "run_manifest.json")),
    await countManifestRefinements(path.join(runDir, "agent_workspace", "run_manifest.json")),
    await maxXmlVersionDirectoryCount(runDir),
    await countAgentAttemptDirectories(path.join(runDir, "agent_workspace")),
  ];
  return Math.max(0, ...candidates);
}

async function countManifestRefinements(manifestPath: string): Promise<number> {
  if (!(await fileExists(manifestPath))) {
    return 0;
  }
  const manifest = await readJson(manifestPath);
  return Math.max(modelRefinementCountFromManifest(manifest), attemptHistoryCountFromManifest(manifest));
}

function attemptHistoryCountFromManifest(manifest: unknown): number {
  if (!isRecord(manifest) || !Array.isArray(manifest.attempt_history)) {
    return 0;
  }
  const attemptIds = new Set<string>();
  let anonymousAttemptCount = 0;
  for (const attempt of manifest.attempt_history) {
    if (!isRecord(attempt)) {
      continue;
    }
    const attemptId = stringValue(attempt.attempt_id);
    if (attemptId) {
      attemptIds.add(attemptId);
    } else {
      anonymousAttemptCount += 1;
    }
  }
  return attemptIds.size + anonymousAttemptCount;
}

async function maxXmlVersionDirectoryCount(rootDir: string): Promise<number> {
  let maxCount = 0;
  await visitDirectories(rootDir, async (directoryPath, name) => {
    if (name.toLowerCase() !== "xml_versions") {
      return;
    }
    const entries = await readDirectorySafe(directoryPath);
    const count = entries.filter(
      (entry) => entry.isFile() && /^model_v\d+\.xml$/i.test(entry.name),
    ).length;
    maxCount = Math.max(maxCount, count);
  });
  return maxCount;
}

async function countAgentAttemptDirectories(agentWorkspaceDir: string): Promise<number> {
  const attemptDirectories = new Set<string>();
  await visitDirectories(agentWorkspaceDir, async (directoryPath, name) => {
    if (/^attempt[_-]?\d+/i.test(name)) {
      attemptDirectories.add(path.resolve(directoryPath));
    }
  });
  return attemptDirectories.size;
}

export async function auditAgentMorpheusAttempts(runDir: string): Promise<AttemptArtifactAudit> {
  const audit: AttemptArtifactAudit = {
    executedAttempts: 0,
    missingModelXml: 0,
    missingReproductionReport: 0,
    missingLogs: 0,
  };
  const agentWorkspaceDir = path.join(runDir, "agent_workspace");
  const attemptDirectories = new Set<string>();
  for (const rootName of ["attempts", "agent_runs"]) {
    const rootDir = path.join(agentWorkspaceDir, rootName);
    await visitDirectories(rootDir, (directoryPath, name) => {
      if (/^attempt[_-]?\d+/i.test(name)) {
        attemptDirectories.add(path.resolve(directoryPath));
      }
    });
  }
  for (const attemptDir of attemptDirectories) {
    const files = await fileNamesUnderDirectory(attemptDir);
    if (!files.has("morpheus_command.json")) {
      continue;
    }
    audit.executedAttempts += 1;
    audit.missingModelXml += Number(!(await fileExists(path.join(attemptDir, "model.xml"))));
    audit.missingReproductionReport += Number(!(await fileExists(path.join(attemptDir, "attempt_reproduction.json"))));
    audit.missingLogs += Number(!files.has("stdout.log") || !files.has("stderr.log"));
  }
  return audit;
}

async function fileNamesUnderDirectory(rootDir: string): Promise<Set<string>> {
  const names = new Set<string>();
  const visit = async (directoryPath: string): Promise<void> => {
    for (const entry of await readDirectorySafe(directoryPath)) {
      const childPath = path.join(directoryPath, entry.name);
      if (entry.isDirectory()) {
        await visit(childPath);
      } else if (entry.isFile()) {
        names.add(entry.name.toLowerCase());
      }
    }
  };
  await visit(rootDir);
  return names;
}

async function visitDirectories(
  rootDir: string,
  visitor: (directoryPath: string, name: string) => Promise<void> | void,
): Promise<void> {
  const entries = await readDirectorySafe(rootDir);
  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }
    const childPath = path.join(rootDir, entry.name);
    await visitor(childPath, entry.name);
    await visitDirectories(childPath, visitor);
  }
}

async function readDirectorySafe(directoryPath: string) {
  try {
    return await readdir(directoryPath, { withFileTypes: true });
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return [];
    }
    throw error;
  }
}

function uniquePaths(values: string[]): string[] {
  return [...new Set(values)];
}

function addCapabilityViolations(target: Set<string>, violations: string[]): void {
  for (const violation of violations) {
    target.add(violation);
  }
}

export function reconcileCapabilityViolationAudit(
  result: PaperRunResult,
  items: ThreadItem[],
): PaperRunResult {
  const capabilityViolations = collectCapabilityViolations(items, result.mode, result.runId);
  const previousViolationError = result.capabilityViolations.length > 0
    ? result.capabilityViolations.join(" ")
    : null;
  const auditedViolationError = capabilityViolations.length > 0
    ? capabilityViolations.join(" ")
    : null;
  return {
    ...result,
    capabilityViolations,
    error: previousViolationError && result.error === previousViolationError
      ? (auditedViolationError ?? undefined)
      : result.error,
    executions: result.executions?.map((execution) => ({
      ...execution,
      error: isStoredCapabilityViolationError(execution.error, previousViolationError)
        ? auditedViolationError
        : execution.error,
    })),
  };
}

function isStoredCapabilityViolationError(error: string | null, previousViolationError: string | null): boolean {
  if (!error) {
    return false;
  }
  if (previousViolationError && error === previousViolationError) {
    return true;
  }
  let remaining = error;
  for (const message of Object.values(CAPABILITY_VIOLATION_MESSAGES)) {
    remaining = remaining.replaceAll(message, "").trim();
  }
  return remaining.length === 0;
}

export async function reconcileStoredRunAudit(
  result: PaperRunResult,
  items: ThreadItem[],
  runDir: string,
): Promise<PaperRunResult> {
  const audited = reconcileCapabilityViolationAudit(result, items);
  const attemptArtifactAudit = await auditAgentMorpheusAttempts(runDir);
  return {
    ...audited,
    attempts: attemptArtifactAudit.executedAttempts,
    attemptArtifactAudit,
    diagnostics: {
      ...audited.diagnostics,
      attemptCount: attemptArtifactAudit.executedAttempts,
    },
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function resolveArtifactPath(runDir: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(runDir, value);
}

async function updateRunManifestMetadata(
  runManifestPath: string,
  metadata: Record<string, unknown>,
): Promise<void> {
  const manifest = (await readJson(runManifestPath)) as Record<string, unknown>;
  await writeJson(runManifestPath, { ...manifest, ...metadata });
}

async function readJson(inputPath: string): Promise<unknown> {
  try {
    const content = await readFile(inputPath, "utf8");
    return JSON.parse(content);
  } catch {
    return {};
  }
}

async function acquireRecoveryLock(lockPath: string): Promise<void> {
  try {
    await writeFile(
      lockPath,
      `${JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString() })}\n`,
      { encoding: "utf8", flag: "wx" },
    );
  } catch (error) {
    if (error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "EEXIST") {
      throw new Error(`Benchmark v2 run is already being postprocessed: ${path.dirname(lockPath)}`);
    }
    throw error;
  }
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function durationBetweenIsoStrings(startedAt: string | null, finishedAt: string | null): number | null {
  if (!startedAt || !finishedAt) {
    return null;
  }
  const start = Date.parse(startedAt);
  const finish = Date.parse(finishedAt);
  return Number.isFinite(start) && Number.isFinite(finish) ? Math.max(0, finish - start) : null;
}

function findStartPaperIndex(pdfs: string[], startAtPaper: string): number {
  const target = startAtPaper.toLowerCase();
  const exactIndex = pdfs.findIndex((pdf) => {
    const base = path.basename(pdf).toLowerCase();
    const stem = path.basename(pdf, path.extname(pdf)).toLowerCase();
    return target === base || target === stem;
  });
  if (exactIndex >= 0) {
    return exactIndex;
  }
  return pdfs.findIndex((pdf) => path.basename(pdf).toLowerCase().includes(target));
}

function recoverBenchmarkModes(results: PaperRunResult[]): BenchmarkModeId[] {
  const present = new Set(results.map((result) => result.mode));
  return (Object.keys(BENCHMARK_MODE_DEFINITIONS) as BenchmarkModeId[]).filter((mode) => present.has(mode));
}

function earliestIsoString(values: Array<string | null>): string | null {
  const timestamps = values
    .flatMap((value) => {
      if (!value) {
        return [];
      }
      const timestamp = Date.parse(value);
      return Number.isFinite(timestamp) ? [{ value, timestamp }] : [];
    })
    .sort((a, b) => a.timestamp - b.timestamp);
  return timestamps.length > 0 ? new Date(timestamps[0].timestamp).toISOString() : null;
}

function latestIsoString(values: Array<string | null>): string | null {
  const timestamps = values
    .flatMap((value) => {
      if (!value) {
        return [];
      }
      const timestamp = Date.parse(value);
      return Number.isFinite(timestamp) ? [timestamp] : [];
    })
    .sort((a, b) => b - a);
  return timestamps.length > 0 ? new Date(timestamps[0]).toISOString() : null;
}

export async function runOneSubjectProcess(params: {
  codex: {
    startThread(options: ThreadOptions): Pick<Thread, "id" | "runStreamed">;
  };
  threadOptions: ThreadOptions;
  input: UserInput[];
  transcriptPath: string;
}): Promise<{
  thread: Pick<Thread, "id" | "runStreamed">;
  turn: CollectedTurn;
}> {
  const thread = params.codex.startThread(params.threadOptions);
  const turn = await collectSubjectTurn(thread as Thread, params.input);
  await writeTranscript(
    params.transcriptPath,
    transcriptEventsForTurnError(turn, "Subject execution ended before producing events."),
  );
  return { thread, turn };
}

export async function runWithCleanInfrastructureReplacement<
  T extends {
    executionId: string;
    stopReason: "agent_finished" | "time_limit" | "infrastructure_failure";
    replacementEligible?: boolean;
  },
>(
  execute: (request: {
    replacementFor: string | null;
    replacementCount: 0 | 1;
  }) => Promise<T>,
): Promise<{ selected: T; executions: T[] }> {
  const first = await execute({ replacementFor: null, replacementCount: 0 });
  if (first.stopReason !== "infrastructure_failure" || first.replacementEligible !== true) {
    return { selected: first, executions: [first] };
  }
  const replacement = await execute({
    replacementFor: first.executionId,
    replacementCount: 1,
  });
  return { selected: replacement, executions: [first, replacement] };
}

async function writeTranscript(outputPath: string, events: ThreadEvent[]): Promise<void> {
  await mkdir(path.dirname(outputPath), { recursive: true });
  const content = events.length > 0 ? `${events.map((event) => JSON.stringify(event)).join("\n")}\n` : "";
  await writeFile(outputPath, content, "utf8");
}

async function writeJson(outputPath: string, payload: unknown): Promise<void> {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(payload, null, 2), "utf8");
}

export async function writeAssignmentRecoveryResult(
  benchmarkRunDir: string,
  result: PaperRunResult,
): Promise<void> {
  const assignmentId = result.assignmentId
    ?? `${sanitizeStem(path.basename(result.paper, path.extname(result.paper)))}__${result.mode}__rep${String(result.repetition).padStart(2, "0")}`;
  await writeJson(
    path.join(benchmarkRunDir, "assignment_results", `${assignmentId}.json`),
    result,
  );
}

function benchmarkAssignmentId(pdfPath: string, mode: BenchmarkModeId, repetition: number): string {
  return `${sanitizeStem(path.basename(pdfPath, path.extname(pdfPath)))}__${mode}__rep${String(repetition).padStart(2, "0")}`;
}

function isBenchmarkJob(value: unknown): value is BenchmarkJob {
  return isRecord(value)
    && typeof value.pdfPath === "string"
    && typeof value.mode === "string"
    && value.mode in BENCHMARK_MODE_DEFINITIONS
    && typeof value.repetition === "number"
    && Number.isInteger(value.repetition)
    && value.repetition >= 1;
}

export function canRerunInfrastructureFailure(
  result: Pick<PaperRunResult, "stopReason" | "replacementCount" | "error" | "summary" | "executions">,
): boolean {
  if (result.stopReason !== "infrastructure_failure") {
    return false;
  }
  if (!result.executions?.length) {
    return (result.replacementCount ?? 0) === 0;
  }
  // Codex quota and capacity refusals say nothing about the assignment, so only the other
  // infrastructure failures use up its one clean replacement.
  const budgetedFailures = result.executions.filter((execution) =>
    execution.stopReason === "infrastructure_failure" && codexServiceFailureKind(execution.error) === null
  ).length;
  return budgetedFailures <= 1;
}

async function reauditRecoveredCapabilityViolations(
  benchmarkRunDir: string,
  result: PaperRunResult,
): Promise<PaperRunResult> {
  const runDirs = [
    ...(result.runId ? [path.join(benchmarkRunDir, result.runId)] : []),
    ...(result.runManifestPath ? [path.dirname(result.runManifestPath)] : []),
  ];
  for (const runDir of uniquePaths(runDirs)) {
    const items = await readCompletedThreadItems(path.join(runDir, "transcripts", "subject.jsonl"));
    if (items === null) {
      continue;
    }
    const audited = await reconcileStoredRunAudit(result, items, runDir);
    if (
      audited.capabilityViolations.join("\n") !== result.capabilityViolations.join("\n")
      || audited.attempts !== result.attempts
      || JSON.stringify(audited.attemptArtifactAudit) !== JSON.stringify(result.attemptArtifactAudit)
    ) {
      await updateRecoveredAuditReportArtifacts(runDir, audited);
    }
    return audited;
  }
  return result;
}

async function readCompletedThreadItems(transcriptPath: string): Promise<ThreadItem[] | null> {
  let content: string;
  try {
    content = await readFile(transcriptPath, "utf8");
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return null;
    }
    throw error;
  }
  const items: ThreadItem[] = [];
  for (const line of content.split(/\r?\n/)) {
    if (!line.trim()) {
      continue;
    }
    try {
      const event = JSON.parse(line) as unknown;
      if (isRecord(event) && event.type === "item.completed" && isRecord(event.item)) {
        items.push(event.item as unknown as ThreadItem);
      }
    } catch {
      continue;
    }
  }
  return items;
}

async function updateRecoveredAuditReportArtifacts(
  runDir: string,
  result: PaperRunResult,
): Promise<void> {
  if (result.reproductionReportPath) {
    const reportPath = resolveArtifactPath(runDir, result.reproductionReportPath);
    const report = await readJson(reportPath);
    if (isRecord(report)) {
      await writeJson(reportPath, {
        ...report,
        capabilityViolations: result.capabilityViolations,
        attempts: result.attempts,
        attemptArtifactAudit: result.attemptArtifactAudit,
        diagnostics: result.diagnostics,
      });
    }
  }
  if (result.reproductionReportTextPath) {
    const reportTextPath = resolveArtifactPath(runDir, result.reproductionReportTextPath);
    try {
      const reportText = await readFile(reportTextPath, "utf8");
      await writeText(
        reportTextPath,
        reportText.replace(
          /^Capability Violations: \d+$/m,
          `Capability Violations: ${result.capabilityViolations.length}`,
        ).replace(/^Host Canonical Attempts: \d+$/m, `Subject Morpheus Attempts: ${result.attempts}`),
      );
    } catch (error) {
      if (!isFileNotFoundError(error)) {
        throw error;
      }
    }
  }
}

async function readAssignmentRecoveryResults(
  benchmarkRunDir: string,
): Promise<Map<string, PaperRunResult>> {
  const results = new Map<string, PaperRunResult>();
  const resultDir = path.join(benchmarkRunDir, "assignment_results");
  let names: string[] = [];
  try {
    names = (await readdir(resultDir)).filter((name) => name.endsWith(".json"));
  } catch {
    return results;
  }
  for (const name of names) {
    const value = await readJson(path.join(resultDir, name));
    if (!isRecord(value)) {
      continue;
    }
    const result = value as unknown as PaperRunResult;
    const assignmentId = result.assignmentId ?? name.slice(0, -".json".length);
    results.set(assignmentId, result);
  }
  return results;
}

async function buildAmbiguousRecoveryExecution(
  job: BenchmarkJob,
  assignmentId: string,
  runInfo: { runId: string; runDir: string; runManifestPath: string },
  config: BenchmarkConfig,
): Promise<PaperRunResult> {
  const timingValue = await readJson(path.join(runInfo.runDir, "subject_execution.json")).catch(() => ({}));
  const timing = isRecord(timingValue) ? timingValue : {};
  const deadlineValue = await readJson(path.join(runInfo.runDir, "subject_deadline.json")).catch(() => ({}));
  const deadline = isRecord(deadlineValue) ? deadlineValue : {};
  const base = failedResult(
    path.basename(job.pdfPath),
    job.pdfPath,
    job.mode,
    "Infrastructure-invalid execution: host recovery found subject state without a committed assignment result.",
    runInfo.runId,
    runInfo.runDir,
    runInfo.runManifestPath,
    null,
    null,
    [],
    job.repetition,
  );
  const startedAt = stringValue(timing.subjectStartedAt) ?? stringValue(deadline.subjectStartedAt);
  const finishedAt = stringValue(timing.subjectFinishedAt);
  const subjectExecutionMs = numberValue(timing.subjectExecutionMs) ?? 0;
  return {
    ...base,
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId,
    executionId: `${assignmentId}__execution_01`,
    replacementFor: null,
    replacementCount: 0,
    replacementEligible: true,
    stopReason: "infrastructure_failure",
    artifactStatus: await fileExists(path.join(runInfo.runDir, "model.xml")) ? "unscoreable" : "missing",
    workspaceDir: path.join(runInfo.runDir, "agent_workspace"),
    codexHomeDir: path.join(runInfo.runDir, "codex_home"),
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    totalTimeLimitMs: config.totalTimeLimitMs,
    finalizationReserveMs: config.finalizationReserveMs,
    subjectStartedAt: startedAt,
    subjectFinishedAt: finishedAt,
    softCutoffAt: stringValue(deadline.softCutoffAt),
    hardCutoffAt: stringValue(deadline.hardCutoffAt),
    subjectExecutionMs,
    morpheusSimulationMs: 0,
    totalJobMs: subjectExecutionMs,
    budgetFraction: subjectExecutionMs / config.totalTimeLimitMs,
    startedAt,
    finishedAt,
    durationMs: subjectExecutionMs,
  };
}

function recordedProvenanceFromState(state: Record<string, unknown>): Pick<
  BenchmarkSummary,
  "benchmarkVersion" | "benchmarkProtocol" | "benchmarkProvenance"
> {
  return {
    benchmarkProtocol: "time_limit_v2",
    ...(typeof state.benchmarkVersion === "number" ? { benchmarkVersion: state.benchmarkVersion } : {}),
    ...(isRecord(state.benchmarkProvenance)
      ? { benchmarkProvenance: state.benchmarkProvenance as unknown as BenchmarkProvenance }
      : {}),
  };
}

/** The cohort check guarantees equal versions and skills; commit details are kept only when every source agrees. */
function combineBenchmarkProvenance(provenances: BenchmarkProvenance[]): BenchmarkProvenance {
  const [first] = provenances;
  const sameCommit = provenances.every((provenance) =>
    provenance?.gitCommit === first.gitCommit && provenance?.gitDirty === first.gitDirty,
  );
  return sameCommit ? first : { ...first, gitCommit: null, gitTag: null, gitDirty: null };
}

function buildRecoveredV2Summary(params: {
  benchmarkRunDir: string;
  benchmarkId: string;
  startedAt: string;
  config: BenchmarkConfig;
  results: PaperRunResult[];
  benchmarkVersion?: number;
  benchmarkProvenance?: BenchmarkProvenance;
}): BenchmarkSummary {
  const diagnostics = emptyBenchmarkDiagnostics();
  for (const result of params.results) {
    mergeBenchmarkDiagnostics(diagnostics, result.diagnostics);
  }
  const outcomeCounts = countV2Outcomes(params.results);
  const refinementStats = summarizeModelRefinements(params.results);
  const technicalScores = params.results.flatMap((result) => result.technicalScore === null ? [] : [result.technicalScore]);
  const reproductionScores = params.results.flatMap((result) => result.reproductionScore === null ? [] : [result.reproductionScore]);
  const finishedAt = new Date().toISOString();
  return {
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    ...(params.benchmarkVersion === undefined ? {} : { benchmarkVersion: params.benchmarkVersion }),
    ...(params.benchmarkProvenance === undefined ? {} : { benchmarkProvenance: params.benchmarkProvenance }),
    config: params.config,
    benchmarkId: params.benchmarkId,
    benchmarkRunDir: params.benchmarkRunDir,
    comparisonJsonPath: path.join(params.benchmarkRunDir, "benchmark_comparison.json"),
    comparisonCsvPath: path.join(params.benchmarkRunDir, "benchmark_comparison.csv"),
    startedAt: params.startedAt,
    finishedAt,
    generatedAt: finishedAt,
    durationMs: durationBetweenIsoStrings(params.startedAt, finishedAt) ?? 0,
    diagnostics,
    ...benchmarkCardinality(params.results),
    benchmarkRepetitions: Math.max(params.config.benchmarkRepetitions, maxObservedRepetition(params.results)),
    ...outcomeCounts,
    totalModelRefinements: refinementStats.total,
    averageModelRefinements: refinementStats.average,
    averageTechnicalScore: average(technicalScores),
    averageTechnicalScoreValidOnly: average(technicalScores),
    averageTechnicalScoreItt: average(params.results.map((result) => result.technicalScore ?? 0)),
    averageReproductionScore: average(reproductionScores),
    averageReproductionScoreValidOnly: average(reproductionScores),
    averageReproductionScoreItt: average(params.results.map((result) => result.reproductionScore ?? 0)),
    paperModeStatistics: buildPaperModeStatistics(params.results, params.config.benchmarkRepetitions),
    results: params.results,
  };
}

export function benchmarkCardinality(results: Pick<PaperRunResult, "paper">[]): {
  totalRuns: number;
  uniquePapers: number;
  totalPapers: number;
} {
  const uniquePapers = new Set(results.map((result) => result.paper)).size;
  return {
    totalRuns: results.length,
    uniquePapers,
    totalPapers: uniquePapers,
  };
}

async function writeText(outputPath: string, content: string): Promise<void> {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, content, "utf8");
}

export function formatReproductionReportText(payload: {
  paper: string;
  pdfPath: string;
  mode: BenchmarkModeId;
  modeLabel: string;
  capabilityViolations: string[];
  runId: string;
  repetition?: number;
  benchmarkFocus: string | null;
  generatedAt: string;
  stopReason?: PaperRunResult["stopReason"];
  artifactStatus?: PaperRunResult["artifactStatus"];
  reproduction: AgentRunResponse["reproduction"];
  summary: string;
  technicalScore: number | null;
  technicalEvaluationPath: string | null;
  attempts: number;
  modelRefinementCount?: number;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationMs?: number;
  diagnostics?: BenchmarkDiagnostics;
}): string {
  const lines = [
    "============================================================",
    "MORPHEUS REPRODUCTION REPORT",
    "============================================================",
    `Paper: ${payload.paper}`,
    `PDF Path: ${payload.pdfPath}`,
    `Benchmark Mode: ${payload.mode} (${payload.modeLabel})`,
    `Benchmark Focus: ${payload.benchmarkFocus ?? "n/a"}`,
    `Run ID: ${payload.runId}`,
    `Repetition: ${payload.repetition ?? 1}`,
    `Timestamp: ${payload.generatedAt}`,
    `Stop Reason: ${payload.stopReason ?? "unknown"}`,
    `Artifact Status: ${payload.artifactStatus ?? "unknown"}`,
    `Started At: ${payload.startedAt ?? "n/a"}`,
    `Finished At: ${payload.finishedAt ?? "n/a"}`,
    `Wall Time: ${formatDuration(payload.durationMs ?? 0)}`,
    `Subject Morpheus Attempts: ${payload.attempts}`,
    `Model Refinements: ${payload.modelRefinementCount ?? 0}`,
    `Agent Wall Time: ${formatDuration(payload.diagnostics?.agentWallTimeMs ?? 0)}`,
    `Morpheus Simulation Time: ${formatDuration(payload.diagnostics?.morpheusSimulationTimeMs ?? 0)}`,
    `Host Morpheus Run Time: ${formatDuration(payload.diagnostics?.hostMorpheusRunTimeMs ?? 0)}`,
    `Host Technical Evaluation Time: ${formatDuration(payload.diagnostics?.hostTechnicalEvaluationTimeMs ?? 0)}`,
    `Tokens: ${payload.diagnostics?.tokens.total ?? 0} total (${payload.diagnostics?.tokens.input ?? 0} input, ${payload.diagnostics?.tokens.cachedInput ?? 0} cached input, ${payload.diagnostics?.tokens.cacheWriteInput ?? 0} cache-write input, ${payload.diagnostics?.tokens.output ?? 0} output, ${payload.diagnostics?.tokens.reasoningOutput ?? 0} reasoning output)`,
    `Technical Score: ${payload.technicalScore ?? "n/a"}`,
    `Technical Evaluation: ${payload.technicalEvaluationPath ?? "n/a"}`,
    `Capability Violations: ${payload.capabilityViolations.length}`,
    "",
    `SUMMARY: ${payload.summary || "No summary available."}`,
  ];

  if (!payload.reproduction) {
    lines.push("", "No reproduction rubric was returned.");
    return lines.join("\n");
  }

  lines.push(
    "",
    `TOTAL REPRODUCTION SCORE: ${payload.reproduction.total_score} / 8`,
    `REPRODUCTION SUMMARY: ${payload.reproduction.summary}`,
  );

  type ReproductionCriterionKey =
    | "source_coverage"
    | "mechanism_mapping"
    | "observable_alignment"
    | "parameter_plausibility";
  const sections: Array<[string, ReproductionCriterionKey]> = [
    ["Source Coverage", "source_coverage"],
    ["Mechanism Mapping", "mechanism_mapping"],
    ["Observable Alignment", "observable_alignment"],
    ["Parameter Plausibility", "parameter_plausibility"],
  ];

  for (const [title, key] of sections) {
    const criterion = payload.reproduction[key];
    lines.push("", `${title}: ${criterion.score} / 2`, `Rationale: ${criterion.rationale}`, "Evidence:");
    if (criterion.evidence.length === 0) {
      lines.push("- None provided");
      continue;
    }
    for (const evidence of criterion.evidence) {
      lines.push(`- ${evidence}`);
    }
  }

  return lines.join("\n");
}

export async function ensureFailureReproductionReport(result: PaperRunResult): Promise<PaperRunResult> {
  const failed = result.stopReason === "infrastructure_failure";
  if (!failed || result.reproductionReportPath || !result.runManifestPath) {
    return result;
  }

  const runDir = path.dirname(result.runManifestPath);
  const reproductionPayload = {
    paper: result.paper,
    pdfPath: result.pdfPath,
    mode: result.mode,
    modeLabel: result.modeLabel,
    capabilities: result.capabilities,
    capabilityViolations: result.capabilityViolations,
    runId: result.runId,
    repetition: result.repetition,
    benchmarkFocus: result.benchmarkFocus,
    generatedAt: new Date().toISOString(),
    stopReason: result.stopReason,
    artifactStatus: result.artifactStatus,
    reproduction: null,
    summary: result.summary || result.error || "Run failed before a final reproduction rubric was available.",
    technicalScore: result.technicalScore,
    technicalEvaluationPath: result.technicalEvaluationPath,
    attempts: result.attempts,
    modelRefinementCount: result.modelRefinementCount,
    startedAt: result.startedAt,
    finishedAt: result.finishedAt,
    durationMs: result.durationMs,
    diagnostics: result.diagnostics,
  };
  const reproductionPath = path.join(runDir, "reproduction_report.json");
  const reproductionTextPath = path.join(runDir, "reproduction_report.txt");
  await writeJson(reproductionPath, reproductionPayload);
  await writeText(reproductionTextPath, formatReproductionReportText(reproductionPayload));
  return {
    ...result,
    reproductionReportPath: reproductionPath,
    reproductionReportTextPath: reproductionTextPath,
  };
}

function failedResult(
  paper: string,
  pdfPath: string,
  mode: BenchmarkModeId,
  error: string,
  runId = "",
  runDir = "",
  runManifestPath: string | null = null,
  threadId: string | null = null,
  benchmarkFocus: string | null = null,
  capabilityViolations: string[] = [],
  repetition = 1,
): PaperRunResult {
  const modeDefinition = BENCHMARK_MODE_DEFINITIONS[mode];
  return {
    paper,
    pdfPath,
    mode,
    modeLabel: modeDefinition.label,
    capabilities: modeDefinition.capabilities,
    capabilityViolations,
    runId,
    threadId,
    repetition,
    startedAt: null,
    finishedAt: null,
    durationMs: 0,
    diagnostics: emptyBenchmarkDiagnostics(),
    attempts: 0,
    modelRefinementCount: 0,
    technicalScore: null,
    reproductionScore: null,
    technicalEvaluationPath: null,
    reproductionReportPath: null,
    reproductionReportTextPath: null,
    runManifestPath,
    benchmarkFocus,
    summary: error,
    error,
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    stopReason: "infrastructure_failure",
    artifactStatus: "missing",
    replacementEligible: true,
  };
}
