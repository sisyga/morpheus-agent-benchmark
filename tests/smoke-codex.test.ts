import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { inflateSync } from "node:zlib";

import type { ThreadItem } from "@openai/codex-sdk";

import {
  buildSmokeCases,
  buildSmokePng,
  evaluateSmokeCase,
  parseSmokeArgs,
} from "../scripts/smoke-codex.js";

test("parseSmokeArgs requires explicit smoke-test selection", () => {
  assert.throws(() => parseSmokeArgs([], process.cwd()), /--subject or --scorer/);
});

test("parseSmokeArgs resolves a relative output directory from the current project", () => {
  const cwd = process.cwd();
  const args = parseSmokeArgs(["--subject", "--output-dir", "reports"], cwd);
  assert.equal(args.subject, true);
  assert.equal(args.scorer, false);
  assert.equal(path.relative(cwd, args.outputDir), "reports");
  assert.deepEqual(args.models, {
    subjectModel: "gpt-6-luna",
    subjectReasoningEffort: "high",
    scorerModel: "gpt-6-luna",
    scorerReasoningEffort: "high",
  });
});

test("parseSmokeArgs collects and validates model and effort overrides", () => {
  const args = parseSmokeArgs([
    "--subject",
    "--scorer",
    "--model",
    "gpt-6.1-sol",
    "--reasoning-effort",
    "xhigh",
    "--scorer-model",
    "gpt-5.6-sol",
    "--scorer-reasoning-effort",
    "medium",
  ]);
  assert.deepEqual(args.models, {
    subjectModel: "gpt-6.1-sol",
    subjectReasoningEffort: "xhigh",
    scorerModel: "gpt-5.6-sol",
    scorerReasoningEffort: "medium",
  });
  assert.throws(() => parseSmokeArgs(["--subject", "--reasoning-effort", "extreme"]), /--reasoning-effort must be/);
  assert.throws(() => parseSmokeArgs(["--subject", "--model"]), /--model requires a value/);
  assert.throws(() => parseSmokeArgs(["--subject", "--model", "--scorer"]), /--model requires a value/);
  assert.throws(() => parseSmokeArgs(["--subject", "--bogus"]), /Unknown smoke-test option/);
});

test("buildSmokeCases uses the selected subject and scorer models", () => {
  const { models } = parseSmokeArgs(["--subject", "--scorer-model", "gpt-5.6-sol", "--scorer-reasoning-effort", "medium"]);
  const cases = buildSmokeCases("/tmp/workspace", "/tmp/workspace/generated.png", models);
  assert.deepEqual(cases.map(({ id, model, reasoningEffort }) => ({ id, model, reasoningEffort })), [
    { id: "subject", model: "gpt-6-luna", reasoningEffort: "high" },
    { id: "scorer", model: "gpt-5.6-sol", reasoningEffort: "medium" },
  ]);
  assert.match(cases[1].input as string, /find and view generated\.png/i);
});

test("buildSmokePng writes a decodable 16x16 red/blue PNG", () => {
  const png = buildSmokePng();
  assert.deepEqual([...png.subarray(0, 8)], [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.equal(png.readUInt32BE(16), 16);
  assert.equal(png.readUInt32BE(20), 16);
  const idatLength = png.readUInt32BE(33);
  assert.equal(png.subarray(37, 41).toString("ascii"), "IDAT");
  const pixels = inflateSync(png.subarray(41, 41 + idatLength));
  assert.equal(pixels.length, 16 * (1 + 16 * 3));
  assert.deepEqual([...pixels.subarray(1, 4)], [255, 0, 0]);
  assert.deepEqual([...pixels.subarray(1 + 15 * 3, 1 + 16 * 3)], [0, 0, 255]);
  assert.equal(png.subarray(-8, -4).toString("ascii"), "IEND");
  assert.equal(png.readUInt32BE(png.length - 4), 0xae426082);
});

test("evaluateSmokeCase requires proof of the checked capability", () => {
  const command = {
    id: "c1",
    type: "command_execution",
    command: "echo codex-smoke",
    aggregated_output: "codex-smoke\n",
    exit_code: 0,
    status: "completed",
  } as ThreadItem;

  assert.deepEqual(evaluateSmokeCase("subject", { ok: true, detail: "done" }, [command]), []);
  assert.match(evaluateSmokeCase("subject", { ok: true, detail: "done" }, []).join(), /command_execution/);
  assert.deepEqual(evaluateSmokeCase("scorer", { ok: true, detail: "Red left half, blue right half." }, []), []);
  assert.deepEqual(evaluateSmokeCase("scorer", { ok: true, detail: "Corrupted image." }, []), [
    "description does not mention red; the image was probably not viewed",
    "description does not mention blue; the image was probably not viewed",
  ]);
  assert.match(evaluateSmokeCase("scorer", { ok: false, detail: "red and blue" }, []).join(), /ok was not true/);
});
