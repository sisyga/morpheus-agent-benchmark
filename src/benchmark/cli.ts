import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { applyCliOverrides, loadConfig, loadConfigForRecoverRun } from "./config.js";
import { runBiologicalScoringForBenchmark } from "./biological-scoring.js";
import { ALL_BENCHMARK_MODES, parseBenchmarkModeId } from "./modes.js";
import { appendProgressLogIfParentExists } from "./progress-log.js";
import { resolveBenchmarkPythonExecutable } from "./python-env.js";
import { BenchmarkRunner, type BenchmarkRecoveryOptions } from "./runner.js";
import type { BenchmarkConfig, BenchmarkSummary } from "./types.js";

/* node:coverage disable */
export type ParsedCliArgs = {
  overrides: Partial<BenchmarkConfig>;
  configPath?: string;
  maxPapers?: number;
  startAtPaper?: string;
  recoverRunDir?: string;
  combineRunDirs?: string[];
  combinedRunDir?: string;
  runAnalysis: boolean;
  scoreBiological: boolean;
  skipScoredAttempts: boolean;
  help: boolean;
};
/* node:coverage enable */

export function parseCliArgs(args: string[]): ParsedCliArgs {
  const overrides: Partial<BenchmarkConfig> = {};
  let configPath: string | undefined;
  let maxPapers: number | undefined;
  let startAtPaper: string | undefined;
  let recoverRunDir: string | undefined;
  let combineRunDirs: string[] | undefined;
  let combinedRunDir: string | undefined;
  let runAnalysis = true;
  let scoreBiological = false;
  let skipScoredAttempts = false;

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    const next = args[index + 1];
    switch (arg) {
      case "--config":
        configPath = requireValue(arg, next);
        index += 1;
        break;
      case "--benchmark-mode":
        overrides.benchmarkModes = [
          ...(overrides.benchmarkModes ?? []),
          parseBenchmarkModeId(requireValue(arg, next)),
        ];
        index += 1;
        break;
      case "--all-benchmark-modes":
        overrides.benchmarkModes = [...ALL_BENCHMARK_MODES];
        break;
      case "--papers-dir":
        overrides.papersDir = requireValue(arg, next);
        index += 1;
        break;
      case "--results-dir":
        overrides.resultsDir = requireValue(arg, next);
        index += 1;
        break;
      case "--benchmark-focus-dir":
        overrides.benchmarkFocusDir = requireValue(arg, next);
        index += 1;
        break;
      case "--no-benchmark-focus":
        overrides.benchmarkFocusDir = null;
        break;
      case "--model":
        overrides.model = requireValue(arg, next);
        index += 1;
        break;
      case "--reasoning-effort":
        overrides.reasoningEffort = requireValue(arg, next) as BenchmarkConfig["reasoningEffort"];
        index += 1;
        break;
      case "--total-time-limit-minutes":
        overrides.totalTimeLimitMs = parseIntegerArg(arg, next, 1) * 60_000;
        index += 1;
        break;
      case "--finalization-reserve-minutes":
        overrides.finalizationReserveMs = parseIntegerArg(arg, next, 1) * 60_000;
        index += 1;
        break;
      case "--max-concurrent-jobs":
        overrides.maxConcurrentJobs = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--codex-quota-job-cost-percent": {
        const value = Number(requireValue(arg, next));
        if (!Number.isFinite(value) || value < 0 || value > 100) {
          throw new Error(`${arg} must be a number from 0 to 100 (0 disables the quota guard).`);
        }
        overrides.codexQuotaJobCostPercent = value;
        index += 1;
        break;
      }
      case "--repetitions":
        overrides.benchmarkRepetitions = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--page-render-dpi":
        overrides.pageRenderDpi = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--representative-output-frames":
        overrides.representativeOutputFrames = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--no-codex-quota-fallback":
      case "--codex-quota-fallback-wait-minutes":
      case "--codex-quota-max-retries":
      case "--codex-quota-retry-buffer-seconds":
        throw new Error(
          `${arg} was removed in time_limit_v2: there are no quota waits or retries; an exhausted quota stops the queue, and --recover-run reruns the affected assignments once the quota resets.`,
        );
      case "--codex-windows-sandbox":
        throw new Error(
          `${arg} was removed. Native Windows benchmark runs now use the elevated Windows sandbox automatically.`,
        );
      case "--codex-allow-env":
        overrides.codexAllowedEnvVars = [
          ...(overrides.codexAllowedEnvVars ?? []),
          parseEnvironmentVariableNameArg(arg, next),
        ];
        index += 1;
        break;
      case "--biological-scoring-criteria-path":
        overrides.biologicalScoringCriteriaPath = requireValue(arg, next);
        index += 1;
        break;
      case "--biological-scoring-model":
        overrides.biologicalScoringModel = requireValue(arg, next);
        index += 1;
        break;
      case "--biological-scoring-reasoning-effort":
        overrides.biologicalScoringReasoningEffort = requireValue(arg, next) as BenchmarkConfig["reasoningEffort"];
        index += 1;
        break;
      case "--biological-scoring-max-concurrent-jobs":
        overrides.biologicalScoringMaxConcurrentJobs = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--biological-scoring-turn-timeout-ms":
        overrides.biologicalScoringTurnTimeoutMs = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--bridge-tool-timeout-ms":
        overrides.bridgeToolTimeoutMs = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--morpheus-run-timeout-ms":
        overrides.morpheusRunTimeoutMs = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--morpheus-num-threads":
        overrides.morpheusNumThreads = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--morpheus-xml-schema-path":
        overrides.morpheusXmlSchemaPath = requireValue(arg, next);
        index += 1;
        break;
      case "--max-papers":
        maxPapers = parseIntegerArg(arg, next, 1);
        index += 1;
        break;
      case "--start-at-paper":
        startAtPaper = requireValue(arg, next);
        index += 1;
        break;
      case "--recover-run":
        recoverRunDir = requireValue(arg, next);
        index += 1;
        break;
      case "--no-analysis":
        runAnalysis = false;
        break;
      case "--score-biological":
        scoreBiological = true;
        break;
      case "--skip-scored-attempts":
        skipScoredAttempts = true;
        break;
      case "--combine-runs": {
        const dirs: string[] = [];
        while (args[index + 1] && !args[index + 1].startsWith("--")) {
          dirs.push(args[index + 1]);
          index += 1;
        }
        if (dirs.length < 2) {
          throw new Error("--combine-runs requires at least two benchmark run directories.");
        }
        combineRunDirs = dirs;
        break;
      }
      case "--combined-run-dir":
        combinedRunDir = requireValue(arg, next);
        index += 1;
        break;
      case "--help":
        return {
          overrides,
          configPath,
          maxPapers,
          startAtPaper,
          recoverRunDir,
          combineRunDirs,
          combinedRunDir,
          runAnalysis,
          scoreBiological,
          skipScoredAttempts,
          help: true,
        };
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return {
    overrides,
    configPath,
    maxPapers,
    startAtPaper,
    recoverRunDir,
    combineRunDirs,
    combinedRunDir,
    runAnalysis,
    scoreBiological,
    skipScoredAttempts,
    help: false,
  };
}

