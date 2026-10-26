import { chmod, copyFile, cp, lstat, mkdir, readdir, readlink, realpath, rm, stat, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import process from "node:process";

import type { ThreadOptions } from "@openai/codex-sdk";

import { CODEX_EXEC_TURN_TIMEOUT_ENV } from "./codex-exec.js";
import { BENCHMARK_DEADLINE_PATH_ENV } from "./deadline.js";
import { BENCHMARK_MODE_DEFINITIONS } from "./modes.js";
import { buildBenchmarkPythonEnv } from "./python-env.js";
import type {
  BenchmarkConfig,
  BenchmarkModeId,
} from "./types.js";

export const MORPHEUS_SKILL_REFERENCES_DIR = path.resolve(process.cwd(), ".agents", "skills", "morpheus", "references");
const BENCHMARK_CODEX_ENV_NAMES = [
  "PATH",
  "Path",
  "HOME",
  "USERPROFILE",
  "SystemRoot",
  "WINDIR",
  "ComSpec",
  "PATHEXT",
  "TEMP",
  "TMP",
  "TMPDIR",
  "LOCALAPPDATA",
  "APPDATA",
  "PSModulePath",
  "SHELL",
  "LANG",
  "LC_ALL",
] as const;
const BENCHMARK_CODEX_MODE_ENV_NAMES = ["MORPHEUS_BIN"] as const;
const SECRET_ENV_NAME_PATTERN = /(^|_)(?:TOKEN|SECRET|KEY|PASSWORD|CREDENTIAL|AUTH)(?:_|$)/i;

export type StagedBenchmarkCommands = {
  agentWorkspaceDir: string;
  binDir: string;
  tempDir: string;
  timeLeftCommandPath: string;
  morpheusCommandPath: string | null;
  morpheusLauncherConfigPath: string | null;
  realMorpheusBin: string | null;
  realMorpheusBinPaths: string[];
};

export type BenchmarkSubjectIsolation = {
  mode: BenchmarkModeId;
  codexHomeDir: string;
  benchmarkDeadlinePath: string;
  realMorpheusBin: string | null;
  realMorpheusBinPaths?: readonly string[];
  pythonRuntimeReadPaths?: readonly string[];
  systemPythonDenyPaths?: readonly string[];
};

export type StageBenchmarkCommandsParams = {
  agentWorkspaceDir: string;
  trustedCommandDir?: string;
  mode: BenchmarkModeId;
  realMorpheusBin: string | null;
  deadlinePath: string;
  morpheusRunTimeoutMs: number;
  pythonExecutable: string;
  executableSearchPath?: string;
  sourceRoot?: string;
};

export function buildBenchmarkThreadOptions(
  config: Pick<BenchmarkConfig, "model" | "reasoningEffort" | "codexApprovalPolicy">,
  activeRunDir: string,
  agentWorkspaceDir = buildBenchmarkAgentWorkspaceDir(activeRunDir),
  mode: BenchmarkModeId = "morpheus_mcp",
): ThreadOptions {
  const agentWorkspaceRoot = path.resolve(agentWorkspaceDir);
  const webSearchEnabled = BENCHMARK_MODE_DEFINITIONS[mode].capabilities.webSearch;

  return {
    model: config.model,
    // Codex CLI 0.147 supports GPT-5.6 efforts including "none" and "max"; the SDK declaration lags the catalog.
    modelReasoningEffort: config.reasoningEffort as ThreadOptions["modelReasoningEffort"],
    approvalPolicy: config.codexApprovalPolicy,
    workingDirectory: agentWorkspaceRoot,
    skipGitRepoCheck: true,
    webSearchMode: webSearchEnabled ? "live" : "disabled",
  };
}

export function buildBenchmarkAgentWorkspaceDir(activeRunDir: string): string {
  return buildBenchmarkScopedTempDir("morpheus-modeling-sessions", activeRunDir);
}

export function buildBenchmarkCodexHomeDir(activeRunDir: string): string {
  return buildBenchmarkScopedTempDir("morpheus-modeling-codex-home", activeRunDir);
}

function buildBenchmarkScopedTempDir(rootName: string, activeRunDir: string): string {
  const resolvedRunDir = path.resolve(activeRunDir);
  const runName = path.basename(resolvedRunDir);
  const parentName = path.basename(path.dirname(resolvedRunDir));
  if (parentName.endsWith("_benchmark")) {
    return path.join(tmpdir(), rootName, parentName.replace(/_benchmark$/, "_session"), runName);
  }
  return path.join(tmpdir(), rootName, runName);
}

export async function cleanupBenchmarkTempRunDirs(tempRunDirs: readonly string[]): Promise<void> {
  const uniqueDirs = [...new Set(tempRunDirs.map((dir) => path.resolve(dir)))];
  for (const dir of uniqueDirs) {
    if (!isBenchmarkTempRunDir(dir)) {
      continue;
    }
    await rm(dir, { recursive: true, force: true });
  }
}

function isBenchmarkTempRunDir(candidateDir: string): boolean {
  const resolvedDir = path.resolve(candidateDir);
  const allowedRoots = [
    path.join(tmpdir(), "morpheus-modeling-sessions"),
    path.join(tmpdir(), "morpheus-modeling-codex-home"),
  ].map((root) => path.resolve(root));

  return allowedRoots.some((root) => {
    const relative = path.relative(root, resolvedDir);
    if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) {
      return false;
    }
    return relative.split(path.sep).filter(Boolean).length >= 2;
  });
}

