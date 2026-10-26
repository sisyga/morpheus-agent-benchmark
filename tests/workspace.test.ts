import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { chmod, lstat, mkdir, mkdtemp, readFile, readlink, rm, stat, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  buildAgentWorkspaceSnapshotDir,
  buildBenchmarkCodexEnv,
  snapshotAgentWorkspace,
  stageBenchmarkCommands,
} from "../src/benchmark/workspace.js";

const nativeMorpheusName = process.platform === "win32" ? "morpheus.cmd" : "morpheus";

async function writeNativeMorpheusExecutable(directory: string): Promise<string> {
  await mkdir(directory, { recursive: true });
  const executable = path.join(directory, nativeMorpheusName);
  await writeFile(
    executable,
    process.platform === "win32" ? "@echo off\r\nexit /b 0\r\n" : "#!/bin/sh\nexit 0\n",
    "utf8",
  );
  if (process.platform !== "win32") {
    await chmod(executable, 0o755);
  }
  return executable;
}

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n/g, "\n");
}

test("stageBenchmarkCommands installs time-left and Morpheus wrappers for capable modes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-command-stage-"));
  const deadlinePath = path.join(root, "subject_deadline.json");
  const trustedCommandDir = path.join(root, "trusted-tools");
  const realMorpheus = await writeNativeMorpheusExecutable(path.join(root, "real-bin"));
  const staged = await stageBenchmarkCommands({
    agentWorkspaceDir: path.join(root, "workspace"),
    trustedCommandDir,
    mode: "morpheus_cli",
    realMorpheusBin: realMorpheus,
    deadlinePath,
    morpheusRunTimeoutMs: 3_600_000,
    pythonExecutable: process.execPath,
    sourceRoot: process.cwd(),
  });

  assert.equal(staged.binDir, trustedCommandDir);
  assert.equal(staged.morpheusCommandPath, path.join(staged.binDir, nativeMorpheusName));
  assert.equal(
    staged.timeLeftCommandPath,
    path.join(staged.binDir, process.platform === "win32" ? "benchmark-time-left.cmd" : "benchmark-time-left"),
  );
  assert.ok((await stat(staged.morpheusCommandPath!)).isFile());
  assert.ok((await stat(staged.timeLeftCommandPath)).isFile());
  assert.match(await readFile(staged.morpheusCommandPath!, "utf8"), /morpheus_timed_launcher\.py/);
  const config = JSON.parse(await readFile(path.join(staged.binDir, "morpheus_launcher.json"), "utf8"));
  assert.equal(config.realMorpheusBin, realMorpheus);
  assert.equal(config.morpheusRunTimeoutMs, 3_600_000);

  const env = buildBenchmarkCodexEnv(
    { ...process.env, MORPHEUS_BIN: realMorpheus },
    "morpheus_cli",
    undefined,
    undefined,
    [],
    null,
    deadlinePath,
    staged,
  );
  assert.equal(env.BENCHMARK_DEADLINE_PATH, deadlinePath);
  assert.equal(env.MORPHEUS_BIN, staged.morpheusCommandPath);
  assert.equal("MORPHEUS_LAUNCHER_CONFIG" in env, false);
  assert.equal(env.PATH?.split(path.delimiter)[0], staged.binDir);
});

test("stageBenchmarkCommands shadows Morpheus with a generic unavailable command for python_web", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-command-stage-web-"));
  const hostBin = path.join(root, "host-bin");
  const realMorpheus = await writeNativeMorpheusExecutable(hostBin);
  const deadlinePath = path.join(root, "subject_deadline.json");
  const staged = await stageBenchmarkCommands({
    agentWorkspaceDir: root,
    mode: "python_web",
    realMorpheusBin: "morpheus",
    executableSearchPath: hostBin,
    deadlinePath,
    morpheusRunTimeoutMs: 3_600_000,
    pythonExecutable: process.execPath,
    sourceRoot: process.cwd(),
  });

  assert.equal(staged.morpheusCommandPath, null);
  assert.equal(staged.realMorpheusBin, realMorpheus);
  assert.ok((await stat(staged.timeLeftCommandPath)).isFile());
  assert.ok((await stat(path.join(staged.binDir, nativeMorpheusName))).isFile());

  const env = buildBenchmarkCodexEnv(
    {
      ...process.env,
      PATH: `${hostBin}${path.delimiter}${process.env.PATH ?? ""}`,
      MORPHEUS_BIN: realMorpheus,
    },
    "python_web",
    undefined,
    undefined,
    [],
    null,
    deadlinePath,
    staged,
  );
  assert.equal(env.PATH?.split(path.delimiter)[0], staged.binDir);
  assert.equal(env.PATH?.split(path.delimiter).includes(hostBin), true);
  assert.equal("MORPHEUS_BIN" in env, false);

  const unavailable = spawnSync("morpheus", ["--help"], {
    encoding: "utf8",
    env,
    shell: true,
  });
  assert.equal(unavailable.status, 127);
  assert.equal(unavailable.stdout, "");
  assert.equal(normalizeLineEndings(unavailable.stderr), "morpheus: command not found\n");
  assert.doesNotMatch(unavailable.stderr, /benchmark|python_web/i);
});

