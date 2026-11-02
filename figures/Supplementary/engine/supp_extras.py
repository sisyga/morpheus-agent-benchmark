"""Supplementary Table 1 (the scorer's criteria and weights for every study) and Supplementary Note 1 (the agent
prompt) for Supplementary_Figures.pdf, generated from the repository and the benchmark run:

- the criteria come from biological_scoring_criteria.json (version 7, exported from Biological_scoring_criteria_v7.xlsx);
  given the benchmark directory, its SHA-256 must match the criteria hash in the scorer's folder name
  (biological_scores/scorer-...__criteria-v7-<first 12 hex digits>), i.e. the file that scored the shown runs;
- the prompt is the saved subject_prompt.txt of the shown run of NOTE_KEY, verbatim, plus the <available_resources>
  block of every setup (the shown run's own, and one run of the same study in each other setup). build() copies these files into <out>/NOTE_DIR.
"""
import glob
import hashlib
import json
import os
import re
import shutil

import config
import legend

CRITERIA = "biological_scoring_criteria.json"
NOTE_KEY = "13_Mole2026"  # the main text's example study
NOTE_DIR = "Supplementary_Note_1"
MODES = ["python_web", "morpheus_cli", "morpheus_cli_docs", "morpheus_skill", "morpheus_mcp"]
TEX_SPECIAL = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$", "&": r"\&", "#": r"\#",
               "^": r"\^{}", "_": r"\_", "%": r"\%", "~": r"\textasciitilde{}"}


def tex(s):
    """Plain text (criteria are quoted verbatim) escaped for LaTeX; Unicode symbols as in the legends."""
    return "".join(TEX_SPECIAL.get(c) or (legend.TEX_CHARS.get(c, c) if ord(c) > 127 else c) for c in s)


def load_criteria(repo, runs=None):
    """{study key: criterion} in config.RUNS order; with runs, checks that this file scored the benchmark."""
    path = os.path.join(repo, CRITERIA)
    raw = open(path, "rb").read()
    d = json.loads(raw)
    if runs:
        digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()  # as committed (LF), on any checkout
        tags = [m.group(2) for p in glob.glob(os.path.join(runs, "biological_scores", "*"))
                if (m := re.search(r"criteria-v(\d+)-([0-9a-f]{12})$", os.path.basename(p)))]
        if not any(digest.startswith(t) for t in tags):
            raise RuntimeError(f"{CRITERIA} (sha256 {digest[:12]}) did not score {runs} (criteria hashes: {tags})")
    by_stem = {c["paper_stems"][0]: c for c in d["criteria"]}
    missing = [k for k in config.RUNS if k not in by_stem]
    if missing:
        raise RuntimeError(f"{CRITERIA} has no criteria for {missing}")
    return d["version"], {k: by_stem[k] for k in config.RUNS}


