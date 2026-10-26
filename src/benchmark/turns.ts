import type { Dirent } from "node:fs";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

import type { Thread, ThreadEvent, ThreadItem, UserInput } from "@openai/codex-sdk";

import {
  isUnavailableMorpheusCommandResult,
  shouldTimeCommandAsMorpheusSimulation,
} from "./guardrails.js";
import { FINAL_RESPONSE_SCHEMA } from "./prompt.js";

export type CodexTokenUsage = {
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_input_tokens?: number;
  output_tokens: number;
  reasoning_output_tokens?: number;
};

export type CollectedTurn = {
  finalResponse: string;
  usage: CodexTokenUsage | null;
  events: ThreadEvent[];
  items: ThreadItem[];
  error: string | null;
  durationMs: number;
  morpheusSimulationMs: number;
};

export async function collectCommandRunnerPreflightTurn(thread: Thread): Promise<CollectedTurn> {
  return collectTurn(
    thread,
    [{ type: "text", text: buildCommandRunnerPreflightPrompt() }],
    undefined,
  );
}

export async function collectSubjectTurn(
  thread: Thread,
  input: UserInput[],
): Promise<CollectedTurn> {
  return collectTurn(thread, input);
}

async function collectTurn(
  thread: Thread,
  input: UserInput[],
  outputSchema: unknown = FINAL_RESPONSE_SCHEMA,
): Promise<CollectedTurn> {
  const startedAt = Date.now();
  const events: ThreadEvent[] = [];
  const items = new Map<string, ThreadItem>();
  const mcpStartedAt = new Map<string, number>();
  const commandStartedAt = new Map<string, number>();
  let usage: CollectedTurn["usage"] = null;
  let finalResponse = "";
  let turnCompleted = false;
  let turnFailedMessage: string | null = null;
  let recoverableStreamError: string | null = null;
  let morpheusSimulationMs = 0;

  const finish = (payload: Omit<CollectedTurn, "durationMs" | "morpheusSimulationMs">): CollectedTurn => {
    const finishedAt = Date.now();
    const openMorpheusMs = [...commandStartedAt.values(), ...mcpStartedAt.values()]
      .reduce((total, itemStartedAt) => total + Math.max(0, finishedAt - itemStartedAt), 0);
    return {
      ...payload,
      durationMs: finishedAt - startedAt,
      morpheusSimulationMs: morpheusSimulationMs + openMorpheusMs,
    };
  };

  try {
    const streamed =
      outputSchema === undefined
        ? await thread.runStreamed(input)
        : await thread.runStreamed(input, { outputSchema });
    for await (const event of streamed.events) {
      events.push(event);
      if (event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") {
        items.set(event.item.id, event.item);
        if (
          event.type === "item.started" &&
          event.item.type === "command_execution" &&
          shouldTimeCommandAsMorpheusSimulation(event.item.command)
        ) {
          commandStartedAt.set(event.item.id, Date.now());
        }
        if (
          event.type === "item.completed" &&
          event.item.type === "command_execution" &&
          shouldTimeCommandAsMorpheusSimulation(event.item.command)
        ) {
          const commandStarted = commandStartedAt.get(event.item.id);
          if (commandStarted !== undefined) {
            if (!isUnavailableMorpheusCommandResult(event.item)) {
              morpheusSimulationMs += Date.now() - commandStarted;
            }
            commandStartedAt.delete(event.item.id);
          }
        }
        if (
          event.type === "item.started" &&
          event.item.type === "mcp_tool_call" &&
          event.item.server === "morpheus" &&
          event.item.tool === "run_morpheus_model"
        ) {
          mcpStartedAt.set(event.item.id, Date.now());
        }
        if (
          event.type === "item.completed" &&
          event.item.type === "mcp_tool_call" &&
          event.item.server === "morpheus" &&
          event.item.tool === "run_morpheus_model"
        ) {
          const toolStartedAt = mcpStartedAt.get(event.item.id);
          if (toolStartedAt !== undefined) {
            morpheusSimulationMs += Date.now() - toolStartedAt;
            mcpStartedAt.delete(event.item.id);
          }
        }
        if (event.item.type === "agent_message") {
          finalResponse = event.item.text;
        }
      }
      if (event.type === "turn.completed") {
        usage = event.usage;
        turnCompleted = true;
      }
      if (event.type === "turn.failed") {
        turnFailedMessage = event.error.message;
      }
      if (event.type === "error") {
        if (isRecoverableStreamError(event.message)) {
          recoverableStreamError = event.message;
          continue;
        }
        return finish({ finalResponse, usage, events, items: [...items.values()], error: event.message });
      }
    }
  } catch (error) {
    return finish({ finalResponse, usage, events, items: [...items.values()], error: stringifyError(error) });
  }

  if (turnFailedMessage) {
    return finish({ finalResponse, usage, events, items: [...items.values()], error: turnFailedMessage });
  }

  if (!turnCompleted) {
    const error = recoverableStreamError
      ? `Turn stream ended before completion after transient stream errors: ${recoverableStreamError}`
      : "Turn stream ended before completion.";
    return finish({ finalResponse, usage, events, items: [...items.values()], error });
  }

  return finish({
    finalResponse,
    usage,
    events,
    items: [...items.values()],
    error: null,
  });
}

