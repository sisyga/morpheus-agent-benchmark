import type { Dirent } from "node:fs";
import { Codex, type ThreadEvent, type ThreadItem, type ThreadOptions, type UserInput } from "@openai/codex-sdk";
import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { buildCodexConfig } from "./codex-config.js";
import { installBenchmarkCodexExecRulesIsolation } from "./codex-exec.js";
import {
  buildBenchmarkCodexEnv,
  buildBenchmarkCodexHomeDir,
  buildBenchmarkThreadOptions,
  buildBenchmarkComparison,
  formatComparisonCsv,
  mapWithConcurrency,
  prepareBenchmarkCodexHome,
  resolveBenchmarkMaxConcurrentJobs,
} from "./runner.js";
import { snapshotCodexHomeTo } from "./workspace.js";
import { hashDirectoryTree, skillSha256ByName } from "./provenance.js";
import { appendProgressLog } from "./progress-log.js";
import { buildBenchmarkPythonEnv, resolveBenchmarkPythonExecutable } from "./python-env.js";
import type {
  BenchmarkConfig,
  BenchmarkSummary,
  PaperRunResult,
  ReasoningEffort,
} from "./types.js";

/* node:coverage disable */
export type BiologicalClauseKind = "numeric" | "qualitative";

export type BiologicalScoringClause = {
  id: string;
  kind: BiologicalClauseKind;
  weight: number;
  description: string;
};

export type BiologicalScoringCriterion = {
  paper_stems: string[];
  normalized_paper_stems: string[];
  target: string;
  scoring_instructions: string;
  clauses: BiologicalScoringClause[];
};

export type BiologicalScoringRegistry = {
  version: number;
  criteriaSha256?: string;
  criteria: BiologicalScoringCriterion[];
  criteriaByPaperStem: Map<string, BiologicalScoringCriterion>;
};

export type BiologicalScoringImage = {
  path: string;
  series: string;
  position: "single" | "early" | "intermediate" | "final";
};

export type BiologicalScoringJob = {
  result: PaperRunResult | Record<string, unknown>;
  criterion: BiologicalScoringCriterion;
  paper: string;
  mode: string;
  repetition: number | null;
  runId: string;
  runDir: string;
  attemptId: string;
  attemptDir: string;
  criteriaVersion: number;
  criteriaSha256?: string;
  attemptIdentity?: string;
  scoringImages?: BiologicalScoringImage[];
};

export type BiologicalClauseDecision = {
  id: string;
  passed: boolean;
  observed_value: string;
  evidence: string[];
  rationale: string;
};

export type BiologicalScoringResponse = {
  status: "scored";
  score: number;
  clauses: BiologicalClauseDecision[];
  summary: string;
  limitations: string[];
};

type CollectedScoringTurn = {
  finalResponse: string;
  usage: {
    input_tokens: number;
    cached_input_tokens: number;
    output_tokens: number;
    reasoning_output_tokens?: number;
  } | null;
  events: ThreadEvent[];
  items: ThreadItem[];
  error: string | null;
};

type BiologicalScoringOptions = {
  criteriaPath: string;
  model: string;
  reasoningEffort: ReasoningEffort;
  maxConcurrentJobs: number;
  turnTimeoutMs: number;
};

type BiologicalScoringJobResult = {
  score: number | null;
  path: string | null;
  status: string;
  error?: string;
};

type AutomaticBiologicalScoreOutcome = {
  status: "model_failed" | "insufficient_evidence";
  score: 0 | null;
  summary: string;
  limitations: string[];
};

type BiologicalScoringJobRunner = (
  job: BiologicalScoringJob,
  config: BenchmarkConfig,
  options: BiologicalScoringOptions,
) => Promise<BiologicalScoringJobResult>;

type BiologicalScoringRunOptions = {
  skipScoredAttempts?: boolean;
  /** Test hook: skip spawning biological_score_details.py. */
  writeDetailWorkbook?: boolean;
};

type ExistingBiologicalScore = {
  score: number | null;
  path: string;
  status: string;
  attemptId: string | null;
  attemptDir: string | null;
  scorerVersion: number | null;
  criteriaVersion: number | null;
  scorerModel: string | null;
  scorerReasoningEffort: string | null;
  criteriaSha256: string | null;
  attemptIdentity: string | null;
};

export type ParsedBiologicalScoringCliArgs = {
  benchmarkDir: string;
  overrides: Partial<BenchmarkConfig>;
  skipScoredAttempts: boolean;
};
/* node:coverage enable */

export const BIOLOGICAL_SCORING_RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    status: { type: "string", enum: ["scored"] },
    score: { type: "number" },
    clauses: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          passed: { type: "boolean" },
          observed_value: { type: "string" },
          evidence: { type: "array", items: { type: "string" } },
          rationale: { type: "string" },
        },
        required: ["id", "passed", "observed_value", "evidence", "rationale"],
        additionalProperties: false,
      },
    },
    summary: { type: "string" },
    limitations: { type: "array", items: { type: "string" } },
  },
  required: ["status", "score", "clauses", "summary", "limitations"],
  additionalProperties: false,
} as const;

export const BIOLOGICAL_SCORER_VERSION = 8;

export const BIOLOGICAL_SCORE_DETAILS_SCRIPT = "biological_score_details.py";

const BIOLOGICAL_SCORING_IMAGE_LIMIT = 12;
const BIOLOGICAL_SCORING_SERIES_IMAGE_LIMIT = 5;
const BIOLOGICAL_SCORING_IMAGE_EXTENSIONS = new Set([".jpeg", ".jpg", ".png", ".webp"]);

export async function loadBiologicalScoringCriteria(criteriaPath: string): Promise<BiologicalScoringRegistry> {
  const source = await readFile(criteriaPath, "utf8");
  const parsed = JSON.parse(source) as unknown;
  if (!isRecord(parsed)) {
    throw new Error("Biological scoring criteria must be a JSON object.");
  }
  const version = finiteNumber(parsed.version, "version");
  if (!Number.isInteger(version) || version < 1) {
    throw new Error("Biological scoring criteria version must be an integer >= 1.");
  }
  if (!Array.isArray(parsed.criteria)) {
    throw new Error("Biological scoring criteria must include a criteria array.");
  }

  const criteria: BiologicalScoringCriterion[] = [];
  const criteriaByPaperStem = new Map<string, BiologicalScoringCriterion>();
  for (const [criterionIndex, rawCriterion] of parsed.criteria.entries()) {
    const criterion = parseCriterion(rawCriterion, criterionIndex);
    for (const paperStem of criterion.normalized_paper_stems) {
      if (criteriaByPaperStem.has(paperStem)) {
        throw new Error(`Duplicate paper stem in biological scoring criteria: ${paperStem}`);
      }
      criteriaByPaperStem.set(paperStem, criterion);
    }
    criteria.push(criterion);
  }

  return { version, criteriaSha256: sha256(source), criteria, criteriaByPaperStem };
}

export async function discoverBiologicalScoringJobs(
  summary: Pick<BenchmarkSummary, "benchmarkRunDir" | "results"> | Record<string, unknown>,
  registry: BiologicalScoringRegistry,
  options: { benchmarkDir?: string } = {},
): Promise<BiologicalScoringJob[]> {
  const benchmarkDir = path.resolve(
    options.benchmarkDir ?? stringValue((summary as Record<string, unknown>).benchmarkRunDir) ?? process.cwd(),
  );
  const rawResults = Array.isArray((summary as Record<string, unknown>).results)
    ? ((summary as Record<string, unknown>).results as Array<Record<string, unknown>>)
    : [];
  const jobs: BiologicalScoringJob[] = [];

  for (const result of rawResults) {
    const criterion = criterionForResult(result, registry);
    if (!criterion) {
      continue;
    }
    const runDir = await resultRunDir(result, benchmarkDir);
    if (!runDir) {
      continue;
    }
    const attemptDir = await canonicalAttemptDir(runDir);
    if (!attemptDir) {
      continue;
    }
    if (!await hasScoreableOutputArtifacts(attemptDir)) {
      continue;
    }
    const scoringImages = await selectBiologicalScoringImages(attemptDir);
    jobs.push({
      result,
      criterion,
      paper: stringValue(result.paper) ?? portableBasename(stringValue(result.pdfPath) ?? ""),
      mode: stringValue(result.mode) ?? "",
      repetition: numberOrNull(result.repetition),
      runId: stringValue(result.runId) ?? path.basename(runDir),
      runDir,
      attemptId: path.basename(attemptDir),
      attemptDir,
      criteriaVersion: registry.version,
      criteriaSha256: criteriaIdentity(registry),
      attemptIdentity: await hashAttemptArtifacts(attemptDir),
      scoringImages,
    });
  }

  return jobs;
}

