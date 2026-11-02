# Molè height rerun (Fig. 2e iv)

`13_Mole_model.xml` is the scored model of the Molè run shown in Fig. 2e (GPT-6.1 Sol, setup 4, repetition 3;
`figures/Supplementary/Supp_Fig_13_Mole2026/data/20261013_173228_13_Mole2026__morpheus_skill__rep03__replacement02/attempts/attempt_001/model.xml`)
with one Logger added that writes the height of the epithelium and of the blastocyst's lowest point every hour
(`logger_height.csv`). It was saved from the Morpheus 2.4.1 GUI, which also converted the file from MorpheusML 4
to 5 (Morpheus's own correction of the division-plane attribute, the title, Gnuplotter colours and a
`ModelGraph` tag); the random seed (1729) and all mechanisms are unchanged. `logger_height.csv` is the Logger
output of running it with Morpheus 2.4.1; `../../make_plots_de.py` draws Fig. 2e iv from it.
