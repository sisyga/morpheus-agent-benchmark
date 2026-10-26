/**
 * Finalizes executions stranded by the 2026-10-11 ENOSPC incident.
 *
 * Their subject turns completed, but the host failed while writing the transcript, so
 * snapshotting, canonical model selection, the host Morpheus run, technical scoring and the
 * assignment result were never committed (the result files are 0 bytes, which recovery
 * would read as `{}`). This script resumes each execution exactly where `processExecution`
 * stopped, reusing the runner's own post-subject steps, and rebuilds the lost subject
 * transcript from the Codex session rollout (see rollout-transcript.ts and its validator).
 *
 * An execution whose subject never started is committed as the infrastructure failure it
 * was, so `--recover-run` gives it its clean rerun.
 *
 * Usage:
 *   tsx scripts/stranded-runs/finalize-stranded-runs.ts <benchmark run dir> [--apply] [--only <run name>] [--concurrency <n>]
 * Without --apply it only prints what it would do.
 */
import { readdir, readFile, rename, rm, stat, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import type { ThreadEvent, ThreadItem } from "@openai/codex-sdk";

import { loadConfigForRecoverRun } from "../../src/benchmark/config.js";
import { loadPaperFocus } from "../../src/benchmark/focus.js";
import {
  collectCapabilityViolations,
  collectInfrastructureFailures,
} from "../../src/benchmark/guardrails.js";
import { BENCHMARK_MODE_DEFINITIONS } from "../../src/benchmark/modes.js";
import { appendProgressLog } from "../../src/benchmark/progress-log.js";
import { parseAgentRunResponse } from "../../src/benchmark/prompt.js";
import type { PythonBridge } from "../../src/benchmark/python-bridge.js";
import {
  auditAgentMorpheusAttempts,
  BenchmarkRunner,
  ensureCanonicalModelFromExecutionArtifacts,
  ensureFailureReproductionReport,
  formatReproductionReportText,
  harvestAttemptModelXmlVersions,
  normalizePaperRunResult,
  readModelRefinementCount,
  writeAssignmentRecoveryResult,
  type TechnicalResult,
} from "../../src/benchmark/runner.js";
import {
  cloneBenchmarkDiagnostics,
  emptyBenchmarkDiagnostics,
  formatPaperRunProgress,
  formatScore,
  mergeTurnDiagnostics,
} from "../../src/benchmark/summary.js";
import type { AgentRunResponse, BenchmarkConfig, BenchmarkDiagnostics, BenchmarkModeId, PaperRunResult } from "../../src/benchmark/types.js";
import {
  applyMorpheusThreadEnv,
  buildBenchmarkAgentWorkspaceDir,
  buildBenchmarkCodexHomeDir,
  cleanupBenchmarkTempRunDirs,
  snapshotAgentWorkspace,
  snapshotBenchmarkCodexHome,
  syncAgentModelXml,
} from "../../src/benchmark/workspace.js";
import { rebuildSubjectTurnFromRollout, subjectMorpheusSimulationMs, type RebuiltSubjectTurn } from "./rollout-transcript.js";

/**
 * Median offsets measured on 147 finished executions of this benchmark (validate-rollout-transcripts
 * and the timing check): the harness records subjectFinishedAt 541 ms after the rollout's
 * task_complete (range 340-998 ms), and the collected turn lasts 14 ms longer than the subject.
 */
const SUBJECT_FINISH_AFTER_TASK_COMPLETE_MS = 541;
const TURN_OVERHEAD_MS = 14;
const RECOVERY_LABEL = "stranded_run_recovery_2026-10-11_enospc";

type Options = { benchmarkRunDir: string; apply: boolean; only: Set<string>; concurrency: number };

type StrandedRun = {
  runName: string;
  runDir: string;
  runManifestPath: string;
  runId: string;
  mode: BenchmarkModeId;
  pdfPath: string;
  repetition: number;
  assignmentId: string;
  assignmentResultPath: string;
  prior: PaperRunResult;
  agentWorkspaceDir: string;
  codexHomeDir: string;
  subjectStarted: boolean;
};

type RunnerInternals = {
  bridge: PythonBridge;
  runHostTechnicalEvaluation(mode: BenchmarkModeId, runId: string, runDir: string, diagnostics: BenchmarkDiagnostics): Promise<TechnicalResult>;
  captureCanonicalModelVersion(runId: string, reason: string): Promise<unknown>;
};

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const benchmarkRunDir = path.resolve(options.benchmarkRunDir);
  const config = await loadConfigForRecoverRun(benchmarkRunDir);
  const logPath = path.join(benchmarkRunDir, "benchmark.log");
  const log = (message: string) => {
    const line = `[stranded-recovery ${new Date().toISOString()}] ${message}`;
    console.log(line);
    if (options.apply) {
      appendProgressLog(logPath, `[benchmark ${formatLocal(new Date())}] ${message}`);
    }
  };

  const stranded = await discoverStrandedRuns(benchmarkRunDir, config, options.only);
  if (stranded.length === 0) {
    console.log("No stranded executions found (no 0-byte assignment results with a matching run).");
    return;
  }

  // Same environment as recoverRun, so the Python bridge resolves runs and limits identically.
  process.env.MORPHEUS_RUNS_DIR = benchmarkRunDir;
  process.env.MORPHEUS_RUN_TIMEOUT_MS = String(config.morpheusRunTimeoutMs);
  process.env.MORPHEUS_XML_SCHEMA_PATH = config.morpheusXmlSchemaPath;
  applyMorpheusThreadEnv(process.env, config.morpheusNumThreads);

  const lockPath = path.join(benchmarkRunDir, ".benchmark-v2-recovery.lock");
  if (options.apply) {
    await writeFile(lockPath, `${JSON.stringify({ pid: process.pid, startedAt: new Date().toISOString(), tool: RECOVERY_LABEL })}\n`, { flag: "wx" });
  }
  try {
    const runner = new BenchmarkRunner(config);
    const internals = runner as unknown as RunnerInternals;
    let failures = 0;
    await mapWithConcurrency(stranded, options.concurrency, async (run) => {
      try {
        const result = run.subjectStarted
          ? await finalizeSubjectExecution(run, config, internals, options.apply, log)
          : await recordUnstartedExecution(run, config, options.apply, log);
        if (result) {
          console.log(`${options.apply ? "COMMITTED" : "WOULD COMMIT"} ${run.assignmentId}: ${formatPaperRunProgress(result)}`);
        }
      } catch (error) {
        failures += 1;
        log(`Stranded run ${run.runName}: finalization failed: ${error instanceof Error ? error.stack ?? error.message : String(error)}`);
      }
    });
    if (failures > 0) {
      process.exitCode = 1;
    }
  } finally {
    if (options.apply) {
      await rm(lockPath, { force: true });
    }
  }
}