async function selectBiologicalScoringImages(attemptDir: string): Promise<BiologicalScoringImage[]> {
  const imagePaths: string[] = [];
  const visit = async (directory: string): Promise<void> => {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => naturalCompare(left.name, right.name))) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(entryPath);
      } else if (entry.isFile() && BIOLOGICAL_SCORING_IMAGE_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
        imagePaths.push(entryPath);
      }
    }
  };
  await visit(attemptDir);

  const grouped = new Map<string, { series: string; paths: string[] }>();
  for (const imagePath of imagePaths) {
    const relativePath = path.relative(attemptDir, imagePath);
    const relativeDirectory = path.dirname(relativePath);
    const stem = path.basename(imagePath, path.extname(imagePath));
    const prefix = stem.replace(/[-+.\d]+$/, "").replace(/[-_]+$/, "") || stem;
    const series = relativeDirectory === "."
      ? prefix
      : path.join(relativeDirectory, prefix).replaceAll(path.sep, "/");
    const key = `${relativeDirectory}\0${prefix}`;
    const group = grouped.get(key) ?? { series, paths: [] };
    group.paths.push(imagePath);
    grouped.set(key, group);
  }

  const series = [...grouped.entries()]
    .sort(([left], [right]) => naturalCompare(left, right))
    .map(([, group]) => ({
      ...group,
      paths: group.paths.sort((left, right) => naturalCompare(left, right)),
    }));
  const quotas = series.map(() => 0);
  let selectedCount = 0;
  while (selectedCount < BIOLOGICAL_SCORING_IMAGE_LIMIT) {
    let added = false;
    for (const [index, group] of series.entries()) {
      const capacity = Math.min(BIOLOGICAL_SCORING_SERIES_IMAGE_LIMIT, group.paths.length);
      if (quotas[index] >= capacity || selectedCount >= BIOLOGICAL_SCORING_IMAGE_LIMIT) {
        continue;
      }
      quotas[index] += 1;
      selectedCount += 1;
      added = true;
    }
    if (!added) {
      break;
    }
  }

  return series.flatMap((group, groupIndex) => {
    const quota = quotas[groupIndex];
    if (quota === 0) {
      return [];
    }
    const indices = quota === 1
      ? [0]
      : Array.from(
        { length: quota },
        (_, index) => Math.round(index * (group.paths.length - 1) / (quota - 1)),
      );
    return indices.map((index): BiologicalScoringImage => ({
      path: group.paths[index],
      series: group.series,
      position: group.paths.length === 1
        ? "single"
        : index === 0
          ? "early"
          : index === group.paths.length - 1
            ? "final"
            : "intermediate",
    }));
  });
}

function naturalCompare(left: string, right: string): number {
  return left.localeCompare(right, "en", { numeric: true, sensitivity: "base" });
}

export function validateBiologicalScoringResponse(
  value: unknown,
  criterion: Pick<BiologicalScoringCriterion, "clauses">,
): BiologicalScoringResponse {
  if (!isRecord(value)) {
    throw new Error("Biological scoring response must be an object.");
  }
  if (value.status !== "scored") {
    throw new Error('Biological scoring response status must be "scored".');
  }
  if (!Array.isArray(value.clauses)) {
    throw new Error("Biological scoring response must include a clauses array.");
  }

  const expectedIds = new Set(criterion.clauses.map((clause) => clause.id));
  const decisions: BiologicalClauseDecision[] = [];
  const seenIds = new Set<string>();
  for (const rawDecision of value.clauses) {
    if (!isRecord(rawDecision)) {
      throw new Error("Biological scoring clause decisions must be objects.");
    }
    const id = requiredString(rawDecision.id, "clause id");
    if (!expectedIds.has(id)) {
      throw new Error(`Unexpected biological scoring clause id: ${id}`);
    }
    if (seenIds.has(id)) {
      throw new Error(`Duplicate biological scoring clause id: ${id}`);
    }
    seenIds.add(id);
    if (typeof rawDecision.passed !== "boolean") {
      throw new Error(`Biological scoring clause ${id} must include a boolean passed value.`);
    }
    if (!Array.isArray(rawDecision.evidence) || rawDecision.evidence.some((entry) => typeof entry !== "string")) {
      throw new Error(`Biological scoring clause ${id} evidence must be an array of strings.`);
    }
    decisions.push({
      id,
      passed: rawDecision.passed,
      observed_value: requiredString(rawDecision.observed_value, `${id}.observed_value`),
      evidence: rawDecision.evidence,
      rationale: requiredString(rawDecision.rationale, `${id}.rationale`),
    });
  }
  for (const expectedId of expectedIds) {
    if (!seenIds.has(expectedId)) {
      throw new Error(`Missing biological scoring clause id: ${expectedId}`);
    }
  }

  const response: BiologicalScoringResponse = {
    status: "scored",
    score: recomputeBiologicalScore(decisions, criterion),
    clauses: decisions,
    summary: requiredString(value.summary, "summary"),
    limitations: Array.isArray(value.limitations)
      ? value.limitations.map((entry) => requiredString(entry, "limitation"))
      : [],
  };
  return response;
}

/**
 * ITT biological score: subject-attributable outcomes count as 0 (``model_failed`` carries 0,
 * ``insufficient_evidence`` is filled with 0); scorer failures and unscored runs are excluded.
 */
export function biologicalIttScore(
  result: Pick<PaperRunResult, "biologicalScore" | "biologicalScoringStatus">,
): number | null {
  if (typeof result.biologicalScore === "number" && Number.isFinite(result.biologicalScore)) {
    return result.biologicalScore;
  }
  return result.biologicalScoringStatus === "insufficient_evidence" ? 0 : null;
}

export function recomputeBiologicalScore(
  decisions: readonly BiologicalClauseDecision[],
  criterion: Pick<BiologicalScoringCriterion, "clauses">,
): number {
  const decisionsById = new Map(decisions.map((decision) => [decision.id, decision]));
  const totalWeight = criterion.clauses.reduce((sum, clause) => sum + clause.weight, 0);
  if (totalWeight <= 0) {
    return 0;
  }
  const passedWeight = criterion.clauses.reduce((sum, clause) => {
    return sum + (decisionsById.get(clause.id)?.passed ? clause.weight : 0);
  }, 0);
  return passedWeight / totalWeight;
}