export function buildBenchmarkCodexHomeConfig(
  agentWorkspaceDir: string,
  _codexAllowedEnvVars: readonly string[] = [],
  subjectIsolation?: BenchmarkSubjectIsolation,
): string {
  const trustedWorkspaceRoot = path.dirname(path.resolve(agentWorkspaceDir)).replace(/'/g, "''");
  const lines = [
    'approval_policy = "never"',
    subjectIsolation ? 'default_permissions = "benchmark-subject"' : 'sandbox_mode = "workspace-write"',
    "",
    "[windows]",
    'sandbox = "elevated"',
    "",
    "[features]",
    "prevent_idle_sleep = false",
    "apps = false",
    "plugins = false",
    "remote_plugin = false",
    "",
    "[shell_environment_policy]",
    // The Codex child process environment is already filtered by buildBenchmarkCodexEnv.
    // Let command execution inherit that filtered env intact; Windows PowerShell can fail
    // during managed runtime startup when Codex reconstructs the env via include_only.
    'inherit = "all"',
    "ignore_default_excludes = false",
    "",
    `[projects.'${trustedWorkspaceRoot}']`,
    'trust_level = "trusted"',
    "",
  ];
  if (subjectIsolation) {
    lines.push(
      "[permissions.benchmark-subject]",
      "",
      "[permissions.benchmark-subject.filesystem]",
      '":minimal" = "read"',
      ...(subjectIsolation.systemPythonDenyPaths ?? []).map(
        (denyPath) => `${tomlString(path.resolve(denyPath))} = "deny"`,
      ),
      `${tomlString(path.resolve(agentWorkspaceDir))} = "write"`,
      `${tomlString(path.resolve(process.cwd(), ".venv"))} = "read"`,
      ...(subjectIsolation.pythonRuntimeReadPaths ?? []).map(
        (runtimePath) => `${tomlString(path.resolve(runtimePath))} = "read"`,
      ),
      `${tomlString(path.resolve(process.cwd(), "node_modules", "@openai"))} = "read"`,
      `${tomlString(path.join(path.resolve(subjectIsolation.codexHomeDir), "benchmark-tools"))} = "read"`,
      `${tomlString(path.resolve(subjectIsolation.benchmarkDeadlinePath))} = "read"`,
    );
    if (BENCHMARK_MODE_DEFINITIONS[subjectIsolation.mode].capabilities.morpheusSkill) {
      lines.push(
        `${tomlString(path.join(path.resolve(subjectIsolation.codexHomeDir), "skills", "morpheus"))} = "read"`,
      );
    }
    if (subjectIsolation.realMorpheusBin) {
      const access = BENCHMARK_MODE_DEFINITIONS[subjectIsolation.mode].capabilities.morpheusCli
        ? "read"
        : "deny";
      const executablePaths = subjectIsolation.realMorpheusBinPaths ?? [subjectIsolation.realMorpheusBin];
      for (const executablePath of executablePaths) {
        lines.push(`${tomlString(path.resolve(executablePath))} = "${access}"`);
      }
    }
    lines.push("");
  }
  return lines.join("\n");
}

function tomlString(value: string): string {
  return JSON.stringify(value);
}

export function buildAgentWorkspaceSnapshotDir(runDir: string): string {
  return path.join(runDir, "agent_workspace");
}

export function buildCodexHomeSnapshotDir(runDir: string): string {
  return path.join(runDir, "codex_home");
}

export function buildAgentWorkspaceStageFiles(params: {
  agentWorkspaceDir: string;
  runDir: string;
  pdfPath: string;
  paperTextPath: string;
  visualManifestPath: string;
  mode?: BenchmarkModeId;
}) {
  const base = {
    sourcePdfPath: params.pdfPath,
    sourcePaperTextPath: resolveArtifactPath(params.runDir, params.paperTextPath),
    sourceVisualManifestPath: resolveArtifactPath(params.runDir, params.visualManifestPath),
    agentPdfPath: path.join(params.agentWorkspaceDir, "paper.pdf"),
    agentPaperTextPath: path.join(params.agentWorkspaceDir, "paper.txt"),
    agentVisualManifestPath: path.join(params.agentWorkspaceDir, "paper_visual_manifest.json"),
  };
  if (params.mode !== "morpheus_cli_docs") {
    return base;
  }
  return {
    ...base,
    sourceMorpheusMlDocPath: path.join(MORPHEUS_SKILL_REFERENCES_DIR, "morpheusml-doc.md"),
    sourceModelTemplatePath: path.join(MORPHEUS_SKILL_REFERENCES_DIR, "model-template.md"),
    agentMorpheusMlDocPath: path.join(params.agentWorkspaceDir, "morpheusml_doc.txt"),
    agentModelTemplatePath: path.join(params.agentWorkspaceDir, "model_template.txt"),
  };
}

export function buildBenchmarkCodexEnv(
  baseEnv: NodeJS.ProcessEnv | Record<string, string | undefined>,
  mode: BenchmarkModeId,
  codexHomeDir?: string,
  codexTurnTimeoutMs?: number,
  codexAllowedEnvVars: readonly string[] = [],
  morpheusNumThreads: number | null = null,
  benchmarkDeadlinePath?: string,
  stagedCommands?: StagedBenchmarkCommands,
): Record<string, string> {
  const nextEnv = buildBenchmarkPythonEnv(
    buildBenchmarkCodexBaseEnv(baseEnv, mode, codexAllowedEnvVars),
  );
  if (codexHomeDir) {
    nextEnv.CODEX_HOME = codexHomeDir;
  }
  if (codexTurnTimeoutMs !== undefined) {
    nextEnv[CODEX_EXEC_TURN_TIMEOUT_ENV] = String(codexTurnTimeoutMs);
  }
  if (benchmarkDeadlinePath) {
    nextEnv[BENCHMARK_DEADLINE_PATH_ENV] = benchmarkDeadlinePath;
  }
  if (stagedCommands) {
    if (stagedCommands.realMorpheusBin && stagedCommands.morpheusCommandPath) {
      removeCommandPath(nextEnv, path.dirname(stagedCommands.realMorpheusBin));
    }
    nextEnv.HOME = stagedCommands.agentWorkspaceDir;
    nextEnv.USERPROFILE = stagedCommands.agentWorkspaceDir;
    nextEnv.TEMP = stagedCommands.tempDir;
    nextEnv.TMP = stagedCommands.tempDir;
    nextEnv.TMPDIR = stagedCommands.tempDir;
    nextEnv.XDG_CACHE_HOME = stagedCommands.tempDir;
    nextEnv.MPLCONFIGDIR = stagedCommands.tempDir;
    prependCommandPath(nextEnv, stagedCommands.binDir);
    if (stagedCommands.morpheusCommandPath && stagedCommands.morpheusLauncherConfigPath) {
      nextEnv.MORPHEUS_BIN = stagedCommands.morpheusCommandPath;
    }
  }
  if (mode !== "python_web") {
    Object.assign(nextEnv, buildMorpheusThreadEnv(morpheusNumThreads));
  }

  if (mode !== "python_web") {
    return nextEnv;
  }

  for (const key of Object.keys(nextEnv)) {
    if (key.toLowerCase().startsWith("morpheus")) {
      delete nextEnv[key];
    }
  }

  for (const pathKey of Object.keys(nextEnv).filter((key) => key.toLowerCase() === "path")) {
    nextEnv[pathKey] = nextEnv[pathKey]
      .split(path.delimiter)
      .filter((entry) => !hasMorpheusExecutablePathSegment(entry))
      .join(path.delimiter);
  }

  return nextEnv;
}

export async function stageBenchmarkCommands(
  params: StageBenchmarkCommandsParams,
): Promise<StagedBenchmarkCommands> {
  const sourceRoot = path.resolve(params.sourceRoot ?? process.cwd());
  const platform = process.platform;
  const binDir = path.resolve(params.trustedCommandDir ?? path.join(params.agentWorkspaceDir, ".benchmark-bin"));
  const agentWorkspaceDir = path.resolve(params.agentWorkspaceDir);
  const tempDir = path.join(agentWorkspaceDir, ".benchmark-tmp");
  await mkdir(binDir, { recursive: true });
  await mkdir(tempDir, { recursive: true });
  const timeLeftScript = path.join(binDir, "benchmark_time_left.py");
  await copyFile(path.join(sourceRoot, "scripts", "benchmark_time_left.py"), timeLeftScript);
  const timeLeftPosix = path.join(binDir, "benchmark-time-left");
  const timeLeftWindows = path.join(binDir, "benchmark-time-left.cmd");
  await writeFile(
    timeLeftPosix,
    `#!/bin/sh\nexec ${shellQuote(params.pythonExecutable)} ${shellQuote(timeLeftScript)} "$@"\n`,
    "utf8",
  );
  await writeFile(
    timeLeftWindows,
    `@echo off\r\n"${escapeCmdValue(params.pythonExecutable)}" "${escapeCmdValue(timeLeftScript)}" %*\r\nexit /b %ERRORLEVEL%\r\n`,
    "utf8",
  );
  await chmod(timeLeftPosix, 0o755);

  const morpheusCapable = BENCHMARK_MODE_DEFINITIONS[params.mode].capabilities.morpheusCli;
  if (!morpheusCapable) {
    const realMorpheusBin = params.realMorpheusBin
      ? await resolveExecutablePath(
          params.realMorpheusBin,
          params.executableSearchPath ?? process.env.PATH ?? "",
          platform,
        )
      : null;
    const realMorpheusBinPaths = realMorpheusBin
      ? await resolveExecutableAliasPaths(
          realMorpheusBin,
          params.executableSearchPath ?? process.env.PATH ?? "",
          platform,
        )
      : [];
    if (params.mode === "python_web") {
      const unavailablePosix = path.join(binDir, "morpheus");
      const unavailableWindows = path.join(binDir, "morpheus.cmd");
      await writeFile(
        unavailablePosix,
        "#!/bin/sh\nprintf '%s\\n' 'morpheus: command not found' >&2\nexit 127\n",
        "utf8",
      );
      await writeFile(
        unavailableWindows,
        "@echo off\r\n1>&2 echo morpheus: command not found\r\nexit /b 127\r\n",
        "utf8",
      );
      await chmod(unavailablePosix, 0o755);
    }
    return {
      agentWorkspaceDir,
      binDir,
      tempDir,
      timeLeftCommandPath: platform === "win32" ? timeLeftWindows : timeLeftPosix,
      morpheusCommandPath: null,
      morpheusLauncherConfigPath: null,
      realMorpheusBin,
      realMorpheusBinPaths,
    };
  }
  if (!params.realMorpheusBin) {
    throw new Error(`A real Morpheus executable is required for benchmark mode ${params.mode}.`);
  }
  const realMorpheusBin = await resolveExecutablePath(
    params.realMorpheusBin,
    params.executableSearchPath ?? process.env.PATH ?? "",
    platform,
  );
  const realMorpheusBinPaths = await resolveExecutableAliasPaths(
    realMorpheusBin,
    params.executableSearchPath ?? process.env.PATH ?? "",
    platform,
  );
  const launcherScript = path.join(binDir, "morpheus_timed_launcher.py");
  const processScript = path.join(binDir, "morpheus_process.py");
  const launcherConfigPath = path.join(binDir, "morpheus_launcher.json");
  await copyFile(path.join(sourceRoot, "morpheus_timed_launcher.py"), launcherScript);
  await copyFile(path.join(sourceRoot, "morpheus_process.py"), processScript);
  await writeFile(
    launcherConfigPath,
    `${JSON.stringify({
      realMorpheusBin,
      morpheusRunTimeoutMs: params.morpheusRunTimeoutMs,
      deadlinePath: params.deadlinePath,
    }, null, 2)}\n`,
    "utf8",
  );
  const morpheusPosix = path.join(binDir, "morpheus");
  const morpheusWindows = path.join(binDir, "morpheus.cmd");
  await writeFile(
    morpheusPosix,
    [
      "#!/bin/sh",
      `MORPHEUS_LAUNCHER_CONFIG=${shellQuote(launcherConfigPath)}`,
      "export MORPHEUS_LAUNCHER_CONFIG",
      `exec ${shellQuote(params.pythonExecutable)} ${shellQuote(launcherScript)} "$@"`,
      "",
    ].join("\n"),
    "utf8",
  );
  await writeFile(
    morpheusWindows,
    [
      "@echo off",
      `set "MORPHEUS_LAUNCHER_CONFIG=${escapeCmdValue(launcherConfigPath)}"`,
      `"${escapeCmdValue(params.pythonExecutable)}" "${escapeCmdValue(launcherScript)}" %*`,
      "exit /b %ERRORLEVEL%",
      "",
    ].join("\r\n"),
    "utf8",
  );
  await chmod(morpheusPosix, 0o755);
  return {
    agentWorkspaceDir,
    binDir,
    tempDir,
    timeLeftCommandPath: platform === "win32" ? timeLeftWindows : timeLeftPosix,
    morpheusCommandPath: platform === "win32" ? morpheusWindows : morpheusPosix,
    morpheusLauncherConfigPath: launcherConfigPath,
    realMorpheusBin,
    realMorpheusBinPaths,
  };
}

async function resolveExecutableAliasPaths(
  executablePath: string,
  searchPath: string,
  platform: NodeJS.Platform,
): Promise<string[]> {
  let target: string;
  try {
    target = await realpath(executablePath);
  } catch {
    return [executablePath];
  }
  const targetKey = platform === "win32" ? target.toLowerCase() : target;
  const aliases = new Set<string>([executablePath]);
  const executableName = path.basename(executablePath);
  for (const directory of searchPath.split(path.delimiter).filter(Boolean)) {
    const candidate = path.resolve(directory, executableName);
    try {
      const candidateTarget = await realpath(candidate);
      const candidateKey = platform === "win32" ? candidateTarget.toLowerCase() : candidateTarget;
      if (candidateKey === targetKey) {
        aliases.add(candidate);
      }
    } catch {
      // Ignore missing or inaccessible PATH entries.
    }
  }
  return [...aliases];
}

async function resolveExecutablePath(
  executable: string,
  searchPath: string,
  platform: NodeJS.Platform,
): Promise<string> {
  if (path.isAbsolute(executable) || executable.includes("/") || executable.includes("\\")) {
    return path.resolve(executable);
  }
  const suffixes = platform === "win32" ? [".exe", ".cmd", ".bat", ""] : [""];
  for (const directory of searchPath.split(path.delimiter).filter(Boolean)) {
    for (const suffix of suffixes) {
      const candidate = path.resolve(directory, `${executable}${suffix}`);
      try {
        if ((await stat(candidate)).isFile()) {
          return candidate;
        }
      } catch {
        // Try the next PATH entry.
      }
    }
  }
  throw new Error(`Unable to resolve the real Morpheus executable before staging its wrapper: ${executable}`);
}

function prependCommandPath(env: Record<string, string>, binDir: string): void {
  const pathKeys = Object.keys(env).filter((key) => key.toLowerCase() === "path");
  if (pathKeys.length === 0) {
    env.PATH = binDir;
    return;
  }
  for (const key of pathKeys) {
    env[key] = [binDir, env[key]].filter(Boolean).join(path.delimiter);
  }
}

function removeCommandPath(env: Record<string, string>, directory: string): void {
  const resolvedDirectory = path.resolve(directory);
  for (const key of Object.keys(env).filter((name) => name.toLowerCase() === "path")) {
    env[key] = env[key]
      .split(path.delimiter)
      .filter((entry) => path.resolve(entry) !== resolvedDirectory)
      .join(path.delimiter);
  }
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'"'"'`)}'`;
}

function escapeCmdValue(value: string): string {
  return value.replace(/%/g, "%%").replace(/"/g, '""');
}

export function buildMorpheusThreadEnv(morpheusNumThreads: number | null): Record<string, string> {
  if (morpheusNumThreads === null) {
    return {};
  }
  return {
    MORPHEUS_NUM_THREADS: String(morpheusNumThreads),
    OMP_NUM_THREADS: String(morpheusNumThreads),
  };
}

export function applyMorpheusThreadEnv(
  env: NodeJS.ProcessEnv,
  morpheusNumThreads: number | null,
): void {
  if (morpheusNumThreads === null) {
    return;
  }
  const threadEnv = buildMorpheusThreadEnv(morpheusNumThreads);
  for (const [key, value] of Object.entries(threadEnv)) {
    env[key] = value;
  }
}

function buildBenchmarkCodexBaseEnv(
  baseEnv: NodeJS.ProcessEnv | Record<string, string | undefined>,
  mode: BenchmarkModeId,
  codexAllowedEnvVars: readonly string[],
): Record<string, string> {
  const env: Record<string, string> = {};
  const envNames = [
    ...BENCHMARK_CODEX_ENV_NAMES,
    ...(mode === "python_web" ? [] : BENCHMARK_CODEX_MODE_ENV_NAMES),
    ...codexAllowedEnvVars,
  ];
  copyAllowedBenchmarkEnvVars(env, baseEnv, envNames);
  return env;
}

function copyAllowedBenchmarkEnvVars(
  target: Record<string, string>,
  source: NodeJS.ProcessEnv | Record<string, string | undefined>,
  allowedNames: readonly string[],
): void {
  const allowed = new Set(allowedNames.map((name) => name.toLowerCase()));
  for (const [key, value] of Object.entries(source)) {
    if (typeof value !== "string" || !allowed.has(key.toLowerCase()) || isSecretEnvName(key)) {
      continue;
    }
    target[key] = value;
  }
}

function uniqueEnvNames(names: readonly string[]): string[] {
  const uniqueNames: string[] = [];
  const seen = new Set<string>();
  for (const name of names) {
    const normalized = name.trim();
    if (!normalized || isSecretEnvName(normalized)) {
      continue;
    }
    const seenKey = normalized.toLowerCase();
    if (!seen.has(seenKey)) {
      uniqueNames.push(normalized);
      seen.add(seenKey);
    }
  }
  return uniqueNames;
}

function isSecretEnvName(name: string): boolean {
  return SECRET_ENV_NAME_PATTERN.test(name);
}

function hasMorpheusExecutablePathSegment(entry: string): boolean {
  return entry.split(/[\\/]+/).some((segment) => segment.toLowerCase() === "morpheus");
}

export function getBenchmarkSkillPathsForMode(
  config: Pick<BenchmarkConfig, "skillPaths">,
  mode: BenchmarkModeId,
): readonly string[] {
  return BENCHMARK_MODE_DEFINITIONS[mode].capabilities.morpheusSkill ? config.skillPaths : [];
}

export async function prepareBenchmarkCodexHome(
  codexHomeDir: string,
  agentWorkspaceDir: string,
  skillPaths: readonly string[] = [],
  codexAllowedEnvVars: readonly string[] = [],
  subjectIsolation?: Omit<BenchmarkSubjectIsolation, "codexHomeDir">,
): Promise<void> {
  await mkdir(codexHomeDir, { recursive: true });
  await copyOptionalCodexHomeFile(codexHomeDir, "auth.json");
  await copyOptionalCodexHomeFile(codexHomeDir, "installation_id");
  await syncBenchmarkSkills(codexHomeDir, skillPaths);
  await writeFile(
    path.join(codexHomeDir, "config.toml"),
    buildBenchmarkCodexHomeConfig(
      agentWorkspaceDir,
      codexAllowedEnvVars,
      subjectIsolation ? { ...subjectIsolation, codexHomeDir } : undefined,
    ),
    "utf8",
  );
}

async function syncBenchmarkSkills(codexHomeDir: string, skillPaths: readonly string[]): Promise<void> {
  const desiredSkillNames = new Set(skillPaths.map((skillPath) => path.basename(path.dirname(skillPath))));
  await removeUnlistedBenchmarkSkills(codexHomeDir, desiredSkillNames);

  for (const skillPath of skillPaths) {
    const sourceSkillDir = path.dirname(skillPath);
    const destinationSkillDir = path.join(codexHomeDir, "skills", path.basename(sourceSkillDir));
    await rm(destinationSkillDir, { recursive: true, force: true });
    await cp(sourceSkillDir, destinationSkillDir, {
      recursive: true,
      force: true,
    });
  }
}

async function removeUnlistedBenchmarkSkills(codexHomeDir: string, desiredSkillNames: Set<string>): Promise<void> {
  const skillsRoot = path.join(codexHomeDir, "skills");
  let entries;
  try {
    entries = await readdir(skillsRoot, { withFileTypes: true });
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return;
    }
    throw error;
  }

  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === ".system" || desiredSkillNames.has(entry.name)) {
      continue;
    }
    await rm(path.join(skillsRoot, entry.name), { recursive: true, force: true });
  }
}