def criteria_table(version, crit):
    """Supplementary Table 1: per study a heading row (figure number, citation, scorer target), then
    each criterion verbatim with its type and weight."""
    balanced = all(sum(c["weight"] for c in v["clauses"] if c["kind"] == "qualitative")
                   == sum(c["weight"] for c in v["clauses"] if c["kind"] == "numeric")
                   for v in crit.values() if {c["kind"] for c in v["clauses"]} == {"qualitative", "numeric"})
    qual_only = [n for n, v in enumerate(crit.values(), start=1) if {c["kind"] for c in v["clauses"]} == {"qualitative"}]
    # the target is criteria.target, which only the scorer gets (src/benchmark/biological-scoring.ts); the agent's
    # prompt had its own, longer target text (benchmark_focus/<key>.txt, in Supplementary Note 1)
    caption = (r"\textbf{Scoring criteria and weights.} For each study, the target and the criteria given to the "
               "LLM scorer. The agents saw neither; their prompt described the target in more detail "
               r"(Supplementary Note~1). A run scores the summed weight of the criteria it meets, divided by the "
               "study's total weight.")
    if balanced:
        caption += " Where a study has qualitative and numeric criteria, both types carry the same total weight."
    if qual_only:
        caption += (f" Studies {qual_only[0]}--{qual_only[-1]} have qualitative criteria only."
                    if qual_only == list(range(qual_only[0], qual_only[-1] + 1))
                    else f" Studies {', '.join(map(str, qual_only))} have qualitative criteria only.")
    # one tabular per study (the page may break between studies; every study fits on a page), and no p columns:
    # with revtex4-2 and the array package (loaded by siunitx), any p{} column fails on TeX Live 2025 ("Extra \or"),
    # so every cell is a box of fixed width: the tabulars line up and each spans \linewidth (criterion, then the
    # type as wide as "qualitative", then the weight as wide as "Weight")
    cols = r"@{}l@{\hspace{1em}}l@{\hspace{1em}}l@{}"
    crit_box = lambda s: r"\parbox[t]{\critW}{\raggedright\strut %s\strut}" % s  # noqa: E731
    row = lambda c, k, w: r"%s & \makebox[\typeW][l]{%s} & \makebox[\wtW][r]{%s}\\" % (crit_box(c), k, w)  # noqa: E731
    out = [r"\clearpage", r"\refstepcounter{table}\label{tab:criteria}",
           # the caption as a paragraph in the figure-legend style (revtex: small type, "Supplementary Fig. 1." label)
           r"{\small\noindent Supplementary Table~\thetable. %s\par}" % caption,
           # \raggedbottom: revtex justifies pages vertically, which would spread the studies apart
           r"\raggedbottom\medskip\begingroup\footnotesize\setlength{\parindent}{0pt}\setlength{\parskip}{0pt}",
           r"\settowidth{\typeW}{qualitative}\settowidth{\wtW}{Weight}"
           r"\setlength{\critW}{\dimexpr\linewidth-\typeW-\wtW-2em\relax}",
           r"\begin{tabular}{%s}\toprule %s\midrule\end{tabular}\par" % (cols, row("Criterion", "Type", "Weight"))]
    for n, (key, v) in enumerate(crit.items(), start=1):
        authors, year = study_name(key)
        rows = [r"\multicolumn{3}{@{}l@{}}{\parbox[t]{\linewidth}{\raggedright\strut \textbf{%d.\ %s}%s\textbf{ (%s). "
                r"Target:} %s\strut}}\\" % (n, authors, legend_cite(key), year, tex(v["target"]))]
        for i, c in enumerate(v["clauses"]):
            if i and c["kind"] != v["clauses"][i - 1]["kind"]:
                rows.append(r"\addlinespace[3pt]")  # qualitative and numeric criteria apart
            rows.append(row(r"\hangindent=1em\hangafter=0 " + tex(c["description"]), c["kind"], "%g" % c["weight"]))
        last = n == len(crit)
        out += [r"\begin{tabular}{%s}" % cols, *rows, r"\bottomrule" if last else r"\midrule",  # rule after each study
                r"\end{tabular}\par"]
    return "\n".join(out + [r"\endgroup", ""])


def study_name(key):
    """(authors, year) from the panel module's legend title ('... (Atwell *et al.*, 2015).'), authors in LaTeX."""
    import build_all
    title = build_all.panel_module(key).LEGEND["title"]
    m = re.search(r"\(([^()]*?), (\d{4})\)\.?$", title)
    return legend._tex(m.group(1)), m.group(2)


def legend_cite(key):
    import build_all
    k = build_all.panel_module(key).LEGEND.get("cite")
    return r"\cite{%s}" % k if k else ""


