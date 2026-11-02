"""Build Fig. 2 of the preprint (Fig2.svg, 180 x 167 mm) from the panel files and assets/fig2_layout.svg.

assets/fig2_layout.svg is the hand-drawn Inkscape layout of rows d and e, reduced to the elements the figure shows: Atwell
et al. (2015) Fig. 3 (CC BY 3.0), the graphical abstract of Molè et al. (2026) (CC BY 4.0), the snapshots of the shown
Atwell and Molè runs, and their axes and labels. This script takes the groups it needs from it (by id).

a      : make_table.py    -> fig2a_table.svg (GPT-6.1 Sol, Nature-style table; values in table1_gpt61sol.xlsx)
b      : make_heatmap.py  -> fig2b_manual_vs_automated_bin01.svg (manual vs automated score, 0.1 bins)
c i-iii: make_row_c.py    -> fig2c_row.svg (one 180 mm row, aligned x-axes, no grid)
d i, d ii, e i: layout groups, moved (d i and d ii enlarged by D_SCALE) with page-space wrapper transforms
d iii, e iv: make_plots_de.py (germ-cell counts; tissue heights in cell diameters)
e ii   : mechanism_graph.py, the interactions of the agent's Molè model
e iii  : the three Molè-model snapshots of the layout, cropped around embryo and gland, right of e i, with a day
         axis drawn like the one in e i
Cell-type legends are drawn like the Fig. 1 legend (../Fig1/build.py, cell_legend: bold title above columns of discs)
at LEGEND_PT instead of 5 pt; e iii uses the
cell names of Molè et al. (2026) with the colours read from the snapshots. Panel labels: bold 8 pt, no brackets.
The matplotlib SVGs are inlined as groups (ids prefixed, global <style> and white figure background dropped) so
their text stays editable in Inkscape.
Usage: python figures/Fig2/build.py (runs the make_*.py panel scripts first), or after them
uv run --locked python figures/Fig2/assemble.py [out.svg]   then   python figures/render_fig.py out.svg
"""
import base64
import copy
import io
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from paths import OUT as BUILD, PANELS, arial  # noqa: E402
import mechanism_graph   # e ii, from the model of the run in bold in the table
SRC = HERE / "assets" / "fig2_layout.svg"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BUILD / "Fig2.svg"
PT = 25.4 / 72   # matplotlib SVG user units are pt; the figure's are mm

NS = {"": "http://www.w3.org/2000/svg", "inkscape": "http://www.inkscape.org/namespaces/inkscape",
      "sodipodi": "http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd", "xlink": "http://www.w3.org/1999/xlink",
      "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "cc": "http://creativecommons.org/ns#",
      "dc": "http://purl.org/dc/elements/1.1/"}
for k, v in NS.items():
    ET.register_namespace(k, v)
SVG = "{http://www.w3.org/2000/svg}"
INK = "{http://www.inkscape.org/namespaces/inkscape}"
XLINK = "{http://www.w3.org/1999/xlink}href"

