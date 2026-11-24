"""Order 8: per run, the training command against the 판 0 command of the same scene (and against FINALTRAIN-v1), host python stdlib.
Compares the train.py argument list of runs/<stem>/<run>/command.json with runs/<stem>/p0_s0/command.json. writes docs/tables/cmd_diff.csv/json"""
import json, csv
from pathlib import Path
R = Path(__file__).resolve().parents[3]; O = R.parent/'JointBuildGS-artifacts/phase-payloads/phd/main_depthfix_v1/PHD-MAIN-DEPTHFIX-v1'; D = R/'docs/experiments/phd/main_depthfix_v1'
def args(p):
    c = json.loads(p.read_text()); i = c.index('df_entry.py') if 'df_entry.py' in c else c.index([x for x in c if x.endswith('df_entry.py')][0]); return c[i+1:]
rows = []
for st in sorted((O/'runs').iterdir()):
    base = st/'p0_s0'/'command.json'
    for run in sorted(st.iterdir()):
        if not (run/'command.json').exists() or run.name.startswith(('offcheck', 'smoke')): continue
        a, b = args(run/'command.json'), args(base) if base.exists() else []
        diff = [f'{x} → {y}' for x, y in zip(b, a) if x != y] + ([f'길이 {len(b)} → {len(a)}'] if len(a) != len(b) else [])
        la = json.loads((run/'launch.json').read_text())
        rows.append(dict(stem=st.name, run=run.name, gpu=la.get('gpu'), differs_from_p0=' ; '.join(diff) if diff else '(같음)',
                         differs_from_finaltrain=' ; '.join(f"{d['finaltrain']} → {d['this']}" for d in la.get('args_diff_vs_finaltrain', []))))
keys = list(rows[0]); (D/'tables').mkdir(exist_ok=True)
with (D/'tables/cmd_diff.csv').open('w', newline='') as f: w = csv.DictWriter(f, fieldnames=keys, lineterminator='\n'); w.writeheader(); w.writerows(rows)
(D/'tables/cmd_diff.json').write_text(json.dumps(dict(rows=rows, note='판마다 다른 것은 판 이름(df_entry 첫 인자), 학습 폴더(-m), 목표 폴더(--jbgs_target_dir), 씨앗뿐인지 확인용', scientific_verdict=None), ensure_ascii=False, indent=1)+'\n')
print(len(rows)); [print(r['stem'], r['run'], r['gpu'], r['differs_from_p0'][:200]) for r in rows]
