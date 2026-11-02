"""Publication legends of the supplementary figures, in the style of the manuscript's main-figure legends.

Each panel module defines LEGEND = {"title", panel letters ("a", "b", ...), optional "abbrev" and "license"}, written
in a small markup: **bold**, *italic*, <sub>…</sub>, <sup>…</sup>, <cite>bibkey</cite> (morpheusai_supp.bib),
[link text](https://…), Unicode symbols and {fields} filled from ctx.fmt
plus the {graph} sentence below. assemble() fills it in; to_markdown() and to_latex() render it. The long
technical captions (CAPTION, B_CAPTION, ...) are kept as technical notes (build_all.caption)."""
import re

import config

HEADER = ("# Legends: paper-comparison supplementary figures\n\n"
          "Publication legends (panels/pNN_*.py: LEGEND; legend.py). Details of every input, crop and "
          "correction: technical_notes{suffix}.md.\n\n")

# panel c of every figure (b for Szabó and Scheel): the reduced (or full) Morpheus model graph
GRAPH_REDUCED = "Model graph of the agent's model as drawn by Morpheus (reduced view{rows})."
GRAPH_FULL = "Model graph of the agent's model as drawn by Morpheus (full graph{rows})."


GRAPH_RE = re.compile(r"drawn by Morpheus(?: from its model\.xml)? \((reduced view|full graph)(?:, wrapped into (\d+) rows)?\)")


def graph_sentence(g):
    rows = f", wrapped into {g['graph_rows']} rows" if g["graph_rows"] > 1 else ""
    return (GRAPH_REDUCED if g["graph_reduced"] else GRAPH_FULL).format(rows=rows)


def graph_from_legend(text):
    """graph_reduced and graph_rows read back from a legend written by graph_sentence ."""
    m = GRAPH_RE.search(text)
    if not m:
        raise ValueError("no model-graph sentence in the legend")
    return dict(graph_reduced=m.group(1) == "reduced view", graph_rows=int(m.group(2) or 1))


def run_sentence(key):
    """As in the manuscript's Fig. 2 legend: 'Model built by GPT-6.1 Sol with setup 4 (Skill; ...)'."""
    _, mode, rep, score = config.RUNS[key]
    num, name = config.SETUP[mode]
    return f"Model built by {config.MODEL_NAME} with setup {num} ({name}; repetition {rep}, score {score:.2f})."


def fields(ctx, info):
    """The values a legend takes from the build: the panel module's ctx.fmt and the layout of the graph panel."""
    return dict(fmt=dict(ctx.fmt), graph_reduced=bool(info["graph"].reduced), graph_rows=int(info["graph_rows"]))



def assemble(mod, key, f):
    """(title, [(letter, text), ...], tail) with all fields filled; the frames panel starts with the run sentence."""
    leg = mod.LEGEND
    fmt = dict(f["fmt"], graph=graph_sentence(dict(graph_reduced=f["graph_reduced"], graph_rows=f["graph_rows"])))
    letters = sorted(k for k in leg if len(k) == 1)
    frames = "a" if config.PANEL_A[key].get("omit") else "b"
    panels = []
    cite = lambda s: add_citations(s, leg.get("cite"))  # noqa: E731
    for k in letters:
        txt = cite(leg[k].format(**fmt))
        if k == frames:
            txt = run_sentence(key) + " " + txt
        panels.append((k, txt))
    tail = " ".join(link_licenses(cite(leg[k].format(**fmt))) for k in ("abbrev", "license") if leg.get(k))
    return leg["title"].format(**fmt), panels, tail  # titles stay without citations


# "CC BY 4.0", "CC BY-NC-ND 4.0", ... -> a link to the license deed (text kept)
LICENSE = re.compile(r"(?<!\[)CC BY((?:-[A-Z]{2})*) (\d\.\d)(?!\])")


def link_licenses(s):
    return LICENSE.sub(lambda m: f"[{m.group(0)}](https://creativecommons.org/licenses/by{m.group(1).lower()}/"
                                 f"{m.group(2)}/)", s)


# "Name *et al.*" (or "Berkemeier & Page") not already followed by a citation
AUTHORS = re.compile(r"(?:\b[A-Z][\w-]*(?: [A-Z][\w-]*)? \*et al\.\*|Berkemeier & Page)(?!<cite>)")


def add_citations(s, key):
    """Cite LEGEND['cite'] after every mention of the authors that has no explicit <cite> of its own."""
    if not key:
        return s
    if not re.fullmatch(r"[^\s{},]+(?:,[^\s{},]+)*", key):
        raise ValueError(f"bad citation key {key!r}")
    return AUTHORS.sub(lambda m: m.group(0) + f"<cite>{key}</cite>", s)


