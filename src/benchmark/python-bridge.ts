import { spawn } from "node:child_process";
import path from "node:path";
import process from "node:process";

import { buildBenchmarkPythonEnv, resolveBenchmarkPythonExecutable } from "./python-env.js";
import type { ToolResult } from "./types.js";

/* node:coverage disable */
export type PythonBridgeProcessTreeCleanupPlan =
  | {
      kind: "taskkill";
      command: "taskkill.exe";
      args: string[];
    }
  | {
      kind: "process-group";
      pid: number;
      signal: NodeJS.Signals;
    };

type PythonToolName =
  | "create_run"
  | "extract_paper_text"
  | "read_pdf"
  | "render_pdf_pages"
  | "list_paper_visuals"
  | "list_paper_figures"
  | "list_references"
  | "read_reference"
  | "read_file_text"
  | "validate_model_xml"
  | "write_model_xml"
  | "capture_model_xml_version"
  | "run_morpheus_model"
  | "summarize_morpheus_run"
  | "sample_output_images"
  | "evaluate_technical_run";

export class PythonBridge {
  private readonly pythonExecutable: string;
  private readonly cliPath: string;
  private readonly timeoutMs: number;

  constructor(options: { timeoutMs?: number } = {}) {
    this.pythonExecutable = resolveBenchmarkPythonExecutable();
    this.cliPath = path.resolve(process.cwd(), "morpheus_tools_cli.py");
    this.timeoutMs = options.timeoutMs ?? 3_600_000;
  }

  invoke<T extends Record<string, unknown>>(command: PythonToolName, payload: Record<string, unknown>): Promise<ToolResult<T>> {
    return new Promise((resolve, reject) => {
      const child = spawn(this.pythonExecutable, [this.cliPath, command], {
        cwd: process.cwd(),
        stdio: ["pipe", "pipe", "pipe"],
        env: buildBenchmarkPythonEnv(process.env),
        ...buildPythonBridgeSpawnOptions(),
      });

      let stdout = "";
      let stderr = "";
      let timedOut = false;
      let settled = false;
      let forceKillTimeout: ReturnType<typeof setTimeout> | null = null;
      const timeout = setTimeout(() => {
        timedOut = true;
        terminatePythonBridgeProcessTree(child, "SIGTERM");
        forceKillTimeout = setTimeout(() => {
          terminatePythonBridgeProcessTree(child, "SIGKILL");
        }, 5_000);
        forceKillTimeout.unref?.();
      }, this.timeoutMs);

      const settleReject = (error: Error) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timeout);
        if (forceKillTimeout) {
          clearTimeout(forceKillTimeout);
        }
        reject(error);
      };

      const settleResolve = (value: ToolResult<T>) => {
        if (settled) {
          return;
        }
        settled = true;
        clearTimeout(timeout);
        if (forceKillTimeout) {
          clearTimeout(forceKillTimeout);
        }
        resolve(value);
      };

      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", (chunk) => {
        stdout += chunk;
      });
      child.stderr.on("data", (chunk) => {
        stderr += chunk;
      });

      child.on("error", (error) => {
        if (timedOut) {
          settleResolve({
            ok: false,
            error: `Python tool ${command} timed out after ${this.timeoutMs}ms.`,
            timed_out: true,
          } as unknown as ToolResult<T>);
          return;
        }
        settleReject(error);
      });
      child.on("close", (code) => {
        clearTimeout(timeout);
        if (timedOut) {
          settleResolve({
            ok: false,
            error: `Python tool ${command} timed out after ${this.timeoutMs}ms.`,
            timed_out: true,
            stdout,
            stderr,
          } as unknown as ToolResult<T>);
          return;
        }
        const cleaned = stdout.trim();
        if (!cleaned) {
          settleReject(new Error(`Python tool ${command} returned no JSON. stderr: ${stderr}`));
          return;
        }
        try {
          const parsed = JSON.parse(cleaned) as ToolResult<T>;
          if (!parsed.ok && !parsed.error && stderr.trim()) {
            parsed.error = stderr.trim();
          }
          if (code !== 0 && parsed.ok) {
            parsed.ok = false;
            parsed.error = parsed.error ?? stderr.trim() ?? `Python tool ${command} failed`;
          }
          settleResolve(parsed);
        } catch (error) {
          settleReject(
            new Error(
              `Failed to parse Python tool output for ${command}: ${(error as Error).message}\nstdout: ${stdout}\nstderr: ${stderr}`,
            ),
          );
        }
      });

      child.stdin.on("error", (error: NodeJS.ErrnoException) => {
        if (!timedOut && error.code !== "EPIPE") {
          settleReject(error);
        }
      });
      child.stdin.write(JSON.stringify(payload));
      child.stdin.end();
    });
  }
}
/* node:coverage enable */

export function buildPythonBridgeSpawnOptions(
  platform: NodeJS.Platform = process.platform,
): { detached: boolean } {
  return { detached: platform !== "win32" };
}

export function buildPythonBridgeProcessTreeCleanupPlan(
  pid: number,
  platform: NodeJS.Platform = process.platform,
  signal: NodeJS.Signals = "SIGTERM",
): PythonBridgeProcessTreeCleanupPlan {
  if (platform === "win32") {
    return {
      kind: "taskkill",
      command: "taskkill.exe",
      args: ["/F", "/T", "/PID", String(pid)],
    };
  }
  return {
    kind: "process-group",
    pid: -pid,
    signal,
  };
}

function terminatePythonBridgeProcessTree(
  child: ReturnType<typeof spawn>,
  signal: NodeJS.Signals,
): void {
  const killDirectChild = (): void => {
    try {
      child.kill(signal);
    } catch {
      // Best effort cleanup; the process may already have exited.
    }
  };
  if (child.pid === undefined) {
    killDirectChild();
    return;
  }

  const plan = buildPythonBridgeProcessTreeCleanupPlan(child.pid, process.platform, signal);
  if (plan.kind === "taskkill") {
    try {
      const cleanup = spawn(plan.command, plan.args, {
        stdio: "ignore",
        windowsHide: true,
      });
      cleanup.once("error", killDirectChild);
      cleanup.unref();
    } catch {
      killDirectChild();
    }
    return;
  }

  try {
    process.kill(plan.pid, plan.signal);
  } catch {
    killDirectChild();
  }
}
