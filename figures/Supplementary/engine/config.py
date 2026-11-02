"""All inputs of the paper-comparison supplementary figures, in one place.

Each figure has its own folder next to this engine (FOLDERS): panel.py (what the figure shows), data/ (the files
of the shown benchmark run that the figure reads), paper_data/ (digitised paper data), model_graph/ (the committed
model graphs) and the figure's helper scripts. Paper PDFs are in benchmark_papers/ at the repository root. With
build_all.py --runs <benchmark dir>, the run files are read from the full benchmark run instead.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUPP = os.path.dirname(HERE)  # figures/Supplementary

BENCHMARK = "20261007_202940_benchmark"
FOLDERS = {
    "01_Szabo2010": "Supp_Fig_01_Szabo2010", "02_Thapa2024": "Supp_Fig_02_Thapa2024",
    "03_Carpenter2024": "Supp_Fig_03_Carpenter2024", "04_Atwell2025": "Supp_Fig_04_Atwell2015",
    "05_Berkemeier2023": "Supp_Fig_05_Berkemeier2023", "06_Herron2022": "Supp_Fig_06_Herron2022",
    "07_Scheel2021": "Supp_Fig_07_Scheel2021", "08_Mu2024": "Supp_Fig_08_Mu2024", "09_Luque2023": "Supp_Fig_09_Luque2023",
    "10_Berkhout2025": "Supp_Fig_10_Berkhout2025", "11_Anlas2024": "Supp_Fig_11_Anlas2024",
    "12_Malkmus2025": "Supp_Fig_12_Malkmus2025", "13_Mole2026": "Supp_Fig_13_Mole2026",
    "14_Otsuki2025": "Supp_Fig_14_Otsuki2025", "15_Reza2025": "Supp_Fig_15_AlReza2025",
}
TABLE_DIR = os.path.join(SUPP, "Supp_Table_1")  # data/biological_scores/<scorer folder name>
NOTE_DIR = os.path.join(SUPP, "Supp_Note_1")  # data/<run>/subject_prompt.txt of the runs quoted in the note


def fig_dir(key):
    """Folder of one figure (key as in RUNS, e.g. 04_Atwell2025)."""
    return os.path.join(SUPP, FOLDERS[key])


def key_for(number):
    """Key of the figure with this paper number (int or '04')."""
    return next(k for k in FOLDERS if int(k[:2]) == int(number))


for _key in FOLDERS:  # the figures' helper scripts (atwell_3d, extractors) are imported by name
    sys.path.insert(0, fig_dir(_key))
ATTEMPT = "attempts/attempt_001"  # scored attempt of every run
MODEL = "gpt-6.1-sol"
MODE_LABEL = {"morpheus_cli": "Morpheus CLI", "morpheus_cli_docs": "Morpheus CLI + docs",
              "morpheus_skill": "Morpheus Skill", "morpheus_mcp": "Morpheus MCP"}
# names in the legends, as in the manuscript (Methods, Agent setups; Fig. 2 legend)
MODEL_NAME = "GPT-6.1 Sol"
SETUP = {"python_web": (1, "Web"), "morpheus_cli": (2, "CLI"), "morpheus_cli_docs": (3, "Docs"),
         "morpheus_skill": (4, "Skill"), "morpheus_mcp": (5, "MCP")}

# Shown run per paper: best run of the mode scheme (papers 1-2 MCP, 3-6 Skill, 7-10 MCP, 11-13 Skill,
# 14-15 MCP); within it, the best-scoring run (ties decided on the simulation outputs). score = the scorer's score
# of that run. Luque: MCP rep 2 has the scorer's 1.00, but the scorer passed its cancer growth ratio of 1756 against
# the criterion's range of 10-1000 in error; with that criterion failed it scores 0.83, as the shown rep 3.
RUNS = {
    "01_Szabo2010": ("20261007_211902_01_Szabo2010__morpheus_mcp__rep03", "morpheus_mcp", 3, 1.0),
    "02_Thapa2024": ("20261007_223642_02_Thapa2024__morpheus_mcp__rep03", "morpheus_mcp", 3, 1.0),
    "03_Carpenter2024": ("20261007_232808_03_Carpenter2024__morpheus_skill__rep01", "morpheus_skill", 1, 1.0),
    "04_Atwell2025": ("20261008_222700_04_Atwell2025__morpheus_skill__rep02__replacement02", "morpheus_skill", 2, 1.0),
    "05_Berkemeier2023": ("20261008_142119_05_Berkemeier2023__morpheus_skill__rep01__replacement02", "morpheus_skill", 1, 1.0),
    "06_Herron2022": ("20261008_142120_06_Herron2022__morpheus_skill__rep01__replacement02", "morpheus_skill", 1, 1.0),
    "07_Scheel2021": ("20261008_152400_07_Scheel2021__morpheus_mcp__rep01__replacement02", "morpheus_mcp", 1, 1.0),
    "08_Mu2024": ("20261011_140942_08_Mu2024__morpheus_mcp__rep02__replacement03", "morpheus_mcp", 2, 0.83),
    "09_Luque2023": ("20261014_135600_09_Luque2023__morpheus_mcp__rep03__replacement04", "morpheus_mcp", 3, 0.83),
    "10_Berkhout2025": ("20261013_143544_10_Berkhout2025__morpheus_mcp__rep03__replacement02", "morpheus_mcp", 3, 1.0),
    "11_Anlas2024": ("20261011_183911_11_Anlas2024__morpheus_skill__rep02__replacement02", "morpheus_skill", 2, 1.0),
    "12_Malkmus2025": ("20261008_203824_12_Malkmus2025__morpheus_skill__rep01__replacement02", "morpheus_skill", 1, 0.8),
    "13_Mole2026": ("20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02", "morpheus_skill", 3, 0.875),
    "14_Otsuki2025": ("20261008_213726_14_Otsuki2025__morpheus_mcp__rep01__replacement02", "morpheus_mcp", 1, 1.0),
    "15_Reza2025": ("20261013_185544_15_Reza2025__morpheus_mcp__rep03__replacement02", "morpheus_mcp", 3, 1.0),
}

# Panel a: crops of benchmark_papers/<key>.pdf. Each crop: (0-based page, (x0, y0, x1, y1) in PDF points,
# sub-label or ""). rows: crop indices per row. Bounding boxes were located by matching the panel-a
# images of the 2026-10-07 drafts against the PDF pages (SIFT) and trimmed by eye.
# omit=True: closed-access publication without an open-access version, panel a is left out (crops kept for reference)
PANEL_A = {
    "01_Szabo2010": dict(title="Szabó et al. (2010), Fig. 10a–d", crops=[(9, (50, 70, 546, 438), "")], rows=[[0]],
                         omit=True),
    # Thapa: arranged by panels/p02_thapa.py (a_images): the row of Suppl. Fig. S12 and the three Fig. 4B iv snapshots
    # (their black plot areas) and Fig. 4D, labelled with the paper's times; the Fig. 4A colour key (without its
    # letter) below Fig. 4D
    "02_Thapa2024": dict(title="Thapa et al. (2024), Model 4",
                         crops=[(22, (239.4, 413.1, 489.0, 638.0), "Suppl. Fig. S12, initial layout at 0 h"),
                                (5, (153.2, 467.9, 244.5, 559.4), "Fig. 4B iv at 24, 72 and 120 h"),
                                (5, (266.0, 467.9, 357.3, 559.4), ""), (5, (378.1, 467.9, 469.4, 559.4), ""),
                                (5, (272.0, 583.0, 484.1, 695.5), "Fig. 4D"),
                                (5, (188.0, 57.8, 413.5, 105.8), "Fig. 4A colour key, below Fig. 4D")],
                         rows=[[0, 1, 2, 3, 4]]),
    # 03, 15: open-access bioRxiv preprints (pdf) instead of the published versions; cite: caption text of panel a
    "03_Carpenter2024": dict(title="Carpenter et al. (2023, bioRxiv preprint), Fig. 2A, D, E–F",
                             cite="Carpenter et al. (2023), bioRxiv preprint doi:10.1101/2023.07.25.550581 (CC BY 4.0; "
                                  "published as Carpenter et al. (2024)), Fig. 2A, D, E–F",
                             pdf="benchmark_papers/preprints/03_Carpenter2023_bioRxiv.pdf",
                             crops=[(3, (86, 64, 208, 183), ""), (3, (430, 64, 545, 183), ""),
                                    (3, (86, 181, 545, 400), "")], rows=[[0, 1, 2]]),
    "04_Atwell2025": dict(title="Atwell et al. (2015), Fig. 3", crops=[(3, (320, 290, 550, 650), "")], rows=[[0]]),
    # Berkemeier: Fig. 1f (the benchmark's case, ε = 1) and the figure's colour bar, at the PDF's common scale
    "05_Berkemeier2023": dict(title="Berkemeier & Page (2023), Fig. 1f (ε = 1, 14 × 14 lattice) with the colour bar of Fig. 1c–f",
                              crops=[(2, (368, 204, 480, 351), ""), (2, (485, 162, 516, 227), "")], rows=[[0, 1]],
                              same_scale=True),
    "06_Herron2022": dict(title="Herron et al. (2022), Fig. 2A, 2C–D and Fig. 4F",
                          crops=[(5, (66, 72, 230, 242), "Fig. 2A"), (5, (68, 249, 588, 394), "Fig. 2C, D"),
                                 (10, (412, 505, 596, 655), "Fig. 4F (target)")], rows=[[0, 1, 2]]),
    "07_Scheel2021": dict(title="Scheel et al. (2021), Fig. 2 (target: cutting → regeneration) and Fig. 5",
                          crops=[(4, (42, 50, 396, 406), "Fig. 2"), (13, (40, 50, 398, 208), "Fig. 5")],
                          rows=[[0, 1]], omit=True),
    "08_Mu2024": dict(title="Mu et al. (2024), Fig. 2A–D", crops=[(4, (94, 214, 502, 558), "")], rows=[[0]]),
    "09_Luque2023": dict(title="Luque et al. (2023), Fig. 10a, b",
                         crops=[(16, (88, 75, 575, 232), ""), (16, (88, 232, 340, 380), "")], rows=[[0, 1]]),
    # Berkhout: the six cell-field snapshots of Fig. 1 (0-50 h, every 10 h), each with its blue frame
    "10_Berkhout2025": dict(title="Berkhout et al. (2025), Fig. 1 (cell field, 0–50 h)",
                            crops=[(2, (x0, 175.0, x1, 234.5), "") for x0, x1 in
                                   ((76.4, 148.9), (150.4, 222.9), (224.5, 297.0), (298.5, 371.0), (372.4, 444.9),
                                    (446.3, 518.8))], rows=[[0, 1, 2, 3, 4, 5]]),
    "11_Anlas2024": dict(title="Anlas et al. (2024), Fig. 1A–E and Fig. 4B",
                         crops=[(2, (68, 48, 542, 378), "Fig. 1A–E"), (6, (322, 82, 545, 177), "Fig. 4B")],
                         rows=[[0, 1]], same_scale=True),  # same_scale: Fig. 4B at the PDF scale of Fig. 1, not enlarged
    "12_Malkmus2025": dict(title="Malkmus et al. (2025), Fig. 5A, C (wild type)",
                           crops=[(7, (98, 50, 506, 166), ""), (7, (98, 266, 506, 376), "")], rows=[[0], [1]]),
    "13_Mole2026": dict(title="Mole et al. (2026), Fig. 3A", crops=[(7, (92, 118, 276, 277), "")], rows=[[0]]),
    "14_Otsuki2025": dict(title="Otsuki et al. (2025), Fig. 5f", crops=[(6, (40, 376, 585, 508), "")], rows=[[0]]),
    "15_Reza2025": dict(title="Al Reza et al. (2024, bioRxiv preprint), Fig. 1a, f and Fig. 4g–i",
                        cite="Al Reza et al. (2024), bioRxiv preprint doi:10.1101/2024.08.30.610426 (CC BY-NC-ND 4.0; "
                             "published as Reza et al. (2025), with Fig. 1f as Fig. 1b), Fig. 1a, f and Fig. 4g–i",
                        pdf="benchmark_papers/preprints/15_Reza2024_bioRxiv.pdf",
                        crops=[(16, (64, 70, 538, 225), "Fig. 1a"), (16, (64, 456, 304, 535), "Fig. 1f"),
                               (20, (64, 440, 542, 604), "Fig. 4g–i")],
                        rows=[[0, 1], [2]]),
}

# Panel b: frames of the run's own Gnuplotter output, starting at the initial state: (file, label).
# Atwell uses 3D renders made by atwell_3d.py from the run's lattice checkpoints (see ATWELL_FRAMES).
FRAMES = {
    "01_Szabo2010": [("plot_00000.png", "0 h"), ("plot_00360.png", "6 h"),
                     ("plot_01440.png", "24 h")],  # 1 MCS = 1 min (B_CAPTION of p01_szabo)
    # Thapa: the paper's times (Fig. 4B: 24, 72, 120 h) after the initial state; the run's Gnuplotter wrote 0, 24, 48,
    # 72 and 120 h (time-step 24, condition time_hours < 95 or > 119)
    "02_Thapa2024": [("plot_000.00000.png", "0 h"), ("plot_024.00000.png", "24 h"), ("plot_072.00000.png", "72 h"),
                     ("plot_120.00000.png", "120 h")],
    "03_Carpenter2024": [("plot_0000.0000.png", "0 τ$_0$"), ("plot_4050.0000.png", "18 τ$_0$"),
                         ("plot_7875.0000.png", "35 τ$_0$")],
    # dimensionless model time t in units of the Notch decay time τ_N (Eqs. 1–2 of the paper)
    "05_Berkemeier2023": [("plot_000.0000.png", "$\\mathit{t}$ = 0"), ("plot_003.0000.png", "$\\mathit{t}$ = 3 τ$_\\mathrm{N}$"),
                          ("plot_006.0000.png", "$\\mathit{t}$ = 6 τ$_\\mathrm{N}$"),
                          ("plot_100.0000.png", "$\\mathit{t}$ = 100 τ$_\\mathrm{N}$")],
    "06_Herron2022": [("plot_00.00000.png", "0 s"), ("plot_10.00000.png", "10 s"), ("plot_20.00000.png", "20 s"),
                      ("plot_40.00000.png", "40 s")],
    "07_Scheel2021": [("fields_raw_plot_x_paper_s_00.00000.png", "Time 0"),  # dimensionless model time;
                      ("fields_raw_plot_x_paper_s_05.00000.png", "Time 5"),  # redrawn as vector plots from
                      ("fields_raw_plot_x_paper_s_10.00000.png", "Time 10")],  # fields_raw.csv (p07_scheel)
    # Mu: 0, 100, 300, 400 h = the 0, 10,000, 30,000, 40,000 mcs snapshots of the paper's Fig. 2D (100 mcs = 1 h)
    "08_Mu2024": [("plot_000.00.png", "0 h"), ("plot_100.00.png", "100 h"), ("plot_300.00.png", "300 h"),
                  ("plot_400.00.png", "400 h")],
    "09_Luque2023": [("plot_00.000000.png", "Day 0"), ("plot_30.000000.png", "Day 30"), ("plot_60.000000.png", "Day 60")],
    # Berkhout: the run's Gnuplotter wrote a frame every 3000 MCS (12.5 h); 240 MCS = 1 h. See BERKHOUT_RERUN.
    "10_Berkhout2025": [("plot_00000.000.png", "0 h"), ("plot_03000.000.png", "12.5 h"), ("plot_06000.000.png", "25 h"),
                        ("plot_09000.000.png", "37.5 h"), ("plot_12000.000.png", "50 h")],
    "11_Anlas2024": [("plot_00000.png", "0 h"), ("plot_00048.png", "48 h"), ("plot_00072.png", "72 h")],
    # Malkmus: the six field plots of each frame are rearranged into species columns (malkmus_frames.py)
    "12_Malkmus2025": [("plot_00000.png", "0 h"), ("plot_00018.png", "18 h"), ("plot_00036.png", "36 h")],
    "13_Mole2026": [("plot_00000.png", "6 d.p.f."), ("plot_00024.png", "7 d.p.f."), ("plot_00048.png", "8 d.p.f."),
                    ("plot_00072.png", "9 d.p.f.")],  # dpf = 6 + elapsed_hours/24 (model.xml)
    "14_Otsuki2025": [("plot_00.00.png", "Day 0"), ("plot_15.00.png", "Day 15"), ("plot_39.00.png", "Day 39")],
    "15_Reza2025": [("plot_00000.png", "Day 0"), ("plot_04320.png", "Day 3"), ("plot_08640.png", "Day 6")],
}
# Berkhout panel b every 10 h, as the paper's Fig. 1: folder of a re-run of the scored model.xml with only the
# Gnuplotter time-step changed from 3000 to 600 MCS (Morpheus 2.4.1, 1 thread, RandomSeed 42 as scored), holding that
# model.xml and its frames; in the figure folder data/rerun_gnuplot_10h (BERKHOUT_RERUN_LOCAL), or relative to the
# folder that holds the benchmark directory (--runs), or absolute. The build
# stops unless the re-run's model.xml is otherwise identical and its frames at the run's own frame times (FRAMES) are
# byte-identical to the run's (Supp_Fig_10_Berkhout2025/panel.py, b_frames). None: panel b shows the run's own five frames.
BERKHOUT_RERUN = "manuscript_figures/figures/reruns/10_Berkhout2025_gnuplot_10h"
BERKHOUT_RERUN_LOCAL = "rerun_gnuplot_10h"
BERKHOUT_RERUN_FRAMES = [("plot_00000.000.png", "0 h"), ("plot_02400.000.png", "10 h"), ("plot_04800.000.png", "20 h"),
                         ("plot_07200.000.png", "30 h"), ("plot_09600.000.png", "40 h"),
                         ("plot_12000.000.png", "50 h")]
ATWELL_FRAMES = [("018.50", "18.5 hph (initial)"), ("025.47", "25.5 hph"), ("032.44", "32.4 hph"),
                 ("039.41", "39.4 hph"), ("046.38", "46.4 hph"), ("053.35", "53.3 hph")]
# crop of a frame to one Gnuplotter sub-plot, as fractions (x0, x1[, y0, y1]) of the frame width/height
FRAME_CROP = {"03_Carpenter2024": (0.0, 1 / 3), "09_Luque2023": (0.0, 1 / 3),
              "10_Berkhout2025": (0.0, 0.25), "15_Reza2025": (0.0, 1 / 3, 0.0, 0.5)}  # Reza: top-left sub-plot (cell.type)
# crop in pixels (x0, x1, y0, y1; x1, y1 exclusive), applied after FRAME_CROP:
# - Thapa: the simulation domain inside the yellow WALL cells (frame rows/columns 0 and 599 black, 1-3 and 596-598
#   yellow WALL, 4 and 595 its outline)
# - Carpenter: inside the left sub-plot's frame lines (rows 0 and 399, columns 0 and 400 of the 1200 x 400 frame)
# - Berkemeier: inside the 3-pixel plot frame (columns 20-22 and 711-713, rows 56-58 and 653-655 of the 900 x 703 frame)
# - Herron: the plot area inside the black Gnuplot frame lines (columns 18 and 626, rows 50 and 658 of the 791 x 700
#   frame, with one anti-aliased pixel next to each), without the title, colour bar and x tick
# - Scheel: a blank (pure white in all three frames) 150 x 110 pixel area inside the plot, only a placeholder that
#   sizes the slots; p07_scheel redraws the frames' data as vector line plots over it
# - Mu: inside the frame lines of the right (affinity) sub-plot (columns 809 and 1116, rows 25 and 270 of the
#   1200 x 292 frame), without its title, x label and colour bar
# - Luque: inside the left sub-plot's frame lines (rows 0 and 599, columns 0 and 600 of the 1800 x 600 frame)
# - Berkhout: inside the cell-fate sub-plot's frame lines (columns 0 and 300, rows 0 and 237 of the 1200 x 238 frame);
#   rows 1-65 (medium above the tissue, white in all five frames; the tissue starts at row 78 at the latest) left out
# - Anlas: rows 74-323 of 400 hold the aggregate at every shown time (rows 83-315 at 72 h); columns 0 and 1199 (the
#   outer frame lines) cut off; the sub-plot dividers at columns 400 and 799 are drawn over in grey (p11_anlas)
# - Mole: inside the black (rows/columns 0, 699 and 874) and grey (1, 698 and 873) frame lines of the 875 x 700 frame,
#   i.e. the full 200 x 160-node domain
# - Otsuki: inside the frame lines of the Hand2 sub-plot (x = 14/475, y = 38/222 of the 1200 x 507 frame); the Shh and
#   memory sub-plots are added below it by panels/p14_otsuki.py
# - Reza: the organoids with a 10-pixel margin (their extent in all three frames is x 60-269, y 83-193 of the
#   400 x 268 cell.type sub-plot), well inside the frame lines (rows 25/247, columns 9/317), so the Gnuplot title and
#   the 0-3 colour bar of the cell.type index are dropped too
FRAME_CROP_PX = {"02_Thapa2024": (5, 595, 5, 595), "03_Carpenter2024": (1, 400, 1, 399),
                 "05_Berkemeier2023": (23, 711, 59, 653), "06_Herron2022": (20, 625, 52, 657),
                 "07_Scheel2021": (375, 525, 270, 380), "08_Mu2024": (810, 1116, 26, 270),
                 "09_Luque2023": (1, 600, 1, 599), "10_Berkhout2025": (1, 300, 66, 237),
                 "11_Anlas2024": (1, 1199, 74, 324), "13_Mole2026": (2, 873, 2, 698),
                 "14_Otsuki2025": (15, 475, 39, 222), "15_Reza2025": (50, 280, 73, 204)}
# frames drawn with a thin grey outline (domain boundary once a coloured border is cropped off)
FRAME_OUTLINE = {"02_Thapa2024", "03_Carpenter2024", "05_Berkemeier2023", "06_Herron2022", "08_Mu2024",
                 "09_Luque2023", "10_Berkhout2025", "11_Anlas2024", "13_Mole2026", "14_Otsuki2025", "15_Reza2025"}
# frames per row in panel b (default: all in one row)
FRAME_COLS = {"04_Atwell2025": 2, "08_Mu2024": 2}

# Model graphs: committed .dot files in model_graphs/ (Morpheus 2.4.1, include-tags="#untagged"). Panel c shows the
# reduced graph (ModelGraph reduced="true") of every paper; the full graphs are on the model-graph pages.
# GRAPH_REDUCE_ASPECT only sizes the panel-c slot (graphs wider than this get a wider slot), so panels a, b and d
# keep their size.
GRAPH_REDUCE_ASPECT = 3.2

# Digitised paper data (paper_data/, headerless WebPlotDigitizer x,y CSVs unless noted)
PAPER_DATA = {
    "01_Szabo2010": ["01_Szabo2010/monolayer.csv"],  # single_cell.csv not used (see captions)
    # Thapa: Model 4 points of Fig. 4D read from the PDF by thapa_fig4d_extract.py (cached copy
    # fig4D_model4_points.csv, headed); cells counted in Fig. 4B iv and Suppl. Fig. S12 (fig4Biv_cell_counts.csv,
    # headed)
    "02_Thapa2024": ["02_Thapa2024/fig4D_model4_points.csv", "02_Thapa2024/fig4Biv_cell_counts.csv"],
    # Carpenter: data points of Fig. 2A taken from the published PDF's vector graphics (carpenter_fig2a_extract.py)
    "03_Carpenter2024": ["03_Carpenter2024/fig2A_apoptosis_on_vector.csv"],
    # Berkemeier: no CSV; the Fig. 1f pattern is counted from the PDF's vector fills on every build
    # (berkemeier_fig1f_extract.py)
    "05_Berkemeier2023": [],
    "08_Mu2024": ["08_Mu2024/total.csv", "08_Mu2024/DZ.csv", "08_Mu2024/LZ.csv", "08_Mu2024/mean_affinity.csv"],
    # Luque: daily values of the Fig. 10b mean lines extracted from the PDF's raster (luque_fig10b_extract.py)
    "09_Luque2023": ["09_Luque2023/fig10b_hepatocytes.csv", "09_Luque2023/fig10b_cancer.csv"],
    # Berkhout: one run of the authors' CompuCell3D model, rerun by co-author L.B. (not published data)
    "10_Berkhout2025": ["10_Berkhout2025/compucell3d_rerun_timecourse.csv"],
    "11_Anlas2024": ["11_Anlas2024/Bra_T.csv", "11_Anlas2024/Sox_2.csv"],
    # Atwell: Table S2 read from the PDF's text by atwell_tables2_extract.py (cached copy, headed)
    "04_Atwell2025": ["04_Atwell2025/tableS2_counts.csv"],
}
