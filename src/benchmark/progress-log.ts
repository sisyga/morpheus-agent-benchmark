import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import path from "node:path";

export function appendProgressLog(logPath: string, message: string): void {
  mkdirSync(path.dirname(logPath), { recursive: true });
  appendFileSync(logPath, `${message}\n`, "utf8");
}

export function appendProgressLogIfParentExists(logPath: string, message: string): void {
  if (!existsSync(path.dirname(logPath))) {
    return;
  }
  appendProgressLog(logPath, message);
}