export async function snapshotBenchmarkCodexHome(codexHomeDir: string, runDir: string): Promise<void> {
  await snapshotCodexHomeTo(codexHomeDir, buildCodexHomeSnapshotDir(runDir));
}

export async function snapshotCodexHomeTo(codexHomeDir: string, snapshotDir: string): Promise<void> {
  await copyOptionalSnapshotFile(codexHomeDir, snapshotDir, "config.toml");
  await copyOptionalSnapshotFile(codexHomeDir, snapshotDir, "cap_sid");
  await copyOptionalSnapshotFile(codexHomeDir, snapshotDir, "session_index.jsonl");
  await copyOptionalSnapshotDirectory(codexHomeDir, snapshotDir, "sessions");
  await copyOptionalSnapshotNonSystemSkills(codexHomeDir, snapshotDir);
  await copyOptionalSnapshotFile(codexHomeDir, snapshotDir, path.join(".sandbox", "setup_marker.json"));
  await copyOptionalSnapshotFile(codexHomeDir, snapshotDir, path.join(".sandbox", "sandbox.log"));
}

async function copyOptionalSnapshotFile(sourceRoot: string, snapshotRoot: string, relativePath: string): Promise<void> {
  try {
    const sourcePath = path.join(sourceRoot, relativePath);
    const destinationPath = path.join(snapshotRoot, relativePath);
    await mkdir(path.dirname(destinationPath), { recursive: true });
    await copyFile(sourcePath, destinationPath);
  } catch (error) {
    if (!isFileNotFoundError(error)) {
      throw error;
    }
  }
}

