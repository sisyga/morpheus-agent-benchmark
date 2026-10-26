"""Nature Methods style: Arial/Helvetica, 5-7 pt text, 8 pt bold panel letters, thin lines."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MM = 1 / 25.4  # inch per mm
FIG_W, FIG_H = 180.0, 185.0  # mm, final print size
FS = 6.0  # default text size [pt]
FS_SMALL = 5.0
FS_HEAD = 7.0
FS_LETTER = 8.0

PAPER_KW = dict(color="0.15", marker="o", ms=2.2, mfc="none", mew=0.6, lw=0, zorder=3)  # digitised paper data
PAPER_LINE_KW = dict(color="0.35", lw=0.7, ls=(0, (2.5, 1.5)), zorder=2)


def apply():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"],
        "font.size": FS, "axes.titlesize": FS, "axes.labelsize": FS,
        "xtick.labelsize": FS_SMALL, "ytick.labelsize": FS_SMALL, "legend.fontsize": FS_SMALL,
        "axes.linewidth": 0.5, "lines.linewidth": 0.9, "patch.linewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
        "xtick.major.size": 2.0, "ytick.major.size": 2.0, "xtick.minor.size": 1.2, "ytick.minor.size": 1.2,
        "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "axes.labelpad": 1.5,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "legend.handlelength": 1.6, "legend.handletextpad": 0.4,
        "legend.borderaxespad": 0.2, "legend.labelspacing": 0.25, "legend.columnspacing": 0.8,
        "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
        "mathtext.default": "regular",
    })
