import { open, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";

export type CodexQuotaReading = {
  /** The binding (highest) used share of the Codex rate-limit windows, in percent. */
  usedPercent: number;
  observedAt: string;
  resetsAt: number | null;
};

const ROLLOUT_TAIL_BYTES = 256 * 1024;

/**
 * Codex records the account's rate-limit windows on every token_count event in its session
 * rollouts. Returns the latest reading in `text`, ignoring limits without a window (e.g. "premium").
 */
export function parseLatestCodexQuotaReading(text: string): CodexQuotaReading | null {
  const lines = text.split("\n");
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (!line.includes("\"used_percent\"")) {
      continue;
    }
    let event: unknown;
    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }
    const reading = quotaReadingFromEvent(event);
    if (reading) {
      return reading;
    }
  }
  return null;
}

function quotaReadingFromEvent(event: unknown): CodexQuotaReading | null {
  if (!isRecord(event) || typeof event.timestamp !== "string" || !isRecord(event.payload)) {
    return null;
  }
  const limits = event.payload.rate_limits;
  if (!isRecord(limits) || (limits.limit_id !== undefined && limits.limit_id !== "codex")) {
    return null;
  }
  const windows = [limits.primary, limits.secondary].filter(isRecord)
    .filter((window) => typeof window.used_percent === "number");
  if (windows.length === 0) {
    return null;
  }
  const binding = windows.reduce((max, window) =>
    (window.used_percent as number) > (max.used_percent as number) ? window : max
  );
  return {
    usedPercent: binding.used_percent as number,
    observedAt: event.timestamp,
    resetsAt: typeof binding.resets_at === "number" ? binding.resets_at : null,
  };
}

/**
 * Reads the newest quota reading from rollouts below `sessionRoots` written since `since`.
 * Unchanged files are served from `cache`, so repeated scans only reread active sessions.
 */
export async function readLatestCodexQuota(
  sessionRoots: string[],
  since: Date,
  cache: Map<string, { mtimeMs: number; size: number; reading: CodexQuotaReading | null }> = new Map(),
): Promise<CodexQuotaReading | null> {
  let latest: CodexQuotaReading | null = null;
  for (const root of sessionRoots) {
    for (const filePath of await listRolloutFiles(root)) {
      let info;
      try {
        info = await stat(filePath);
      } catch {
        continue;
      }
      if (info.mtimeMs < since.getTime()) {
        continue;
      }
      const cached = cache.get(filePath);
      let reading = cached && cached.mtimeMs === info.mtimeMs && cached.size === info.size ? cached.reading : undefined;
      if (reading === undefined) {
        reading = parseLatestCodexQuotaReading(await readTail(filePath, info.size));
        cache.set(filePath, { mtimeMs: info.mtimeMs, size: info.size, reading });
      }
      if (reading && Date.parse(reading.observedAt) >= since.getTime()
        && (!latest || reading.observedAt > latest.observedAt)) {
        latest = reading;
      }
    }
  }
  return latest;
}

async function listRolloutFiles(root: string): Promise<string[]> {
  let entries;
  try {
    entries = await readdir(root, { withFileTypes: true });
  } catch {
    return [];
  }
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listRolloutFiles(entryPath));
    } else if (entry.isFile() && entry.name.startsWith("rollout-") && entry.name.endsWith(".jsonl")) {
      files.push(entryPath);
    }
  }
  return files;
}

async function readTail(filePath: string, size: number): Promise<string> {
  const length = Math.min(size, ROLLOUT_TAIL_BYTES);
  const handle = await open(filePath, "r");
  try {
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, size - length);
    return buffer.toString("utf8");
  } catch {
    return "";
  } finally {
    await handle.close();
  }
}

