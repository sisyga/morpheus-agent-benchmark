import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { normalizeBenchmarkModes } from "./modes.js";
import type { BenchmarkConfig, BenchmarkSummary } from "./types.js";

const DEFAULT_CONFIG_PATH = "benchmark.config.json";
const MORPHEUS_RETURN_CUSHION_MS = 120_000;

export async function loadConfig(configPath?: string): Promise<BenchmarkConfig> {
  const resolvedPath = path.resolve(process.cwd(), configPath ?? DEFAULT_CONFIG_PATH);
  const raw = await readFile(resolvedPath, "utf8");
  const parsed = JSON.parse(raw) as Partial<BenchmarkConfig>;

  const config: BenchmarkConfig = {
    papersDir: path.resolve(process.cwd(), parsed.papersDir ?? "benchmark_papers"),
    resultsDir: path.resolve(process.cwd(), parsed.resultsDir ?? "benchmark_runs"),
    benchmarkFocusDir:
      parsed.benchmarkFocusDir === null
        ? null
        : path.resolve(process.cwd(), parsed.benchmarkFocusDir ?? "benchmark_focus"),
    benchmarkModes: normalizeBenchmarkModes(parsed.benchmarkModes),
    benchmarkRepetitions: integerAtLeast(parsed.benchmarkRepetitions ?? 1, "benchmarkRepetitions", 1),
    model: parsed.model ?? "gpt-6.1-sol",
    reasoningEffort: parsed.reasoningEffort ?? "max",
    totalTimeLimitMs: integerAtLeast(parsed.totalTimeLimitMs ?? 14_400_000, "totalTimeLimitMs", 1),
    finalizationReserveMs: integerAtLeast(
      parsed.finalizationReserveMs ?? 600_000,
      "finalizationReserveMs",
      1,
    ),
    maxConcurrentJobs: integerAtLeast(parsed.maxConcurrentJobs ?? 1, "maxConcurrentJobs", 1),
    codexQuotaJobCostPercent: parsed.codexQuotaJobCostPercent ?? 2,
    pageRenderDpi: integerAtLeast(parsed.pageRenderDpi ?? 150, "pageRenderDpi", 1),
    representativeOutputFrames: integerAtLeast(
      parsed.representativeOutputFrames ?? 5,
      "representativeOutputFrames",
      1,
    ),
    codexApprovalPolicy: parsed.codexApprovalPolicy ?? "never",
    codexAllowedEnvVars: environmentVariableNameList(parsed.codexAllowedEnvVars ?? [], "codexAllowedEnvVars"),
    biologicalScoringCriteriaPath: path.resolve(
      process.cwd(),
      parsed.biologicalScoringCriteriaPath ?? "biological_scoring_criteria.json",
    ),
    biologicalScoringModel: parsed.biologicalScoringModel ?? "gpt-6-luna",
    biologicalScoringReasoningEffort: reasoningEffortValue(
      parsed.biologicalScoringReasoningEffort ?? "high",
      "biologicalScoringReasoningEffort",
    ),
    biologicalScoringMaxConcurrentJobs: integerAtLeast(
      parsed.biologicalScoringMaxConcurrentJobs ?? 1,
      "biologicalScoringMaxConcurrentJobs",
      1,
    ),
    biologicalScoringTurnTimeoutMs: integerAtLeast(
      parsed.biologicalScoringTurnTimeoutMs ?? 5_400_000,
      "biologicalScoringTurnTimeoutMs",
      1,
    ),
    mcpCommand: parsed.mcpCommand ?? ["python", "server.py"],
    mcpToolTimeoutMs: integerAtLeast(parsed.mcpToolTimeoutMs ?? 3_720_000, "mcpToolTimeoutMs", 1),
    bridgeToolTimeoutMs: integerAtLeast(
      parsed.bridgeToolTimeoutMs ?? 3_720_000,
      "bridgeToolTimeoutMs",
      1,
    ),
    morpheusRunTimeoutMs: integerAtLeast(
      parsed.morpheusRunTimeoutMs ?? 3_600_000,
      "morpheusRunTimeoutMs",
      1,
    ),
    morpheusNumThreads: nullableIntegerAtLeast(
      parsed.morpheusNumThreads ?? null,
      "morpheusNumThreads",
      1,
    ),
    morpheusXmlSchemaPath: path.resolve(
      process.cwd(),
      parsed.morpheusXmlSchemaPath ?? "src/benchmark/MorpheusML.xsd",
    ),
    skillPaths: (parsed.skillPaths ?? [".agents/skills/morpheus/SKILL.md"]).map((skillPath) =>
      path.resolve(process.cwd(), skillPath),
    ),
  };

  const validated = validateBenchmarkConfig(config);
  await mkdir(validated.resultsDir, { recursive: true });
  return validated;
}

