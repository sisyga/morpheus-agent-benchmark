import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";

import type { ToolResult } from "./types.js";

/* node:coverage disable */
type PaperArtifactCommand = "extract_paper_text" | "list_paper_visuals";

export type PaperArtifactBridge = {
  invoke<T extends Record<string, unknown>>(
    command: PaperArtifactCommand,
    payload: Record<string, unknown>,
  ): Promise<ToolResult<T>>;
};

type ExtractPaperPayload = {
  run_id: string;
  run_dir: string;
  text_path: string;
};

type VisualManifestPayload = {
  run_id?: string;
  run_dir?: string;
  figure_pages: number[];
  table_pages: number[];
  visual_pages: number[];
  manifest_path: string;
  warnings?: string[];
  [key: string]: unknown;
};

export type ExtractPaperResult = ToolResult<ExtractPaperPayload>;
export type VisualManifestResult = ToolResult<VisualManifestPayload>;

export type PreparedPaperArtifacts = {
  extract: ExtractPaperResult;
  visualManifest: VisualManifestResult;
};

type PreparePaperArtifactsParams = {
  benchmarkRunDir: string;
  pdfPath: string;
  runId: string;
  runDir: string;
};

type CachedPaperArtifacts = PreparedPaperArtifacts & {
  sourceTextPath: string;
  sourceVisualManifestPath: string;
};
/* node:coverage enable */

export class PaperArtifactCache {
  private readonly entries = new Map<string, Promise<PreparedPaperArtifacts>>();

  constructor(private readonly bridge: PaperArtifactBridge) {}

  async prepareForRun(params: PreparePaperArtifactsParams): Promise<PreparedPaperArtifacts> {
    const key = paperArtifactCacheKey(params.benchmarkRunDir, params.pdfPath);
    let entry = this.entries.get(key);
    if (!entry) {
      entry = this.generateForRun(params).catch((error) => {
        this.entries.delete(key);
        throw error;
      });
      this.entries.set(key, entry);
    }

    const source = await entry;
    if (!isReusable(source)) {
      this.entries.delete(key);
      return source;
    }
    return copyCachedArtifactsToRun(source, params);
  }

  private async generateForRun(params: PreparePaperArtifactsParams): Promise<PreparedPaperArtifacts> {
    const extract = await this.bridge.invoke<ExtractPaperPayload>("extract_paper_text", {
      pdf_path: params.pdfPath,
      run_id: params.runId,
    });
    if (!extract.ok) {
      return { extract, visualManifest: failedVisualManifest(params, "Paper text extraction failed.") };
    }

    const visualManifest = await this.bridge.invoke<VisualManifestPayload>("list_paper_visuals", {
      pdf_path: params.pdfPath,
      run_id: params.runId,
    });
    if (!visualManifest.ok) {
      return { extract, visualManifest };
    }

    const sourceTextPath = resolveArtifactPath(params.runDir, extract.text_path);
    const sourceVisualManifestPath = resolveArtifactPath(params.runDir, visualManifest.manifest_path);
    const cached: CachedPaperArtifacts = {
      sourceTextPath,
      sourceVisualManifestPath,
      extract: rebaseExtract(extract, params, sourceTextPath),
      visualManifest: rebaseVisualManifest(visualManifest, params, sourceVisualManifestPath),
    };
    return cached;
  }
}

export function paperArtifactCacheKey(benchmarkRunDir: string, pdfPath: string): string {
  return `${path.resolve(benchmarkRunDir)}:${path.resolve(pdfPath)}`;
}

async function copyCachedArtifactsToRun(
  source: CachedPaperArtifacts,
  params: PreparePaperArtifactsParams,
): Promise<PreparedPaperArtifacts> {
  const targetTextPath = path.join(params.runDir, "paper.txt");
  const targetVisualManifestPath = path.join(params.runDir, "paper_visual_manifest.json");
  await copyIfDifferent(source.sourceTextPath, targetTextPath);
  await copyIfDifferent(source.sourceVisualManifestPath, targetVisualManifestPath);
  return {
    extract: rebaseExtract(source.extract, params, targetTextPath),
    visualManifest: rebaseVisualManifest(source.visualManifest, params, targetVisualManifestPath),
  };
}

async function copyIfDifferent(sourcePath: string, targetPath: string): Promise<void> {
  if (path.resolve(sourcePath) === path.resolve(targetPath)) {
    return;
  }
  await mkdir(path.dirname(targetPath), { recursive: true });
  await copyFile(sourcePath, targetPath);
}

function isReusable(artifacts: PreparedPaperArtifacts): artifacts is CachedPaperArtifacts {
  return (
    artifacts.extract.ok &&
    artifacts.visualManifest.ok &&
    typeof (artifacts as Partial<CachedPaperArtifacts>).sourceTextPath === "string" &&
    typeof (artifacts as Partial<CachedPaperArtifacts>).sourceVisualManifestPath === "string"
  );
}

function failedVisualManifest(params: PreparePaperArtifactsParams, error: string): VisualManifestResult {
  return {
    ok: false,
    run_id: params.runId,
    run_dir: params.runDir,
    figure_pages: [],
    table_pages: [],
    visual_pages: [],
    manifest_path: "",
    error,
  };
}

function rebaseExtract(
  extract: ExtractPaperResult,
  params: PreparePaperArtifactsParams,
  textPath: string,
): ExtractPaperResult {
  return {
    ...extract,
    run_id: params.runId,
    run_dir: params.runDir,
    text_path: textPath,
  };
}

function rebaseVisualManifest(
  visualManifest: VisualManifestResult,
  params: PreparePaperArtifactsParams,
  manifestPath: string,
): VisualManifestResult {
  return {
    ...visualManifest,
    run_id: params.runId,
    run_dir: params.runDir,
    manifest_path: manifestPath,
  };
}

function resolveArtifactPath(runDir: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(runDir, value);
}
