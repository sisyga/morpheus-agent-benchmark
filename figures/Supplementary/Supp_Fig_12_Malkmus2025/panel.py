"""Malkmus et al. (2025): agent-only quantification of the six-species pattern: final profiles along a line
through the domain centre, pattern amplitude vs time and a Sox9 kymograph. Panel b shows the frames as one
column per species (malkmus_frames.py) with species and time labels and one colour key drawn here."""
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import config
import malkmus_frames
import style
from figure import mm_axes, text
from malkmus_frames import SPECIES, VMAX
from panels.common import axes, legend, split

b_frames = malkmus_frames.columns  # panel b: species columns instead of the 3 x 2 Gnuplotter frames

DX_UM = 10.0  # Lattice NodeLength (dx_um = 10 µm per node)
CX = 54.5  # domain centre in lattice nodes: (l.x-54.5)^2+(l.y-54.5)^2 <= 50^2
ROW = 54  # lattice row of the profile line (l.y = 54, 5 µm from the centre; rows 54 and 55 are equally central)
ACT = "Activity (steady state = 1)"
# panel c: the reduced graph needs 39.4 mm at the 6.5 pt label cap; a slot of that height and a taller panel d
# leave no blank strip at the foot of the page (default: 46 mm slot sized for the full graph)
GRAPH_MAX_H = 39.5
D_HEIGHT = 72.0
# panel d line order: the in-phase pairs (Sox9, SULF1), (WNT2, beta_cat) and the shallow pair (Sfrp2, BMP2), so the
# three-column legend shows one pair per column
ORDER = [SPECIES[i] for i in (5, 4, 1, 2, 0, 3)]


def cmap(colour):
    return LinearSegmentedColormap.from_list("ramp", ["#000000", colour])


B_KEY_H = 6.0  # mm below the frames: the shared colour key
AB_GAP = 8.0  # mm between panels a and b (side by side): room for the frame times left of the rows
B_CAPTION = ("each Gnuplotter frame holds six field plots (Sfrp2, WNT2, β-catenin / BMP2, SULF1, Sox9; the "
             "agent's normalised activities); the panel shows them as one column per species, rows at 0, 18 and "
             "36 h after E10.5, each plot cropped to the circular domain (diameter 1000 µm, 1 node = 10 µm) plus "
             "about one node of background (pixels 13–370 of each 385-pixel field image), so the Gnuplot "
             "titles, colour bars and the time stamp are cropped off and replaced by the species labels, the time "
             "labels and one colour key. All six ColorMaps of the run are linear ramps from black (activity 0) to "
             "one colour (activity 2) on the same fixed range 0–2 (adaptive-range=\"false\"). The key shows the six "
             "ramps stacked in column order; 1 is the uniform steady state of the model, "
             "the lattice outside the domain (value 0, black in the run's frames) is drawn white")
CAPTION = ("Agent-only quantification from fields_raw.csv (Logger every 3 h, all {nodes} lattice nodes of the "
           "domain; activities normalised so that the uniform steady state is 1, as defined in the agent's "
           "model.xml; time in hours after E10.5; 1 node = 10 µm). (i) Activity of the six species at 36 h along "
           "the lattice row through the domain centre (l.y = 54; the centre is at 54.5), position relative to the "
           "centre; the in-phase pairs share a legend column, with the follower dashed (SULF1 follows Sox9, "
           "β-catenin follows WNT2; Sfrp2 and BMP2 vary least). (ii) Pattern amplitude: standard deviation of "
           "each species' activity over all domain nodes vs time (log scale), colours as in (i); the ±1 % uniform random "
           "initial perturbation (s.d. {sd0}) first decays (minimum at 3 h), then grows about threefold per 3 h "
           "from 6 to 15 h and levels off after about 24 h (s.d. at 36 h: Sox9 {sdsox9}, WNT2 {sdwnt2}). "
           "(iii) Kymograph of Sox9 activity along the line of (i), one row per logged time (every 3 h), in the "
           "colour ramp of b (black at 0 to the Sox9 colour at 2); the stripes appear between 15 and 21 h, and from "
           "18 to 36 h the Sox9 minima along the line shift by at most 40 µm.")


# Publication legend (legend.py): keys are the panel letters as printed; legend.py prepends the run sentence to the
# frames panel and fills {graph} and the {name} fields of ctx.fmt.
LEGEND = {
    "cite": "malkmus2025",  # bib key (morpheusai_supp.bib) cited after every mention of the authors
    "title": "Digit–interdigit patterning in the mouse limb bud (Malkmus *et al.*, 2025).",
    "a": "*Sox9* with *Sulf1* (top) and *Sfrp2* with *Sulf1* (bottom) in wild-type forelimb buds from 12 to 36 h "
         "after E10.5 (adapted from Fig. 5A, C of Malkmus *et al.*).",
    "b": "Activities of the six species on the circular domain, one column per species, starting from the uniform "
         "steady state with a small random perturbation. Activities are normalized so that the steady state is 1; "
         "each color ramp runs from black at 0 to the species color at 2 (key below).",
    "c": "{graph}",
    "d": "**i**, Activities at the final time along a line through the "
         "domain center. Dashed lines mark species that follow another in phase (SULF1 follows Sox9, β-catenin "
         "follows WNT2). **ii**, Spatial standard deviation of each species over time (log scale), colored as in "
         "**i**. The initial perturbation first decays, then grows exponentially and levels off. **iii**, Sox9 "
         "activity along the line in **i** over time (kymograph); the stripes form and then stay in place.",
    "abbrev": "E10.5, embryonic day 10.5.",
    "license": "Material from Malkmus *et al.* is adapted under a CC BY 4.0 license.",
}


