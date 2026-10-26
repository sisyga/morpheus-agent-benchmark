/* node:coverage disable */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { parseCliArgs, resolveConfigForCli, runBenchmarkCommand } from "../src/benchmark/cli.js";
import { loadConfig } from "../src/benchmark/config.js";
import type { BenchmarkSummary } from "../src/benchmark/types.js";

test("parseCliArgs accepts repeatable benchmark modes", () => {
  const parsed = parseCliArgs([
    "--benchmark-mode",
    "python_web",
    "--benchmark-mode",
    "morpheus_cli",
    "--benchmark-mode",
    "morpheus_cli_docs",
    "--max-papers",
    "2",
  ]);

  assert.deepEqual(parsed.overrides.benchmarkModes, ["python_web", "morpheus_cli", "morpheus_cli_docs"]);
  assert.equal(parsed.maxPapers, 2);
});

test("parseCliArgs expands all benchmark modes", () => {
  const parsed = parseCliArgs(["--all-benchmark-modes"]);

  assert.deepEqual(parsed.overrides.benchmarkModes, [
    "python_web",
    "morpheus_cli",
    "morpheus_cli_docs",
    "morpheus_skill",
    "morpheus_mcp",
  ]);
});

test("parseCliArgs parses recovery and paper start options", () => {
  const parsed = parseCliArgs([
    "--recover-run",
    "benchmark_runs/20260508_211543_benchmark",
    "--start-at-paper",
    "9_Luque2023_clean",
  ]);

  assert.equal(parsed.recoverRunDir, "benchmark_runs/20260508_211543_benchmark");
  assert.equal(parsed.startAtPaper, "9_Luque2023_clean");
});

test("parseCliArgs rejects removed continuation and turn flags", () => {
  assert.throws(() => parseCliArgs(["--continue-incomplete"]), /Unknown argument: --continue-incomplete/);
  assert.throws(() => parseCliArgs(["--max-turns", "7"]), /Unknown argument: --max-turns/);
  assert.throws(() => parseCliArgs(["--codex-turn-timeout-ms", "1"]), /Unknown argument/);
  assert.equal(parseCliArgs(["--codex-quota-job-cost-percent", "1.5"]).overrides.codexQuotaJobCostPercent, 1.5);
  assert.equal(parseCliArgs(["--codex-quota-job-cost-percent", "0"]).overrides.codexQuotaJobCostPercent, 0);
  assert.throws(() => parseCliArgs(["--codex-quota-job-cost-percent", "-1"]), /from 0 to 100/);
  assert.throws(() => parseCliArgs(["--no-codex-quota-fallback"]), /no quota waits or retries/);
  assert.throws(() => parseCliArgs(["--codex-quota-max-retries", "2"]), /no quota waits or retries/);
  assert.throws(
    () => parseCliArgs(["--codex-windows-sandbox", "unelevated"]),
    /removed.*elevated Windows sandbox automatically/i,
  );
});

test("parseCliArgs allows disabling post-run analysis", () => {
  const parsed = parseCliArgs(["--no-analysis"]);

  assert.equal(parsed.runAnalysis, false);
});

test("parseCliArgs parses skip-scored-attempts", () => {
  const parsed = parseCliArgs(["--score-biological", "--skip-scored-attempts"]);

  assert.equal(parsed.scoreBiological, true);
  assert.equal(parsed.skipScoredAttempts, true);
});

test("parseCliArgs rejects the removed no-score-workbook option", () => {
  assert.throws(
    () => parseCliArgs(["--score-biological", "--no-score-workbook"]),
    /unknown argument: --no-score-workbook/i,
  );
});

test("parseCliArgs returns help without changing benchmark defaults", () => {
  const parsed = parseCliArgs(["--help"]);

  assert.equal(parsed.help, true);
  assert.equal(parsed.configPath, undefined);
  assert.equal(parsed.maxPapers, undefined);
  assert.equal(parsed.runAnalysis, true);
  assert.equal(parsed.scoreBiological, false);
  assert.deepEqual(parsed.overrides, {});
});

test("parseCliArgs parses path, model, and render overrides", () => {
  const parsed = parseCliArgs([
    "--config",
    "benchmark.local.json",
    "--papers-dir",
    "papers",
    "--results-dir",
    "runs",
    "--benchmark-focus-dir",
    "focus",
    "--model",
    "gpt-5.4",
    "--reasoning-effort",
    "high",
    "--page-render-dpi",
    "180",
    "--representative-output-frames",
    "7",
    "--biological-scoring-criteria-path",
    "criteria.json",
  ]);

  assert.equal(parsed.configPath, "benchmark.local.json");
  assert.equal(parsed.overrides.papersDir, "papers");
  assert.equal(parsed.overrides.resultsDir, "runs");
  assert.equal(parsed.overrides.benchmarkFocusDir, "focus");
  assert.equal(parsed.overrides.model, "gpt-5.4");
  assert.equal(parsed.overrides.reasoningEffort, "high");
  assert.equal(parsed.overrides.pageRenderDpi, 180);
  assert.equal(parsed.overrides.representativeOutputFrames, 7);
  assert.equal(parsed.overrides.biologicalScoringCriteriaPath, "criteria.json");
});

