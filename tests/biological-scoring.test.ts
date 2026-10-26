/* node:coverage disable */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, readdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  BIOLOGICAL_SCORER_VERSION,
  BIOLOGICAL_SCORE_DETAILS_SCRIPT,
  biologicalIttScore,
  biologicalScoreProvenanceDir,
  biologicalScoreVariantKey,
  buildBiologicalScoreWorkbookArgs,
  buildBiologicalScoringCodexSetup,
  buildBiologicalScoringInput,
  buildBiologicalScoringPrompt,
  buildBiologicalScoringThreadOptions,
  createBiologicalScoringCodex,
  discoverBiologicalScoringJobs,
  loadBiologicalScoringCriteria,
  parseBiologicalScoringCliArgs,
  recomputeBiologicalScore,
  runBiologicalScoringForBenchmark,
  validateBiologicalScoringResponse,
} from "../src/benchmark/biological-scoring.js";
import type { BiologicalScoringJob } from "../src/benchmark/biological-scoring.js";
import { parseCliArgs } from "../src/benchmark/cli.js";
import { loadPaperFocus } from "../src/benchmark/focus.js";
import type { BenchmarkConfig } from "../src/benchmark/types.js";

function zeroDiagnostics() {
  return {
    turnCount: 0,
    attemptCount: 0,
    agentWallTimeMs: 0,
    morpheusSimulationTimeMs: 0,
    agentAnalysisTimeMs: 0,
    hostMorpheusRunTimeMs: 0,
    hostTechnicalEvaluationTimeMs: 0,
    tokens: { input: 0, cachedInput: 0, output: 0, reasoningOutput: 0, total: 0 },
  };
}

function biologicalTestConfig(root: string, criteriaPath: string): BenchmarkConfig {
  return {
    papersDir: path.join(root, "papers"),
    resultsDir: path.dirname(root),
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
    biologicalScoringCriteriaPath: criteriaPath,
    biologicalScoringModel: "gpt-5.4-mini",
    biologicalScoringReasoningEffort: "low",
    biologicalScoringMaxConcurrentJobs: 1,
    biologicalScoringTurnTimeoutMs: 1000,
    mcpCommand: ["python", "server.py"],
    mcpToolTimeoutMs: 1000,
    bridgeToolTimeoutMs: 1000,
    morpheusRunTimeoutMs: 1000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: path.resolve("src/benchmark/MorpheusML.xsd"),
    skillPaths: [],
  };
}

async function createScoreableBiologicalBenchmark() {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-scoreable-"));
  const runDir = path.join(root, "run_szabo");
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  const criteriaPath = path.join(root, "criteria.json");
  await mkdir(attemptDir, { recursive: true });
  await writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(attemptDir, "logger.csv"), "time,count\n0,1\n", "utf8");
  await writeFile(path.join(attemptDir, "plot_00010.png"), "png", "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({ run_id: "run_szabo", technical_attempt_dir: attemptDir }),
    "utf8",
  );
  await writeFile(
    criteriaPath,
    JSON.stringify({
      version: 1,
      criteria: [
        {
          paper_stems: ["01_Szabo2010"],
          target: "Dense monolayer",
          scoring_instructions: "Score observed CSVs or images.",
          clauses: [{ id: "volume", kind: "numeric", weight: 1, description: "Volume below threshold." }],
        },
      ],
    }),
    "utf8",
  );
  await writeFile(
    path.join(root, "benchmark_summary.json"),
    JSON.stringify({
      benchmarkRunDir: root,
      benchmarkId: "benchmark",
      comparisonJsonPath: path.join(root, "benchmark_comparison.json"),
      comparisonCsvPath: path.join(root, "benchmark_comparison.csv"),
      startedAt: "2026-05-24T00:00:00.000Z",
      finishedAt: "2026-05-24T00:01:00.000Z",
      generatedAt: "2026-05-24T00:01:00.000Z",
      durationMs: 60_000,
      diagnostics: zeroDiagnostics(),
      totalRuns: 1,
      uniquePapers: 1,
      benchmarkRepetitions: 1,
      totalPapers: 1,
      totalModelRefinements: 0,
      averageModelRefinements: 0,
      averageTechnicalScore: null,
      averageReproductionScore: null,
      averageBiologicalScore: null,
      config: { benchmarkModes: ["morpheus_mcp"] },
      results: [
        {
          paper: "01_Szabo2010.pdf",
          pdfPath: "benchmark_papers/01_Szabo2010.pdf",
          mode: "morpheus_mcp",
          modeLabel: "Morpheus MCP",
          capabilities: {},
          capabilityViolations: [],
          runId: "run_szabo",
          threadId: null,
          repetition: 1,
          startedAt: null,
          finishedAt: null,
          durationMs: 0,
          diagnostics: zeroDiagnostics(),
          attempts: 1,
          modelRefinementCount: 0,
          technicalScore: null,
          reproductionScore: null,
          technicalEvaluationPath: null,
          reproductionReportPath: null,
          reproductionReportTextPath: null,
          runManifestPath: path.join(runDir, "run_manifest.json"),
          benchmarkFocus: null,
          summary: "Completed with scoreable outputs.",
        },
      ],
    }),
    "utf8",
  );
  return { root, runDir, criteriaPath, config: biologicalTestConfig(root, criteriaPath) };
}

test("loadBiologicalScoringCriteria rejects duplicate paper stems and clause ids", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-criteria-"));
  const criteriaPath = path.join(root, "criteria.json");
  await writeFile(
    criteriaPath,
    JSON.stringify({
      version: 1,
      criteria: [
        {
          paper_stems: ["1_Szabo2010_clean", "Szabo2010"],
          target: "Dense monolayer",
          scoring_instructions: "Score logged outputs.",
          clauses: [
            { id: "speed_min", kind: "numeric", weight: 1, description: "Mean speed above threshold." },
            { id: "speed_min", kind: "numeric", weight: 1, description: "Duplicate id." },
          ],
        },
        {
          paper_stems: ["szabo2010"],
          target: "Duplicate normalized paper stem",
          scoring_instructions: "Should be rejected.",
          clauses: [{ id: "volume", kind: "numeric", weight: 1, description: "Volume criterion." }],
        },
      ],
    }),
    "utf8",
  );

  await assert.rejects(
    () => loadBiologicalScoringCriteria(criteriaPath),
    /duplicate clause id.*speed_min|duplicate paper stem.*szabo2010/i,
  );
});

test("loadBiologicalScoringCriteria supports new paper additions without workbook input", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-criteria-"));
  const criteriaPath = path.join(root, "criteria.json");
  await writeFile(
    criteriaPath,
    JSON.stringify({
      version: 1,
      criteria: [
        {
          paper_stems: ["Otsuki2025_LimbRegeneration"],
          target: "Regenerating cut limb tissue",
          scoring_instructions: "Use images and CSVs.",
          clauses: [
            { id: "hand2_cut", kind: "qualitative", weight: 1, description: "Hand2 rises near the cut." },
          ],
        },
      ],
    }),
    "utf8",
  );

  const registry = await loadBiologicalScoringCriteria(criteriaPath);

  assert.equal(registry.version, 1);
  assert.equal(registry.criteriaByPaperStem.get("otsuki2025_limbregeneration")?.target, "Regenerating cut limb tissue");
});

test("loadBiologicalScoringCriteria discards local reference model metadata", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-criteria-"));
  const criteriaPath = path.join(root, "criteria.json");
  await writeFile(
    criteriaPath,
    JSON.stringify({
      version: 1,
      criteria: [
        {
          paper_stems: ["1_Szabo2010_clean"],
          target: "Dense monolayer",
          reference_model: "local-only/model.xml",
          scoring_instructions: "Score CSVs.",
          clauses: [{ id: "volume", kind: "numeric", weight: 1, description: "Volume below threshold." }],
        },
      ],
    }),
    "utf8",
  );

  const registry = await loadBiologicalScoringCriteria(criteriaPath);

  assert.equal("reference_model" in (registry.criteria[0] as Record<string, unknown>), false);
});