/** Codex session directories of a benchmark's jobs: live temp homes and snapshots in the run folders. */
export async function benchmarkCodexSessionRoots(benchmarkRunDir: string, tempCodexHomeRoot: string): Promise<string[]> {
  const roots: string[] = [];
  for (const [parent, sessionsPath] of [
    [tempCodexHomeRoot, "sessions"],
    [benchmarkRunDir, path.join("codex_home", "sessions")],
  ] as const) {
    let entries;
    try {
      entries = await readdir(parent, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      if (entry.isDirectory()) {
        roots.push(path.join(parent, entry.name, sessionsPath));
      }
    }
  }
  return roots;
}

export type CodexQuotaGuardOptions = {
  readLatest: () => Promise<CodexQuotaReading | null>;
  /** Assumed weekly-quota share per job until enough jobs have finished to measure it. */
  initialJobCostPercent: number;
  report: (message: string) => void;
  pollMs?: number;
  /** How long to hold further jobs back while waiting for the first reading. */
  firstReadingTimeoutMs?: number;
};

/** Finished jobs needed before the measured per-job cost replaces the initial estimate. */
const MIN_FINISHED_JOBS_FOR_ESTIMATE = 5;

/**
 * Starts a job only when the remaining Codex quota covers it and every running job, so a quota
 * outage leaves the queue unstarted instead of cutting running subjects off mid-execution.
 */
export class CodexQuotaGuard {
  private active = 0;
  private finishedSinceBaseline = 0;
  private finishedTotal = 0;
  private baseline: CodexQuotaReading | null = null;
  private last: CodexQuotaReading | null = null;
  private carriedCostPercent: number | null = null;
  private queue: Promise<unknown> = Promise.resolve();
  private readonly pollMs: number;
  private readonly firstReadingTimeoutMs: number;

  constructor(private readonly options: CodexQuotaGuardOptions) {
    this.pollMs = options.pollMs ?? 15_000;
    this.firstReadingTimeoutMs = options.firstReadingTimeoutMs ?? 10 * 60_000;
  }

  /** Resolves true when a job may start (and counts it as running), false when the quota is too low. */
  admit(): Promise<boolean> {
    const decision = this.queue.then(() => this.decide());
    this.queue = decision.catch(() => undefined);
    return decision;
  }

  finish(): void {
    this.active = Math.max(0, this.active - 1);
    this.finishedSinceBaseline += 1;
    this.finishedTotal += 1;
  }

  /** Estimated weekly-quota share one job uses. */
  jobCostPercent(): number {
    if (!this.baseline || !this.last || this.finishedSinceBaseline < MIN_FINISHED_JOBS_FOR_ESTIMATE) {
      return this.carriedCostPercent ?? this.options.initialJobCostPercent;
    }
    // Running jobs are on average about halfway through, and their usage is already in the reading.
    const jobEquivalents = this.finishedSinceBaseline + this.active / 2;
    return Math.max(0.1, (this.last.usedPercent - this.baseline.usedPercent) / jobEquivalents);
  }

  private async decide(): Promise<boolean> {
    const waitStartedAt = Date.now();
    let reading = await this.observe();
    // Codex reports the quota only once a session has run, so hold further jobs back until the
    // first running job has produced a reading. Without any readings (e.g. API-key auth) give up.
    while (!reading && this.active > 0 && this.finishedTotal === 0
      && Date.now() - waitStartedAt < this.firstReadingTimeoutMs) {
      await sleep(this.pollMs);
      reading = await this.observe();
    }
    if (!reading) {
      this.active += 1;
      return true;
    }
    const cost = this.jobCostPercent();
    const projected = reading.usedPercent + (this.active + 1) * cost;
    if (projected > 100) {
      this.options.report(
        `Codex quota guard: not starting another job; weekly quota is at ${formatPercent(reading.usedPercent)}`
        + ` with ${this.active} running job(s) at ~${formatPercent(cost)} each. Reset the quota, then run --recover-run.`,
      );
      return false;
    }
    this.active += 1;
    this.options.report(
      `Codex quota guard: starting job at ${formatPercent(reading.usedPercent)} weekly quota,`
      + ` ${this.active} running, ~${formatPercent(cost)} per job.`,
    );
    return true;
  }

  private async observe(): Promise<CodexQuotaReading | null> {
    const reading = await this.options.readLatest();
    if (!reading) {
      return this.last;
    }
    // A manual quota reset drops the usage; measure the per-job cost afresh from there.
    if (!this.baseline || (this.last && reading.usedPercent < this.last.usedPercent - 1)) {
      if (this.baseline) {
        this.carriedCostPercent = this.jobCostPercent();
      }
      this.baseline = reading;
      this.finishedSinceBaseline = 0;
    }
    this.last = reading;
    return reading;
  }
}

function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