async function discoverStrandedRuns(benchmarkRunDir: string, config: BenchmarkConfig, only: Set<string>): Promise<StrandedRun[]> {
  const summary = JSON.parse(await readFile(path.join(benchmarkRunDir, "benchmark_summary.json"), "utf8")) as { results: PaperRunResult[] };
  const summaryByAssignment = new Map(summary.results.map((result) => [result.assignmentId ?? "", result]));
  const resultDir = path.join(benchmarkRunDir, "assignment_results");
  const emptyAssignments = new Set<string>();
  for (const name of await readdir(resultDir)) {
    if (name.endsWith(".json") && (await stat(path.join(resultDir, name))).size === 0) {
      emptyAssignments.add(name.slice(0, -".json".length));
    }
  }

  const candidates: StrandedRun[] = [];
  for (const runName of (await readdir(benchmarkRunDir)).sort()) {
    const runDir = path.join(benchmarkRunDir, runName);
    const runManifestPath = path.join(runDir, "run_manifest.json");
    let manifest: Record<string, unknown>;
    try {
      manifest = JSON.parse(await readFile(runManifestPath, "utf8")) as Record<string, unknown>;
    } catch {
      continue;
    }
    const mode = manifest.mode as BenchmarkModeId;
    const pdfPath = String(manifest.paper_pdf_path ?? "");
    const repetition = Number(manifest.repetition ?? 1);
    if (!(mode in BENCHMARK_MODE_DEFINITIONS) || !pdfPath) {
      continue;
    }
    const assignmentId = `${sanitizeStem(path.basename(pdfPath, path.extname(pdfPath)))}__${mode}__rep${String(repetition).padStart(2, "0")}`;
    if (!emptyAssignments.has(assignmentId) || (only.size > 0 && !only.has(runName))) {
      continue;
    }
    const prior = summaryByAssignment.get(assignmentId);
    if (!prior) {
      throw new Error(`${assignmentId} has a 0-byte result but no prior result in benchmark_summary.json.`);
    }
    candidates.push({
      runName,
      runDir,
      runManifestPath,
      runId: String(manifest.run_id ?? runName),
      mode,
      pdfPath,
      repetition,
      assignmentId,
      assignmentResultPath: path.join(resultDir, `${assignmentId}.json`),
      prior,
      agentWorkspaceDir: buildBenchmarkAgentWorkspaceDir(runDir),
      codexHomeDir: buildBenchmarkCodexHomeDir(runDir),
      subjectStarted: await nonEmptyFile(path.join(runDir, "subject_deadline.json")),
    });
  }

  // Several runs can share an assignment (earlier executions); only the newest one was stranded.
  const newestByAssignment = new Map<string, StrandedRun>();
  for (const candidate of candidates) {
    newestByAssignment.set(candidate.assignmentId, candidate);
  }
  const stranded = [...newestByAssignment.values()];
  const priorRunIds = new Set(stranded.flatMap((run) => (run.prior.executions ?? []).map((execution) => execution.runId)));
  for (const run of stranded) {
    if (priorRunIds.has(run.runId)) {
      throw new Error(`${run.runName} is already recorded in the prior result of ${run.assignmentId}; refusing to treat it as stranded.`);
    }
  }
  return stranded;
}