# rows c and d/e are moved up by C_SHIFT and DE_SHIFT; rows d/e are laid out at the coordinates below and then
# translated as one group
C_SHIFT, DE_SHIFT = 1.5, 3.0
PAGE_H = 170.0 - DE_SHIFT
ROW_C_Y = 62.0 - C_SHIFT   # top of row c (table ends at 59 mm)
Y_DE = 106.0               # baseline of the d and e panel labels
D_SCALE = 1.15             # d i and d ii enlarged into the space freed by the narrower e iii
E_X = 88.0                 # left edge of e i and e ii
# layout groups moved here: id -> visible top-left in layout page mm (measured in Chrome), new top-left, scale
MOVE = {
    "g564": ((1.7, 126.3), (1.0, Y_DE + 1.0), D_SCALE),                                        # d i
    "g565": ((39.6, 125.9), (1.0 + (39.6 - 1.7) * D_SCALE, Y_DE + 1.0 - 0.4 * D_SCALE), D_SCALE),  # d ii
    # e i, 40.2 x 39.5 mm at E_I_SCALE; raised so the baseline of "Apposition" (4.41 mm below its group top at
    # full size) sits on the baseline of the panel label "e i"
    "g250": ((84.0, 119.1), (E_X, Y_DE - 4.41 * 0.9), 0.9),
}
E_I_SCALE = 0.9           # e i reduced so that the mechanism graph (e ii) under it gets 30 mm
E_I_W, E_I_BOTTOM = 40.2 * E_I_SCALE, Y_DE - 4.41 * E_I_SCALE + 39.5 * E_I_SCALE
E_GRAPH_Y = E_I_BOTTOM + 2.0   # top of the mechanism graph (e ii) under e i
TOP_TEXT = 106.5          # top of "Time (hph)" in d ii and of "Apposition" in e i
# (prefix, file, x mm, y mm, scale): matplotlib panels are in pt, the table SVG is already in page mm
PLACEMENTS = [
    ("fig2a_", PANELS / "fig2a_table.svg", 0.0, 0.0, 1.0),
    ("fig2b_", PANELS / "fig2b_manual_vs_automated_bin01.svg", 132.5, 8.0, PT),
    ("fig2c_", PANELS / "fig2c_row.svg", 0.0, ROW_C_Y, PT),
    ("fig2diii_", PANELS / "fig2diii_cell_counts.svg", 41.75, 150.0, PT),   # y-axis on the time axis of d ii
    # e iv under e iii, level with d iii; starts right of its label "iv", which lines up with "iii" above
    ("fig2eiv_", PANELS / "fig2eiv_height.svg", 132.5, 150.0, PT),
]
# layout content replaced: table (g566), b heatmap (figure_1-4), old Pareto plot (figure_1), d iii (figure_1-7),
# height raster (image1), snapshot panel (g580) and both cell-type legends (g579-7 d, g579 e), plus the bracket labels
REMOVE = {"g566", "figure_1", "figure_1-4", "figure_1-7", "image1", "g580", "g579", "g579-7"}
LABEL_PREFIX = "text1127"
# live text of d ii -> BODY_PT before the D_SCALE enlargement: id prefix -> current size in pt (measured in Chrome)
RESIZE = {"text279-2": 4.0, "text1109-1": 4.36}
BODY_PT = 5.0
# e iii: Molè-model snapshots at 6, 7 and 8 d.p.f. (875 x 700 px), cropped to embryo and gland
E_III_IMAGES = ["image8dbb17694e", "image5f0e858126", "imagec40b8b0648"]
# tight crop around blastocyst (x 219-488 px), gland (442-541 px) and the upper stroma, dropping empty space, so the
# three snapshots are drawn larger (all at the same scale)
E_III_CROP = (205, 140, 555, 620)
# e iii: the snapshots side by side, left to right like the stages in e i, on a rightward time axis
E_III_X, E_III_W, E_III_GAP, E_III_Y = 131.5, 48.5, 0.6, TOP_TEXT
SUB = 2.7   # x offset of a sub-label (i) after its panel letter (mm)
LABELS = [  # (text, x, baseline) in mm
    ("a", 0.0, 5.0), ("b", 132.0, 5.0),
    ("c", 0.0, ROW_C_Y + 1.6), ("i", SUB, ROW_C_Y + 1.6), ("ii", 61.0, ROW_C_Y + 1.6), ("iii", 121.0, ROW_C_Y + 1.6),
    ("d", 0.0, Y_DE), ("i", SUB, Y_DE), ("ii", MOVE["g565"][1][0], Y_DE), ("iii", 37.4, 153.0),
    ("e", E_X - 2.0, Y_DE), ("i", E_X - 2.0 + SUB, Y_DE), ("ii", E_X - 2.0, E_GRAPH_Y + 2.6),
    ("iii", 129.4, Y_DE), ("iv", 129.4, 153.0),
]
LABEL_SIZE = 8 * PT
CELLS_D = [("Proliferative", "#e6b400"), ("Meiotic", "#228b22"), ("Spermatocyte", "#87cefa"),
           ("Sperm", "#1f3fd6"), ("Oocyte", "#d62020"), ("DTC", "#0f9b9b")]   # Fig. 1 CELL_TYPES