test("parseCliArgs parses disabled benchmark focus", () => {
  const parsed = parseCliArgs(["--no-benchmark-focus"]);

  assert.equal(parsed.overrides.benchmarkFocusDir, null);
});

test("runBenchmarkCommand runs one automatic recovery pass before analysis after normal runs", async () => {
  const calls: string[] = [];
  const progress: string[] = [];
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-cli-progress-log-"));
  const runDir = path.join(root, "run_a");
  await mkdir(runDir, { recursive: true });
  const initialSummary = { benchmarkRunDir: runDir } as BenchmarkSummary;
  const recoveredSummary = { benchmarkRunDir: runDir, totalRuns: 1 } as BenchmarkSummary;
  const runner = {
    async run(maxPapers?: number, options?: { startAtPaper?: string }) {
      calls.push(`run:${maxPapers ?? "all"}:${options?.startAtPaper ?? "first"}`);
      return initialSummary;
    },
    async recoverRun(runDir: string, options?: { rerunInfrastructureFailures?: boolean }) {
      calls.push(`recover:${runDir}:${options?.rerunInfrastructureFailures === true ? "rerun" : "postprocess"}`);
      return recoveredSummary;
    },
    async combineRuns() {
      throw new Error("combineRuns should not be called");
    },
  };

  const summary = await runBenchmarkCommand(
    parseCliArgs(["--max-papers", "2", "--start-at-paper", "03_Carpenter2024"]),
    runner,
    async (analysisSummary) => {
      calls.push(`analysis:${analysisSummary.benchmarkRunDir}:${analysisSummary.totalRuns}`);
    },
    undefined,
    (message) => progress.push(message),
  );

  assert.equal(summary, recoveredSummary);
  assert.deepEqual(calls, [
    "run:2:03_Carpenter2024",
    `recover:${runDir}:postprocess`,
    `analysis:${runDir}:1`,
  ]);
  assert.ok(progress.some((message) => /Starting automatic deterministic postprocessing pass/.test(message) && message.includes(runDir)));
  assert.ok(progress.some((message) => /Automatic recovery pass complete/.test(message) && /totalRuns=1/.test(message)));
  assert.ok(progress.some((message) => /Starting analysis/.test(message) && message.includes(runDir)));
  assert.ok(progress.some((message) => /Analysis complete/.test(message) && message.includes(runDir)));
  const benchmarkLog = await readFile(path.join(runDir, "benchmark.log"), "utf8");
  assert.match(benchmarkLog, /Starting automatic deterministic postprocessing pass/);
  assert.match(benchmarkLog, /Automatic recovery pass complete/);
  assert.match(benchmarkLog, /Starting analysis/);
  assert.match(benchmarkLog, /Analysis complete/);
});

test("runBenchmarkCommand skips analysis when disabled", async () => {
  const calls: string[] = [];
  const summary = { benchmarkRunDir: "benchmark_runs/run_a" } as BenchmarkSummary;
  const runner = {
    async run() {
      calls.push("run");
      return summary;
    },
    async recoverRun() {
      calls.push("recover");
      return summary;
    },
    async combineRuns() {
      throw new Error("combineRuns should not be called");
    },
  };

  await runBenchmarkCommand(parseCliArgs(["--no-analysis"]), runner, async () => {
    calls.push("analysis");
  });

  assert.deepEqual(calls, ["run", "recover"]);
});

test("runBenchmarkCommand logs analysis failures before rethrowing", async () => {
  const progress: string[] = [];
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-cli-analysis-log-"));
  const runDir = path.join(root, "run_a");
  await mkdir(runDir, { recursive: true });
  const summary = { benchmarkRunDir: runDir } as BenchmarkSummary;
  const runner = {
    async run() {
      return summary;
    },
    async recoverRun() {
      return summary;
    },
    async combineRuns() {
      throw new Error("combineRuns should not be called");
    },
  };

  await assert.rejects(
    () => runBenchmarkCommand(
      parseCliArgs([]),
      runner,
      async () => {
        throw new Error("disk full while writing analysis figure");
      },
      undefined,
      (message) => progress.push(message),
    ),
    /disk full while writing analysis figure/,
  );

  assert.ok(progress.some((message) => /Analysis failed/.test(message) && /disk full/.test(message)));
  const benchmarkLog = await readFile(path.join(runDir, "benchmark.log"), "utf8");
  assert.match(benchmarkLog, /Analysis failed/);
  assert.match(benchmarkLog, /disk full while writing analysis figure/);
});

