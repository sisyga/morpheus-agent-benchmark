/**
 * Checks rollout-transcript.ts against every execution that has both a real subject
 * transcript and a Codex session rollout.
 *
 * Usage: tsx scripts/stranded-runs/validate-rollout-transcripts.ts <benchmark run dir> <codex-home session dir>
 */
import { isDeepStrictEqual } from "node:util";
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import type { ThreadEvent, ThreadItem } from "@openai/codex-sdk";

import { collectCapabilityViolations, collectInfrastructureFailures } from "../../src/benchmark/guardrails.js";
import type { BenchmarkModeId, PaperRunResult } from "../../src/benchmark/types.js";
import { rebuildSubjectTurnFromRollout, subjectMorpheusSimulationMs } from "./rollout-transcript.js";

async function main(): Promise<void> {
  const [benchmarkRunDir, codexSessionDir] = process.argv.slice(2);
  if (!benchmarkRunDir || !codexSessionDir) {
    throw new Error("Usage: validate-rollout-transcripts.ts <benchmark run dir> <codex-home session dir>");
  }
  const contentExamples: string[] = [];
  const contentMismatchRuns: string[] = [];
  const totals = { runs: 0, completedContentEqual: 0, directBinaryEqual: 0, eventsExact: 0, itemsExact: 0,violationsEqual: 0, infraEqual: 0, finalEqual: 0, usageEqual: 0, events: 0, eventsMatched: 0 };
  const mismatchKinds = new Map<string, number>();
  const examples: string[] = [];
  const exampleCounts = new Map<string, number>();
  const skippedIncomplete: string[] = [];
  const simulationDiffs: Array<{ runName: string; recorded: number; rebuilt: number }> = [];
  const recordedByRun = new Map<string, PaperRunResult>();
  for (const name of await readdir(path.join(benchmarkRunDir, "assignment_results"))) {
    try {
      const result = JSON.parse(await readFile(path.join(benchmarkRunDir, "assignment_results", name), "utf8")) as PaperRunResult;
      if (result.runId && result.diagnostics) {
        recordedByRun.set(result.runId, result);
      }
    } catch {
      // 0-byte results of the stranded runs.
    }
  }

  for (const runName of (await readdir(benchmarkRunDir)).sort()) {
    const runDir = path.join(benchmarkRunDir, runName);
    const transcriptPath = path.join(runDir, "transcripts", "subject.jsonl");
    if (!(await nonEmpty(transcriptPath))) {
      continue;
    }
    const realEvents = (await readFile(transcriptPath, "utf8")).split("\n").filter(Boolean).map((line) => JSON.parse(line) as ThreadEvent);
    const threadId = (realEvents[0] as { thread_id?: string }).thread_id;
    if (!threadId) {
      continue;
    }
    const rolloutPath = await findRollout(path.join(codexSessionDir, runName), threadId)
      ?? await findRollout(path.join(runDir, "codex_home"), threadId);
    if (!rolloutPath) {
      continue;
    }
    const manifest = JSON.parse(await readFile(path.join(runDir, "run_manifest.json"), "utf8")) as { mode?: BenchmarkModeId; run_id?: string };
    if (!manifest.mode) {
      continue;
    }
    const rebuilt = await rebuildSubjectTurnFromRollout(rolloutPath);
    if (rebuilt.unparsedLineCount > 0 || !rebuilt.taskCompleted) {
      // A snapshot copied mid-write is not a fair comparison; the stranded rollouts are complete.
      skippedIncomplete.push(`${runName} (unparsed=${rebuilt.unparsedLineCount}, taskCompleted=${rebuilt.taskCompleted})`);
      continue;
    }
    totals.runs += 1;

    totals.events += realEvents.length;
    let matched = 0;
    for (let index = 0; index < Math.min(realEvents.length, rebuilt.events.length); index += 1) {
      if (isDeepStrictEqual(normalize(realEvents[index]), normalize(rebuilt.events[index]))) {
        matched += 1;
      } else {
        const kind = describe(realEvents[index], rebuilt.events[index]);
        mismatchKinds.set(kind, (mismatchKinds.get(kind) ?? 0) + 1);
        if ((exampleCounts.get(kind) ?? 0) < 2) {
          exampleCounts.set(kind, (exampleCounts.get(kind) ?? 0) + 1);
          examples.push(`[${kind}] ${runName} #${index}\n  real:    ${JSON.stringify(realEvents[index]).slice(0, 400)}\n  rebuilt: ${JSON.stringify(rebuilt.events[index]).slice(0, 400)}`);
        }
      }
    }
    totals.eventsMatched += matched;
    if (realEvents.length === rebuilt.events.length && matched === realEvents.length) {
      totals.eventsExact += 1;
    } else if (realEvents.length !== rebuilt.events.length) {
      const kind = `event count real=${realEvents.length} rebuilt=${rebuilt.events.length}`;
      mismatchKinds.set("event count differs", (mismatchKinds.get("event count differs") ?? 0) + 1);
      if (examples.length < 12) {
        examples.push(`${runName}: ${kind}`);
      }
    }

    const recorded = recordedByRun.get(runName);
    if (recorded) {
      const rebuiltMs = subjectMorpheusSimulationMs(rebuilt);
      simulationDiffs.push({ runName, recorded: recorded.diagnostics.morpheusSimulationTimeMs, rebuilt: rebuiltMs });
    }
    const realItems = itemsFromEvents(realEvents);
    const realContent = completedContent(realEvents);
    const rebuiltContent = completedContent(rebuilt.events);
    if (isDeepStrictEqual(realContent, rebuiltContent)) {
      totals.completedContentEqual += 1;
    } else {
      const realSet = new Map<string, number>();
      for (const entry of realContent) realSet.set(entry, (realSet.get(entry) ?? 0) + 1);
      let onlyRebuilt = 0;
      for (const entry of rebuiltContent) {
        const count = realSet.get(entry) ?? 0;
        if (count > 0) realSet.set(entry, count - 1);
        else {
          onlyRebuilt += 1;
          if (contentExamples.length < 8) contentExamples.push(`${runName} ONLY REBUILT: ${entry.slice(0, 350)}`);
        }
      }
      const onlyReal = [...realSet.entries()].filter(([, count]) => count > 0);
      for (const [entry] of onlyReal.slice(0, 2)) {
        if (contentExamples.length < 16) contentExamples.push(`${runName} ONLY REAL: ${entry.slice(0, 350)}`);
      }
      contentMismatchRuns.push(`${runName}: onlyReal=${onlyReal.reduce((sum, [, count]) => sum + count, 0)} onlyRebuilt=${onlyRebuilt} of ${realContent.length}`);
    }
    if (usesDirectMorpheusBinary(realEvents) === usesDirectMorpheusBinary(rebuilt.events)) {
      totals.directBinaryEqual += 1;
    } else {
      examples.push(`${runName}: DIRECT MORPHEUS BINARY DETECTION DIFFERS`);
    }
    const sortById = (items: ThreadItem[]) => [...items].map(normalize).sort((a, b) => String((a as { id: string }).id).localeCompare(String((b as { id: string }).id)));
    if (isDeepStrictEqual(sortById(realItems), sortById(rebuilt.items))) {
      totals.itemsExact += 1;
    }
    const runId = manifest.run_id ?? runName;
    if (isDeepStrictEqual(collectCapabilityViolations(realItems, manifest.mode, runId).sort(), collectCapabilityViolations(rebuilt.items, manifest.mode, runId).sort())) {
      totals.violationsEqual += 1;
    } else {
      examples.push(`${runName}: VIOLATIONS DIFFER real=${JSON.stringify(collectCapabilityViolations(realItems, manifest.mode, runId))} rebuilt=${JSON.stringify(collectCapabilityViolations(rebuilt.items, manifest.mode, runId))}`);
    }
    if (isDeepStrictEqual(collectInfrastructureFailures(realItems), collectInfrastructureFailures(rebuilt.items))) {
      totals.infraEqual += 1;
    }
    const realFinal = [...realItems].reverse().find((item) => item.type === "agent_message");
    if ((realFinal?.type === "agent_message" ? realFinal.text : "") === rebuilt.finalResponse) {
      totals.finalEqual += 1;
    } else {
      examples.push(`${runName}: FINAL RESPONSE DIFFERS`);
    }
    const realCompleted = realEvents.find((event) => event.type === "turn.completed") as { usage?: unknown } | undefined;
    if (isDeepStrictEqual(realCompleted?.usage ?? null, rebuilt.taskCompleted ? rebuilt.usage : null)) {
      totals.usageEqual += 1;
    }
  }

  console.log(JSON.stringify(totals, null, 1));
  const deltas = simulationDiffs.map((entry) => entry.rebuilt - entry.recorded).sort((a, b) => a - b);
  const relative = simulationDiffs
    .filter((entry) => entry.recorded > 0)
    .map((entry) => Math.abs(entry.rebuilt - entry.recorded) / entry.recorded)
    .sort((a, b) => a - b);
  console.log(`Morpheus simulation time, rebuilt minus recorded (ms) over ${deltas.length} runs: `
    + `min=${deltas[0]} median=${deltas[Math.floor(deltas.length / 2)]} max=${deltas[deltas.length - 1]}; `
    + `relative |error| median=${(relative[Math.floor(relative.length / 2)] * 100).toFixed(2)}% p90=${(relative[Math.floor(relative.length * 0.9)] * 100).toFixed(2)}% max=${(relative[relative.length - 1] * 100).toFixed(2)}%`);
  for (const entry of simulationDiffs.filter((candidate) => Math.abs(candidate.rebuilt - candidate.recorded) > 60_000).slice(0, 5)) {
    console.log(`  large simulation-time difference: ${JSON.stringify(entry)}`);
  }
  console.log(`Skipped ${skippedIncomplete.length} incomplete rollouts:`, skippedIncomplete.slice(0, 5));
  console.log("Mismatch kinds:", [...mismatchKinds.entries()].sort((a, b) => b[1] - a[1]).slice(0, 25));
  console.log(examples.join("\n"));
  console.log(`\nRuns whose completed-item content differs (${contentMismatchRuns.length}):`);
  console.log(contentMismatchRuns.slice(0, 30).join("\n"));
  console.log(contentExamples.join("\n"));
}