def collect_prompts(runs, out):
    """Copy the shown NOTE_KEY run's subject_prompt.txt and the <available_resources> block of every setup (the
    shown run's own, one run of the same study for the others) into <out>/NOTE_DIR; returns the folder."""
    dst = os.path.join(out, NOTE_DIR)
    os.makedirs(dst, exist_ok=True)
    run, mode = config.RUNS[NOTE_KEY][:2]
    shutil.copyfile(os.path.join(runs, run, "subject_prompt.txt"), os.path.join(dst, f"prompt_{mode}.txt"))
    sources = [f"prompt_{mode}.txt: {run}/subject_prompt.txt"]
    for m in MODES:
        cands = [os.path.join(runs, run)] if m == mode else sorted(
            p for p in glob.glob(os.path.join(runs, f"*_{NOTE_KEY}__{m}__rep*"))
            if os.path.isfile(os.path.join(p, "subject_prompt.txt")))
        if not cands:
            raise RuntimeError(f"no {NOTE_KEY} run in setup {m} with subject_prompt.txt in {runs}")
        text = open(os.path.join(cands[0], "subject_prompt.txt"), encoding="utf-8").read()
        block = re.search(r"<available_resources>.*?</available_resources>", text, re.S)
        with open(os.path.join(dst, f"resources_{m}.txt"), "w", encoding="utf-8") as f:
            f.write(block.group(0) + "\n")
        sources.append(f"resources_{m}.txt: {os.path.basename(cands[0])}/subject_prompt.txt")
    with open(os.path.join(dst, "sources.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sources) + "\n")
    return dst


def prompt_note(out):
    """Supplementary Note 1 from <out>/NOTE_DIR (made by collect_prompts)."""
    run, mode, rep = config.RUNS[NOTE_KEY][:3]
    num, name = config.SETUP[mode]
    n_fig = list(config.RUNS).index(NOTE_KEY) + 1
    listing = r"\lstinputlisting[style=prompt]{%s/%s}"
    parts = [
        r"\clearpage",
        r"\section*{Supplementary Note 1: Agent prompt}",
        # the main-text panel is fixed (manuscript Fig. 2e ii-iv shows the Mole run); the supplementary number is computed
        ("Each agent received one prompt, which depended on the study and the setup. Below are the complete prompt "
         f"of the run on {study_name(NOTE_KEY)[0]}{legend_cite(NOTE_KEY)} shown in Fig.~2e\\,ii--iv of the main "
         f"text and in Supplementary Fig.~{n_fig} (setup {num}, {name}), followed by the resources block of each "
         "setup, all copied from the prompts the runs saved. When the agent started, the benchmark replaced the "
         "placeholders in double braces with the run's start and cutoff times."),
        "",
        r"\medskip\noindent\textbf{Complete prompt, setup %d (%s)}" % (num, name),
        listing % (NOTE_DIR, f"prompt_{mode}.txt"),
    ]
    for m in MODES:
        k, nm = config.SETUP[m]
        parts += [r"\medskip\noindent\textbf{Resources block, setup %d (%s)}" % (k, nm),
                  listing % (NOTE_DIR, f"resources_{m}.txt")]
    return "\n".join(parts + [""])


PREAMBLE = r"""\usepackage{array}
\usepackage{booktabs}
\usepackage{listings}
\lstdefinestyle{prompt}{basicstyle=\ttfamily\scriptsize, breaklines=true, columns=fullflexible, keepspaces=true,
  frame=single, framesep=4pt, xleftmargin=4pt, xrightmargin=4pt, aboveskip=4pt, belowskip=8pt}
\newlength{\critW}\newlength{\typeW}\newlength{\wtW}
\renewcommand{\tablename}{Supplementary Table}
\renewcommand{\thetable}{\arabic{table}}
"""


def build(out, repo, runs=None, note_runs=None):
    """The LaTeX of Supplementary Table 1 and Note 1, or only the table if no prompts are available (no runs and
    no NOTE_DIR in out). runs: folder with biological_scores/ (criteria check); note_runs: folder with the runs
    whose subject_prompt.txt the note quotes (default runs). Returns (tex blocks, notes for the log)."""
    version, crit = load_criteria(repo, runs)
    blocks, log = [], []
    if note_runs or runs:
        try:
            collect_prompts(note_runs or runs, out)
        except (OSError, RuntimeError) as e:
            log.append(f"Supplementary Note 1: prompts not collected ({e})")
    if os.path.isdir(os.path.join(out, NOTE_DIR)):
        blocks.append(prompt_note(out))  # the prompt first, then the table
    else:
        log.append("Supplementary Note 1 skipped: no prompts (pass the benchmark directory)")
    blocks.append(criteria_table(version, crit))
    return blocks, log
