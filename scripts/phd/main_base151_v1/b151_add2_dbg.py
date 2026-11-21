"""addendum 2 debug (read-only): which cell-3 image differs between the recomputed 25 % rule and cells.json. scientific_verdict: null"""
import json, sys
sys.path.insert(0, '/b151s')
import numpy as np
from b151_add2 import cams, CJ, coverage, TU1
cm = cams(); sp = json.loads((TU1 / 'scenes/campus/split.json').read_text())
c = CJ['cells'][3]; elo, ehi = c['expanded_min'], c['expanded_max']
pos = [n for n in sp['train'] if elo[0] <= cm[n]['C'][0] < ehi[0] and elo[1] <= cm[n]['C'][1] < ehi[1]]
for n in sp['train']:
    if n in pos: continue
    f = coverage(cm[n], c['projection_box_min'], c['projection_box_max'])
    if abs(f - .25) < .01 or ((f >= .25) != (n in c['images'])): print(n, repr(f), n in c['images'])
pj = TU1 / 'scenes/campus/poses.json'; p = json.loads(pj.read_text()); print(type(p), str(p)[:600])
