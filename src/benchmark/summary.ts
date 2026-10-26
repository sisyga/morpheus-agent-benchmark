import { BENCHMARK_MODE_DEFINITIONS } from "./modes.js";
import type {
  BenchmarkDiagnostics,
  BenchmarkModeId,
  BenchmarkNumericStats,
  BenchmarkSummary,
  PaperModeStatistics,
  PaperRunResult,
} from "./types.js";

export type BenchmarkComparison = {
  generatedAt: string;
  modes: Array<{
    mode: BenchmarkModeId;
    modeLabel: string;
    totalRuns: number;
    totalPapers: number;
    agentFinishedRuns: number;
    timeLimitRuns: number;
    infrastructureFailureRuns: number;
    scoreableRuns: number;
    replacementRuns: number;
    totalModelRefinements: number;
    averageModelRefinements: number;
    totalDurationMs: number;
    averageDurationMs: number;
    diagnostics: BenchmarkDiagnostics;
    averageTechnicalScore: number;
    averageReproductionScore: number;
    averageBiologicalScore: number | null;
    capabilityViolationCount: number;
  }>;
};

export function emptyBenchmarkDiagnostics(): BenchmarkDiagnostics {
  return {
    turnCount: 0,
    attemptCount: 0,
    agentWallTimeMs: 0,
    morpheusSimulationTimeMs: 0,
    agentAnalysisTimeMs: 0,
    hostMorpheusRunTimeMs: 0,
    hostTechnicalEvaluationTimeMs: 0,
    tokens: {
      input: 0,
      cachedInput: 0,
      cacheWriteInput: 0,
      output: 0,
      reasoningOutput: 0,
      total: 0,
    },
  };
}

export function cloneBenchmarkDiagnostics(diagnostics: BenchmarkDiagnostics): BenchmarkDiagnostics {
  return {
    ...diagnostics,
    tokens: { ...diagnostics.tokens },
  };
}

export function mergeBenchmarkDiagnostics(
  target: BenchmarkDiagnostics,
  source: BenchmarkDiagnostics,
): void {
  target.turnCount += source.turnCount;
  target.attemptCount += source.attemptCount;
  target.agentWallTimeMs += source.agentWallTimeMs;
  target.morpheusSimulationTimeMs += source.morpheusSimulationTimeMs;
  target.hostMorpheusRunTimeMs += source.hostMorpheusRunTimeMs;
  target.hostTechnicalEvaluationTimeMs += source.hostTechnicalEvaluationTimeMs;
  target.agentAnalysisTimeMs = Math.max(
    0,
    target.agentWallTimeMs - target.morpheusSimulationTimeMs,
  );
  target.tokens.input += source.tokens.input;
  target.tokens.cachedInput += source.tokens.cachedInput;
  target.tokens.cacheWriteInput += source.tokens.cacheWriteInput;
  target.tokens.output += source.tokens.output;
  target.tokens.reasoningOutput += source.tokens.reasoningOutput;
  target.tokens.total = target.tokens.input + target.tokens.output;
}

export function mergeTurnDiagnostics(
  diagnostics: BenchmarkDiagnostics,
  turn: {
    durationMs: number;
    morpheusSimulationMs: number;
    usage: {
      input_tokens: number;
      cached_input_tokens: number;
      cache_write_input_tokens?: number;
      output_tokens: number;
      reasoning_output_tokens?: number;
    } | null;
  },
): void {
  diagnostics.turnCount += 1;
  diagnostics.agentWallTimeMs += turn.durationMs;
  diagnostics.morpheusSimulationTimeMs += turn.morpheusSimulationMs;
  diagnostics.agentAnalysisTimeMs = Math.max(
    0,
    diagnostics.agentWallTimeMs - diagnostics.morpheusSimulationTimeMs,
  );
  if (!turn.usage) {
    return;
  }
  diagnostics.tokens.input += turn.usage.input_tokens;
  diagnostics.tokens.cachedInput += turn.usage.cached_input_tokens;
  diagnostics.tokens.cacheWriteInput += turn.usage.cache_write_input_tokens ?? 0;
  diagnostics.tokens.output += turn.usage.output_tokens;
  diagnostics.tokens.reasoningOutput += turn.usage.reasoning_output_tokens ?? 0;
  diagnostics.tokens.total = diagnostics.tokens.input + diagnostics.tokens.output;
}

