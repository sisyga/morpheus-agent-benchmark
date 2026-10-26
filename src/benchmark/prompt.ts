import type {
  AgentRunResponse,
  BenchmarkModeId,
  ReproductionCriterion,
  ReproductionReport,
} from "./types.js";

export const FINAL_RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    runId: { type: "string" },
    agentReportedStatus: {
      type: "string",
      enum: ["completed", "best_effort"],
    },
    summary: { type: "string" },
    reproduction: {
      type: ["object", "null"],
      properties: {
        source_coverage: criterionSchema(),
        mechanism_mapping: criterionSchema(),
        observable_alignment: criterionSchema(),
        parameter_plausibility: criterionSchema(),
        total_score: { type: "number" },
        summary: { type: "string" },
      },
      required: [
        "source_coverage",
        "mechanism_mapping",
        "observable_alignment",
        "parameter_plausibility",
        "total_score",
        "summary",
      ],
      additionalProperties: false,
    },
  },
  required: ["runId", "agentReportedStatus", "summary", "reproduction"],
  additionalProperties: false,
} as const;

function criterionSchema() {
  return {
    type: "object",
    properties: {
      score: { type: "number", enum: [0, 1, 2] },
      evidence: { type: "array", items: { type: "string" } },
      rationale: { type: "string" },
    },
    required: ["score", "evidence", "rationale"],
    additionalProperties: false,
  } as const;
}

export type BenchmarkPromptParams = {
  mode?: BenchmarkModeId;
  paperName: string;
  focusText?: string | null;
  runId: string;
  pageRenderDpi: number;
  representativeOutputFrames: number;
  likelyFigurePages?: number[];
  totalTimeLimitMs: number;
  finalizationReserveMs: number;
  morpheusRunTimeoutMs: number;
};

export function buildBenchmarkPrompt(params: BenchmarkPromptParams): string {
  const mode = params.mode ?? "morpheus_mcp";
  const focus = params.focusText
    ? [
        "<validation_target>",
        `Showcase/validation target: ${params.focusText}`,
        "Treat this as the final showcase, not the sole design target. Ground the model in the paper's mechanisms first and use at least one additional relevant paper result to constrain it when available.",
        "</validation_target>",
      ].join("\n")
    : "";
  const likelyPages = params.likelyFigurePages?.length
    ? `Likely visual pages: ${params.likelyFigurePages.join(", ")}`
    : "";

  return [
    "<task>",
    "Recreate the paper's model or the closest biologically grounded Morpheus reproduction, then leave the strongest auditable result.",
    `Paper: ${params.paperName}`,
    "PDF: paper.pdf",
    "Paper text: paper.txt",
    `Run ID: ${params.runId}`,
    "Run directory: .",
    "Visual manifest: paper_visual_manifest.json",
    likelyPages,
    `Preferred paper render DPI: ${params.pageRenderDpi}`,
    `Preferred representative output frames: ${params.representativeOutputFrames}`,
    "Work only inside the run directory. Unrelated local folders and artifacts are out of scope.",
    "</task>",
    focus,
    buildTimeBudgetBlock(mode, params),
    buildModeBlock(mode, params),
    buildScientificContract(),
    buildWorkContract(mode),
    buildRubricContract(),
    buildOutputContract(),
  ]
    .filter(Boolean)
    .join("\n\n");
}