test("loadBiologicalScoringCriteria rejects malformed registry and criterion entries", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-criteria-invalid-"));
  const cases: Array<[string, unknown, RegExp]> = [
    ["root array", [], /must be a JSON object/],
    ["missing version", { criteria: [] }, /version must be a finite number/],
    ["zero version", { version: 0, criteria: [] }, /version must be an integer >= 1/],
    ["missing criteria", { version: 1 }, /criteria array/],
    ["non-object criterion", { version: 1, criteria: [null] }, /criterion 1 must be an object/],
    [
      "missing paper stems",
      { version: 1, criteria: [{ target: "T", scoring_instructions: "S", clauses: [] }] },
      /criterion 1 must include paper_stems/,
    ],
    [
      "empty target",
      {
        version: 1,
        criteria: [
          {
            paper_stems: ["paper"],
            target: "",
            scoring_instructions: "S",
            clauses: [{ id: "c", kind: "numeric", weight: 1, description: "D" }],
          },
        ],
      },
      /target must be a non-empty string/,
    ],
    [
      "missing clauses",
      {
        version: 1,
        criteria: [{ paper_stems: ["paper"], target: "T", scoring_instructions: "S" }],
      },
      /criterion 1 must include clauses/,
    ],
    [
      "non-object clause",
      {
        version: 1,
        criteria: [{ paper_stems: ["paper"], target: "T", scoring_instructions: "S", clauses: [null] }],
      },
      /clause 1 must be an object/,
    ],
    [
      "bad clause kind",
      {
        version: 1,
        criteria: [
          {
            paper_stems: ["paper"],
            target: "T",
            scoring_instructions: "S",
            clauses: [{ id: "c", kind: "text", weight: 1, description: "D" }],
          },
        ],
      },
      /kind must be "numeric" or "qualitative"/,
    ],
    [
      "bad clause weight",
      {
        version: 1,
        criteria: [
          {
            paper_stems: ["paper"],
            target: "T",
            scoring_instructions: "S",
            clauses: [{ id: "c", kind: "numeric", weight: 0, description: "D" }],
          },
        ],
      },
      /weight must be > 0/,
    ],
  ];

  for (const [name, payload, message] of cases) {
    const criteriaPath = path.join(root, `${name.replaceAll(" ", "_")}.json`);
    await writeFile(criteriaPath, JSON.stringify(payload), "utf8");
    await assert.rejects(() => loadBiologicalScoringCriteria(criteriaPath), message, name);
  }
});

test("discoverBiologicalScoringJobs selects the canonical technical attempt and ignores unmatched papers", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-jobs-"));
  const runDir = path.join(root, "run_szabo");
  const technicalAttempt = path.join(runDir, "attempts", "attempt_002");
  const olderAttempt = path.join(runDir, "attempts", "attempt_001");
  await mkdir(technicalAttempt, { recursive: true });
  await mkdir(olderAttempt, { recursive: true });
  await writeFile(path.join(technicalAttempt, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(technicalAttempt, "logger.csv"), "time,count\n0,1\n", "utf8");
  await writeFile(path.join(technicalAttempt, "plot_00010.png"), "png", "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      run_id: "run_szabo",
      technical_attempt_dir: technicalAttempt,
    }),
    "utf8",
  );

  const summary = {
    benchmarkRunDir: root,
    results: [
      {
        paper: "01_Szabo2010.pdf",
        pdfPath: path.join("benchmark_papers", "01_Szabo2010.pdf"),
        mode: "morpheus_mcp",
        runId: "run_szabo",
        repetition: 1,
        runManifestPath: path.join(runDir, "run_manifest.json"),
      },
      {
        paper: "15_Reza2025.pdf",
        pdfPath: "benchmark_papers/15_Reza2025.pdf",
        mode: "morpheus_mcp",
        runId: "run_reza",
        repetition: 1,
      },
    ],
  };
  const registry = {
    version: 1,
    criteria: [
      {
        paper_stems: ["01_Szabo2010"],
        normalized_paper_stems: ["01_szabo2010"],
        target: "Dense monolayer",
        scoring_instructions: "Score CSVs.",
        clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
      },
    ],
    criteriaByPaperStem: new Map([
      [
        "01_szabo2010",
        {
          paper_stems: ["01_Szabo2010"],
          normalized_paper_stems: ["01_szabo2010"],
          target: "Dense monolayer",
          scoring_instructions: "Score CSVs.",
          clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
        },
      ],
    ]),
  };

  const jobs = await discoverBiologicalScoringJobs(summary, registry);

  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].paper, "01_Szabo2010.pdf");
  assert.equal(jobs[0].attemptId, "attempt_002");
  assert.equal(path.resolve(jobs[0].attemptDir), path.resolve(technicalAttempt));
  assert.equal("modelXmlPath" in jobs[0], false);
  assert.equal("csvPaths" in jobs[0], false);
  assert.equal("imagePaths" in jobs[0], false);
  assert.equal("logPaths" in jobs[0], false);
});

test("discoverBiologicalScoringJobs samples every canonical image series within the attachment cap", async () => {
  const { root, runDir, criteriaPath } = await createScoreableBiologicalBenchmark();
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  const times = [0, 10, 20, 30, 40, 50, 60, 70];
  for (const series of ["plot", "plot-2", "plot-3"]) {
    for (const time of times) {
      await writeFile(path.join(attemptDir, `${series}_${String(time).padStart(5, "0")}.png`), "png", "utf8");
    }
  }
  await writeFile(path.join(attemptDir, "domain.tif"), "tif", "utf8");

  const summary = JSON.parse(await readFile(path.join(root, "benchmark_summary.json"), "utf8"));
  const registry = await loadBiologicalScoringCriteria(criteriaPath);
  const [job] = await discoverBiologicalScoringJobs(summary, registry, { benchmarkDir: root });
  const scoringImages = (job as BiologicalScoringJob & {
    scoringImages: Array<{ path: string; series: string; position: string }>;
  }).scoringImages;

  assert.equal(scoringImages.length, 12);
  assert.deepEqual(
    scoringImages.map((image) => [image.series, path.basename(image.path), image.position]),
    [
      ["plot", "plot_00000.png", "early"],
      ["plot", "plot_00020.png", "intermediate"],
      ["plot", "plot_00050.png", "intermediate"],
      ["plot", "plot_00070.png", "final"],
      ["plot-2", "plot-2_00000.png", "early"],
      ["plot-2", "plot-2_00020.png", "intermediate"],
      ["plot-2", "plot-2_00050.png", "intermediate"],
      ["plot-2", "plot-2_00070.png", "final"],
      ["plot-3", "plot-3_00000.png", "early"],
      ["plot-3", "plot-3_00020.png", "intermediate"],
      ["plot-3", "plot-3_00050.png", "intermediate"],
      ["plot-3", "plot-3_00070.png", "final"],
    ],
  );
});

test("discoverBiologicalScoringJobs scores the latest numbered attempt even when manifest points older", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-latest-"));
  const runDir = path.join(root, "run_szabo");
  const olderAttempt = path.join(runDir, "attempts", "attempt_001");
  const latestAttempt = path.join(runDir, "attempts", "attempt_002");
  await mkdir(olderAttempt, { recursive: true });
  await mkdir(latestAttempt, { recursive: true });
  await writeFile(path.join(olderAttempt, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(olderAttempt, "old_logger.csv"), "time,count\n0,1\n", "utf8");
  await writeFile(path.join(latestAttempt, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(latestAttempt, "latest_logger.csv"), "time,count\n0,2\n", "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      run_id: "run_szabo",
      technical_attempt_dir: olderAttempt,
    }),
    "utf8",
  );

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const registry = {
    version: 1,
    criteria: [criterion],
    criteriaByPaperStem: new Map([["01_szabo2010", criterion]]),
  };
  const summary = {
    benchmarkRunDir: root,
    results: [
      {
        paper: "01_Szabo2010.pdf",
        pdfPath: path.join("benchmark_papers", "01_Szabo2010.pdf"),
        mode: "morpheus_mcp",
        runId: "run_szabo",
        repetition: 1,
        runManifestPath: path.join(runDir, "run_manifest.json"),
      },
    ],
  };

  const jobs = await discoverBiologicalScoringJobs(summary, registry);

  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].attemptId, "attempt_002");
  assert.equal(path.resolve(jobs[0].attemptDir), path.resolve(latestAttempt));
});

test("discoverBiologicalScoringJobs uses the local benchmark dir for moved Windows summaries", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-moved-"));
  const runDir = path.join(root, "run_szabo");
  const technicalAttempt = path.join(runDir, "attempts", "attempt_001");
  await mkdir(technicalAttempt, { recursive: true });
  await writeFile(path.join(technicalAttempt, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(technicalAttempt, "plot_00010.png"), "png", "utf8");
  await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ run_id: "run_szabo" }), "utf8");

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const registry = {
    version: 1,
    criteria: [criterion],
    criteriaByPaperStem: new Map([["01_szabo2010", criterion]]),
  };
  const summary = {
    benchmarkRunDir: "E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\20260524_002842_benchmark",
    results: [
      {
        paper: "01_Szabo2010.pdf",
        pdfPath: "E:\\PycharmProjects\\Morpheus.AI\\benchmark_papers\\01_Szabo2010.pdf",
        mode: "morpheus_mcp",
        runId: "run_szabo",
        repetition: 1,
        runManifestPath:
          "E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\20260524_002842_benchmark\\run_szabo\\run_manifest.json",
      },
    ],
  };

  const jobs = await discoverBiologicalScoringJobs(summary, registry, { benchmarkDir: root });

  assert.equal(jobs.length, 1);
  assert.equal(path.resolve(jobs[0].runDir), path.resolve(runDir));
  assert.equal(path.resolve(jobs[0].attemptDir), path.resolve(technicalAttempt));
});

