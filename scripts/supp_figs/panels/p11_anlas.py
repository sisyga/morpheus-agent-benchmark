"""Anlas et al. (2024): final A-P profiles of Bra and Sox2 vs Fig. 1E; Aldh1a2/Eomes profiles; cell number."""
import numpy as np

from panels.common import axes, paper, split

C_BRA, C_SOX, C_ALD, C_EOM, C_N = "#2ca02c", "#8e5fd0", "#2e86c1", "#b9770e", "#444444"  # Bra green, Sox2 purple
B_LEGEND = [("#39d339", "Bra/T"), ("#a77be0", "Sox2"), ("#f0a020", "N-cadherin (Cdh2); bright = high")]
NBINS = 10
CAPTION = ("(i) Bra/T and Sox2 along the anterior–posterior (A–P) axis at the final time, 72 h (cells.csv): the "
           "A–P axis runs from the Sox2-weighted to the Bra-weighted centroid of the cells; cell positions are "
           "projected on it, normalised to 0–1 and binned into 10 bins (mean per bin); each curve is divided by "
           "its maximum. Paper: 72 hpa profiles of Fig. 1E (digitised, 11_Anlas/Bra_T.csv, Sox_2.csv), each also "
           "divided by its maximum. (ii) Aldh1a2 and Eomes along the same axis, normalised in the same way. "
           "(iii) Cell number vs time (cells.csv). Frames in b show Bra/T, Sox2 and N-cadherin per cell (left to "
           "right; each scaled 0–1).")


def ap_profile(c, cols):
    p = c[["cell.center.x", "cell.center.y"]].to_numpy()
    wa, wp = c.Sox2.to_numpy(), c.Bra.to_numpy()
    a = (p * wa[:, None]).sum(0) / wa.sum()
    b = (p * wp[:, None]).sum(0) / wp.sum()
    e = (b - a) / np.linalg.norm(b - a)
    s = p @ e
    s = (s - s.min()) / (s.max() - s.min())
    k = np.minimum((s * NBINS).astype(int), NBINS - 1)
    x = (np.arange(NBINS) + 0.5) / NBINS
    out = {}
    for col in cols:
        m = np.array([c[col].to_numpy()[k == i].mean() for i in range(NBINS)])
        out[col] = m / np.nanmax(m)
    return x, out


def draw(ctx, fig, box):
    d = ctx.csv("cells.csv", sep=None, engine="python")
    T = d.time_h.max()
    x, prof = ap_profile(d[d.time_h == T], ["Bra", "Sox2", "Aldh1a2", "Eomes"])
    pb = ctx.paper("11_Anlas/Bra_T.csv")
    ps = ctx.paper("11_Anlas/Sox_2.csv")
    b1, b2, b3 = split(box, [1.3, 1, 0.9], gap=10)
    ax = axes(fig, b1, label="i")
    ax.plot(x, prof["Bra"], color=C_BRA, label="agent, Bra/T")
    ax.plot(x, prof["Sox2"], color=C_SOX, label="agent, Sox2")
    paper(ax, pb.x, pb.y / pb.y.max(), label="paper Fig. 1E, Bra/T (digitised)", ms=1.6)
    paper(ax, ps.x, ps.y / ps.y.max(), label="paper Fig. 1E, Sox2 (digitised)", marker="s", ms=1.4)
    ax.set(xlabel="normalised length A → P", ylabel="expression / maximum", xlim=(0, 1), ylim=(0, 1.45),
           yticks=[0, 0.25, 0.5, 0.75, 1])
    ax.legend(loc="upper center", ncol=2, fontsize=4.8)
    ax = axes(fig, b2, label="ii")
    ax.plot(x, prof["Aldh1a2"], color=C_ALD, label="Aldh1a2")
    ax.plot(x, prof["Eomes"], color=C_EOM, label="Eomes")
    ax.set(xlabel="normalised length A → P", ylabel="expression / maximum", xlim=(0, 1), ylim=(0, 1.08))
    ax.legend(loc="upper right")
    n = d.groupby("time_h").size()
    ax = axes(fig, b3, label="iii")
    ax.plot(n.index, n.values, color=C_N)
    ax.set(xlabel="time [h]", ylabel="cells", xlim=(0, T))
