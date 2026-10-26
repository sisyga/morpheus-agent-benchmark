/* node:coverage disable */
import assert from "node:assert/strict";
import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { applyCliOverrides, loadConfig, loadConfigForRecoverRun } from "../src/benchmark/config.js";

test("loadConfig loads and validates the checked-in benchmark config", async () => {
  const config = await loadConfig();

  assert.ok(config.benchmarkModes.length > 0);
  for (const configPath of [config.papersDir, config.resultsDir, config.morpheusXmlSchemaPath, ...config.skillPaths]) {
    assert.ok(path.isAbsolute(configPath), configPath);
  }
  assert.ok(config.benchmarkFocusDir === null || path.isAbsolute(config.benchmarkFocusDir));
  assert.equal("maxTurnsPerPaper" in config, false);
  assert.equal("codexTurnTimeoutMs" in config, false);
  assert.equal("codexWindowsSandboxMode" in config, false);
});

test("applyCliOverrides resolves local path overrides", async () => {
  const config = await loadConfig();
  const overridden = applyCliOverrides(config, {
    papersDir: "alt_papers",
    resultsDir: "alt_results",
    benchmarkFocusDir: "alt_focus",
    benchmarkModes: ["python_web", "morpheus_cli"],
  });

  assert.ok(overridden.papersDir.endsWith("alt_papers"));
  assert.ok(overridden.resultsDir.endsWith("alt_results"));
  assert.ok(overridden.benchmarkFocusDir?.endsWith("alt_focus"));
  assert.deepEqual(overridden.benchmarkModes, ["python_web", "morpheus_cli"]);
  assert.equal(overridden.model, config.model);
});

test("applyCliOverrides accepts explicit Codex env allowlist overrides", async () => {
  const config = await loadConfig();
  const overridden = applyCliOverrides(config, {
    codexAllowedEnvVars: ["BENCHMARK_SAFE_FLAG", "MORPHEUS_LICENSE_PATH"],
  });

  assert.deepEqual(overridden.codexAllowedEnvVars, ["BENCHMARK_SAFE_FLAG", "MORPHEUS_LICENSE_PATH"]);
});

test("applyCliOverrides rejects invalid numeric values", async () => {
  const config = await loadConfig();

  assert.equal(config.codexQuotaJobCostPercent, 2);
  assert.throws(() => applyCliOverrides(config, { codexQuotaJobCostPercent: 101 }), /codexQuotaJobCostPercent must be a number from 0 to 100/);
  assert.throws(
    () => applyCliOverrides(config, { maxConcurrentJobs: 0 }),
    /maxConcurrentJobs must be an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, { benchmarkRepetitions: 0 }),
    /benchmarkRepetitions must be an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, { morpheusRunTimeoutMs: -1 }),
    /morpheusRunTimeoutMs must be an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, { morpheusNumThreads: 0 }),
    /morpheusNumThreads must be null or an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, {
      totalTimeLimitMs: 600_000,
      finalizationReserveMs: 600_000,
    }),
    /totalTimeLimitMs must be greater than finalizationReserveMs/,
  );
  assert.throws(
    () => applyCliOverrides(config, { mcpToolTimeoutMs: 3_600_000 }),
    /mcpToolTimeoutMs must be at least morpheusRunTimeoutMs \+ 120000/,
  );
  assert.throws(
    () => applyCliOverrides(config, { bridgeToolTimeoutMs: 3_600_000 }),
    /bridgeToolTimeoutMs must be at least morpheusRunTimeoutMs \+ 120000/,
  );
  assert.throws(
    () => applyCliOverrides(config, { codexAllowedEnvVars: ["GOOD_NAME", "bad-name"] as any }),
    /codexAllowedEnvVars entries must be environment variable names/,
  );
});

test("applyCliOverrides ignores the removed Windows sandbox field in recovered configs", async () => {
  const config = await loadConfig();
  const overridden = applyCliOverrides(config, {
    codexWindowsSandboxMode: "unelevated",
  } as any);

  assert.equal("codexWindowsSandboxMode" in overridden, false);
});

test("loadConfig defaults to gpt-6.1-sol xhigh subjects and gpt-6-luna high scorers", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-config-defaults-"));
  const configPath = path.join(root, "benchmark.config.json");
  await writeFile(configPath, "{}", "utf8");
  const expected = {
    model: "gpt-6.1-sol",
    reasoningEffort: "xhigh",
    biologicalScoringModel: "gpt-6-luna",
    biologicalScoringReasoningEffort: "high",
  };
  const pick = (config: Awaited<ReturnType<typeof loadConfig>>) => ({
    model: config.model,
    reasoningEffort: config.reasoningEffort,
    biologicalScoringModel: config.biologicalScoringModel,
    biologicalScoringReasoningEffort: config.biologicalScoringReasoningEffort,
  });

  assert.deepEqual(pick(await loadConfig(configPath)), expected);
  assert.deepEqual(pick(await loadConfig()), expected);
});

