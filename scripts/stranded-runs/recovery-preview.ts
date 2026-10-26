/**
 * Read-only preview of what `npm run benchmark -- --recover-run <dir>` will rerun, using the
 * runner's own selection rule, plus every assignment whose committed result mentions ENOSPC.
 *
 * Usage: tsx scripts/stranded-runs/recovery-preview.ts <benchmark run dir>
 */
import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { codexServiceFailureKind } from "../../src/benchmark/guardrails.js";
import { canRerunInfrastructureFailure } from "../../src/benchmark/runner.js";
import type { PaperRunResult } from "../../src/benchmark/types.js";

const benchmarkRunDir = path.resolve(process.argv[2] ?? "");
const state = JSON.parse(await readFile(path.join(benchmarkRunDir, "benchmark_recovery.json"), "utf8")) as {
  jobs: Array<{ pdfPath: string; mode: string; repetition: number }>;
};
const summary = JSON.parse(await readFile(path.join(benchmarkRunDir, "benchmark_summary.json"), "utf8")) as { results: PaperRunResult[] };
const assignmentId = (pdfPath: string, mode: string, repetition: number) =>
  `${path.basename(pdfPath, path.extname(pdfPath)).replace(/[^a-zA-Z0-9_-]+/g, "_")}__${mode}__rep${String(repetition).padStart(2, "0")}`;

const results = new Map<string, PaperRunResult>();
const emptyFiles: string[] = [];
for (const name of await readdir(path.join(benchmarkRunDir, "assignment_results"))) {
  const filePath = path.join(benchmarkRunDir, "assignment_results", name);
  if ((await stat(filePath)).size === 0) {
    emptyFiles.push(name);
    continue;
  }
  const result = JSON.parse(await readFile(filePath, "utf8")) as PaperRunResult;
  results.set(result.assignmentId ?? name.slice(0, -5), result);
}
for (const result of summary.results) {
  const id = result.assignmentId ?? assignmentId(result.pdfPath, result.mode, result.repetition);
  if (!results.has(id)) {
    results.set(id, result);
  }
}

const rerun: string[] = [];
const neverLaunched: string[] = [];
const stuck: string[] = [];
const enospc: string[] = [];
const outcomes = new Map<string, number>();
for (const job of state.jobs) {
  const id = assignmentId(job.pdfPath, job.mode, job.repetition);
  const result = results.get(id);
  const key = result ? `${result.stopReason}/${result.artifactStatus}` : "no result";
  outcomes.set(key, (outcomes.get(key) ?? 0) + 1);
  if (!result) {
    neverLaunched.push(id);
  } else if (canRerunInfrastructureFailure(result)) {
    rerun.push(`${id} (${(result.executions ?? []).length} prior executions)`);
  } else if (result.stopReason === "infrastructure_failure") {
    const budgeted = (result.executions ?? []).filter((execution) => execution.stopReason === "infrastructure_failure" && codexServiceFailureKind(execution.error) === null);
    stuck.push(`${id}: ${budgeted.length} budgeted failures: ${budgeted.map((execution) => (execution.error ?? "").slice(0, 90)).join(" | ")}`);
  }
  const text = JSON.stringify(result ?? {});
  if (/ENOSPC|no space left/i.test(text)) {
    enospc.push(`${id}: selected ${result?.runId} stop=${result?.stopReason} rerun=${result ? canRerunInfrastructureFailure(result) : "n/a"}`);
  }
}

console.log(`Jobs: ${state.jobs.length}; 0-byte result files: ${emptyFiles.length} ${emptyFiles.join(", ")}`);
console.log("Current outcomes:", Object.fromEntries(outcomes));
console.log(`--recover-run would rerun ${rerun.length} infrastructure failure(s) and launch ${neverLaunched.length} never-launched assignment(s).`);
console.log(rerun.join("\n"));
console.log(`\nAssignments mentioning ENOSPC (${enospc.length}):\n${enospc.join("\n")}`);
console.log(`\nInfrastructure failures that will NOT be rerun (budget used up) (${stuck.length}):\n${stuck.join("\n")}`);
