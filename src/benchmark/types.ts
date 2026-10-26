export type ReasoningEffort = "none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max";
export const BENCHMARK_ARTIFACT_SCHEMA_VERSION = 2 as const;
export const BENCHMARK_PROTOCOL = "time_limit_v2" as const;
// Bump when the subject-facing setup changes (skill, docs-mode references, prompts, runner behavior), then tag the
// release commit as benchmark-v<N>. Runs from different versions are never recovered or combined together.
export const BENCHMARK_VERSION = 3 as const;
export type CodexApprovalPolicy = "never" | "on-request" | "on-failure" | "untrusted";
export type CodexWindowsSandboxMode = "elevated" | "unelevated";
export type BenchmarkModeId =
  | "python_web"
  | "morpheus_cli"
  | "morpheus_cli_docs"
  | "morpheus_skill"
  | "morpheus_mcp";

export type BenchmarkModeCapabilities = {
  webSearch: boolean;
  python: boolean;
  morpheusCli: boolean;
  morpheusSkill: boolean;
  morpheusMcp: boolean;
  hostTechnicalEvaluation: boolean;
  inAgentMorpheusDebugging: boolean;
};

export type BenchmarkConfig = {
  papersDir: string;
  resultsDir: string;
  benchmarkFocusDir: string | null;
  benchmarkModes: BenchmarkModeId[];
  benchmarkRepetitions: number;
  model: string;
  reasoningEffort: ReasoningEffort;
  totalTimeLimitMs: number;
  finalizationReserveMs: number;
  maxConcurrentJobs: number;
  /** Assumed weekly Codex quota share per job before it is measured; 0 disables the quota guard. */
  codexQuotaJobCostPercent: number;
  pageRenderDpi: number;
  representativeOutputFrames: number;
  codexApprovalPolicy: CodexApprovalPolicy;
  codexAllowedEnvVars: string[];
  biologicalScoringCriteriaPath: string;
  biologicalScoringModel: string;
  biologicalScoringReasoningEffort: ReasoningEffort;
  biologicalScoringMaxConcurrentJobs: number;
  biologicalScoringTurnTimeoutMs: number;
  mcpCommand: string[];
  mcpToolTimeoutMs: number;
  bridgeToolTimeoutMs: number;
  morpheusRunTimeoutMs: number;
  morpheusNumThreads: number | null;
  morpheusXmlSchemaPath: string;
  skillPaths: string[];
};

export type ToolResult<T = Record<string, unknown>> = T & {
  ok: boolean;
  error?: string;
};

export type ReproductionCriterion = {
  score: 0 | 1 | 2;
  evidence: string[];
  rationale: string;
};

export type ReproductionReport = {
  source_coverage: ReproductionCriterion;
  mechanism_mapping: ReproductionCriterion;
  observable_alignment: ReproductionCriterion;
  parameter_plausibility: ReproductionCriterion;
  total_score: number;
  summary: string;
};

export type AgentRunResponse = {
  runId: string;
  agentReportedStatus: "completed" | "best_effort";
  summary: string;
  reproduction: ReproductionReport | null;
};

export type V2StopReason = "agent_finished" | "time_limit" | "infrastructure_failure";
export type V2ArtifactStatus = "scoreable" | "unscoreable" | "missing";

export type PaperRunResult = {
  paper: string;
  pdfPath: string;
  mode: BenchmarkModeId;
  modeLabel: string;
  capabilities: BenchmarkModeCapabilities;
  capabilityViolations: string[];
  runId: string;
  threadId: string | null;
  repetition: number;
  startedAt: string | null;
  finishedAt: string | null;
  durationMs: number;
  diagnostics: BenchmarkDiagnostics;
  attempts: number;
  attemptArtifactAudit?: AttemptArtifactAudit;
  modelRefinementCount: number;
  technicalScore: number | null;
  reproductionScore: number | null;
  biologicalScore?: number | null;
  technicalEvaluationPath: string | null;
  reproductionReportPath: string | null;
  reproductionReportTextPath: string | null;
  biologicalScorePath?: string | null;
  biologicalScoringStatus?: string | null;
  runManifestPath: string | null;
  benchmarkFocus: string | null;
  summary: string;
  error?: string;
  artifactSchemaVersion?: 2;
  benchmarkProtocol?: "time_limit_v2";
  assignmentId?: string;
  executionId?: string;
  model?: string;
  reasoningEffort?: ReasoningEffort;
  replacementFor?: string | null;
  replacementCount?: 0 | 1;
  stopReason?: V2StopReason;
  artifactStatus?: V2ArtifactStatus;
  workspaceDir?: string;
  codexHomeDir?: string;
  totalTimeLimitMs?: number;
  finalizationReserveMs?: number;
  subjectStartedAt?: string | null;
  subjectFinishedAt?: string | null;
  softCutoffAt?: string | null;
  hardCutoffAt?: string | null;
  subjectExecutionMs?: number;
  morpheusSimulationMs?: number;
  totalJobMs?: number;
  budgetFraction?: number;
  replacementEligible?: boolean;
  selectedExecutionId?: string;
  sourceBenchmarkRunDir?: string;
  sourceRepetition?: number;
  executions?: Array<{
    executionId: string;
    runId: string;
    replacementFor: string | null;
    replacementCount: 0 | 1;
    stopReason: V2StopReason;
    workspaceDir: string;
    codexHomeDir: string;
    model: string;
    reasoningEffort: ReasoningEffort;
    totalTimeLimitMs: number;
    finalizationReserveMs: number;
    subjectExecutionMs: number;
    morpheusSimulationMs: number;
    totalJobMs: number;
    artifactStatus: V2ArtifactStatus;
    startedAt: string | null;
    finishedAt: string | null;
    error: string | null;
  }>;
};