test("runBenchmarkCommand lets explicit recovery rerun eligible infrastructure failures", async () => {
  const calls: string[] = [];
  const summary = { benchmarkRunDir: "benchmark_runs/run_a" } as BenchmarkSummary;
  const runner = {
    async run() {
      throw new Error("run should not be called");
    },
    async recoverRun(runDir: string, options?: { rerunInfrastructureFailures?: boolean }) {
      calls.push(`recover:${runDir}:${options?.rerunInfrastructureFailures === true ? "rerun" : "postprocess"}`);
      return summary;
    },
    async combineRuns() {
      throw new Error("combineRuns should not be called");
    },
  };

  await runBenchmarkCommand(
    parseCliArgs([
      "--recover-run",
      "benchmark_runs/run_a",
      "--no-analysis",
    ]),
    runner,
  );

  assert.deepEqual(calls, ["recover:benchmark_runs/run_a:rerun"]);
});

test("runBenchmarkCommand combines runs and scores before analysis", async () => {
  const calls: string[] = [];
  const combinedSummary = { benchmarkRunDir: "benchmark_runs/combined", totalRuns: 2 } as BenchmarkSummary;
  const scoredSummary = {
    benchmarkRunDir: "benchmark_runs/combined",
    totalRuns: 2,
    averageBiologicalScore: 0.5,
  } as BenchmarkSummary;
  const runner = {
    async run() {
      throw new Error("run should not be called");
    },
    async recoverRun() {
      throw new Error("recoverRun should not be called");
    },
    async combineRuns(runDirs: string[], combinedRunDir?: string) {
      calls.push(`combine:${runDirs.join(",")}:${combinedRunDir ?? ""}`);
      return combinedSummary;
    },
  };

  const summary = await runBenchmarkCommand(
    parseCliArgs([
      "--combine-runs",
      "benchmark_runs/run_a",
      "benchmark_runs/run_b",
      "--combined-run-dir",
      "benchmark_runs/combined",
      "--score-biological",
      "--skip-scored-attempts",
    ]),
    runner,
    async (analysisSummary) => {
      calls.push(`analysis:${analysisSummary.benchmarkRunDir}:${analysisSummary.averageBiologicalScore}`);
    },
    async (scoringSummary, scoringOptions) => {
      calls.push(`score:${scoringSummary.benchmarkRunDir}:${scoringSummary.totalRuns}:${scoringOptions?.skipScoredAttempts ?? false}`);
      return scoredSummary;
    },
  );

  assert.equal(summary, scoredSummary);
  assert.deepEqual(calls, [
    "combine:benchmark_runs/run_a,benchmark_runs/run_b:benchmark_runs/combined",
    "score:benchmark_runs/combined:2:true",
    "analysis:benchmark_runs/combined:0.5",
  ]);
});

test("resolveConfigForCli uses recovered benchmark config as recover-run defaults", async () => {
  const baseConfig = await loadConfig();
  const runDir = await mkdtemp(path.join(os.tmpdir(), "morpheus-recover-config-"));
  await writeFile(
    path.join(runDir, "benchmark_summary.json"),
    JSON.stringify({
      config: {
        ...baseConfig,
        benchmarkModes: ["morpheus_cli", "morpheus_mcp"],
        maxConcurrentJobs: 5,
        reasoningEffort: "xhigh",
      },
      results: [],
    }),
    "utf8",
  );

  const config = await resolveConfigForCli(parseCliArgs(["--recover-run", runDir]));

  assert.deepEqual(config.benchmarkModes, ["morpheus_cli", "morpheus_mcp"]);
  assert.equal(config.maxConcurrentJobs, 5);
  assert.equal(config.reasoningEffort, "xhigh");
});

test("resolveConfigForCli lets explicit recover-run CLI overrides beat recovered config", async () => {
  const baseConfig = await loadConfig();
  const runDir = await mkdtemp(path.join(os.tmpdir(), "morpheus-recover-config-"));
  await writeFile(
    path.join(runDir, "benchmark_summary.json"),
    JSON.stringify({
      config: {
        ...baseConfig,
        benchmarkModes: ["morpheus_cli"],
      },
      results: [],
    }),
    "utf8",
  );

  const config = await resolveConfigForCli(
    parseCliArgs(["--recover-run", runDir, "--benchmark-mode", "morpheus_mcp"]),
  );

  assert.deepEqual(config.benchmarkModes, ["morpheus_mcp"]);
});

