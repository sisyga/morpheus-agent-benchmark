/* node:coverage disable */
import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import {
  buildBenchmarkPythonEnv,
  resolveBenchmarkPythonExecutable,
  resolveBenchmarkPythonRuntimeReadPaths,
  resolveSystemPythonDenyPaths,
} from "../src/benchmark/python-env.js";

test("resolveBenchmarkPythonExecutable returns the executable matching the discovered venv bin dir", () => {
  const root = path.join("tmp", "repo");
  const linuxPython = path.join(root, ".venv", "bin", "python");

  const resolved = resolveBenchmarkPythonExecutable({
    cwd: root,
    pathExists: (candidate) => candidate === linuxPython,
  });

  assert.equal(resolved, linuxPython);
});

test("resolveBenchmarkPythonExecutable resolves Windows venv scripts", () => {
  const root = path.join("tmp", "repo");
  const windowsPython = path.join(root, ".venv", "Scripts", "python.exe");
  const resolved = resolveBenchmarkPythonExecutable({
    cwd: root,
    pathExists: (candidate) => candidate === windowsPython,
  });

  assert.equal(resolved, windowsPython);
});

test("buildBenchmarkPythonEnv preserves string env and ignores non-string values", () => {
  const env = buildBenchmarkPythonEnv(
    { PATH: "/usr/bin", EMPTY: "", SKIP: undefined },
    { cwd: "missing", pathExists: () => false },
  );

  assert.deepEqual(env, { PATH: "/usr/bin", EMPTY: "" });
});

test("buildBenchmarkPythonEnv adds local venv to PATH and VIRTUAL_ENV", () => {
  const root = path.join("tmp", "repo");
  const venvBin = path.join(root, ".venv", "bin");
  const env = buildBenchmarkPythonEnv(
    { PATH: ["/usr/bin", venvBin, "/bin"].join(path.delimiter) },
    {
      cwd: root,
      pathExists: (candidate) => candidate === path.join(venvBin, "python"),
    },
  );

  assert.equal(env.VIRTUAL_ENV, path.join(root, ".venv"));
  assert.equal(env.PATH, [venvBin, "/usr/bin", "/bin"].join(path.delimiter));
});

test("buildBenchmarkPythonEnv creates PATH when base env has no path key", () => {
  const root = path.join("tmp", "repo");
  const venvScripts = path.join(root, ".venv", "Scripts");
  const env = buildBenchmarkPythonEnv(
    { HOME: "/home/test" },
    {
      cwd: root,
      pathExists: (candidate) => candidate === path.join(venvScripts, "python.exe"),
    },
  );

  assert.equal(env.HOME, "/home/test");
  assert.equal(env.VIRTUAL_ENV, path.join(root, ".venv"));
  assert.equal(env.PATH, venvScripts);
});

test("buildBenchmarkPythonEnv preserves an existing virtualenv marker", () => {
  const root = path.join("tmp", "repo");
  const venvBin = path.join(root, ".venv", "bin");
  const env = buildBenchmarkPythonEnv(
    { PATH: "/usr/bin", VIRTUAL_ENV: "/already-active" },
    {
      cwd: root,
      pathExists: (candidate) => candidate === path.join(venvBin, "python"),
    },
  );

  assert.equal(env.VIRTUAL_ENV, "/already-active");
  assert.equal(env.PATH, [venvBin, "/usr/bin"].join(path.delimiter));
});

test("buildBenchmarkPythonEnv updates all case-insensitive path keys", () => {
  const root = path.join("tmp", "repo");
  const venvScripts = path.join(root, ".venv", "Scripts");
  const env = buildBenchmarkPythonEnv(
    { Path: "/win", PATH: "/usr" },
    {
      cwd: root,
      pathExists: (candidate) => candidate === path.join(venvScripts, "python.exe"),
    },
  );

  assert.equal(env.Path, [venvScripts, "/win"].join(path.delimiter));
  assert.equal(env.PATH, [venvScripts, "/usr"].join(path.delimiter));
});

test("resolveBenchmarkPythonRuntimeReadPaths grants the uv-managed install root and its resolved target", () => {
  const root = path.resolve("tmp", "repo");
  const venvDir = path.join(root, ".venv");
  const aliasRoot = path.resolve("uv", "python", "cpython-3.12-linux-x86_64-gnu");
  const realRoot = path.resolve("uv", "python", "cpython-3.12.14-linux-x86_64-gnu");

  const paths = resolveBenchmarkPythonRuntimeReadPaths({
    cwd: root,
    pathExists: (candidate) => candidate === path.join(venvDir, "bin", "python"),
    readTextFile: (filePath) => {
      assert.equal(filePath, path.join(venvDir, "pyvenv.cfg"));
      return `home = ${path.join(aliasRoot, "bin")}\nimplementation = CPython\nuv = 0.12.21\n`;
    },
    realPath: (candidate) => (candidate === aliasRoot ? realRoot : candidate),
  });

  assert.deepEqual(paths, [aliasRoot, realRoot]);
});

