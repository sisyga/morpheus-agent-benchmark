import assert from "node:assert/strict";
import { mkdir, mkdtemp, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  benchmarkCodexSessionRoots,
  CodexQuotaGuard,
  parseLatestCodexQuotaReading,
  readLatestCodexQuota,
  type CodexQuotaReading,
} from "../src/benchmark/quota.js";

function quotaEvent(timestamp: string, primary: number | null, secondary: number | null = null, limitId = "codex") {
  const window = (used: number | null) => used === null ? null : { used_percent: used, window_minutes: 10080, resets_at: 1791963035 };
  return JSON.stringify({
    timestamp,
    type: "event_msg",
    payload: { type: "token_count", rate_limits: { limit_id: limitId, primary: window(primary), secondary: window(secondary) } },
  });
}

test("parseLatestCodexQuotaReading takes the last codex reading and its binding window", () => {
  const text = [
    quotaEvent("2026-10-08T00:00:00.000Z", 10),
    "not json \"used_percent\"",
    quotaEvent("2026-10-08T01:00:00.000Z", 30, 55),
    quotaEvent("2026-10-08T01:00:01.000Z", null, null, "premium"),
    JSON.stringify({ timestamp: "2026-10-08T02:00:00.000Z", payload: { type: "agent_message" } }),
  ].join("\n");
  assert.deepEqual(parseLatestCodexQuotaReading(text), {
    usedPercent: 55,
    observedAt: "2026-10-08T01:00:00.000Z",
    resetsAt: 1791963035,
  });
  assert.equal(parseLatestCodexQuotaReading(quotaEvent("2026-10-08T00:00:00.000Z", null, null, "premium")), null);
  assert.equal(parseLatestCodexQuotaReading("{}"), null);
});

test("readLatestCodexQuota scans live and snapshotted sessions written since the guard started", async () => {
  const root = await mkdtemp(path.join(tmpdir(), "morpheus-quota-read-"));
  const runDir = path.join(root, "run");
  const tempRoot = path.join(root, "temp");
  const since = new Date("2026-10-08T01:00:00.000Z");
  const snapshot = path.join(runDir, "job_a", "codex_home", "sessions", "2026", "10", "08");
  const live = path.join(tempRoot, "job_b", "sessions", "2026", "10", "08");
  const stale = path.join(runDir, "job_old", "codex_home", "sessions");
  await mkdir(snapshot, { recursive: true });
  await mkdir(live, { recursive: true });
  await mkdir(stale, { recursive: true });
  await writeFile(path.join(snapshot, "rollout-a.jsonl"), quotaEvent("2026-10-08T01:10:00.000Z", 40), "utf8");
  await writeFile(path.join(live, "rollout-b.jsonl"), quotaEvent("2026-10-08T01:20:00.000Z", 42), "utf8");
  await writeFile(path.join(live, "notes.jsonl"), quotaEvent("2026-10-08T01:30:00.000Z", 99), "utf8");
  // Written before the guard started (e.g. before a manual quota reset): ignored.
  await writeFile(path.join(stale, "rollout-old.jsonl"), quotaEvent("2026-10-08T00:30:00.000Z", 100), "utf8");
  await utimes(path.join(stale, "rollout-old.jsonl"), new Date("2026-10-08T00:30:00Z"), new Date("2026-10-08T00:30:00Z"));

  const roots = await benchmarkCodexSessionRoots(runDir, tempRoot);
  const cache = new Map();
  const latest = await readLatestCodexQuota(roots, since, cache);
  assert.equal(latest?.usedPercent, 42);
  assert.equal((await readLatestCodexQuota(roots, since, cache))?.usedPercent, 42);
  assert.deepEqual(await benchmarkCodexSessionRoots(path.join(root, "missing"), path.join(root, "missing")), []);
  assert.equal(await readLatestCodexQuota([path.join(root, "missing")], since), null);
});

function reading(usedPercent: number): CodexQuotaReading {
  return { usedPercent, observedAt: new Date().toISOString(), resetsAt: null };
}

test("CodexQuotaGuard admits jobs while the quota covers them and every running job", async () => {
  let current: CodexQuotaReading | null = reading(80);
  const messages: string[] = [];
  const guard = new CodexQuotaGuard({
    readLatest: async () => current,
    initialJobCostPercent: 5,
    report: (message) => messages.push(message),
  });

  assert.equal(await guard.admit(), true); // 80 + 1×5
  assert.equal(await guard.admit(), true); // 80 + 2×5
  assert.equal(await guard.admit(), true); // 80 + 3×5
  assert.equal(await guard.admit(), true); // 80 + 4×5 = 100
  assert.equal(await guard.admit(), false);
  assert.match(messages.at(-1)!, /not starting another job; weekly quota is at 80\.0% with 4 running job\(s\) at ~5\.0% each/);
  guard.finish();
  current = reading(83);
  assert.equal(await guard.admit(), false); // 83 + 4×5
});

test("CodexQuotaGuard measures the per-job cost and carries it across a manual quota reset", async () => {
  let current: CodexQuotaReading | null = reading(10);
  const guard = new CodexQuotaGuard({ readLatest: async () => current, initialJobCostPercent: 2, report: () => {} });

  assert.equal(await guard.admit(), true);
  for (let used = 13; used <= 25; used += 3) {
    current = reading(used);
    guard.finish();
    assert.equal(await guard.admit(), true);
  }
  // 5 finished jobs and 1 running (counted as half) used 25 − 10 = 15%.
  assert.equal(guard.jobCostPercent(), 15 / 5.5);
  current = reading(1);
  assert.equal(await guard.admit(), true);
  assert.equal(guard.jobCostPercent(), 15 / 5.5);
});

test("CodexQuotaGuard waits for the first reading, then proceeds without one", async () => {
  let current: CodexQuotaReading | null = null;
  let reads = 0;
  const guard = new CodexQuotaGuard({
    readLatest: async () => {
      reads += 1;
      if (reads === 3) {
        current = reading(50);
      }
      return current;
    },
    initialJobCostPercent: 2,
    report: () => {},
    pollMs: 1,
  });
  assert.equal(await guard.admit(), true); // nothing running: start without a reading
  assert.equal(await guard.admit(), true); // waits until the running job reports 50%
  assert.equal(reads, 3);

  const blind = new CodexQuotaGuard({
    readLatest: async () => null,
    initialJobCostPercent: 2,
    report: () => {},
    pollMs: 1,
    firstReadingTimeoutMs: 5,
  });
  assert.equal(await blind.admit(), true);
  assert.equal(await blind.admit(), true); // gave up waiting
  blind.finish();
  assert.equal(await blind.admit(), true);
});