/* node:coverage disable */
async function main(args = process.argv.slice(2)): Promise<void> {
  const parsed = parseCliArgs(args);
  if (parsed.help) {
    printHelp();
    return;
  }

  const config = await resolveConfigForCli(parsed);
  const runner = new BenchmarkRunner(config, {
    progress: (message) => console.error(message),
  });
  const summary = await runBenchmarkCommand(
    parsed,
    runner,
    runAnalysisScript,
    async (scoringSummary) => runBiologicalScoringForBenchmark(
      scoringSummary.benchmarkRunDir,
      config,
      (message) => console.error(message),
      undefined,
      { skipScoredAttempts: parsed.skipScoredAttempts },
    ),
    (message) => console.error(message),
  );

  console.log(JSON.stringify(summary, null, 2));
}
/* node:coverage enable */

/* node:coverage disable */
export type BenchmarkCliRunner = {
  run: BenchmarkRunner["run"];
  recoverRun: (benchmarkRunDir: string, options?: BenchmarkRecoveryOptions) => Promise<BenchmarkSummary>;
  combineRuns: BenchmarkRunner["combineRuns"];
};
export type BenchmarkAnalysisRunner = (summary: BenchmarkSummary) => Promise<void>;
export type BenchmarkBiologicalScoringOptions = {
  skipScoredAttempts?: boolean;
};
export type BenchmarkBiologicalScoringRunner = (
  summary: BenchmarkSummary,
  options?: BenchmarkBiologicalScoringOptions,
) => Promise<BenchmarkSummary>;
export type BenchmarkCommandProgressReporter = (message: string) => void;
/* node:coverage enable */

