/* node:coverage disable */
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPythonBridgeProcessTreeCleanupPlan,
  buildPythonBridgeSpawnOptions,
} from "../src/benchmark/python-bridge.js";

test("PythonBridge timeout cleanup force-kills Windows process trees", () => {
  assert.deepEqual(buildPythonBridgeProcessTreeCleanupPlan(1234, "win32", "SIGTERM"), {
    kind: "taskkill",
    command: "taskkill.exe",
    args: ["/F", "/T", "/PID", "1234"],
  });
});

test("PythonBridge timeout cleanup targets POSIX process groups", () => {
  assert.deepEqual(buildPythonBridgeProcessTreeCleanupPlan(1234, "linux", "SIGTERM"), {
    kind: "process-group",
    pid: -1234,
    signal: "SIGTERM",
  });
});

test("PythonBridge spawns bridge processes in a cleanup-friendly process group on POSIX", () => {
  assert.deepEqual(buildPythonBridgeSpawnOptions("linux"), { detached: true });
  assert.deepEqual(buildPythonBridgeSpawnOptions("darwin"), { detached: true });
  assert.deepEqual(buildPythonBridgeSpawnOptions("win32"), { detached: false });
});
