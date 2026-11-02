"""Build the paper-comparison supplementary figures of the Morpheus.AI benchmark.

    python figures/Supplementary/engine/build_all.py --runs <benchmark dir> --out <new output folder> [--only 02_Thapa2024 ...]

Writes one folder per paper, <out>/NN_<Paper><year>/, with the figure (.svg/.pdf/.png), the full model graph
(<key>_model_graph.svg), the legend (caption.md, caption.tex), technical_notes.md, the scored model.xml and
sources.csv (every input with sha256); and, at the top level, captions.md, technical_notes.md,
Supplementary_Figures.tex/.pdf (all figures with their legends, supp_document.py), best_models.csv,
Supp_Fig_best_model_xmls.zip, the model-graph supplementary figure (Supp_model_graphs/), README.md and
style_check.md (check_style.py). Inputs are named in config.py; panel d of
each paper is drawn by panels/pNN_*.py. Every sources.csv, best_models.csv and the README record the build commit.
"""
import argparse
import csv
import datetime
import glob
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import check_style  # noqa: E402
import config  # noqa: E402
import figure  # noqa: E402
import graph_pages  # noqa: E402
import graphs  # noqa: E402
import legend  # noqa: E402
import paper_data  # noqa: E402
import supp_document  # noqa: E402
import supp_extras  # noqa: E402

MARKER = ".supp_figs_build"
ZIP_NAME = "Supp_Fig_best_model_xmls.zip"
# what Morpheus's reduced model graph leaves out, from comparing the full and reduced dot files of all 15 models
REDUCED_TXT = ("Compared with the full graph, reduced mode leaves out the analysis plugins (Logger, Gnuplotter, "
               "TiffPlotter, ContactLogger and similar) with their edges and the symbols only they read, the "
               "functions and cell-type properties that only feed them, and the plugins' descriptive names; plugins "
               "of the same type and time step are drawn as one node. Clusters (Global, cell types, CPM "
               "components) are kept.")


def panel_module(key):
    """panel.py of the figure folder of key (what the figure shows), imported once as panel_<key>."""
    name = f"panel_{key}"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, os.path.join(config.fig_dir(key), "panel.py"))
        sys.modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sys.modules[name])
    return sys.modules[name]


def runs_for(key, runs):
    """Folder that holds the shown run of key: the full benchmark directory (--runs) or the figure's data/."""
    return runs or os.path.join(config.fig_dir(key), "data")


def prepare_out(out):
    """The output folder must be new or one made by this script: nothing else is ever overwritten."""
    if os.path.exists(out) and os.listdir(out) and not os.path.exists(os.path.join(out, MARKER)):
        raise SystemExit(f"{out} exists and was not made by build_all.py; choose a new folder.")
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, MARKER), "w").write("output folder of figures/Supplementary/engine/build_all.py\n")