test("discoverBiologicalScoringJobs prefers the copied benchmark dir over a still-existing original", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-copy-"));
  const writeRun = async (benchmarkDir: string) => {
    const runDir = path.join(benchmarkDir, "run_szabo");
    const attemptDir = path.join(runDir, "attempts", "attempt_001");
    await mkdir(attemptDir, { recursive: true });
    await writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel />", "utf8");
    await writeFile(path.join(attemptDir, "logger.csv"), "time,count\n0,1\n", "utf8");
    await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ run_id: "run_szabo" }), "utf8");
    return runDir;
  };
  const originalRunDir = await writeRun(path.join(root, "original"));
  const copiedRunDir = await writeRun(path.join(root, "copy"));

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const jobs = await discoverBiologicalScoringJobs(
    {
      results: [
        {
          paper: "01_Szabo2010.pdf",
          mode: "morpheus_mcp",
          runId: "run_szabo",
          repetition: 1,
          runManifestPath: path.join(originalRunDir, "run_manifest.json"),
        },
      ],
    },
    { version: 1, criteria: [criterion], criteriaByPaperStem: new Map([["01_szabo2010", criterion]]) },
    { benchmarkDir: path.join(root, "copy") },
  );

  assert.equal(jobs.length, 1);
  assert.equal(path.resolve(jobs[0].runDir), path.resolve(copiedRunDir));
  assert.equal(path.resolve(jobs[0].attemptDir), path.resolve(path.join(copiedRunDir, "attempts", "attempt_001")));
});

test("discoverBiologicalScoringJobs falls back to a moved manifest parent when runId is absent", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-parent-"));
  const runDir = path.join(root, "portable_run");
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  await mkdir(attemptDir, { recursive: true });
  await writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(attemptDir, "logger.csv"), "time,count\n0,1\n", "utf8");

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const jobs = await discoverBiologicalScoringJobs(
    {
      results: [
        {
          pdfPath: "C:\\archived\\01_Szabo2010.pdf",
          runManifestPath: "C:\\archived\\portable_run\\run_manifest.json",
        },
      ],
    },
    { version: 1, criteria: [criterion], criteriaByPaperStem: new Map([["01_szabo2010", criterion]]) },
    { benchmarkDir: root },
  );

  assert.equal(jobs.length, 1);
  assert.equal(jobs[0].paper, "01_Szabo2010.pdf");
  assert.equal(jobs[0].runId, "portable_run");
  assert.equal(path.resolve(jobs[0].runDir), path.resolve(runDir));
});

test("discoverBiologicalScoringJobs falls back to technical evaluation attempt dirs without sampling artifacts", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-technical-"));
  const runDir = path.join(root, "run_szabo");
  const attemptDir = path.join(runDir, "host_eval_attempt");
  await mkdir(attemptDir, { recursive: true });
  await writeFile(path.join(attemptDir, "MODEL.XML"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(attemptDir, "logger.tsv"), "time\tcount\n0\t1\n", "utf8");
  await writeFile(path.join(attemptDir, "plot_00001.JPG"), "jpg", "utf8");
  await writeFile(path.join(attemptDir, "plot_00002.jpeg"), "jpeg", "utf8");
  await writeFile(path.join(attemptDir, "plot_00003.png"), "png", "utf8");
  await writeFile(path.join(runDir, "technical_evaluation.json"), JSON.stringify({ attempt_dir: attemptDir }), "utf8");

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score TSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const jobs = await discoverBiologicalScoringJobs(
    {
      benchmarkRunDir: root,
      results: [{ paper: "01_Szabo2010.pdf", mode: "morpheus_mcp", runId: "run_szabo", repetition: 1 }],
    },
    { version: 1, criteria: [criterion], criteriaByPaperStem: new Map([["01_szabo2010", criterion]]) },
  );

  assert.equal(jobs.length, 1);
  assert.equal(path.resolve(jobs[0].attemptDir), path.resolve(attemptDir));
  assert.equal("modelXmlPath" in jobs[0], false);
  assert.equal("csvPaths" in jobs[0], false);
  assert.equal("imagePaths" in jobs[0], false);
  assert.equal("logPaths" in jobs[0], false);
});

test("discoverBiologicalScoringJobs skips entries without matching paper or run directory", async () => {
  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };

  const jobs = await discoverBiologicalScoringJobs(
    {
      results: [
        { mode: "morpheus_mcp", runId: "run_without_paper" },
        { paper: "01_Szabo2010.pdf", mode: "morpheus_mcp" },
      ],
    },
    { version: 1, criteria: [criterion], criteriaByPaperStem: new Map([["01_szabo2010", criterion]]) },
  );

  assert.deepEqual(jobs, []);
});

test("discoverBiologicalScoringJobs skips attempts without output artifacts", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-model-only-"));
  const runDir = path.join(root, "run_szabo");
  const technicalAttempt = path.join(runDir, "attempts", "attempt_001");
  await mkdir(technicalAttempt, { recursive: true });
  await writeFile(path.join(technicalAttempt, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(technicalAttempt, "stderr.log"), "runtime failure", "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      run_id: "run_szabo",
      technical_attempt_dir: technicalAttempt,
    }),
    "utf8",
  );

  const criterion = {
    paper_stems: ["01_Szabo2010"],
    normalized_paper_stems: ["01_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [{ id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." }],
  };
  const registry = {
    version: 1,
    criteria: [criterion],
    criteriaByPaperStem: new Map([["01_szabo2010", criterion]]),
  };
  const summary = {
    benchmarkRunDir: root,
    results: [
      {
        paper: "01_Szabo2010.pdf",
        pdfPath: "benchmark_papers/01_Szabo2010.pdf",
        mode: "morpheus_mcp",
        runId: "run_szabo",
        repetition: 1,
        runManifestPath: path.join(runDir, "run_manifest.json"),
      },
    ],
  };

  const jobs = await discoverBiologicalScoringJobs(summary, registry);

  assert.equal(jobs.length, 0);
});

test("discoverBiologicalScoringJobs includes dat files as tabular scoring evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-dat-"));
  const runDir = path.join(root, "run_thapa");
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  await mkdir(attemptDir, { recursive: true });
  await writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(attemptDir, "CANCER_displacement.dat"), "#Time POP_SUM MSD CELL-TRAJECTORIES...\n0 0 0 1\n", "utf8");
  await writeFile(path.join(attemptDir, "stdout.log"), "Time: 100\n", "utf8");
  await writeFile(path.join(runDir, "run_manifest.json"), JSON.stringify({ run_id: "run_thapa" }), "utf8");

  const criterion = {
    paper_stems: ["02_Thapa2024"],
    normalized_paper_stems: ["02_thapa2024"],
    target: "Cancer growth ratios",
    scoring_instructions: "Score numeric outputs.",
    clauses: [{ id: "growth", kind: "numeric" as const, weight: 1, description: "Growth ratio." }],
  };
  const registry = {
    version: 1,
    criteria: [criterion],
    criteriaByPaperStem: new Map([["02_thapa2024", criterion]]),
  };
  const summary = {
    benchmarkRunDir: root,
    results: [
      {
        paper: "02_Thapa2024.pdf",
        pdfPath: path.join("benchmark_papers", "02_Thapa2024.pdf"),
        mode: "morpheus_cli_docs",
        runId: "run_thapa",
        repetition: 1,
        runManifestPath: path.join(runDir, "run_manifest.json"),
      },
    ],
  };

  const jobs = await discoverBiologicalScoringJobs(summary, registry);

  assert.equal(jobs.length, 1);
});

test("runBiologicalScoringForBenchmark writes comparison files into the local benchmark dir", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-summary-"));
  const criteriaPath = path.join(root, "criteria.json");
  await writeFile(criteriaPath, JSON.stringify({ version: 1, criteria: [] }), "utf8");
  await writeFile(
    path.join(root, "benchmark_summary.json"),
    JSON.stringify({
      benchmarkRunDir: "E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\20260524_002842_benchmark",
      comparisonJsonPath:
        "E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\20260524_002842_benchmark\\benchmark_comparison.json",
      comparisonCsvPath:
        "E:\\PycharmProjects\\Morpheus.AI\\benchmark_runs\\20260524_002842_benchmark\\benchmark_comparison.csv",
      generatedAt: "2026-05-24T00:28:42.000Z",
      config: { benchmarkModes: ["morpheus_mcp"] },
      results: [],
    }),
    "utf8",
  );
  const config = {
    papersDir: path.join(root, "papers"),
    resultsDir: path.dirname(root),
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
    biologicalScoringCriteriaPath: criteriaPath,
    biologicalScoringModel: "gpt-5.4-mini",
    biologicalScoringReasoningEffort: "low",
    biologicalScoringMaxConcurrentJobs: 4,
    biologicalScoringTurnTimeoutMs: 1000,
    mcpCommand: ["python", "server.py"],
    mcpToolTimeoutMs: 1000,
    bridgeToolTimeoutMs: 1000,
    morpheusRunTimeoutMs: 1000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: path.resolve("src/benchmark/MorpheusML.xsd"),
    skillPaths: [],
  } satisfies BenchmarkConfig;

  const progress: string[] = [];
  const updated = await runBiologicalScoringForBenchmark(root, config, (message) => {
    progress.push(message);
  }, undefined, { writeDetailWorkbook: false });

  assert.equal(await readFile(path.join(root, "benchmark_comparison.json"), "utf8").then(Boolean), true);
  assert.equal(await readFile(path.join(root, "benchmark_comparison.csv"), "utf8").then(Boolean), true);
  assert.equal(
    updated.config.biologicalScoringMaxConcurrentJobs,
    process.platform === "win32" ? 1 : 4,
  );
  if (process.platform === "win32") {
    assert.ok(progress.includes(
      "Native Windows uses serial biological scoring; requested concurrency=4 was reduced to concurrency=1. Use Linux or WSL2 for parallel jobs.",
    ));
  }
});