async function copyOptionalSnapshotDirectory(
  sourceRoot: string,
  snapshotRoot: string,
  relativePath: string,
): Promise<void> {
  try {
    const destinationPath = path.join(snapshotRoot, relativePath);
    await mkdir(path.dirname(destinationPath), { recursive: true });
    await copySnapshotTree(path.join(sourceRoot, relativePath), destinationPath);
  } catch (error) {
    if (!isFileNotFoundError(error)) {
      throw error;
    }
  }
}

async function copyOptionalSnapshotNonSystemSkills(sourceRoot: string, snapshotRoot: string): Promise<void> {
  const sourceSkillsRoot = path.join(sourceRoot, "skills");
  const destinationSkillsRoot = path.join(snapshotRoot, "skills");
  let entries;
  try {
    entries = await readdir(sourceSkillsRoot, { withFileTypes: true });
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return;
    }
    throw error;
  }

  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name === ".system") {
      continue;
    }
    await mkdir(destinationSkillsRoot, { recursive: true });
    await cp(path.join(sourceSkillsRoot, entry.name), path.join(destinationSkillsRoot, entry.name), {
      recursive: true,
      force: true,
    });
  }
}

async function copyOptionalCodexHomeFile(codexHomeDir: string, filename: string): Promise<void> {
  try {
    await copyFile(path.join(resolveSourceCodexHome(), filename), path.join(codexHomeDir, filename));
  } catch (error) {
    if (!isFileNotFoundError(error)) {
      throw error;
    }
  }
}

