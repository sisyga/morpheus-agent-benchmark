import { existsSync, readdirSync, readFileSync, realpathSync } from "node:fs";
import path from "node:path";
import process from "node:process";

type EnvInput = NodeJS.ProcessEnv | Record<string, string | undefined>;

type PythonEnvOptions = {
  cwd?: string;
  pathExists?: (candidatePath: string) => boolean;
};

type PythonRuntimeOptions = PythonEnvOptions & {
  readTextFile?: (filePath: string) => string;
  realPath?: (candidatePath: string) => string;
};

type SystemPythonOptions = {
  searchPath: string;
  allowedRoots: readonly string[];
  platform?: NodeJS.Platform;
  listDir?: (dirPath: string) => string[];
  realPath?: (candidatePath: string) => string;
};

const UV_SYNC_HINT = "Run 'uv sync --locked' from the repository root.";
// uv-managed installs are named like cpython-3.12.14-linux-x86_64-gnu (or a cpython-3.12-... minor alias).
const UV_MANAGED_INSTALL_PATTERN = /^(?:cpython|pypy|graalpy)-\d+\.\d+/i;
const PYTHON_EXECUTABLE_PATTERN = /^python(?:\d+(?:\.\d+)*)?$/;
const PYTHON_STDLIB_DIR_PATTERN = /^python\d+(?:\.\d+)*$/;
const STANDARD_POSIX_BIN_DIRS = ["/usr/bin", "/usr/local/bin", "/bin"];

/**
 * Returns the base interpreter installation behind the project `.venv`, so the
 * benchmark-subject sandbox can read it. The venv must be created by uv; its
 * `python` symlink points into uv's managed Python store, outside the repo.
 */
export function resolveBenchmarkPythonRuntimeReadPaths(options: PythonRuntimeOptions = {}): string[] {
  const venvBinDir = resolveLocalVenvBinDir(options);
  if (!venvBinDir) {
    throw new Error(`No project .venv was found for benchmark Python. ${UV_SYNC_HINT}`);
  }

  const venvDir = path.dirname(venvBinDir);
  const readTextFile = options.readTextFile ?? ((filePath: string) => readFileSync(filePath, "utf8"));
  const pyvenvCfg = parsePyvenvCfg(readTextFile(path.join(venvDir, "pyvenv.cfg")));
  if (!pyvenvCfg.uv) {
    throw new Error(`${venvDir} was not created by uv, so it would not use a uv-managed Python. ${UV_SYNC_HINT}`);
  }
  if (!pyvenvCfg.home) {
    throw new Error(`${path.join(venvDir, "pyvenv.cfg")} does not record the base Python home. ${UV_SYNC_HINT}`);
  }

  // POSIX installs record `<root>/bin`; Windows installs record the root itself.
  const home = path.resolve(pyvenvCfg.home);
  const installRoot = path.basename(home).toLowerCase() === "bin" ? path.dirname(home) : home;
  if (!UV_MANAGED_INSTALL_PATTERN.test(path.basename(installRoot))) {
    throw new Error(
      `${venvDir} is based on ${installRoot}, which is not a uv-managed Python. ` +
        `Keep python-preference = "only-managed" in pyproject.toml and rerun 'uv sync --locked'.`,
    );
  }
  const realPath = options.realPath ?? realpathSync;
  let resolvedRoot = installRoot;
  try {
    resolvedRoot = realPath(installRoot);
  } catch {
    // Keep the recorded path; Python startup will report a missing interpreter.
  }
  return [...new Set([installRoot, resolvedRoot])];
}

/**
 * Returns resolved system interpreter binaries and their stdlib directories so
 * the benchmark-subject sandbox can deny them. Codex's Linux sandbox cannot
 * bind-mount over symlinks, so only resolved targets are returned; aliases such
 * as /usr/bin/python3 then point at a denied file. Interpreters inside
 * `allowedRoots` (the project venv and its uv-managed runtime) are kept.
 * Native Windows is not covered.
 */