test("parseCliArgs parses benchmark run combination options", () => {
  const parsed = parseCliArgs([
    "--combine-runs",
    "benchmark_runs/run_a",
    "benchmark_runs/run_b",
    "--combined-run-dir",
    "benchmark_runs",
  ]);

  assert.deepEqual(parsed.combineRunDirs, ["benchmark_runs/run_a", "benchmark_runs/run_b"]);
  assert.equal(parsed.combinedRunDir, "benchmark_runs");
});

test("parseCliArgs rejects run combination without at least two runs", () => {
  assert.throws(() => parseCliArgs(["--combine-runs"]), /--combine-runs requires at least two benchmark run directories/);
  assert.throws(
    () => parseCliArgs(["--combine-runs", "benchmark_runs/run_a"]),
    /--combine-runs requires at least two benchmark run directories/,
  );
});

test("parseCliArgs rejects unknown benchmark modes", () => {
  assert.throws(
    () => parseCliArgs(["--benchmark-mode", "not_a_mode"]),
    /Unknown benchmark mode: not_a_mode/,
  );
});

test("parseCliArgs parses reliability and timeout overrides", () => {
  const parsed = parseCliArgs([
    "--max-concurrent-jobs",
    "2",
    "--repetitions",
    "3",
    "--total-time-limit-minutes",
    "300",
    "--finalization-reserve-minutes",
    "10",
    "--codex-allow-env",
    "BENCHMARK_SAFE_FLAG",
    "--codex-allow-env",
    "MORPHEUS_LICENSE_PATH",
    "--bridge-tool-timeout-ms",
    "1000",
    "--morpheus-run-timeout-ms",
    "2000",
    "--morpheus-num-threads",
    "4",
    "--morpheus-xml-schema-path",
    "src/benchmark/MorpheusML.xsd",
  ]);

  assert.equal(parsed.overrides.maxConcurrentJobs, 2);
  assert.equal(parsed.overrides.benchmarkRepetitions, 3);
  assert.equal(parsed.overrides.totalTimeLimitMs, 18_000_000);
  assert.equal(parsed.overrides.finalizationReserveMs, 600_000);
  assert.deepEqual(parsed.overrides.codexAllowedEnvVars, ["BENCHMARK_SAFE_FLAG", "MORPHEUS_LICENSE_PATH"]);
  assert.equal(parsed.overrides.bridgeToolTimeoutMs, 1000);
  assert.equal(parsed.overrides.morpheusRunTimeoutMs, 2000);
  assert.equal(parsed.overrides.morpheusNumThreads, 4);
  assert.equal(parsed.overrides.morpheusXmlSchemaPath, "src/benchmark/MorpheusML.xsd");
});

test("parseCliArgs parses biological scoring overrides", () => {
  const parsed = parseCliArgs([
    "--biological-scoring-model",
    "gpt-5.4-mini",
    "--biological-scoring-reasoning-effort",
    "low",
    "--biological-scoring-max-concurrent-jobs",
    "3",
    "--biological-scoring-turn-timeout-ms",
    "1234",
  ]);

  assert.equal(parsed.overrides.biologicalScoringModel, "gpt-5.4-mini");
  assert.equal(parsed.overrides.biologicalScoringReasoningEffort, "low");
  assert.equal(parsed.overrides.biologicalScoringMaxConcurrentJobs, 3);
  assert.equal(parsed.overrides.biologicalScoringTurnTimeoutMs, 1234);
});

test("parseCliArgs rejects invalid numeric values", () => {
  assert.throws(
    () => parseCliArgs(["--max-concurrent-jobs", "0"]),
    /--max-concurrent-jobs must be an integer >= 1/,
  );
  assert.throws(() => parseCliArgs(["--repetitions", "0"]), /--repetitions must be an integer >= 1/);
  assert.throws(() => parseCliArgs(["--max-papers", "many"]), /--max-papers must be an integer >= 1/);
  assert.throws(
    () => parseCliArgs(["--bridge-tool-timeout-ms", "-1"]),
    /--bridge-tool-timeout-ms must be an integer >= 1/,
  );
  assert.throws(
    () => parseCliArgs(["--morpheus-num-threads", "0"]),
    /--morpheus-num-threads must be an integer >= 1/,
  );
  assert.throws(
    () => parseCliArgs(["--codex-allow-env", "bad-name"]),
    /--codex-allow-env must be an environment variable name/,
  );
  assert.throws(() => parseCliArgs(["--config"]), /Missing value for --config/);
  assert.throws(() => parseCliArgs(["--model", "--max-concurrent-jobs"]), /Missing value for --model/);
  assert.throws(
    () => parseCliArgs(["--representative-output-frames", "0"]),
    /--representative-output-frames must be an integer >= 1/,
  );
  assert.throws(
    () => parseCliArgs(["--biological-scoring-image-limit", "1"]),
    /Unknown argument/,
  );
});
