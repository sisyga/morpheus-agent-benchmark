import type { ThreadItem } from "@openai/codex-sdk";

import { BENCHMARK_MODE_DEFINITIONS } from "./modes.js";
import type { BenchmarkModeId, PaperRunResult } from "./types.js";

const WINDOWS_SANDBOX_LOGON_FAILURE =
  "Windows sandbox command execution was unavailable because Codex could not launch its command runner (CreateProcessWithLogonW error 1326).";
const WINDOWS_POWERSHELL_MANAGED_LOAD_FAILURE =
  "Windows PowerShell command execution was unavailable because managed Windows PowerShell failed to initialize (error 8009001d / NTE_PROVIDER_DLL_FAIL).";
const WINDOWS_UNELEVATED_PERMISSION_PROFILE_FAILURE =
  "Native Windows benchmark command execution requires the elevated Codex sandbox because the unelevated sandbox cannot enforce the benchmark filesystem permission profile.";

export function isUnrecoverableCommandRunnerPreflightError(error: string): boolean {
  return (
    /windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions/i.test(error) ||
    error.includes(WINDOWS_UNELEVATED_PERMISSION_PROFILE_FAILURE)
  );
}

export function normalizeCommandRunnerPreflightError(error: string): string {
  return isUnrecoverableCommandRunnerPreflightError(error)
    ? WINDOWS_UNELEVATED_PERMISSION_PROFILE_FAILURE
    : error;
}
export const CAPABILITY_VIOLATION_MESSAGES = {
  morpheusMcp: "Used Morpheus MCP tools in a mode where Morpheus MCP is disabled.",
  agentsInstructions: "Read repository AGENTS.md instructions that are reserved for benchmark harness development.",
  inheritedExtensions: "Used inherited Codex plugins or skills in a subject run.",
  crossSession: "Read artifacts from another isolated modeling session.",
  morpheusCli: "Ran the Morpheus CLI in a mode where in-agent Morpheus execution is disabled.",
  morpheusSkill: "Read local Morpheus skill files in a mode where the Morpheus skill is disabled.",
  morpheusReferences: "Read local Morpheus reference files in a mode where local Morpheus references are disabled.",
} as const;

export function collectInfrastructureFailures(items: ThreadItem[]): string[] {
  let sawWindowsSandboxLogonFailure = false;
  let sawWindowsPowerShellManagedLoadFailure = false;

  for (const item of items) {
    if (item.type !== "command_execution") {
      continue;
    }

    const commandItem = item as {
      command: string;
      aggregated_output?: string;
      exit_code?: number | null;
      error?: string | null;
      status?: string | null;
    };
    const commandText = [
      commandItem.command,
      commandItem.aggregated_output,
      commandItem.error,
    ]
      .filter((value): value is string => typeof value === "string")
      .join("\n")
      .replace(/\u0000/g, "");

    if (
      /CreateProcessWithLogonW failed:\s*1326/i.test(commandText) ||
      /runner launch failed before process start:.*error=1326/i.test(commandText)
    ) {
      sawWindowsSandboxLogonFailure = true;
    }

    if (
      /8009001d/i.test(commandText) &&
      /(?:internal windows powershell|managed windows powershell|provider dll failed to initialize)/i.test(commandText)
    ) {
      sawWindowsPowerShellManagedLoadFailure = true;
    }
  }

  const sawSuccessfulCommandExecution = hasSuccessfulCommandExecution(items);
  if (sawSuccessfulCommandExecution) {
    return [];
  }

  return [
    ...(sawWindowsSandboxLogonFailure ? [WINDOWS_SANDBOX_LOGON_FAILURE] : []),
    ...(sawWindowsPowerShellManagedLoadFailure ? [WINDOWS_POWERSHELL_MANAGED_LOAD_FAILURE] : []),
  ];
}

export type CodexServiceFailureKind = "quota_exhausted" | "model_at_capacity";

/** Codex refused service for reasons outside the subject's control (account quota or provider capacity). */
export function codexServiceFailureKind(error: string | null | undefined): CodexServiceFailureKind | null {
  if (!error) {
    return null;
  }
  if (/hit your usage limit|usage limit (?:reached|exceeded)|exceeded your current quota|insufficient_quota/i.test(error)) {
    return "quota_exhausted";
  }
  if (/selected model is at capacity/i.test(error)) {
    return "model_at_capacity";
  }
  return null;
}

/** An exhausted quota fails every later execution identically until it resets, so the queue should stop. */
export function isCodexQuotaExhaustedFailure(
  result: Pick<PaperRunResult, "stopReason" | "summary" | "error">,
): boolean {
  return (
    result.stopReason === "infrastructure_failure" &&
    codexServiceFailureKind(result.error ?? result.summary) === "quota_exhausted"
  );
}

export function isSystemicCommandRunnerInfrastructureFailure(
  result: Pick<PaperRunResult, "stopReason" | "summary">,
): boolean {
  return (
    result.stopReason === "infrastructure_failure" &&
    /Command-runner preflight failed/i.test(result.summary) &&
    (
      result.summary.includes(WINDOWS_SANDBOX_LOGON_FAILURE) ||
      result.summary.includes(WINDOWS_POWERSHELL_MANAGED_LOAD_FAILURE) ||
      isUnrecoverableCommandRunnerPreflightError(result.summary) ||
      /8009001d/i.test(result.summary) ||
      /refresh token was already used|access token could not be refreshed.*log out and sign in again/i.test(result.summary)
    )
  );
}

