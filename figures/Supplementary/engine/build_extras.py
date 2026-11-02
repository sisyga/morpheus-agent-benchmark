"""Build Supplementary Table 1 or Supplementary Note 1 alone (LaTeX and PDF, as typeset in the supplement).

Usage: python figures/Supplementary/engine/build_extras.py table|note --out <folder>

table: the scorer's target, criteria and weights for every study, from biological_scoring_criteria.json at the
repository root; its SHA-256 is checked against the scorer folder name in Supp_Table_1/data/biological_scores/.
note: the agent prompt of the shown Molè run and the resources block of every setup, from the subject_prompt.txt
files in Supp_Note_1/data/.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402
import supp_document  # noqa: E402
import supp_extras  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part", choices=["table", "note"])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    repo = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    os.makedirs(a.out, exist_ok=True)
    if a.part == "table":
        block = supp_extras.criteria_table(*supp_extras.load_criteria(repo, os.path.join(config.TABLE_DIR, "data")))
    else:
        supp_extras.collect_prompts(os.path.join(config.NOTE_DIR, "data"), a.out)
        block = supp_extras.prompt_note(a.out)
    tex = supp_document.write(a.out, [], "_" + ("Table_1" if a.part == "table" else "Note_1"), [block])
    print(f"wrote {supp_document.compile(tex) or tex}")


if __name__ == "__main__":
    main()
