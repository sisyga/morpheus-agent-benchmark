import { readFile, readdir } from "node:fs/promises";
import path from "node:path";

export async function loadPaperFocus(
  focusDir: string | null | undefined,
  pdfPath: string,
): Promise<string | null> {
  if (!focusDir) {
    return null;
  }

  const focusPath = path.join(focusDir, `${path.basename(pdfPath, path.extname(pdfPath))}.txt`);
  try {
    const focus = (await readFile(focusPath, "utf8")).trim();
    return focus.length > 0 ? focus : null;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return loadPaperFocusByNormalizedStem(focusDir, pdfPath);
    }
    throw error;
  }
}

async function loadPaperFocusByNormalizedStem(focusDir: string, pdfPath: string): Promise<string | null> {
  const target = normalizedFocusStem(path.basename(pdfPath, path.extname(pdfPath)));
  if (!target) {
    return null;
  }
  let entries;
  /* node:coverage disable */
  try {
    entries = await readdir(focusDir, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return null;
    }
    throw error;
  }
  /* node:coverage enable */

  const match = entries
    .filter((entry) => entry.isFile() && entry.name.toLowerCase().endsWith(".txt"))
    .map((entry) => entry.name)
    .find((name) => normalizedFocusStem(path.basename(name, path.extname(name))).includes(target));
  if (!match) {
    return null;
  }
  const focus = (await readFile(path.join(focusDir, match), "utf8")).trim();
  return focus.length > 0 ? focus : null;
}

function normalizedFocusStem(value: string): string {
  return value
    .replace(/_(?:clean|short)$/i, "")
    .replace(/^\d+_/, "")
    .replace(/^ten_/i, "")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/_+/g, "_")
    .toLowerCase();
}