test("stageBenchmarkCommands records every PATH alias for the real Morpheus executable", async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-command-aliases-"));
  const realBinDir = path.join(root, "real-bin");
  const firstAliasDir = path.join(root, "first-bin");
  const secondAliasDir = path.join(root, "second-bin");
  await Promise.all([mkdir(firstAliasDir), mkdir(secondAliasDir)]);
  const realMorpheus = await writeNativeMorpheusExecutable(realBinDir);
  const firstAlias = path.join(firstAliasDir, nativeMorpheusName);
  const secondAlias = path.join(secondAliasDir, nativeMorpheusName);
  try {
    await Promise.all([symlink(realMorpheus, firstAlias), symlink(realMorpheus, secondAlias)]);
  } catch (error) {
    const code = error && typeof error === "object" && "code" in error ? error.code : null;
    if (code === "EPERM" || code === "EACCES") {
      t.skip("symbolic links are unavailable in this environment");
      return;
    }
    throw error;
  }

  const staged = await stageBenchmarkCommands({
    agentWorkspaceDir: path.join(root, "workspace"),
    mode: "python_web",
    realMorpheusBin: "morpheus",
    executableSearchPath: [firstAliasDir, secondAliasDir].join(path.delimiter),
    deadlinePath: path.join(root, "subject_deadline.json"),
    morpheusRunTimeoutMs: 3_600_000,
    pythonExecutable: process.execPath,
    sourceRoot: process.cwd(),
  });

  assert.deepEqual(staged.realMorpheusBinPaths, [firstAlias, secondAlias]);
});

test("stageBenchmarkCommands resolves a bare host Morpheus command before prepending its wrapper", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-command-resolve-"));
  const hostBin = path.join(root, "host-bin");
  const realMorpheus = await writeNativeMorpheusExecutable(hostBin);

  const staged = await stageBenchmarkCommands({
    agentWorkspaceDir: path.join(root, "workspace"),
    mode: "morpheus_cli",
    realMorpheusBin: "morpheus",
    executableSearchPath: hostBin,
    deadlinePath: path.join(root, "subject_deadline.json"),
    morpheusRunTimeoutMs: 3_600_000,
    pythonExecutable: process.execPath,
    sourceRoot: process.cwd(),
  });

  const config = JSON.parse(await readFile(staged.morpheusLauncherConfigPath!, "utf8"));
  assert.equal(config.realMorpheusBin, realMorpheus);
  assert.equal(staged.realMorpheusBin, realMorpheus);
  assert.notEqual(config.realMorpheusBin, staged.morpheusCommandPath);

  const env = buildBenchmarkCodexEnv(
    {
      ...process.env,
      PATH: `${hostBin}${path.delimiter}${process.env.PATH ?? ""}`,
      MORPHEUS_BIN: realMorpheus,
    },
    "morpheus_cli",
    undefined,
    undefined,
    [],
    null,
    path.join(root, "subject_deadline.json"),
    staged,
  );
  assert.equal(env.PATH?.split(path.delimiter).includes(hostBin), false);
  assert.equal(env.PATH?.split(path.delimiter)[0], staged.binDir);
  assert.equal(env.MORPHEUS_BIN, staged.morpheusCommandPath);
});

test("snapshotAgentWorkspace can re-snapshot symlinks and keeps in-workspace link targets after cleanup", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-snapshot-symlink-"));
  const workspace = path.join(root, "live_workspace");
  const runDir = path.join(root, "run");
  const attemptDir = path.join(workspace, "attempts", "attempt_001");
  const outsideFile = path.join(root, "outside.txt");
  await mkdir(attemptDir, { recursive: true });
  await mkdir(runDir, { recursive: true });
  await writeFile(path.join(attemptDir, "plot-1_00000.png"), "png-bytes", "utf8");
  await writeFile(outsideFile, "host data", "utf8");
  await symlink(path.join(attemptDir, "plot-1_00000.png"), path.join(attemptDir, "plot_00000.png"));
  await symlink(outsideFile, path.join(workspace, "outside_link.txt"));
  await symlink(path.join(workspace, "missing.png"), path.join(workspace, "dangling.png"));

  await snapshotAgentWorkspace(workspace, runDir);
  await snapshotAgentWorkspace(workspace, runDir);
  await rm(workspace, { recursive: true, force: true });

  const snapshotDir = buildAgentWorkspaceSnapshotDir(runDir);
  const snapshotPlot = path.join(snapshotDir, "attempts", "attempt_001", "plot_00000.png");
  assert.equal((await lstat(snapshotPlot)).isSymbolicLink(), false);
  assert.equal(await readFile(snapshotPlot, "utf8"), "png-bytes");
  const snapshotOutsideLink = path.join(snapshotDir, "outside_link.txt");
  assert.equal((await lstat(snapshotOutsideLink)).isSymbolicLink(), true);
  assert.equal(await readlink(snapshotOutsideLink), outsideFile);
  assert.equal((await lstat(path.join(snapshotDir, "dangling.png"))).isSymbolicLink(), true);
});
