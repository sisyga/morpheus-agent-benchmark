import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, readdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { promisify } from "node:util";

import {
  BENCHMARK_VERSION,
  type BenchmarkConfig,
  type BenchmarkProvenance,
  type BenchmarkSoftware,
  type BenchmarkSummary,
} from "./types.js";
import { resolveBenchmarkPythonExecutable } from "./python-env.js";
import { MORPHEUS_SKILL_REFERENCES_DIR } from "./workspace.js";

const execFileAsync = promisify(execFile);

export type SoftwareExecutables = {
  morpheus: string;
  python: string;
  uv: string;
};

export async function collectBenchmarkProvenance(
  config: Pick<BenchmarkConfig, "skillPaths" | "benchmarkFocusDir">,
  repoRoot = process.cwd(),
  executables: SoftwareExecutables = {
    morpheus: process.env.MORPHEUS_BIN ?? "morpheus",
    python: resolveBenchmarkPythonExecutable(),
    uv: "uv",
  },
): Promise<BenchmarkProvenance> {
  const [gitCommit, gitTag, gitDirty] = await Promise.all([
    gitOutput(repoRoot, ["rev-parse", "HEAD"]),
    gitOutput(repoRoot, ["describe", "--tags", "--exact-match", "HEAD"]),
    gitOutput(repoRoot, ["status", "--porcelain", "--untracked-files=no"]).then((status) =>
      status === null ? null : status.length > 0,
    ),
  ]);
  return {
    benchmarkVersion: BENCHMARK_VERSION,
    gitCommit,
    gitTag,
    gitDirty,
    skills: await Promise.all(
      config.skillPaths.map(async (skillPath) => ({
        name: path.basename(path.dirname(skillPath)),
        sha256: await hashOptionalDirectoryTree(path.dirname(skillPath)),
      })),
    ),
    docsReferences: {
      morpheusMlDocSha256: await hashOptionalFile(path.join(MORPHEUS_SKILL_REFERENCES_DIR, "morpheusml-doc.md")),
      modelTemplateSha256: await hashOptionalFile(path.join(MORPHEUS_SKILL_REFERENCES_DIR, "model-template.md")),
    },
    prompts: {
      subjectPromptSourceSha256: await hashOptionalFile(path.join(repoRoot, "src", "benchmark", "prompt.ts")),
      mcpServerSha256: await hashOptionalFile(path.join(repoRoot, "morpheus_mcp_server.py")),
      focusSha256: config.benchmarkFocusDir ? await hashOptionalDirectoryTree(config.benchmarkFocusDir) : null,
    },
    software: await collectBenchmarkSoftware(repoRoot, executables),
  };
}

export async function collectBenchmarkSoftware(
  repoRoot: string,
  executables: SoftwareExecutables,
): Promise<BenchmarkSoftware> {
  const [
    codexSdk,
    codexCli,
    packageLock,
    installedPackages,
    morpheus,
    morpheusRevision,
    gnuplot,
    python,
    pythonInstalledMatchesLock,
  ] = await Promise.all([
    readPackageVersion(path.join(repoRoot, "node_modules", "@openai", "codex-sdk", "package.json")),
    readPackageVersion(path.join(repoRoot, "node_modules", "@openai", "codex", "package.json")),
    readOptionalJson(path.join(repoRoot, "package-lock.json")),
    readOptionalJson(path.join(repoRoot, "node_modules", ".package-lock.json")),
    commandOutput(executables.morpheus, ["--version"]),
    commandOutput(executables.morpheus, ["--revision"]),
    commandOutput(executables.morpheus, ["--gnuplot-version"]),
    commandOutput(executables.python, ["--version"]),
    commandSucceeds(executables.uv, ["sync", "--locked", "--check"], repoRoot),
  ]);
  const lockedPackages = isRecord(packageLock) && isRecord(packageLock.packages) ? packageLock.packages : {};
  const lockedSdk = lockedPackages["node_modules/@openai/codex-sdk"];
  return {
    node: process.version,
    platform: `${process.platform}-${process.arch} ${os.release()}`,
    codexSdk,
    codexSdkLocked: isRecord(lockedSdk) && typeof lockedSdk.version === "string" ? lockedSdk.version : null,
    codexCli,
    morpheus: firstLineValue(morpheus, /^Version:\s*(.+)$/m),
    morpheusRevision: firstLineValue(morpheusRevision, /^Revision:\s*(.+)$/m),
    gnuplot: firstLineValue(gnuplot, /^(gnuplot\s.+)$/m),
    python: firstLineValue(python, /^Python\s+(.+)$/m),
    packageLockSha256: await hashOptionalFile(path.join(repoRoot, "package-lock.json")),
    uvLockSha256: await hashOptionalFile(path.join(repoRoot, "uv.lock")),
    npmInstalledMatchesLock: npmInstallMatchesLock(packageLock, installedPackages),
    pythonInstalledMatchesLock,
  };
}

