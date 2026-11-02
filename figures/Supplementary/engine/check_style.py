"""Style check of the built supplementary figures (Nature Methods guide, as Fig. 1 and Fig. 2).

    python figures/Supplementary/engine/check_style.py <output folder>

Parses every figure and model-graph page SVG under the folder and lists each text below 5 pt or above 8 pt,
bold text other than panel letters (a-d) and sub-panel numerals (i-iv), text whose fill is not black, square
brackets in text, pages that are not 180 x 170 mm, and (passed in by build_all.py) legends that cover data
(figure.legend_overlaps). Text inside the embedded Graphviz graphs (nested
<svg>) and inside raster images cannot be restyled and is not checked; build_all.py lists it per paper as
exempt. Writes style_check.md into the folder and never raises on findings.
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

NS = "{http://www.w3.org/2000/svg}"
PAGE_MM = (180.0, 170.0)
FS_MIN, FS_MAX = 5.0, 8.0
BOLD_OK = {"a", "b", "c", "d", "i", "ii", "iii", "iv"}
BLACK = {"#000000", "#000", "black", "rgb(0,0,0)"}


def _style(el):
    out = {}
    for part in (el.get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    for k in ("font-size", "font-weight", "fill"):
        if el.get(k) is not None:
            out.setdefault(k, el.get(k))
    return out


def _pt(v):
    m = re.match(r"([\d.]+)\s*(px|pt)?", v or "")
    return float(m.group(1)) if m else None  # matplotlib writes the SVG in pt user units (1px = 1pt)


def _mm(v):
    m = re.match(r"([\d.]+)\s*(pt|mm|px)?", v or "")
    if not m:
        return None
    x, u = float(m.group(1)), m.group(2) or "px"
    return {"pt": x * 25.4 / 72, "px": x * 25.4 / 72, "mm": x}[u]


def check_svg(path):
    """Findings (issue, text, detail) of one SVG."""
    root = ET.parse(path).getroot()
    found = []
    w, h = _mm(root.get("width")), _mm(root.get("height"))
    if w is None or h is None or abs(w - PAGE_MM[0]) > 0.5 or abs(h - PAGE_MM[1]) > 0.5:
        found.append(("page size", "", f"{w:.1f} x {h:.1f} mm" if w and h else "no size"))

    def walk(el, inherited, nested):
        st = _style(el)
        ctx = dict(inherited)
        ctx.update({k: v for k, v in st.items() if k in ("fill", "font-weight", "font-size")})
        if el.tag == NS + "svg" and el is not root:
            nested = True
        if el.tag == NS + "text" and not nested:
            check_text(el, ctx)
            return
        for c in el:
            walk(c, ctx, nested)

    def check_text(el, ctx):
        parts = [(el, ctx)]
        for t in el.iter(NS + "tspan"):
            c = dict(ctx)
            c.update({k: v for k, v in _style(t).items() if k in ("fill", "font-weight", "font-size")})
            parts.append((t, c))
        s = "".join(el.itertext()).strip()
        if not s:
            return
        sizes = {_pt(c.get("font-size")) for e, c in parts if (e.text or "").strip()} - {None}
        bold = any(c.get("font-weight", "").lower() in ("bold", "700", "800", "900")
                   for e, c in parts if (e.text or "").strip())
        fills = {c.get("fill", "#000000").lower().replace(" ", "") for e, c in parts if (e.text or "").strip()}
        for z in sorted(sizes):
            if z < FS_MIN - 0.01:
                found.append(("below 5 pt", s, f"{z:g} pt"))
            elif z > FS_MAX + 0.01:
                found.append(("above 8 pt", s, f"{z:g} pt"))
        if bold and s not in BOLD_OK:
            found.append(("bold", s, ", ".join(f"{z:g} pt" for z in sorted(sizes))))
        for f in sorted(fills - BLACK):
            found.append(("not black", s, f))
        if "[" in s or "]" in s:
            found.append(("square bracket", s, ""))

    walk(root, {}, False)
    return found


def svg_texts(path):
    """The set of our own text strings in an SVG (text inside the embedded Graphviz graphs not included)."""
    root = ET.parse(path).getroot()
    out = set()

    def walk(el, nested):
        if el.tag == NS + "svg" and el is not root:
            nested = True
        if el.tag == NS + "text":
            s = " ".join("".join(el.itertext()).split())
            if s and not nested:
                out.add(s)
            return
        for c in el:
            walk(c, nested)

    walk(root, False)
    return out


def text_diff(out, prev):
    """Per SVG of out (relative path): (strings that disappeared, strings that appeared) compared with the SVG of
    the same name in the previous build folder prev; files only in one of the two are reported as such."""
    res = {}
    new = {os.path.relpath(p, out).replace("\\", "/"): p for p in svgs(out)}
    old = {os.path.relpath(p, prev).replace("\\", "/"): p for p in svgs(prev)}
    built = {r.split("/")[0] for r in new}  # a partial build (--only) is compared for its own figures only
    for rel in sorted(set(new) | set(old)):
        if rel not in old:
            res[rel] = ("new file", None)
        elif rel not in new:
            if rel.split("/")[0] in built or rel.startswith("Supp_model_graphs/"):
                res[rel] = ("file missing", None)
        else:
            a, b = svg_texts(old[rel]), svg_texts(new[rel])
            if a != b:
                res[rel] = (sorted(a - b), sorted(b - a))
    return res


def text_diff_md(out, prev):
    """Markdown section of text_diff."""
    d = text_diff(out, prev)
    lines = [f"\n## Text changes vs {prev}\n",
             "Text strings of each SVG compared with the previous build (a regression check: a vanished label "
             "shows up here; not counted as findings).\n"]
    if not d:
        lines.append("No changes.")
    for rel, (gone, came) in d.items():
        if came is None:
            lines.append(f"- **{rel}**: {gone}")
            continue
        lines.append(f"- **{rel}**")
        if gone:
            lines.append("  - disappeared: " + "; ".join(f"`{s}`" for s in gone))
        if came:
            lines.append("  - appeared: " + "; ".join(f"`{s}`" for s in came))
    return "\n".join(lines) + "\n", d


def svgs(out):
    """Figure and model-graph page SVGs; the per-paper *_model_graph.svg files are pure Graphviz output."""
    figs = sorted(glob.glob(os.path.join(out, "*", "[0-9][0-9]_*.svg")))
    figs = [f for f in figs if not f.endswith("_model_graph.svg")]
    pages = sorted(glob.glob(os.path.join(out, "Supp_model_graphs", "Supp_model_graphs_p*.svg")))
    return figs + pages


def main(out, exempt=None, legend_hits=None, graph_text=None, compare_to=None):
    """exempt: {paper: [text that is not checked]}; legend_hits: {paper: [(legend, number of data elements under
    it)]} from the build; graph_text: {paper: [Graphviz label sizes]}; compare_to: previous build folder for the
    text regression check. The model-graph pages are SI zoomable vector graphs at A4 landscape: their page size is
    listed, not counted. Returns the number of findings per issue."""
    rows, counts, graph_pages = [], {}, []
    for p in svgs(out):
        rel = os.path.relpath(p, out).replace("\\", "/")
        for issue, s, det in check_svg(p):
            if issue == "page size" and rel.startswith("Supp_model_graphs/"):
                graph_pages.append((rel, det))
                continue
            rows.append((rel, issue, s, det))
            counts[issue] = counts.get(issue, 0) + 1
    for key, hits in (legend_hits or {}).items():
        for desc, k in hits:
            rows.append((f"{key}/{key}.svg", "legend overlaps data", desc, f"{k} data element(s)"))
            counts["legend overlaps data"] = counts.get("legend overlaps data", 0) + 1
    n_files = len(svgs(out))
    with open(os.path.join(out, "style_check.md"), "w", encoding="utf-8") as f:
        f.write("# Style check\n\n"
                f"Generated by figures/Supplementary/engine/check_style.py over {n_files} SVG files (figures and model-graph "
                "pages). Checked: text below 5 pt or above 8 pt, bold text other than panel letters and sub-panel "
                "numerals, text fill other than black, square brackets, page size other than 180 x 170 mm (figures), legends that "
                "cover data (line segments, markers or points inside the legend box plus 1 pt; from the build). "
                "Text inside the embedded Graphviz graphs and inside raster images is not checked (see the exempt "
                "sections).\n\n")
        f.write("## Summary\n\n| issue | count |\n|---|---|\n")
        for k in ("below 5 pt", "above 8 pt", "bold", "not black", "square bracket", "page size",
                  "legend overlaps data"):
            f.write(f"| {k} | {counts.get(k, 0)} |\n")
        f.write("\n## Findings\n\n")
        if rows:
            f.write("| file | issue | text | detail |\n|---|---|---|---|\n")
            for r in rows:
                f.write("| " + " | ".join(x.replace("|", "\\|").replace("\n", " ") for x in r) + " |\n")
        else:
            f.write("None.\n")
        if graph_pages or graph_text:
            f.write("\n## SI zoomable vector graphs (exempt)\n\n"
                    "Model graphs are vector graphics with live Arial text, to be zoomed in the SI PDF; their label "
                    "sizes and the A4 landscape model-graph pages are not counted as findings.\n\n")
            for rel, det in graph_pages:
                f.write(f"- {rel}: {det}\n")
            for k, items in (graph_text or {}).items():
                f.write(f"- **{k}**: " + "; ".join(items) + "\n")
        if exempt:
            f.write("\n## Exempt (not restyled: text baked into raster images)\n\n")
            for k, items in exempt.items():
                f.write(f"- **{k}**: " + "; ".join(items) + "\n")
        if compare_to:
            md, d = text_diff_md(out, compare_to)
            f.write(md)
            print(f"text changes vs {compare_to}: {len(d)} file(s) changed")
    total = sum(counts.values())
    print(f"style check: {total} finding(s) in {n_files} SVG files"
          + (" (" + ", ".join(f"{k}: {v}" for k, v in counts.items()) + ")" if counts else "")
          + f"; table in {os.path.join(out, 'style_check.md')}")
    return counts


if __name__ == "__main__":
    # check_style.py <out> [--compare-to <previous build>] [--diff-only: print the text diff, write nothing]
    a = sys.argv[1:]
    prev = a[a.index("--compare-to") + 1] if "--compare-to" in a else None
    if "--diff-only" in a:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text_diff_md(a[0], prev)[0])
    else:
        main(a[0], compare_to=prev)