async function finalizeSubjectExecution(
  run: StrandedRun,
  config: BenchmarkConfig,
  internals: RunnerInternals,
  apply: boolean,
  log: (message: string) => void,
): Promise<PaperRunResult | null> {
  const { runDir, runId, mode, pdfPath, repetition, runManifestPath, agentWorkspaceDir, codexHomeDir } = run;
  if (!(await nonEmptyFile(path.join(agentWorkspaceDir, "paper.txt")))) {
    throw new Error(`The temporary agent workspace ${agentWorkspaceDir} is missing; restore it from the share backup first.`);
  }
  const paper = path.basename(pdfPath);
  const modeDefinition = BENCHMARK_MODE_DEFINITIONS[mode];
  const benchmarkFocus = await loadPaperFocus(config.benchmarkFocusDir, pdfPath);
  const manifest = JSON.parse(await readFile(runManifestPath, "utf8")) as Record<string, unknown>;
  const deadline = JSON.parse(await readFile(path.join(runDir, "subject_deadline.json"), "utf8")) as Record<string, unknown>;
  const transcriptPath = path.join(runDir, "transcripts", "subject.jsonl");
  const executionTimingPath = path.join(runDir, "subject_execution.json");

  // The subject turn: the committed transcript when it survived, otherwise the rollout.
  const turn = await loadSubjectTurn(run, transcriptPath);
  if (!turn.taskCompleted) {
    throw new Error(`The subject turn of ${run.runName} never completed; it is not a stranded finished execution.`);
  }
  const existingTiming = await readJsonOrNull(executionTimingPath);
  const subjectStartedAt = String(deadline.subjectStartedAt);
  const timing = existingTiming && typeof existingTiming.subjectFinishedAt === "string"
    ? existingTiming
    : {
        artifactSchemaVersion: 2,
        benchmarkProtocol: "time_limit_v2",
        subjectStartedAt,
        subjectFinishedAt: new Date((turn.taskCompletedAtMs ?? 0) + SUBJECT_FINISH_AFTER_TASK_COMPLETE_MS).toISOString(),
        subjectExecutionMs: Math.max(0, (turn.taskCompletedAtMs ?? 0) + SUBJECT_FINISH_AFTER_TASK_COMPLETE_MS - Date.parse(subjectStartedAt)),
        // Codex exited normally: the rollout ends in task_complete and no time-limit kill happened.
        stopReason: "agent_finished",
      };
  const subjectExecutionMs = Number(timing.subjectExecutionMs);
  if (subjectExecutionMs > config.totalTimeLimitMs) {
    throw new Error(`${run.runName}: reconstructed subject time ${subjectExecutionMs} ms exceeds the time limit; refusing to guess.`);
  }
  const runStartedAt = new Date(String(manifest.created_at));
  if (!Number.isFinite(runStartedAt.getTime()) || Date.parse(subjectStartedAt) - runStartedAt.getTime() > 10 * 60_000 || runStartedAt.getTime() > Date.parse(subjectStartedAt)) {
    throw new Error(`${run.runName}: run_manifest created_at ${String(manifest.created_at)} is not a plausible run start before ${subjectStartedAt}.`);
  }

  const capabilityViolations = new Set(collectCapabilityViolations(turn.items, mode, runId));
  const infrastructureFailures = collectInfrastructureFailures(turn.items);
  let finalResponse: AgentRunResponse | null = null;
  let responseError: string | null = null;
  try {
    finalResponse = parseAgentRunResponse(turn.finalResponse);
    if (finalResponse.runId !== runId) {
      throw new Error(`response runId ${finalResponse.runId} does not match ${runId}`);
    }
  } catch (error) {
    finalResponse = null;
    responseError = turn.finalResponse.trim()
      ? `Invalid final response: ${(error as Error).message}`
      : "No final response was produced.";
  }
  const morpheusSimulationMs = subjectMorpheusSimulationMs(turn.rebuilt);
  const plan = `${run.runName}: source=${turn.source}, items=${turn.items.length}, stop=${String(timing.stopReason)}, `
    + `subject=${Math.round(subjectExecutionMs / 60000)} min, simulation=${Math.round(morpheusSimulationMs / 60000)} min, `
    + `selfReportedReproduction=${finalResponse?.reproduction?.total_score ?? "n/a"}, violations=${capabilityViolations.size}, `
    + `infrastructureFailures=${infrastructureFailures.length}, responseError=${responseError ?? "none"}, `
    + `prior executions=${(run.prior.executions ?? []).length}`;
  if (!apply) {
    console.log(`PLAN ${plan}`);
    return null;
  }
  log(`Stranded run ${runId}: resuming host finalization after the 2026-10-11 ENOSPC failure (${plan}).`);
  const finalizationStartedAt = Date.now();

  // Re-create what the crash left half-written before the runner's own steps run again.
  if (turn.source === "rollout") {
    await writeFile(transcriptPath, `${turn.events.map((event) => JSON.stringify(event)).join("\n")}\n`, "utf8");
  }
  await writeJson(executionTimingPath, timing);
  for (const name of await readdir(runDir)) {
    if (/^subject_execution\.json\.\d+\.\d+\.tmp$/.test(name)) {
      await rm(path.join(runDir, name), { force: true });
    }
  }
  await setAsideInterruptedHostAttempts(run);

  // From here on this mirrors BenchmarkRunner.processExecution after the subject turn.
  const runDiagnostics = emptyBenchmarkDiagnostics();
  mergeTurnDiagnostics(runDiagnostics, {
    durationMs: subjectExecutionMs + TURN_OVERHEAD_MS,
    morpheusSimulationMs,
    usage: turn.usage,
  });
  await snapshotBenchmarkCodexHome(codexHomeDir, runDir);
  await syncAgentModelXml(agentWorkspaceDir, runDir);
  await snapshotAgentWorkspace(agentWorkspaceDir, runDir);
  await harvestAttemptModelXmlVersions(runDir);
  await internals.captureCanonicalModelVersion(runId, "subject_execution");

  const subjectStopReason = String(timing.stopReason);
  const infrastructureError = subjectStopReason === "infrastructure_failure"
    ? infrastructureFailures.join(" ") || "Subject process failed."
    : null;

  await ensureCanonicalModelFromExecutionArtifacts({ bridge: internals.bridge, runDir, agentWorkspaceDir });
  const technical = await internals.runHostTechnicalEvaluation(mode, runId, runDir, runDiagnostics);
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
    : (await nonEmptyFile(path.join(runDir, "model.xml")) ? "unscoreable" : "missing");
  const technicalScore = technical.ok ? technical.total_score : null;
  const technicalPath = technical.ok ? technical.evaluation_json_path : null;
  const attemptCount = attemptArtifactAudit.executedAttempts;
  const reproductionScore = finalResponse?.reproduction?.total_score ?? null;

  // The job timeline as if the host had finalized right after the subject; the real
  // finalization time is still measured and the actual date is recorded in strandedRecovery.
  const finalizationMs = Date.now() - finalizationStartedAt;
  const finishedAt = new Date(Date.parse(String(timing.subjectFinishedAt)) + finalizationMs);
  const durationMs = finishedAt.getTime() - runStartedAt.getTime();
  const resultDiagnostics = cloneBenchmarkDiagnostics(runDiagnostics);
  const modelRefinementCount = await readModelRefinementCount(runManifestPath);
  log(
    `Run ${runId}: subject stop=${subjectStopReason}, technical=${technical.ok ? formatScore(technicalScore, technical.max_possible_score ?? 7) : "failed"}, reproduction=${formatScore(reproductionScore, 8)}, modelRefinements=${modelRefinementCount}.`,
  );
  const strandedRecovery = {
    label: RECOVERY_LABEL,
    finalizedAt: new Date().toISOString(),
    subjectTurnSource: turn.source,
    subjectTimingSource: existingTiming ? "subject_execution.json" : "rollout task_complete + 541 ms",
    hostFinalizationMs: finalizationMs,
    note: "Subject turn completed on 2026-10-11; host finalization failed with ENOSPC and was resumed from the preserved workspace and Codex session.",
  };
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
    strandedRecovery,
  };
  const primaryReportDir = technicalPath ? path.dirname(technicalPath) : runDir;
  for (const reportDir of [...new Set([primaryReportDir, runDir])]) {
    await writeJson(path.join(reportDir, "reproduction_report.json"), reproductionPayload);
    await writeFile(path.join(reportDir, "reproduction_report.txt"), formatReproductionReportText(reproductionPayload), "utf8");
  }

  const executionId = `${run.assignmentId}__execution_${String((run.prior.executions ?? []).length + 1).padStart(2, "0")}`;
  const selected: PaperRunResult = {
    paper,
    pdfPath,
    mode,
    modeLabel: modeDefinition.label,
    capabilities: modeDefinition.capabilities,
    capabilityViolations: [...capabilityViolations],
    runId,
    threadId: turn.threadId,
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
    reproductionReportPath: path.join(primaryReportDir, "reproduction_report.json"),
    reproductionReportTextPath: path.join(primaryReportDir, "reproduction_report.txt"),
    runManifestPath,
    benchmarkFocus,
    summary: finalResponse?.summary ?? responseError ?? infrastructureError ?? "No final summary available.",
    error: runFailed ? infrastructureError ?? [...capabilityViolations].join(" ") : undefined,
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId: run.assignmentId,
    executionId,
    replacementFor: priorExecutionId(run),
    replacementCount: 1,
    stopReason,
    artifactStatus,
    workspaceDir: path.join(runDir, "agent_workspace"),
    codexHomeDir: path.join(runDir, "codex_home"),
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    totalTimeLimitMs: config.totalTimeLimitMs,
    finalizationReserveMs: config.finalizationReserveMs,
    subjectStartedAt: String(timing.subjectStartedAt),
    subjectFinishedAt: String(timing.subjectFinishedAt),
    softCutoffAt: typeof deadline.softCutoffAt === "string" ? deadline.softCutoffAt : null,
    hardCutoffAt: typeof deadline.hardCutoffAt === "string" ? deadline.hardCutoffAt : null,
    subjectExecutionMs,
    morpheusSimulationMs: runDiagnostics.morpheusSimulationTimeMs,
    totalJobMs: durationMs,
    budgetFraction: subjectExecutionMs / config.totalTimeLimitMs,
    replacementEligible: false,
    ...({ strandedRecovery } as Record<string, unknown>),
  } as PaperRunResult;
  await updateManifest(runManifestPath, { stranded_recovery: strandedRecovery });
  const committed = await commitAssignmentResult(run, selected, log);
  await cleanupBenchmarkTempRunDirs([agentWorkspaceDir, codexHomeDir]);
  return committed;
}