test("loadConfig handles nullable focus and biological scoring timeout fallback", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-config-"));
  const configPath = path.join(root, "benchmark.config.json");
  await writeFile(
    configPath,
    JSON.stringify({
      benchmarkFocusDir: null,
      biologicalScoringTurnTimeoutMs: 12_345,
      biologicalScoringCriteriaPath: "criteria.json",
      biologicalScoringModel: "score-model",
      biologicalScoringReasoningEffort: "medium",
      biologicalScoringMaxConcurrentJobs: 2,
      morpheusNumThreads: null,
    }),
    "utf8",
  );

  const config = await loadConfig(configPath);

  assert.equal(config.benchmarkFocusDir, null);
  assert.equal(config.biologicalScoringTurnTimeoutMs, 12_345);
  assert.ok(config.biologicalScoringCriteriaPath.endsWith("criteria.json"));
  assert.equal(config.biologicalScoringModel, "score-model");
  assert.equal(config.biologicalScoringReasoningEffort, "medium");
  assert.equal(config.biologicalScoringMaxConcurrentJobs, 2);
  assert.equal(config.morpheusNumThreads, null);
});

test("loadConfig rejects invalid v2 deadline and Morpheus timeout relationships", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-config-invalid-v2-"));
  const deadlinePath = path.join(root, "deadline.json");
  await writeFile(
    deadlinePath,
    JSON.stringify({ totalTimeLimitMs: 600_000, finalizationReserveMs: 600_000 }),
    "utf8",
  );
  await assert.rejects(
    loadConfig(deadlinePath),
    /totalTimeLimitMs must be greater than finalizationReserveMs/,
  );

  const toolPath = path.join(root, "tool.json");
  await writeFile(
    toolPath,
    JSON.stringify({
      morpheusRunTimeoutMs: 3_600_000,
      mcpToolTimeoutMs: 3_600_000,
      bridgeToolTimeoutMs: 3_720_000,
    }),
    "utf8",
  );
  await assert.rejects(
    loadConfig(toolPath),
    /mcpToolTimeoutMs must be at least morpheusRunTimeoutMs \+ 120000/,
  );
});

test("loadConfigForRecoverRun normalizes historical outer timeouts without rewriting the summary", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-config-historical-"));
  const summaryPath = path.join(root, "benchmark_summary.json");
  const summaryJson = JSON.stringify({
    config: {
      morpheusRunTimeoutMs: 3_600_000,
      mcpToolTimeoutMs: 3_600_000,
      bridgeToolTimeoutMs: 3_600_000,
    },
  });
  await writeFile(summaryPath, summaryJson, "utf8");

  const config = await loadConfigForRecoverRun(root);

  assert.equal(config.morpheusRunTimeoutMs, 3_600_000);
  assert.equal(config.mcpToolTimeoutMs, 3_720_000);
  assert.equal(config.bridgeToolTimeoutMs, 3_720_000);
  assert.equal(await readFile(summaryPath, "utf8"), summaryJson);
});

test("loadConfigForRecoverRun keeps current v2 timeout validation strict", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-config-current-v2-"));
  await writeFile(
    path.join(root, "benchmark_summary.json"),
    JSON.stringify({
      artifactSchemaVersion: 2,
      benchmarkProtocol: "time_limit_v2",
      config: {
        morpheusRunTimeoutMs: 3_600_000,
        mcpToolTimeoutMs: 3_600_000,
        bridgeToolTimeoutMs: 3_600_000,
      },
    }),
    "utf8",
  );

  await assert.rejects(
    loadConfigForRecoverRun(root),
    /mcpToolTimeoutMs must be at least morpheusRunTimeoutMs \+ 120000/,
  );
});

test("applyCliOverrides validates biological scoring and env overrides", async () => {
  const config = await loadConfig();

  const overridden = applyCliOverrides(config, {
    biologicalScoringReasoningEffort: "xhigh",
    biologicalScoringMaxConcurrentJobs: 3,
    biologicalScoringTurnTimeoutMs: 10,
    morpheusNumThreads: null,
    codexAllowedEnvVars: [" SAFE_FLAG ", "safe_flag", "OPENAI_API_KEY", "OTHER"],
  } as any);

  assert.equal(overridden.biologicalScoringReasoningEffort, "xhigh");
  assert.equal(overridden.biologicalScoringMaxConcurrentJobs, 3);
  assert.equal(overridden.biologicalScoringTurnTimeoutMs, 10);
  assert.equal(overridden.morpheusNumThreads, null);
  assert.deepEqual(overridden.codexAllowedEnvVars, ["SAFE_FLAG", "OPENAI_API_KEY", "OTHER"]);

  assert.throws(
    () => applyCliOverrides(config, { biologicalScoringReasoningEffort: "extreme" as any }),
    /biologicalScoringReasoningEffort must be "none"/,
  );
  assert.throws(
    () => applyCliOverrides(config, { biologicalScoringMaxConcurrentJobs: 0 }),
    /biologicalScoringMaxConcurrentJobs must be an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, { biologicalScoringTurnTimeoutMs: 0 }),
    /biologicalScoringTurnTimeoutMs must be an integer >= 1/,
  );
  assert.throws(
    () => applyCliOverrides(config, { codexAllowedEnvVars: "SAFE_FLAG" as any }),
    /codexAllowedEnvVars must be an array/,
  );
});

test("applyCliOverrides accepts max reasoning for benchmark and biological scoring agents", async () => {
  const config = await loadConfig();
  const overridden = applyCliOverrides(config, {
    reasoningEffort: "max",
    biologicalScoringReasoningEffort: "max",
  });

  assert.equal(overridden.reasoningEffort, "max");
  assert.equal(overridden.biologicalScoringReasoningEffort, "max");
});

test("applyCliOverrides rejects invalid benchmark reasoning effort", async () => {
  const config = await loadConfig();

  assert.throws(
    () => applyCliOverrides(config, { reasoningEffort: "extreme" as any }),
    /reasoningEffort must be "none"/,
  );
});
