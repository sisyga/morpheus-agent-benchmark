import assert from "node:assert/strict";
import test from "node:test";

import {
  createDeadlineRecord,
  renderDeadlinePromptTokens,
  snapshotDeadline,
} from "../src/benchmark/deadline.js";

test("createDeadlineRecord derives a five-hour hard cutoff and ten-minute reserve", () => {
  const record = createDeadlineRecord(
    Date.parse("2026-08-20T08:00:00.000Z"),
    5 * 60 * 60 * 1000,
    10 * 60 * 1000,
    60 * 60 * 1000,
  );

  assert.equal(record.subjectStartedAt, "2026-08-20T08:00:00.000Z");
  assert.equal(record.softCutoffAt, "2026-08-20T12:50:00.000Z");
  assert.equal(record.hardCutoffAt, "2026-08-20T13:00:00.000Z");
  assert.equal(record.totalTimeLimitMs, 18_000_000);
  assert.equal(record.finalizationReserveMs, 600_000);
});

test("snapshotDeadline reports elapsed and clamped remaining time", () => {
  const record = createDeadlineRecord(
    Date.parse("2026-08-20T08:00:00.000Z"),
    5 * 60 * 60 * 1000,
    10 * 60 * 1000,
    60 * 60 * 1000,
  );

  assert.deepEqual(snapshotDeadline(record, Date.parse("2026-08-20T12:40:00.000Z")), {
    elapsedMs: 16_800_000,
    softRemainingMs: 600_000,
    hardRemainingMs: 1_200_000,
  });
  assert.deepEqual(snapshotDeadline(record, Date.parse("2026-08-20T13:01:00.000Z")), {
    elapsedMs: 18_060_000,
    softRemainingMs: 0,
    hardRemainingMs: 0,
  });
});

test("renderDeadlinePromptTokens substitutes all authoritative deadline values", () => {
  const record = createDeadlineRecord(
    Date.parse("2026-08-20T08:00:00.000Z"),
    14_400_000,
    600_000,
    3_600_000,
  );
  const template = [
    "start={{BENCHMARK_SUBJECT_STARTED_AT}}",
    "soft={{BENCHMARK_SOFT_CUTOFF_AT}}",
    "hard={{BENCHMARK_HARD_CUTOFF_AT}}",
    "total={{BENCHMARK_TOTAL_TIME_LIMIT_MS}}",
    "reserve={{BENCHMARK_FINALIZATION_RESERVE_MS}}",
    "morpheus={{BENCHMARK_MORPHEUS_TIMEOUT_MS}}",
  ].join("\n");

  const rendered = renderDeadlinePromptTokens(template, record);

  assert.match(rendered, /start=2026-08-20T08:00:00.000Z/);
  assert.match(rendered, /soft=2026-08-20T11:50:00.000Z/);
  assert.match(rendered, /hard=2026-08-20T12:00:00.000Z/);
  assert.match(rendered, /total=14400000/);
  assert.match(rendered, /reserve=600000/);
  assert.match(rendered, /morpheus=3600000/);
  assert.doesNotMatch(rendered, /\{\{BENCHMARK_/);
});

test("renderDeadlinePromptTokens rejects unknown benchmark deadline markers", () => {
  const record = createDeadlineRecord(0, 10_000, 1_000, 5_000);
  assert.throws(
    () => renderDeadlinePromptTokens("{{BENCHMARK_UNKNOWN_DEADLINE}}", record),
    /Unresolved benchmark deadline marker/,
  );
});
