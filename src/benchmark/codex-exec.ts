import { spawn } from "node:child_process";
import { mkdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { createInterface } from "node:readline";

import type { Codex, ThreadOptions } from "@openai/codex-sdk";

import { createDeadlineRecord, renderDeadlinePromptTokens } from "./deadline.js";
import type { CodexWindowsSandboxMode } from "./types.js";

type CodexConfigValue = string | number | boolean | CodexConfigValue[] | CodexConfigObject;

export type CodexConfigObject = {
  [key: string]: CodexConfigValue | undefined;
};

export type BenchmarkCodexExecArgs = {
  baseUrl?: string;
  model?: string;
  sandboxMode?: ThreadOptions["sandboxMode"];
  windowsSandboxMode?: CodexWindowsSandboxMode;
  workingDirectory?: string;
  additionalDirectories?: string[];
  skipGitRepoCheck?: boolean;
  outputSchemaFile?: string;
  modelReasoningEffort?: ThreadOptions["modelReasoningEffort"];
  networkAccessEnabled?: boolean;
  webSearchMode?: ThreadOptions["webSearchMode"];
  webSearchEnabled?: boolean;
  approvalPolicy?: ThreadOptions["approvalPolicy"];
  threadId?: string | null;
  images?: string[];
};

type BenchmarkCodexExecRunArgs = BenchmarkCodexExecArgs & {
  input: string;
  apiKey?: string;
  signal?: AbortSignal;
};

type BenchmarkCodexExec = {
  executablePath: string;
  envOverride?: Record<string, string>;
  configOverrides?: CodexConfigObject;
  benchmarkSubjectBudget?: BenchmarkSubjectBudget;
  run: (args: BenchmarkCodexExecRunArgs) => AsyncGenerator<string>;
};

export type BenchmarkSubjectBudget = {
  totalTimeLimitMs: number;
  finalizationReserveMs: number;
  morpheusRunTimeoutMs: number;
  deadlinePath: string;
  executionTimingPath: string;
};

export class CodexSubjectTimeLimitError extends Error {
  readonly code = "BENCHMARK_SUBJECT_TIME_LIMIT";
}

export function isCodexSubjectTimeLimitError(error: unknown): boolean {
  return error instanceof CodexSubjectTimeLimitError;
}

export type CodexExecProcessTreeCleanupPlan =
  | {
      kind: "taskkill";
      command: "taskkill.exe";
      args: string[];
    }
  | {
      kind: "process-group";
      pid: number;
      signal: NodeJS.Signals;
    };

const INTERNAL_ORIGINATOR_ENV = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE";
const TYPESCRIPT_SDK_ORIGINATOR = "codex_sdk_ts";
export const CODEX_EXEC_TURN_TIMEOUT_ENV = "CODEX_EXEC_TURN_TIMEOUT_MS";

export function buildBenchmarkCodexExecArgs(
  args: BenchmarkCodexExecArgs,
  configOverrides?: CodexConfigObject,
): string[] {
  const commandArgs = ["exec", "--experimental-json", "--ignore-rules"];
  if (configOverrides) {
    for (const override of serializeCodexConfigOverrides(configOverrides)) {
      commandArgs.push("--config", override);
    }
  }
  if (args.baseUrl) {
    commandArgs.push("--config", `openai_base_url=${toTomlValue(args.baseUrl, "openai_base_url")}`);
  }
  if (args.model) {
    commandArgs.push("--model", args.model);
  }
  if (args.sandboxMode) {
    commandArgs.push("--sandbox", args.sandboxMode);
  }
  if (args.windowsSandboxMode) {
    commandArgs.push("--config", `windows.sandbox="${args.windowsSandboxMode}"`);
  }
  if (args.workingDirectory) {
    commandArgs.push("--cd", args.workingDirectory);
  }
  if (args.additionalDirectories?.length) {
    for (const dir of args.additionalDirectories) {
      commandArgs.push("--add-dir", dir);
    }
  }
  if (args.skipGitRepoCheck) {
    commandArgs.push("--skip-git-repo-check");
  }
  if (args.outputSchemaFile) {
    commandArgs.push("--output-schema", args.outputSchemaFile);
  }
  if (args.modelReasoningEffort) {
    commandArgs.push("--config", `model_reasoning_effort="${args.modelReasoningEffort}"`);
  }
  if (args.networkAccessEnabled !== undefined) {
    commandArgs.push("--config", `sandbox_workspace_write.network_access=${args.networkAccessEnabled}`);
  }
  if (args.webSearchMode) {
    commandArgs.push("--config", `web_search="${args.webSearchMode}"`);
  } else if (args.webSearchEnabled === true) {
    commandArgs.push("--config", 'web_search="live"');
  } else if (args.webSearchEnabled === false) {
    commandArgs.push("--config", 'web_search="disabled"');
  }
  if (args.approvalPolicy) {
    commandArgs.push("--config", `approval_policy="${args.approvalPolicy}"`);
  }
  if (args.threadId) {
    commandArgs.push("resume", args.threadId);
  }
  for (const image of args.images ?? []) {
    commandArgs.push("--image", image);
  }
  return commandArgs;
}

/* node:coverage disable */
export function installBenchmarkCodexExecRulesIsolation(
  codex: Codex,
  budget?: BenchmarkSubjectBudget,
): void {
  const exec = (codex as unknown as { exec?: BenchmarkCodexExec }).exec;
  if (!exec || typeof exec.run !== "function") {
    throw new Error("Unable to install benchmark Codex exec isolation.");
  }

  // The SDK does not expose `--ignore-rules` or a turn watchdog; benchmark subjects and scorers need both.
  exec.benchmarkSubjectBudget = budget;
  exec.run = benchmarkCodexExecRun.bind(exec);
}

async function* benchmarkCodexExecRun(
  this: BenchmarkCodexExec,
  args: BenchmarkCodexExecRunArgs,
): AsyncGenerator<string> {
  const commandArgs = buildBenchmarkCodexExecArgs(args, this.configOverrides);
  const env = buildBenchmarkCodexProcessEnv(this.envOverride, args.apiKey);
  const child = spawn(this.executablePath, commandArgs, {
    env,
    signal: args.signal,
    detached: process.platform !== "win32",
  });
  const exitPromise = waitForCodexExecExit(child);
  const abortCleanup = (): void => terminateCodexExecProcessTree(child, "SIGTERM");
  args.signal?.addEventListener("abort", abortCleanup, { once: true });
  let spawnError: Error | null = null;
  const spawnPromise = child.pid !== undefined
    ? Promise.resolve()
    : new Promise<void>((resolve, reject) => {
        child.once("spawn", resolve);
        child.once("error", reject);
      });
  child.once("error", (error) => {
    spawnError = error;
  });
  if (!child.stdin) {
    terminateCodexExecProcessTree(child, "SIGTERM");
    throw new Error("Child process has no stdin");
  }
  if (!child.stdout) {
    terminateCodexExecProcessTree(child, "SIGTERM");
    throw new Error("Child process has no stdout");
  }

  const budget = this.benchmarkSubjectBudget;
  let subjectStartedAtMonotonicMs: number | null = null;
  let deadline: ReturnType<typeof createDeadlineRecord> | null = null;
  const turnTimeoutMs = budget?.totalTimeLimitMs ?? getCodexExecTurnTimeoutMs(env);
  let timedOut = false;
  let timeout: ReturnType<typeof setTimeout> | null = null;
  const stderrChunks: Buffer[] = [];
  child.stderr?.on("data", (data: Buffer | string) => {
    stderrChunks.push(Buffer.isBuffer(data) ? data : Buffer.from(data));
  });
  const rl = createInterface({
    input: child.stdout,
    crlfDelay: Infinity,
  });
  void exitPromise.then(() => rl.close());
  let completedNormally = false;

  try {
    await spawnPromise;
    const subjectStartedAtEpochMs = Date.now();
    subjectStartedAtMonotonicMs = performance.now();
    deadline = budget
      ? createDeadlineRecord(
          subjectStartedAtEpochMs,
          budget.totalTimeLimitMs,
          budget.finalizationReserveMs,
          budget.morpheusRunTimeoutMs,
        )
      : null;
    if (turnTimeoutMs !== null) {
      timeout = setTimeout(() => {
        timedOut = true;
        try {
          terminateCodexExecProcessTree(child, "SIGKILL");
        } catch {
          // Best effort; the exit path below will still report the timeout.
        }
      }, turnTimeoutMs);
      timeout.unref?.();
    }
    if (budget && deadline) {
      await writeJsonAtomic(budget.deadlinePath, deadline);
    }
    child.stdin.write(deadline ? renderDeadlinePromptTokens(args.input, deadline) : args.input);
    child.stdin.end();
    const lines = rl[Symbol.asyncIterator]();
    while (true) {
      const nextLine = await Promise.race([
        lines.next(),
        exitPromise.then(() => ({ done: true as const, value: undefined })),
      ]);
      if (nextLine.done) {
        break;
      }
      const normalizedLine = normalizeBenchmarkCodexExecStdoutLine(nextLine.value);
      if (normalizedLine === null) {
        continue;
      }
      yield normalizedLine;
    }
    if (timedOut) {
      throw budget
        ? new CodexSubjectTimeLimitError(formatCodexSubjectTimeLimitError(turnTimeoutMs ?? 0))
        : new Error(formatCodexExecTurnTimeoutError(turnTimeoutMs ?? 0));
    }
    if (spawnError) {
      throw spawnError;
    }
    const { code, signal } = await exitPromise;
    if (timedOut) {
      throw budget
        ? new CodexSubjectTimeLimitError(formatCodexSubjectTimeLimitError(turnTimeoutMs ?? 0))
        : new Error(formatCodexExecTurnTimeoutError(turnTimeoutMs ?? 0));
    }
    if (code !== 0 || signal) {
      const detail = signal ? `signal ${signal}` : `code ${code ?? 1}`;
      throw new Error(`Codex Exec exited with ${detail}: ${Buffer.concat(stderrChunks).toString("utf8")}`);
    }
    completedNormally = true;
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
    rl.close();
    args.signal?.removeEventListener("abort", abortCleanup);
    child.removeAllListeners();
    try {
      if (child.exitCode === null && child.signalCode === null) {
        terminateCodexExecProcessTree(child, timedOut ? "SIGKILL" : "SIGTERM");
      }
    } catch {
      // Best effort cleanup; the process may already have exited.
    }
    if (budget && deadline && subjectStartedAtMonotonicMs !== null) {
      const subjectFinishedAtEpochMs = Date.now();
      await writeJsonAtomic(budget.executionTimingPath, {
        artifactSchemaVersion: 2,
        benchmarkProtocol: "time_limit_v2",
        subjectStartedAt: deadline.subjectStartedAt,
        subjectFinishedAt: new Date(subjectFinishedAtEpochMs).toISOString(),
        subjectExecutionMs: Math.max(0, Math.round(performance.now() - subjectStartedAtMonotonicMs)),
        stopReason: timedOut
          ? "time_limit"
          : completedNormally
            ? "agent_finished"
            : "infrastructure_failure",
      });
    }
  }
}

function waitForCodexExecExit(
  child: ReturnType<typeof spawn>,
): Promise<{ code: number | null; signal: NodeJS.Signals | null }> {
  if (
    (child.exitCode !== null || child.signalCode !== null)
    && (child.stdout?.readableEnded ?? true)
    && (child.stderr?.readableEnded ?? true)
  ) {
    return Promise.resolve({ code: child.exitCode, signal: child.signalCode });
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (code: number | null, signal: NodeJS.Signals | null) => {
      if (settled) {
        return;
      }
      settled = true;
      clearInterval(poll);
      resolve({ code, signal });
    };
    const poll = setInterval(() => {
      if (
        (child.exitCode !== null || child.signalCode !== null)
        && (child.stdout?.readableEnded ?? true)
        && (child.stderr?.readableEnded ?? true)
      ) {
        finish(child.exitCode, child.signalCode);
      }
    }, 10);
    poll.unref?.();
    child.once("close", finish);
  });
}
/* node:coverage enable */

