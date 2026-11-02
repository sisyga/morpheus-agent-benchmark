"""Folders of the Fig. 2 scripts.

DATA   data/ next to this file: per-run table of both benchmarks, manual vs automated scores, the Atwell run's cell
       counts and the Molè height rerun (see README.md)
OUT    build folder: $FIGURE_OUT, else build/ next to this file; panel files go to OUT/panels
config the supplementary-figure settings (figures/Supplementary/engine/config.py): the run shown for each study
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "figures" / "Supplementary" / "engine"))
import config  # noqa: E402,F401  (used by make_table.py: the run shown for each study)
from PIL import ImageFont  # noqa: E402


def arial(bold=False, size=1000):
    """Arial for text widths: Windows fonts, msttcorefonts on Linux, or macOS (same metrics)."""
    names = ("arialbd.ttf", "Arial Bold.ttf") if bold else ("arial.ttf", "Arial.ttf")
    for d in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/msttcorefonts", "/Library/Fonts/Supplemental"):
        for n in names:
            if os.path.exists(f"{d}/{n}"):
                return ImageFont.truetype(f"{d}/{n}", size)
    raise FileNotFoundError(f"Arial not found ({names[0]})")


DATA = HERE / "data"
OUT = Path(os.environ.get("FIGURE_OUT", HERE / "build"))
PANELS = OUT / "panels"
PANELS.mkdir(parents=True, exist_ok=True)