function buildTimeBudgetBlock(mode: BenchmarkModeId, params: BenchmarkPromptParams): string {
  const modeInstructions = mode === "python_web"
    ? [
        "- Run benchmark-time-left before a major new modeling attempt and whenever you need an updated reminder.",
        "- Preserve the strongest valid candidate early. When the soft cutoff arrives, use the reserve to finalize the canonical XML and evidence.",
      ]
    : [
        `- Morpheus simulation limit: ${formatMinutes(params.morpheusRunTimeoutMs)}, dynamically shortened near the soft cutoff.`,
        "- Run benchmark-time-left before a simulation or a major new attempt and whenever you need an updated reminder.",
        "- Preserve the strongest valid candidate early. When the soft cutoff arrives, do not start another Morpheus simulation; use the reserve to finalize the canonical XML and evidence.",
        "- A Morpheus simulation that reaches its effective limit is killed with exit code 124. Its exact XML, partial outputs, stdout, stderr logs, and morpheus_command.json remain inspectable in that attempt folder; inspect and use them rather than assuming the attempt vanished.",
      ];
  return [
    "<time_budget>",
    `- Total subject execution limit: ${formatDuration(params.totalTimeLimitMs)}.`,
    `- Finalization reserve: ${formatDuration(params.finalizationReserveMs)}.`,
    "- Subject process started at: {{BENCHMARK_SUBJECT_STARTED_AT}}.",
    "- Soft cutoff: {{BENCHMARK_SOFT_CUTOFF_AT}}.",
    "- Hard cutoff: {{BENCHMARK_HARD_CUTOFF_AT}}.",
    ...modeInstructions,
    "</time_budget>",
  ].join("\n");
}

function buildModeBlock(mode: BenchmarkModeId, params: BenchmarkPromptParams): string {
  const scope = "Keep every file under the current working directory.";
  if (mode === "python_web") {
    return [
      "<available_resources>",
      "Use the staged paper assets, web search, and Python for paper analysis, XML authoring, static validation, and local image inspection.",
      "The Morpheus CLI is unavailable in this environment. Do not attempt to invoke it. Author and validate model.xml statically with Python, and report runtime evidence as unavailable.",
      scope,
      "</available_resources>",
    ].join("\n");
  }
  if (mode === "morpheus_cli") {
    return [
      "<available_resources>",
      "Use the staged paper assets, web search, Python, shell editing, and the Morpheus CLI.",
      "Invoke Morpheus with explicit -f and a fresh --outdir for every attempt.",
      "Use only the staged `morpheus` command. Do not invoke Morpheus through an absolute binary path such as `/bin/morpheus` or `/usr/bin/morpheus`; absolute paths bypass benchmark timing and attempt capture.",
      scope,
      "</available_resources>",
    ].join("\n");
  }
  if (mode === "morpheus_cli_docs") {
    return [
      "<available_resources>",
      "Use the staged paper assets, Python, shell editing, the Morpheus CLI, morpheusml_doc.txt, and model_template.txt.",
      "Use model_template.txt as the starting skeleton and morpheusml_doc.txt as the tag and attribute reference.",
      "Invoke Morpheus with explicit -f and a fresh --outdir for every attempt.",
      "Use only the staged `morpheus` command. Do not invoke Morpheus through an absolute binary path such as `/bin/morpheus` or `/usr/bin/morpheus`; absolute paths bypass benchmark timing and attempt capture.",
      scope,
      "</available_resources>",
    ].join("\n");
  }
  if (mode === "morpheus_skill") {
    return [
      "<available_resources>",
      "Use the loaded Morpheus skill, staged paper assets, web search, Python, shell editing, and the Morpheus CLI.",
      "Invoke Morpheus with explicit -f and a fresh --outdir for every attempt.",
      "Use only the staged `morpheus` command. Do not invoke Morpheus through an absolute binary path such as `/bin/morpheus` or `/usr/bin/morpheus`; absolute paths bypass benchmark timing and attempt capture.",
      scope,
      "</available_resources>",
    ].join("\n");
  }
  return [
    "<available_resources>",
    "Use the staged paper assets, web search, Python, shell editing, and the exposed Morpheus MCP tools.",
    `Always pass run_id="${params.runId}" to write_model_xml, run_morpheus_model, summarize_morpheus_run, sample_output_images, render_pdf_pages, and evaluate_technical_run.`,
    "Use run_morpheus_model for fresh attempt folders; use summarize_morpheus_run and sample_output_images to inspect artifacts and render_pdf_pages only for relevant paper pages.",
    scope,
    "</available_resources>",
  ].join("\n");
}