export function resolveSystemPythonDenyPaths(options: SystemPythonOptions): string[] {
  if ((options.platform ?? process.platform) === "win32") {
    return [];
  }
  const listDir = options.listDir ?? ((dirPath: string) => readdirSync(dirPath));
  const realPath = options.realPath ?? realpathSync;
  const tryRealPath = (candidate: string): string | null => {
    try {
      return realPath(candidate);
    } catch {
      return null;
    }
  };
  const tryListDir = (dirPath: string): string[] => {
    try {
      return listDir(dirPath);
    } catch {
      return [];
    }
  };
  const allowedRoots = options.allowedRoots.flatMap((root) => [path.resolve(root), tryRealPath(root)]).filter(
    (root): root is string => root !== null,
  );
  const isAllowed = (candidate: string) =>
    allowedRoots.some((root) => {
      const relative = path.relative(root, candidate);
      return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
    });

  const searchDirs = [
    ...options.searchPath.split(path.delimiter).filter(Boolean),
    ...STANDARD_POSIX_BIN_DIRS,
  ].map((dir) => path.resolve(dir));
  const executables = new Set<string>();
  for (const dir of new Set(searchDirs)) {
    for (const entry of tryListDir(dir)) {
      if (!PYTHON_EXECUTABLE_PATTERN.test(entry)) {
        continue;
      }
      const target = tryRealPath(path.join(dir, entry));
      if (target && !isAllowed(target)) {
        executables.add(target);
      }
    }
  }

  const denyPaths = new Set(executables);
  for (const executable of executables) {
    const libDir = path.join(path.dirname(path.dirname(executable)), "lib");
    for (const entry of tryListDir(libDir)) {
      if (!PYTHON_STDLIB_DIR_PATTERN.test(entry)) {
        continue;
      }
      const target = tryRealPath(path.join(libDir, entry));
      if (target && !isAllowed(target)) {
        denyPaths.add(target);
      }
    }
  }
  return [...denyPaths].sort();
}

function parsePyvenvCfg(content: string): Record<string, string> {
  const values: Record<string, string> = {};
  for (const line of content.split(/\r?\n/)) {
    const separator = line.indexOf("=");
    if (separator > 0) {
      values[line.slice(0, separator).trim().toLowerCase()] = line.slice(separator + 1).trim();
    }
  }
  return values;
}

export function resolveBenchmarkPythonExecutable(options: PythonEnvOptions = {}): string {
  const venvPython = resolveLocalVenvPython(options);
  return venvPython ?? "python";
}

export function buildBenchmarkPythonEnv(
  baseEnv: EnvInput,
  options: PythonEnvOptions = {},
): Record<string, string> {
  const nextEnv: Record<string, string> = {};
  for (const [key, value] of Object.entries(baseEnv)) {
    if (typeof value === "string") {
      nextEnv[key] = value;
    }
  }

  const venvBinDir = resolveLocalVenvBinDir(options);
  if (!venvBinDir) {
    return nextEnv;
  }

  const venvDir = path.dirname(venvBinDir);
  nextEnv.VIRTUAL_ENV = nextEnv.VIRTUAL_ENV ?? venvDir;

  const pathKeys = Object.keys(nextEnv).filter((key) => key.toLowerCase() === "path");
  if (pathKeys.length === 0) {
    nextEnv.PATH = venvBinDir;
    return nextEnv;
  }

  for (const pathKey of pathKeys) {
    const entries = nextEnv[pathKey].split(path.delimiter).filter((entry) => entry.length > 0);
    nextEnv[pathKey] = [venvBinDir, ...entries.filter((entry) => path.resolve(entry) !== path.resolve(venvBinDir))].join(
      path.delimiter,
    );
  }

  return nextEnv;
}

function resolveLocalVenvPython(options: PythonEnvOptions): string | null {
  const binDir = resolveLocalVenvBinDir(options);
  if (!binDir) {
    return null;
  }

  return path.basename(binDir).toLowerCase() === "scripts" ? path.join(binDir, "python.exe") : path.join(binDir, "python");
}

function resolveLocalVenvBinDir(options: PythonEnvOptions): string | null {
  const cwd = options.cwd ?? process.cwd();
  const pathExists = options.pathExists ?? existsSync;
  const candidates = [
    path.join(cwd, ".venv", "Scripts"),
    path.join(cwd, ".venv", "bin"),
  ];

  for (const binDir of candidates) {
    const pythonPath =
      path.basename(binDir).toLowerCase() === "scripts" ? path.join(binDir, "python.exe") : path.join(binDir, "python");
    if (pathExists(pythonPath)) {
      return binDir;
    }
  }

  return null;
}
