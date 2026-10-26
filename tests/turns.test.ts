/* node:coverage disable */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import type { ThreadEvent, ThreadOptions, UserInput } from "@openai/codex-sdk";

import {
  runOneSubjectProcess,
  runWithCleanInfrastructureReplacement,
  selectCanonicalModelCandidate,
} from "../src/benchmark/runner.js";
import { lastRolloutTokenUsage, readCodexSessionTokenUsage } from "../src/benchmark/turns.js";

function tokenCountLine(input: number, cached: number, output: number, reasoning: number): string {
  return JSON.stringify({
    timestamp: "2026-09-22T12:00:00.000Z",
    type: "event_msg",
    payload: {
      type: "token_count",
      info: {
        total_token_usage: {
          input_tokens: input,
          cached_input_tokens: cached,
          cache_write_input_tokens: 0,
          output_tokens: output,
          reasoning_output_tokens: reasoning,
          total_tokens: input + output,
        },
        last_token_usage: {
          input_tokens: 1,
          cached_input_tokens: 0,
          cache_write_input_tokens: 0,
          output_tokens: 1,
          reasoning_output_tokens: 0,
          total_tokens: 2,
        },
        model_context_window: 272_000,
      },
      rate_limits: null,
    },
  });
}

test("lastRolloutTokenUsage returns the final cumulative token_count and skips rate-limit-only events", () => {
  const rollout = [
    JSON.stringify({ timestamp: "t", type: "session_meta", payload: { id: "thread_9" } }),
    tokenCountLine(100, 40, 20, 5),
    "not json token_count",
    tokenCountLine(900, 600, 300, 120),
    JSON.stringify({ timestamp: "t", type: "event_msg", payload: { type: "token_count", info: null } }),
  ].join("\n");

  assert.deepEqual(lastRolloutTokenUsage(rollout), {
    input_tokens: 900,
    cached_input_tokens: 600,
    cache_write_input_tokens: 0,
    output_tokens: 300,
    reasoning_output_tokens: 120,
  });
  assert.equal(lastRolloutTokenUsage(""), null);
});

test("readCodexSessionTokenUsage reads only the subject thread rollout from a Codex home", async () => {
  const codexHome = await mkdtemp(path.join(tmpdir(), "benchmark-v2-session-usage-"));
  const dayDir = path.join(codexHome, "sessions", "2026", "09", "22");
  await mkdir(dayDir, { recursive: true });
  await writeFile(path.join(dayDir, "rollout-2026-09-22T12-00-00-preflight-thread.jsonl"), tokenCountLine(5, 0, 1, 0));
  await writeFile(path.join(dayDir, "rollout-2026-09-22T12-01-00-subject-thread.jsonl"), tokenCountLine(700, 500, 90, 30));

  assert.deepEqual(await readCodexSessionTokenUsage(codexHome, "subject-thread"), {
    input_tokens: 700,
    cached_input_tokens: 500,
    cache_write_input_tokens: 0,
    output_tokens: 90,
    reasoning_output_tokens: 30,
  });
  assert.equal(await readCodexSessionTokenUsage(codexHome, "missing-thread"), null);
  assert.equal(await readCodexSessionTokenUsage(codexHome, null), null);
  assert.equal(await readCodexSessionTokenUsage(path.join(codexHome, "absent"), "subject-thread"), null);
});

test("runOneSubjectProcess starts one thread, makes one streamed call, and writes subject transcript", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "benchmark-v2-subject-"));
  const transcriptPath = path.join(root, "transcripts", "subject.jsonl");
  const events: ThreadEvent[] = [
    { type: "thread.started", thread_id: "thread_1" },
    {
      type: "item.completed",
      item: { id: "message_1", type: "agent_message", text: '{"runId":"run_1"}' },
    },
    {
      type: "turn.completed",
      usage: {
        input_tokens: 10,
        cached_input_tokens: 3,
        cache_write_input_tokens: 0,
        output_tokens: 2,
        reasoning_output_tokens: 0,
      },
    },
  ];
  let startThreadCalls = 0;
  let runStreamedCalls = 0;
  const fakeThread = {
    id: "thread_1",
    async runStreamed(_input: UserInput[], _options: unknown) {
      runStreamedCalls += 1;
      return {
        events: (async function* () {
          for (const event of events) {
            yield event;
          }
        })(),
      };
    },
  };
  const fakeCodex = {
    startThread(_options: ThreadOptions) {
      startThreadCalls += 1;
      return fakeThread;
    },
  };

  const result = await runOneSubjectProcess({
    codex: fakeCodex,
    threadOptions: {} as ThreadOptions,
    input: [{ type: "text", text: "prompt" }],
    transcriptPath,
  });

  assert.equal(startThreadCalls, 1);
  assert.equal(runStreamedCalls, 1);
  assert.equal(result.thread.id, "thread_1");
  assert.equal(result.turn.error, null);
  const written = (await readFile(transcriptPath, "utf8")).trim().split("\n").map((line) => JSON.parse(line));
  assert.deepEqual(written, events);
});

