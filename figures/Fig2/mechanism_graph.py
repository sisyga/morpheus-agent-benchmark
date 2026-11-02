"""Fig. 2e ii: the mechanisms of the agent's Molè model as a small graph, drawn into an ElementTree SVG group.

Every node and edge is read off the model of the run shown in bold in Fig. 2a (GPT-6.1 Sol, Skill, repetition 3,
figures/Supplementary/Supp_Fig_13_Mole2026/data/20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/
model.xml; the same fields appear in its model_graph.dot). EDGES lists the XML element behind each edge.
Cell types are drawn as pills in the e iii legend colours, the diffusing fields (Global/Field) as white boxes.
Simplified: only the interactions listed in EDGES are drawn (see NOT_DRAWN).
"""
import xml.etree.ElementTree as ET

from paths import arial

SVG = "{http://www.w3.org/2000/svg}"
PT = 25.4 / 72
CELL_PT, FIELD_PT, KEY_PT = 6.0, 5.0, 5.0
LW = 0.5 * PT
GREY = "#808080"
_font = arial()

# key: (label, kind, colour, x centre, y centre) in mm from the graph origin; cells: (fill colour)
CELLS = {
    "te": ("Trophectoderm", "#c59d59", 8.0, 2.0),
    "evt": ("EVT", "#bd6d35", 28.0, 2.0),
    "gland": ("Gland", "#cf7e96", 4.6, 21.5),
    "epi": ("Epithelium", "#edb5b8", 15.0, 21.5),
    "stroma": ("Stroma", "#cb727a", 26.6, 21.5),
}
FIELDS = {   # Global/Field symbols, shown with readable names
    "gland_signal": ("Gland signal", 5.6, 9.5),
    "FGF2": ("FGF2", 17.2, 9.5),
    "host_support": ("Support", 24.4, 12.8),
    "MMP": ("MMP", 35.8, 9.5),
    "PROS1": ("PROS1", 31.4, 15.8),
    "ECM": ("ECM", 36.0, 21.5),
}
# (source, target, kind, XML evidence); kinds: make = secretion (cell -> field), act = field acts on a cell (attraction,
# activation or growth), become = change of cell type, degrade = field reaction removing ECM, adhere = adhesion
EDGES = [
    ("gland", "gland_signal", "make", "CellType gland: Constant q_gland_signal=0.8"),
    ("gland_signal", "te", "act", "CellType trophectoderm: Chemotaxis field=gland_signal"),
    ("te", "evt", "become", "ChangeCellType -> invasive_trophoblast: contact_hours >= 24, contact_maturation > 0.75, "
                            "fgf_sensed > 0.005"),
    ("FGF2", ("te", "evt"), "act", "trophectoderm Mapper FGF2 -> fgf_sensed, in the ChangeCellType condition"),
    ("FGF2", "evt", "act", "CellType invasive_trophoblast: Chemotaxis field=FGF2"),
    ("stroma", "FGF2", "make", "CellType stroma: Constant q_FGF2=0.2 (epithelium, gland: 0.025)"),
    ("epi", "FGF2", "make", "CellType epithelium: Constant q_FGF2=0.025"),
    ("evt", "PROS1", "make", "CellType invasive_trophoblast: Function q_PROS1=0.35"),
    ("PROS1", "stroma", "act", "stroma: Mapper PROS1 -> pros_sensed -> axl_drive -> AXL_state"),
    ("stroma", "host_support", "make", "stroma: Function q_support=0.3*AXL_state"),
    ("host_support", "evt", "act", "invasive_trophoblast: Chemotaxis field=host_support; growth term with "
                                   "support_sensed"),
    ("evt", "MMP", "make", "CellType invasive_trophoblast: Function q_MMP=0.8"),
    ("MMP", "ECM", "degrade", "Global/System DiffEqn ECM: -1.2*MMP*ECM"),
    ("te", "epi", "adhere", "CPM Contact trophectoderm-epithelium (and -gland): HeterophilicAdhesion EFNA1-EPHA2, "
                            "NECTIN3-CADM1"),
]
NOT_DRAWN = ["EVT also chemotaxes up gland_signal and adheres to epithelium/gland (weaker)",
             "gland secretes FGF2 (0.025)", "EVT is repelled by ECM (Haptotaxis -matrix_penalty); stroma follows ECM",
             "ECM anchors epithelium, gland and stroma (DirectedMotion)", "MMP softens epithelial junctions"]
KEY = [("make", "secretes"), ("act", "acts on"), ("become", "becomes"), ("degrade", "degrades"),
       ("adhere", "adhesion")]
HGT = {"cell": 3.4, "field": 2.6}


def _w(text, pt):
    return _font.getlength(text) / 1000 * pt * PT