export async function runBenchmarkCommand(
  parsed: ParsedCliArgs,
  runner: BenchmarkCliRunner,
  runAnalysis: BenchmarkAnalysisRunner = runAnalysisScript,
  runBiologicalScoring: BenchmarkBiologicalScoringRunner = runBiologicalScoringScript,
  progress?: BenchmarkCommandProgressReporter,
): Promise<BenchmarkSummary> {
  let summary: BenchmarkSummary;
  let benchmarkLogPath = parsed.recoverRunDir
    ? path.join(path.resolve(parsed.recoverRunDir), "benchmark.log")
    : parsed.combinedRunDir
      ? path.join(path.resolve(parsed.combinedRunDir), "benchmark.log")
      : null;
  const useBenchmarkLog = (benchmarkRunDir: string) => {
    benchmarkLogPath = path.join(path.resolve(benchmarkRunDir), "benchmark.log");
  };
  const reportProgress = (message: string) => {
    progress?.(message);
    if (benchmarkLogPath) {
      appendProgressLogIfParentExists(benchmarkLogPath, message);
    }
  };

  if (parsed.combineRunDirs) {
    reportProgress(`Combining ${parsed.combineRunDirs.length} benchmark runs.`);
    summary = await runner.combineRuns(parsed.combineRunDirs, parsed.combinedRunDir);
    useBenchmarkLog(summary.benchmarkRunDir);
    reportProgress(`Run combination complete: ${summary.benchmarkRunDir}.`);
  } else if (parsed.recoverRunDir) {
    reportProgress(`Starting recovery for ${parsed.recoverRunDir}.`);
    summary = await runner.recoverRun(parsed.recoverRunDir, { rerunInfrastructureFailures: true });
    useBenchmarkLog(summary.benchmarkRunDir);
    reportProgress(`Recovery complete for ${summary.benchmarkRunDir}: totalRuns=${summary.totalRuns}.`);
  } else {
    const initialSummary = await runner.run(parsed.maxPapers, { startAtPaper: parsed.startAtPaper });
    useBenchmarkLog(initialSummary.benchmarkRunDir);
    reportProgress(`Starting automatic deterministic postprocessing pass for ${initialSummary.benchmarkRunDir}.`);
    summary = await runner.recoverRun(initialSummary.benchmarkRunDir);
    useBenchmarkLog(summary.benchmarkRunDir);
    reportProgress(`Automatic recovery pass complete for ${summary.benchmarkRunDir}: totalRuns=${summary.totalRuns}.`);
  }

  if (parsed.scoreBiological) {
    reportProgress(`Starting biological scoring for ${summary.benchmarkRunDir}.`);
    summary = await runBiologicalScoring(summary, {
      skipScoredAttempts: parsed.skipScoredAttempts,
    });
    useBenchmarkLog(summary.benchmarkRunDir);
    reportProgress(`Biological scoring complete for ${summary.benchmarkRunDir}: averageBiologicalScore=${summary.averageBiologicalScore ?? "n/a"}.`);
  }

  if (parsed.runAnalysis) {
    reportProgress(`Starting analysis for ${summary.benchmarkRunDir}.`);
    try {
      await runAnalysis(summary);
      reportProgress(`Analysis complete for ${summary.benchmarkRunDir}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      reportProgress(`Analysis failed for ${summary.benchmarkRunDir}: ${message}`);
      throw error;
    }
  }
  return summary;
}

/* node:coverage disable */
export async function runAnalysisScript(summary: Pick<BenchmarkSummary, "benchmarkRunDir">): Promise<void> {
  const scriptPath = path.resolve(process.cwd(), "analyze_benchmark.py");
  await new Promise<void>((resolve, reject) => {
    const child = spawn(resolveBenchmarkPythonExecutable(), [scriptPath, summary.benchmarkRunDir], {
      cwd: process.cwd(),
      stdio: "inherit",
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Analysis script failed with exit code ${code ?? "unknown"}.`));
      }
    });
  });
}
/* node:coverage enable */