export function average(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }
  return Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2));
}

function roundStat(value: number): number {
  return Number(value.toFixed(2));
}

function numericStats(values: number[]): BenchmarkNumericStats {
  const finiteValues = values.filter((value) => Number.isFinite(value));
  if (finiteValues.length === 0) {
    return { count: 0, mean: 0, stdDev: 0, min: 0, max: 0, sum: 0 };
  }
  const sum = finiteValues.reduce((total, value) => total + value, 0);
  const mean = sum / finiteValues.length;
  const variance =
    finiteValues.length > 1
      ? finiteValues.reduce((total, value) => total + (value - mean) ** 2, 0) / (finiteValues.length - 1)
      : 0;
  return {
    count: finiteValues.length,
    mean: roundStat(mean),
    stdDev: roundStat(Math.sqrt(variance)),
    min: Math.min(...finiteValues),
    max: Math.max(...finiteValues),
    sum: roundStat(sum),
  };
}

export function repetitionValue(value: unknown): number | null {
  const repetition = numberValue(value);
  return repetition === null ? null : Math.max(1, Math.floor(repetition));
}

export function resultRepetition(result: Pick<PaperRunResult, "repetition">): number {
  return repetitionValue(result.repetition) ?? 1;
}

export function maxObservedRepetition(results: PaperRunResult[]): number {
  return Math.max(1, ...results.map((result) => resultRepetition(result)));
}

export function formatScore(value: number | null, max: number): string {
  return value === null ? "n/a" : `${value}/${max}`;
}

export function formatPaperRunProgress(result: PaperRunResult): string {
  return [
    `${result.paper} [${result.mode}]`,
    `stop=${result.stopReason ?? "unknown"}`,
    `artifacts=${result.artifactStatus ?? "unknown"}`,
    `attempts=${result.attempts}`,
    `modelRefinements=${result.modelRefinementCount}`,
    `technical=${formatScore(result.technicalScore, 7)}`,
    `reproduction=${formatScore(result.reproductionScore, 8)}`,
  ].join(", ");
}

export function modelRefinementCountValue(value: unknown): number | null {
  const count = numberValue(value);
  return count === null ? null : Math.max(0, Math.floor(count));
}

export function summarizeModelRefinements(results: PaperRunResult[]): { total: number; average: number } {
  const counts = results.map(
    (result) => modelRefinementCountValue((result as { modelRefinementCount?: unknown }).modelRefinementCount) ?? 0,
  );
  return {
    total: counts.reduce((sum, value) => sum + value, 0),
    average: average(counts),
  };
}

const PAPER_MODE_NUMERIC_METRICS: Array<[string, (result: PaperRunResult) => number | null]> = [
  ["technicalScore", (result) => result.technicalScore],
  ["reproductionScore", (result) => result.reproductionScore],
  ["biologicalScore", (result) => result.biologicalScore ?? null],
  ["attempts", (result) => result.attempts],
  ["modelRefinementCount", (result) => result.modelRefinementCount],
  ["durationMs", (result) => result.durationMs],
  ["turnCount", (result) => result.diagnostics.turnCount],
  ["diagnosticAttemptCount", (result) => result.diagnostics.attemptCount],
  ["agentWallTimeMs", (result) => result.diagnostics.agentWallTimeMs],
  ["morpheusSimulationTimeMs", (result) => result.diagnostics.morpheusSimulationTimeMs],
  ["agentAnalysisTimeMs", (result) => result.diagnostics.agentAnalysisTimeMs],
  ["hostMorpheusRunTimeMs", (result) => result.diagnostics.hostMorpheusRunTimeMs],
  ["hostTechnicalEvaluationTimeMs", (result) => result.diagnostics.hostTechnicalEvaluationTimeMs],
  ["inputTokens", (result) => result.diagnostics.tokens.input],
  ["cachedInputTokens", (result) => result.diagnostics.tokens.cachedInput],
  ["cacheWriteInputTokens", (result) => result.diagnostics.tokens.cacheWriteInput],
  ["outputTokens", (result) => result.diagnostics.tokens.output],
  ["reasoningOutputTokens", (result) => result.diagnostics.tokens.reasoningOutput],
  ["totalTokens", (result) => result.diagnostics.tokens.total],
  ["capabilityViolationCount", (result) => result.capabilityViolations.length],
];