/* node:coverage disable */
export async function runBiologicalScoringForBenchmark(
  benchmarkDir: string,
  config: BenchmarkConfig,
  progress: (message: string) => void = () => {},
  scoreJob: BiologicalScoringJobRunner = scoreBiologicalJob,
  runOptions: BiologicalScoringRunOptions = {},
): Promise<BenchmarkSummary> {
  const resolvedBenchmarkDir = path.resolve(benchmarkDir);
  const scoringLogPath = path.join(resolvedBenchmarkDir, "scoring.log");
  const reportProgress = (message: string) => {
    progress(message);
    appendProgressLog(scoringLogPath, message);
  };
  const summaryPath = path.join(resolvedBenchmarkDir, "benchmark_summary.json");
  const summary = JSON.parse(await readFile(summaryPath, "utf8")) as BenchmarkSummary;
  const configuredOptions = biologicalScoringOptionsFromConfig(config);
  const maxConcurrentJobs = resolveBenchmarkMaxConcurrentJobs(configuredOptions.maxConcurrentJobs, process.platform);
  const options = { ...configuredOptions, maxConcurrentJobs };
  if (maxConcurrentJobs < configuredOptions.maxConcurrentJobs) {
    reportProgress(
      `Native Windows uses serial biological scoring; requested concurrency=${configuredOptions.maxConcurrentJobs} was reduced to concurrency=${maxConcurrentJobs}. Use Linux or WSL2 for parallel jobs.`,
    );
  }
  const recordedSkillSha256 = skillSha256ByName(summary.benchmarkProvenance).morpheus;
  if (recordedSkillSha256) {
    const scoringSkillSha256 = await hashDirectoryTree(path.dirname(biologicalScoringSkillPath()));
    if (scoringSkillSha256 !== recordedSkillSha256) {
      reportProgress(
        `Warning: scorers will load the current Morpheus skill (${scoringSkillSha256.slice(0, 12)}), which differs from the skill this benchmark ran with (${recordedSkillSha256.slice(0, 12)}).`,
      );
    }
  }
  const registry = await loadBiologicalScoringCriteria(options.criteriaPath);
  const jobs = await discoverBiologicalScoringJobs(summary, registry, {
    benchmarkDir: resolvedBenchmarkDir,
  });
  const jobsByRunId = new Map(jobs.map((job) => [job.runId, job]));
  const scoredResults = new Map<string, BiologicalScoringJobResult>();

  const matchedResults = summary.results.filter((result) => criterionForResult(result, registry));
  let missingArtifactCount = 0;
  let modelFailureCount = 0;
  let skippedExistingCount = 0;
  reportProgress(
    `Biological scoring benchmark ${resolvedBenchmarkDir}: results=${summary.results.length}, matchedResults=${matchedResults.length}, scoreableJobs=${jobs.length}, concurrency=${options.maxConcurrentJobs}.`,
  );
  for (const result of matchedResults) {
    const runId = result.runId;
    if (!jobsByRunId.has(runId)) {
      const runDir = await resultRunDir(result, resolvedBenchmarkDir);
      if (runDir) {
        const attemptDir = await canonicalAttemptDir(runDir);
        const failureReason = attemptDir ? await canonicalAttemptFailureReason(runDir, attemptDir) : null;
        const outcome: AutomaticBiologicalScoreOutcome = failureReason
          ? {
              status: "model_failed",
              score: 0,
              summary: `The canonical Morpheus attempt failed (${failureReason}), so the biological score is zero.`,
              limitations: ["The failed canonical attempt produced no scoreable biological output artifacts."],
            }
          : {
              status: "insufficient_evidence",
              score: null,
              summary: "The canonical attempt does not contain enough output evidence for biological scoring.",
              limitations: ["No canonical scoreable attempt artifacts or explicit execution failure were found."],
            };
        const expectedScore = {
          scorerModel: options.model,
          scorerReasoningEffort: options.reasoningEffort,
          criteriaVersion: registry.version,
          criteriaSha256: criteriaIdentity(registry),
          attemptIdentity: attemptDir ? await hashAttemptArtifacts(attemptDir) : null,
        };
        const existingScore = runOptions.skipScoredAttempts
          ? await readExistingBiologicalScore(runDir, expectedScore)
          : null;
        if (
          existingScore
          && isReusableExistingBiologicalScore(
            existingScore,
            runDir,
            attemptDir,
            outcome.status,
            expectedScore,
          )
        ) {
          skippedExistingCount += 1;
          scoredResults.set(runId, {
            score: existingScore.score,
            path: existingScore.path,
            status: existingScore.status,
          });
          reportProgress(`Biological scoring ${runId} skipped: existing ${outcome.status} result matches the current canonical attempt at ${existingScore.path}.`);
          continue;
        }
        const evidencePath = await writeAutomaticBiologicalScore(
          result,
          runDir,
          registry,
          options,
          attemptDir,
          outcome,
        );
        if (failureReason) {
          modelFailureCount += 1;
          reportProgress(`Biological scoring ${runId}: model failed (${failureReason}); score=0, wrote status to ${evidencePath}.`);
        } else {
          missingArtifactCount += 1;
          reportProgress(`Biological scoring ${runId} skipped: insufficient evidence; wrote status to ${evidencePath}.`);
        }
        scoredResults.set(runId, { score: outcome.score, path: evidencePath, status: outcome.status });
      } else {
        reportProgress(`Biological scoring ${runId} skipped: no run directory found for matched criterion.`);
      }
    }
  }

  let failedJobCount = 0;
  await mapWithConcurrency(jobs, options.maxConcurrentJobs, async (job, index) => {
    if (runOptions.skipScoredAttempts) {
      const expectedScore = {
        scorerModel: options.model,
        scorerReasoningEffort: options.reasoningEffort,
        criteriaVersion: job.criteriaVersion,
        criteriaSha256: job.criteriaSha256 ?? "",
        attemptIdentity: job.attemptIdentity ?? "",
      };
      const existingScore = await readExistingBiologicalScore(job.runDir, expectedScore);
      if (existingScore && isReusableExistingBiologicalScore(existingScore, job.runDir, job.attemptDir, "scored", expectedScore)) {
        skippedExistingCount += 1;
        scoredResults.set(job.runId, {
          score: existingScore.score,
          path: existingScore.path,
          status: existingScore.status,
        });
        reportProgress(`Biological scoring ${index + 1}/${jobs.length} skipped: ${job.runId}; existing biological score matches ${job.attemptId} at ${existingScore.path}.`);
        return;
      }
    }
    reportProgress(`Biological scoring ${index + 1}/${jobs.length} starting: ${job.runId} (${job.paper}, ${job.mode}).`);
    let result: BiologicalScoringJobResult;
    try {
      result = await scoreJob(job, config, options);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      failedJobCount += 1;
      reportProgress(`Biological scoring ${index + 1}/${jobs.length} failed: ${job.runId}; ${message}`);
      throw error;
    }
    if (result.status === "scored") {
      reportProgress(`Biological scoring ${index + 1}/${jobs.length} finished: ${job.runId}; score=${result.score ?? "n/a"}, path=${result.path ?? "none"}.`);
    } else {
      failedJobCount += 1;
      reportProgress(`Biological scoring ${index + 1}/${jobs.length} failed: ${job.runId}; ${result.error ?? result.status}.`);
    }
    scoredResults.set(job.runId, result);
  });

  const results = summary.results.map((result) => {
    const scored = scoredResults.get(result.runId);
    if (!scored) {
      return result;
    }
    return {
      ...result,
      biologicalScore: scored.score,
      biologicalScorePath: scored.path,
      biologicalScoringStatus: scored.status,
    };
  });
  const biologicalScores = results.flatMap((result) =>
    result.biologicalScore === null || result.biologicalScore === undefined ? [] : [result.biologicalScore],
  );
  const biologicalIttScores = results.flatMap((result) => {
    const score = biologicalIttScore(result);
    return score === null ? [] : [score];
  });
  const comparisonJsonPath = benchmarkOutputPath(
    resolvedBenchmarkDir,
    updatedSummaryPath(summary.comparisonJsonPath),
    "benchmark_comparison.json",
  );
  const comparisonCsvPath = benchmarkOutputPath(
    resolvedBenchmarkDir,
    updatedSummaryPath(summary.comparisonCsvPath),
    "benchmark_comparison.csv",
  );
  const updatedSummary: BenchmarkSummary = {
    ...summary,
    config: {
      ...summary.config,
      biologicalScoringModel: options.model,
      biologicalScoringReasoningEffort: options.reasoningEffort,
      biologicalScoringMaxConcurrentJobs: options.maxConcurrentJobs,
    },
    biologicalScorerVersion: BIOLOGICAL_SCORER_VERSION,
    benchmarkRunDir: resolvedBenchmarkDir,
    results,
    averageBiologicalScore: average(biologicalScores),
    averageBiologicalScoreValidOnly: biologicalScores.length === 0 ? null : average(biologicalScores),
    averageBiologicalScoreItt: average(biologicalIttScores),
    comparisonJsonPath,
    comparisonCsvPath,
    generatedAt: new Date().toISOString(),
  };
  await writeFile(summaryPath, JSON.stringify(updatedSummary, null, 2), "utf8");

  const comparison = buildBenchmarkComparison(updatedSummary);
  await mkdir(path.dirname(comparisonJsonPath), { recursive: true });
  await mkdir(path.dirname(comparisonCsvPath), { recursive: true });
  await writeFile(comparisonJsonPath, JSON.stringify(comparison, null, 2), "utf8");
  await writeFile(comparisonCsvPath, formatComparisonCsv(comparison), "utf8");

  if (runOptions.writeDetailWorkbook !== false) {
    await writeBiologicalScoreDetailWorkbook(
      resolvedBenchmarkDir,
      biologicalScoreVariantKey({
        scorerModel: options.model,
        scorerReasoningEffort: options.reasoningEffort,
        criteriaVersion: registry.version,
        criteriaSha256: criteriaIdentity(registry),
      }),
      options.criteriaPath,
      reportProgress,
    );
  }

  reportProgress(
    `Biological scoring complete: scored=${jobs.length - failedJobCount}, missingArtifacts=${missingArtifactCount}, modelFailures=${modelFailureCount}, skippedExisting=${skippedExistingCount}, failed=${failedJobCount}, average=${updatedSummary.averageBiologicalScore ?? "n/a"}.`,
  );
  return updatedSummary;
}