# names as in Molè et al. (2026); colours sampled from the snapshots (cream blastocoel fluid left out)
CELLS_E = [("Trophectoderm", "#c59d59"), ("Epiblast", "#68558d"), ("Hypoblast", "#51ada9"), ("EVT", "#bd6d35"),
           ("Epithelium", "#edb5b8"), ("Gland", "#cf7e96"), ("Stroma", "#cb727a")]
LEGEND_PT = 6.0
LEGEND = LEGEND_PT * PT
font = arial()


def cell_legend(parent, x0, y0, columns, gid):
    """Cell-type legend as in Fig. 1 (../Fig1/build.py, cell_legend): a bold title "Cell types" above columns
    of colour discs with labels in a light box, scaled from 5 pt to LEGEND_PT. Left edge at x0, first row centred at y0."""
    k = LEGEND_PT / 5
    r, pitch, gap = 0.55 * k, 2.1 * k, 1.0 * k   # wider column gap than Fig. 1: longer labels here
    g = ET.SubElement(parent, SVG + "g", {"id": gid, "style": "font-family:Arial, Helvetica, sans-serif;fill:#000000"})
    ET.SubElement(g, SVG + "text", {"x": f"{x0:.3f}", "y": f"{y0 - pitch + LEGEND * 0.35:.3f}", "font-weight": "bold",
                                   "font-size": f"{LEGEND:.4f}"}).text = "Cell types"
    x = x0
    for col in columns:
        for i, (lab, colr) in enumerate(col):
            y = y0 + i * pitch
            ET.SubElement(g, SVG + "circle", {"cx": f"{x + r:.3f}", "cy": f"{y:.3f}", "r": f"{r:.3f}", "fill": colr})
            ET.SubElement(g, SVG + "text", {"x": f"{x + 2 * r + 0.5:.3f}", "y": f"{y + LEGEND * 0.35:.3f}",
                                           "font-size": f"{LEGEND:.4f}"}).text = lab
        x += max(font.getlength(l) / 1000 * LEGEND for l, _ in col) + 2 * r + 0.5 + gap
    # box as in Fig. 1 (rounded, light gray 0.5 pt line, translucent white), drawn behind the entries
    top, bottom = y0 - pitch - 0.9 * k, y0 + (max(len(c) for c in columns) - 1) * pitch + 0.8 * k + 0.4
    box = ET.Element(SVG + "rect", {"x": f"{x0 - 0.7:.3f}", "y": f"{top:.3f}", "width": f"{x + 0.3 - (x0 - 0.7):.3f}",
                                    "height": f"{bottom - top:.3f}", "rx": "0.8", "fill": "#ffffff",
                                    "fill-opacity": "0.85", "stroke": "#cccccc", "stroke-width": f"{0.5 * PT:.4f}"})
    g.insert(0, box)


# d i: Atwell et al.'s Fig. 3 raster has a 4-5 pt time axis and stage labels (L3 ... L4/Adult). As in Fig. 1
# (../Fig1/build.py, atwell_output), they are painted out and the axis is redrawn as vector text at the size of the
# d ii labels; the stage labels are left out. Positions are page mm in the enlarged d i (measured on the render).
DI_PAINT = (0.3, 106.3, 10.0, 148.2)               # white box over the raster axis and stage labels
DI_AXIS_X, DI_AXIS_Y = 5.0, (108.9, 147.6)   # 1 mm left of the raster axis: the labels clear the cells
DI_TIMES = [("18.5", 110.2), ("27.5", 115.5), ("32.5", 122.9), ("35.5", 132.8), ("60.5", 143.1)]   # baselines
DI_BARS = [("32 µm", 34.7, 113.4, "middle", (32.6, 111.4, 36.8, 113.0)),     # scale-bar labels: text, x, baseline,
           ("115 µm", 28.1, 129.0, "start", (27.9, 127.28, 32.3, 129.1))]   # anchor, white box over the raster label
