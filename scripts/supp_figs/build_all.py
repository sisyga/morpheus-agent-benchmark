"""Build the paper-comparison supplementary figures of the Morpheus agent benchmark.

    python scripts/supp_figs/build_all.py --runs <benchmark dir> --out <new output folder> [--only 02_Thapa2024 ...]

Writes, per paper, NN_<Paper><year>.svg/.pdf/.png, the model-graph supplementary figure
(Supp_model_graphs.pdf/.svg/.png pages and model_graphs/<key>.svg), sources.csv (every input with sha256)
and captions.md. Inputs are named in config.py; panel d of each paper is drawn by panels/pNN_*.py.
"""
import argparse
import csv
import glob
import importlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config  # noqa: E402
import figure  # noqa: E402
import graph_pages  # noqa: E402
import paper_data  # noqa: E402

MARKER = ".supp_figs_build"


def panel_module(key):
    f = glob.glob(os.path.join(HERE, "panels", f"p{key[:2]}_*.py"))[0]
    return importlib.import_module("panels." + os.path.basename(f)[:-3])


def prepare_out(out):
    """The output folder must be new or one made by this script: nothing else is ever overwritten."""
    if os.path.exists(out) and os.listdir(out) and not os.path.exists(os.path.join(out, MARKER)):
        raise SystemExit(f"{out} exists and was not made by build_all.py; choose a new folder.")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, MARKER), "w").write("output folder of scripts/supp_figs/build_all.py\n")


def atwell_frames(ctx):
    png = os.path.join(ctx.work, "atwell3d", "png")
    want = [os.path.join(png, f"atwell_3d_{t}hph.png") for t, _ in config.ATWELL_FRAMES]
    if not all(os.path.exists(p) for p in want):
        import atwell_3d
        atwell_3d.main(ctx.att, os.path.join(ctx.work, "atwell3d"))
    for name in ["model.xml", "cell_states.csv", "cell_counts.csv"] + \
            sorted(os.path.basename(p) for p in glob.glob(os.path.join(ctx.att, "*.xml.gz"))):
        ctx.attempt(name, role="panel b input (3D render)")


def plain(label):
    """Frame label without matplotlib mathtext, for captions.md: 'τ$_0$' -> 'τ₀' (Arial in the figures has no
    subscript digits, so the labels themselves keep mathtext)."""
    return re.sub(r"\$_\{?(\d+)\}?\$", lambda m: m.group(1).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")),
                  label)


def caption(n, key, ctx, mod, info):
    spec = config.PANEL_A[key]
    pages = sorted({p + 1 for p, _, _ in spec["crops"]})
    frames = config.ATWELL_FRAMES if key == "04_Atwell2025" else config.FRAMES[key]
    frames = [(f, plain(lab)) for f, lab in frames]
    btxt = ("3D renders (atwell_3d.py) of the run's lattice checkpoints and of the initial lattice rebuilt from "
            "model.xml, at " + ", ".join(lab for _, lab in frames)
            if key == "04_Atwell2025" else
            "the run's own Gnuplotter output (" + "; ".join(f"{f}: {lab}" for f, lab in frames) + ")")
    if key in config.FRAME_CROP:
        btxt += ", cropped to one sub-plot"
    g = info["graph"]
    gtxt = ("Model graph of the scored model.xml, generated with Morpheus 2.4.1 (ModelGraph include-tags=\"#untagged\""
            + (', reduced="true"' if g.reduced else "") + ") and laid out with Graphviz dot"
            + (f"; wrapped into {info['graph_rows']} rows" if info["graph_rows"] > 1 else "")
            + (f"; labels print at {info['graph_text_pt']:.1f} pt, so the full-size graph is on its own page of the "
               "model-graph supplementary figure" if info["graph_text_pt"] < config.GRAPH_MIN_TEXT_PT else "")
            + f"; vector file model_graphs/{key}.svg.")
    lines = [f"## Supplementary Fig. {n} ({key})", "",
             f"**a**, {spec['title']} (crop of benchmark_papers/{key}.pdf, page{'s' if len(pages) > 1 else ''} "
             f"{', '.join(map(str, pages))}). "
             f"**b**, Reimplementation by {config.MODEL} in mode {config.MODE_LABEL[ctx.mode]} "
             f"(repetition {ctx.rep}, judge score {ctx.score:.2f}; run {ctx.run}, scored attempt {config.ATTEMPT}): "
             f"{btxt}. **c**, {gtxt} **d**, {mod.CAPTION}"]
    if ctx.notes:
        lines += ["", "Data handling: " + " ".join(ctx.notes)]
    if ctx.missing:
        lines += ["", "Not shown because the run did not log it: " + "; ".join(ctx.missing) + "."]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help=f"benchmark directory ({config.BENCHMARK})")
    ap.add_argument("--out", required=True, help="output folder (new, or one made by this script)")
    ap.add_argument("--only", nargs="*", help="paper keys, e.g. 02_Thapa2024")
    ap.add_argument("--work", help="folder for intermediate files (default: <out>/_intermediate)")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(HERE)), help="repository root")
    a = ap.parse_args()
    prepare_out(a.out)
    work = a.work or os.path.join(a.out, "_intermediate")
    os.makedirs(work, exist_ok=True)
    keys = [k for k in config.RUNS if not a.only or k in a.only]

    rows, caps, graph_info = [], [], {}
    for n, key in enumerate(config.RUNS, start=1):
        if key not in keys:
            continue
        print(key, flush=True)
        ctx = figure.Ctx(key, a.runs, a.repo, work)
        if key == "04_Atwell2025":
            atwell_frames(ctx)
        mod = panel_module(key)
        info = figure.build(key, mod, ctx, os.path.join(a.out, key))
        graph_info[key] = info
        caps.append(caption(n, key, ctx, mod, info))
        for role, path in ctx.inputs:
            rows.append(dict(figure=f"{key}.svg/.pdf/.png", paper=key, run_dir=ctx.run_dir, mode=ctx.mode,
                             rep=ctx.rep, score=f"{ctx.score:.3f}", role=role, file=path, sha256=figure.sha256(path)))

    gp = graph_pages.build(graph_info, a.out, work)
    for role, path in gp["inputs"]:
        rows.append(dict(figure="Supp_model_graphs", paper="", run_dir="", mode="", rep="", score="",
                         role=role, file=path, sha256=figure.sha256(path)))

    suffix = "" if not a.only else "_" + "_".join(k[:2] for k in keys)
    with open(os.path.join(a.out, f"sources{suffix}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(a.out, f"captions{suffix}.md"), "w", encoding="utf-8") as f:
        f.write("# Captions: paper-comparison supplementary figures\n\n"
                "Generated by scripts/supp_figs/build_all.py. Paper data are digitised from the cited figures "
                "(WebPlotDigitizer) unless noted; agent data come from the scored attempt's own output files.\n\n")
        f.write("\n".join(caps))
        f.write("\n" + gp["caption"])
        f.write("\n## Corrections of digitised paper data\n\n| file | action | description |\n|---|---|---|\n")
        for rel, kind, desc in paper_data.corrections_table():
            f.write(f"| {rel} | {kind} | {desc} |\n")


if __name__ == "__main__":
    main()