function isRecoverableStreamError(message: string): boolean {
  const normalized = message.toLowerCase();
  return (
    normalized.includes("reconnecting") ||
    normalized.includes("stream disconnected before completion") ||
    normalized.includes("websocket closed by server")
  );
}

export function transcriptEventsForTurnError(turn: CollectedTurn, fallbackMessage: string): ThreadEvent[] {
  if (turn.events.length > 0 && turn.error) {
    return [...turn.events, { type: "error", message: turn.error } as ThreadEvent];
  }
  if (turn.events.length > 0 || !turn.error) {
    return turn.events;
  }
  return [{ type: "error", message: turn.error ?? fallbackMessage } as ThreadEvent];
}

function stringifyError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

/**
 * Cumulative token usage of one Codex thread, read from its session rollout.
 *
 * `turn.completed` carries usage only when a turn finishes, so time-limited or killed
 * subjects need this fallback. The rollout's last `token_count` event holds the same
 * cumulative totals that `turn.completed` would have reported.
 */
export async function readCodexSessionTokenUsage(
  codexHomeDir: string,
  threadId: string | null,
): Promise<CodexTokenUsage | null> {
  if (!threadId) {
    return null;
  }
  const rolloutPaths = (await listFilesRecursive(path.join(codexHomeDir, "sessions")))
    .filter((filePath) => {
      const name = path.basename(filePath);
      return name.startsWith("rollout-") && name.endsWith(".jsonl") && name.includes(threadId);
    })
    .sort();
  let usage: CodexTokenUsage | null = null;
  for (const rolloutPath of rolloutPaths) {
    usage = lastRolloutTokenUsage(await readFile(rolloutPath, "utf8")) ?? usage;
  }
  return usage;
}

export function lastRolloutTokenUsage(rolloutText: string): CodexTokenUsage | null {
  let usage: CodexTokenUsage | null = null;
  for (const line of rolloutText.split(/\r?\n/)) {
    if (!line.includes("token_count")) {
      continue;
    }
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    const payload = isRecord(event) && isRecord(event.payload) ? event.payload : null;
    const info = payload?.type === "token_count" && isRecord(payload.info) ? payload.info : null;
    const total = info && isRecord(info.total_token_usage) ? info.total_token_usage : null;
    if (!total || !isTokenCount(total.input_tokens) || !isTokenCount(total.output_tokens)) {
      continue;
    }
    usage = {
      input_tokens: total.input_tokens,
      cached_input_tokens: isTokenCount(total.cached_input_tokens) ? total.cached_input_tokens : 0,
      cache_write_input_tokens: isTokenCount(total.cache_write_input_tokens) ? total.cache_write_input_tokens : 0,
      output_tokens: total.output_tokens,
      reasoning_output_tokens: isTokenCount(total.reasoning_output_tokens) ? total.reasoning_output_tokens : 0,
    };
  }
  return usage;
}

async function listFilesRecursive(rootDir: string): Promise<string[]> {
  let entries: Dirent[];
  try {
    entries = await readdir(rootDir, { withFileTypes: true });
  } catch {
    return [];
  }
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listFilesRecursive(entryPath));
    } else if (entry.isFile()) {
      files.push(entryPath);
    }
  }
  return files;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isTokenCount(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

export function buildCommandRunnerPreflightPrompt(): string {
  return [
    "Run exactly one shell command:",
    "pwd",
    "After it completes, reply with: ready",
    "Do not inspect files or run extra commands.",
  ].join("\n");
}
