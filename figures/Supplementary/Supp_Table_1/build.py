"""Build Supplementary Table 1 (scoring criteria and weights) into build/ here (or --out <folder>).

Usage (repository root): python figures/Supplementary/Supp_Table_1/build.py [--out <folder>]
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--out", default=os.path.join(HERE, "build"))
a = ap.parse_args()
sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "..", "engine", "build_extras.py"), "table", "--out", a.out]))
