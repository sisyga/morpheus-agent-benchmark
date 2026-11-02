"""Atwell et al. (2015) Table S2 (cell counts of the single run shown in Fig. 3), read from the text layer of the
benchmark PDF (page 23 = index 22 of benchmark_papers/04_Atwell2025.pdf, supplementary information). Panel d of the
Atwell figure calls extract() on every build and checks it against the cached copy written by this script.

Table S2 has eight columns of eight values (in the text layer one column after the other): time (hours post
hatching), Proliferative + Meiotic S (yellow cells), Proliferative - Meiotic S, Meiotic S, Meiotic (green cells),
Sperm/Spermatogenic (blue cells), Oogenic (pink cells), Meiotic + Spermatogenic + Oogenic. The table's own sums are
checked: yellow = (Proliferative - Meiotic S) + Meiotic S holds in every row; the last column = green + blue + pink
holds from 32.5 hph on, but the table gives 0 at 27.5 and 30.5 hph, where green is 8 and 85 (an inconsistency of
the published table, in a column not used here).

    python figures/Supplementary/Supp_Fig_04_Atwell2015/atwell_tables2_extract.py [--repo <repository root>]

Output: paper_data/tableS2_counts.csv with columns time_hph, yellow, green, blue, pink.
"""
import argparse
import os
import re

import pandas as pd
import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "paper_data", "tableS2_counts.csv")
PAGE = 22  # 0-based
COLS = ["time_hph", "yellow", "prolif_minus_meiotic_s", "meiotic_s", "green", "blue", "pink", "gametogenic"]


def extract(pdf):
    text = pymupdf.open(pdf)[PAGE].get_text()
    i, j = text.index("Table S2. Cell counts for a single run"), text.index("*In later time points")
    nums = [float(s) for s in (ln.strip().rstrip("*") for ln in text[i:j].splitlines())
            if re.fullmatch(r"\d+(\.\d+)?", s)]
    if len(nums) != 64:
        raise ValueError(f"Table S2: {len(nums)} numbers, expected 8 x 8")
    t = pd.DataFrame({c: nums[8 * k:8 * k + 8] for k, c in enumerate(COLS)})
    bad = t.time_hph[t.green + t.blue + t.pink != t.gametogenic].tolist()
    if not (t.prolif_minus_meiotic_s + t.meiotic_s == t.yellow).all() or bad != [27.5, 30.5]:
        raise ValueError(f"Table S2: row sums do not match as expected (last column off at {bad} hph)")
    t[COLS[1:]] = t[COLS[1:]].astype(int)
    return t[["time_hph", "yellow", "green", "blue", "pink"]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    a = ap.parse_args()
    df = extract(os.path.join(a.repo, "benchmark_papers", "04_Atwell2025.pdf"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write("# Atwell et al. (2015) Table S2: cell counts of the single run shown in Fig. 3 (model output).\n"
                "# Written by figures/Supplementary/Supp_Fig_04_Atwell2015/atwell_tables2_extract.py from the text layer of page 23 of "
                "benchmark_papers/04_Atwell2025.pdf.\n")
        df.to_csv(f, index=False)
    print(df.to_string(index=False))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