export async function loadConfigForRecoverRun(
  benchmarkRunDir: string,
  configPath?: string,
): Promise<BenchmarkConfig> {
  const fallbackConfig = await loadConfig(configPath);
  const resolvedRunDir = path.join(path.resolve(process.cwd(), benchmarkRunDir));
  let recovered: Partial<BenchmarkSummary> | { config?: Partial<BenchmarkConfig> } = {};
  for (const fileName of ["benchmark_summary.json", "benchmark_recovery.json"]) {
    try {
      recovered = JSON.parse(await readFile(path.join(resolvedRunDir, fileName), "utf8")) as typeof recovered;
      if (recovered.config) {
        break;
      }
    } catch {
      // Try the other persisted v2 configuration source.
    }
  }
  if (!recovered.config) {
    return fallbackConfig;
  }
  let recoveredConfig = recovered.config;
  const isCurrentV2 = "benchmarkProtocol" in recovered
    && recovered.benchmarkProtocol === "time_limit_v2"
    && "artifactSchemaVersion" in recovered
    && recovered.artifactSchemaVersion === 2;
  const morpheusRunTimeoutMs = recoveredConfig.morpheusRunTimeoutMs ?? fallbackConfig.morpheusRunTimeoutMs;
  if (!isCurrentV2 && Number.isInteger(morpheusRunTimeoutMs) && morpheusRunTimeoutMs >= 1) {
    const minimumOuterTimeoutMs = morpheusRunTimeoutMs + MORPHEUS_RETURN_CUSHION_MS;
    const mcpToolTimeoutMs = recoveredConfig.mcpToolTimeoutMs ?? fallbackConfig.mcpToolTimeoutMs;
    const bridgeToolTimeoutMs = recoveredConfig.bridgeToolTimeoutMs ?? fallbackConfig.bridgeToolTimeoutMs;
    recoveredConfig = {
      ...recoveredConfig,
      mcpToolTimeoutMs: Number.isInteger(mcpToolTimeoutMs) && mcpToolTimeoutMs >= 1
        ? Math.max(mcpToolTimeoutMs, minimumOuterTimeoutMs)
        : mcpToolTimeoutMs,
      bridgeToolTimeoutMs: Number.isInteger(bridgeToolTimeoutMs) && bridgeToolTimeoutMs >= 1
        ? Math.max(bridgeToolTimeoutMs, minimumOuterTimeoutMs)
        : bridgeToolTimeoutMs,
    };
  }
  return applyCliOverrides(fallbackConfig, recoveredConfig);
}

export function applyCliOverrides(
  config: BenchmarkConfig,
  overrides: Partial<BenchmarkConfig>,
): BenchmarkConfig {
  const { codexWindowsSandboxMode: _removedWindowsSandboxMode, ...supportedOverrides } = overrides as Partial<BenchmarkConfig> & {
    codexWindowsSandboxMode?: unknown;
  };
  const merged = {
    ...config,
    ...supportedOverrides,
    papersDir: overrides.papersDir ? path.resolve(process.cwd(), overrides.papersDir) : config.papersDir,
    resultsDir: overrides.resultsDir ? path.resolve(process.cwd(), overrides.resultsDir) : config.resultsDir,
    benchmarkFocusDir:
      overrides.benchmarkFocusDir === undefined
        ? config.benchmarkFocusDir
        : overrides.benchmarkFocusDir === null
          ? null
          : path.resolve(process.cwd(), overrides.benchmarkFocusDir),
    skillPaths: overrides.skillPaths
      ? overrides.skillPaths.map((skillPath) => path.resolve(process.cwd(), skillPath))
      : config.skillPaths,
    biologicalScoringCriteriaPath: overrides.biologicalScoringCriteriaPath
      ? path.resolve(process.cwd(), overrides.biologicalScoringCriteriaPath)
      : config.biologicalScoringCriteriaPath,
    morpheusXmlSchemaPath: overrides.morpheusXmlSchemaPath
      ? path.resolve(process.cwd(), overrides.morpheusXmlSchemaPath)
      : config.morpheusXmlSchemaPath,
    benchmarkModes: overrides.benchmarkModes
      ? normalizeBenchmarkModes(overrides.benchmarkModes)
      : config.benchmarkModes,
  };
  return validateBenchmarkConfig(merged);
}