def to_markdown(n, title, panels, tail):
    body = " ".join(f"**{k}**, {t}" for k, t in panels)
    text = f"**Supplementary Fig. {n} | {title}** {body}" + (f" {tail}" if tail else "") + "\n"
    return CITE.sub(lambda m: "[" + m.group(1).replace(" ", "") + "]", text)  # citations as [bibkey]


# Unicode -> LaTeX (pdflatex, T1, utf8 inputenc): accented Latin letters pass through; everything else must be
# listed here, so that a new symbol fails the build instead of silently breaking the PDF
TEX_CHARS = {
    "µ": r"\textmu{}", "α": r"$\alpha$", "β": r"$\beta$", "γ": r"$\gamma$", "δ": r"$\delta$", "Δ": r"$\Delta$",
    "ε": r"$\varepsilon$", "ν": r"$\nu$", "π": r"$\pi$", "σ": r"$\sigma$", "τ": r"$\tau$", "φ": r"$\phi$",
    "χ": r"$\chi$", "λ": r"$\lambda$", "θ": r"$\theta$", "ρ": r"$\rho$", "ω": r"$\omega$", "κ": r"$\kappa$",
    "×": r"$\times$", "−": r"$-$", "–": "--", "—": "---", "≈": r"$\approx$", "≥": r"$\geq$", "≤": r"$\leq$",
    "±": r"$\pm$", "→": r"$\rightarrow$", "←": r"$\leftarrow$", "↔": r"$\leftrightarrow$", "°": r"$^{\circ}$",
    "…": r"\ldots{}", "’": "'", "‘": "`", "“": "``", "”": "''", " ": r"\,", " ": "~", "·": r"$\cdot$",
    "∼": r"$\sim$", "~": r"$\sim$", "%": r"\%", "&": r"\&", "#": r"\#", "$": r"\$", "_": r"\_",
}
SUP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+"))
SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉", "0123456789"))


def _plain(s):
    """Escape and translate plain text (no markup)."""
    out, i = [], 0
    while i < len(s):
        c = s[i]
        for table, op in ((SUP, "^"), (SUB, "_")):
            if c in table:
                j = i
                while j < len(s) and s[j] in table:
                    j += 1
                out.append(f"${op}{{{''.join(table[x] for x in s[i:j])}}}$")
                i = j
                break
        else:
            if c in TEX_CHARS:
                out.append(TEX_CHARS[c])
            elif c in "\\{}^":
                raise ValueError(f"legend text contains {c!r}: {s!r}")
            elif ord(c) > 127 and not c.isalpha():
                raise ValueError(f"no LaTeX mapping for {c!r} (U+{ord(c):04X}) in legend text: {s!r}")
            else:
                out.append(c)
            i += 1
    return "".join(out)


MARKUP = re.compile(r"\*\*(.+?)\*\*|\*(.+?)\*|<sub>(.+?)</sub>|<sup>(.+?)</sup>|<cite>([^<]+)</cite>"
                    r"|\[([^\]]+)\]\((https?://[^)\s]+)\)")
CITE = re.compile(r"<cite>([^<]+)</cite>")


def _tex(s):
    out, pos = [], 0
    for m in MARKUP.finditer(s):
        out.append(_plain(s[pos:m.start()]))
        b, it, sub, sup, cite, ltext, url = m.groups()
        if cite is not None:  # keys of morpheusai_supp.bib
            if not re.fullmatch(r"[^\s{},]+(?:,[^\s{},]+)*", cite):
                raise ValueError(f"bad citation key {cite!r}")
            out.append(r"\cite{" + cite + "}")
        elif ltext is not None:
            out.append(r"\href{" + url + "}{" + _tex(ltext) + "}")
        elif b is not None:
            out.append(r"\textbf{" + _tex(b) + "}")
        elif it is not None:
            out.append(r"\textit{" + _tex(it) + "}")
        else:
            inner = _plain(sub if sub is not None else sup).replace("$", "")
            out.append(("$_{" if sub is not None else "$^{") + r"\mathrm{" + inner + "}}$")
        pos = m.end()
    out.append(_plain(s[pos:]))
    # "et al." followed by a period-space must not end a sentence in TeX spacing
    # (a capital letter after it starts a new sentence, which keeps the sentence space)
    return re.sub(r"(\\textit\{et al\.\}(?:\\cite\{[^}]*\})?) (?![A-Z])", r"\1\\ ", "".join(out))


def to_latex(title, panels, tail):
    body = " ".join(r"\textbf{" + k + "}, " + _tex(t) for k, t in panels)
    return r"\textbf{" + _tex(title) + "} " + body + (" " + _tex(tail) if tail else "")
