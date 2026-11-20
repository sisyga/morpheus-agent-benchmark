"""Seed ensemble for Supp. Fig. 5 d (time courses): copies of the shown Berkemeier model.xml in which only
(1) RandomSeed = 1..10 (seed 1 = the scored run),
(2) StopTime 100 -> 20 and the output intervals 100/99 -> 20/99 tau_N (Logger, ClusteringTracker) and
    100 -> 20 (ContactLogger), so that the agent's scripts/analyze_run.py (which expects 100 logged states from
    start to stop) runs unchanged at ~0.2 tau_N resolution,
(3) the External command (agent's Linux path; analyze_run.py is run afterwards) and the Gnuplotter (frames) are
    removed. Usage: python setup_runs_t20.py <shown model.xml> <out dir>"""
import re, sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
out = pathlib.Path(sys.argv[2])
subs = [('<RandomSeed value="1" />', None),
        ('<StopTime value="100" />', '<StopTime value="20" />'),
        ('<Logger time-step="100/99">', '<Logger time-step="20/99">'),
        ('<ContactLogger time-step="100"', '<ContactLogger time-step="20"'),
        ('<ClusteringTracker time-step="100/99"', '<ClusteringTracker time-step="20/99"')]
base = src
for old, new in subs:
    assert base.count(old) == 1, old
    if new:
        base = base.replace(old, new)
base = re.sub(r'\s*<External time-step="0">.*?</External>', '', base, flags=re.S)
base = re.sub(r'\s*<Gnuplotter .*?</Gnuplotter>', '', base, flags=re.S)
assert '<External' not in base and '<Gnuplotter' not in base
for seed in range(1, 11):
    d = out / f'seed_{seed:02d}'
    d.mkdir(parents=True, exist_ok=True)
    (d / 'model.xml').write_text(base.replace('<RandomSeed value="1" />', f'<RandomSeed value="{seed}" />'),
                                 encoding='utf-8')
print('ok')