function resolveSourceCodexHome(): string {
  return process.env.CODEX_HOME ?? path.join(process.env.USERPROFILE ?? process.env.HOME ?? "", ".codex");
}

export async function stageBenchmarkAgentWorkspace(params: ReturnType<typeof buildAgentWorkspaceStageFiles>): Promise<void> {
  await mkdir(path.dirname(params.agentPdfPath), { recursive: true });
  await copyFile(params.sourcePdfPath, params.agentPdfPath);
  await copyFile(params.sourcePaperTextPath, params.agentPaperTextPath);
  await copyFile(params.sourceVisualManifestPath, params.agentVisualManifestPath);
  if ("sourceMorpheusMlDocPath" in params) {
    await copyFile(params.sourceMorpheusMlDocPath, params.agentMorpheusMlDocPath);
    await copyFile(params.sourceModelTemplatePath, params.agentModelTemplatePath);
  }
}

export async function restoreAgentWorkspaceFromSnapshot(runDir: string, agentWorkspaceDir: string): Promise<void> {
  const snapshotDir = buildAgentWorkspaceSnapshotDir(runDir);
  if (!(await directoryExists(snapshotDir))) {
    return;
  }
  await cp(snapshotDir, agentWorkspaceDir, {
    recursive: true,
    force: true,
  });
}

