/**
 * Rebuilds the `codex exec --json` ThreadEvent stream of a subject turn from its Codex
 * session rollout.
 *
 * Used only to recover executions whose subject turn completed but whose host-side
 * transcript write failed (the 2026-10-11 ENOSPC incident). `validate-rollout-transcripts.ts`
 * checks this conversion against every execution that has both a real transcript and a
 * rollout before it is trusted on the stranded ones.
 */
import { readFile } from "node:fs/promises";

import type { ThreadEvent, ThreadItem } from "@openai/codex-sdk";

import type { CodexTokenUsage } from "../../src/benchmark/turns.js";
import { lastRolloutTokenUsage } from "../../src/benchmark/turns.js";
import { isUnavailableMorpheusCommandResult, shouldTimeCommandAsMorpheusSimulation } from "../../src/benchmark/guardrails.js";

type RolloutLine = { timestamp?: string; type: string; payload?: Record<string, unknown> };

export type RebuiltSubjectTurn = {
  threadId: string;
  events: ThreadEvent[];
  items: ThreadItem[];
  finalResponse: string;
  usage: CodexTokenUsage | null;
  taskStartedAtMs: number | null;
  taskCompletedAtMs: number | null;
  taskDurationMs: number | null;
  taskCompleted: boolean;
  /** Start and end of every converted item, keyed by the ThreadItem id. */
  itemTimes: Map<string, { startedAtMs: number; completedAtMs: number }>;
  /** Lines that were not valid JSON, e.g. a final line cut off mid-write. */
  unparsedLineCount: number;
};

export async function rebuildSubjectTurnFromRollout(rolloutPath: string): Promise<RebuiltSubjectTurn> {
  return rebuildSubjectTurnFromRolloutText(await readFile(rolloutPath, "utf8"));
}

export function rebuildSubjectTurnFromRolloutText(rolloutText: string): RebuiltSubjectTurn {
  let unparsedLineCount = 0;
  const lines: RolloutLine[] = rolloutText
    .split(/\r?\n/)
    .filter((line) => line.trim().length > 0)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as RolloutLine];
      } catch {
        unparsedLineCount += 1;
        return [];
      }
    });

  let threadId = "";
  let taskStartedAtMs: number | null = null;
  let taskCompletedAtMs: number | null = null;
  let taskDurationMs: number | null = null;
  let taskCompleted = false;
  const timeline: Array<{ atMs: number; order: number; phase: "started" | "completed"; raw: Record<string, unknown> }> = [];

  lines.forEach((line, index) => {
    const payload = line.payload ?? {};
    if (line.type === "session_meta" && typeof payload.id === "string") {
      threadId = payload.id;
    }
    if (line.type !== "event_msg") {
      return;
    }
    if (payload.type === "task_started") {
      taskStartedAtMs = epochMs(line.timestamp);
    }
    if (payload.type === "task_complete") {
      taskCompleted = true;
      taskCompletedAtMs = epochMs(line.timestamp);
      taskDurationMs = typeof payload.duration_ms === "number" ? payload.duration_ms : null;
    }
    if (payload.type === "item_completed" && isRecord(payload.item)) {
      const startedAtMs = numberOr(payload.started_at_ms, epochMs(line.timestamp) ?? 0);
      const completedAtMs = numberOr(payload.completed_at_ms, startedAtMs);
      if (hasStartedEvent(payload.item)) {
        timeline.push({ atMs: startedAtMs, order: index * 2, phase: "started", raw: payload.item });
      }
      timeline.push({ atMs: completedAtMs, order: index * 2 + 1, phase: "completed", raw: payload.item });
    }
  });

  timeline.sort((left, right) => left.atMs - right.atMs || left.order - right.order);

  const events: ThreadEvent[] = [{ type: "thread.started", thread_id: threadId } as ThreadEvent, { type: "turn.started" } as ThreadEvent];
  const items = new Map<string, ThreadItem>();
  const idsByRawId = new Map<string, string>();
  const itemTimes = new Map<string, { startedAtMs: number; completedAtMs: number }>();
  let nextItemNumber = 0;
  let finalResponse = "";

  for (const entry of timeline) {
    const rawId = String(entry.raw.id ?? "");
    const knownId = idsByRawId.get(rawId);
    // Web searches keep Codex's own id but still consume a number of the exec processor's counter.
    const candidateId = knownId ?? (entry.raw.type === "Extension" ? rawId : `item_${nextItemNumber}`);
    const item = entry.phase === "started" ? toStartedItem(entry.raw, candidateId) : toCompletedItem(entry.raw, candidateId);
    if (item === null) {
      continue;
    }
    const id = candidateId;
    if (knownId === undefined) {
      idsByRawId.set(rawId, id);
      nextItemNumber += 1;
    }
    itemTimes.set(id, {
      startedAtMs: itemTimes.get(id)?.startedAtMs ?? entry.atMs,
      completedAtMs: entry.atMs,
    });
    items.set(id, item);
    if (item.type === "agent_message") {
      finalResponse = item.text;
    }
    events.push({ type: entry.phase === "started" ? "item.started" : "item.completed", item } as ThreadEvent);
  }

  const usage = lastRolloutTokenUsage(rolloutText);
  if (taskCompleted) {
    events.push({ type: "turn.completed", usage } as ThreadEvent);
  }

  return {
    threadId,
    events,
    items: [...items.values()],
    finalResponse,
    usage,
    taskStartedAtMs,
    taskCompletedAtMs,
    taskDurationMs,
    taskCompleted,
    itemTimes,
    unparsedLineCount,
  };
}