export async function resolveConfigForCli(parsed: Pick<ParsedCliArgs, "configPath" | "recoverRunDir" | "overrides">): Promise<BenchmarkConfig> {
  const baseConfig = parsed.recoverRunDir
    ? await loadConfigForRecoverRun(parsed.recoverRunDir, parsed.configPath)
    : await loadConfig(parsed.configPath);
  return applyCliOverrides(baseConfig, parsed.overrides);
}

function requireValue(arg: string, value: string | undefined): string {
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${arg}`);
  }
  return value;
}

function parseIntegerArg(arg: string, value: string | undefined, minimum: number): number {
  const raw = requireValue(arg, value);
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(`${arg} must be an integer >= ${minimum}.`);
  }
  return parsed;
}

/* node:coverage disable */
export async function runBiologicalScoringScript(
  summary: Pick<BenchmarkSummary, "benchmarkRunDir">,
  options: BenchmarkBiologicalScoringOptions = {},
): Promise<BenchmarkSummary> {
  const config = await loadConfigForRecoverRun(summary.benchmarkRunDir);
  return runBiologicalScoringForBenchmark(
    summary.benchmarkRunDir,
    config,
    (message) => console.error(message),
    undefined,
    options,
  );
}
/* node:coverage enable */

function parseEnvironmentVariableNameArg(arg: string, value: string | undefined): string {
  const raw = requireValue(arg, value).trim();
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(raw)) {
    throw new Error(`${arg} must be an environment variable name.`);
  }
  return raw;
}

/* node:coverage disable */
function printHelp(): void {
  console.log(
    [
      "Usage: npm run benchmark -- [options]",
      "",
      "Options:",
      "  --config <path>",
      "  --benchmark-mode <python_web|morpheus_cli|morpheus_cli_docs|morpheus_skill|morpheus_mcp> (repeatable)",
      "  --all-benchmark-modes",
      "  --papers-dir <path>",
      "  --results-dir <path>",
      "  --benchmark-focus-dir <path>",
      "  --no-benchmark-focus",
      "  --model <name>",
      "  --reasoning-effort <none|low|medium|high|xhigh|max>",
      "  --total-time-limit-minutes <number>",
      "  --finalization-reserve-minutes <number>",
      "  --max-concurrent-jobs <number>",
      "  --codex-quota-job-cost-percent <number> (0 disables the quota guard)",
      "  --repetitions <number>",
      "  --page-render-dpi <number>",
      "  --representative-output-frames <number>",
      "  --codex-allow-env <NAME> (repeatable)",
      "  --score-biological",
      "  --skip-scored-attempts",
      "  --biological-scoring-criteria-path <path>",
      "  --biological-scoring-model <name>",
      "  --biological-scoring-reasoning-effort <none|low|medium|high|xhigh|max>",
      "  --biological-scoring-max-concurrent-jobs <number>",
      "  --biological-scoring-turn-timeout-ms <number>",
      "  --bridge-tool-timeout-ms <number>",
      "  --morpheus-run-timeout-ms <number>",
      "  --morpheus-num-threads <number>",
      "  --morpheus-xml-schema-path <path>",
      "  --max-papers <number>",
      "  --start-at-paper <pdf filename|stem>",
      "  --recover-run <benchmark run dir>",
      "  --no-analysis",
      "  --combine-runs <benchmark run dir> <benchmark run dir> [...]",
      "  --combined-run-dir <output dir>",
    ].join("\n"),
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
/* node:coverage enable */
