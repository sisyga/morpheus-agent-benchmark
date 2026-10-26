export const BENCHMARK_DEADLINE_PATH_ENV = "BENCHMARK_DEADLINE_PATH";

export type SubjectDeadlineRecord = {
  artifactSchemaVersion: 2;
  benchmarkProtocol: "time_limit_v2";
  subjectStartedAt: string;
  softCutoffAt: string;
  hardCutoffAt: string;
  subjectStartedAtEpochMs: number;
  softCutoffEpochMs: number;
  hardCutoffEpochMs: number;
  totalTimeLimitMs: number;
  finalizationReserveMs: number;
  morpheusRunTimeoutMs: number;
};

export type SubjectDeadlineSnapshot = {
  elapsedMs: number;
  softRemainingMs: number;
  hardRemainingMs: number;
};

export function createDeadlineRecord(
  startedAtEpochMs: number,
  totalTimeLimitMs: number,
  finalizationReserveMs: number,
  morpheusRunTimeoutMs: number,
): SubjectDeadlineRecord {
  const hardCutoffEpochMs = startedAtEpochMs + totalTimeLimitMs;
  const softCutoffEpochMs = hardCutoffEpochMs - finalizationReserveMs;
  return {
    artifactSchemaVersion: 2,
    benchmarkProtocol: "time_limit_v2",
    subjectStartedAt: new Date(startedAtEpochMs).toISOString(),
    softCutoffAt: new Date(softCutoffEpochMs).toISOString(),
    hardCutoffAt: new Date(hardCutoffEpochMs).toISOString(),
    subjectStartedAtEpochMs: startedAtEpochMs,
    softCutoffEpochMs,
    hardCutoffEpochMs,
    totalTimeLimitMs,
    finalizationReserveMs,
    morpheusRunTimeoutMs,
  };
}

export function snapshotDeadline(
  record: SubjectDeadlineRecord,
  nowEpochMs: number,
): SubjectDeadlineSnapshot {
  return {
    elapsedMs: Math.max(0, nowEpochMs - record.subjectStartedAtEpochMs),
    softRemainingMs: Math.max(0, record.softCutoffEpochMs - nowEpochMs),
    hardRemainingMs: Math.max(0, record.hardCutoffEpochMs - nowEpochMs),
  };
}

export function renderDeadlinePromptTokens(
  prompt: string,
  record: SubjectDeadlineRecord,
): string {
  const values: Record<string, string> = {
    BENCHMARK_SUBJECT_STARTED_AT: record.subjectStartedAt,
    BENCHMARK_SOFT_CUTOFF_AT: record.softCutoffAt,
    BENCHMARK_HARD_CUTOFF_AT: record.hardCutoffAt,
    BENCHMARK_TOTAL_TIME_LIMIT_MS: String(record.totalTimeLimitMs),
    BENCHMARK_FINALIZATION_RESERVE_MS: String(record.finalizationReserveMs),
    BENCHMARK_MORPHEUS_TIMEOUT_MS: String(record.morpheusRunTimeoutMs),
  };
  let rendered = prompt;
  for (const [name, value] of Object.entries(values)) {
    rendered = rendered.replaceAll(`{{${name}}}`, value);
  }
  if (/\{\{BENCHMARK_[A-Z0-9_]+\}\}/.test(rendered)) {
    throw new Error("Unresolved benchmark deadline marker in subject prompt.");
  }
  return rendered;
}
