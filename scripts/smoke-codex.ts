import { Codex, type ThreadItem, type ThreadOptions } from "@openai/codex-sdk";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { deflateSync } from "node:zlib";

import { reasoningEffortValue } from "../src/benchmark/config.js";
import { hasSuccessfulCommandExecution } from "../src/benchmark/guardrails.js";
import { collectBenchmarkSoftware } from "../src/benchmark/provenance.js";
import { resolveBenchmarkPythonExecutable } from "../src/benchmark/python-env.js";
import type { ReasoningEffort } from "../src/benchmark/types.js";

export const DEFAULT_SMOKE_MODEL = "gpt-6-luna";
export const DEFAULT_SMOKE_REASONING_EFFORT: ReasoningEffort = "high";

const RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    ok: { type: "boolean" },
    detail: { type: "string" },
  },
  required: ["ok", "detail"],
  additionalProperties: false,
} as const;

export type SmokeModels = {
  subjectModel: string;
  subjectReasoningEffort: ReasoningEffort;
  scorerModel: string;
  scorerReasoningEffort: ReasoningEffort;
};

export type SmokeArgs = {
  subject: boolean;
  scorer: boolean;
  outputDir: string;
  models: SmokeModels;
};

const VALUE_OPTIONS = {
  "--model": "subjectModel",
  "--reasoning-effort": "subjectReasoningEffort",
  "--scorer-model": "scorerModel",
  "--scorer-reasoning-effort": "scorerReasoningEffort",
} as const;

export function parseSmokeArgs(argv: string[], cwd = process.cwd()): SmokeArgs {
  let subject = false;
  let scorer = false;
  let outputDir = path.join(cwd, "smoke_reports");
  const models: SmokeModels = {
    subjectModel: DEFAULT_SMOKE_MODEL,
    subjectReasoningEffort: DEFAULT_SMOKE_REASONING_EFFORT,
    scorerModel: DEFAULT_SMOKE_MODEL,
    scorerReasoningEffort: DEFAULT_SMOKE_REASONING_EFFORT,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--subject") {
      subject = true;
      continue;
    }
    if (argument === "--scorer") {
      scorer = true;
      continue;
    }
    const value = argv[index + 1];
    if (argument === "--output-dir" || argument in VALUE_OPTIONS) {
      if (!value || value.startsWith("--")) {
        throw new Error(`${argument} requires a value.`);
      }
      index += 1;
    }
    if (argument === "--output-dir") {
      outputDir = path.resolve(cwd, value);
    } else if (argument in VALUE_OPTIONS) {
      const key = VALUE_OPTIONS[argument as keyof typeof VALUE_OPTIONS];
      if (key === "subjectReasoningEffort" || key === "scorerReasoningEffort") {
        models[key] = reasoningEffortValue(value, argument);
      } else {
        models[key] = value;
      }
    } else {
      throw new Error(`Unknown smoke-test option: ${argument}`);
    }
  }
  if (!subject && !scorer) {
    throw new Error("Select at least one smoke test with --subject or --scorer.");
  }
  return { subject, scorer, outputDir, models };
}

const SMOKE_COMMAND_MARKER = "codex-smoke";

/** A valid 16x16 RGB PNG: left half red, right half blue, so a passing description proves the image was seen. */
export function buildSmokePng(): Buffer {
  const size = 16;
  const rows: Buffer[] = [];
  for (let y = 0; y < size; y += 1) {
    const row = Buffer.alloc(1 + size * 3);
    for (let x = 0; x < size; x += 1) {
      row.set(x < size / 2 ? [255, 0, 0] : [0, 0, 255], 1 + x * 3);
    }
    rows.push(row);
  }
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 2, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    pngChunk("IHDR", header),
    pngChunk("IDAT", deflateSync(Buffer.concat(rows))),
    pngChunk("IEND", Buffer.alloc(0)),
  ]);
}

function pngChunk(type: string, data: Buffer): Buffer {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const typeAndData = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typeAndData));
  return Buffer.concat([length, typeAndData, crc]);
}