/** Completed items without ids, as a sorted multiset: order- and numbering-independent content. */
function completedContent(events: ThreadEvent[]): string[] {
  return events
    .filter((event) => event.type === "item.completed")
    .map((event) => {
      const { id: _id, ...rest } = (event as { item: Record<string, unknown> }).item;
      if (rest.type === "file_change" && Array.isArray(rest.changes)) {
        // Codex emits multi-file patches in HashMap order, which the rollout does not preserve.
        rest.changes = [...rest.changes].sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
      }
      return JSON.stringify(normalize(rest));
    })
    .sort();
}

/** Port of analyze_benchmark.py `transcript_uses_direct_morpheus_binary`. */
function usesDirectMorpheusBinary(events: ThreadEvent[]): boolean {
  const executablePattern = /(?:[a-z]:[\\/]|\/|\\\\)[^\s"';&|]*[\\/]morpheus(?:\.exe)?(?=[\s"']|$)/gi;
  for (const event of events) {
    const item = (event as { item?: { type?: string; command?: unknown } }).item;
    if (item?.type !== "command_execution" || typeof item.command !== "string") {
      continue;
    }
    const command = item.command;
    for (const match of command.matchAll(executablePattern)) {
      const executablePath = match[0].replaceAll("\\", "/").toLowerCase();
      if (executablePath.includes("/benchmark-tools/morpheus")) {
        continue;
      }
      const tail = command.slice((match.index ?? 0) + match[0].length).split(/\r?\n|;|&&|\|\|?/)[0];
      if (/(?:^|\s)-f(?:\s|$)/.test(tail)) {
        return true;
      }
    }
  }
  return false;
}

function itemsFromEvents(events: ThreadEvent[]): ThreadItem[] {
  const items = new Map<string, ThreadItem>();
  for (const event of events) {
    if (event.type === "item.started" || event.type === "item.updated" || event.type === "item.completed") {
      items.set(event.item.id, event.item);
    }
  }
  return [...items.values()];
}

function normalize<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function describe(real: ThreadEvent, rebuilt: ThreadEvent | undefined): string {
  if (!rebuilt) {
    return "missing";
  }
  if (real.type !== rebuilt.type) {
    return `type ${real.type} vs ${rebuilt.type}`;
  }
  const realItem = (real as { item?: Record<string, unknown> }).item;
  const rebuiltItem = (rebuilt as { item?: Record<string, unknown> }).item;
  if (!realItem || !rebuiltItem) {
    return `${real.type} payload`;
  }
  if (realItem.type !== rebuiltItem.type) {
    return `item type ${String(realItem.type)} vs ${String(rebuiltItem.type)}`;
  }
  const keys = new Set([...Object.keys(realItem), ...Object.keys(rebuiltItem)]);
  const differing = [...keys].filter((key) => !isDeepStrictEqual(normalize(realItem[key]), normalize(rebuiltItem[key])));
  return `${real.type}/${String(realItem.type)}: ${differing.join(",")}`;
}

async function findRollout(codexHomeDir: string, threadId: string): Promise<string | null> {
  const found: string[] = [];
  const walk = async (dir: string): Promise<void> => {
    let entries;
    try {
      entries = await readdir(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const entryPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        await walk(entryPath);
      } else if (entry.name.startsWith("rollout-") && entry.name.includes(threadId)) {
        found.push(entryPath);
      }
    }
  };
  await walk(path.join(codexHomeDir, "sessions"));
  return found.sort()[0] ?? null;
}

async function nonEmpty(filePath: string): Promise<boolean> {
  try {
    return (await stat(filePath)).size > 0;
  } catch {
    return false;
  }
}

await main();