/** Mirrors collectTurn's timing of Morpheus CLI commands and MCP model runs, from rollout item times. */
export function subjectMorpheusSimulationMs(turn: Pick<RebuiltSubjectTurn, "items" | "itemTimes">): number {
  let total = 0;
  for (const item of turn.items) {
    const times = turn.itemTimes.get(item.id);
    if (!times) {
      continue;
    }
    const elapsed = Math.max(0, times.completedAtMs - times.startedAtMs);
    if (item.type === "command_execution" && shouldTimeCommandAsMorpheusSimulation(item.command) && !isUnavailableMorpheusCommandResult(item)) {
      total += elapsed;
    }
    if (item.type === "mcp_tool_call" && item.server === "morpheus" && item.tool === "run_morpheus_model") {
      total += elapsed;
    }
  }
  return total;
}

function hasStartedEvent(raw: Record<string, unknown>): boolean {
  return raw.type === "CommandExecution"
    || raw.type === "FileChange"
    || raw.type === "McpToolCall"
    || (raw.type === "Extension" && raw.kind === "web.search");
}

function toStartedItem(raw: Record<string, unknown>, id: string): ThreadItem | null {
  switch (raw.type) {
    case "CommandExecution":
      return {
        id,
        type: "command_execution",
        command: shellJoin(raw.command),
        aggregated_output: "",
        exit_code: null,
        status: "in_progress",
      } as unknown as ThreadItem;
    case "FileChange":
      return { id, type: "file_change", changes: fileChanges(raw.changes), status: "in_progress" } as unknown as ThreadItem;
    case "McpToolCall":
      return {
        id,
        type: "mcp_tool_call",
        server: raw.server,
        tool: raw.tool,
        arguments: raw.arguments ?? null,
        result: null,
        error: null,
        status: "in_progress",
      } as unknown as ThreadItem;
    case "Extension":
      return { id, type: "web_search", query: "", action: { type: "other" } } as unknown as ThreadItem;
    default:
      return null;
  }
}

function toCompletedItem(raw: Record<string, unknown>, id: string): ThreadItem | null {
  switch (raw.type) {
    case "CommandExecution":
      return {
        id,
        type: "command_execution",
        command: shellJoin(raw.command),
        aggregated_output: typeof raw.aggregated_output === "string" ? raw.aggregated_output : "",
        exit_code: typeof raw.exit_code === "number" ? raw.exit_code : null,
        status: raw.status,
      } as unknown as ThreadItem;
    case "FileChange":
      return { id, type: "file_change", changes: fileChanges(raw.changes), status: raw.status } as unknown as ThreadItem;
    case "McpToolCall": {
      const result = isRecord(raw.result) ? raw.result : null;
      const error = isRecord(raw.error) ? raw.error : typeof raw.error === "string" ? { message: raw.error } : null;
      return {
        id,
        type: "mcp_tool_call",
        server: raw.server,
        tool: raw.tool,
        arguments: raw.arguments ?? null,
        result: result
          ? {
              content: Array.isArray(result.content) ? result.content : [],
              structured_content: result.structuredContent ?? result.structured_content ?? null,
              ...(result._meta === undefined ? {} : { _meta: result._meta }),
            }
          : null,
        error,
        status: raw.status,
      } as unknown as ThreadItem;
    }
    case "AgentMessage":
      return {
        id,
        type: "agent_message",
        text: (Array.isArray(raw.content) ? raw.content : [])
          .filter((part): part is Record<string, unknown> => isRecord(part) && typeof part.text === "string")
          .map((part) => part.text as string)
          .join(""),
      } as unknown as ThreadItem;
    case "Extension":
      if (raw.kind !== "web.search") {
        return null;
      }
      return {
        id,
        type: "web_search",
        query: typeof raw.query === "string" ? raw.query : "",
        action: webSearchAction(raw.action),
        ...(raw.results === undefined ? {} : { results: raw.results }),
      } as unknown as ThreadItem;
    default:
      // Reasoning, ImageView, UserMessage and ContextCompaction never reach the exec JSON stream.
      return null;
  }
}