/* node:coverage disable */
async function writeBiologicalScoreDetailWorkbook(
  benchmarkDir: string,
  variantKey: string,
  criteriaPath: string,
  reportProgress: (message: string) => void,
): Promise<void> {
  const args = buildBiologicalScoreWorkbookArgs(benchmarkDir, variantKey, criteriaPath);
  const failure = await new Promise<string | null>((resolve) => {
    const child = spawn(resolveBenchmarkPythonExecutable(), args, {
      cwd: process.cwd(),
      stdio: ["ignore", "ignore", "pipe"],
      env: buildBenchmarkPythonEnv(process.env),
    });
    let stderr = "";
    child.stderr?.on("data", (chunk: Buffer | string) => {
      stderr += String(chunk);
    });
    child.on("error", (error: Error) => resolve(error.message));
    child.on("close", (code: number | null) => {
      if (code === 0) {
        resolve(null);
        return;
      }
      const detail = stderr.trim().split("\n").slice(-3).join(" ").trim();
      resolve(`exit code ${code ?? "unknown"}${detail ? `: ${detail}` : ""}`);
    });
  });
  if (failure) {
    reportProgress(`Biological score detail workbook skipped for ${variantKey}: ${failure}`);
    return;
  }
  reportProgress(`Biological score detail workbook written for ${variantKey}.`);
}
/* node:coverage enable */

export function buildBiologicalScoreWorkbookArgs(
  benchmarkDir: string,
  variantKey: string,
  criteriaPath: string,
): string[] {
  return [
    path.resolve(process.cwd(), BIOLOGICAL_SCORE_DETAILS_SCRIPT),
    benchmarkDir,
    "--variant",
    variantKey,
    "--criteria-path",
    path.resolve(criteriaPath),
  ];
}

async function scoreBiologicalJob(
  job: BiologicalScoringJob,
  config: BenchmarkConfig,
  options: BiologicalScoringOptions,
): Promise<BiologicalScoringJobResult> {
  const codexHomeDir = path.join(buildBenchmarkCodexHomeDir(job.runDir), "biological_scoring");
  const scoringWorkspaceDir = job.attemptDir;
  const codexSetup = buildBiologicalScoringCodexSetup(config, codexHomeDir);
  await prepareBenchmarkCodexHome(
    codexHomeDir,
    scoringWorkspaceDir,
    codexSetup.skillPaths,
    config.codexAllowedEnvVars,
  );
  const codex = createBiologicalScoringCodex(config, codexSetup.codexConfig, codexHomeDir, options.turnTimeoutMs);
  const thread = codex.startThread(buildBiologicalScoringThreadOptions(job, options));
  const input = buildBiologicalScoringInput(job);
  const turn = await collectScoringTurn(thread, input);
  const provenanceDir = biologicalScoreProvenanceDir(job.runDir, jobScoreProvenance(job, options));
  await rm(provenanceDir, { recursive: true, force: true });
  await writeTranscript(path.join(provenanceDir, "transcript.jsonl"), turn.events);
  await snapshotCodexHomeTo(codexHomeDir, path.join(provenanceDir, "codex_home"));
  await cleanupScoringCodexHome(codexHomeDir);

  if (turn.error) {
    const outputPath = await writeFailedBiologicalScore(job, options, turn.error);
    return { score: null, path: outputPath, status: "scoring_failed", error: turn.error };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(turn.finalResponse) as unknown;
  } catch (error) {
    const message = `Biological scoring response was not valid JSON: ${error instanceof Error ? error.message : String(error)}`;
    const outputPath = await writeFailedBiologicalScore(job, options, message);
    return { score: null, path: outputPath, status: "scoring_failed", error: message };
  }
  let response: BiologicalScoringResponse;
  try {
    response = validateBiologicalScoringResponse(parsed, job.criterion);
  } catch (error) {
    const message = `Biological scoring response failed validation: ${error instanceof Error ? error.message : String(error)}`;
    const outputPath = await writeFailedBiologicalScore(job, options, message);
    return { score: null, path: outputPath, status: "scoring_failed", error: message };
  }
  const outputPath = await writeBiologicalScore(job, options, response);
  return { score: response.score, path: outputPath, status: response.status };
}
/* node:coverage enable */