function validateBenchmarkConfig(config: BenchmarkConfig): BenchmarkConfig {
  const validated = {
    ...config,
    reasoningEffort: reasoningEffortValue(config.reasoningEffort, "reasoningEffort"),
    totalTimeLimitMs: integerAtLeast(config.totalTimeLimitMs, "totalTimeLimitMs", 1),
    finalizationReserveMs: integerAtLeast(
      config.finalizationReserveMs,
      "finalizationReserveMs",
      1,
    ),
    maxConcurrentJobs: integerAtLeast(config.maxConcurrentJobs, "maxConcurrentJobs", 1),
    codexQuotaJobCostPercent: percentValue(config.codexQuotaJobCostPercent, "codexQuotaJobCostPercent"),
    benchmarkRepetitions: integerAtLeast(config.benchmarkRepetitions, "benchmarkRepetitions", 1),
    pageRenderDpi: integerAtLeast(config.pageRenderDpi, "pageRenderDpi", 1),
    representativeOutputFrames: integerAtLeast(
      config.representativeOutputFrames,
      "representativeOutputFrames",
      1,
    ),
    codexAllowedEnvVars: environmentVariableNameList(config.codexAllowedEnvVars, "codexAllowedEnvVars"),
    biologicalScoringReasoningEffort: reasoningEffortValue(
      config.biologicalScoringReasoningEffort,
      "biologicalScoringReasoningEffort",
    ),
    biologicalScoringMaxConcurrentJobs: integerAtLeast(
      config.biologicalScoringMaxConcurrentJobs,
      "biologicalScoringMaxConcurrentJobs",
      1,
    ),
    biologicalScoringTurnTimeoutMs: integerAtLeast(
      config.biologicalScoringTurnTimeoutMs,
      "biologicalScoringTurnTimeoutMs",
      1,
    ),
    mcpToolTimeoutMs: integerAtLeast(config.mcpToolTimeoutMs, "mcpToolTimeoutMs", 1),
    bridgeToolTimeoutMs: integerAtLeast(config.bridgeToolTimeoutMs, "bridgeToolTimeoutMs", 1),
    morpheusRunTimeoutMs: integerAtLeast(config.morpheusRunTimeoutMs, "morpheusRunTimeoutMs", 1),
    morpheusNumThreads: nullableIntegerAtLeast(config.morpheusNumThreads, "morpheusNumThreads", 1),
  };
  if (validated.totalTimeLimitMs <= validated.finalizationReserveMs) {
    throw new Error("totalTimeLimitMs must be greater than finalizationReserveMs.");
  }
  const minimumOuterTimeoutMs = validated.morpheusRunTimeoutMs + MORPHEUS_RETURN_CUSHION_MS;
  if (validated.mcpToolTimeoutMs < minimumOuterTimeoutMs) {
    throw new Error(
      `mcpToolTimeoutMs must be at least morpheusRunTimeoutMs + ${MORPHEUS_RETURN_CUSHION_MS}.`,
    );
  }
  if (validated.bridgeToolTimeoutMs < minimumOuterTimeoutMs) {
    throw new Error(
      `bridgeToolTimeoutMs must be at least morpheusRunTimeoutMs + ${MORPHEUS_RETURN_CUSHION_MS}.`,
    );
  }
  return validated;
}

function percentValue(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
    throw new Error(`${name} must be a number from 0 to 100.`);
  }
  return value;
}

export function reasoningEffortValue(value: unknown, name: string): BenchmarkConfig["reasoningEffort"] {
  if (
    value !== "none" &&
    value !== "minimal" &&
    value !== "low" &&
    value !== "medium" &&
    value !== "high" &&
    value !== "xhigh" &&
    value !== "max"
  ) {
    throw new Error(`${name} must be "none", "minimal" (legacy), "low", "medium", "high", "xhigh", or "max".`);
  }
  return value;
}

function environmentVariableNameList(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array of environment variable names.`);
  }

  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const entry of value) {
    if (typeof entry !== "string") {
      throw new Error(`${name} entries must be environment variable names.`);
    }
    const envVarName = entry.trim();
    if (!isEnvironmentVariableName(envVarName)) {
      throw new Error(`${name} entries must be environment variable names.`);
    }
    const seenKey = envVarName.toLowerCase();
    if (!seen.has(seenKey)) {
      normalized.push(envVarName);
      seen.add(seenKey);
    }
  }
  return normalized;
}

function isEnvironmentVariableName(value: string): boolean {
  return /^[A-Za-z_][A-Za-z0-9_]*$/.test(value);
}

function integerAtLeast(value: unknown, name: string, minimum: number): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) {
    throw new Error(`${name} must be an integer >= ${minimum}.`);
  }
  return value;
}

function nullableIntegerAtLeast(value: unknown, name: string, minimum: number): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== "number" || !Number.isInteger(value) || value < minimum) {
    throw new Error(`${name} must be null or an integer >= ${minimum}.`);
  }
  return value;
}
