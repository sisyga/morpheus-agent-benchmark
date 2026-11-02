"""Nature Methods style, as Fig. 1 and Fig. 2 of the paper: Arial; 8 pt bold panel letters and sub-panel
numerals, 7 pt axis labels, 6 pt tick labels, legends and annotations (5 pt only as a floor); 0.5 pt axes,
outward ticks, black text only, no grids, frameless legends."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import _mathtext  # noqa: E402

MM = 1 / 25.4  # inch per mm
FIG_W, FIG_H = 180.0, 170.0  # mm, final print size (Nature maximum that leaves room for the legend); never scaled
FS = 6.0  # tick labels, legends, colour-bar labels, annotations, frame labels
FS_LABEL = 7.0  # axis labels
FS_MIN = 5.0  # floor, only where space forces it
FS_LETTER = 8.0  # panel letters (bold) and sub-panel numerals (bold)
LW_DATA = 0.75
LW_REF = 0.8  # reference and dashed lines

PAPER_KW = dict(color="0.15", marker="o", ms=2.5, mfc="none", mew=0.5, lw=0, zorder=3)  # digitised paper data
PAPER_LINE_KW = dict(color="0.35", lw=LW_REF, ls=(0, (2.5, 1.5)), zorder=2)


def apply():
    # mathtext sub/superscripts (τ$_0$) shrink by 0.7 by default, below the 5 pt floor at 6-7 pt
    _mathtext.SHRINK_FACTOR = 0.85
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "Liberation Sans", "DejaVu Sans"],
        "font.size": FS, "axes.titlesize": FS_LABEL, "axes.labelsize": FS_LABEL,
        "xtick.labelsize": FS, "ytick.labelsize": FS, "legend.fontsize": FS, "legend.title_fontsize": FS,
        "text.color": "black", "axes.labelcolor": "black", "xtick.labelcolor": "black",
        "ytick.labelcolor": "black", "axes.edgecolor": "black", "xtick.color": "black", "ytick.color": "black",
        "axes.linewidth": 0.5, "lines.linewidth": LW_DATA, "patch.linewidth": 0.5,
        "lines.markersize": 3.0, "lines.markeredgewidth": 0.5,
        "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
        "xtick.major.size": 2.0, "ytick.major.size": 2.0, "xtick.minor.size": 1.2, "ytick.minor.size": 1.2,
        "xtick.direction": "out", "ytick.direction": "out",
        "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "xtick.minor.pad": 1.5, "ytick.minor.pad": 1.5,
        "axes.labelpad": 2.0,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
        "legend.frameon": False, "legend.handlelength": 1.2, "legend.handletextpad": 0.4,
        "legend.borderaxespad": 0.2, "legend.labelspacing": 0.25, "legend.columnspacing": 0.8,
        "svg.fonttype": "none", "pdf.fonttype": 42, "ps.fonttype": 42,
        "mathtext.default": "regular", "mathtext.fontset": "custom", "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
    })