/** An execution killed before its subject started: commit the infrastructure failure it was. */
async function recordUnstartedExecution(
  run: StrandedRun,
  config: BenchmarkConfig,
  apply: boolean,
  log: (message: string) => void,
): Promise<PaperRunResult | null> {
  const message = "Infrastructure failure: ENOSPC: no space left on device (host disk full during the 2026-10-11 recovery; "
    + "the subject never started, and the original error text was lost because the result file could not be written).";
  if (!apply) {
    console.log(`PLAN ${run.runName}: subject never started; commit infrastructure_failure so --recover-run reruns it once.`);
    return null;
  }
  const modeDefinition = BENCHMARK_MODE_DEFINITIONS[run.mode];
  const executionId = `${run.assignmentId}__execution_${String((run.prior.executions ?? []).length + 1).padStart(2, "0")}`;
  const failure = {
    paper: path.basename(run.pdfPath),
    pdfPath: run.pdfPath,
    mode: run.mode,
    modeLabel: modeDefinition.label,
    capabilities: modeDefinition.capabilities,
    capabilityViolations: [],
    runId: run.runId,
    threadId: null,
    repetition: run.repetition,
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
    runManifestPath: run.runManifestPath,
    benchmarkFocus: await loadPaperFocus(config.benchmarkFocusDir, run.pdfPath),
    summary: message,
    error: message,
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    assignmentId: run.assignmentId,
    executionId,
    replacementFor: priorExecutionId(run),
    replacementCount: 1,
    stopReason: "infrastructure_failure",
    artifactStatus: "missing",
    workspaceDir: "",
    codexHomeDir: "",
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    totalTimeLimitMs: config.totalTimeLimitMs,
    finalizationReserveMs: config.finalizationReserveMs,
    subjectExecutionMs: 0,
    replacementEligible: true,
    strandedRecovery: { label: RECOVERY_LABEL, finalizedAt: new Date().toISOString(), subjectStarted: false },
  } as unknown as PaperRunResult;
  const committed = await commitAssignmentResult(run, failure, log);
  await cleanupBenchmarkTempRunDirs([run.agentWorkspaceDir, run.codexHomeDir]);
  return committed;
}