export function buildBiologicalScoringPrompt(job: BiologicalScoringJob): string {
  const agentWorkspaceDir = path.resolve(job.runDir, "agent_workspace");
  const scoringImages = job.scoringImages ?? [];
  const visualEvidenceInstructions = scoringImages.length === 0
    ? [
      "No canonical raster images are attached. Score qualitative clauses from other direct canonical output evidence when possible, and fail only clauses whose required visual outcome is unsupported.",
    ]
    : [
      "The following attached canonical visual evidence is ordered from early to late within each output series:",
      ...scoringImages.map((image, index) => (
        `IMAGE_${String(index + 1).padStart(2, "0")}: ${image.path} (series ${image.series}, ${image.position})`
      )),
      "Use the attached images as direct visual evidence for relevant qualitative clauses.",
      "Cite the relevant IMAGE_NN labels and exact paths in every qualitative decision that uses visual evidence.",
      "Compare the attached timepoints needed to judge transitions, persistence, direction, morphology, patterning, polarity, continuity, domain shape, and dynamics.",
      "Do not infer unseen frames or claim visual evidence beyond what the attached images directly show.",
    ];
  return [
    "Task: score one Morpheus benchmark attempt against a repo-defined biological criterion.",
    "Do not modify files. Do not use network access.",
    "The current read-only working directory is the canonical attempt directory.",
    "Score only the model.xml and simulation outputs in the canonical attempt directory.",
    `A second read-only agent workspace is available for reference at: ${agentWorkspaceDir}`,
    "Use the agent workspace only to locate or inspect assets referenced by the canonical model.xml, including assets whose archived absolute path is now stale.",
    "Do not score any model.xml, attempts, plots, logs, or simulation outputs found in the agent workspace; they are not the canonical scoring target.",
    "When a clause asks about a model-defined property, a referenced asset is valid evidence if the canonical model.xml uses it; otherwise realized biological outcome evidence must come from canonical attempt outputs.",
    "Use the available Morpheus skill only as a technical reference to interpret MorpheusML, output formats, and model input assets.",
    "Do not run or rerun the model, modify it, repair it, or generate replacement outputs while scoring.",
    "Inspect the available model.xml, CSV files, other outputs, logs, and images, and intelligently choose the artifacts relevant to each clause.",
    ...visualEvidenceInstructions,
    "Use attached visual evidence from the canonical attempt only, except for referenced image assets used by the canonical model.xml.",
    "Score observed biological outcomes, not model intent.",
    "Apply each clause description literally and independently; do not substitute a stricter general definition for the paper-specific definition supplied below.",
    "Use model XML to verify intended mechanisms, variables, cell types, and output definitions.",
    "Intended mechanism clauses can be supported by model XML, especially for mechanisms that are not directly visible in a plot.",
    "Realized biological outcome clauses require direct output evidence from images, tabular/data outputs, or logs.",
    "Do not pass realized outcome clauses from model XML or initial conditions alone unless the clause explicitly defines a model input or initial state as its subject.",
    "When qualitative outcome evidence is ambiguous, fail the clause and describe the missing direct output evidence.",
    "Do not compensate for weak outputs because a benchmark mode is limited; apply the same output-evidence threshold in python_web and Morpheus modes.",
    "Use output images, tabular/data measurements, and logged outputs to judge whether the attempted biological phenotype is actually present or contradicted.",
    "For numeric clauses, use the best available observed evidence. Prefer direct logger CSV/TSV files; if they are missing, inspect other tabular/data outputs such as .dat files, plots/images, stdout/stderr, and model-defined initial populations to estimate values when defensible.",
    "For every numeric decision, cite the machine-readable file, exact rows or timepoints and columns, calculation formula or aggregation, and units when available; report the unrounded result.",
    "Do not estimate a number from an image when machine-readable numeric evidence is available. Apply rounding or tolerance only when the criterion explicitly specifies it.",
    "Initial conditions may support only baseline or static numeric clauses. Never use initial conditions as evidence for dynamic behavior or final outcomes.",
    "For Morpheus DisplacementTracker .dat files with CELL-TRAJECTORIES columns, estimate cell counts from the number of trajectory values after the Time, POP_SUM, and MSD columns at the relevant sampled rows.",
    "Do not fail solely because an expected logger CSV is missing; report the inference and uncertainty in observed_value and rationale.",
    "If stdout/stderr indicate the simulation crashed, stopped early, timed out, or never reached the configured end time but scoreable outputs exist, treat the latest output actually produced as the observed endpoint for clauses referring to end or t_end.",
    "Record the interruption or nonzero exit as a limitation, not as an automatic clause failure; score each clause from the outputs observed through that endpoint.",
    "Do not pass a clause from model XML or initial conditions alone when the run is crashed, truncated, or contradicted by tiny/flat logged values.",
    "For crashed or truncated runs, output evidence must directly show each dynamic or realized outcome before you pass it.",
    "XML or initial conditions are not enough for dynamic or realized outcomes in crashed or truncated runs.",
    "Do not use model intent to override missing or contradictory output evidence for observed outcomes.",
    `Paper: ${job.paper}`,
    `Mode: ${job.mode}`,
    `Repetition: ${job.repetition ?? "n/a"}`,
    "",
    "<criterion>",
    `Target: ${job.criterion.target}`,
    `Scoring instructions: ${job.criterion.scoring_instructions}`,
    "Clauses:",
    ...job.criterion.clauses.map(
      (clause) => `- ${clause.id} [${clause.kind}, weight=${clause.weight}]: ${clause.description}`,
    ),
    "</criterion>",
    "",
    "Return structured JSON only. For each clause, set passed=true only when the available artifacts support it.",
    "Use observed_value for the exact number, qualitative label, or concise description you used.",
    "The host will recompute the final score from clause decisions, so do not optimize the score field manually.",
  ]
    .filter((line): line is string => line !== null)
    .join("\n");
}

function biologicalScoringSkillPath(): string {
  return path.resolve(process.cwd(), ".agents", "skills", "morpheus", "SKILL.md");
}

export function buildBiologicalScoringCodexSetup(config: BenchmarkConfig, codexHomeDir: string) {
  const skillPaths = [biologicalScoringSkillPath()];
  return {
    skillPaths,
    codexConfig: buildCodexConfig(
      { ...config, skillPaths },
      "morpheus_skill",
      undefined,
      undefined,
      codexHomeDir,
    ),
  };
}

export function createBiologicalScoringCodex(
  config: Pick<BenchmarkConfig, "codexAllowedEnvVars">,
  codexConfig: ReturnType<typeof buildBiologicalScoringCodexSetup>["codexConfig"],
  codexHomeDir: string,
  turnTimeoutMs: number,
): Codex {
  const codex = new Codex({
    config: codexConfig,
    env: buildBenchmarkCodexEnv(
      process.env,
      "morpheus_skill",
      codexHomeDir,
      turnTimeoutMs,
      config.codexAllowedEnvVars,
    ),
  });
  // The stock SDK executor ignores CODEX_EXEC_TURN_TIMEOUT_MS; the benchmark executor enforces it.
  installBenchmarkCodexExecRulesIsolation(codex);
  return codex;
}

export function buildBiologicalScoringThreadOptions(
  job: BiologicalScoringJob,
  options: Pick<BiologicalScoringOptions, "model" | "reasoningEffort">,
): ThreadOptions {
  return {
    ...buildBenchmarkThreadOptions(
      {
        model: options.model,
        reasoningEffort: options.reasoningEffort,
        codexApprovalPolicy: "never",
      },
      job.runDir,
      job.attemptDir,
      "morpheus_skill",
    ),
    additionalDirectories: [path.resolve(job.runDir, "agent_workspace")],
    sandboxMode: "read-only",
    networkAccessEnabled: false,
    webSearchMode: "disabled",
  };
}

export function buildBiologicalScoringInput(job: BiologicalScoringJob): UserInput[] {
  return [
    { type: "text", text: buildBiologicalScoringPrompt(job) },
    ...(job.scoringImages ?? []).map((image): UserInput => ({ type: "local_image", path: image.path })),
  ];
}

/* node:coverage disable */
async function collectScoringTurn(thread: ReturnType<Codex["startThread"]>, input: UserInput[]): Promise<CollectedScoringTurn> {
  const events: ThreadEvent[] = [];
  const items = new Map<string, ThreadItem>();
  let usage: CollectedScoringTurn["usage"] = null;
  let finalResponse = "";
  let turnCompleted = false;
  let turnError: string | null = null;

  try {
    const streamed = await thread.runStreamed(input, { outputSchema: BIOLOGICAL_SCORING_RESPONSE_SCHEMA });
    for await (const event of streamed.events) {
      events.push(event);
      if (event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") {
        items.set(event.item.id, event.item);
        if (event.item.type === "agent_message") {
          finalResponse = event.item.text;
        }
      }
      if (event.type === "turn.completed") {
        usage = event.usage;
        turnCompleted = true;
      }
      if (event.type === "turn.failed") {
        turnError = event.error.message;
      }
      if (event.type === "error") {
        turnError = event.message;
      }
    }
  } catch (error) {
    turnError = error instanceof Error ? error.message : String(error);
  }

  if (!turnError && !turnCompleted) {
    turnError = "Biological scoring turn ended before completion.";
  }
  return { finalResponse, usage, events, items: [...items.values()], error: turnError };
}
/* node:coverage enable */

async function writeBiologicalScore(
  job: BiologicalScoringJob,
  options: BiologicalScoringOptions,
  response: BiologicalScoringResponse,
): Promise<string> {
  const payload = {
    ok: true,
    status: response.status,
    generatedAt: new Date().toISOString(),
    paper: job.paper,
    mode: job.mode,
    repetition: job.repetition,
    runId: job.runId,
    attemptId: job.attemptId,
    attemptDir: path.relative(job.runDir, job.attemptDir),
    scorerVersion: BIOLOGICAL_SCORER_VERSION,
    scorerModel: options.model,
    scorerReasoningEffort: options.reasoningEffort,
    criteriaVersion: job.criteriaVersion,
    criteriaSha256: job.criteriaSha256 ?? "",
    attemptIdentity: job.attemptIdentity ?? "",
    scoringImagePaths: biologicalScoringImagePaths(job),
    ...scorerProvenancePaths(job, options),
    target: job.criterion.target,
    score: response.score,
    maxScore: 1,
    clauses: response.clauses,
    summary: response.summary,
    limitations: response.limitations,
  };
  const outputPath = biologicalScoreArtifactPath(job.runDir, jobScoreProvenance(job, options));
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(payload, null, 2), "utf8");
  await writeBiologicalScoreText(outputPath, payload);
  return outputPath;
}