DI_PT = BODY_PT * D_SCALE                           # same size as the d ii time labels
TIME_AXIS_LW = 0.75 * PT                            # all time axes in d and e: 0.75 pt line, arrowhead at the end
D_II_AXIS = (48.75, (108.37, 147.6))                # layout hairline of d ii, redrawn on top in the same style


def time_axis(g, x, y0, y1):
    """Downward time axis: line and filled arrowhead ending at y1 (Fig. 1 time_axis, heavier line)."""
    ET.SubElement(g, SVG + "line", {"x1": f"{x:.3f}", "y1": f"{y0:.3f}", "x2": f"{x:.3f}", "y2": f"{y1 - 1.2:.3f}",
                                   "stroke": "#000000", "stroke-width": f"{TIME_AXIS_LW:.4f}"})
    ET.SubElement(g, SVG + "path", {"d": f"M {x - 0.6:.3f},{y1 - 1.4:.3f} L {x + 0.6:.3f},{y1 - 1.4:.3f} "
                                         f"L {x:.3f},{y1:.3f} Z"})


def time_axis_h(g, y, x0, x1):
    """Rightward time axis in the same style (e iii, where time runs left to right as in e i)."""
    ET.SubElement(g, SVG + "line", {"x1": f"{x0:.3f}", "y1": f"{y:.3f}", "x2": f"{x1 - 1.2:.3f}", "y2": f"{y:.3f}",
                                   "stroke": "#000000", "stroke-width": f"{TIME_AXIS_LW:.4f}"})
    ET.SubElement(g, SVG + "path", {"d": f"M {x1 - 1.4:.3f},{y - 0.6:.3f} L {x1 - 1.4:.3f},{y + 0.6:.3f} "
                                         f"L {x1:.3f},{y:.3f} Z"})


def d_i_time_axis(parent):
    g = ET.SubElement(parent, SVG + "g", {"id": "fig2di_axis", INK + "label": "d i time axis",
                                         "style": "font-family:Arial, Helvetica, sans-serif;fill:#000000"})
    size = f"{DI_PT * PT:.4f}"

    def box(x0, y0, x1, y1):
        ET.SubElement(g, SVG + "rect", {"x": f"{x0:.3f}", "y": f"{y0:.3f}", "width": f"{x1 - x0:.3f}",
                                       "height": f"{y1 - y0:.3f}", "fill": "#ffffff"})
    box(*DI_PAINT)
    x, (y0, y1) = DI_AXIS_X, DI_AXIS_Y
    time_axis(g, x, y0, y1)
    time_axis(g, D_II_AXIS[0], *D_II_AXIS[1])
    ET.SubElement(g, SVG + "text", {"x": f"{x - 4.05:.3f}", "y": f"{y0 - 0.75:.3f}", "font-size": size}
                  ).text = "Time (hph)"
    for lab, yb in DI_TIMES:
        ET.SubElement(g, SVG + "text", {"x": f"{x + 0.6:.3f}", "y": f"{yb:.3f}", "font-size": size}).text = lab
    for lab, xt, yb, anchor, white in DI_BARS:
        box(*white)
        ET.SubElement(g, SVG + "text", {"x": f"{xt:.3f}", "y": f"{yb:.3f}", "font-size": size,
                                       "text-anchor": anchor}).text = lab


def scale_font(e, factor):
    for el in e.iter():
        st = el.get("style")
        if st and "font-size" in st:
            el.set("style", re.sub(r"font-size:([\d.]+)px", lambda m: f"font-size:{float(m.group(1)) * factor:.4f}px", st))
        if el.get("font-size"):
            el.set("font-size", f"{float(el.get('font-size')) * factor:.4f}")
        st = el.get("style")
        if st:
            el.set("style", re.sub(r"font-family:[^;]*", "font-family:Arial", st))