/** processPaper's audit trail plus recoverRun's normalization, then the durable write. */
async function commitAssignmentResult(run: StrandedRun, selected: PaperRunResult, log: (message: string) => void): Promise<PaperRunResult> {
  const priorAudits = run.prior.executions ?? [];
  const combined: PaperRunResult = {
    ...selected,
    assignmentId: run.assignmentId,
    selectedExecutionId: selected.executionId,
    executions: [...priorAudits, toExecutionAudit(selected)],
  };
  const recovered = await ensureFailureReproductionReport(await normalizePaperRunResult(combined));
  await writeAssignmentRecoveryResult(path.dirname(path.dirname(run.assignmentResultPath)), recovered);
  const written = JSON.parse(await readFile(run.assignmentResultPath, "utf8")) as PaperRunResult;
  if (written.executionId !== selected.executionId) {
    throw new Error(`Read-back of ${run.assignmentResultPath} does not contain ${selected.executionId}.`);
  }
  log(`Finished stranded-run recovery: ${formatPaperRunProgress(recovered)}.`);
  return recovered;
}

function toExecutionAudit(execution: PaperRunResult): NonNullable<PaperRunResult["executions"]>[number] {
  return {
    executionId: execution.executionId ?? execution.runId,
    runId: execution.runId,
    replacementFor: execution.replacementFor ?? null,
    replacementCount: execution.replacementCount ?? 0,
    stopReason: execution.stopReason ?? "infrastructure_failure",
    workspaceDir: execution.workspaceDir ?? "",
    codexHomeDir: execution.codexHomeDir ?? "",
    model: execution.model ?? "",
    reasoningEffort: execution.reasoningEffort ?? "high",
    totalTimeLimitMs: execution.totalTimeLimitMs ?? 0,
    finalizationReserveMs: execution.finalizationReserveMs ?? 0,
    subjectExecutionMs: execution.subjectExecutionMs ?? 0,
    morpheusSimulationMs: execution.morpheusSimulationMs ?? 0,
    totalJobMs: execution.totalJobMs ?? execution.durationMs ?? 0,
    artifactStatus: execution.artifactStatus ?? "missing",
    startedAt: execution.startedAt ?? null,
    finishedAt: execution.finishedAt ?? null,
    error: execution.error ?? null,
  } as NonNullable<PaperRunResult["executions"]>[number];
}