/**
 * Compares package-lock.json with npm's record of the installed tree (node_modules/.package-lock.json).
 * Optional packages for other platforms are legitimately absent.
 */
export function npmInstallMatchesLock(packageLock: unknown, installedLock: unknown): boolean | null {
  if (!isRecord(packageLock) || !isRecord(packageLock.packages)) {
    return null;
  }
  const installed = isRecord(installedLock) && isRecord(installedLock.packages) ? installedLock.packages : {};
  return Object.entries(packageLock.packages).every(([packagePath, locked]) => {
    if (packagePath === "" || !isRecord(locked)) {
      return true;
    }
    const present = installed[packagePath];
    if (!isRecord(present)) {
      return locked.optional === true;
    }
    return present.version === locked.version;
  });
}

/** Software differences do not invalidate a run, but recovery and combining should say so. */
export function describeSoftwareDifferences(
  recorded: BenchmarkSoftware | undefined,
  current: BenchmarkSoftware | undefined,
): string[] {
  if (!recorded || !current) {
    return [];
  }
  return (Object.keys(recorded) as Array<keyof BenchmarkSoftware>)
    .filter((key) => recorded[key] !== current[key])
    .map((key) => `${key}: ${recorded[key] ?? "unknown"} -> ${current[key] ?? "unknown"}`);
}

/** Runs written before benchmark versions were stamped are inferred from their protocol. */
export function resolveBenchmarkVersion(
  summary: Pick<BenchmarkSummary, "benchmarkVersion" | "benchmarkProtocol"> | null | undefined,
): number {
  if (typeof summary?.benchmarkVersion === "number") {
    return summary.benchmarkVersion;
  }
  return summary?.benchmarkProtocol === "time_limit_v2" ? 2 : 1;
}

/**
 * Subject executions for an existing run must use the benchmark version and skill content that produced it.
 * Throws with the git tag to check out when they differ.
 */
export function assertProvenanceAllowsSubjectExecution(
  recorded: Pick<BenchmarkSummary, "benchmarkVersion" | "benchmarkProtocol" | "benchmarkProvenance">,
  current: BenchmarkProvenance,
): void {
  const recordedVersion = resolveBenchmarkVersion(recorded);
  if (recordedVersion !== current.benchmarkVersion) {
    throw new Error(
      `This run was produced by benchmark v${recordedVersion}, but the current code is benchmark v${current.benchmarkVersion}. `
      + `Check out tag benchmark-v${recordedVersion} to launch subject executions for it.`,
    );
  }
  const recordedPrompts = recorded.benchmarkProvenance?.prompts;
  if (recordedPrompts) {
    const changedPrompts = (Object.keys(recordedPrompts) as Array<keyof BenchmarkProvenance["prompts"]>)
      .filter((key) => recordedPrompts[key] !== current.prompts[key]);
    if (changedPrompts.length > 0) {
      throw new Error(
        `Subject-facing prompts changed since this run started (${changedPrompts.join(", ")}). `
        + "Restore them or bump BENCHMARK_VERSION and start a new run.",
      );
    }
  }
  const recordedSkills = recorded.benchmarkProvenance?.skills ?? [];
  for (const skill of recordedSkills) {
    const currentSkill = current.skills.find((candidate) => candidate.name === skill.name);
    if (skill.sha256 !== null && currentSkill?.sha256 !== skill.sha256) {
      throw new Error(
        `Skill "${skill.name}" changed since this run started (recorded ${skill.sha256.slice(0, 12)}, `
        + `current ${currentSkill?.sha256?.slice(0, 12) ?? "missing"}). Restore the recorded skill or bump BENCHMARK_VERSION and start a new run.`,
      );
    }
  }
}

