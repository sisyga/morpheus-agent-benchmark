/* node:coverage disable */
import { strict as assert } from "node:assert";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

import { PaperArtifactCache } from "../src/benchmark/paper-artifacts.js";
import type { ToolResult } from "../src/benchmark/types.js";

test("paper artifacts are generated once per paper and copied to later runs", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-paper-cache-"));
  const pdfPath = path.join(root, "ExamplePaper.pdf");
  const run1 = path.join(root, "run-1");
  const run2 = path.join(root, "run-2");
  await mkdir(run1);
  await mkdir(run2);
  await writeFile(pdfPath, "%PDF-1.4\n");

  const runDirs = new Map([
    ["run-1", run1],
    ["run-2", run2],
  ]);
  const calls = { extract: 0, visuals: 0 };

  const bridge = {
    async invoke<T extends Record<string, unknown>>(
      command: "extract_paper_text" | "list_paper_visuals",
      payload: Record<string, unknown>,
    ): Promise<ToolResult<T>> {
      const runId = String(payload.run_id);
      const runDir = runDirs.get(runId);
      assert.ok(runDir, `unexpected run_id ${runId}`);

      if (command === "extract_paper_text") {
        calls.extract += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        const textPath = path.join(runDir, "paper.txt");
        await writeFile(textPath, "cached paper text");
        return {
          ok: true,
          run_id: runId,
          run_dir: runDir,
          text_path: textPath,
        } as unknown as ToolResult<T>;
      }

      if (command === "list_paper_visuals") {
        calls.visuals += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        const manifestPath = path.join(runDir, "paper_visual_manifest.json");
        await writeFile(manifestPath, JSON.stringify({ items: [{ page: 2, kind: "figure" }] }));
        return {
          ok: true,
          run_id: runId,
          run_dir: runDir,
          manifest_path: "paper_visual_manifest.json",
          visual_pages: [2, 4],
          figure_pages: [2],
          table_pages: [4],
          warnings: [],
        } as unknown as ToolResult<T>;
      }

      throw new Error(`unexpected command ${command}`);
    },
  };

  const cache = new PaperArtifactCache(bridge);
  const [first, second] = await Promise.all([
    cache.prepareForRun({ benchmarkRunDir: root, pdfPath, runId: "run-1", runDir: run1 }),
    cache.prepareForRun({ benchmarkRunDir: root, pdfPath, runId: "run-2", runDir: run2 }),
  ]);

  assert.equal(calls.extract, 1);
  assert.equal(calls.visuals, 1);
  assert.equal(first.extract.text_path, path.join(run1, "paper.txt"));
  assert.equal(second.extract.text_path, path.join(run2, "paper.txt"));
  assert.equal(second.visualManifest.manifest_path, path.join(run2, "paper_visual_manifest.json"));
  assert.deepEqual(second.visualManifest.visual_pages, [2, 4]);
  assert.equal(await readFile(path.join(run2, "paper.txt"), "utf8"), "cached paper text");
  assert.equal(
    await readFile(path.join(run2, "paper_visual_manifest.json"), "utf8"),
    JSON.stringify({ items: [{ page: 2, kind: "figure" }] }),
  );
});

test("paper artifact cache returns failed visual manifest when extraction fails", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-paper-cache-"));
  const runDir = path.join(root, "run-1");
  await mkdir(runDir);
  const calls: string[] = [];
  const cache = new PaperArtifactCache({
    async invoke<T extends Record<string, unknown>>(
      command: "extract_paper_text" | "list_paper_visuals",
    ): Promise<ToolResult<T>> {
      calls.push(command);
      return { ok: false, error: "extract failed" } as unknown as ToolResult<T>;
    },
  });

  const result = await cache.prepareForRun({
    benchmarkRunDir: root,
    pdfPath: path.join(root, "paper.pdf"),
    runId: "run-1",
    runDir,
  });

  assert.deepEqual(calls, ["extract_paper_text"]);
  assert.equal(result.extract.ok, false);
  assert.equal(result.visualManifest.ok, false);
  assert.equal(result.visualManifest.error, "Paper text extraction failed.");
  assert.deepEqual(result.visualManifest.visual_pages, []);
});

test("paper artifact cache retries failed generations", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-paper-cache-"));
  const runDir = path.join(root, "run-1");
  await mkdir(runDir);
  let extractCalls = 0;
  let visualCalls = 0;
  const cache = new PaperArtifactCache({
    async invoke<T extends Record<string, unknown>>(
      command: "extract_paper_text" | "list_paper_visuals",
      payload: Record<string, unknown>,
    ): Promise<ToolResult<T>> {
      if (command === "extract_paper_text") {
        extractCalls += 1;
        const textPath = path.join(runDir, `paper-${extractCalls}.txt`);
        await writeFile(textPath, "paper");
        return { ok: true, run_id: payload.run_id, run_dir: runDir, text_path: textPath } as unknown as ToolResult<T>;
      }
      visualCalls += 1;
      if (visualCalls === 1) {
        return { ok: false, error: "visual failure" } as unknown as ToolResult<T>;
      }
      const manifestPath = path.join(runDir, "paper_visual_manifest.json");
      await writeFile(manifestPath, "{}");
      return {
        ok: true,
        run_id: payload.run_id,
        run_dir: runDir,
        figure_pages: [],
        table_pages: [],
        visual_pages: [],
        manifest_path: manifestPath,
      } as unknown as ToolResult<T>;
    },
  });

  const first = await cache.prepareForRun({
    benchmarkRunDir: root,
    pdfPath: path.join(root, "paper.pdf"),
    runId: "run-1",
    runDir,
  });
  const second = await cache.prepareForRun({
    benchmarkRunDir: root,
    pdfPath: path.join(root, "paper.pdf"),
    runId: "run-1",
    runDir,
  });

  assert.equal(first.visualManifest.ok, false);
  assert.equal(second.visualManifest.ok, true);
  assert.equal(extractCalls, 2);
  assert.equal(visualCalls, 2);
});
