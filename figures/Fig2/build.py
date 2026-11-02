"""Build Fig. 2 of the preprint: build/Fig2.svg, .pdf and a 600 dpi .png (or --out <folder>).

Usage (repository root): uv run --locked python figures/Fig2/build.py [--out <folder>]

Runs the panel scripts (make_table.py: a; make_heatmap.py: b; make_row_c.py: c i-iii; make_plots_de.py: d iii and
e iv) into <out>/panels, assembles the figure (assemble.py) and renders it with headless Chrome (../render_fig.py).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["make_table.py", "make_heatmap.py", "make_row_c.py", "make_plots_de.py"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(HERE / "build"), help="output folder (default: build/ here)")
    out = Path(ap.parse_args().out).resolve()
    env = dict(os.environ, FIGURE_OUT=str(out), PYTHONIOENCODING="utf-8")
    run = lambda *cmd: subprocess.run([sys.executable, *map(str, cmd)], check=True, env=env)  # noqa: E731
    for step in STEPS:
        run(HERE / step)
    run(HERE / "assemble.py", out / "Fig2.svg")
    run(HERE.parent / "render_fig.py", out / "Fig2.svg")


if __name__ == "__main__":
    main()
