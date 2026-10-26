/* node:coverage disable */
import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { loadPaperFocus } from "../src/benchmark/focus.js";

test("loadPaperFocus reads focus text matching the PDF stem", async () => {
  const focus = await loadPaperFocus(
    path.resolve("benchmark_focus"),
    path.resolve("benchmark_papers/10_Berkhout2025.pdf"),
  );

  assert.match(focus ?? "", /WT Fig\.1 and Fig\.2/);
  assert.match(focus ?? "", /single csv file for 100 time points/i);
  assert.match(focus ?? "", /right half of space/i);
});

test("loadPaperFocus treats missing focus files as optional", async () => {
  const focus = await loadPaperFocus(path.resolve("benchmark_focus"), "benchmark_papers/missing.pdf");
  assert.equal(focus, null);
});

test("loadPaperFocus treats disabled and missing focus dirs as optional", async () => {
  assert.equal(await loadPaperFocus(null, "benchmark_papers/01_Szabo2010.pdf"), null);
  assert.equal(await loadPaperFocus(undefined, "benchmark_papers/01_Szabo2010.pdf"), null);
  assert.equal(await loadPaperFocus(path.join(os.tmpdir(), "missing-morpheus-focus-dir"), "01_Szabo2010.pdf"), null);
});

test("loadPaperFocus falls back to normalized stem matches", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-focus-"));
  await writeFile(path.join(root, "ten_Berkhout2025_clean.txt"), " normalized focus \n", "utf8");

  const focus = await loadPaperFocus(root, path.join(root, "10_Berkhout2025.pdf"));

  assert.equal(focus, "normalized focus");
});

test("loadPaperFocus returns null for empty normalized targets and empty matched files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-focus-"));
  await mkdir(path.join(root, "nested"));
  await writeFile(path.join(root, "Szabo2010.txt"), " \n", "utf8");

  assert.equal(await loadPaperFocus(root, "!!!.pdf"), null);
  assert.equal(await loadPaperFocus(root, "01_Szabo2010_clean.pdf"), null);
});

test("loadPaperFocus returns null for an empty exact-stem focus file", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-focus-"));
  await writeFile(path.join(root, "01_Szabo2010.txt"), " \n", "utf8");

  assert.equal(await loadPaperFocus(root, path.join(root, "01_Szabo2010.pdf")), null);
});

test("loadPaperFocus rethrows non-missing filesystem errors", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "morpheus-focus-"));
  const filePath = path.join(root, "not-a-directory");
  await writeFile(filePath, "focus", "utf8");

  await assert.rejects(
    () => loadPaperFocus(filePath, "missing.pdf"),
    /ENOTDIR/,
  );
});

test("loadPaperFocus reads focus text for new biological benchmark papers by exact PDF stem", async () => {
  // Pin the stem match, not the prompt wording, which is revised independently of the loader.
  const cases = [
    ["benchmark_papers/15_Reza2025.pdf", "Aggregation and growth of two adjacent hepatocyte clusters"],
    ["benchmark_papers/13_Mole2026.pdf", "Blastocyst as a cell cluster"],
    ["benchmark_papers/11_Anlas2024.pdf", "Cell cluster as in Fig.1A and Fig.4A"],
    ["benchmark_papers/14_Otsuki2025.pdf", "As shown in Fig.5f"],
    ["benchmark_papers/12_Malkmus2025.pdf", "A circular 2D domain"],
  ] as const;

  for (const [pdfPath, anchor] of cases) {
    const focus = await loadPaperFocus(path.resolve("benchmark_focus"), path.resolve(pdfPath));
    const focusFile = path.resolve("benchmark_focus", `${path.basename(pdfPath, ".pdf")}.txt`);
    assert.equal(focus, (await readFile(focusFile, "utf8")).trim(), pdfPath);
    assert.ok(focus?.startsWith(anchor), pdfPath);
  }
});
