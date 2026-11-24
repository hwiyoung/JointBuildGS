"""Gaussian count per recorded iteration (every 100 iterations, target_monitor/curve.jsonl = training record) for 판 0, 1, 2, 3, 4, 9 (and 판 0 seed 1), all scenes
(host python, stdlib). writes docs/tables/gaussians_per_iteration.csv (long: stem, run, iteration, gaussians, loss, rgb_loss, target_depth_loss) and a wide csv."""
import json, csv
from pathlib import Path
R = Path(__file__).resolve().parents[3]; O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'; T = R/'docs/experiments/phd/main_depthfix_v1/tables'
ARMS = ('p0', 'p1', 'p2', 'p3', 'p4', 'p9'); long, wide = [], {}
for d in sorted((O/'runs').glob('*/*')):
    if d.name.split('_s')[0] not in ARMS or not (d/'receipt.json').exists(): continue
    st = json.loads((d/'receipt.json').read_text())['status']; f = d/'model/target_monitor/curve.jsonl'
    if not f.exists(): continue
    for l in f.read_text().splitlines():
        r = json.loads(l); long.append(dict(stem=d.parent.name, run=d.name, status=st, iteration=r['iteration'], gaussians=r['gaussians'], loss=r['loss'], rgb_loss=r['rgb_loss'], target_depth_loss=r['target_depth_loss']))
        wide.setdefault(r['iteration'], {})[f'{d.parent.name}__{d.name}'] = r['gaussians']
with (T/'gaussians_per_iteration.csv').open('w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(long[0]), lineterminator='\n'); w.writeheader(); w.writerows(long)
cols = sorted({k for v in wide.values() for k in v})
with (T/'gaussians_per_iteration_wide.csv').open('w', newline='') as fh:
    w = csv.writer(fh, lineterminator='\n'); w.writerow(['iteration'] + cols)
    for it in sorted(wide): w.writerow([it] + [wide[it].get(c, '') for c in cols])
print(len(long), len(cols))