export function buildPaperModeStatistics(
  results: PaperRunResult[],
  expectedRepetitions = 1,
): PaperModeStatistics[] {
  const groups = new Map<string, PaperRunResult[]>();
  const order: string[] = [];
  for (const result of results) {
    const key = `${result.paper}__${result.mode}`;
    if (!groups.has(key)) {
      groups.set(key, []);
      order.push(key);
    }
    groups.get(key)?.push(result);
  }

  return order.flatMap((key) => {
    const groupResults = groups.get(key);
    if (!groupResults || groupResults.length === 0) {
      return [];
    }
    const first = groupResults[0];
    const repetitions = [...new Set(groupResults.map((result) => resultRepetition(result)))].sort((a, b) => a - b);
    const outcomeCounts = countV2Outcomes(groupResults);
    const metrics = Object.fromEntries(
      PAPER_MODE_NUMERIC_METRICS.map(([metricName, readMetric]) => [
        metricName,
        numericStats(groupResults.flatMap((result) => {
          const value = readMetric(result);
          return value === null ? [] : [value];
        })),
      ]),
    );
    return [{
      paper: first.paper,
      pdfPath: first.pdfPath,
      mode: first.mode,
      modeLabel: first.modeLabel,
      expectedRepetitions: Math.max(expectedRepetitions, ...repetitions),
      observedRepetitions: groupResults.length,
      repetitions,
      runIds: groupResults.map((result) => result.runId),
      ...outcomeCounts,
      metrics,
    }];
  });
}

export function countV2Outcomes(results: PaperRunResult[]) {
  const totalExecutions = results.reduce(
    (total, result) => total + (result.executions?.length ?? 1),
    0,
  );
  const infrastructureFailureExecutions = results.reduce(
    (total, result) => total + (
      result.executions
        ? result.executions.filter((execution) => execution.stopReason === "infrastructure_failure").length
        : result.stopReason === "infrastructure_failure" ? 1 : 0
    ),
    0,
  );
  return {
    agentFinishedRuns: results.filter((result) => result.stopReason === "agent_finished").length,
    timeLimitRuns: results.filter((result) => result.stopReason === "time_limit").length,
    infrastructureFailureRuns: results.filter((result) => result.stopReason === "infrastructure_failure").length,
    scoreableRuns: results.filter((result) => result.artifactStatus === "scoreable").length,
    replacementRuns: results.filter((result) => (result.replacementCount ?? 0) > 0).length,
    totalExecutions,
    infrastructureFailureExecutions,
  };
}

export function buildBenchmarkManifest(summary: BenchmarkSummary): Record<string, unknown> {
  return {
    ...(summary.benchmarkVersion === undefined ? {} : { benchmarkVersion: summary.benchmarkVersion }),
    benchmarkId: summary.benchmarkId,
    benchmarkRunDir: summary.benchmarkRunDir,
    startedAt: summary.startedAt,
    finishedAt: summary.finishedAt,
    durationMs: summary.durationMs,
    diagnostics: summary.diagnostics,
    totalRuns: summary.totalRuns,
    uniquePapers: summary.uniquePapers,
    benchmarkRepetitions: summary.benchmarkRepetitions,
    totalModelRefinements: summary.totalModelRefinements,
    averageModelRefinements: summary.averageModelRefinements,
    paperModeStatistics: summary.paperModeStatistics,
    config: summary.config,
    papers: summary.results.map((result) => ({
      paper: result.paper,
      runId: result.runId,
      repetition: result.repetition,
      stopReason: result.stopReason,
      artifactStatus: result.artifactStatus,
      mode: result.mode,
      attempts: result.attempts,
      modelRefinementCount: result.modelRefinementCount,
      durationMs: result.durationMs,
      diagnostics: result.diagnostics,
      technicalScore: result.technicalScore,
      reproductionScore: result.reproductionScore,
      biologicalScore: result.biologicalScore ?? null,
      runManifestPath: result.runManifestPath,
      reproductionReportPath: result.reproductionReportPath,
      biologicalScorePath: result.biologicalScorePath ?? null,
    })),
  };
}

