"""Reza et al. (2025): agent-only zone cell numbers and mean GST, GS, glutamine proxies per zone vs time."""
from panels.common import axes, legend, split

# panel a (the preprint's Fig. 1a, f and 4g-i) 1.55x as wide as with A_SHARE 0.55 and D_HEIGHT 46; tested:
# 1.7x (A_SHARE 0.8, D_HEIGHT 34) leaves panel d too short; the y labels are two lines so they clear "ii"-"iv"
A_SHARE = 0.75
D_HEIGHT = 36.0
# zone colours of the run's cell.type ColorMap, as in its frames (panel b): Z1 red, Z3 green, lumen light grey
C_Z1, C_Z3, C_LUMEN = "#df5b4c", "#56b966", "#d3d3d3"
B_LEGEND = [(C_Z1, "Z1-HLO (mCherry)"), (C_Z3, "Z3-HLO (GFP)"), (C_LUMEN, "Lumen")]
B_CAPTION = ("the top-left sub-plot (cells coloured by cell.type), "
             "cropped to the organoids with a 10-pixel margin, the same crop for all three frames (pixels 50–279 of "
             "400 in x, 73–203 of 268 in y; the organoids span pixels 60–269 and 83–193; the whole lattice is "
             "360 × 260 sites, 2 µm per site) with a grey outline; the cropped Gnuplot colour bar (0–3) only spanned the "
             "cell.type index (0 medium, 1 Lumen, 2 Z1, 3 Z3), which the key below the frames replaces. Frames at 0, "
             "3 and 6 days of "
             "elapsed model time (time 0, 4320 and 8640 min; t = 0 is co-culture day 1 in the model)")
TYPES = {2: ("Z1-HLO", C_Z1), 3: ("Z3-HLO", C_Z3)}  # cell.type index in cells.csv (model.xml order)
CAPTION = ("Agent-only quantification (the paper's Fig. 4g–i report enzyme activity over a 20–60 min assay and an "
           "end-point glutamine measurement per organoid type, so no like-for-like overlay exists; compare "
           "qualitatively with a). Time is elapsed model time in days (elapsed_days = time/1440 min). "
           "(i) Current number of Z1-HLO and Z3-HLO cells (counts.csv: celltype.Z1.size, celltype.Z3.size; "
           "logged every 180 min). (ii–iv) Mean over the cells of each zone at each logged time (cells.csv) of the "
           "model's normalised proxies, in model units: (ii) GST capacity, gst = 0.04 + 0.16·lineage + "
           "6·interzone; (iii) GS capacity, gs = 0.02 + 0.98·hif1a; (iv) glutamine production proxy, which "
           "relaxes (τ = 1440 min) to gs/(0.25 + urea_capacity + gs). These are dimensionless per-cell model "
           "variables ('normalized diagnostic proxies, not absolute experimental units', model.xml), not the "
           "measured quantities of a: GST and GS capacity stand for the enzyme activities that the paper measures "
           "for each organoid type in mU/mg over a 20–60 min assay (GST activity, Fig. 4g; GS activity, "
           "Fig. 4h), and the "
           "glutamine proxy for the glutamine produced (nmol per CTG 10^6, Fig. 4i), so only the ordering of "
           "Z1 and Z3 cells can be compared. Colours as in b.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "alreza2025",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Multi-zonal liver organoids (Al Reza *et al.*, 2025).",
    "a": "Generation of zone 1 and zone 3 liver organoids and their fusion (Fig. 1a, f), and the GST and GS "
         "activities and glutamine production measured for each organoid type (Fig. 4g–i), from the preprint of Al Reza *et al.*",
    "b": "Two organoids of Z1-HLO and Z3-HLO cells around lumens, which fuse over time (key below).",
    "c": "{graph}",
    "d": "**i**, Number of Z1-HLO and Z3-HLO cells. **ii**–**iv**, Mean "
         "over the cells of each zone of the model's GST capacity (**ii**), GS capacity (**iii**) and glutamine "
         "production (**iv**). These are dimensionless proxies, so only their ordering between Z1 and Z3 compares "
         "with the measurements of Al Reza *et al.* in **a**.",
    "abbrev": "GS, glutamine synthetase; GST, glutathione S-transferase; HLO, human liver organoid; Z1 and Z3, zones "
              "1 and 3.",
    "license": "The panels in **a** are excerpted (cropped and rearranged, otherwise unaltered) from the preprint of Al Reza *et al.*, available under a CC BY-NC-ND 4.0 license.",
}


def draw(ctx, fig, box):
    n = ctx.csv("counts.csv")
    n = n.loc[:, ~n.columns.duplicated()]
    d = ctx.csv("cells.csv")
    d = d.loc[:, ~d.columns.duplicated()]
    m = d[d["cell.type"].isin(TYPES)].groupby(["elapsed_days", "cell.type"])[["gst", "gs", "glutamine"]].mean()
    bs = split(box, [1, 1, 1, 1], gap=7)
    ax = axes(fig, bs[0], label="i")
    ax.plot(n.elapsed_days, n["celltype.Z1.size"], color=C_Z1, label="Z1-HLO")
    ax.plot(n.elapsed_days, n["celltype.Z3.size"], color=C_Z3, label="Z3-HLO")
    ax.set(xlabel="Time (days)", ylabel="Number of cells", xlim=(0, n.elapsed_days.max()), ylim=(0, None))
    legend(ax, loc="lower right")
    for b, col, lab, sub in zip(bs[1:], ["gst", "gs", "glutamine"],
                                ["GST capacity", "GS capacity", "Glutamine proxy"],
                                ["ii", "iii", "iv"]):
        ax = axes(fig, b, label=sub)
        for t, (name, c) in TYPES.items():
            s = m[col].xs(t, level="cell.type")
            ax.plot(s.index, s.values, color=c, label=name)
        ax.set(xlabel="Time (days)", ylabel=f"{lab}\n(model units)", xlim=(0, s.index.max()), ylim=(0, None))
