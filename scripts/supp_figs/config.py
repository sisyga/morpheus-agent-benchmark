"""All inputs of the paper-comparison supplementary figures, in one place.

Paths are relative to the benchmark directory (--runs), to the repository root (paper PDFs) or to this
folder (paper_data/, model_graphs/). Everything the figures show is defined here or in panels/*.py.
"""

BENCHMARK = "20261007_202940_benchmark"
ATTEMPT = "attempts/attempt_001"  # scored attempt of every run
MODEL = "gpt-6.1-sol"
MODE_LABEL = {"morpheus_cli": "Morpheus CLI", "morpheus_cli_docs": "Morpheus CLI + docs",
              "morpheus_skill": "Morpheus Skill", "morpheus_mcp": "Morpheus MCP"}

# Shown run per paper: best run of the mode scheme (papers 1-2 MCP, 3-6 Skill, 7-10 MCP, 11-13 Skill,
# 14-15 MCP). score = judge score of that run; Luque corrected by hand to 0.83 (judge error).
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
PANEL_A = {
    "01_Szabo2010": dict(title="Szabó et al. (2010), Fig. 10a–d", crops=[(9, (50, 70, 546, 438), "")], rows=[[0]]),
    "02_Thapa2024": dict(title="Thapa et al. (2024), Fig. 4B iv (Model 4; 24, 72, 120 h) and Fig. 4D",
                         crops=[(5, (108, 453.8, 482, 561), ""), (5, (262, 572, 492, 703), "")], rows=[[0, 1]]),
    "03_Carpenter2024": dict(title="Carpenter et al. (2024), Fig. 2A, D, E–F",
                             crops=[(4, (60, 52, 178, 168), ""), (4, (402, 55, 520, 168), ""),
                                    (4, (55, 165, 550, 393), "")], rows=[[0, 1, 2]]),
    "04_Atwell2025": dict(title="Atwell et al. (2015), Fig. 3", crops=[(3, (320, 290, 550, 650), "")], rows=[[0]]),
    "05_Berkemeier2023": dict(title="Berkemeier & Page (2023), Fig. 1a–f (target: 1f, ε = 1)",
                              crops=[(2, (72, 48, 524, 360), "")], rows=[[0]]),
    "06_Herron2022": dict(title="Herron et al. (2022), Fig. 2A, 2C–D and Fig. 4F",
                          crops=[(5, (66, 72, 230, 242), "Fig. 2A"), (5, (68, 249, 588, 394), "Fig. 2C, D"),
                                 (10, (412, 505, 596, 655), "Fig. 4F (target)")], rows=[[0, 1, 2]]),
    "07_Scheel2021": dict(title="Scheel et al. (2021), Fig. 2 (target: cutting → regeneration) and Fig. 5",
                          crops=[(4, (42, 50, 396, 406), "Fig. 2"), (13, (40, 50, 398, 208), "Fig. 5")],
                          rows=[[0, 1]]),
    "08_Mu2024": dict(title="Mu et al. (2024), Fig. 2A–D", crops=[(4, (94, 214, 502, 558), "")], rows=[[0]]),
    "09_Luque2023": dict(title="Luque et al. (2023), Fig. 10a, b",
                         crops=[(16, (88, 75, 575, 232), ""), (16, (88, 232, 340, 380), "")], rows=[[0, 1]]),
    "10_Berkhout2025": dict(title="Berkhout et al. (2025), Fig. 1", crops=[(2, (66, 50, 528, 240), "")], rows=[[0]]),
    "11_Anlas2024": dict(title="Anlas et al. (2024), Fig. 1A–E and Fig. 4B",
                         crops=[(2, (68, 48, 542, 378), "Fig. 1A–E"), (6, (322, 82, 545, 177), "Fig. 4B")],
                         rows=[[0], [1]]),
    "12_Malkmus2025": dict(title="Malkmus et al. (2025), Fig. 5A, C (wild type)",
                           crops=[(7, (98, 50, 506, 166), ""), (7, (98, 266, 506, 376), "")], rows=[[0], [1]]),
    "13_Mole2026": dict(title="Mole et al. (2026), Fig. 3A", crops=[(7, (92, 118, 276, 277), "")], rows=[[0]]),
    "14_Otsuki2025": dict(title="Otsuki et al. (2025), Fig. 5f", crops=[(6, (40, 376, 585, 508), "")], rows=[[0]]),
    "15_Reza2025": dict(title="Reza et al. (2025), Fig. 1a, b and Fig. 4g–i",
                        crops=[(2, (60, 48, 540, 300), "Fig. 1a, b"), (6, (33, 384, 568, 558), "Fig. 4g–i")],
                        rows=[[0], [1]]),
}

