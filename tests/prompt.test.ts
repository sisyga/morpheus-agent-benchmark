/* node:coverage disable */
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBenchmarkPrompt,
  FINAL_RESPONSE_SCHEMA,
  parseAgentRunResponse,
  validateAgentRunResponse,
} from "../src/benchmark/prompt.js";
import type { AgentRunResponse, BenchmarkModeId, ReproductionCriterion } from "../src/benchmark/types.js";

const MODES: BenchmarkModeId[] = [
  "python_web",
  "morpheus_cli",
  "morpheus_cli_docs",
  "morpheus_skill",
  "morpheus_mcp",
];

function buildPrompt(mode: BenchmarkModeId, totalTimeLimitMs = 14_400_000): string {
  return buildBenchmarkPrompt({
    mode,
    paperName: "1_Szabo2010_clean.pdf",
    focusText: "Reproduce Figure 10(d)",
    runId: `run_${mode}`,
    pageRenderDpi: 150,
    representativeOutputFrames: 5,
    likelyFigurePages: [2, 4],
    totalTimeLimitMs,
    finalizationReserveMs: 600_000,
    morpheusRunTimeoutMs: 3_600_000,
  });
}

function validResponse(): AgentRunResponse {
  const criterion: ReproductionCriterion = {
    score: 2,
    evidence: ["paper page 2", "plot_001.png"],
    rationale: "Matched.",
  };
  return {
    runId: "run_morpheus_mcp",
    agentReportedStatus: "completed",
    summary: "Finished with direct evidence.",
    reproduction: {
      source_coverage: criterion,
      mechanism_mapping: criterion,
      observable_alignment: criterion,
      parameter_plausibility: criterion,
      total_score: 8,
      summary: "Complete.",
    },
  };
}

test("FINAL_RESPONSE_SCHEMA is strict and exposes only v2 response fields", () => {
  assert.deepEqual(Object.keys(FINAL_RESPONSE_SCHEMA.properties), [
    "runId",
    "agentReportedStatus",
    "summary",
    "reproduction",
  ]);
  assert.deepEqual(FINAL_RESPONSE_SCHEMA.required, [
    "runId",
    "agentReportedStatus",
    "summary",
    "reproduction",
  ]);
  assert.equal(FINAL_RESPONSE_SCHEMA.additionalProperties, false);
  assert.equal(FINAL_RESPONSE_SCHEMA.properties.reproduction.additionalProperties, false);
});

test("master prompt gives every subject common time controls without cycle concepts", () => {
  for (const mode of MODES) {
    const prompt = buildPrompt(mode);
    assert.match(prompt, /Total subject execution limit: 4 hours/i);
    assert.match(prompt, /Finalization reserve: 10 minutes/i);
    assert.match(prompt, /Soft cutoff: \{\{BENCHMARK_SOFT_CUTOFF_AT\}\}/);
    assert.match(prompt, /Hard cutoff: \{\{BENCHMARK_HARD_CUTOFF_AT\}\}/);
    assert.match(prompt, /benchmark-time-left/);
    assert.doesNotMatch(prompt, /\bcycle\b|\biteration\b|\bcontinuation\b|another turn|only modeling execution/i);
    assert.equal(prompt.match(/model\.xml at the run directory root/g)?.length, 1);
    assert.equal(prompt.match(/forbidden shortcut/g)?.length, 1);
  }

  for (const mode of MODES.filter((candidate) => candidate !== "python_web")) {
    const prompt = buildPrompt(mode);
    assert.match(prompt, /Morpheus simulation limit: 60 minutes/i);
    assert.match(prompt, /exit code 124/i);
    assert.match(prompt, /partial outputs.*logs.*inspectable/i);
  }
});

test("master prompt addresses staged inputs relative to the current workspace", () => {
  const prompt = buildPrompt("morpheus_mcp");

  assert.match(prompt, /^PDF: paper\.pdf$/m);
  assert.match(prompt, /^Paper text: paper\.txt$/m);
  assert.match(prompt, /^Run directory: \.$/m);
  assert.match(prompt, /^Visual manifest: paper_visual_manifest\.json$/m);
  assert.match(prompt, /^Keep every file under the current working directory\.$/m);
  assert.match(prompt, /^- Create model\.xml at the run directory root: model\.xml\./m);
  assert.doesNotMatch(prompt, /\/work\/run/);
});

test("configured five-hour input changes total time without hard-coded cutoff math", () => {
  const prompt = buildPrompt("morpheus_cli", 18_000_000);
  assert.match(prompt, /Total subject execution limit: 5 hours/i);
  assert.match(prompt, /Finalization reserve: 10 minutes/i);
  assert.match(prompt, /Soft cutoff: \{\{BENCHMARK_SOFT_CUTOFF_AT\}\}/);
  assert.doesNotMatch(prompt, /4 hours/i);
});

