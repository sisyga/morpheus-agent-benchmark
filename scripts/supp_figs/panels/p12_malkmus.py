"""Malkmus et al. (2025): agent-only final profiles of the six species and Sox9/WNT2 kymographs."""
import numpy as np

from panels.common import axes, split
import style

SPECIES = [("Sox9", "Sox9", "#d62728", "-"), ("SULF1", "SULF1", "#17becf", "-"), ("Sfrp2", "Sfrp2", "#c71585", "-"),
           ("WNT2", "WNT2", "#1f3fd6", "-"), ("beta_cat", "β-catenin", "#1b2a6b", (0, (3, 1.5))),
           ("BMP2", "BMP2", "#2ca02c", "-")]
CAPTION = ("Agent-only quantification along the centre line of the circular domain (fields_raw.csv, row through "
           "the centre; 1 node = 10 µm): (i) profiles of Sox9, SULF1, Sfrp2, WNT2, β-catenin and BMP2 at the final "
           "time (36 h), each divided by its maximum along the line; (ii) kymograph of Sox9 and (iii) of WNT2 "
           "(concentrations in model units).")


def draw(ctx, fig, box):
    d = ctx.csv("fields_raw.csv", sep=None, engine="python")
    ys = np.sort(d["l.y"].unique())
    yc = ys[np.argmin(np.abs(ys - ys.mean()))]
    line = d[d["l.y"] == yc].sort_values(["time_h", "x_um"])
    T = line.time_h.max()
    b1, b2, b3 = split(box, [1.3, 1, 1], gap=12)
    ax = axes(fig, b1, label="i")
    fin = line[line.time_h == T]
    for col, lab, c, ls in SPECIES:
        ax.plot(fin.x_um, fin[col] / fin[col].max(), color=c, ls=ls, lw=0.8, label=lab)
    ax.set(xlabel="position along centre line [µm]", ylabel=f"level / maximum at t = {T:g} h", ylim=(0, 1.35))
    ax.legend(loc="upper center", ncol=3, fontsize=4.8)
    for b, col, cmap, lab in [(b2, "Sox9", "Reds", "ii"), (b3, "WNT2", "Blues", "iii")]:
        ax = axes(fig, b, label=lab, right=7)
        k = line.pivot(index="time_h", columns="x_um", values=col)
        x, t = k.columns.to_numpy(), k.index.to_numpy()
        im = ax.pcolormesh(x, t, k.to_numpy(), cmap=cmap, shading="nearest", rasterized=True)
        ax.set(xlabel="position along centre line [µm]", ylabel="time [h]")
        ax.text(0.02, 1.01, col, transform=ax.transAxes, fontsize=style.FS_SMALL, va="bottom")
        cb = fig.colorbar(im, ax=ax, fraction=0.06, pad=0.03)
        cb.ax.tick_params(labelsize=style.FS_SMALL, width=0.4, length=1.5)
        cb.outline.set_linewidth(0.4)
