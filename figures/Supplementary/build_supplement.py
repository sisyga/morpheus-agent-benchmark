"""Build the whole supplement: Supplementary Figs. 1-15, the model-graph pages, Supplementary Table 1, Note 1,
the Supplementary Data zip (the 15 model.xml) and Supplementary_Figures.pdf, into build/ here (or --out).

Usage (repository root): python figures/Supplementary/build_supplement.py [--out <new folder>] [--from-scratch]
Every figure folder can also be built on its own with its build.py. Options go to engine/build_all.py.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--out", default=os.path.join(HERE, "build"))
a, rest = ap.parse_known_args()
sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "engine", "build_all.py"), "--out", a.out, *rest]))