test("mode prompt boundaries expose only intended modeling resources", () => {
  const python = buildPrompt("python_web");
  assert.match(python, /staged paper assets, web search, and Python/i);
  assert.match(python, /Morpheus CLI is unavailable in this environment/i);
  assert.match(python, /Do not attempt to invoke it/i);
  assert.doesNotMatch(python, /write_model_xml|run_morpheus_model|morpheusml_doc\.txt|Morpheus skill/i);

  const cli = buildPrompt("morpheus_cli");
  assert.match(cli, /Morpheus CLI/i);
  assert.doesNotMatch(cli, /write_model_xml|run_morpheus_model|morpheusml_doc\.txt|Morpheus skill/i);

  const docs = buildPrompt("morpheus_cli_docs");
  assert.match(docs, /morpheusml_doc\.txt/);
  assert.match(docs, /model_template\.txt/);
  assert.doesNotMatch(docs, /write_model_xml|run_morpheus_model|Morpheus skill|web search/i);

  const skill = buildPrompt("morpheus_skill");
  assert.match(skill, /Morpheus skill/i);
  assert.match(skill, /Morpheus CLI/i);
  assert.doesNotMatch(skill, /write_model_xml|run_morpheus_model|morpheusml_doc\.txt/i);

  const mcp = buildPrompt("morpheus_mcp");
  assert.match(mcp, /write_model_xml/);
  assert.match(mcp, /run_morpheus_model/);
  assert.match(mcp, /sample_output_images/);
  assert.match(mcp, /render_pdf_pages/);
  assert.doesNotMatch(mcp, /morpheusml_doc\.txt|model_template\.txt/i);
});

test("CLI mode prompts prohibit bypassing the staged Morpheus launcher", () => {
  for (const mode of ["morpheus_cli", "morpheus_cli_docs", "morpheus_skill"] as const) {
    const prompt = buildPrompt(mode);
    assert.match(prompt, /Use only the staged `morpheus` command/i);
    assert.match(prompt, /Do not invoke Morpheus through an absolute binary path/i);
  }
});

test("python_web prompt contains only static-model instructions", () => {
  const prompt = buildPrompt("python_web");

  assert.match(prompt, /validate model\.xml statically with Python/i);
  assert.match(prompt, /runtime evidence as unavailable/i);
  assert.doesNotMatch(
    prompt,
    /Morpheus simulation limit|before a simulation|another Morpheus simulation|exit code 124|morpheus_command\.json|fresh attempt folder|attempts\/attempt_###|generated CSV\/PNG|output PNGs|logger output/i,
  );
});

test("general mode prompts do not advertise Morpheus repositories", () => {
  for (const mode of MODES) {
    assert.doesNotMatch(buildPrompt(mode), /gitlab\.com\/morpheus\.lab/i);
  }
});

test("Morpheus-running prompts name the attempt self-score contract that analysis reads", () => {
  for (const mode of MODES.filter((candidate) => candidate !== "python_web")) {
    const prompt = buildPrompt(mode);
    assert.match(prompt, /attempts\/attempt_###\/attempt_reproduction\.json/);
    for (const field of ["source_coverage", "mechanism_mapping", "observable_alignment", "parameter_plausibility"]) {
      assert.match(prompt, new RegExp(field), `${mode} prompt must name ${field}`);
    }
  }
});

test("validateAgentRunResponse accepts strict 8/8 completion and parser validates", () => {
  const response = validResponse();
  assert.deepEqual(validateAgentRunResponse(response), response);
  assert.deepEqual(parseAgentRunResponse(JSON.stringify(response)), response);
});

test("validateAgentRunResponse rejects extra keys, inconsistent totals, and incomplete completion", () => {
  assert.throws(
    () => validateAgentRunResponse({ ...validResponse(), extra: true }),
    /unexpected key/i,
  );
  const wrongTotal = validResponse();
  wrongTotal.reproduction!.total_score = 7;
  assert.throws(
    () => validateAgentRunResponse(wrongTotal),
    /total_score must equal the four criterion scores/i,
  );
  const partial = validResponse();
  partial.reproduction!.source_coverage = {
    ...partial.reproduction!.source_coverage,
    score: 1,
  };
  partial.reproduction!.total_score = 7;
  assert.throws(
    () => validateAgentRunResponse(partial),
    /completed requires a non-null 8\/8 reproduction/i,
  );
});

test("best_effort may return a partial or null reproduction", () => {
  const response = validResponse();
  response.agentReportedStatus = "best_effort";
  response.reproduction = null;
  assert.equal(validateAgentRunResponse(response).reproduction, null);
});