function priorExecutionId(run: StrandedRun): string | null {
  const priorAudits = run.prior.executions ?? [];
  return priorAudits[priorAudits.length - 1]?.executionId ?? run.prior.executionId ?? null;
}

type LoadedTurn = Pick<RebuiltSubjectTurn, "threadId" | "items" | "finalResponse" | "usage" | "taskCompleted" | "taskCompletedAtMs" | "itemTimes"> & {
  events: ThreadEvent[];
  source: "transcript" | "rollout";
  /** Always the rollout rebuild: the only source of per-item timings. */
  rebuilt: RebuiltSubjectTurn;
};

async function loadSubjectTurn(run: StrandedRun, transcriptPath: string): Promise<LoadedTurn> {
  const rollout = await findSubjectRollout(run);
  const rebuilt = await rebuildSubjectTurnFromRollout(rollout);
  if (rebuilt.unparsedLineCount > 0) {
    throw new Error(`${rollout} has ${rebuilt.unparsedLineCount} unparseable lines.`);
  }
  const transcriptText = await readFile(transcriptPath, "utf8").catch(() => "");
  const events = transcriptText.split("\n").filter(Boolean).flatMap((line) => {
    try {
      return [JSON.parse(line) as ThreadEvent];
    } catch {
      return [];
    }
  });
  if (events.some((event) => event.type === "turn.completed")) {
    const items = new Map<string, ThreadItem>();
    let finalResponse = "";
    let usage = rebuilt.usage;
    for (const event of events) {
      if (event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") {
        items.set(event.item.id, event.item);
        if (event.item.type === "agent_message") {
          finalResponse = event.item.text;
        }
      }
      if (event.type === "turn.completed") {
        usage = event.usage as typeof usage;
      }
    }
    if ((events[0] as { thread_id?: string }).thread_id !== rebuilt.threadId) {
      throw new Error(`${run.runName}: transcript thread does not match the subject rollout.`);
    }
    return { ...rebuilt, events, items: [...items.values()], finalResponse, usage, source: "transcript", rebuilt };
  }
  return { ...rebuilt, source: "rollout", rebuilt };
}

