#!/usr/bin/env bash
set -euo pipefail

output_path="$(mktemp)"
trap 'rm -f "$output_path"' EXIT

node --import tsx --test --experimental-test-coverage tests/*.test.ts | tee "$output_path"

awk -F'|' '
function trim(value) {
  gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
  return value
}

BEGIN {
  expected["src/benchmark/config.ts"] = 1
  expected["src/benchmark/focus.ts"] = 1
  expected["src/benchmark/modes.ts"] = 1
  expected["src/benchmark/paper-artifacts.ts"] = 1
  expected["src/benchmark/prompt.ts"] = 1
  expected["src/benchmark/python-bridge.ts"] = 1
  expected["src/benchmark/python-env.ts"] = 1

  # Node 18 + tsx reports this call-site argument line as uncovered even
  # though default and override timeout behavior are covered in config tests.
  allowed["src/benchmark/config.ts", "48"] = 1
}

/^# src\/benchmark\/.*\.ts[[:space:]]*\|/ {
  file = trim($1)
  sub(/^# /, "", file)
  if (!(file in expected)) {
    next
  }

  seen[file] = 1
  line_coverage = trim($2)
  uncovered = trim($5)
  split(uncovered, lines, ",")
  for (i in lines) {
    line_number = trim(lines[i])
    if (line_number == "") {
      continue
    }
    if (!((file, line_number) in allowed)) {
      if (unexpected[file] == "") {
        unexpected[file] = line_number
      } else {
        unexpected[file] = unexpected[file] ", " line_number
      }
    }
  }
  if (line_coverage != "100.00" && uncovered == "") {
    unexpected[file] = "line coverage " line_coverage " without line detail"
  }
}

END {
  for (file in expected) {
    if (!(file in seen)) {
      print "missing coverage row: " file > "/dev/stderr"
      failed = 1
    }
  }
  for (file in unexpected) {
    print "coverage gap: " file " uncovered " unexpected[file] > "/dev/stderr"
    failed = 1
  }
  if (failed) {
    exit 1
  }
}
' "$output_path"

echo "Deterministic standalone TypeScript source-line coverage gate passed." >&2