test("runOneSubjectProcess preserves partial events and never starts a replacement on failure", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "benchmark-v2-subject-error-"));
  let startThreadCalls = 0;
  const partial: ThreadEvent = {
    type: "item.started",
    item: {
      id: "command_1",
      type: "command_execution",
      command: "python work.py",
      aggregated_output: "",
      status: "in_progress",
    },
  };
  const fakeCodex = {
    startThread() {
      startThreadCalls += 1;
      return {
        id: "thread_failed",
        async runStreamed() {
          return {
            events: (async function* () {
              yield partial;
              yield { type: "error", message: "transport failed" } as ThreadEvent;
            })(),
          };
        },
      };
    },
  };

  const result = await runOneSubjectProcess({
    codex: fakeCodex,
    threadOptions: {} as ThreadOptions,
    input: [{ type: "text", text: "prompt" }],
    transcriptPath: path.join(root, "transcripts", "subject.jsonl"),
  });

  assert.equal(startThreadCalls, 1);
  assert.equal(result.turn.error, "transport failed");
  assert.equal(result.turn.events.length, 2);
});

test("subject timing charges an in-flight Morpheus command when the stream ends before item completion", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "benchmark-v2-open-morpheus-"));
  const fakeCodex = {
    startThread() {
      return {
        id: "thread_open_morpheus",
        async runStreamed() {
          return {
            events: (async function* () {
              yield {
                type: "item.started",
                item: {
                  id: "command_1",
                  type: "command_execution",
                  command: "morpheus -f model.xml --outdir attempt_001",
                  aggregated_output: "",
                  exit_code: undefined,
                  status: "in_progress",
                },
              } as ThreadEvent;
              await new Promise((resolve) => setTimeout(resolve, 20));
              yield { type: "error", message: "subject hard cutoff" } as ThreadEvent;
            })(),
          };
        },
      };
    },
  };

  const result = await runOneSubjectProcess({
    codex: fakeCodex as any,
    threadOptions: {} as ThreadOptions,
    input: [{ type: "text", text: "prompt" }],
    transcriptPath: path.join(root, "subject.jsonl"),
  });

  assert.match(result.turn.error ?? "", /hard cutoff/);
  assert.ok(result.turn.morpheusSimulationMs >= 15);
});

test("subject timing does not charge a Morpheus command rejected by the unavailable shim", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "benchmark-v2-unavailable-morpheus-"));
  const fakeCodex = {
    startThread() {
      return {
        id: "thread_unavailable_morpheus",
        async runStreamed() {
          return {
            events: (async function* () {
              yield {
                type: "item.started",
                item: {
                  id: "command_1",
                  type: "command_execution",
                  command: "morpheus -f model.xml --outdir attempt_001",
                  aggregated_output: "",
                  status: "in_progress",
                },
              } as ThreadEvent;
              await new Promise((resolve) => setTimeout(resolve, 20));
              yield {
                type: "item.completed",
                item: {
                  id: "command_1",
                  type: "command_execution",
                  command: "morpheus -f model.xml --outdir attempt_001",
                  aggregated_output: "morpheus: command not found\n",
                  exit_code: 127,
                  status: "failed",
                },
              } as ThreadEvent;
              yield {
                type: "turn.completed",
                usage: {
                  input_tokens: 10,
                  cached_input_tokens: 0,
                  cache_write_input_tokens: 0,
                  output_tokens: 2,
                  reasoning_output_tokens: 0,
                },
              } as ThreadEvent;
            })(),
          };
        },
      };
    },
  };

  const result = await runOneSubjectProcess({
    codex: fakeCodex as any,
    threadOptions: {} as ThreadOptions,
    input: [{ type: "text", text: "prompt" }],
    transcriptPath: path.join(root, "subject.jsonl"),
  });

  assert.equal(result.turn.error, null);
  assert.equal(result.turn.morpheusSimulationMs, 0);
});

test("selectCanonicalModelCandidate prefers valid inspected evidence, then score, then later attempt", () => {
  const selected = selectCanonicalModelCandidate([
    { path: "/work/attempt_009/model.xml", valid: false, inspected: true, reproductionScore: 8, attemptNumber: 9 },
    { path: "/work/attempt_004/model.xml", valid: true, inspected: false, reproductionScore: 8, attemptNumber: 4 },
    { path: "/work/attempt_005/model.xml", valid: true, inspected: true, reproductionScore: 6, attemptNumber: 5 },
    { path: "/work/attempt_006/model.xml", valid: true, inspected: true, reproductionScore: 7, attemptNumber: 6 },
    { path: "/work/attempt_007/model.xml", valid: true, inspected: true, reproductionScore: 7, attemptNumber: 7 },
  ]);

  assert.equal(selected?.path, "/work/attempt_007/model.xml");
  assert.equal(selectCanonicalModelCandidate([]), null);
});

test("clean replacement runs once only for infrastructure failure and links fresh execution", async () => {
  const calls: Array<{ replacementFor: string | null; replacementCount: 0 | 1 }> = [];
  const outcome = await runWithCleanInfrastructureReplacement(async (request) => {
    calls.push(request);
    return request.replacementCount === 0
      ? { executionId: "execution_original", stopReason: "infrastructure_failure" as const, replacementEligible: true }
      : { executionId: "execution_replacement", stopReason: "agent_finished" as const };
  });

  assert.deepEqual(calls, [
    { replacementFor: null, replacementCount: 0 },
    { replacementFor: "execution_original", replacementCount: 1 },
  ]);
  assert.equal(outcome.selected.executionId, "execution_replacement");
  assert.equal(outcome.executions.length, 2);
});

test("clean replacement does not rerun time-limit or subject artifact outcomes", async () => {
  for (const stopReason of ["agent_finished", "time_limit"] as const) {
    let calls = 0;
    const outcome = await runWithCleanInfrastructureReplacement(async () => {
      calls += 1;
      return { executionId: `execution_${stopReason}`, stopReason };
    });
    assert.equal(calls, 1);
    assert.equal(outcome.executions.length, 1);
  }
});
