"""Model-graph supplementary figure: the full model graph of every paper on its own landscape A4 page (vector,
live text, to be zoomed in the SI PDF; panel c of each paper figure shows the reduced graph), plus every full
graph as its own SVG (<key>/<key>_model_graph.svg)."""
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


def build(graph_info, out, work, graph_svg):
    """out: folder of the landscape pages; graph_svg(key): where the full graph's SVG goes."""
    style.apply()
    os.makedirs(out, exist_ok=True)
    inputs, pages = [], []
    for key in graph_info:
        g = Graph(key, os.path.join(work, "graphs"))  # full graph
        shutil.copyfile(g.full_svg, graph_svg(key))
        inputs.append(("model graph (dot)", graphs.dot_path(f"{key}.dot")))
        pages.append((key, g))

    pdfs, text_pt = [], {}
    for i, (key, g) in enumerate(pages, start=1):
        # wide search window and any-ink cuts, so a row break never runs through a node label
        k, s, sl = figure.graph_plan(g, BOX_W, BOX_H, gap=2.0, kmax=12, window=0.25, any_ink=True, max_text_pt=8.0)
        fig = plt.figure(figsize=(PAGE_W * style.MM, PAGE_H * style.MM))
        x0, y0 = (PAGE_W - BOX_W) / 2, (PAGE_H - BOX_H) / 2  # no title line: the caption names each page's paper
        slots, y = [], y0
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
        text_pt[key] = graphs.GRAPH_FONT_PT * s * figure.PT
        print(f"  graph page {i}: {key}, {k} row(s), text {text_pt[key]:.1f} pt")
    if pdfs:
        allp = pymupdf.open()
        for p in pdfs:
            allp.insert_pdf(pymupdf.open(p))
        allp.save(os.path.join(out, "Supp_model_graphs.pdf"))
    lines = ["## Supplementary Fig. model graphs", "",
             "Full Morpheus model graphs of the scored models (panel c of each paper figure shows the reduced "
             "graph), one landscape page each, as vector graphics with live text to be zoomed: "
             + "; ".join(f"page {i}: {k} (Supplementary Fig. {list(config.RUNS).index(k) + 1})"
                         for i, (k, _) in enumerate(pages, 1))
             + ". Graphs generated with Morpheus 2.4.1 (ModelGraph include-tags=\"#untagged\") and laid out with "
               "Graphviz dot; wide graphs are wrapped into rows. Every full graph is also given as a vector file, "
               "<paper>/<paper>_model_graph.svg.", ""]
    return dict(inputs=inputs, caption="\n".join(lines) + "\n",
                pages={k: (i, text_pt[k]) for i, (k, _) in enumerate(pages, 1)},
                files=[os.path.join(out, f"Supp_model_graphs_p{i:02d}") for i in range(1, len(pages) + 1)])