def prefixed(root, prefix):
    ids = {e.get("id") for e in root.iter() if e.get("id")}
    ref = re.compile(r"url\(#([^)]+)\)")
    for e in root.iter():
        for k, v in list(e.attrib.items()):
            if k == "id":
                e.set(k, prefix + v)
            elif k == XLINK and v.startswith("#") and v[1:] in ids:
                e.set(k, "#" + prefix + v[1:])
            elif "url(#" in v:
                e.set(k, ref.sub(lambda m: f"url(#{prefix}{m.group(1)})" if m.group(1) in ids else m.group(0), v))
    return root


def panel_group(prefix, path, x, y, scale):
    root = ET.parse(path).getroot()
    g = ET.Element(SVG + "g", {"id": prefix + "panel", INK + "label": path.stem,
                               "transform": f"translate({x:.3f},{y:.3f}) scale({scale:.6f})",
                               "style": "stroke-linejoin:round;stroke-linecap:butt"})
    for child in list(root):
        tag = child.tag.split("}")[-1]
        if tag in ("metadata", "style"):
            continue
        child = copy.deepcopy(child)
        if tag == "defs":
            for s in child.findall(SVG + "style"):
                child.remove(s)
        else:   # drop the white figure background so a panel cannot hide labels next to it
            for patch in child.findall(SVG + "g"):
                if patch.get("id") == "patch_1":
                    child.remove(patch)
        g.append(child)
    print(f"{path.name} at ({x}, {y})")
    return prefixed(g, prefix)


