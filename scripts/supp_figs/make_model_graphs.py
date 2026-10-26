"""Regenerate the committed model graphs from the scored model.xml of each shown run with the Morpheus CLI
(tested with Morpheus 2.4.1): model_graphs/<key>.dot (ModelGraph reduced="false") and
model_graphs/<key>_reduced.dot (reduced="true").

    python scripts/supp_figs/make_model_graphs.py --runs W:\\20261007_202940_benchmark

Morpheus writes the graph's lines in a non-deterministic order, so a regenerated graph can be laid out
slightly differently; the figures are built from the committed files.
"""
import argparse
import os

import config
from graphs import GRAPH_DIR, find_morpheus, generate_dot


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="benchmark directory holding the run folders")
    ap.add_argument("--only", nargs="*", default=None, help="paper keys to regenerate")
    a = ap.parse_args()
    morpheus = find_morpheus()
    if not morpheus:
        raise SystemExit("Morpheus CLI not found; the committed model_graphs/*.dot are used instead.")
    os.makedirs(GRAPH_DIR, exist_ok=True)
    for key, (run, *_rest) in config.RUNS.items():
        if a.only and key not in a.only:
            continue
        xml = os.path.join(a.runs, run, config.ATTEMPT, "model.xml")
        full = os.path.join(GRAPH_DIR, f"{key}.dot")
        red = os.path.join(GRAPH_DIR, f"{key}_reduced.dot")
        generate_dot(xml, full, morpheus, reduced=False)
        generate_dot(xml, red, morpheus, reduced=True)
        print(f"{key}: full {os.path.getsize(full)} bytes, reduced {os.path.getsize(red)} bytes")


if __name__ == "__main__":
    main()