function buildScientificContract(): string {
  return [
    "<scientific_contract>",
    "- Identify whether the paper has an explicit computational source model and identify its source model class before authoring XML.",
    "- Preserve the reported mechanisms, assumptions, parameters, observables, spatial scale, temporal scale, and cell counts as closely as Morpheus allows. Do not invent exact values that the paper does not support.",
    "- Preserve the requested biological time window and choose a consistent conversion to simulation time. Where a CSV time series is requested, include the initial and final simulation states among the requested time points, and label the time column with its units.",
    "- Cell-resolved or individual-cell source models require a cell-resolved Morpheus representation. Do not replace explicit cells with a pure field surrogate; fields may support explicit cells.",
    "- Field-only models are appropriate only for genuinely field-based source models or biology.",
    "- Do not pre-place future cells, trace target snapshots with schedules or masks, impose unreported axes or seeds, or tune hidden cues solely to draw the requested figure. Any such forbidden shortcut makes the result incomplete even if it looks similar.",
    "- If exact mechanics are unavailable, use the closest defensible approximation and state the limitation honestly.",
    "</scientific_contract>",
  ].join("\n");
}

function buildWorkContract(mode: BenchmarkModeId): string {
  if (mode === "python_web") {
    return [
      "<work_contract>",
      "- Create model.xml at the run directory root: model.xml. This is the canonical deliverable.",
      "- Read paper.txt first, determine the model class and quantitative anchors, and consult only the figures, tables, references, or web sources needed to resolve a concrete uncertainty.",
      "- Statically validate well-formed MorpheusML version 4 with Description, Space, Time, and Analysis sections; be explicit that runtime evidence is unavailable.",
      "- Render only relevant paper PNGs and inspect them directly with view_image when images matter.",
      "- Preserve an evidence-backed candidate before risky changes. Use paper anchors and direct inspection, not filenames alone.",
      "</work_contract>",
    ].join("\n");
  }

  const imageWorkflow = mode === "morpheus_mcp"
    ? "Use render_pdf_pages and sample_output_images to locate relevant PNGs, then inspect those local images directly with view_image."
    : "Render only relevant paper/output PNGs and inspect them directly with view_image when images matter.";
  return [
    "<work_contract>",
    "- Create model.xml at the run directory root: model.xml. This is the canonical deliverable.",
    "- Read paper.txt first, determine the model class and quantitative anchors, and consult only the figures, tables, references, or web sources needed to resolve a concrete uncertainty.",
    "- Run and debug the model, inspect stdout/stderr and generated CSV/PNG evidence, and revise conservatively. A parse alone is not sufficient runtime evidence.",
    `- ${imageWorkflow}`,
    "- Keep each execution attempt in a fresh attempt folder at attempts/attempt_###/ containing the exact model.xml, logs, and outputs. Write attempts/attempt_###/attempt_reproduction.json for every execution with four numeric scores: source_coverage, mechanism_mapping, observable_alignment, and parameter_plausibility, each 0, 1, or 2.",
    "- Preserve an evidence-backed candidate before risky changes. Use quantitative logs/CSV and direct visual inspection, not filenames alone.",
    "- Configure useful PNG and logger output without producing wasteful repeated line plots.",
    "</work_contract>",
  ].join("\n");
}

function buildRubricContract(): string {
  return [
    "<reproduction_rubric>",
    "Score source_coverage, mechanism_mapping, observable_alignment, and parameter_plausibility from 0 to 2. Cite specific paper pages/figures/tables and exact output files in every evidence list.",
    "A score of 2 for observable_alignment requires direct checks of relevant spatial, temporal, count, numeric, or visual anchors. A score of 2 for mechanism_mapping requires the paper's mechanisms, not merely a similar image.",
    "Set agentReportedStatus=completed only for a non-null 8/8 report. Otherwise use best_effort and describe the strongest artifacts and remaining limitations.",
    "The total_score must equal the four criterion scores.",
    "</reproduction_rubric>",
  ].join("\n");
}

function buildOutputContract(): string {
  return [
    "<output_contract>",
    "Return only the JSON object matching the supplied schema, without prose, markdown fences, or extra keys.",
    "Keep assumptions explicit in evidence and rationales, but do not reveal hidden reasoning.",
    "</output_contract>",
  ].join("\n");
}