async function writeFailedBiologicalScore(
  job: BiologicalScoringJob,
  options: BiologicalScoringOptions,
  summary: string,
): Promise<string> {
  const payload = {
    ok: false,
    status: "scoring_failed",
    generatedAt: new Date().toISOString(),
    paper: job.paper,
    mode: job.mode,
    repetition: job.repetition,
    runId: job.runId,
    attemptId: job.attemptId,
    attemptDir: path.relative(job.runDir, job.attemptDir),
    scorerVersion: BIOLOGICAL_SCORER_VERSION,
    scorerModel: options.model,
    scorerReasoningEffort: options.reasoningEffort,
    criteriaVersion: job.criteriaVersion,
    criteriaSha256: job.criteriaSha256 ?? "",
    attemptIdentity: job.attemptIdentity ?? "",
    scoringImagePaths: biologicalScoringImagePaths(job),
    ...scorerProvenancePaths(job, options),
    target: job.criterion.target,
    score: null,
    maxScore: 1,
    clauses: [],
    summary,
    limitations: [summary],
  };
  const outputPath = biologicalScoreArtifactPath(job.runDir, jobScoreProvenance(job, options));
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(payload, null, 2), "utf8");
  await writeBiologicalScoreText(outputPath, payload);
  return outputPath;
}

async function writeAutomaticBiologicalScore(
  result: PaperRunResult,
  runDir: string,
  registry: BiologicalScoringRegistry,
  options: BiologicalScoringOptions,
  attemptDir: string | null,
  outcome: AutomaticBiologicalScoreOutcome,
): Promise<string> {
  const criterion = criterionForResult(result, registry);
  const payload = {
    ok: true,
    status: outcome.status,
    generatedAt: new Date().toISOString(),
    paper: result.paper,
    mode: result.mode,
    repetition: result.repetition,
    runId: result.runId,
    attemptId: attemptDir ? path.basename(attemptDir) : null,
    attemptDir: attemptDir ? path.relative(runDir, attemptDir) : null,
    scorerVersion: BIOLOGICAL_SCORER_VERSION,
    scorerModel: options.model,
    scorerReasoningEffort: options.reasoningEffort,
    criteriaVersion: registry.version,
    criteriaSha256: criteriaIdentity(registry),
    attemptIdentity: attemptDir ? await hashAttemptArtifacts(attemptDir) : null,
    scoringImagePaths: [],
    score: outcome.score,
    maxScore: 1,
    target: criterion?.target ?? "",
    clauses: [],
    summary: outcome.summary,
    limitations: outcome.limitations,
  };
  const outputPath = biologicalScoreArtifactPath(runDir, {
    scorerModel: options.model,
    scorerReasoningEffort: options.reasoningEffort,
    criteriaVersion: registry.version,
    criteriaSha256: criteriaIdentity(registry),
    attemptIdentity: attemptDir ? await hashAttemptArtifacts(attemptDir) : null,
  });
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(payload, null, 2), "utf8");
  await writeBiologicalScoreText(outputPath, payload);
  return outputPath;
}

function biologicalScoringImagePaths(job: BiologicalScoringJob): string[] {
  return (job.scoringImages ?? []).map((image) => (
    path.relative(job.runDir, image.path).replaceAll(path.sep, "/")
  ));
}

async function writeBiologicalScoreText(outputPath: string, payload: Record<string, unknown>): Promise<void> {
  const clauses = Array.isArray(payload.clauses) ? payload.clauses : [];
  const lines = [
    `Biological score: ${payload.score ?? "n/a"} / 1`,
    `Status: ${payload.status ?? "unknown"}`,
    `Summary: ${payload.summary ?? ""}`,
    "",
    "Clauses:",
    ...clauses.map((clause) => {
      if (!isRecord(clause)) {
        return "- invalid clause";
      }
      return `- ${clause.id}: ${clause.passed ? "pass" : "fail"} (${clause.observed_value ?? ""})`;
    }),
  ];
  await writeFile(outputPath.replace(/\.json$/, ".txt"), lines.join("\n"), "utf8");
}

function parseCriterion(value: unknown, criterionIndex: number): BiologicalScoringCriterion {
  if (!isRecord(value)) {
    throw new Error(`Biological scoring criterion ${criterionIndex + 1} must be an object.`);
  }
  if (!Array.isArray(value.paper_stems) || value.paper_stems.length === 0) {
    throw new Error(`Biological scoring criterion ${criterionIndex + 1} must include paper_stems.`);
  }
  const paperStems = value.paper_stems.map((entry) => requiredString(entry, "paper_stem"));
  const normalizedPaperStems = [...new Set(paperStems.flatMap((stem) => paperStemCandidates(stem)))];
  const clauses = parseClauses(value.clauses, criterionIndex);
  return {
    paper_stems: paperStems,
    normalized_paper_stems: normalizedPaperStems,
    target: requiredString(value.target, "target"),
    scoring_instructions: requiredString(value.scoring_instructions, "scoring_instructions"),
    clauses,
  };
}

function parseClauses(value: unknown, criterionIndex: number): BiologicalScoringClause[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`Biological scoring criterion ${criterionIndex + 1} must include clauses.`);
  }
  const seenIds = new Set<string>();
  return value.map((rawClause, clauseIndex) => {
    if (!isRecord(rawClause)) {
      throw new Error(`Biological scoring criterion ${criterionIndex + 1} clause ${clauseIndex + 1} must be an object.`);
    }
    const id = requiredString(rawClause.id, "clause id");
    if (seenIds.has(id)) {
      throw new Error(`Duplicate clause id in biological scoring criterion ${criterionIndex + 1}: ${id}`);
    }
    seenIds.add(id);
    if (rawClause.kind !== "numeric" && rawClause.kind !== "qualitative") {
      throw new Error(`Biological scoring clause ${id} kind must be "numeric" or "qualitative".`);
    }
    const weight = finiteNumber(rawClause.weight, `${id}.weight`);
    if (weight <= 0) {
      throw new Error(`Biological scoring clause ${id} weight must be > 0.`);
    }
    return {
      id,
      kind: rawClause.kind,
      weight,
      description: requiredString(rawClause.description, `${id}.description`),
    };
  });
}

function criterionForResult(
  result: Pick<PaperRunResult, "paper" | "pdfPath"> | Record<string, unknown>,
  registry: BiologicalScoringRegistry,
): BiologicalScoringCriterion | null {
  const source = stringValue((result as Record<string, unknown>).pdfPath) ?? stringValue((result as Record<string, unknown>).paper);
  if (!source) {
    return null;
  }
  for (const candidate of paperStemCandidates(source)) {
    const criterion = registry.criteriaByPaperStem.get(candidate);
    if (criterion) {
      return criterion;
    }
  }
  return null;
}

async function resultRunDir(result: Record<string, unknown>, benchmarkDir: string): Promise<string | null> {
  const manifest = stringValue(result.runManifestPath);
  if (manifest) {
    for (const manifestPath of manifestPathCandidates(manifest, benchmarkDir, stringValue(result.runId))) {
      try {
        await stat(manifestPath);
        return path.dirname(manifestPath);
      } catch {
        // Try the next portable path candidate.
      }
    }
    const runId = stringValue(result.runId);
    if (runId) {
      return path.join(benchmarkDir, runId);
    }
    const manifestParentName = portableParentBasename(manifest);
    return manifestParentName ? path.join(benchmarkDir, manifestParentName) : null;
  }
  const runId = stringValue(result.runId);
  return runId ? path.join(benchmarkDir, runId) : null;
}