test("runBiologicalScoringForBenchmark marks matched runs without scoreable artifacts as insufficient evidence", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-bio-missing-score-"));
  const runDir = path.join(root, "run_szabo");
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  const criteriaPath = path.join(root, "criteria.json");
  await mkdir(attemptDir, { recursive: true });
  await writeFile(path.join(attemptDir, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({ run_id: "run_szabo", technical_attempt_dir: attemptDir }),
    "utf8",
  );
  await writeFile(
    criteriaPath,
    JSON.stringify({
      version: 1,
      criteria: [
        {
          paper_stems: ["01_Szabo2010"],
          target: "Dense monolayer",
          scoring_instructions: "Score observed CSVs or images.",
          clauses: [{ id: "volume", kind: "numeric", weight: 1, description: "Volume below threshold." }],
        },
      ],
    }),
    "utf8",
  );
  await writeFile(
    path.join(root, "benchmark_summary.json"),
    JSON.stringify({
      benchmarkRunDir: root,
      benchmarkId: "benchmark",
      comparisonJsonPath: path.join(root, "benchmark_comparison.json"),
      comparisonCsvPath: path.join(root, "benchmark_comparison.csv"),
      startedAt: "2026-05-24T00:00:00.000Z",
      finishedAt: "2026-05-24T00:01:00.000Z",
      generatedAt: "2026-05-24T00:01:00.000Z",
      durationMs: 60_000,
      diagnostics: {
        turnCount: 0,
        attemptCount: 0,
        agentWallTimeMs: 0,
        morpheusSimulationTimeMs: 0,
        agentAnalysisTimeMs: 0,
        hostMorpheusRunTimeMs: 0,
        hostTechnicalEvaluationTimeMs: 0,
        tokens: { input: 0, cachedInput: 0, output: 0, reasoningOutput: 0, total: 0 },
      },
      totalRuns: 1,
      uniquePapers: 1,
      benchmarkRepetitions: 1,
      totalPapers: 1,
      totalModelRefinements: 0,
      averageModelRefinements: 0,
      totalTechnicalScore: 0,
      averageTechnicalScore: null,
      totalReproductionScore: 0,
      averageReproductionScore: null,
      averageBiologicalScore: null,
      config: { benchmarkModes: ["morpheus_mcp"] },
      results: [
        {
          paper: "01_Szabo2010.pdf",
          pdfPath: "benchmark_papers/01_Szabo2010.pdf",
          mode: "morpheus_mcp",
          modeLabel: "Morpheus MCP",
          capabilities: {},
          capabilityViolations: [],
          runId: "run_szabo",
          threadId: null,
          repetition: 1,
          startedAt: null,
          finishedAt: null,
          durationMs: 0,
          diagnostics: {
            turnCount: 0,
            attemptCount: 0,
            agentWallTimeMs: 0,
            morpheusSimulationTimeMs: 0,
            agentAnalysisTimeMs: 0,
            hostMorpheusRunTimeMs: 0,
            hostTechnicalEvaluationTimeMs: 0,
            tokens: { input: 0, cachedInput: 0, output: 0, reasoningOutput: 0, total: 0 },
          },
          attempts: 1,
          modelRefinementCount: 0,
          technicalScore: null,
          reproductionScore: null,
          technicalEvaluationPath: null,
          reproductionReportPath: null,
          reproductionReportTextPath: null,
          runManifestPath: path.join(runDir, "run_manifest.json"),
          benchmarkFocus: null,
          summary: "Completed without scoreable outputs.",
        },
      ],
    }),
    "utf8",
  );
  const config = {
    papersDir: path.join(root, "papers"),
    resultsDir: path.dirname(root),
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
    biologicalScoringCriteriaPath: criteriaPath,
    biologicalScoringModel: "gpt-5.4-mini",
    biologicalScoringReasoningEffort: "low",
    biologicalScoringMaxConcurrentJobs: 1,
    biologicalScoringTurnTimeoutMs: 1000,
    mcpCommand: ["python", "server.py"],
    mcpToolTimeoutMs: 1000,
    bridgeToolTimeoutMs: 1000,
    morpheusRunTimeoutMs: 1000,
    morpheusNumThreads: null,
    morpheusXmlSchemaPath: path.resolve("src/benchmark/MorpheusML.xsd"),
    skillPaths: [],
  } satisfies BenchmarkConfig;

  const progress: string[] = [];
  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    (message) => progress.push(message),
    undefined,
    { writeDetailWorkbook: false },
  );
  const scorePath = summary.results[0].biologicalScorePath!;
  const score = JSON.parse(await readFile(scorePath, "utf8"));
  const scoreText = await readFile(scorePath.replace(/\.json$/, ".txt"), "utf8");

  assert.equal(summary.results[0].biologicalScore, null);
  assert.match(scorePath, /biological_scores[\\/]scorer-v8__/);
  assert.equal(summary.averageBiologicalScore, null);
  assert.equal(score.status, "insufficient_evidence");
  assert.equal(score.score, null);
  assert.deepEqual(score.clauses, []);
  assert.equal(score.scorerVersion, BIOLOGICAL_SCORER_VERSION);
  assert.deepEqual(score.scoringImagePaths, []);
  assert.equal(score.scorerModel, config.biologicalScoringModel);
  assert.equal(score.scorerReasoningEffort, config.biologicalScoringReasoningEffort);
  assert.match(score.criteriaSha256, /^[a-f0-9]{64}$/);
  assert.match(score.attemptIdentity, /^[a-f0-9]{64}$/);
  assert.equal(score.criteriaVersion, 1);
  assert.match(scoreText, /insufficient_evidence/);
  assert.ok(progress.some((message) => /Biological scoring benchmark/.test(message) && /matchedResults=1/.test(message)));
  assert.ok(progress.some((message) => /Biological scoring run_szabo skipped/.test(message) && /insufficient evidence/.test(message)));
  assert.ok(progress.some((message) => /Biological scoring complete/.test(message) && /missingArtifacts=1/.test(message)));
  const scoringLog = await readFile(path.join(root, "scoring.log"), "utf8");
  assert.match(scoringLog, /Biological scoring benchmark/);
  assert.match(scoringLog, /Biological scoring run_szabo skipped/);
  assert.match(scoringLog, /Biological scoring complete/);
});

test("runBiologicalScoringForBenchmark scores an explicitly failed canonical model as zero", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  await rm(path.join(attemptDir, "logger.csv"));
  await rm(path.join(attemptDir, "plot_00010.png"));

  const initialSummary = await runBiologicalScoringForBenchmark(root, config, () => {}, undefined, {
    writeDetailWorkbook: false,
  });
  const initialScorePath = initialSummary.results[0].biologicalScorePath!;
  const initialScore = JSON.parse(await readFile(initialScorePath, "utf8"));
  assert.equal(initialScore.status, "insufficient_evidence");
  assert.equal(initialSummary.results[0].biologicalScore, null);
  assert.equal(initialSummary.results[0].biologicalScoringStatus, "insufficient_evidence");
  assert.equal(initialSummary.averageBiologicalScoreValidOnly, null);
  assert.equal(initialSummary.averageBiologicalScoreItt, 0);

  await writeFile(
    path.join(runDir, "run_manifest.json"),
    JSON.stringify({
      run_id: "run_szabo",
      latest_attempt_id: "attempt_001",
      latest_attempt_returncode: 1,
      latest_attempt_timed_out: false,
      attempt_history: [{ attempt_id: "attempt_001", returncode: 1, timed_out: false }],
    }),
    "utf8",
  );

  const progress: string[] = [];
  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    (message) => progress.push(message),
    async () => {
      throw new Error("scoring agent should not run for an explicitly failed model");
    },
    { skipScoredAttempts: true, writeDetailWorkbook: false },
  );
  const scorePath = summary.results[0].biologicalScorePath!;
  const score = JSON.parse(await readFile(scorePath, "utf8"));
  const scoreText = await readFile(scorePath.replace(/\.json$/, ".txt"), "utf8");

  assert.equal(scorePath, initialScorePath);
  assert.equal(summary.results[0].biologicalScore, 0);
  assert.equal(summary.averageBiologicalScore, 0);
  assert.equal(summary.averageBiologicalScoreValidOnly, 0);
  assert.equal(summary.averageBiologicalScoreItt, 0);
  assert.equal(score.status, "model_failed");
  assert.equal(score.score, 0);
  assert.deepEqual(score.clauses, []);
  assert.match(score.summary, /nonzero exit code 1/);
  assert.match(scoreText, /model_failed/);
  assert.ok(progress.some((message) => /model failed/.test(message) && /score=0/.test(message)));
  assert.ok(progress.some((message) => /missingArtifacts=0/.test(message) && /modelFailures=1/.test(message)));
});