/** The subject thread is the rollout whose first user message is the stored subject prompt. */
async function findSubjectRollout(run: StrandedRun): Promise<string> {
  const prompt = (await readFile(path.join(run.runDir, "subject_prompt.txt"), "utf8")).slice(0, 400);
  const rollouts: string[] = [];
  const walk = async (dir: string): Promise<void> => {
    for (const entry of await readdir(dir, { withFileTypes: true }).catch(() => [])) {
      const entryPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(entryPath);
      } else if (entry.name.startsWith("rollout-") && entry.name.endsWith(".jsonl")) {
        rollouts.push(entryPath);
      }
    }
  };
  await walk(path.join(run.codexHomeDir, "sessions"));
  const matches: string[] = [];
  for (const rollout of rollouts) {
    const text = await readFile(rollout, "utf8");
    if (text.includes(JSON.stringify(prompt.slice(0, 200)).slice(1, -1))) {
      matches.push(rollout);
    }
  }
  if (matches.length !== 1) {
    throw new Error(`${run.runName}: expected exactly one subject rollout under ${run.codexHomeDir}, found ${matches.length} of ${rollouts.length}.`);
  }
  return matches[0];
}

/** A host attempt interrupted by the crash would otherwise become attempt_001 next to the rerun. */
async function setAsideInterruptedHostAttempts(run: StrandedRun): Promise<void> {
  const attemptsDir = path.join(run.runDir, "attempts");
  const entries = await readdir(attemptsDir).catch(() => [] as string[]);
  if (entries.length === 0) {
    return;
  }
  const asideDir = path.join(run.runDir, "stranded_recovery");
  await mkdir(asideDir, { recursive: true });
  for (const name of entries) {
    await rename(path.join(attemptsDir, name), path.join(asideDir, `interrupted_host_${name}`));
  }
  await writeJson(path.join(asideDir, "README.json"), {
    label: RECOVERY_LABEL,
    movedAt: new Date().toISOString(),
    reason: "Host Morpheus run interrupted by ENOSPC on 2026-10-11; set aside so the resumed host run is attempt_001 as in every other execution.",
    moved: entries,
  });
}