function fileChanges(changes: unknown): Array<{ path: string; kind: string }> {
  if (Array.isArray(changes)) {
    return changes.filter(isRecord).map((change) => ({ path: String(change.path), kind: String(change.kind ?? change.type) }));
  }
  if (!isRecord(changes)) {
    return [];
  }
  return Object.entries(changes).map(([filePath, change]) => ({
    path: filePath,
    kind: isRecord(change) && typeof change.type === "string" ? change.type : "update",
  }));
}

/** The rollout stores the action type in camelCase (`openPage`); exec JSON uses snake_case. */
function webSearchAction(action: unknown): unknown {
  const cleaned = dropNulls(action);
  if (!isRecord(cleaned) || typeof cleaned.type !== "string") {
    return cleaned;
  }
  return { ...cleaned, type: cleaned.type.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`) };
}

function dropNulls(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(dropNulls);
  }
  if (!isRecord(value)) {
    return value;
  }
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => entry !== null).map(([key, entry]) => [key, dropNulls(entry)]),
  );
}

/** Port of the Rust `shlex` 1.3 `try_join` used by codex exec to render command argv. */
export function shellJoin(command: unknown): string {
  if (typeof command === "string") {
    return command;
  }
  if (!Array.isArray(command)) {
    return "";
  }
  return command.map((word) => shellQuote(String(word))).join(" ");
}

const UNQUOTED = 1;
const SINGLE = 2;
const DOUBLE = 4;

function unquotedOk(code: number): boolean {
  const c = String.fromCharCode(code);
  return /[+\-./:@\]_0-9A-Za-z]/.test(c);
}

function singleQuotedOk(code: number): boolean {
  return code !== 0x27 && code !== 0x5e && code !== 0x5c;
}

function doubleQuotedOk(code: number): boolean {
  return code !== 0x60 && code !== 0x24 && code !== 0x21 && code !== 0x5e;
}

export function shellQuote(word: string): string {
  if (word.length === 0) {
    return "''";
  }
  let bytes = Buffer.from(word, "utf8");
  const out: number[] = [];
  while (bytes.length > 0) {
    const [length, strategy] = quotingStrategy(bytes);
    if (length === bytes.length && strategy === UNQUOTED && out.length === 0) {
      return word;
    }
    const chunk = bytes.subarray(0, length);
    bytes = bytes.subarray(length);
    if (strategy === UNQUOTED) {
      out.push(...chunk);
    } else if (strategy === SINGLE) {
      out.push(0x27, ...chunk, 0x27);
    } else {
      out.push(0x22);
      for (const c of chunk) {
        if (c === 0x24 || c === 0x60 || c === 0x22 || c === 0x5c) {
          out.push(0x5c);
        }
        out.push(c);
      }
      out.push(0x22);
    }
  }
  return Buffer.from(out).toString("utf8");
}

function quotingStrategy(bytes: Buffer): [number, number] {
  let previous = SINGLE | DOUBLE | UNQUOTED;
  let index = 0;
  if (bytes[0] === 0x5e) {
    previous = SINGLE;
    index = 1;
  }
  while (index < bytes.length) {
    const c = bytes[index];
    let current = previous;
    if (c >= 0x80) {
      current &= ~UNQUOTED;
    } else {
      if (!unquotedOk(c)) {
        current &= ~UNQUOTED;
      }
      if (!singleQuotedOk(c)) {
        current &= ~SINGLE;
      }
      if (!doubleQuotedOk(c)) {
        current &= ~DOUBLE;
      }
    }
    if (current === 0) {
      break;
    }
    previous = current;
    index += 1;
  }
  const strategy = previous & UNQUOTED ? UNQUOTED : previous & SINGLE ? SINGLE : DOUBLE;
  return [index, strategy];
}

function epochMs(timestamp: string | undefined): number | null {
  if (!timestamp) {
    return null;
  }
  const value = Date.parse(timestamp);
  return Number.isFinite(value) ? value : null;
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