test("runBiologicalScoringForBenchmark logs scoring agent backend failures and writes failure JSON", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  const progress: string[] = [];

  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    (message) => progress.push(message),
    async () => {
      const outputPath = path.join(runDir, "biological_score.json");
      await writeFile(
        outputPath,
        JSON.stringify({
          ok: false,
          status: "scoring_failed",
          score: null,
          summary: "OpenAI API 500 while scoring biology.",
          clauses: [],
          limitations: ["OpenAI API 500 while scoring biology."],
        }),
        "utf8",
      );
      await writeFile(path.join(runDir, "biological_score.txt"), "Status: scoring_failed\n", "utf8");
      return {
        score: null,
        path: outputPath,
        status: "scoring_failed",
        error: "OpenAI API 500 while scoring biology.",
      };
    },
    { writeDetailWorkbook: false },
  );
  const outputPath = path.join(runDir, "biological_score.json");
  const score = JSON.parse(await readFile(outputPath, "utf8"));

  assert.equal(summary.results[0].biologicalScore, null);
  assert.equal(summary.results[0].biologicalScorePath, outputPath);
  assert.equal(summary.averageBiologicalScore, null);
  assert.equal(score.status, "scoring_failed");
  assert.match(score.summary, /OpenAI API 500/);
  assert.ok(progress.some((message) => /Biological scoring 1\/1 starting/.test(message) && /run_szabo/.test(message)));
  assert.ok(progress.some((message) => /Biological scoring 1\/1 failed/.test(message) && /OpenAI API 500/.test(message)));
  assert.ok(progress.some((message) => /Biological scoring complete/.test(message) && /failed=1/.test(message)));
  const scoringLog = await readFile(path.join(root, "scoring.log"), "utf8");
  assert.match(scoringLog, /Biological scoring 1\/1 starting/);
  assert.match(scoringLog, /Biological scoring 1\/1 failed/);
  assert.match(scoringLog, /OpenAI API 500/);
});

test("runBiologicalScoringForBenchmark skips existing scores for the current attempt when requested", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  const registry = await loadBiologicalScoringCriteria(config.biologicalScoringCriteriaPath);
  const benchmarkSummary = JSON.parse(await readFile(path.join(root, "benchmark_summary.json"), "utf8"));
  const [job] = await discoverBiologicalScoringJobs(benchmarkSummary, registry, { benchmarkDir: root });
  const outputPath = path.join(runDir, "biological_score.json");
  await writeFile(
    outputPath,
    JSON.stringify({
      ok: true,
      status: "scored",
      score: 0.75,
      scorerVersion: BIOLOGICAL_SCORER_VERSION,
      scorerModel: config.biologicalScoringModel,
      scorerReasoningEffort: config.biologicalScoringReasoningEffort,
      criteriaVersion: 1,
      criteriaSha256: job.criteriaSha256,
      attemptIdentity: job.attemptIdentity,
      attemptId: "attempt_001",
      attemptDir: path.join("attempts", "attempt_001"),
      clauses: [],
      summary: "Already scored.",
      limitations: [],
    }),
    "utf8",
  );
  const progress: string[] = [];

  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    (message: string) => progress.push(message),
    async () => {
      throw new Error("scoring agent should not run for an already-scored attempt");
    },
    { skipScoredAttempts: true, writeDetailWorkbook: false },
  );

  assert.equal(summary.results[0].biologicalScore, 0.75);
  assert.equal(summary.results[0].biologicalScorePath, outputPath);
  assert.ok(progress.some((message) => /skipped/.test(message) && /existing biological score/.test(message)));
  const scoringLog = await readFile(path.join(root, "scoring.log"), "utf8");
  assert.match(scoringLog, /existing biological score/);
});

test("runBiologicalScoringForBenchmark invalidates a cached score when attempt artifacts change", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  const registry = await loadBiologicalScoringCriteria(config.biologicalScoringCriteriaPath);
  const benchmarkSummary = JSON.parse(await readFile(path.join(root, "benchmark_summary.json"), "utf8"));
  const [job] = await discoverBiologicalScoringJobs(benchmarkSummary, registry, { benchmarkDir: root });
  const outputPath = path.join(runDir, "biological_score.json");
  await writeFile(outputPath, JSON.stringify({
    ok: true,
    status: "scored",
    score: 0.75,
    scorerVersion: BIOLOGICAL_SCORER_VERSION,
    scorerModel: config.biologicalScoringModel,
    scorerReasoningEffort: config.biologicalScoringReasoningEffort,
    criteriaVersion: 1,
    criteriaSha256: job.criteriaSha256,
    attemptIdentity: job.attemptIdentity,
    attemptId: job.attemptId,
    attemptDir: path.relative(job.runDir, job.attemptDir),
  }), "utf8");
  await writeFile(path.join(job.attemptDir, "logger.csv"), "time,count\n0,1\n1,2\n", "utf8");
  let scoringCalls = 0;

  await runBiologicalScoringForBenchmark(root, config, () => {}, async () => {
    scoringCalls += 1;
    return { score: 0.5, path: outputPath, status: "scored" };
  }, { skipScoredAttempts: true, writeDetailWorkbook: false });

  assert.equal(scoringCalls, 1);
});

test("runBiologicalScoringForBenchmark rescoring ignores cached scores from old scorer or criteria versions", async () => {
  for (const staleVersions of [
    { scorerVersion: BIOLOGICAL_SCORER_VERSION - 1, criteriaVersion: 1 },
    { scorerVersion: BIOLOGICAL_SCORER_VERSION, criteriaVersion: 0 },
  ]) {
    const { root, runDir, config } = await createScoreableBiologicalBenchmark();
    const outputPath = path.join(runDir, "biological_score.json");
    await writeFile(
      outputPath,
      JSON.stringify({
        ok: true,
        status: "scored",
        score: 0.75,
        ...staleVersions,
        attemptId: "attempt_001",
        attemptDir: path.join("attempts", "attempt_001"),
        clauses: [],
        summary: "Stale score.",
        limitations: [],
      }),
      "utf8",
    );
    let scoringCalls = 0;

    const summary = await runBiologicalScoringForBenchmark(
      root,
      config,
      () => {},
      async (job) => {
        scoringCalls += 1;
        await writeFile(
          outputPath,
          JSON.stringify({
            ok: true,
            status: "scored",
            score: 0.5,
            scorerVersion: 1,
            criteriaVersion: 1,
            attemptId: job.attemptId,
            attemptDir: path.relative(job.runDir, job.attemptDir),
            clauses: [],
            summary: "Fresh score.",
            limitations: [],
          }),
          "utf8",
        );
        return { score: 0.5, path: outputPath, status: "scored" };
      },
      { skipScoredAttempts: true, writeDetailWorkbook: false },
    );

    assert.equal(scoringCalls, 1);
    assert.equal(summary.results[0].biologicalScore, 0.5);
  }
});

test("runBiologicalScoringForBenchmark scores recovered newer attempts despite an old missing-artifacts zero", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  await writeFile(
    path.join(runDir, "biological_score.json"),
    JSON.stringify({
      ok: true,
      status: "missing_scoreable_artifacts",
      score: 0,
      attemptId: "attempt_001",
      attemptDir: path.join("attempts", "attempt_001"),
      clauses: [],
      summary: "Old missing attempt.",
      limitations: [],
    }),
    "utf8",
  );
  const recoveredAttemptDir = path.join(runDir, "attempts", "attempt_002");
  await mkdir(recoveredAttemptDir, { recursive: true });
  await writeFile(path.join(recoveredAttemptDir, "model.xml"), "<MorpheusModel />", "utf8");
  await writeFile(path.join(recoveredAttemptDir, "logger.csv"), "time,count\n0,2\n", "utf8");
  const seenAttempts: string[] = [];

  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    () => {},
    async (job) => {
      seenAttempts.push(job.attemptId);
      const outputPath = path.join(runDir, "biological_score.json");
      await writeFile(
        outputPath,
        JSON.stringify({
          ok: true,
          status: "scored",
          score: 0.6,
          attemptId: job.attemptId,
          attemptDir: path.relative(job.runDir, job.attemptDir),
          clauses: [],
          summary: "Recovered attempt scored.",
          limitations: [],
        }),
        "utf8",
      );
      return { score: 0.6, path: outputPath, status: "scored" };
    },
    { skipScoredAttempts: true, writeDetailWorkbook: false },
  );

  assert.deepEqual(seenAttempts, ["attempt_002"]);
  assert.equal(summary.results[0].biologicalScore, 0.6);
});