function manifestPathCandidates(manifest: string, benchmarkDir: string, runId: string | null): string[] {
  // Prefer locations inside benchmarkDir so scoring a copied benchmark never writes
  // into the original run folder that the stored absolute path still points at.
  const absolute = isCurrentPlatformAbsolutePath(manifest);
  const candidates = absolute ? [] : [path.join(benchmarkDir, manifest)];
  if (runId) {
    candidates.push(path.join(benchmarkDir, runId, portableBasename(manifest)));
  }
  const manifestParentName = portableParentBasename(manifest);
  if (manifestParentName) {
    candidates.push(path.join(benchmarkDir, manifestParentName, portableBasename(manifest)));
  }
  if (absolute) {
    candidates.push(manifest);
  }
  return [...new Set(candidates)];
}

async function canonicalAttemptDir(runDir: string): Promise<string | null> {
  const latestAttempt = await latestAttemptDir(path.join(runDir, "attempts"));
  if (latestAttempt) {
    return latestAttempt;
  }

  const manifestPath = path.join(runDir, "run_manifest.json");
  const manifest = await readOptionalJson(manifestPath);
  const manifestAttemptDir = isRecord(manifest) ? stringValue(manifest.technical_attempt_dir) : null;
  if (manifestAttemptDir) {
    const resolved = resolveArtifactPath(runDir, manifestAttemptDir);
    if (await directoryExists(resolved)) {
      return resolved;
    }
  }

  const technical = await readOptionalJson(path.join(runDir, "technical_evaluation.json"));
  const technicalAttemptDir = isRecord(technical) ? stringValue(technical.attempt_dir) : null;
  if (technicalAttemptDir) {
    const resolved = resolveArtifactPath(runDir, technicalAttemptDir);
    if (await directoryExists(resolved)) {
      return resolved;
    }
  }

  return null;
}

async function hasScoreableOutputArtifacts(attemptDir: string): Promise<boolean> {
  let entries: Dirent[];
  try {
    entries = await readdir(attemptDir, { withFileTypes: true });
  } catch {
    entries = [];
  }
  return entries.some(
    (entry) => entry.isFile()
      && [".csv", ".tsv", ".dat", ".png", ".jpg", ".jpeg"].includes(path.extname(entry.name).toLowerCase()),
  );
}

async function canonicalAttemptFailureReason(runDir: string, attemptDir: string): Promise<string | null> {
  const attemptId = path.basename(attemptDir);
  const manifest = await readOptionalJson(path.join(runDir, "run_manifest.json"));
  if (!isRecord(manifest) || stringValue(manifest.latest_attempt_id) !== attemptId) {
    return null;
  }
  return explicitAttemptFailureReason(manifest.latest_attempt_returncode, manifest.latest_attempt_timed_out);
}

function explicitAttemptFailureReason(returncodeValue: unknown, timedOutValue: unknown): string | null {
  const returncode = numberOrNull(returncodeValue);
  if (timedOutValue === true) {
    return returncode !== null && returncode !== 0
      ? `timed out with nonzero exit code ${returncode}`
      : "timed out";
  }
  return returncode !== null && returncode !== 0 ? `nonzero exit code ${returncode}` : null;
}

async function latestAttemptDir(attemptsRoot: string): Promise<string | null> {
  let entries: Dirent[];
  try {
    entries = await readdir(attemptsRoot, { withFileTypes: true });
  } catch {
    return null;
  }
  const attempts = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({ name: entry.name, number: attemptNumber(entry.name) }))
    .filter((entry): entry is { name: string; number: number } => entry.number !== null)
    .sort((left, right) => right.number - left.number);
  return attempts[0] ? path.join(attemptsRoot, attempts[0].name) : null;
}

function attemptNumber(name: string): number | null {
  const match = name.match(/^attempt[_-](\d+)$/i);
  return match ? Number(match[1]) : null;
}

function biologicalScoringOptionsFromConfig(config: BenchmarkConfig): BiologicalScoringOptions {
  return {
    criteriaPath: config.biologicalScoringCriteriaPath,
    model: config.biologicalScoringModel,
    reasoningEffort: config.biologicalScoringReasoningEffort,
    maxConcurrentJobs: config.biologicalScoringMaxConcurrentJobs,
    turnTimeoutMs: config.biologicalScoringTurnTimeoutMs,
  };
}

function paperStemCandidates(input: string): string[] {
  const base = portableBasename(input);
  const normalized = normalizePaperStem(base);
  const withoutPrefix = normalized.replace(/^\d+_/, "");
  return [...new Set([normalized, withoutPrefix])].filter(Boolean);
}

function normalizePaperStem(value: string): string {
  return value
    .trim()
    .replace(/\.[^.\\/]+$/, "")
    .replace(/_(?:clean|short)$/i, "")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_")
    .toLowerCase();
}

function resolveArtifactPath(runDir: string, value: string): string {
  return path.isAbsolute(value) ? value : path.resolve(runDir, value);
}

function benchmarkOutputPath(benchmarkDir: string, savedPath: string | null, defaultName: string): string {
  if (!savedPath) {
    return path.join(benchmarkDir, defaultName);
  }
  if (isCurrentPlatformAbsolutePath(savedPath)) {
    const relative = path.relative(benchmarkDir, savedPath);
    if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
      return savedPath;
    }
    return path.join(benchmarkDir, portableBasename(savedPath) || defaultName);
  }
  if (isWindowsAbsolutePath(savedPath)) {
    return path.join(benchmarkDir, portableBasename(savedPath) || defaultName);
  }
  return path.resolve(benchmarkDir, savedPath);
}

function updatedSummaryPath(value: unknown): string | null {
  return stringValue(value);
}

function isCurrentPlatformAbsolutePath(value: string): boolean {
  return path.isAbsolute(value);
}

function isWindowsAbsolutePath(value: string): boolean {
  return /^[A-Za-z]:[\\/]/.test(value) || value.startsWith("\\\\");
}

function portableBasename(value: string): string {
  return isWindowsAbsolutePath(value) ? path.win32.basename(value) : path.basename(value);
}

function portableParentBasename(value: string): string | null {
  const parent = isWindowsAbsolutePath(value) ? path.win32.dirname(value) : path.dirname(value);
  const base = portableBasename(parent);
  return base && base !== "." ? base : null;
}

async function readOptionalJson(inputPath: string): Promise<unknown | null> {
  try {
    return JSON.parse(await readFile(inputPath, "utf8")) as unknown;
  } catch {
    return null;
  }
}

async function readExistingBiologicalScore(
  runDir: string,
  expected: {
    scorerModel: string;
    scorerReasoningEffort: ReasoningEffort;
    criteriaVersion: number;
    criteriaSha256: string;
    attemptIdentity: string | null;
  },
): Promise<ExistingBiologicalScore | null> {
  const cohortPath = biologicalScoreArtifactPath(runDir, expected);
  const legacyPath = path.join(runDir, "biological_score.json");
  const cohortParsed = await readOptionalJson(cohortPath);
  const scorePath = isRecord(cohortParsed) ? cohortPath : legacyPath;
  const parsed = isRecord(cohortParsed) ? cohortParsed : await readOptionalJson(legacyPath);
  if (!isRecord(parsed)) {
    return null;
  }
  const status = stringValue(parsed.status);
  if (!status) {
    return null;
  }
  return {
    score: numberOrNull(parsed.score),
    path: scorePath,
    status,
    attemptId: stringValue(parsed.attemptId),
    attemptDir: stringValue(parsed.attemptDir),
    scorerVersion: numberOrNull(parsed.scorerVersion),
    criteriaVersion: numberOrNull(parsed.criteriaVersion),
    scorerModel: stringValue(parsed.scorerModel),
    scorerReasoningEffort: stringValue(parsed.scorerReasoningEffort),
    criteriaSha256: stringValue(parsed.criteriaSha256),
    attemptIdentity: stringValue(parsed.attemptIdentity),
  };
}

export function biologicalScoreVariantKey(provenance: {
  scorerModel: string;
  scorerReasoningEffort: string;
  criteriaVersion: number;
  criteriaSha256: string;
}): string {
  const safeModel = provenance.scorerModel.replace(/[^A-Za-z0-9._-]+/g, "-");
  const criteria = (provenance.criteriaSha256 || "unknown").slice(0, 12);
  return `scorer-v${BIOLOGICAL_SCORER_VERSION}__${safeModel}__${provenance.scorerReasoningEffort}__criteria-v${provenance.criteriaVersion}-${criteria}`;
}

