"""Build Supplementary Fig. 14 (Otsuki2025) into build/ here (or --out <folder>).

Usage (repository root): python figures/Supplementary/Supp_Fig_14_Otsuki2025/build.py [--out <folder>] [--from-scratch]

--from-scratch also regenerates the model graph from data/.../model.xml with the Morpheus CLI and renders every
intermediate file anew. Other options go to the shared engine (../engine/build_all.py); see README.md.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = "14_Otsuki2025"

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--out", default=os.path.join(HERE, "build"))
a, rest = ap.parse_known_args()
sys.exit(subprocess.call([sys.executable, os.path.join(HERE, "..", "engine", "build_all.py"), "--only", KEY,
                          "--out", a.out, *rest]))