export function skillSha256ByName(provenance: BenchmarkProvenance | undefined): Record<string, string | null> {
  return Object.fromEntries((provenance?.skills ?? []).map((skill) => [skill.name, skill.sha256]));
}

/** Hash of every file below `root`, keyed by POSIX relative path, with CRLF normalized so Windows and Linux checkouts agree. */
export async function hashDirectoryTree(root: string): Promise<string> {
  const hash = createHash("sha256");
  for (const relativePath of await listFilesRecursive(root)) {
    const content = normalizeTextContent(await readFile(path.join(root, relativePath)));
    hash.update(relativePath.split(path.sep).join("/"));
    hash.update("\0");
    hash.update(createHash("sha256").update(content).digest("hex"));
    hash.update("\n");
  }
  return hash.digest("hex");
}

async function hashOptionalDirectoryTree(root: string): Promise<string | null> {
  try {
    return await hashDirectoryTree(root);
  } catch {
    return null;
  }
}

async function hashOptionalFile(filePath: string): Promise<string | null> {
  try {
    return createHash("sha256").update(normalizeTextContent(await readFile(filePath))).digest("hex");
  } catch {
    return null;
  }
}

async function listFilesRecursive(root: string, relativeDir = ""): Promise<string[]> {
  const entries = await readdir(path.join(root, relativeDir), { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries.sort((left, right) => (left.name < right.name ? -1 : left.name > right.name ? 1 : 0))) {
    const relativePath = path.join(relativeDir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listFilesRecursive(root, relativePath));
    } else if (entry.isFile()) {
      files.push(relativePath);
    }
  }
  return files;
}

function normalizeTextContent(content: Buffer): Buffer {
  if (content.includes(0)) {
    return content;
  }
  return Buffer.from(content.toString("latin1").replace(/\r\n/g, "\n"), "latin1");
}

async function readPackageVersion(packageJsonPath: string): Promise<string | null> {
  const parsed = await readOptionalJson(packageJsonPath);
  return isRecord(parsed) && typeof parsed.version === "string" ? parsed.version : null;
}

async function readOptionalJson(filePath: string): Promise<unknown> {
  try {
    return JSON.parse(await readFile(filePath, "utf8")) as unknown;
  } catch {
    return null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function firstLineValue(output: string | null, pattern: RegExp): string | null {
  return output?.match(pattern)?.[1]?.trim() ?? null;
}

async function commandOutput(command: string, args: string[]): Promise<string | null> {
  try {
    const { stdout, stderr } = await execFileAsync(command, args, { timeout: 15_000, windowsHide: true });
    return `${stdout}\n${stderr}`;
  } catch {
    return null;
  }
}

/** true on exit 0, false on a non-zero exit, null when the command cannot be started. */
async function commandSucceeds(command: string, args: string[], cwd: string): Promise<boolean | null> {
  try {
    await execFileAsync(command, args, { cwd, timeout: 60_000, windowsHide: true });
    return true;
  } catch (error) {
    return typeof (error as { code?: unknown }).code === "number" ? false : null;
  }
}

async function gitOutput(cwd: string, args: string[]): Promise<string | null> {
  try {
    const { stdout } = await execFileAsync("git", args, { cwd, windowsHide: true });
    return stdout.trim();
  } catch {
    return null;
  }
}
