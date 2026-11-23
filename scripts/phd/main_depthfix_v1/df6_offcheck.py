"""Order 2 off-check (host python, json only): all switches off + FINALTRAIN target file (arm ftoff), R1 x ALS, 1,000 iterations, seeds 0 and 1,
against the FINALTRAIN-v1 record (ft_ALS_s0 target_monitor/curve.jsonl).
Exact equality is not expected (PRESCRIBE-v1 issues 11-20: from-scratch GPU training is not bit-reproducible).
Criterion (PRESCRIBE-v1 p2_offcheck_within rule with the seed-1 off run in place of a second recorded seed):
per recorded iteration <= 1000 and value (gaussians, loss, rgb_loss, target_depth_loss): |off_s0 − FT_s0| <= |off_s1 − FT_s0|; and the camera sequence of off_s0 equals FT_s0."""
import json
from pathlib import Path
R = Path(__file__).resolve().parents[3]; PH = R.parent/'JointBuildGS-artifacts/phase-payloads/phd'; O = PH/'main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'; D = R/'docs/experiments/phd/main_depthfix_v1'
def curve(p): return {r['iteration']: r for r in map(json.loads, Path(p).read_text().splitlines()) if r['iteration'] <= 1000}
ft = curve(PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs/R1rep_b10/ft_ALS_s0/attempt1/model/target_monitor/curve.jsonl')
a = curve(O/'runs/R1rep_b10__ALS/offcheck_s0/model/target_monitor/curve.jsonl'); b = curve(O/'runs/R1rep_b10__ALS/offcheck_s1/model/target_monitor/curve.jsonl')
rows = []; keys = ['gaussians', 'loss', 'rgb_loss', 'target_depth_loss']
for it in sorted(ft):
    for k in keys:
        d0 = abs(a[it][k]-ft[it][k]); d1 = abs(b[it][k]-ft[it][k])
        rows.append(dict(iteration=it, value=k, finaltrain_s0=ft[it][k], off_s0=a[it][k], off_s1=b[it][k], abs_off_s0_minus_ft=d0, abs_off_s1_minus_ft=d1, within=d0 <= d1, exact=a[it][k] == ft[it][k]))
cams = all(a[it]['camera'] == ft[it]['camera'] for it in ft)
res = dict(task='PHD-MAIN-DEPTHFIX-v1', check='switches off = FINALTRAIN-v1 (order 2)', iterations=sorted(ft), values=len(rows), within=sum(r['within'] for r in rows), exact=sum(r['exact'] for r in rows),
           camera_sequence_equal=cams, passed=bool(cams and all(r['within'] for r in rows)), rule=__doc__, rows=rows, scientific_verdict=None)
(D/'tables').mkdir(parents=True, exist_ok=True); (D/'tables/offcheck.json').write_text(json.dumps(res, ensure_ascii=False, indent=1)+'\n')
import csv
with (D/'tables/offcheck.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); w.writeheader(); w.writerows(rows)
print(json.dumps({k: res[k] for k in ['values', 'within', 'exact', 'camera_sequence_equal', 'passed']}))