def build_commit(repo):
    """'<sha>' of the repository HEAD, with ' dirty' if the build's inputs in the repository (this folder and
    benchmark_papers/) had uncommitted changes or untracked files; files elsewhere, e.g. a local .claude/, don't count."""
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                             check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "figures/Supplementary/engine", "benchmark_papers"],
                               cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown (no git)"
    return sha + (" dirty" if dirty else "")


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
    """Frame label without matplotlib mathtext, for the technical notes: 'τ$_0$' -> 'τ₀', '$\\mathit{t}$' -> 't',
    'τ$_\\mathrm{N}$' -> 'τ_N' (Arial in the figures has no subscript digits, so the labels themselves keep
    mathtext)."""
    label = re.sub(r"\$\\mathit\{(\w+)\}\$", r"\1", label)
    label = re.sub(r"\$_\\mathrm\{(\w+)\}\$", r"_\1", label)
    return re.sub(r"\$_\{?(\d+)\}?\$", lambda m: m.group(1).translate(str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")),
                  label)


def caption(n, key, ctx, mod, info, page):
    """Legend of one figure. The figures carry no panel headings, so everything they used to say (paper figure
    numbers, model, mode, repetition, score, reduced/wrapped graph, page of the full-size graph) is said here.
    page: (number, label size) of the model graph's landscape page, or None."""
    spec = config.PANEL_A[key]
    pages = sorted({p + 1 for p, _, _ in spec["crops"]})
    frames = config.ATWELL_FRAMES if key == "04_Atwell2025" else config.FRAMES[key]
    frames = [(f, plain(lab)) for f, lab in frames]
    btxt = getattr(mod, "B_SOURCE", None) or (
        "3D renders (atwell_3d.py) of the run's lattice checkpoints and of the initial lattice rebuilt from "
        "model.xml, at " + ", ".join(lab for _, lab in frames)
        if key == "04_Atwell2025" else
        "the run's own Gnuplotter output (" + "; ".join(f"{f}: {lab}" for f, lab in frames) + ")")
    if key in config.FRAME_CROP:
        btxt += ", cropped to one sub-plot"
    if getattr(mod, "B_LEGEND", None):
        btxt += "; colour key below the frames"
    if getattr(mod, "B_CAPTION", None):
        btxt += "; " + mod.B_CAPTION
    g = info["graph"]
    (fn, fe), (rn, re_) = info["counts_full"], info["counts_shown"]
    if g.reduced:
        gtxt = ("Reduced model graph of the scored model.xml (Morpheus 2.4.1 ModelGraph, include-tags=\"#untagged\", "
                f"reduced=\"true\"; {rn} nodes and {re_} edges, full graph {fn} nodes and {fe} edges), laid out with "
                "Graphviz dot" + (f" and wrapped into {info['graph_rows']} rows" if info["graph_rows"] > 1 else "")
                + f"; labels print at {info['graph_text_pt']:.1f} pt as vector text. " + REDUCED_TXT)
    else:
        gtxt = ("Full model graph of the scored model.xml (Morpheus 2.4.1 ModelGraph, include-tags=\"#untagged\"; "
                f"{fn} nodes, {fe} edges). The panel shows the full graph instead of the reduced one because "
                "Graphviz dot 16.1 cannot lay out this model's reduced graph (error 'trouble in init_rank')"
                + (f"; it is wrapped into {info['graph_rows']} rows" if info["graph_rows"] > 1 else "")
                + f"; labels print at {info['graph_text_pt']:.1f} pt as vector text.")
    gtxt += (f" Full graph: page {page[0]} of the model-graph supplementary figure" if page else " Full graph")
    gtxt += f" and vector file {key}/{key}_model_graph.svg."
    if spec.get("omit"):
        atxt, lt = "", dict(zip("bcd", "abc"))
    else:
        labs = [lab for _, _, lab in spec["crops"]]
        order = ""
        if any(labs):
            order = ("; crops in reading order: " if len(labs) > 1 else "; ") + "; ".join(lab for lab in labs if lab)
        atxt = (f"**a**, {spec.get('cite', spec['title'])} (crop{'s' if len(labs) > 1 else ''} of "
                f"{spec.get('pdf', f'benchmark_papers/{key}.pdf')}, page{'s' if len(pages) > 1 else ''} "
                f"{', '.join(map(str, pages))}{order}). ")
        lt = dict(zip("bcd", "bcd"))
    lines = [f"## Supplementary Fig. {n} ({key})", "",
             atxt + f"**{lt['b']}**, Reimplementation by {config.MODEL} in mode {config.MODE_LABEL[ctx.mode]} "
             f"(repetition {ctx.rep}, judge score {ctx.score:.2f}; run {ctx.run}, scored attempt {config.ATTEMPT}): "
             f"{btxt}. **{lt['c']}**, {gtxt} **{lt['d']}**, "
             f"{mod.CAPTION.format(**ctx.fmt) if ctx.fmt else mod.CAPTION}"]
    if spec.get("omit"):
        lines += ["", f"The original figure ({spec['title']}) is not reproduced because the publication is not "
                      "open access."]
    if ctx.notes:
        lines += ["", "Data handling: " + " ".join(ctx.notes)]
    if ctx.missing:
        lines += ["", "Not shown because the run did not log it: " + "; ".join(ctx.missing) + "."]
    return "\n".join(lines) + "\n"


def exempt_text(key, mod, info, page):
    """Text in the figure that the style check cannot see or that is not ours to restyle. A panel module whose
    frames are drawn as vector graphics sets B_EXEMPT (list of extra lines, usually empty)."""
    spec = config.PANEL_A[key]
    lt = dict(zip("bcd", "abc")) if spec.get("omit") else dict(zip("bcd", "bcd"))
    out = []
    if not spec.get("omit"):
        out.append(f"panel a: {len(spec['crops'])} raster crop(s) of the publication PDF (its own lettering and "
                   "axis text)")
    if getattr(mod, "B_EXEMPT", None) is not None:
        out += mod.B_EXEMPT
    elif key == "04_Atwell2025":
        out.append(f"panel {lt['b']}: {len(config.ATWELL_FRAMES)} raster 3D renders (atwell_3d.py)")
    else:
        out.append(f"panel {lt['b']}: {len(config.FRAMES[key])} raster Gnuplotter frames of the agent's run, "
                   "cropped (any text left in them is the run's own)")
    return out


def graph_text(key, info, page):
    """Graphviz label sizes of panel c and of the paper's model-graph page (zoomable vector text)."""
    lt = dict(zip("bcd", "abc")) if config.PANEL_A[key].get("omit") else dict(zip("bcd", "bcd"))
    out = [f"panel {lt['c']} ({'reduced' if info['graph'].reduced else 'full'} graph): "
           f"{info['graph_text_pt']:.1f} pt"]
    if page:
        out.append(f"Supp_model_graphs_p{page[0]:02d} (full graph): {page[1]:.1f} pt")
    out.append(f"{key}_model_graph.svg: full graph at Graphviz size ({graphs.GRAPH_FONT_PT:g} pt)")
    return out


def provenance(path, runs, repo, work):
    """category (benchmark run / paper source / committed derived / built here) and the path relative to the
    benchmark root, the repository or the intermediate folder."""
    p = os.path.abspath(path)
    def rel(root):
        if root is None:
            return None
        try:  # different drives (Windows) cannot be related
            r = os.path.relpath(p, os.path.abspath(root))
        except ValueError:
            return None
        return None if r.startswith("..") else r.replace("\\", "/")

    if rel(runs) and rel(runs).startswith("rerun_"):  # a rerun kept in a figure folder's data/
        return dict(category="rerun", rel_path=rel(runs))
    for root, cat in ((runs, "benchmark run output"), (work, "derived, built from the run here")):
        if rel(root):
            return dict(category=cat, rel_path=rel(root))
    r = rel(repo) or p
    if "/model_graph/" in r:
        cat = "derived, committed (model graph of the run's model.xml)"
    elif r.startswith("benchmark_papers/") or "/paper_data/" in r:
        cat = "paper source"
    elif runs and rel(os.path.dirname(os.path.abspath(runs))):  # reruns kept next to the benchmark directory
        cat, r = "rerun next to the benchmark directory", rel(os.path.dirname(os.path.abspath(runs)))
    else:
        cat = "other"
    return dict(category=cat, rel_path=r)


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", help=f"full benchmark directory ({config.BENCHMARK}); default: each figure folder's data/")
    ap.add_argument("--out", required=True, help="output folder (new, or one made by this script)")
    ap.add_argument("--only", nargs="*", help="paper keys, e.g. 02_Thapa2024")
    ap.add_argument("--work", help="folder for intermediate files (default: <out>/_intermediate)")
    ap.add_argument("--repo", default=os.path.dirname(os.path.dirname(os.path.dirname(HERE))), help="repository root")
    ap.add_argument("--from-scratch", action="store_true",
                    help="rebuild every derived input from the benchmark run and the paper sources: a new, empty "
                         "intermediate folder (no cached renders), and all model graphs regenerated from the runs' "
                         "model.xml with the Morpheus CLI and checked against the committed model_graphs/*.dot")
    ap.add_argument("--compare-to", help="previous build folder: style_check.md lists text strings of each SVG that "
                                         "disappeared or appeared (regression check)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # log lines quote figure text (α, µ)
    commit = build_commit(a.repo)
    prepare_out(a.out)
    work = a.work or os.path.join(a.out, "_intermediate")
    if a.from_scratch and os.path.exists(work) and os.listdir(work):
        raise SystemExit(f"--from-scratch needs a new or empty intermediate folder; {work} is not empty.")
    os.makedirs(work, exist_ok=True)
    keys = [k for k in config.RUNS if not a.only or k in a.only]
    missing = [(k, p) for k in keys for p in [os.path.join(a.repo, config.PANEL_A[k].get("pdf", f"benchmark_papers/{k}.pdf"))]
               if not config.PANEL_A[k].get("omit") and not os.path.exists(p)]
    if missing:  # e.g. the CC BY-NC-ND Al Reza preprint, which the repository does not redistribute
        raise SystemExit("Panel a needs paper PDFs that are missing (see benchmark_papers/README.md):\n"
                         + "\n".join(f"  {k}: {os.path.relpath(p, a.repo)}" for k, p in missing)
                         + "\nAdd them, or leave these papers out with --only.")
    print(f"build commit {commit}" + (", from scratch" if a.from_scratch else ""))
    regen, model_inputs = {}, {}
    if a.from_scratch:
        morpheus = graphs.find_morpheus()
        if not morpheus:
            raise SystemExit("--from-scratch needs the Morpheus CLI (model graphs); none found.")
        for key in keys:
            xml = os.path.join(runs_for(key, a.runs), config.RUNS[key][0], config.ATTEMPT, "model.xml")
            regen[key], model_inputs[key] = graphs.regenerate(key, xml, os.path.join(work, "model_graphs"), morpheus)
            for name, _, verdict in regen[key]:
                print(f"  model graph {name}: regenerated from model.xml, {verdict}")

    built, graph_info = [], {}
    for n, key in enumerate(config.RUNS, start=1):
        if key not in keys:
            continue
        print(key, flush=True)
        kdir = os.path.join(a.out, key)
        os.makedirs(kdir, exist_ok=True)
        ctx = figure.Ctx(key, runs_for(key, a.runs), a.repo, work)
        if key == "04_Atwell2025":
            atwell_frames(ctx)
        mod = panel_module(key)
        info = figure.build(key, mod, ctx, os.path.join(kdir, key))
        if ctx.summaries:  # tables computed here from large outputs (Ctx.summary)
            os.makedirs(os.path.join(kdir, figure.SUMMARY_DIR), exist_ok=True)
            for name, df in ctx.summaries.items():
                df.to_csv(os.path.join(kdir, figure.SUMMARY_DIR, name + ".csv"), index=False,
                          lineterminator="\n")
        graph_info[key] = info
        built.append((n, key, ctx, mod, info))

    gdir = os.path.join(a.out, "Supp_model_graphs")
    gp = graph_pages.build(graph_info, gdir, work, lambda k: os.path.join(a.out, k, f"{k}_model_graph.svg"))

    caps, legends, texs, best, exempt, gtext = [], [], [], [], {}, {}
    for n, key, ctx, mod, info in built:
        kdir = os.path.join(a.out, key)
        page = gp["pages"].get(key)
        cap = caption(n, key, ctx, mod, info, page)
        caps.append(cap)
        open(os.path.join(kdir, "technical_notes.md"), "w", encoding="utf-8").write(cap)
        lf = legend.fields(ctx, info)
        title, panels, tail = legend.assemble(mod, key, lf)
        legends.append(legend.to_markdown(n, title, panels, tail))
        texs.append((n, key, legend.to_latex(title, panels, tail)))
        open(os.path.join(kdir, "caption.md"), "w", encoding="utf-8").write(legends[-1])
        open(os.path.join(kdir, "caption.tex"), "w", encoding="utf-8").write(texs[-1][2] + "\n")
        xml = os.path.join(ctx.att, "model.xml")
        shutil.copyfile(xml, os.path.join(kdir, "model.xml"))
        inputs = list(ctx.inputs) + [("model graph (regenerated from model.xml; " + verdict + ")", path)
                                     for name, path, verdict in regen.get(key, [])] +                  [("model input file read by model.xml (needed to regenerate the model graph)", f)
                  for f in model_inputs.get(key, [])]
        write_csv(os.path.join(kdir, "sources.csv"), [
            dict(figure=f"{key}.svg/.pdf/.png", paper=key, run_dir=ctx.run, mode=ctx.mode, rep=ctx.rep,
                 score=f"{ctx.score:.3f}", role=role, **provenance(path, runs_for(key, a.runs), a.repo, work),
                 sha256=figure.sha256(path), build_commit=commit)
            for role, path in inputs])
        best.append(dict(paper=key, run=ctx.run, mode=ctx.mode, rep=ctx.rep, score=f"{ctx.score:.3f}",
                         model_xml_source=f"{ctx.run}/{config.ATTEMPT}/model.xml", sha256=figure.sha256(xml),
                         figure_build=commit))
        exempt[key] = exempt_text(key, mod, info, page)
        gtext[key] = graph_text(key, info, page)

    write_csv(os.path.join(gdir, "sources.csv"), [
        dict(figure="Supp_model_graphs", role=role, **provenance(path, a.runs, a.repo, work),
             sha256=figure.sha256(path), build_commit=commit)
        for role, path in gp["inputs"]])

    suffix = "" if not a.only else "_" + "_".join(k[:2] for k in keys)
    write_csv(os.path.join(a.out, f"best_models{suffix}.csv"), best)
    with zipfile.ZipFile(os.path.join(a.out, ZIP_NAME if not suffix else ZIP_NAME[:-4] + suffix + ".zip"), "w",
                         zipfile.ZIP_DEFLATED) as z:
        for b in best:
            z.write(os.path.join(runs_for(b["paper"], a.runs), b["model_xml_source"]), f"{b['paper']}/model.xml")
    with open(os.path.join(a.out, f"captions{suffix}.md"), "w", encoding="utf-8") as f:
        f.write(legend.HEADER.format(suffix=suffix))
        f.write("\n".join(legends))
    with open(os.path.join(a.out, f"technical_notes{suffix}.md"), "w", encoding="utf-8") as f:
        f.write("# Technical notes: paper-comparison supplementary figures\n\n"
                "Generated by figures/Supplementary/engine/build_all.py. Paper data are digitised from the cited figures "
                "(WebPlotDigitizer) unless noted; agent data come from the scored attempt's own output files.\n\n")
        f.write("\n".join(caps))
        f.write("\n" + gp["caption"])
        f.write("\n## Corrections of digitised paper data\n\n| file | action | description |\n|---|---|---|\n")
        for rel, kind, desc in paper_data.corrections_table():
            f.write(f"| {rel} | {kind} | {desc} |\n")
    with open(os.path.join(a.out, f"README{suffix}.md"), "w", encoding="utf-8") as f:
        f.write("# Paper-comparison supplementary figures\n\n"
                f"Built {datetime.date.today().isoformat()} by `figures/Supplementary/engine/build_all.py` at commit "
                f"`{commit}` of the repository, from " + (f"the benchmark `{os.path.basename(os.path.normpath(a.runs))}`" if a.runs else "the data/ folders of the figure folders")
                + (" from scratch (`--from-scratch`: model graphs regenerated from each run's model.xml with the "
                   "Morpheus CLI, every derived file rebuilt in a new intermediate folder)" if a.from_scratch else "")
                + ".\n\nReproduce: `python figures/Supplementary/engine/build_all.py --runs <benchmark dir> --out <new folder> "
                  "--from-scratch`; inputs, tools and versions: figures/Supplementary/README.md, section Full "
                  "reproduction. Each `sources.csv` lists every input with its category, its path relative to the "
                  "benchmark root or the repository, and its SHA-256.\n\n"
                "- `NN_<Paper><year>/`: the figure (`.svg`, `.pdf`, `.png` at 600 dpi; 180 x 170 mm), the full model "
                "graph (`<key>_model_graph.svg`), the legend (`caption.md`, `caption.tex`), `technical_notes.md`, the "
                "scored `model.xml` and `sources.csv` (every input file with its sha256 and the build commit)\n"
                "- `Supp_model_graphs/`: the full model graph of every paper on a landscape A4 page, vector with "
                "live text to be zoomed (`Supp_model_graphs.pdf` has all pages); panel c shows the reduced graph\n"
                "- `Supplementary_Figures.pdf` (`.tex`): every figure on its own page followed by its legend, typeset "
                "with the manuscript's document class (revtex4-2), by `supp_document.py`\n"
                "- `captions.md`: the publication legends; `technical_notes.md`: the detailed notes on every input, "
                "the model-graph figure legend and the corrections of digitized data\n"
                f"- `best_models.csv`, `{ZIP_NAME}`: the shown run and scored model.xml per paper\n"
                "- `style_check.md`: text sizes, weights, colours, brackets and page sizes checked against the "
                "Nature Methods figure guide (`check_style.py`)\n")
    extras, notes = supp_extras.build(a.out, a.repo, a.runs or os.path.join(config.TABLE_DIR, "data"),
                                      a.runs or os.path.join(config.NOTE_DIR, "data"))
    for line in notes:
        print(line)
    tex = supp_document.write(a.out, texs, suffix, extras)
    try:
        pdf = supp_document.compile(tex)
        print(f"supplementary PDF: {pdf}" if pdf else f"no TeX engine found; wrote {tex} only")
    except RuntimeError as e:
        print(f"supplementary PDF failed: {e}")
    try:  # the check reports, it never stops the build
        check_style.main(a.out, exempt=exempt, legend_hits={k: i["legend_hits"] for k, i in graph_info.items()},
                         graph_text=gtext, compare_to=a.compare_to)
    except Exception as e:  # noqa: BLE001
        print(f"style check failed: {e!r}")


if __name__ == "__main__":
    main()