export function buildCodexExecProcessTreeCleanupPlan(
  pid: number,
  platform: NodeJS.Platform = process.platform,
  signal: NodeJS.Signals = "SIGTERM",
): CodexExecProcessTreeCleanupPlan {
  if (platform === "win32") {
    const args = ["/PID", String(pid), "/T"];
    if (signal === "SIGKILL") {
      args.push("/F");
    }
    return {
      kind: "taskkill",
      command: "taskkill.exe",
      args,
    };
  }
  return {
    kind: "process-group",
    pid: -pid,
    signal,
  };
}

/* node:coverage disable */
function terminateCodexExecProcessTree(
  child: ReturnType<typeof spawn>,
  signal: NodeJS.Signals,
): void {
  const killDirectChild = (): void => {
    try {
      child.kill(signal);
    } catch {
      // Best effort cleanup; the process may already have exited.
    }
  };
  if (child.pid === undefined) {
    killDirectChild();
    return;
  }
  const plan = buildCodexExecProcessTreeCleanupPlan(child.pid, process.platform, signal);
  if (plan.kind === "taskkill") {
    try {
      const cleanup = spawn(plan.command, plan.args, {
        stdio: "ignore",
        windowsHide: true,
      });
      cleanup.once("error", killDirectChild);
      cleanup.unref();
    } catch {
      killDirectChild();
    }
    return;
  }
  try {
    process.kill(plan.pid, plan.signal);
  } catch {
    killDirectChild();
  }
}
/* node:coverage enable */