function crc32(data: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of data) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit += 1) {
      crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Each case must prove the capability it checks, not just return ok=true. */
export function evaluateSmokeCase(
  id: "subject" | "scorer",
  parsed: { ok?: unknown; detail?: unknown },
  items: ThreadItem[],
): string[] {
  const failures: string[] = [];
  if (parsed.ok !== true) {
    failures.push("response ok was not true");
  }
  if (id === "subject" && !hasSuccessfulCommandExecution(items)) {
    failures.push("no successful command_execution item (the runner's command-runner preflight would fail)");
  }
  if (id === "scorer") {
    const detail = typeof parsed.detail === "string" ? parsed.detail.toLowerCase() : "";
    for (const color of ["red", "blue"]) {
      if (!detail.includes(color)) {
        failures.push(`description does not mention ${color}; the image was probably not viewed`);
      }
    }
  }
  return failures;
}

export function buildSmokeCases(workspaceDir: string, imagePath: string, models: SmokeModels) {
  return [
    {
      id: "subject",
      enabledBy: "subject" as const,
      model: models.subjectModel,
      reasoningEffort: models.subjectReasoningEffort,
      sandboxMode: "workspace-write" as const,
      input: `Run a harmless shell command that prints ${SMOKE_COMMAND_MARKER}, then return JSON with ok=true and a short detail.`,
      workspaceDir,
    },
    {
      id: "scorer",
      enabledBy: "scorer" as const,
      model: models.scorerModel,
      reasoningEffort: models.scorerReasoningEffort,
      sandboxMode: "read-only" as const,
      input: `Find and view ${path.basename(imagePath)} in the current read-only workspace, then return JSON with ok=true and a short visual description that names its colors.`,
      workspaceDir,
    },
  ];
}

function countItemTypes(items: ThreadItem[]): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const item of items) {
    counts[item.type] = (counts[item.type] ?? 0) + 1;
  }
  return counts;
}

async function main(): Promise<void> {
  const args = parseSmokeArgs(process.argv.slice(2));
  const workspaceDir = await mkdtemp(path.join(tmpdir(), "morpheus-codex-smoke-"));
  const imagePath = path.join(workspaceDir, "generated-smoke.png");
  await writeFile(imagePath, buildSmokePng());
  const codex = new Codex();
  const results: Record<string, unknown>[] = [];
  for (const smokeCase of buildSmokeCases(workspaceDir, imagePath, args.models)) {
    if (!args[smokeCase.enabledBy]) {
      continue;
    }
    const startedAt = new Date();
    try {
      const thread = codex.startThread({
        model: smokeCase.model,
        modelReasoningEffort: smokeCase.reasoningEffort as ThreadOptions["modelReasoningEffort"],
        sandboxMode: smokeCase.sandboxMode,
        workingDirectory: smokeCase.workspaceDir,
        skipGitRepoCheck: true,
        approvalPolicy: "never",
        networkAccessEnabled: false,
        webSearchMode: "disabled",
      });
      const turn = await thread.run(smokeCase.input, { outputSchema: RESPONSE_SCHEMA });
      const parsed = JSON.parse(turn.finalResponse) as { ok?: unknown; detail?: unknown };
      const failures = evaluateSmokeCase(smokeCase.id as "subject" | "scorer", parsed, turn.items);
      results.push({
        id: smokeCase.id,
        ok: failures.length === 0,
        failures,
        itemTypes: countItemTypes(turn.items),
        model: smokeCase.model,
        reasoningEffort: smokeCase.reasoningEffort,
        threadId: thread.id,
        startedAt: startedAt.toISOString(),
        finishedAt: new Date().toISOString(),
        response: parsed,
        usage: turn.usage,
      });
    } catch (error) {
      results.push({
        id: smokeCase.id,
        ok: false,
        model: smokeCase.model,
        reasoningEffort: smokeCase.reasoningEffort,
        startedAt: startedAt.toISOString(),
        finishedAt: new Date().toISOString(),
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  const generatedAt = new Date();
  await mkdir(args.outputDir, { recursive: true });
  const reportPath = path.join(args.outputDir, `${generatedAt.toISOString().replaceAll(":", "-")}.json`);
  const software = await collectBenchmarkSoftware(process.cwd(), {
    morpheus: process.env.MORPHEUS_BIN ?? "morpheus",
    python: resolveBenchmarkPythonExecutable(),
    uv: "uv",
  });
  await writeFile(
    reportPath,
    JSON.stringify({ generatedAt: generatedAt.toISOString(), software, results }, null, 2),
    "utf8",
  );
  process.stdout.write(`${reportPath}\n`);
  if (results.some((result) => result.ok !== true)) {
    process.exitCode = 1;
  }
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  await main();
}