def draw_b_key(fig, pos, y):
    """Species labels come from the column labels; here the frame times left of the rows and one key below:
    the six colour ramps of the run (0-2, all plots the same range) stacked in column order."""
    x0 = pos[0][0]
    for (_, lab), yc in zip(config.FRAMES[malkmus_frames.KEY], malkmus_frames.row_centres(pos[0])):
        text(fig, x0 - 1.0, yc, lab, ha="right", va="center", fontsize=style.FS)
    x1 = pos[-1][0] + pos[-1][2]
    bw, sh = 30.0, 0.4
    lab_w = 0.55 * style.FS * 0.3528 * len(ACT)  # approximate width of the key label (mm)
    xb = (x0 + x1) / 2 - (bw - lab_w - 2.0) / 2
    ax = mm_axes(fig, xb, y + 0.4, bw, sh * len(SPECIES))
    t = np.linspace(0, 1, 512)
    rgb = np.stack([cmap(c)(t)[:, :3] for _, _, c, _ in SPECIES])  # one row per species, column order
    ax.imshow(rgb, extent=(0, VMAX, len(SPECIES), 0), aspect="auto", interpolation="nearest")
    ax.set(xlim=(0, VMAX), ylim=(len(SPECIES), 0), yticks=[])
    ax.set_xticks([0, 0.5, 1, 1.5, 2], ["0", "0.5", "1", "1.5", "2"])
    for s in ("left", "right", "top"):
        ax.spines[s].set_visible(True)
    text(fig, xb - 2.0, y + 0.4 + sh * len(SPECIES) / 2, ACT, ha="right", va="center", fontsize=style.FS)


def draw(ctx, fig, box):
    d = ctx.csv("fields_raw.csv")
    sp = [s for s, *_ in SPECIES]
    b1, b2, b3 = split(box, [1.25, 1.0, 1.1], gap=11)

    ax = axes(fig, b1, label="i")
    T = d.time_h.max()
    line = d[(d["l.y"] == ROW) & (d.time_h == T)].sort_values("l.x")
    xr = (line["l.x"] - CX) * DX_UM
    for s, lab, c, ls in ORDER:
        ax.plot(xr, line[s], color=c, ls=ls, label=lab)
    ax.set(xlabel="Position from domain center (µm)", ylabel=ACT, xlim=(-500, 500), ylim=(0, 2))
    ax.set_xticks([-500, -250, 0, 250, 500])
    legend(ax, loc="upper center", ncol=3)

    ax = axes(fig, b2, label="ii")
    sd = d.groupby("time_h")[sp].std()
    for s, lab, c, ls in ORDER:
        ax.semilogy(sd.index, sd[s], color=c, ls=ls, label=lab)
    ax.set(xlabel="Time after E10.5 (h)", ylabel="Spatial s.d. of activity", xlim=(0, T))
    ax.set_xticks(np.arange(0, T + 1, 6))

    R = 11.5  # mm right of the kymograph: colour bar (1.6 mm wide, 2.5 mm from the axes), ticks and label
    ax = axes(fig, b3, label="iii", right=R)
    k = d[d["l.y"] == ROW].pivot(index="time_h", columns="l.x", values="Sox9")
    x, t = (k.columns.to_numpy() - CX) * DX_UM, k.index.to_numpy()
    sox9 = [c for s, _, c, _ in SPECIES if s == "Sox9"][0]
    im = ax.pcolormesh(x, t, k.to_numpy(), cmap=cmap(sox9), vmin=0, vmax=VMAX, shading="nearest", rasterized=True)
    ax.set(xlabel="Position from domain center (µm)", ylabel="Time after E10.5 (h)", xlim=(-500, 500),
           ylim=(t.min() - 1.5, t.max() + 1.5))
    ax.set_xticks([-500, 0, 500])
    ax.set_yticks(np.arange(0, T + 1, 6))
    bx, by, bw, bh = b3
    cb = fig.colorbar(im, cax=mm_axes(fig, bx + bw - R + 2.5, by + 4.2, 1.6, bh - 4.2 - 8.0))
    cb.set_label("Sox9 activity (steady state = 1)", fontsize=style.FS)
    cb.set_ticks([0, 0.5, 1, 1.5, 2], labels=["0", "0.5", "1", "1.5", "2"])
    cb.ax.tick_params(labelsize=style.FS, width=0.5, length=2.0)
    cb.outline.set_linewidth(0.5)

    n = int((d.time_h == 0).sum())
    ctx.fmt.update(nodes=f"{n:,}", sd0=f"{sd.loc[0].mean():.4f}", sdsox9=f"{sd.loc[T, 'Sox9']:.2f}",
                   sdwnt2=f"{sd.loc[T, 'WNT2']:.2f}")