export function normalizeBenchmarkCodexExecStdoutLine(line: string): string | null {
  return isWindowsTaskkillCleanupLine(line.trim()) ? null : line;
}

function isWindowsTaskkillCleanupLine(line: string): boolean {
  return /^SUCCESS:\s+(?:Sent termination signal to the process with PID \d+|The process with PID \d+(?: \(child process of PID \d+\))? has been terminated)\.$/.test(
    line,
  );
}

function buildBenchmarkCodexProcessEnv(
  envOverride: Record<string, string> | undefined,
  apiKey: string | undefined,
): Record<string, string> {
  const env: Record<string, string> = {};
  if (envOverride) {
    Object.assign(env, envOverride);
  } else {
    for (const [key, value] of Object.entries(process.env)) {
      if (value !== undefined) {
        env[key] = value;
      }
    }
  }
  if (!env[INTERNAL_ORIGINATOR_ENV]) {
    env[INTERNAL_ORIGINATOR_ENV] = TYPESCRIPT_SDK_ORIGINATOR;
  }
  if (apiKey) {
    env.CODEX_API_KEY = apiKey;
  }
  return env;
}

function getCodexExecTurnTimeoutMs(env: Record<string, string>): number | null {
  const raw = env[CODEX_EXEC_TURN_TIMEOUT_ENV];
  if (!raw) {
    return null;
  }
  const parsed = Number(raw);
  if (!Number.isInteger(parsed) || parsed < 1) {
    return null;
  }
  return parsed;
}