export async function copyRecoveredModelToAgentWorkspace(runDir: string, agentWorkspaceDir: string): Promise<void> {
  const modelPath = path.join(runDir, "model.xml");
  if (!(await fileExists(modelPath))) {
    return;
  }
  await mkdir(agentWorkspaceDir, { recursive: true });
  await copyFile(modelPath, path.join(agentWorkspaceDir, "model.xml"));
}

export async function restoreBenchmarkCodexHomeFromSnapshot(runDir: string, codexHomeDir: string): Promise<void> {
  const snapshotDir = buildCodexHomeSnapshotDir(runDir);
  if (!(await directoryExists(snapshotDir))) {
    return;
  }
  await cp(snapshotDir, codexHomeDir, {
    recursive: true,
    force: true,
  });
}

export async function syncAgentModelXml(agentWorkspaceDir: string, runDir: string): Promise<void> {
  try {
    await copyFile(path.join(agentWorkspaceDir, "model.xml"), path.join(runDir, "model.xml"));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "ENOENT") {
      throw error;
    }
  }
}

export async function recoverModelXmlFromAgentWorkspace(runDir: string): Promise<boolean> {
  const agentModelPath = path.join(runDir, "agent_workspace", "model.xml");
  const hostModelPath = path.join(runDir, "model.xml");
  if (!(await fileExists(agentModelPath))) {
    return false;
  }
  await copyFile(agentModelPath, hostModelPath);
  return true;
}