test("resolveBenchmarkPythonRuntimeReadPaths uses the recorded home as the Windows install root", () => {
  const root = path.resolve("tmp", "repo");
  const installRoot = path.resolve("uv", "python", "cpython-3.12.14-windows-x86_64-none");

  const paths = resolveBenchmarkPythonRuntimeReadPaths({
    cwd: root,
    pathExists: (candidate) => candidate === path.join(root, ".venv", "Scripts", "python.exe"),
    readTextFile: () => `home = ${installRoot}\r\nuv = 0.12.21\r\n`,
    realPath: (candidate) => candidate,
  });

  assert.deepEqual(paths, [installRoot]);
});

test("resolveBenchmarkPythonRuntimeReadPaths rejects missing or non-uv virtual environments", () => {
  const root = path.resolve("tmp", "repo");
  const linuxPython = path.join(root, ".venv", "bin", "python");

  assert.throws(
    () => resolveBenchmarkPythonRuntimeReadPaths({ cwd: root, pathExists: () => false }),
    /No project \.venv.*uv sync --locked/,
  );
  assert.throws(
    () =>
      resolveBenchmarkPythonRuntimeReadPaths({
        cwd: root,
            pathExists: (candidate) => candidate === linuxPython,
        readTextFile: () => "home = /usr/bin\ninclude-system-site-packages = false\n",
      }),
    /not created by uv.*uv sync --locked/,
  );
  assert.throws(
    () =>
      resolveBenchmarkPythonRuntimeReadPaths({
        cwd: root,
            pathExists: (candidate) => candidate === linuxPython,
        readTextFile: () => "uv = 0.12.21\n",
      }),
    /does not record the base Python home/,
  );
  assert.throws(
    () =>
      resolveBenchmarkPythonRuntimeReadPaths({
        cwd: root,
            pathExists: (candidate) => candidate === linuxPython,
        readTextFile: () => "home = /usr/bin\nuv = 0.12.21\n",
      }),
    /not a uv-managed Python.*only-managed/,
  );
});

test("resolveSystemPythonDenyPaths denies resolved system interpreters and their stdlib but keeps uv runtimes", () => {
  const venvDir = "/repo/.venv";
  const uvRoot = "/home/u/.local/share/uv/python/cpython-3.12.14-linux-x86_64-gnu";
  const dirs: Record<string, string[]> = {
    "/repo/.venv/bin": ["python", "python3", "activate"],
    "/usr/bin": ["python", "python3", "python3.12", "python3-config", "pydoc3", "morpheus"],
    "/usr/local/bin": [],
    "/opt/homebrew/bin": ["python3"],
    "/usr/lib": ["python3", "python3.12", "pythonish", "x86_64-linux-gnu"],
    "/opt/homebrew/Cellar/python/Frameworks/3.13/lib": ["python3.13"],
  };
  const links: Record<string, string> = {
    "/repo/.venv/bin/python": `${uvRoot}/bin/python3.12`,
    "/repo/.venv/bin/python3": `${uvRoot}/bin/python3.12`,
    "/usr/bin/python": "/usr/bin/python3.12",
    "/usr/bin/python3": "/usr/bin/python3.12",
    "/bin": "/usr/bin",
    "/opt/homebrew/bin/python3": "/opt/homebrew/Cellar/python/Frameworks/3.13/bin/python3.13",
  };

  const denyPaths = resolveSystemPythonDenyPaths({
    searchPath: ["/repo/.venv/bin", "/opt/homebrew/bin", "/missing", "/usr/bin"].join(path.delimiter),
    allowedRoots: [venvDir, uvRoot],
    platform: "linux",
    listDir: (dirPath) => {
      const entries = dirs[dirPath];
      if (!entries) {
        throw new Error(`ENOENT ${dirPath}`);
      }
      return entries;
    },
    realPath: (candidate) => links[candidate] ?? candidate,
  });

  assert.deepEqual(denyPaths, [
    "/opt/homebrew/Cellar/python/Frameworks/3.13/bin/python3.13",
    "/opt/homebrew/Cellar/python/Frameworks/3.13/lib/python3.13",
    "/usr/bin/python3.12",
    "/usr/lib/python3",
    "/usr/lib/python3.12",
  ]);
});

test("resolveSystemPythonDenyPaths skips native Windows and unresolvable entries", () => {
  assert.deepEqual(
    resolveSystemPythonDenyPaths({ searchPath: "C:\\Python312", allowedRoots: [], platform: "win32" }),
    [],
  );
  assert.deepEqual(
    resolveSystemPythonDenyPaths({
      searchPath: "/usr/bin",
      allowedRoots: [],
      platform: "linux",
      listDir: (dirPath) => (dirPath === "/usr/bin" ? ["python3"] : []),
      realPath: () => {
        throw new Error("dangling symlink");
      },
    }),
    [],
  );
});
