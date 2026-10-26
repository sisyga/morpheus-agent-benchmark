import path from "node:path";
import process from "node:process";

import { BENCHMARK_MODE_DEFINITIONS } from "./modes.js";
import { resolveBenchmarkPythonExecutable } from "./python-env.js";
import type {
  BenchmarkConfig,
  BenchmarkModeId,
} from "./types.js";
import { buildMorpheusThreadEnv } from "./workspace.js";

const BENCHMARK_DISABLED_SYSTEM_SKILL_NAMES = [
  "imagegen",
  "openai-docs",
  "plugin-creator",
  "skill-creator",
  "skill-installer",
] as const;

export function buildMorpheusMcpServerConfig(
  config: Pick<
    BenchmarkConfig,
    "mcpCommand" | "resultsDir" | "mcpToolTimeoutMs" | "morpheusRunTimeoutMs" | "morpheusXmlSchemaPath"
  > &
    Partial<Pick<BenchmarkConfig, "morpheusNumThreads">>,
  activeRunId?: string,
  agentWorkspaceDir?: string,
  benchmarkDeadlinePath?: string,
  realMorpheusBin?: string,
) {
  const mcpWorkspaceRoot = agentWorkspaceDir ? path.resolve(agentWorkspaceDir) : null;
  const mcpRunsDir = mcpWorkspaceRoot ? path.dirname(mcpWorkspaceRoot) : config.resultsDir;
  const mcpActiveRunId = mcpWorkspaceRoot ? path.basename(mcpWorkspaceRoot) : activeRunId;

  return {
    command: resolveMcpCommand(config.mcpCommand[0]),
    args: config.mcpCommand.slice(1).map(resolveMcpCommandArg),
    default_tools_approval_mode: "approve" as const,
    tool_timeout_sec: millisecondsToSeconds(config.mcpToolTimeoutMs),
    env: {
      MORPHEUS_RUNS_DIR: mcpRunsDir,
      ...(mcpActiveRunId ? { MORPHEUS_ACTIVE_RUN_ID: mcpActiveRunId } : {}),
      MORPHEUS_RUN_TIMEOUT_MS: String(config.morpheusRunTimeoutMs),
      ...(realMorpheusBin ? { MORPHEUS_BIN: realMorpheusBin } : {}),
      ...(benchmarkDeadlinePath
        ? { BENCHMARK_DEADLINE_PATH: path.resolve(benchmarkDeadlinePath) }
        : {}),
      MORPHEUS_XML_SCHEMA_PATH: path.resolve(process.cwd(), config.morpheusXmlSchemaPath),
      ...buildMorpheusThreadEnv(config.morpheusNumThreads ?? null),
    },
  };
}

export function buildCodexConfig(
  config: Pick<
    BenchmarkConfig,
    | "mcpCommand"
    | "resultsDir"
    | "mcpToolTimeoutMs"
    | "morpheusRunTimeoutMs"
    | "morpheusNumThreads"
    | "morpheusXmlSchemaPath"
    | "skillPaths"
  >,
  mode: BenchmarkModeId,
  activeRunId?: string,
  agentWorkspaceDir?: string,
  codexHomeDir?: string,
  benchmarkDeadlinePath?: string,
  realMorpheusBin?: string,
) {
  const modeDefinition = BENCHMARK_MODE_DEFINITIONS[mode];
  const codexConfig: Record<string, any> = {
    windows: {
      sandbox: "elevated",
    },
  };

  if (modeDefinition.capabilities.morpheusMcp) {
    codexConfig.mcp_servers = {
      morpheus: buildMorpheusMcpServerConfig(
        config,
        activeRunId,
        agentWorkspaceDir,
        benchmarkDeadlinePath,
        realMorpheusBin,
      ),
    };
  }

  codexConfig.skills = {
    config: buildBenchmarkSkillConfigEntries(
      modeDefinition.capabilities.morpheusSkill ? config.skillPaths : [],
      codexHomeDir,
    ),
  };

  return codexConfig;
}

export function buildBenchmarkSkillConfigEntries(
  skillPaths: readonly string[],
  codexHomeDir?: string,
): Array<{ path: string; enabled: boolean }> {
  return [
    ...buildDisabledSystemSkillConfigEntries(codexHomeDir),
    ...skillPaths.map((skillPath) => ({
      path: buildStagedBenchmarkSkillPath(skillPath, codexHomeDir),
      enabled: true,
    })),
  ];
}

function buildDisabledSystemSkillConfigEntries(codexHomeDir?: string): Array<{ path: string; enabled: false }> {
  if (!codexHomeDir) {
    return [];
  }
  return BENCHMARK_DISABLED_SYSTEM_SKILL_NAMES.map((skillName) => ({
    path: path.join(codexHomeDir, "skills", ".system", skillName, "SKILL.md"),
    enabled: false,
  }));
}

function buildStagedBenchmarkSkillPath(skillPath: string, codexHomeDir?: string): string {
  if (!codexHomeDir) {
    return skillPath;
  }
  return path.join(codexHomeDir, "skills", path.basename(path.dirname(skillPath)), "SKILL.md");
}

function millisecondsToSeconds(milliseconds: number): number {
  return Math.max(1, Math.ceil(nonNegativeNumber(milliseconds) / 1000));
}

function resolveMcpCommandArg(arg: string): string {
  if (path.isAbsolute(arg) || arg.startsWith("-")) {
    return arg;
  }
  if (arg.includes("/") || arg.includes("\\") || arg.toLowerCase().endsWith(".py")) {
    return path.resolve(process.cwd(), arg);
  }
  return arg;
}

function resolveMcpCommand(command: string): string {
  return /^python(?:3|\.exe)?$/i.test(command) ? resolveBenchmarkPythonExecutable() : command;
}

function nonNegativeNumber(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}