function formatCodexExecTurnTimeoutError(timeoutMs: number): string {
  return `Codex Exec timed out after ${formatDuration(timeoutMs)} without completing the turn. ` +
    "This usually indicates a stalled Codex/API stream or an internal wait that did not return control to the benchmark host.";
}

function formatCodexSubjectTimeLimitError(timeoutMs: number): string {
  return `Codex subject execution time limit reached after ${formatDuration(timeoutMs)}.`;
}

async function writeJsonAtomic(filePath: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  const temporaryPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
  await writeFile(temporaryPath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(temporaryPath, filePath);
}

function serializeCodexConfigOverrides(configOverrides: CodexConfigObject): string[] {
  const overrides: string[] = [];
  flattenCodexConfigOverrides(configOverrides, "", overrides);
  return overrides;
}

function flattenCodexConfigOverrides(
  value: CodexConfigValue | CodexConfigObject | undefined,
  prefix: string,
  overrides: string[],
): void {
  if (!isPlainObject(value)) {
    if (prefix) {
      overrides.push(`${prefix}=${toTomlValue(value, prefix)}`);
      return;
    }
    throw new Error("Codex config overrides must be a plain object");
  }

  const entries = Object.entries(value);
  if (!prefix && entries.length === 0) {
    return;
  }
  if (prefix && entries.length === 0) {
    overrides.push(`${prefix}={}`);
    return;
  }
  for (const [key, child] of entries) {
    if (!key) {
      throw new Error("Codex config override keys must be non-empty strings");
    }
    if (child === undefined) {
      continue;
    }
    const childPath = prefix ? `${prefix}.${key}` : key;
    if (isPlainObject(child)) {
      flattenCodexConfigOverrides(child, childPath, overrides);
    } else {
      overrides.push(`${childPath}=${toTomlValue(child, childPath)}`);
    }
  }
}

export function toTomlValue(value: CodexConfigValue | undefined, configPath: string): string {
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new Error(`Codex config override at ${configPath} must be a finite number`);
    }
    return `${value}`;
  }
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (Array.isArray(value)) {
    const rendered = value.map((item, index) => toTomlValue(item, `${configPath}[${index}]`));
    return `[${rendered.join(", ")}]`;
  }
  if (isPlainObject(value)) {
    const parts: string[] = [];
    for (const [key, child] of Object.entries(value)) {
      if (!key) {
        throw new Error("Codex config override keys must be non-empty strings");
      }
      if (child === undefined) {
        continue;
      }
      parts.push(`${formatTomlKey(key)} = ${toTomlValue(child, `${configPath}.${key}`)}`);
    }
    return `{${parts.join(", ")}}`;
  }
  throw new Error(`Unsupported Codex config override value at ${configPath}: ${value === null ? "null" : typeof value}`);
}

const TOML_BARE_KEY = /^[A-Za-z0-9_-]+$/;

function formatTomlKey(key: string): string {
  return TOML_BARE_KEY.test(key) ? key : JSON.stringify(key);
}

function isPlainObject(value: unknown): value is CodexConfigObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatDuration(milliseconds: number): string {
  const totalSeconds = Math.ceil(nonNegativeNumber(milliseconds) / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const parts: string[] = [];
  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (minutes > 0 || hours > 0) {
    parts.push(`${minutes}m`);
  }
  parts.push(`${seconds}s`);
  return parts.join(" ");
}

function nonNegativeNumber(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}
