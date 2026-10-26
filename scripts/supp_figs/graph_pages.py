"""Model-graph supplementary figure: one landscape A4 page per model whose graph text prints below
config.GRAPH_MIN_TEXT_PT in panel c, plus every full graph as its own SVG (model_graphs/<key>.svg)."""
import os
import shutil

import matplotlib.pyplot as plt
import pymupdf

import config
import figure
import graphs
import style
from graphs import Graph

PAGE_W, PAGE_H = 297.0, 210.0
BOX_W, BOX_H = 267.0, 180.0  # usable area


def build(graph_info, out, work):
    style.apply()
    gdir = os.path.join(out, "model_graphs")
    os.makedirs(gdir, exist_ok=True)
    inputs, pages = [], []
    for key, info in graph_info.items():
        g = Graph(key, os.path.join(work, "graphs"))  # full graph
        shutil.copyfile(g.full_svg, os.path.join(gdir, f"{key}.svg"))
        inputs.append(("model graph (dot)", os.path.join(graphs.GRAPH_DIR, f"{key}.dot")))
        if info["graph_text_pt"] >= config.GRAPH_MIN_TEXT_PT:
            continue
        reduced = key in config.GRAPH_PAGE_REDUCED and g.use_reduced()
        if reduced:
            inputs.append(("model graph (dot)", os.path.join(graphs.GRAPH_DIR, f"{key}_reduced.dot")))
        pages.append((key, g, reduced))

    pdfs = []
    for i, (key, g, reduced) in enumerate(pages, start=1):
        # wide search window and any-ink cuts, so a row break never runs through a node label
        k, s, sl = figure.graph_plan(g, BOX_W, BOX_H - 8, gap=2.0, kmax=12, window=0.25, any_ink=True)
        fig = plt.figure(figsize=(PAGE_W * style.MM, PAGE_H * style.MM))
        x0, y0 = (PAGE_W - BOX_W) / 2, (PAGE_H - BOX_H) / 2
        title = f"Supplementary Fig. model graphs, page {i}: {key}" + \
                (' (reduced graph, Morpheus ModelGraph reduced="true")' if reduced else " (full graph)")
        fig.text(x0 / PAGE_W, 1 - y0 / PAGE_H, title, fontsize=style.FS_HEAD, va="top")
        slots, y = [], y0 + 8
        for a, b in sl:
            w, h = (b - a) * s, g.h * s
            slots.append(((a, b), (x0 + (BOX_W - w) / 2 if k == 1 else x0, y, w, h)))
            y += h + 3.0
        base = os.path.join(out, f"Supp_model_graphs_p{i:02d}")
        fig.savefig(base + ".svg")
        fig.savefig(base + ".pdf")
        plt.close(fig)
        # page coordinates: figure.insert_* work in mm from the top-left corner like the figures
        figure.insert_graph_svg(base + ".svg", g, slots)
        figure.insert_graph_pdf(base + ".pdf", g, slots)
        pymupdf.open(base + ".pdf")[0].get_pixmap(dpi=300).save(base + ".png")
        pdfs.append(base + ".pdf")
        print(f"  graph page {i}: {key}, {k} row(s), text {graphs.GRAPH_FONT_PT * s * figure.PT:.1f} pt")
    if pdfs:
        allp = pymupdf.open()
        for p in pdfs:
            allp.insert_pdf(pymupdf.open(p))
        allp.save(os.path.join(out, "Supp_model_graphs.pdf"))
    lines = ["## Supplementary Fig. model graphs", "",
             "Full-size Morpheus model graphs of the scored models whose graph labels print below "
             f"{config.GRAPH_MIN_TEXT_PT:g} pt in panel c of the paper figure, one landscape page each: "
             + ", ".join(f"page {i}: {k}" + (" (reduced graph)" if r else "") for i, (k, _, r) in enumerate(pages, 1))
             + ". Graphs generated with Morpheus 2.4.1 (ModelGraph include-tags=\"#untagged\") and laid out with "
               "Graphviz dot; wide graphs are wrapped into rows. Every full graph is also given as a vector file, "
               "model_graphs/<paper>.svg.", ""]
    return dict(inputs=inputs, caption="\n".join(lines) + "\n")