# Panel b: frames of the run's own Gnuplotter output, starting at the initial state: (file, label).
# Atwell uses 3D renders made by atwell_3d.py from the run's lattice checkpoints (see ATWELL_FRAMES).
FRAMES = {
    "01_Szabo2010": [("plot_00000.png", "t = 0 MCS"), ("plot_00360.png", "t = 360 MCS (6 h)"),
                     ("plot_01440.png", "t = 1440 MCS (24 h)")],
    "02_Thapa2024": [("plot_000.00000.png", "t = 0 h"), ("plot_048.00000.png", "t = 48 h"),
                     ("plot_120.00000.png", "t = 120 h")],
    "03_Carpenter2024": [("plot_0000.0000.png", "t = 0"), ("plot_4050.0000.png", "t = 18 τ$_0$"),
                         ("plot_7875.0000.png", "t = 35 τ$_0$")],
    "05_Berkemeier2023": [("plot_000.0000.png", "t = 0"), ("plot_010.0000.png", "t = 10"),
                          ("plot_100.0000.png", "t = 100")],
    "06_Herron2022": [("plot_00.00000.png", "t = 0 s"), ("plot_10.00000.png", "t = 10 s"),
                      ("plot_40.00000.png", "t = 40 s")],
    "07_Scheel2021": [("fields_raw_plot_x_paper_s_00.00000.png", "t = 0"),
                      ("fields_raw_plot_x_paper_s_05.00000.png", "t = 5"),
                      ("fields_raw_plot_x_paper_s_10.00000.png", "t = 10")],
    "08_Mu2024": [("plot_000.00.png", "t = 0 h"), ("plot_100.00.png", "t = 100 h"), ("plot_200.00.png", "t = 200 h"),
                  ("plot_400.00.png", "t = 400 h")],
    "09_Luque2023": [("plot_00.000000.png", "day 0"), ("plot_30.000000.png", "day 30"), ("plot_60.000000.png", "day 60")],
    "10_Berkhout2025": [("plot_00000.000.png", "t = 0 h"), ("plot_03000.000.png", "t = 12.5 h"),
                        ("plot_12000.000.png", "t = 50 h")],
    "11_Anlas2024": [("plot_00000.png", "t = 0 h"), ("plot_00036.png", "t = 36 h"), ("plot_00072.png", "t = 72 h")],
    "12_Malkmus2025": [("plot_00000.png", "t = 0 h"), ("plot_00018.png", "t = 18 h"), ("plot_00036.png", "t = 36 h")],
    "13_Mole2026": [("plot_00000.png", "6 d.p.f."), ("plot_00048.png", "8 d.p.f."), ("plot_00072.png", "9 d.p.f.")],
    "14_Otsuki2025": [("plot_00.00.png", "day 0"), ("plot_15.00.png", "day 15"), ("plot_39.00.png", "day 39")],
    "15_Reza2025": [("plot_00000.png", "day 0"), ("plot_04320.png", "day 3"), ("plot_08640.png", "day 6")],
}
ATWELL_FRAMES = [("018.50", "18.5 hph (initial)"), ("025.47", "25.5 hph"), ("032.44", "32.4 hph"),
                 ("039.41", "39.4 hph"), ("046.38", "46.4 hph"), ("053.35", "53.3 hph")]
# crop of a frame to one Gnuplotter sub-plot, as fractions (x0, x1[, y0, y1]) of the frame width/height
FRAME_CROP = {"03_Carpenter2024": (0.0, 1 / 3), "08_Mu2024": (0.672, 1.0, 0.075, 1.0), "09_Luque2023": (0.0, 1 / 3),
              "10_Berkhout2025": (0.0, 0.25), "15_Reza2025": (0.006, 0.333, 0.035, 0.5)}  # y0: below the clipped title (rows 3-16 of 536), above the frame
# frames per row in panel b (default: all in one row)
FRAME_COLS = {"04_Atwell2025": 2, "08_Mu2024": 2}

# Model graphs: committed .dot files in model_graphs/ (Morpheus 2.4.1, include-tags="#untagged").
# Graphs wider than GRAPH_REDUCE_ASPECT use the reduced graph (ModelGraph reduced="true") if that is narrower.
GRAPH_REDUCE_ASPECT = 3.2
GRAPH_MIN_TEXT_PT = 5.0  # graphs whose text is smaller in panel c get a landscape page
GRAPH_PAGE_REDUCED = {"10_Berkhout2025"}  # landscape page shows the reduced graph (full one is too large)

# Digitised paper data (paper_data/, headerless WebPlotDigitizer x,y CSVs unless noted)
PAPER_DATA = {
    "01_Szabo2010": ["1_Szabo_2010/monolayer.csv"],  # single_cell.csv not used (see captions)
    "02_Thapa2024": ["2_Thappa_2024/model_4.csv"],
    "03_Carpenter2024": ["3_Carpenter_2024/apoptosis_on.csv"],
    # Berkemeier: curves extracted from the PDF's vector paths (berkemeier_fig4a_extract.py; cached copy in
    # 5_Berkemier/fig4a_vector_paths.csv); the digitised 5_Berkemier/delta_activity.csv is no longer used
    "05_Berkemeier2023": ["5_Berkemier/fig4a_vector_paths.csv"],
    "08_Mu2024": ["8_Mu/total.csv", "8_Mu/DZ.csv", "8_Mu/LZ.csv", "8_Mu/mean_affinity.csv"],
    "09_Luque2023": ["9_Luque_2023/hepatocytes.csv", "9_Luque_2023/cancer.csv"],
    "10_Berkhout2025": ["10_Berkhout_2025/My_cNTC_timecourse_hours.csv"],
    "11_Anlas2024": ["11_Anlas/Bra_T.csv", "11_Anlas/Sox_2.csv"],
}

# Atwell et al. (2015) Table S2, single run of Fig. 3
ATWELL_TABLE_S2 = {
    "time_hph": [18.5, 27.5, 30.5, 32.5, 33.5, 35.5, 60.5, 87.5],
    "yellow": [16, 113, 147, 184, 174, 228, 366, 314],
    "green": [0, 8, 85, 80, 76, 57, 143, 178],
    "blue": [0, 0, 0, 38, 38, 152, 111, 47],
    "pink": [0, 0, 0, 0, 36, 69, 60, 83],
}
