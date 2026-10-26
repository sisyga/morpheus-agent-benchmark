import assert from "node:assert/strict";
import { chmod, mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import type { Codex } from "@openai/codex-sdk";

import {
  buildCodexExecProcessTreeCleanupPlan,
  installBenchmarkCodexExecRulesIsolation,
  isCodexSubjectTimeLimitError,
  type BenchmarkSubjectBudget,
} from "../src/benchmark/codex-exec.js";

type FakeExec = {
  executablePath: string;
  envOverride: Record<string, string>;
  run: (args: { input: string }) => AsyncGenerator<string>;
};

async function writeExecutable(root: string, name: string, body: string): Promise<string> {
  const executable = path.join(root, name);
  await writeFile(executable, `#!/bin/sh\nset -eu\n${body}\n`, "utf8");
  await chmod(executable, 0o755);
  return executable;
}

function fakeCodex(executablePath: string, env: Record<string, string>): { codex: Codex; exec: FakeExec } {
  const exec: FakeExec = {
    executablePath,
    envOverride: env,
    async *run() {
      throw new Error("benchmark executor was not installed");
    },
  };
  return { codex: { exec } as unknown as Codex, exec };
}

function budget(root: string, totalTimeLimitMs: number): BenchmarkSubjectBudget {
  return {
    totalTimeLimitMs,
    finalizationReserveMs: Math.min(10, totalTimeLimitMs - 1),
    morpheusRunTimeoutMs: 1_000,
    deadlinePath: path.join(root, "subject_deadline.json"),
    executionTimingPath: path.join(root, "subject_execution.json"),
  };
}

test("benchmark Codex executor creates the deadline after spawn and renders prompt tokens", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-codex-deadline-"));
  const capturedInput = path.join(root, "input.txt");
  const executable = await writeExecutable(
    root,
    "fake-codex",
    'cat > "$CAPTURE_INPUT_PATH"\nprintf \'{"type":"thread.started","thread_id":"thread-1"}\\n\'',
  );
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  env.CAPTURE_INPUT_PATH = capturedInput;
  const { codex, exec } = fakeCodex(executable, env);
  const subjectBudget = budget(root, 2_000);
  installBenchmarkCodexExecRulesIsolation(codex, subjectBudget);

  const lines: string[] = [];
  for await (const line of exec.run({
    input: "hard={{BENCHMARK_HARD_CUTOFF_AT}} total={{BENCHMARK_TOTAL_TIME_LIMIT_MS}}",
  })) {
    lines.push(line);
  }

  assert.equal(lines.length, 1);
  const deadline = JSON.parse(await readFile(subjectBudget.deadlinePath, "utf8"));
  const timing = JSON.parse(await readFile(subjectBudget.executionTimingPath, "utf8"));
  const input = await readFile(capturedInput, "utf8");
  assert.equal(deadline.hardCutoffEpochMs - deadline.subjectStartedAtEpochMs, 2_000);
  assert.match(input, new RegExp(`hard=${deadline.hardCutoffAt}`));
  assert.match(input, /total=2000/);
  assert.doesNotMatch(input, /\{\{BENCHMARK_/);
  assert.equal(timing.stopReason, "agent_finished");
  assert.ok(timing.subjectExecutionMs >= 0);
  assert.equal(timing.subjectStartedAt, deadline.subjectStartedAt);
});

test("benchmark Codex executor hard cutoff records time_limit and throws a classified error", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-codex-time-limit-"));
  const executable = await writeExecutable(
    root,
    "fake-codex",
    'cat >/dev/null\nprintf \'{"type":"thread.started","thread_id":"thread-1"}\\n\'\nsleep 30',
  );
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  const { codex, exec } = fakeCodex(executable, env);
  const subjectBudget = budget(root, 50);
  installBenchmarkCodexExecRulesIsolation(codex, subjectBudget);

  let caught: unknown;
  try {
    for await (const _line of exec.run({ input: "run" })) {
      // Consume the event stream until the hard cutoff closes it.
    }
  } catch (error) {
    caught = error;
  }

  assert.equal(isCodexSubjectTimeLimitError(caught), true);
  assert.match(String(caught), /subject execution time limit/i);
  const timing = JSON.parse(await readFile(subjectBudget.executionTimingPath, "utf8"));
  assert.equal(timing.stopReason, "time_limit");
  assert.ok(timing.subjectExecutionMs >= 40);
});

test("benchmark Codex executor enforces the env turn watchdog without a subject budget", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-codex-turn-watchdog-"));
  const argsPath = path.join(root, "args.txt");
  const executable = await writeExecutable(
    root,
    "fake-codex",
    `printf '%s\\n' "$@" > "${argsPath}"\ncat >/dev/null\nprintf '{"type":"thread.started","thread_id":"thread-1"}\\n'\nsleep 30`,
  );
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  env.CODEX_EXEC_TURN_TIMEOUT_MS = "100";
  const { codex, exec } = fakeCodex(executable, env);
  installBenchmarkCodexExecRulesIsolation(codex);

  const startedAt = Date.now();
  let caught: unknown;
  try {
    for await (const _line of (exec.run as (args: { input: string; images?: string[] }) => AsyncGenerator<string>)({
      input: "score",
      images: [path.join(root, "frame.png")],
    })) {
      // Consume events until the watchdog kills the stalled child.
    }
  } catch (error) {
    caught = error;
  }

  assert.match(String(caught), /timed out after/i);
  assert.equal(isCodexSubjectTimeLimitError(caught), false);
  assert.ok(Date.now() - startedAt < 10_000);
  const forwardedArgs = (await readFile(argsPath, "utf8")).split("\n");
  assert.ok(forwardedArgs.includes("--ignore-rules"));
  assert.deepEqual(forwardedArgs.slice(forwardedArgs.indexOf("--image"), forwardedArgs.indexOf("--image") + 2), [
    "--image",
    path.join(root, "frame.png"),
  ]);
});