export function parseAgentRunResponse(raw: string): AgentRunResponse {
  return validateAgentRunResponse(JSON.parse(raw));
}

export function validateAgentRunResponse(value: unknown): AgentRunResponse {
  const response = requireRecord(value, "response");
  assertExactKeys(response, ["runId", "agentReportedStatus", "summary", "reproduction"], "response");
  if (typeof response.runId !== "string" || response.runId.length === 0) {
    throw new Error("response.runId must be a non-empty string");
  }
  if (response.agentReportedStatus !== "completed" && response.agentReportedStatus !== "best_effort") {
    throw new Error("response.agentReportedStatus must be completed or best_effort");
  }
  if (typeof response.summary !== "string") {
    throw new Error("response.summary must be a string");
  }
  const reproduction = response.reproduction === null
    ? null
    : validateReproductionReport(response.reproduction);
  if (
    response.agentReportedStatus === "completed" &&
    (reproduction === null || reproduction.total_score !== 8)
  ) {
    throw new Error("completed requires a non-null 8/8 reproduction");
  }
  return {
    runId: response.runId,
    agentReportedStatus: response.agentReportedStatus,
    summary: response.summary,
    reproduction,
  };
}

function validateReproductionReport(value: unknown): ReproductionReport {
  const report = requireRecord(value, "reproduction");
  const criterionNames = [
    "source_coverage",
    "mechanism_mapping",
    "observable_alignment",
    "parameter_plausibility",
  ] as const;
  assertExactKeys(report, [...criterionNames, "total_score", "summary"], "reproduction");
  const criteria = criterionNames.map((name) => validateCriterion(report[name], name));
  if (typeof report.total_score !== "number" || !Number.isFinite(report.total_score)) {
    throw new Error("reproduction.total_score must be finite");
  }
  if (report.total_score !== criteria.reduce((sum, criterion) => sum + criterion.score, 0)) {
    throw new Error("reproduction.total_score must equal the four criterion scores");
  }
  if (typeof report.summary !== "string") {
    throw new Error("reproduction.summary must be a string");
  }
  return {
    source_coverage: criteria[0],
    mechanism_mapping: criteria[1],
    observable_alignment: criteria[2],
    parameter_plausibility: criteria[3],
    total_score: report.total_score,
    summary: report.summary,
  };
}

function validateCriterion(value: unknown, name: string): ReproductionCriterion {
  const criterion = requireRecord(value, name);
  assertExactKeys(criterion, ["score", "evidence", "rationale"], name);
  if (criterion.score !== 0 && criterion.score !== 1 && criterion.score !== 2) {
    throw new Error(`${name}.score must be 0, 1, or 2`);
  }
  if (!Array.isArray(criterion.evidence) || criterion.evidence.some((entry) => typeof entry !== "string")) {
    throw new Error(`${name}.evidence must be an array of strings`);
  }
  if (typeof criterion.rationale !== "string") {
    throw new Error(`${name}.rationale must be a string`);
  }
  return {
    score: criterion.score,
    evidence: [...criterion.evidence] as string[],
    rationale: criterion.rationale,
  };
}

function requireRecord(value: unknown, name: string): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${name} must be an object`);
  }
  return value as Record<string, unknown>;
}

function assertExactKeys(value: Record<string, unknown>, expected: string[], name: string): void {
  const expectedSet = new Set(expected);
  const extra = Object.keys(value).find((key) => !expectedSet.has(key));
  if (extra) {
    throw new Error(`${name} has unexpected key: ${extra}`);
  }
  const missing = expected.find((key) => !(key in value));
  if (missing) {
    throw new Error(`${name} is missing key: ${missing}`);
  }
}

function formatDuration(milliseconds: number): string {
  const minutes = Math.round(milliseconds / 60_000);
  if (minutes % 60 === 0) {
    const hours = minutes / 60;
    return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  if (minutes > 60) {
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    return `${hours} ${hours === 1 ? "hour" : "hours"} ${remainder} minutes`;
  }
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}

function formatMinutes(milliseconds: number): string {
  const minutes = Math.round(milliseconds / 60_000);
  return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
}