test("runBiologicalScoringForBenchmark rewrites old missing-artifacts zeros as insufficient evidence", async () => {
  const { root, runDir, config } = await createScoreableBiologicalBenchmark();
  const attemptDir = path.join(runDir, "attempts", "attempt_001");
  await rm(path.join(attemptDir, "logger.csv"));
  await rm(path.join(attemptDir, "plot_00010.png"));
  await writeFile(path.join(runDir, "biological_score.json"), JSON.stringify({
    ok: true,
    status: "missing_scoreable_artifacts",
    score: 0,
    clauses: [],
    summary: "Old missing score without attempt metadata.",
    limitations: [],
  }), "utf8");

  const summary = await runBiologicalScoringForBenchmark(
    root,
    config,
    () => {},
    async () => {
      throw new Error("scoring agent should not run without scoreable artifacts");
    },
    { skipScoredAttempts: true, writeDetailWorkbook: false },
  );
  const oldScore = JSON.parse(await readFile(path.join(runDir, "biological_score.json"), "utf8"));
  const score = JSON.parse(await readFile(summary.results[0].biologicalScorePath!, "utf8"));

  assert.equal(summary.results[0].biologicalScore, null);
  assert.equal(score.status, "insufficient_evidence");
  assert.equal(score.score, null);
  assert.equal(score.attemptId, "attempt_001");
  assert.equal(score.attemptDir, path.join("attempts", "attempt_001"));
  assert.equal(oldScore.status, "missing_scoreable_artifacts");
});

test("buildBiologicalScoringPrompt allows XML mechanism evidence when outputs exist", () => {
  const prompt = buildBiologicalScoringPrompt({
    result: {},
    criterion: {
      paper_stems: ["13_Mole2026"],
      normalized_paper_stems: ["13_mole2026"],
      target: "Blastocyst implantation",
      scoring_instructions: "Use output images and model mechanisms.",
      clauses: [
        {
          id: "chemotaxis_to_gland",
          kind: "qualitative",
          weight: 1,
          description: "The blastocyst moves or is biased toward the gland.",
        },
      ],
    },
    paper: "13_Mole2026.pdf",
    mode: "morpheus_mcp",
    repetition: 1,
    runId: "run_mole",
    runDir: "/tmp/run_mole",
    attemptId: "attempt_001",
    attemptDir: "/tmp/run_mole/attempts/attempt_001",
    criteriaVersion: 1,
  });

  assert.match(prompt, /score observed biological outcomes, not model intent/i);
  assert.doesNotMatch(prompt, /completed Morpheus benchmark attempt/i);
  assert.match(prompt, /use model XML to verify intended mechanisms/i);
  assert.match(prompt, /intended mechanism clauses can be supported by model XML/i);
  assert.match(prompt, /realized biological outcome clauses require direct output evidence/i);
  assert.match(prompt, /Do not pass realized outcome clauses from model XML or initial conditions alone/i);
  assert.doesNotMatch(prompt, /Do not pass dynamic qualitative clauses from model XML alone/);
  assert.match(
    prompt,
    /inspect the available model\.xml, CSV files, other outputs, logs, and images/i,
  );
  assert.match(prompt, /current read-only working directory is the canonical attempt directory/i);
  assert.doesNotMatch(prompt, /Run directory:/i);
  assert.doesNotMatch(prompt, /Attempt directory:/i);
  assert.doesNotMatch(prompt, /plot_00100\.png/i);
});

test("buildBiologicalScoringInput attaches canonical images with a labeled evidence manifest", () => {
  const job = {
    result: {},
    criterion: {
      paper_stems: ["12_Malkmus2025"],
      normalized_paper_stems: ["12_malkmus2025"],
      target: "Spatial pattern formation",
      scoring_instructions: "Score the observed pattern and dynamics.",
      clauses: [
        {
          id: "pattern",
          kind: "qualitative",
          weight: 1,
          description: "The output forms the requested spatial pattern over time.",
        },
      ],
    },
    paper: "12_Malkmus2025.pdf",
    mode: "morpheus_mcp",
    repetition: 2,
    runId: "run_malkmus",
    runDir: "/tmp/run_malkmus",
    attemptId: "attempt_002",
    attemptDir: "/tmp/run_malkmus/attempts/attempt_002",
    criteriaVersion: 1,
    scoringImages: [
      {
        path: "/tmp/run_malkmus/attempts/attempt_002/plot_00000.png",
        series: "plot",
        position: "early",
      },
      {
        path: "/tmp/run_malkmus/attempts/attempt_002/plot_00080.png",
        series: "plot",
        position: "final",
      },
    ],
  } as BiologicalScoringJob & {
    scoringImages: Array<{ path: string; series: string; position: string }>;
  };
  const input = buildBiologicalScoringInput(job);
  const prompt = buildBiologicalScoringPrompt(job);

  assert.deepEqual(input, [
    { type: "text", text: prompt },
    { type: "local_image", path: job.scoringImages[0].path },
    { type: "local_image", path: job.scoringImages[1].path },
  ]);
  assert.match(prompt, /attached canonical visual evidence/i);
  assert.match(prompt, /IMAGE_01.*plot_00000\.png.*series plot.*early/i);
  assert.match(prompt, /IMAGE_02.*plot_00080\.png.*series plot.*final/i);
  assert.match(prompt, /cite.*IMAGE_NN.*paths.*qualitative/i);
  assert.match(prompt, /do not infer unseen frames/i);
  assert.doesNotMatch(prompt, /view_image/i);
});

test("buildBiologicalScoringPrompt requires reproducible numeric evidence and scores the observed endpoint", () => {
  const prompt = buildBiologicalScoringPrompt({
    result: {},
    criterion: {
      paper_stems: ["02_Thapa2024"],
      normalized_paper_stems: ["02_thapa2024"],
      target: "Cancer growth ratios",
      scoring_instructions: "Use all available observed outputs.",
      clauses: [
        {
          id: "cancer_growth",
          kind: "numeric",
          weight: 1,
          description: "Cancer count growth ratio is in range.",
        },
      ],
    },
    paper: "02_Thapa2024.pdf",
    mode: "morpheus_cli_docs",
    repetition: 2,
    runId: "run_thapa",
    runDir: "/tmp/run_thapa",
    attemptId: "attempt_002",
    attemptDir: "/tmp/run_thapa/attempts/attempt_002",
    criteriaVersion: 1,
  });

  assert.match(prompt, /best available observed evidence/i);
  assert.match(prompt, /exact rows.*columns.*formula.*units/i);
  assert.match(prompt, /do not estimate.*image.*machine-readable numeric evidence/i);
  assert.match(prompt, /CELL-TRAJECTORIES/i);
  assert.match(prompt, /do not fail solely because an expected logger CSV is missing/i);
  assert.match(prompt, /Initial conditions may support only baseline or static numeric clauses/i);
  assert.match(prompt, /Never use initial conditions as evidence for dynamic behavior or final outcomes/i);
  assert.match(prompt, /crashed, stopped early, timed out, or never reached/i);
  assert.match(prompt, /latest output actually produced.*observed endpoint/i);
  assert.match(prompt, /nonzero exit.*limitation.*not.*automatic clause failure/i);
  assert.match(prompt, /Do not pass a clause from model XML or initial conditions alone/i);
  assert.match(prompt, /For crashed or truncated runs, output evidence must directly show each dynamic or realized outcome/i);
  assert.match(prompt, /XML or initial conditions are not enough for dynamic or realized outcomes/i);
  assert.doesNotMatch(prompt, /CANCER_displacement\.dat/i);
  assert.doesNotMatch(prompt, /stdout\.log/i);
});

test("biological scorer gives Codex the canonical attempt and reference agent workspace", () => {
  const job: BiologicalScoringJob = {
    result: {},
    criterion: {
      paper_stems: ["01_Szabo2010"],
      normalized_paper_stems: ["01_szabo2010"],
      target: "Dense monolayer",
      scoring_instructions: "Inspect observed outputs.",
      clauses: [{ id: "volume", kind: "numeric", weight: 1, description: "Volume is in range." }],
    },
    paper: "01_Szabo2010.pdf",
    mode: "morpheus_mcp",
    repetition: 1,
    runId: "run_szabo",
    runDir: "/tmp/run_szabo",
    attemptId: "attempt_001",
    attemptDir: "/tmp/run_szabo/attempts/attempt_001",
    criteriaVersion: 1,
  };
  const threadOptions = buildBiologicalScoringThreadOptions(job, {
    model: "gpt-5.6-sol",
    reasoningEffort: "medium",
  });
  const input = buildBiologicalScoringInput(job);

  assert.equal(threadOptions.workingDirectory, path.resolve(job.attemptDir));
  assert.equal(threadOptions.sandboxMode, "read-only");
  assert.equal(threadOptions.networkAccessEnabled, false);
  assert.equal(threadOptions.webSearchMode, "disabled");
  assert.deepEqual(threadOptions.additionalDirectories, [path.resolve(job.runDir, "agent_workspace")]);
  assert.deepEqual(input, [{ type: "text", text: buildBiologicalScoringPrompt(job) }]);

  const prompt = buildBiologicalScoringPrompt(job);
  assert.match(prompt, /working directory is the canonical attempt directory/i);
  assert.match(prompt, /score only the model\.xml and simulation outputs in the canonical attempt directory/i);
  assert.match(prompt, /agent workspace.*reference/i);
  assert.ok(prompt.includes(path.resolve(job.runDir, "agent_workspace")));
  assert.match(prompt, /assets referenced by the canonical model\.xml/i);
  assert.match(prompt, /model-defined propert.*referenced asset.*valid evidence/i);
  assert.match(prompt, /do not score.*model\.xml.*agent workspace/i);
  assert.match(prompt, /Morpheus skill.*interpret/i);
  assert.match(prompt, /do not run or rerun.*modify.*repair/i);
});