async function updateManifest(runManifestPath: string, metadata: Record<string, unknown>): Promise<void> {
  const manifest = JSON.parse(await readFile(runManifestPath, "utf8")) as Record<string, unknown>;
  await writeJson(runManifestPath, { ...manifest, ...metadata });
}

async function writeJson(outputPath: string, payload: unknown): Promise<void> {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(payload, null, 2), "utf8");
}

async function readJsonOrNull(inputPath: string): Promise<Record<string, unknown> | null> {
  try {
    const value = JSON.parse(await readFile(inputPath, "utf8")) as unknown;
    return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

async function nonEmptyFile(filePath: string): Promise<boolean> {
  try {
    const info = await stat(filePath);
    return info.isFile() && info.size > 0;
  } catch {
    return false;
  }
}

function sanitizeStem(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "_");
}

function formatLocal(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function mapWithConcurrency<T>(values: T[], concurrency: number, worker: (value: T) => Promise<void>): Promise<void> {
  let next = 0;
  await Promise.all(Array.from({ length: Math.max(1, Math.min(concurrency, values.length)) }, async () => {
    while (next < values.length) {
      const value = values[next++];
      await worker(value);
    }
  }));
}

function parseArgs(args: string[]): Options {
  const options: Options = { benchmarkRunDir: "", apply: false, only: new Set(), concurrency: 3 };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--apply") {
      options.apply = true;
    } else if (arg === "--only") {
      options.only.add(args[++index]);
    } else if (arg === "--concurrency") {
      options.concurrency = Number(args[++index]);
    } else if (!options.benchmarkRunDir) {
      options.benchmarkRunDir = arg;
    } else {
      throw new Error(`Unexpected argument ${arg}`);
    }
  }
  if (!options.benchmarkRunDir) {
    throw new Error("Usage: finalize-stranded-runs.ts <benchmark run dir> [--apply] [--only <run name>] [--concurrency <n>]");
  }
  return options;
}

await main();