export function hasSuccessfulCommandExecution(items: ThreadItem[]): boolean {
  return items.some(isSuccessfulCommandExecution);
}

function isSuccessfulCommandExecution(item: ThreadItem): boolean {
  if (item.type !== "command_execution") {
    return false;
  }
  const commandItem = item as {
    exit_code?: number | null;
    status?: string | null;
  };
  return commandItem.status === "completed" && commandItem.exit_code === 0;
}

export function collectCapabilityViolations(items: ThreadItem[], mode: BenchmarkModeId, activeRunId?: string): string[] {
  const capabilities = BENCHMARK_MODE_DEFINITIONS[mode].capabilities;
  const violations = new Set<string>();
  const agentsInstructionsKnownMissing = items.some(isAgentsInstructionsDiscoveryWithoutMatch);

  for (const item of items) {
    if (item.type === "mcp_tool_call" && item.server === "morpheus" && !capabilities.morpheusMcp) {
      violations.add(CAPABILITY_VIOLATION_MESSAGES.morpheusMcp);
    }

    if (item.type === "command_execution") {
      const command = item.command.toLowerCase();
      if (readsReservedAgentsInstructions(command, agentsInstructionsKnownMissing)) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.agentsInstructions);
      }
      if (command.includes(".codex") && (command.includes("plugins") || command.includes("skills"))) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.inheritedExtensions);
      }
      if (referencesAnotherModelingSession(item, activeRunId)) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.crossSession);
      }
      if (
        !capabilities.morpheusCli &&
        looksLikeMorpheusCliExecution(command) &&
        !isUnavailableMorpheusCommandResult(item)
      ) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.morpheusCli);
      }
      if (!capabilities.morpheusSkill && command.includes(".agents") && command.includes("skills") && command.includes("morpheus")) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.morpheusSkill);
      }
      if (!capabilities.morpheusSkill && containsMorpheusReferencePath(command)) {
        violations.add(CAPABILITY_VIOLATION_MESSAGES.morpheusReferences);
      }
    }
  }

  return [...violations];
}

function looksLikeMorpheusCliExecution(command: string): boolean {
  const shellPayload = unwrapShellPayload(command);
  return splitShellSegments(shellPayload ?? command)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0)
    .some(segmentExecutesMorpheus);
}

export function shouldTimeCommandAsMorpheusSimulation(command: string): boolean {
  return looksLikeMorpheusCliExecution(command);
}

export function isUnavailableMorpheusCommandResult(item: ThreadItem): boolean {
  return (
    item.type === "command_execution" &&
    item.exit_code === 127 &&
    item.aggregated_output.trim() === "morpheus: command not found"
  );
}

function readsReservedAgentsInstructions(command: string, knownMissing: boolean): boolean {
  if (!command.includes("agents.md")) {
    return false;
  }
  if (knownMissing && /\bif\s+\[\s+-f\s+[^\]]*agents\.md[^\]]*\]/i.test(command)) {
    return false;
  }
  return splitShellSegments(unwrapShellPayload(command) ?? command).some((segment) => {
    const normalized = segment.toLowerCase();
    if (!normalized.includes("agents.md") || /\brg\b[^\n]*\s--files\b/.test(normalized)) {
      return false;
    }
    return /(?:^|\s)(?:cat|get-content|grep|head|more|rg|sed|tail|type)(?:\.exe)?\b[^\n]*agents\.md\b/i.test(normalized);
  });
}

function isAgentsInstructionsDiscoveryWithoutMatch(item: ThreadItem): boolean {
  if (item.type !== "command_execution") {
    return false;
  }
  const output = item.aggregated_output?.toLowerCase() ?? "";
  return /\brg\b[^\n]*\s--files\b/i.test(item.command)
    && item.command.toLowerCase().includes("agents.md")
    && !/(?:^|[\\/])agents\.md(?:$|\s)/im.test(output);
}