def png_data(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def e_ii(parent, sources):
    """Three cropped snapshots side by side right of e i, on a rightward time axis with the day marks of e i."""
    g = ET.SubElement(parent, SVG + "g", {"id": "fig2eiii_snapshots", INK + "label": "e iii snapshots",
                                         "style": "font-family:Arial, Helvetica, sans-serif;fill:#000000"})
    w = (E_III_W - 2 * E_III_GAP) / 3
    x0, y0, x1, y1 = E_III_CROP
    h = w * (y1 - y0) / (x1 - x0)
    size = f"{DI_PT * PT:.4f}"
    y_text, y_axis = E_III_Y + h + 2.5, E_III_Y + h + 3.8
    for i, (day, img) in enumerate(zip((6, 7, 8), sources)):
        x = E_III_X + i * (w + E_III_GAP)
        ET.SubElement(g, SVG + "image", {"x": f"{x:.3f}", "y": f"{E_III_Y:.3f}", "width": f"{w:.3f}",
                                        "height": f"{h:.3f}", "preserveAspectRatio": "none",
                                        XLINK: png_data(img.crop(E_III_CROP))})
        ET.SubElement(g, SVG + "circle", {"cx": f"{x + w / 2:.3f}", "cy": f"{y_axis:.3f}", "r": "0.55"})
        ET.SubElement(g, SVG + "text", {"x": f"{x + w / 2:.3f}", "y": f"{y_text:.3f}", "text-anchor": "middle",
                                       "font-size": size}).text = f"{day} d.p.f."
    time_axis_h(g, y_axis, E_III_X, E_III_X + E_III_W)
    return y_axis

tree = ET.parse(SRC)
root = tree.getroot()
parents = {c: p for p in root.iter() for c in p}
by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
snapshots = []
for gid in E_III_IMAGES:   # read before g580 (which holds them) is removed
    href = by_id[gid].get(XLINK)
    snapshots.append(Image.open(io.BytesIO(base64.b64decode(re.sub(r"^data:image/\w+;base64,\s*", "", href))))
                     .convert("RGB"))
for e in list(root.iter()):
    if e.get("id") in REMOVE or (e.tag == SVG + "text" and (e.get("id") or "").startswith(LABEL_PREFIX)):
        parents[e].remove(e)
for e in list(root.iter(SVG + "text")):
    if (e.get("id") or "").startswith(tuple(RESIZE)):
        size = next(v for k, v in RESIZE.items() if e.get("id").startswith(k))
        scale_font(e, BODY_PT / size)
        parents[e].remove(e)   # drawn after their sibling images, so the snapshots do not cover them
        parents[e].append(e)
layer = ET.SubElement(root, SVG + "g", {"id": "fig2_panels", INK + "groupmode": "layer",
                                        INK + "label": "Fig. 2 (a, b, c, d, e; legends, labels)"})
for gid, ((vx, vy), (nx, ny), s) in MOVE.items():
    e = by_id[gid]
    outer = parents[e].get("transform", "")   # g1-7: layout group of rows d and e
    parents[e].remove(e)
    wrap = ET.SubElement(layer, SVG + "g", {"id": f"{gid}_moved", "transform":
                                            f"translate({nx:.3f},{ny:.3f}) scale({s}) translate({-vx},{-vy}) {outer}"})
    wrap.append(e)
    print(f"{gid}: ({vx}, {vy}) -> ({nx:.1f}, {ny:.1f}) x {s}")
for placement in PLACEMENTS:
    layer.append(panel_group(*placement))
e_ii_axis = e_ii(layer, snapshots)
# legends left-aligned with the images above them: d i rows start at 10.2 mm, the e i drawing at 90.8 mm
cell_legend(layer, 10.2, 154.5, [CELLS_D[:3], CELLS_D[3:]], "fig2d_cell_legend")
# e iii legend directly under the e iii time axis, so it reads as part of e iii; embryo | host tissue
k_leg = LEGEND_PT / 5
# centred on the 7 d.p.f. mark (middle snapshot)
cols_e = [CELLS_E[:4], CELLS_E[4:]]
w_e = sum(max(font.getlength(l) / 1000 * LEGEND for l, _ in c) + 2 * 0.55 * k_leg + 0.5 + 1.0 * k_leg for c in cols_e)
x_mid = E_III_X + E_III_W / 2
cell_legend(layer, x_mid - (w_e - 0.4) / 2, e_ii_axis + 2.5 + 2.1 * k_leg + 0.9 * k_leg, cols_e, "fig2e_cell_legend")
d_i_time_axis(layer)
mechanism_graph.draw(layer, E_X + 0.3, E_GRAPH_Y, E_GRAPH_Y + 25.3)
labels = ET.SubElement(layer, SVG + "g", {"id": "fig2_labels", INK + "label": "panel labels",
                                          "style": f"font-family:Arial, Helvetica, sans-serif;font-weight:bold;"
                                                   f"font-size:{LABEL_SIZE:.4f}px;fill:#000000"})
for i, (s, x, y) in enumerate(LABELS):
    ET.SubElement(labels, SVG + "text", {"id": f"fig2_label_{i}", "x": f"{x:.3f}",
                                         "y": f"{y - (DE_SHIFT if y > 100 else 0):.3f}"}).text = s
# rows d and e: everything placed below row c moves up by DE_SHIFT
de = ET.Element(SVG + "g", {"id": "fig2_rows_de", "transform": f"translate(0,{-DE_SHIFT})"})
for child in list(layer):
    cid = child.get("id") or ""
    if cid.endswith("_moved") or cid.startswith(("fig2diii_", "fig2eiv_", "fig2eiii", "fig2d_", "fig2e_", "fig2di_")):
        layer.remove(child)
        de.append(child)
layer.insert(0, de)
# d ii time label 39.5 -> 39.4 hph, as in Fig. 1 (the snapshot is the 39.4 hph lattice checkpoint)
for e in root.iter(SVG + "text"):
    for el in e.iter():
        if el.text and el.text.strip() == "39.5" and (e.get("id") or "").startswith("text279"):
            el.text = el.text.replace("39.5", "39.4")
root.set("height", f"{PAGE_H}mm")
root.set("viewBox", f"0 0 180 {PAGE_H}")
for p in root.iter(INK + "page"):
    if p.get("id") == "page1":
        p.set("height", str(PAGE_H))
root.set("{http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd}docname", OUT.name)
tree.write(OUT, encoding="UTF-8", xml_declaration=True)
print("wrote", OUT)
