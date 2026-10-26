"""Digitised paper data (paper_data/) and every correction applied to it.

Rule: a digitisation error is fixed only when the intended value is obvious; otherwise the point is
dropped. Each entry of CORRECTIONS is applied on loading and listed in captions.md.
"""
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

# Szabo Fig. 7b monolayer: digitised with a linear calibration on log-log axes (see
# szabo_recalibration.py; fitted on fig_7b.png, sha256 02f0cdcfc9fb54e6...6c74a5ae95e, rms 0.009 decades).
SZABO_MAP = (-1.98395, 0.297344, -0.05654, 0.019297)  # log10 t[h] = a + b x ; log10 D[um] = c + d y

# file -> list of (kind, rows (0-based, original file order), description)
CORRECTIONS = {
    "1_Szabo_2010/monolayer.csv": [
        ("drop", [0, 1, 2], "rows 1-3, (0.61, 72.8), (0.81, 62.0), (1.01, 98.5): the legend's red line, not data"),
        ("map", None, "all values: digitised with a linear axis calibration on the log-log axes of Fig. 7b; "
                      "mapped to log10(t / h) = %.5f + %.6f x and log10(D / µm) = %.5f + %.6f y, fitted to the "
                      "red curve of the figure (szabo_recalibration.py; rms deviation 0.009 decades)" % SZABO_MAP),
    ],
    "9_Luque_2023/hepatocytes.csv": [
        ("drop", [1], "row 2, (-0.945, -0.066): stray point off the curve"),
    ],
}


def _read(rel):
    path = os.path.join(HERE, "paper_data", rel)
    if rel.endswith("My_cNTC_timecourse_hours.csv"):  # CC3D output, tab-separated, decimal comma
        return pd.read_csv(path, sep="\t", decimal=",")
    return pd.read_csv(path, header=None, names=["x", "y"], skipinitialspace=True)


def load(rel):
    """DataFrame with corrections applied, and caption sentences describing them."""
    df = _read(rel)
    notes = []
    for kind, rows, desc in CORRECTIONS.get(rel, []):
        if kind == "drop":
            df = df.drop(index=rows)
        elif kind == "map" and rel.startswith("1_Szabo_2010/"):
            a, b, c, d = SZABO_MAP
            df = df.assign(x=10 ** (a + b * df.x), y=10 ** (c + d * df.y))
        notes.append(f"{rel}: {desc}.")
    return df.reset_index(drop=True), notes


def corrections_table():
    return [(rel, kind, desc) for rel, lst in CORRECTIONS.items() for kind, _, desc in lst]
