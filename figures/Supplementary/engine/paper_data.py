"""Digitised paper data (paper_data/) and every correction applied to it.

Rule: a digitisation error is fixed only when the intended value is obvious; otherwise the point is
dropped. Each entry of CORRECTIONS is applied on loading and listed in technical_notes.md.
"""
import os

import pandas as pd

import config

HERE = os.path.dirname(os.path.abspath(__file__))

# Szabo Fig. 7b monolayer: digitised with a linear calibration on log-log axes (see
# szabo_recalibration.py; fitted on fig_7b.png, sha256 02f0cdcfc9fb54e6...6c74a5ae95e, rms 0.009 decades).
SZABO_MAP = (-1.98395, 0.297344, -0.05654, 0.019297)  # log10 t[h] = a + b x ; log10 D[um] = c + d y

# file -> list of (kind, rows (0-based, original file order; for "fix" {row: (x, y)}), description)
CORRECTIONS = {
    "01_Szabo2010/monolayer.csv": [
        ("drop", [0, 1, 2], "rows 1-3, (0.61, 72.8), (0.81, 62.0), (1.01, 98.5): the legend's red line, not data"),
        ("map", None, "all values: digitised with a linear axis calibration on the log-log axes of Fig. 7b; "
                      "mapped to log10(t / h) = %.5f + %.6f x and log10(D / µm) = %.5f + %.6f y, fitted to the "
                      "red curve of the figure (szabo_recalibration.py; rms deviation 0.009 decades)" % SZABO_MAP),
    ],
    "08_Mu2024/total.csv": [
        ("fix", {0: (0.0, 0.200)}, "row 1, (0.00, 0.134), set to (0, 0.200): the total starts with the 200 B cells "
                                   "of the set-up (p. 6, 'the GC starts with 200 B cells'); at t = 0 the zone lines "
                                   "rise steeply over the total line"),
        ("drop", [4, 5, 7], "rows 5, 6 and 8, (57.6, 0.0527), (72.0, 0.0759), (101, 0.0861): taken from the "
                            "dark-zone line, which covers the total line there, 20–40 cells below the total"),
    ],
    "11_Anlas2024/Sox_2.csv": [
        ("drop", [81], "row 82, (1.01, 0.0926): beyond the end of the A–P axis (1.0)"),
    ],
}


def path(rel):
    """File of a digitised data set: rel is "<paper number>_<name>/<file>" (as in config.PAPER_DATA and CORRECTIONS),
    stored as paper_data/<file> in that paper's figure folder."""
    sub, name = rel.split("/", 1)
    return os.path.join(config.fig_dir(config.key_for(sub.split("_")[0])), "paper_data", name)


def _read(rel):
    path_ = path(rel)
    if rel.endswith("compucell3d_rerun_timecourse.csv"):  # CC3D output, tab-separated, decimal comma
        return pd.read_csv(path_, sep="\t", decimal=",")
    with open(path_, encoding="utf-8") as f:
        if f.read(1) == "#":  # headed CSV with '#' provenance lines (Thapa)
            return pd.read_csv(path_, comment="#")
    return pd.read_csv(path_, header=None, names=["x", "y"], skipinitialspace=True)


def load(rel):
    """DataFrame with corrections applied, and caption sentences describing them."""
    df = _read(rel)
    notes = []
    for kind, rows, desc in CORRECTIONS.get(rel, []):
        if kind == "drop":
            df = df.drop(index=rows)
        elif kind == "fix":
            for i, xy in rows.items():
                df.loc[i, ["x", "y"]] = xy
        elif kind == "map" and rel.startswith("01_Szabo2010/"):
            a, b, c, d = SZABO_MAP
            df = df.assign(x=10 ** (a + b * df.x), y=10 ** (c + d * df.y))
        notes.append(f"{rel}: {desc}.")
    return df.reset_index(drop=True), notes


def corrections_table():
    return [(rel, kind, desc) for rel, lst in CORRECTIONS.items() for kind, _, desc in lst]