test("biological scorer ignores a machine-specific recovered skill path", () => {
  const localSkillPath = path.resolve(".agents", "skills", "morpheus", "SKILL.md");
  const config = biologicalTestConfig("/tmp/benchmark", "/tmp/criteria.json");
  config.skillPaths = [path.resolve("E:\\PycharmProjects\\Morpheus.AI\\.agents\\skills\\morpheus\\SKILL.md")];
  const codexHomeDir = "/tmp/scoring-codex-home";
  const setup = buildBiologicalScoringCodexSetup(config, codexHomeDir);

  assert.deepEqual(setup.skillPaths, [localSkillPath]);
  assert.equal(setup.codexConfig.mcp_servers, undefined);
  assert.equal(setup.codexConfig.plugins, undefined);
  const skills = setup.codexConfig.skills as { config: Array<{ path: string; enabled: boolean }> };
  assert.deepEqual(skills.config.filter((entry) => entry.enabled), [{
    path: path.join(codexHomeDir, "skills", "morpheus", "SKILL.md"),
    enabled: true,
  }]);
});

test("createBiologicalScoringCodex installs the benchmark executor so the turn watchdog applies", () => {
  const config = biologicalTestConfig("/tmp/benchmark", "/tmp/criteria.json");
  const codexHomeDir = "/tmp/scoring-codex-home";
  const codex = createBiologicalScoringCodex(
    config,
    buildBiologicalScoringCodexSetup(config, codexHomeDir).codexConfig,
    codexHomeDir,
    123_000,
  );
  const exec = (codex as unknown as { exec: { run: { name: string }; envOverride: Record<string, string> } }).exec;

  assert.equal(exec.run.name, "bound benchmarkCodexExecRun");
  assert.equal(exec.envOverride.CODEX_EXEC_TURN_TIMEOUT_MS, "123000");
  assert.equal(exec.envOverride.CODEX_HOME, codexHomeDir);
});

test("biological scorer provenance folders are cohort- and attempt-specific siblings of the score JSON", () => {
  const provenance = {
    scorerModel: "gpt-5.6-sol",
    scorerReasoningEffort: "medium",
    criteriaVersion: 5,
    criteriaSha256: "a".repeat(64),
    attemptIdentity: "b".repeat(64),
  };
  const runDir = path.join("/tmp", "benchmark", "run");
  const dir = biologicalScoreProvenanceDir(runDir, provenance);

  assert.equal(
    dir,
    path.join(runDir, "biological_scores", `${biologicalScoreVariantKey(provenance)}__attempt-${"b".repeat(12)}`),
  );
  assert.notEqual(dir, biologicalScoreProvenanceDir(runDir, { ...provenance, scorerReasoningEffort: "high" }));
  assert.notEqual(dir, biologicalScoreProvenanceDir(runDir, { ...provenance, attemptIdentity: "c".repeat(64) }));
  assert.equal(dir.endsWith(".json"), false);
});

test("biologicalIttScore zero-fills subject failures but excludes scorer failures and unscored runs", () => {
  assert.equal(biologicalIttScore({ biologicalScore: 0.5, biologicalScoringStatus: "scored" }), 0.5);
  assert.equal(biologicalIttScore({ biologicalScore: 0, biologicalScoringStatus: "model_failed" }), 0);
  assert.equal(biologicalIttScore({ biologicalScore: null, biologicalScoringStatus: "insufficient_evidence" }), 0);
  assert.equal(biologicalIttScore({ biologicalScore: null, biologicalScoringStatus: "scoring_failed" }), null);
  assert.equal(biologicalIttScore({ biologicalScore: undefined, biologicalScoringStatus: undefined }), null);
});

test("buildBiologicalScoringPrompt leaves phenotype definitions to the supplied criterion", () => {
  const prompt = buildBiologicalScoringPrompt({
    result: {},
    criterion: {
      paper_stems: ["15_Reza2025"],
      normalized_paper_stems: ["15_reza2025"],
      target: "A paper-specific morphology",
      scoring_instructions: "Use output images and logs.",
      clauses: [
        {
          id: "paper_specific_shape",
          kind: "qualitative",
          weight: 1,
          description: "The final output has the shape defined for this paper.",
        },
      ],
    },
    paper: "15_Reza2025.pdf",
    mode: "python_web",
    repetition: 1,
    runId: "run_reza",
    runDir: "/tmp/run_reza",
    attemptId: "attempt_001",
    attemptDir: "/tmp/run_reza/attempts/attempt_001",
    criteriaVersion: 1,
  });

  assert.match(prompt, /When qualitative outcome evidence is ambiguous, fail the clause/i);
  assert.match(prompt, /apply each clause description literally/i);
  assert.match(prompt, /do not substitute a stricter general definition/i);
  assert.doesNotMatch(prompt, /lumen or hollow tube requires/i);
  assert.doesNotMatch(prompt, /fusion or organoid formation requires/i);
  assert.doesNotMatch(prompt, /Turing, digit, or spot pattern clauses require/i);
  assert.doesNotMatch(prompt, /Growth requires direct early-to-late increase/i);
  assert.match(prompt, /Do not compensate for weak outputs because a benchmark mode is limited/i);
});

test("parseCliArgs parses biological scoring options", () => {
  const parsed = parseCliArgs([
    "--score-biological",
    "--biological-scoring-model",
    "gpt-5.4-mini",
    "--biological-scoring-reasoning-effort",
    "low",
    "--biological-scoring-max-concurrent-jobs",
    "3",
    "--biological-scoring-turn-timeout-ms",
    "120000",
  ]);

  assert.equal(parsed.scoreBiological, true);
  assert.equal(parsed.overrides.biologicalScoringModel, "gpt-5.4-mini");
  assert.equal(parsed.overrides.biologicalScoringReasoningEffort, "low");
  assert.equal(parsed.overrides.biologicalScoringMaxConcurrentJobs, 3);
  assert.equal(parsed.overrides.biologicalScoringTurnTimeoutMs, 120000);
});

test("parseBiologicalScoringCliArgs parses standalone scoring overrides", () => {
  const parsed = parseBiologicalScoringCliArgs([
    "/tmp/benchmark_run",
    "--model",
    "gpt-5.5",
    "--reasoning-effort",
    "low",
    "--max-concurrent-jobs",
    "4",
    "--criteria-path",
    "custom-criteria.json",
    "--turn-timeout-ms",
    "120000",
    "--skip-scored-attempts",
  ]);

  assert.equal(parsed.benchmarkDir, "/tmp/benchmark_run");
  assert.equal(parsed.overrides.biologicalScoringModel, "gpt-5.5");
  assert.equal(parsed.overrides.biologicalScoringReasoningEffort, "low");
  assert.equal(parsed.overrides.biologicalScoringMaxConcurrentJobs, 4);
  assert.equal(parsed.overrides.biologicalScoringCriteriaPath, "custom-criteria.json");
  assert.equal(parsed.overrides.biologicalScoringTurnTimeoutMs, 120000);
  assert.equal(parsed.skipScoredAttempts, true);
});

test("biologicalScoreVariantKey names the cohort shared by every run scored the same way", () => {
  const key = biologicalScoreVariantKey({
    scorerModel: "gpt-5.6 sol",
    scorerReasoningEffort: "high",
    criteriaVersion: 3,
    criteriaSha256: "1adfb5d366a0ef41e132dd152164aaff",
  });

  assert.equal(key, `scorer-v${BIOLOGICAL_SCORER_VERSION}__gpt-5.6-sol__high__criteria-v3-1adfb5d366a0`);
});

test("biologicalScoreVariantKey falls back to an unknown criteria marker", () => {
  const key = biologicalScoreVariantKey({
    scorerModel: "gpt-5.6-sol",
    scorerReasoningEffort: "medium",
    criteriaVersion: 2,
    criteriaSha256: "",
  });

  assert.equal(key, `scorer-v${BIOLOGICAL_SCORER_VERSION}__gpt-5.6-sol__medium__criteria-v2-unknown`);
});

test("buildBiologicalScoreWorkbookArgs targets one variant of one benchmark", () => {
  const args = buildBiologicalScoreWorkbookArgs("/tmp/benchmark_run", "scorer-v7__gpt-5.6-sol__high__criteria-v3-abc", "criteria.json");

  assert.equal(args[0], path.resolve(process.cwd(), BIOLOGICAL_SCORE_DETAILS_SCRIPT));
  assert.deepEqual(args.slice(1), [
    "/tmp/benchmark_run",
    "--variant",
    "scorer-v7__gpt-5.6-sol__high__criteria-v3-abc",
    "--criteria-path",
    path.resolve("criteria.json"),
  ]);
});

