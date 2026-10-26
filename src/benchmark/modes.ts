import type { BenchmarkModeCapabilities, BenchmarkModeId } from "./types.js";

export type BenchmarkModeDefinition = {
  id: BenchmarkModeId;
  label: string;
  description: string;
  capabilities: BenchmarkModeCapabilities;
};

export const ALL_BENCHMARK_MODES: BenchmarkModeId[] = [
  "python_web",
  "morpheus_cli",
  "morpheus_cli_docs",
  "morpheus_skill",
  "morpheus_mcp",
];

export const BENCHMARK_MODE_DEFINITIONS: Record<BenchmarkModeId, BenchmarkModeDefinition> = {
  python_web: {
    id: "python_web",
    label: "Python + web search",
    description: "Web search and Python only; the agent writes MorpheusML but cannot run Morpheus.",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: false,
      morpheusSkill: false,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: false,
    },
  },
  morpheus_cli: {
    id: "morpheus_cli",
    label: "Morpheus CLI",
    description: "Web search, Python, and Morpheus CLI; no Morpheus skill or MCP tools.",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: true,
      morpheusSkill: false,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
  },
  morpheus_cli_docs: {
    id: "morpheus_cli_docs",
    label: "Morpheus CLI + basic docs",
    description:
      "No internet, no Morpheus skill, no example repository; the agent uses Morpheus CLI plus staged MorpheusML docs and a model template.",
    capabilities: {
      webSearch: false,
      python: true,
      morpheusCli: true,
      morpheusSkill: false,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
  },
  morpheus_skill: {
    id: "morpheus_skill",
    label: "Morpheus skill + CLI",
    description: "Web search, Python, Morpheus CLI, and the Morpheus skill; no MCP tools.",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: true,
      morpheusSkill: true,
      morpheusMcp: false,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
  },
  morpheus_mcp: {
    id: "morpheus_mcp",
    label: "Full Morpheus MCP harness",
    description: "Web search, Python, Morpheus CLI, Morpheus skill, and Morpheus MCP tools.",
    capabilities: {
      webSearch: true,
      python: true,
      morpheusCli: true,
      morpheusSkill: true,
      morpheusMcp: true,
      hostTechnicalEvaluation: true,
      inAgentMorpheusDebugging: true,
    },
  },
};

export function isBenchmarkModeId(value: string): value is BenchmarkModeId {
  return (ALL_BENCHMARK_MODES as string[]).includes(value);
}

export function parseBenchmarkModeId(value: string): BenchmarkModeId {
  if (!isBenchmarkModeId(value)) {
    throw new Error(`Unknown benchmark mode: ${value}`);
  }
  return value;
}

export function normalizeBenchmarkModes(values: readonly string[] | undefined): BenchmarkModeId[] {
  const modes = values && values.length > 0 ? values : ["morpheus_mcp"];
  return [...new Set(modes.map(parseBenchmarkModeId))];
}