def draw(parent, x0, y0, key_y):
    g = ET.SubElement(parent, SVG + "g", {"id": "fig2e_graph", "style": "font-family:Arial, Helvetica, sans-serif"})
    boxes = {}
    for k, (lab, col, cx, cy) in CELLS.items():
        w, h = _w(lab, CELL_PT) + 2.0, HGT["cell"]
        boxes[k] = (x0 + cx - w / 2, y0 + cy - h / 2, x0 + cx + w / 2, y0 + cy + h / 2)
    for k, (lab, cx, cy) in FIELDS.items():
        w, h = _w(lab, FIELD_PT) + 1.4, HGT["field"]
        boxes[k] = (x0 + cx - w / 2, y0 + cy - h / 2, x0 + cx + w / 2, y0 + cy + h / 2)

    def anchor(k, towards):
        """Point on the border of box k facing the point towards (box centre to point, clipped)."""
        x1, y1, x2, y2 = boxes[k]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        dx, dy = towards[0] - cx, towards[1] - cy
        sx = (x2 - x1) / 2 / abs(dx) if dx else float("inf")
        sy = (y2 - y1) / 2 / abs(dy) if dy else float("inf")
        s = min(sx, sy)
        return cx + dx * s, cy + dy * s

    def centre(k):
        x1, y1, x2, y2 = boxes[k]
        return (x1 + x2) / 2, (y1 + y2) / 2

    def head(x, y, ux, uy, filled=True, colour="#000000", size=1.0):
        px, py = -uy, ux
        bx, by = x - ux * 1.1 * size, y - uy * 1.1 * size
        pts = f"M {bx + px * 0.5 * size:.3f},{by + py * 0.5 * size:.3f} L {x:.3f},{y:.3f} " \
              f"L {bx - px * 0.5 * size:.3f},{by - py * 0.5 * size:.3f}"
        ET.SubElement(g, SVG + "path", {"d": pts + " Z",
                                       "fill": colour if filled else "#ffffff", "stroke": colour,
                                       "stroke-width": f"{LW:.4f}", "stroke-linejoin": "miter"})

    def line(p, q, kind):
        (x1, y1), (x2, y2) = p, q
        dx, dy = x2 - x1, y2 - y1
        n = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / n, dy / n
        colour = GREY if kind == "make" else "#000000"
        width = {"become": 0.9 * PT}.get(kind, LW)
        back = {"make": 1.0, "act": 1.1, "become": 1.6, "degrade": 0.0, "adhere": 0.0}[kind]
        attrs = {"x1": f"{x1:.3f}", "y1": f"{y1:.3f}", "x2": f"{x2 - ux * back:.3f}", "y2": f"{y2 - uy * back:.3f}",
                 "stroke": colour, "stroke-width": f"{width:.4f}"}
        if kind == "adhere":
            attrs["stroke-dasharray"] = f"{0.25:.2f},{0.45:.2f}"
            attrs["stroke-width"] = f"{0.8 * PT:.4f}"
            attrs["stroke-linecap"] = "round"
        ET.SubElement(g, SVG + "line", attrs)
        if kind == "make":
            head(x2, y2, ux, uy, filled=True, colour=GREY, size=0.8)
        elif kind == "act":
            head(x2, y2, ux, uy)
        elif kind == "become":
            head(x2, y2, ux, uy, filled=False, size=1.45)
        elif kind == "degrade":
            px, py = -uy, ux
            ET.SubElement(g, SVG + "line", {"x1": f"{x2 + px * 0.75:.3f}", "y1": f"{y2 + py * 0.75:.3f}",
                                           "x2": f"{x2 - px * 0.75:.3f}", "y2": f"{y2 - py * 0.75:.3f}",
                                           "stroke": "#000000", "stroke-width": f"{0.7 * PT:.4f}"})

    for src, dst, kind, _ in EDGES:
        if isinstance(dst, tuple):   # acts on the change of cell type: arrow ends on the middle of that edge
            a, b = (anchor(dst[0], centre(dst[1])), anchor(dst[1], centre(dst[0])))
            target = ((a[0] + b[0]) / 2 - 0.4, (a[1] + b[1]) / 2 + 0.25)
            line(anchor(src, target), target, kind)
            continue
        p = anchor(src, centre(dst))
        q = anchor(dst, centre(src))
        line(p, q, kind)
    # nodes on top of the edges
    for k, (lab, col, cx, cy) in CELLS.items():
        x1, y1, x2, y2 = boxes[k]
        ET.SubElement(g, SVG + "rect", {"x": f"{x1:.3f}", "y": f"{y1:.3f}", "width": f"{x2 - x1:.3f}",
                                       "height": f"{y2 - y1:.3f}", "rx": f"{(y2 - y1) / 2:.3f}", "fill": col,
                                       "fill-opacity": "0.45", "stroke": col, "stroke-width": f"{LW:.4f}"})
        ET.SubElement(g, SVG + "text", {"x": f"{x0 + cx:.3f}", "y": f"{y0 + cy + CELL_PT * PT * 0.35:.3f}",
                                       "text-anchor": "middle", "font-size": f"{CELL_PT * PT:.4f}"}).text = lab
    for k, (lab, cx, cy) in FIELDS.items():
        x1, y1, x2, y2 = boxes[k]
        ET.SubElement(g, SVG + "rect", {"x": f"{x1:.3f}", "y": f"{y1:.3f}", "width": f"{x2 - x1:.3f}",
                                       "height": f"{y2 - y1:.3f}", "rx": "0.4", "fill": "#ffffff",
                                       "stroke": GREY, "stroke-width": f"{LW:.4f}"})
        ET.SubElement(g, SVG + "text", {"x": f"{x0 + cx:.3f}", "y": f"{y0 + cy + FIELD_PT * PT * 0.35:.3f}",
                                       "text-anchor": "middle", "font-size": f"{FIELD_PT * PT:.4f}"}).text = lab
    # key: sample edges with their meaning, two rows
    for row, items in enumerate((KEY[:3], KEY[3:])):
        x, y = x0, key_y + row * 2.6
        for kind, lab in items:
            line((x, y), (x + 3.2, y), kind)
            ET.SubElement(g, SVG + "text", {"x": f"{x + 3.7:.3f}", "y": f"{y + KEY_PT * PT * 0.35:.3f}",
                                           "font-size": f"{KEY_PT * PT:.4f}"}).text = lab
            x += 3.7 + _w(lab, KEY_PT) + 2.0
    return boxes