function biologicalScoreArtifactPath(
  runDir: string,
  provenance: {
    scorerModel: string;
    scorerReasoningEffort: string;
    criteriaVersion: number;
    criteriaSha256: string;
    attemptIdentity: string | null;
  },
): string {
  const attempt = (provenance.attemptIdentity || "none").slice(0, 12);
  return path.join(
    runDir,
    "biological_scores",
    `${biologicalScoreVariantKey(provenance)}__attempt-${attempt}.json`,
  );
}

export function biologicalScoreProvenanceDir(
  runDir: string,
  provenance: Parameters<typeof biologicalScoreArtifactPath>[1],
): string {
  return biologicalScoreArtifactPath(runDir, provenance).replace(/\.json$/, "");
}

function jobScoreProvenance(
  job: BiologicalScoringJob,
  options: Pick<BiologicalScoringOptions, "model" | "reasoningEffort">,
): Parameters<typeof biologicalScoreArtifactPath>[1] {
  return {
    scorerModel: options.model,
    scorerReasoningEffort: options.reasoningEffort,
    criteriaVersion: job.criteriaVersion,
    criteriaSha256: job.criteriaSha256 ?? "",
    attemptIdentity: job.attemptIdentity ?? "",
  };
}

function scorerProvenancePaths(
  job: BiologicalScoringJob,
  options: Pick<BiologicalScoringOptions, "model" | "reasoningEffort">,
): { scorerTranscriptPath: string; scorerCodexHomePath: string } {
  const provenanceDir = path.relative(job.runDir, biologicalScoreProvenanceDir(job.runDir, jobScoreProvenance(job, options)));
  return {
    scorerTranscriptPath: path.join(provenanceDir, "transcript.jsonl").replaceAll(path.sep, "/"),
    scorerCodexHomePath: path.join(provenanceDir, "codex_home").replaceAll(path.sep, "/"),
  };
}

function isReusableExistingBiologicalScore(
  score: ExistingBiologicalScore,
  runDir: string,
  attemptDir: string | null,
  expectedStatus: "scored" | "model_failed" | "insufficient_evidence",
  expected: {
    scorerModel: string;
    scorerReasoningEffort: ReasoningEffort;
    criteriaVersion: number;
    criteriaSha256: string;
    attemptIdentity: string | null;
  },
): boolean {
  if (
    score.status !== expectedStatus
    || score.scorerVersion !== BIOLOGICAL_SCORER_VERSION
    || score.scorerModel !== expected.scorerModel
    || score.scorerReasoningEffort !== expected.scorerReasoningEffort
    || score.criteriaVersion !== expected.criteriaVersion
    || score.criteriaSha256 !== expected.criteriaSha256
    || score.attemptIdentity !== expected.attemptIdentity
  ) {
    return false;
  }
  if ((expectedStatus !== "insufficient_evidence") !== (score.score !== null)) {
    return false;
  }
  if (expectedStatus === "model_failed" && score.score !== 0) {
    return false;
  }
  if (!attemptDir) {
    return score.attemptId === null && score.attemptDir === null;
  }
  if (score.attemptId && score.attemptId === path.basename(attemptDir)) {
    return true;
  }
  if (!score.attemptDir) {
    return false;
  }
  return path.resolve(runDir, score.attemptDir) === path.resolve(attemptDir);
}

async function directoryExists(inputPath: string): Promise<boolean> {
  try {
    return (await stat(inputPath)).isDirectory();
  } catch {
    return false;
  }
}

function sha256(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function criteriaIdentity(registry: BiologicalScoringRegistry): string {
  return registry.criteriaSha256 ?? sha256(JSON.stringify(registry.criteria));
}

async function hashAttemptArtifacts(attemptDir: string): Promise<string> {
  const files: string[] = [];
  const visit = async (directory: string): Promise<void> => {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
      const entryPath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        await visit(entryPath);
      } else if (entry.isFile()) {
        files.push(entryPath);
      }
    }
  };
  await visit(attemptDir);
  const hash = createHash("sha256");
  for (const file of files) {
    hash.update(path.relative(attemptDir, file).replaceAll(path.sep, "/"));
    hash.update("\0");
    hash.update(await readFile(file));
    hash.update("\0");
  }
  return hash.digest("hex");
}

async function writeTranscript(outputPath: string, events: ThreadEvent[]): Promise<void> {
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${events.map((event) => JSON.stringify(event)).join("\n")}\n`, "utf8");
}

async function cleanupScoringCodexHome(codexHomeDir: string): Promise<void> {
  const resolved = path.resolve(codexHomeDir);
  const allowedRoot = path.resolve(path.join(tmpdir(), "morpheus-modeling-codex-home"));
  const relative = path.relative(allowedRoot, resolved);
  if (relative && !relative.startsWith("..") && !path.isAbsolute(relative)) {
    await rm(resolved, { recursive: true, force: true });
  }
}

function average(values: number[]): number | null {
  return values.length === 0 ? null : values.reduce((sum, value) => sum + value, 0) / values.length;
}

function finiteNumber(value: unknown, name: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`Biological scoring ${name} must be a finite number.`);
  }
  return value;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function requiredString(value: unknown, name: string): string {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new Error(`Biological scoring ${name} must be a non-empty string.`);
  }
  return value;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseBiologicalScoringCliArgs(args: string[]): ParsedBiologicalScoringCliArgs {
  const benchmarkDir = args[0];
  if (!benchmarkDir || benchmarkDir.startsWith("--")) {
    throw new Error(
      "Usage: npm run score:biology -- <benchmark_dir> [--model <name>] [--reasoning-effort <none|low|medium|high|xhigh|max>] [--max-concurrent-jobs <number>] [--criteria-path <path>] [--turn-timeout-ms <number>] [--skip-scored-attempts]",
    );
  }

  const overrides: Partial<BenchmarkConfig> = {};
  let skipScoredAttempts = false;
  for (let index = 1; index < args.length; index += 1) {
    const arg = args[index];
    const next = args[index + 1];
    switch (arg) {
      case "--criteria-path":
        overrides.biologicalScoringCriteriaPath = requireCliValue(arg, next);
        index += 1;
        break;
      case "--model":
        overrides.biologicalScoringModel = requireCliValue(arg, next);
        index += 1;
        break;
      case "--reasoning-effort":
        overrides.biologicalScoringReasoningEffort = requireCliValue(arg, next) as ReasoningEffort;
        index += 1;
        break;
      case "--max-concurrent-jobs":
        overrides.biologicalScoringMaxConcurrentJobs = parseIntegerCliValue(arg, next, 1);
        index += 1;
        break;
      case "--turn-timeout-ms":
        overrides.biologicalScoringTurnTimeoutMs = parseIntegerCliValue(arg, next, 1);
        index += 1;
        break;
      case "--skip-scored-attempts":
        skipScoredAttempts = true;
        break;
      default:
        throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return { benchmarkDir, overrides, skipScoredAttempts };
}

function requireCliValue(arg: string, value: string | undefined): string {
  if (!value || value.startsWith("--")) {
    throw new Error(`Missing value for ${arg}`);
  }
  return value;
}

function parseIntegerCliValue(arg: string, value: string | undefined, minimum: number): number {
  const raw = requireCliValue(arg, value);
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < minimum) {
    throw new Error(`${arg} must be an integer >= ${minimum}.`);
  }
  return parsed;
}

async function main(args = process.argv.slice(2)): Promise<void> {
  const parsed = parseBiologicalScoringCliArgs(args);
  const { applyCliOverrides, loadConfigForRecoverRun } = await import("./config.js");
  const baseConfig = await loadConfigForRecoverRun(parsed.benchmarkDir);
  const config = applyCliOverrides(baseConfig, parsed.overrides);
  await runBiologicalScoringForBenchmark(
    parsed.benchmarkDir,
    config,
    (message) => console.error(message),
    undefined,
    { skipScoredAttempts: parsed.skipScoredAttempts },
  );
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