export function buildBenchmarkComparison(summary: BenchmarkSummary): BenchmarkComparison {
  return {
    generatedAt: summary.generatedAt,
    modes: summary.config.benchmarkModes.map((mode) => {
      const results = summary.results.filter((result) => result.mode === mode);
      const technicalScores = results.flatMap((result) =>
        result.technicalScore === null ? [] : [result.technicalScore],
      );
      const reproductionScores = results.flatMap((result) =>
        result.reproductionScore === null ? [] : [result.reproductionScore],
      );
      const biologicalScores = results.flatMap((result) =>
        result.biologicalScore === null || result.biologicalScore === undefined ? [] : [result.biologicalScore],
      );
      const diagnostics = emptyBenchmarkDiagnostics();
      for (const result of results) {
        mergeBenchmarkDiagnostics(diagnostics, result.diagnostics);
      }
      const totalDurationMs = results.reduce((sum, result) => sum + result.durationMs, 0);
      const modelRefinementStats = summarizeModelRefinements(results);
      const outcomeCounts = countV2Outcomes(results);
      return {
        mode,
        modeLabel: BENCHMARK_MODE_DEFINITIONS[mode].label,
        totalRuns: results.length,
        totalPapers: new Set(results.map((result) => result.paper)).size,
        ...outcomeCounts,
        totalModelRefinements: modelRefinementStats.total,
        averageModelRefinements: modelRefinementStats.average,
        totalDurationMs,
        averageDurationMs: results.length === 0 ? 0 : Math.round(totalDurationMs / results.length),
        diagnostics,
        averageTechnicalScore: average(technicalScores),
        averageReproductionScore: average(reproductionScores),
        averageBiologicalScore: biologicalScores.length === 0 ? null : average(biologicalScores),
        capabilityViolationCount: results.reduce(
          (sum, result) => sum + result.capabilityViolations.length,
          0,
        ),
      };
    }),
  };
}

export function formatComparisonCsv(comparison: BenchmarkComparison): string {
  const header = [
    "mode",
    "modeLabel",
    "totalRuns",
    "totalPapers",
    "agentFinishedRuns",
    "timeLimitRuns",
    "infrastructureFailureRuns",
    "scoreableRuns",
    "replacementRuns",
    "totalModelRefinements",
    "averageModelRefinements",
    "totalDurationMs",
    "averageDurationMs",
    "turnCount",
    "attemptCount",
    "agentWallTimeMs",
    "morpheusSimulationTimeMs",
    "agentAnalysisTimeMs",
    "hostMorpheusRunTimeMs",
    "hostTechnicalEvaluationTimeMs",
    "inputTokens",
    "cachedInputTokens",
    "cacheWriteInputTokens",
    "outputTokens",
    "reasoningOutputTokens",
    "totalTokens",
    "averageTechnicalScore",
    "averageReproductionScore",
    "averageBiologicalScore",
    "capabilityViolationCount",
  ];
  const rows = comparison.modes.map((mode) =>
    [
      mode.mode,
      csvEscape(mode.modeLabel),
      mode.totalRuns,
      mode.totalPapers,
      mode.agentFinishedRuns,
      mode.timeLimitRuns,
      mode.infrastructureFailureRuns,
      mode.scoreableRuns,
      mode.replacementRuns,
      mode.totalModelRefinements,
      mode.averageModelRefinements,
      mode.totalDurationMs,
      mode.averageDurationMs,
      mode.diagnostics.turnCount,
      mode.diagnostics.attemptCount,
      mode.diagnostics.agentWallTimeMs,
      mode.diagnostics.morpheusSimulationTimeMs,
      mode.diagnostics.agentAnalysisTimeMs,
      mode.diagnostics.hostMorpheusRunTimeMs,
      mode.diagnostics.hostTechnicalEvaluationTimeMs,
      mode.diagnostics.tokens.input,
      mode.diagnostics.tokens.cachedInput,
      mode.diagnostics.tokens.cacheWriteInput,
      mode.diagnostics.tokens.output,
      mode.diagnostics.tokens.reasoningOutput,
      mode.diagnostics.tokens.total,
      mode.averageTechnicalScore,
      mode.averageReproductionScore,
      mode.averageBiologicalScore,
      mode.capabilityViolationCount,
    ].join(","),
  );
  return `${header.join(",")}\n${rows.join("\n")}\n`;
}

function csvEscape(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replaceAll('"', '""')}"` : value;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}