export async function snapshotAgentWorkspace(agentWorkspaceDir: string, runDir: string): Promise<void> {
  await copySnapshotTree(agentWorkspaceDir, buildAgentWorkspaceSnapshotDir(runDir));
}

/**
 * Copies a live temp tree into a durable snapshot. Symlinks to files inside the tree become
 * regular files, so the snapshot stays readable after the temp tree is cleaned up; other
 * links are recreated verbatim and never followed out of the tree. Handling links here also
 * avoids Node 18's `cp`, which throws ERR_FS_CP_EINVAL when re-copying a symlink onto an
 * identical existing one.
 */
async function copySnapshotTree(sourceRoot: string, destinationRoot: string): Promise<void> {
  const realSourceRoot = await realpath(sourceRoot);
  await cp(sourceRoot, destinationRoot, {
    recursive: true,
    force: true,
    filter: async (sourcePath, destinationPath) => {
      if (!(await lstat(sourcePath)).isSymbolicLink()) {
        return true;
      }
      await copySnapshotSymlink(sourcePath, destinationPath, realSourceRoot);
      return false;
    },
  });
}

async function copySnapshotSymlink(sourcePath: string, destinationPath: string, realSourceRoot: string): Promise<void> {
  await rm(destinationPath, { recursive: true, force: true });
  await mkdir(path.dirname(destinationPath), { recursive: true });
  const target = await resolveSymlinkTarget(sourcePath);
  const relativeTarget = target === null ? "" : path.relative(realSourceRoot, target);
  const insideSource = relativeTarget !== "" && !relativeTarget.startsWith("..") && !path.isAbsolute(relativeTarget);
  if (target !== null && insideSource && (await stat(target)).isFile()) {
    await copyFile(target, destinationPath);
    return;
  }
  await symlink(await readlink(sourcePath), destinationPath);
}

async function resolveSymlinkTarget(linkPath: string): Promise<string | null> {
  try {
    return await realpath(linkPath);
  } catch (error) {
    if (isFileNotFoundError(error) || (error as NodeJS.ErrnoException).code === "ELOOP") {
      return null;
    }
    throw error;
  }
}

function resolveArtifactPath(runDir: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(runDir, value);
}

function isFileNotFoundError(error: unknown): boolean {
  return error instanceof Error && "code" in error && (error as NodeJS.ErrnoException).code === "ENOENT";
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    const info = await stat(filePath);
    return info.isFile() && info.size > 0;
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return false;
    }
    throw error;
  }
}

async function directoryExists(directoryPath: string): Promise<boolean> {
  try {
    const info = await stat(directoryPath);
    return info.isDirectory();
  } catch (error) {
    if (isFileNotFoundError(error)) {
      return false;
    }
    throw error;
  }
}