test("Codex cleanup plans isolate POSIX groups and Windows trees", () => {
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(42, "linux", "SIGKILL"), {
    kind: "process-group",
    pid: -42,
    signal: "SIGKILL",
  });
  assert.deepEqual(buildCodexExecProcessTreeCleanupPlan(42, "win32", "SIGKILL"), {
    kind: "taskkill",
    command: "taskkill.exe",
    args: ["/PID", "42", "/T", "/F"],
  });
});

test("benchmark Codex executor cleans up a spawned child when deadline persistence fails", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-codex-deadline-failure-"));
  const pidPath = path.join(root, "child.pid");
  const executable = await writeExecutable(
    root,
    "fake-codex",
    `printf '%s' "$$" > "${pidPath}"\nsleep 30`,
  );
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  const { codex, exec } = fakeCodex(executable, env);
  const subjectBudget = budget(root, 2_000);
  await mkdir(subjectBudget.deadlinePath);
  installBenchmarkCodexExecRulesIsolation(codex, subjectBudget);

  await assert.rejects(async () => {
    for await (const _line of exec.run({ input: "run" })) {
      // The deadline write fails before any events are emitted.
    }
  });

  // The child may be killed before its shell writes the pid file; then nothing survived.
  // A surviving child writes its pid first and would still be running below.
  const waitUntil = Date.now() + 2_000;
  let pidText: string | null = null;
  while (pidText === null && Date.now() < waitUntil) {
    pidText = await readFile(pidPath, "utf8").catch(() => null);
    if (pidText === null) {
      await new Promise((resolve) => setTimeout(resolve, 20));
    }
  }
  if (pidText === null) {
    return;
  }
  const pid = Number(pidText);
  const stoppedBy = Date.now() + 2_000;
  while (processExists(pid) && Date.now() < stoppedBy) {
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
  assert.equal(processExists(pid), false);
});

test("benchmark Codex executor observes a child that exits immediately after spawn", {
  skip: process.platform === "win32",
}, async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-codex-fast-exit-"));
  const executable = await writeExecutable(root, "fake-codex", "exit 0");
  const env = Object.fromEntries(
    Object.entries(process.env).filter((entry): entry is [string, string] => entry[1] !== undefined),
  );
  const { codex, exec } = fakeCodex(executable, env);
  installBenchmarkCodexExecRulesIsolation(codex, budget(root, 2_000));

  const completed = Promise.race([
    (async () => {
      for await (const _line of exec.run({ input: "run" })) {
        // No output expected.
      }
      return true;
    })(),
    new Promise<boolean>((_, reject) => setTimeout(() => reject(new Error("executor hung")), 1_000)),
  ]);
  assert.equal(await completed, true);
});

function processExists(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