test("parseBiologicalScoringCliArgs rejects the removed no-score-workbook option", () => {
  assert.throws(
    () => parseBiologicalScoringCliArgs(["/tmp/benchmark_run", "--no-score-workbook"]),
    /unknown argument: --no-score-workbook/i,
  );
});

test("parseBiologicalScoringCliArgs rejects unknown standalone scoring options", () => {
  assert.throws(
    () => parseBiologicalScoringCliArgs(["/tmp/benchmark_run", "--biological-scoring-model", "gpt-5.5"]),
    /unknown argument/i,
  );
});

test("parseBiologicalScoringCliArgs rejects missing and invalid standalone scoring values", () => {
  assert.throws(() => parseBiologicalScoringCliArgs([]), /Usage:/);
  assert.throws(() => parseBiologicalScoringCliArgs(["--model"]), /Usage:/);
  assert.throws(() => parseBiologicalScoringCliArgs(["/tmp/benchmark_run", "--model"]), /Missing value for --model/);
  assert.throws(
    () => parseBiologicalScoringCliArgs(["/tmp/benchmark_run", "--max-concurrent-jobs", "0"]),
    /--max-concurrent-jobs must be an integer >= 1/,
  );
  assert.throws(
    () => parseBiologicalScoringCliArgs(["/tmp/benchmark_run", "--image-limit", "1"]),
    /unknown argument/i,
  );
});

test("validateBiologicalScoringResponse recomputes score from clause decisions", () => {
  const criterion = {
    paper_stems: ["1_Szabo2010_clean"],
    normalized_paper_stems: ["1_szabo2010"],
    target: "Dense monolayer",
    scoring_instructions: "Score CSVs.",
    clauses: [
      { id: "volume", kind: "numeric" as const, weight: 2, description: "Volume below threshold." },
      { id: "speed_min", kind: "numeric" as const, weight: 1, description: "Speed above threshold." },
      { id: "speed_max", kind: "numeric" as const, weight: 1, description: "Speed below threshold." },
    ],
  };
  const response = {
    status: "scored",
    score: 0,
    clauses: [
      {
        id: "volume",
        passed: false,
        observed_value: "35048",
        evidence: ["logger.csv"],
        rationale: "Medium volume is too high.",
      },
      {
        id: "speed_min",
        passed: true,
        observed_value: "0.197",
        evidence: ["logger.csv"],
        rationale: "Speed is above the minimum.",
      },
      {
        id: "speed_max",
        passed: true,
        observed_value: "0.197",
        evidence: ["logger.csv"],
        rationale: "Speed is below the maximum.",
      },
    ],
    summary: "Two of four weighted points pass.",
    limitations: [],
  };

  const validated = validateBiologicalScoringResponse(response, criterion);

  assert.equal(recomputeBiologicalScore(validated.clauses, criterion), 0.5);
  assert.equal(validated.score, 0.5);
});

test("validateBiologicalScoringResponse rejects malformed responses", () => {
  const criterion = {
    clauses: [
      { id: "volume", kind: "numeric" as const, weight: 1, description: "Volume below threshold." },
      { id: "speed", kind: "numeric" as const, weight: 1, description: "Speed above threshold." },
    ],
  };
  const valid = {
    status: "scored",
    clauses: [
      { id: "volume", passed: true, observed_value: "1", evidence: ["logger.csv"], rationale: "ok" },
      { id: "speed", passed: false, observed_value: "0", evidence: [], rationale: "slow" },
    ],
    summary: "summary",
    limitations: [],
  };

  assert.throws(() => validateBiologicalScoringResponse(null, criterion), /must be an object/);
  assert.throws(() => validateBiologicalScoringResponse({ ...valid, status: "draft" }, criterion), /status/);
  assert.throws(() => validateBiologicalScoringResponse({ ...valid, clauses: "bad" }, criterion), /clauses array/);
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        { ...valid, clauses: [{ id: "volume", passed: true, observed_value: "1", evidence: [], rationale: "ok" }] },
        criterion,
      ),
    /Missing biological scoring clause id: speed/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: true, observed_value: "1", evidence: [], rationale: "ok" },
            { id: "volume", passed: false, observed_value: "2", evidence: [], rationale: "duplicate" },
          ],
        },
        criterion,
      ),
    /Duplicate biological scoring clause id: volume/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: true, observed_value: "1", evidence: [], rationale: "ok" },
            { id: "unexpected", passed: false, observed_value: "0", evidence: [], rationale: "bad" },
          ],
        },
        criterion,
      ),
    /Unexpected biological scoring clause id: unexpected/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: "yes", observed_value: "1", evidence: [], rationale: "ok" },
            { id: "speed", passed: false, observed_value: "0", evidence: [], rationale: "slow" },
          ],
        },
        criterion,
      ),
    /boolean passed value/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: true, observed_value: "1", evidence: [1], rationale: "ok" },
            { id: "speed", passed: false, observed_value: "0", evidence: [], rationale: "slow" },
          ],
        },
        criterion,
      ),
    /evidence must be an array of strings/,
  );
  assert.throws(
    () => validateBiologicalScoringResponse({ ...valid, limitations: [1] }, criterion),
    /limitation must be a non-empty string/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: true, observed_value: "", evidence: [], rationale: "ok" },
            { id: "speed", passed: false, observed_value: "0", evidence: [], rationale: "slow" },
          ],
        },
        criterion,
      ),
    /volume\.observed_value must be a non-empty string/,
  );
  assert.throws(
    () =>
      validateBiologicalScoringResponse(
        {
          ...valid,
          clauses: [
            { id: "volume", passed: true, observed_value: "1", evidence: [], rationale: "ok" },
            { id: "speed", passed: false, observed_value: "0", evidence: [], rationale: "" },
          ],
        },
        criterion,
      ),
    /speed\.rationale must be a non-empty string/,
  );
});

test("repo criteria cover every benchmark paper once with balanced category weights", async () => {
  const registry = await loadBiologicalScoringCriteria(path.resolve("biological_scoring_criteria.json"));
  // The paper PDFs are not redistributed; benchmark_papers/papers.csv lists the benchmark corpus.
  const manifest = (await readFile(path.resolve("benchmark_papers", "papers.csv"), "utf8")).trim().split(/\r?\n/).slice(1);
  const papers = manifest.map((line) => `${line.split(",")[0]}.pdf`);
  assert.ok(papers.length > 0);
  const localPdfs = (await readdir(path.resolve("benchmark_papers"))).filter((name) => name.endsWith(".pdf"));
  assert.deepEqual(localPdfs.filter((name) => !papers.includes(name)), [], "local paper PDFs must be listed in papers.csv");

  for (const paper of papers) {
    const stem = paper.replace(/\.pdf$/, "");
    const matches = registry.criteria.filter((criterion) => criterion.normalized_paper_stems.includes(stem.toLowerCase()));
    assert.equal(matches.length, 1, `${paper} must match exactly one criterion`);
    assert.ok(await loadPaperFocus(path.resolve("benchmark_focus"), path.resolve("benchmark_papers", paper)), `${paper} needs a focus file`);
  }
  for (const criterion of registry.criteria) {
    const categoryWeight = (kind: string) =>
      criterion.clauses.filter((clause) => clause.kind === kind).reduce((sum, clause) => sum + clause.weight, 0);
    const qualitative = categoryWeight("qualitative");
    const numeric = categoryWeight("numeric");
    if (qualitative > 0 && numeric > 0) {
      assert.equal(qualitative, numeric, `${criterion.paper_stems[0]} categories must carry equal total weight`);
    }
  }
});

test("recomputeBiologicalScore weights passed clauses by clause weight", () => {
  const criterion = {
    clauses: [
      { id: "qualitative", kind: "qualitative" as const, weight: 2, description: "q" },
      { id: "numeric_a", kind: "numeric" as const, weight: 1, description: "a" },
      { id: "numeric_b", kind: "numeric" as const, weight: 1, description: "b" },
    ],
  };
  const passing = (...ids: string[]) =>
    criterion.clauses.map((clause) => ({
      id: clause.id,
      passed: ids.includes(clause.id),
      observed_value: "",
      evidence: [],
      rationale: "",
    }));

  assert.equal(recomputeBiologicalScore(passing("qualitative"), criterion), 0.5);
  assert.equal(recomputeBiologicalScore(passing("numeric_a"), criterion), 0.25);
  assert.equal(recomputeBiologicalScore(passing("qualitative", "numeric_b"), criterion), 0.75);
});

test("recomputeBiologicalScore returns zero for zero total weight", () => {
  assert.equal(
    recomputeBiologicalScore(
      [{ id: "volume", passed: true, observed_value: "1", evidence: [], rationale: "ok" }],
      { clauses: [{ id: "volume", kind: "numeric" as const, weight: 0, description: "No weight." }] },
    ),
    0,
  );
});
