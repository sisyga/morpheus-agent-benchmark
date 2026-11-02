"""Render a figure SVG to PDF (vector, fonts embedded) and a 600 dpi PNG with headless Chrome.

Usage: python figures/render_fig.py Fig1.svg [more.svg ...]   -> writes .pdf and .png next to each SVG.
The page size is read from the SVG's width/height in mm. Chrome is looked up in $CHROME, the usual install
locations (Windows, macOS, Linux) and the Playwright browser cache. Output is rendered into a temporary folder
and then copied, so a PDF that is open in a viewer (Windows locks it) fails with a message, not a half file.
"""
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

DPI = 600


def find_chrome():
    cands = [os.environ.get("CHROME", "")]
    cands += ["C:/Program Files/Google/Chrome/Application/chrome.exe",
              "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    cands += [shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")]
    for cache in (os.path.expanduser("~/.cache/ms-playwright"), os.path.expandvars("%LOCALAPPDATA%/ms-playwright")):
        cands += sorted(glob.glob(f"{cache}/chromium-*/chrome-*/chrome") + glob.glob(f"{cache}/chromium-*/chrome-*/chrome.exe"),
                        reverse=True)
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    sys.exit("Chrome not found; set CHROME to its executable")


def chrome(exe, args):
    # default profile on purpose: Chrome for Testing 151 hangs in headless mode with a fresh --user-data-dir
    flags = ["--headless", "--disable-gpu", "--hide-scrollbars"]
    if sys.platform.startswith("linux"):
        flags.append("--no-sandbox")
    subprocess.run([exe, *flags, *args], check=True, capture_output=True, timeout=120)


def render(svg, exe):
    head = open(svg, encoding="utf-8").read(2000)
    w, h = (float(re.search(rf'{k}="([\d.]+)mm"', head).group(1)) for k in ("width", "height"))
    stem = os.path.splitext(svg)[0]
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copyfile(svg, f"{tmp}/fig.svg")
        page = (f'<!doctype html><html><head><meta charset="utf-8"><title>{os.path.basename(stem)}</title><style>'
                f'@page{{size:{w}mm {h}mm;margin:0}}html,body{{margin:0;padding:0;background:#fff}}'
                f'img{{display:block;width:{w}mm;height:{h}mm}}</style></head><body><img src="fig.svg"></body></html>')
        open(f"{tmp}/_print.html", "w", encoding="utf-8").write(page)
        url = "file:///" + os.path.abspath(f"{tmp}/_print.html").replace("\\", "/").lstrip("/")
        chrome(exe, ["--no-pdf-header-footer", f"--print-to-pdf={tmp}/fig.pdf", url])
        # PNG: screenshot at 600 dpi (CSS px are 1/96 in), cropped to the exact figure size
        scale = DPI / 96
        css_w, css_h = w / 25.4 * 96, h / 25.4 * 96
        chrome(exe, [f"--force-device-scale-factor={scale}", f"--window-size={math.ceil(css_w)},{math.ceil(css_h)}",
                     f"--screenshot={tmp}/shot.png", url])
        px = (round(w / 25.4 * DPI), round(h / 25.4 * DPI))
        Image.open(f"{tmp}/shot.png").convert("RGB").crop((0, 0, *px)).save(f"{tmp}/fig.png", dpi=(DPI, DPI),
                                                                             optimize=True)
        for ext in ("pdf", "png"):
            try:
                shutil.copyfile(f"{tmp}/fig.{ext}", f"{stem}.{ext}")
            except PermissionError:
                alt = f"{stem}_new.{ext}"
                shutil.copyfile(f"{tmp}/fig.{ext}", alt)
                print(f"  {stem}.{ext} is locked (open in a viewer?); wrote {alt} instead")
    print(f"{svg}: {w} x {h} mm -> PDF, PNG {px[0]} x {px[1]} px at {DPI} dpi")


if __name__ == "__main__":
    exe = find_chrome()
    for f in sys.argv[1:]:
        render(f, exe)