export type BenchmarkNumericStats = {
  count: number;
  mean: number;
  stdDev: number;
  min: number;
  max: number;
  sum: number;
};

export type PaperModeStatistics = {
  paper: string;
  pdfPath: string;
  mode: BenchmarkModeId;
  modeLabel: string;
  expectedRepetitions: number;
  observedRepetitions: number;
  repetitions: number[];
  runIds: string[];
  agentFinishedRuns: number;
  timeLimitRuns: number;
  infrastructureFailureRuns: number;
  totalExecutions: number;
  infrastructureFailureExecutions: number;
  scoreableRuns: number;
  replacementRuns: number;
  metrics: Record<string, BenchmarkNumericStats>;
};

export type BenchmarkTokenDiagnostics = {
  input: number;
  cachedInput: number;
  cacheWriteInput: number;
  output: number;
  reasoningOutput: number;
  total: number;
};

export type BenchmarkDiagnostics = {
  turnCount: number;
  attemptCount: number;
  agentWallTimeMs: number;
  morpheusSimulationTimeMs: number;
  agentAnalysisTimeMs: number;
  hostMorpheusRunTimeMs: number;
  hostTechnicalEvaluationTimeMs: number;
  tokens: BenchmarkTokenDiagnostics;
};

export type AttemptArtifactAudit = {
  executedAttempts: number;
  missingModelXml: number;
  missingReproductionReport: number;
  missingLogs: number;
};

export type BenchmarkProvenance = {
  benchmarkVersion: number;
  gitCommit: string | null;
  gitTag: string | null;
  gitDirty: boolean | null;
  skills: Array<{ name: string; sha256: string | null }>;
  docsReferences: {
    morpheusMlDocSha256: string | null;
    modelTemplateSha256: string | null;
  };
  // Subject-facing text: prompt builder source, MCP server (instructions and tool descriptions), and focus prompts.
  prompts: {
    subjectPromptSourceSha256: string | null;
    mcpServerSha256: string | null;
    focusSha256: string | null;
  };
  software: BenchmarkSoftware;
};

export type BenchmarkSoftware = {
  node: string;
  platform: string;
  codexSdk: string | null;
  codexSdkLocked: string | null;
  codexCli: string | null;
  morpheus: string | null;
  morpheusRevision: string | null;
  gnuplot: string | null;
  python: string | null;
  packageLockSha256: string | null;
  uvLockSha256: string | null;
  // Whether node_modules and .venv contain exactly the locked packages; null when it cannot be checked.
  npmInstalledMatchesLock: boolean | null;
  pythonInstalledMatchesLock: boolean | null;
};

export type BenchmarkSummary = {
  artifactSchemaVersion?: 2;
  benchmarkProtocol?: "time_limit_v2";
  benchmarkVersion?: number;
  benchmarkProvenance?: BenchmarkProvenance;
  biologicalScorerVersion?: number;
  config: BenchmarkConfig;
  benchmarkId: string;
  benchmarkRunDir: string;
  comparisonJsonPath: string;
  comparisonCsvPath: string;
  startedAt: string;
  finishedAt: string;
  generatedAt: string;
  durationMs: number;
  diagnostics: BenchmarkDiagnostics;
  totalRuns: number;
  uniquePapers: number;
  benchmarkRepetitions: number;
  totalPapers: number;
  agentFinishedRuns: number;
  timeLimitRuns: number;
  infrastructureFailureRuns: number;
  scoreableRuns: number;
  replacementRuns: number;
  totalModelRefinements: number;
  averageModelRefinements: number;
  averageTechnicalScore: number;
  averageTechnicalScoreValidOnly?: number;
  averageTechnicalScoreItt?: number;
  averageReproductionScore: number;
  averageReproductionScoreValidOnly?: number;
  averageReproductionScoreItt?: number;
  averageBiologicalScore?: number | null;
  averageBiologicalScoreValidOnly?: number | null;
  averageBiologicalScoreItt?: number | null;
  paperModeStatistics: PaperModeStatistics[];
  results: PaperRunResult[];
};
