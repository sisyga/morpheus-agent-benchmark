"""One PDF with all supplementary figures, each on its own page followed by its legend, typeset with the
manuscript's document class and preamble (revtex4-2, set in one column), so the legends
look like the main-figure legends. build_all.py calls write() after the figures are built; compile() runs latexmk or pdflatex
if one is installed.

    python figures/Supplementary/engine/supp_document.py <build folder>   # re-typeset an existing build
"""
import os
import shutil
import subprocess
import sys

import supp_extras

TEX_NAME = "Supplementary_Figures"
HERE = os.path.dirname(os.path.abspath(__file__))
BIB, BST = "morpheusai_supp", "naturemag"  # the cited papers; the manuscript's bibliography style

PREAMBLE = r"""\documentclass[
  aps,
  prl,
  reprint,
  onecolumn,
  nofootinbib,
  nobibnotes,
  floatfix
]{revtex4-2}

\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{siunitx}

\setcitestyle{super,sort&compress}
\renewcommand{\figurename}{Supplementary Fig.}
\hypersetup{pdftitle={Supplementary Figures}}

\begin{document}
"""

# title page: title and author block of the manuscript, with the
# subtitle; nothing else on the page
TITLE_PAGE = r"""\title{Morpheus.AI: agents autonomously generate, execute and refine virtual tissue models\\[0.6em]
\normalfont Supplementary material}

\author{Prerana Chandratre}
\author{Anjali Sharma}
\author{Justin Bürger Michaelis}
\author{Diego Jahn}
\author{Jörn Starruß}
\author{Lutz Brusch}
\thanks{These authors contributed equally to this work.}
\author{Simon Syga}
\thanks{These authors contributed equally to this work.}
\collaboration{Corresponding authors: \href{mailto:lutz.brusch@tu-dresden.de}{lutz.brusch@tu-dresden.de}, \href{mailto:simon.syga@tu-dresden.de}{simon.syga@tu-dresden.de}}
\affiliation{Center for Interdisciplinary Digital Sciences, TUD Dresden University of Technology, Dresden, Germany}

\maketitle
\newpage

"""


def figure_tex(n, key, legend_tex):
    """One page: the figure at full text width (at most 70 % of the text height) and its legend below."""
    return "\n".join([
        r"\setcounter{figure}{%d}" % (n - 1),
        r"\begin{figure}[p]",
        r"\centering",
        r"\includegraphics[width=\textwidth,height=0.7\textheight,keepaspectratio]{%s/%s.pdf}" % (key, key),
        r"\caption{%s}" % legend_tex,
        r"\label{fig:%s}" % key,
        r"\end{figure}",
        r"\clearpage",
        ""])


def write(out, entries, suffix="", extras=()):
    """entries: [(number, key, legend_tex)]. Writes <out>/Supplementary_Figures<suffix>.tex, followed by the
    references cited in the legends (morpheusai_supp.bib, naturemag.bst as in the manuscript, both copied to out),
    and returns its path. extras: LaTeX blocks before the figures (supp_extras.py: Supplementary Table 1, Note 1)."""
    path = os.path.join(out, TEX_NAME + suffix + ".tex")
    for f in (BIB + ".bib", BST + ".bst"):
        shutil.copyfile(os.path.join(HERE, f), os.path.join(out, f))
    with open(path, "w", encoding="utf-8") as f:
        f.write(PREAMBLE.replace("\\begin{document}", supp_extras.PREAMBLE + "\n\\begin{document}") if extras
                else PREAMBLE)
        f.write(TITLE_PAGE)
        for block in extras:
            f.write(block + "\n")
        if extras:
            f.write(r"\clearpage" + "\n")
        for n, key, tex in entries:
            f.write(figure_tex(n, key, tex))
        f.write(r"\bibliographystyle{%s}" % BST + "\n" + r"\bibliography{%s}" % BIB + "\n")
        f.write(r"\end{document}" + "\n")
    return path


def compile(tex):
    """Typeset tex in its folder. Returns the PDF path, or None if no TeX engine is installed; raises on errors."""
    folder, name = os.path.split(os.path.abspath(tex))
    if shutil.which("latexmk"):
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", name]
        runs = [cmd]
    elif shutil.which("pdflatex") and shutil.which("bibtex"):
        cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", name]
        runs = [cmd, ["bibtex", os.path.splitext(name)[0]], cmd, cmd]
    else:
        return None
    for c in runs:
        r = subprocess.run(c, cwd=folder, capture_output=True, text=True, errors="replace")
        if r.returncode:
            log = os.path.splitext(tex)[0] + ".log"
            raise RuntimeError(f"{' '.join(c)} failed (see {log}):\n" + r.stdout[-3000:])
    return os.path.splitext(tex)[0] + ".pdf"


if __name__ == "__main__":
    out = sys.argv[1]
    entries = []
    for key in sorted(os.listdir(out)):
        cap = os.path.join(out, key, "caption.tex")
        if os.path.isfile(cap):
            entries.append((int(key[:2]), key, open(cap, encoding="utf-8").read().strip()))
    pdf = compile(write(out, entries))
    print(pdf or "no TeX engine found; wrote the .tex only")