function unwrapShellPayload(command: string): string | null {
  const marker = command.match(/\s(?:-lc|-command)\s/i);
  const shellToken = command.trim().match(/^("[^"]+"|'[^']+'|\S+)/)?.[1]?.replace(/^['"]|['"]$/g, "");
  if (
    marker?.index === undefined
    || !shellToken
    || !/(?:^|[\\/])(?:ba)?sh(?:\.exe)?$|powershell(?:\.exe)?$/i.test(shellToken)
  ) {
    return null;
  }
  const payload = command.slice(marker.index + marker[0].length).trim();
  const quote = payload[0];
  const unwrapped = (quote === "'" || quote === '"') && payload.at(-1) === quote
    ? payload.slice(1, -1)
    : payload;
  const decoded = quote === '"' && payload.at(-1) === quote
    ? unwrapped.replaceAll('\\"', '"').replaceAll('""\'', "'")
    : unwrapped;
  return decoded.replaceAll("'\"'", "'");
}

function splitShellSegments(command: string): string[] {
  const segments: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;
  let escaped = false;
  for (let index = 0; index < command.length; index += 1) {
    const character = command[index];
    if (escaped) {
      current += character;
      escaped = false;
      continue;
    }
    if (character === "\\" && quote !== "'") {
      current += character;
      escaped = true;
      continue;
    }
    if (quote) {
      current += character;
      if (character === quote) {
        quote = null;
      }
      continue;
    }
    if (character === "'" || character === '"') {
      current += character;
      quote = character;
      continue;
    }
    const twoCharacters = command.slice(index, index + 2);
    if (character === "\n" || character === ";" || character === "|" || twoCharacters === "&&" || twoCharacters === "||") {
      if (current.trim()) {
        segments.push(current.trim());
      }
      current = "";
      if (twoCharacters === "&&" || twoCharacters === "||") {
        index += 1;
      }
      continue;
    }
    current += character;
  }
  if (current.trim()) {
    segments.push(current.trim());
  }
  return segments;
}

function segmentExecutesMorpheus(segment: string): boolean {
  let remaining = segment.trim().replace(/^[&(]\s*/, "");
  while (remaining) {
    const shifted = shiftShellToken(remaining);
    if (!shifted) {
      return false;
    }
    const token = shifted.token.replace(/^['"]|['"]$/g, "");
    remaining = shifted.remaining;
    if (/^[A-Za-z_][A-Za-z0-9_]*=\S+$/.test(token)) {
      continue;
    }
    const executable = token.replace(/\\/g, "/").split("/").at(-1)?.toLowerCase();
    if (executable === "morpheus" || executable === "morpheus.exe") {
      return true;
    }
    if (executable === "env" || executable === "command") {
      remaining = remaining.replace(/^(?:-\S+\s+)*/, "");
      continue;
    }
    if (executable === "nice") {
      remaining = remaining.replace(/^(?:(?:-n\s+\S+|-\S+)\s+)*/, "");
      continue;
    }
    if (executable === "timeout") {
      remaining = remaining
        .replace(/^(?:(?:-(?:k|s)\s+\S+|--\S+)\s+)*/, "")
        .replace(/^\S+\s+/, "");
      continue;
    }
    return false;
  }
  return false;
}

function shiftShellToken(value: string): { token: string; remaining: string } | null {
  const match = value.trim().match(/^("[^"]+"|'[^']+'|\S+)(?:\s+|$)/);
  return match
    ? { token: match[1], remaining: value.trim().slice(match[0].length).trim() }
    : null;
}

function containsMorpheusReferencePath(command: string): boolean {
  return /(?:^|[\\/])morpheus[\\/]references(?=$|[\\/\s"'])/i.test(command);
}

function referencesAnotherModelingSession(item: ThreadItem, activeRunId?: string): boolean {
  if (item.type !== "command_execution") {
    return false;
  }
  const evidence = [item.command, item.aggregated_output ?? ""];
  const active = activeRunId?.toLowerCase();
  return evidence.some((text) => modelingSessionRunIds(text).some(
    (runId) => !active || (runId !== active && !isSameModelingRunVariant(runId, active)),
  ));
}

function modelingSessionRunIds(text: string): string[] {
  const runIds: string[] = [];
  const pattern = /morpheus-modeling-sessions((?:[\\/][^\\/\s"'()[\]{}]+)+)/gi;
  for (const match of text.matchAll(pattern)) {
    const runRoot = match[1]
      .split(/[\\/]/)
      .find((component) => component && !component.toLowerCase().endsWith("_session"));
    if (runRoot && isBenchmarkSubjectRunId(runRoot)) {
      runIds.push(runRoot.toLowerCase());
    }
  }
  return runIds;
}

function isBenchmarkSubjectRunId(value: string): boolean {
  return /^\d{8}_\d{6}_.+__(?:python_web|morpheus_cli|morpheus_cli_docs|morpheus_skill|morpheus_mcp)(?:__rep\d+)?(?:__replacement\d+)?$/i.test(value);
}

function isSameModelingRunVariant(candidate: string, active: string): boolean {
  const pattern = /^(\d{8}_\d{6})_(.+)__(python_web|morpheus_cli|morpheus_cli_docs|morpheus_skill|morpheus_mcp)((?:__rep\d+)?(?:__replacement\d+)?)$/i;
  const candidateParts = candidate.match(pattern);
  const activeParts = active.match(pattern);
  if (!candidateParts || !activeParts) {
    return false;
  }
  return candidateParts[1] === activeParts[1]
    && candidateParts[3] === activeParts[3]
    && candidateParts[4] === activeParts[4]
    && (
      candidateParts[2] === activeParts[2]
      || hasDuplicatedPaperToken(candidateParts[2], activeParts[2])
      || hasDuplicatedPaperToken(activeParts[2], candidateParts[2])
    );
}

function hasDuplicatedPaperToken(candidate: string, original: string): boolean {
  const paperToken = original.replace(/^\d+_/, "");
  return paperToken !== original && candidate === `${original}__${paperToken}`;
}
