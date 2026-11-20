"""Stage 3 (order 10): run-command difference table, FINALTRAIN (method run) vs this run, per scene and run (CPU, reads command.json / cfg_args only).
Rows: every training argument (after the entry script) and every docker -e variable / image / fork mount that differs; equal arguments are counted.
table cmd_diff (+ cmd_diff_summary)."""
import sys
sys.path.insert(0, '/repo/scripts/phd/main_gttarget_v1')
from gt_common import *
def parse(cmd):
    env = {cmd[i+1].split('=', 1)[0]: cmd[i+1].split('=', 1)[1] for i in range(len(cmd)-1) if cmd[i] == '-e'}
    mounts = {cmd[i+1].rsplit(':', 2)[1]: cmd[i+1].rsplit(':', 2)[0] for i in range(len(cmd)-1) if cmd[i] == '-v'}
    image = cmd[cmd.index('--entrypoint')+2]; k = next(i for i, x in enumerate(cmd) if x == '-s'); args = {}; i = k
    while i < len(cmd):
        if cmd[i].startswith('-'):
            j = i+1; vals = []
            while j < len(cmd) and not (cmd[j].startswith('-') and not cmd[j].lstrip('-').replace('.', '').isdigit()): vals.append(cmd[j]); j += 1
            args[cmd[i]] = ' '.join(vals); i = j
        else: i += 1
    return env, mounts, image, args, cmd[k-2] if k >= 2 else ''
rows, summ = [], []
PATHY = {'-s', '-m'}
for stem in STEMS:
    site, prior = stem.split('__'); ftc = json.loads((FT/'runs'/site/f'ft_{prior}_s0/attempt1/command.json').read_text())
    for run in sorted(p.name for p in (O/'runs'/stem).iterdir() if (p/'command.json').exists()):
        gc = json.loads((O/'runs'/stem/run/'command.json').read_text()); a, b = parse(ftc), parse(gc); same = 0; diff = 0
        keys = list(dict.fromkeys(list(a[3])+list(b[3])))
        for k in keys:
            va, vb = a[3].get(k), b[3].get(k)
            if va == vb: same += 1; continue
            if k in PATHY: va_, vb_ = va, vb; kind = '경로(출력 위치)' if k == '-m' else '경로'
            else: kind = '학습 인자'
            diff += 1; rows.append(dict(title=TITLE, stem=stem, run=run, what=kind, key=k, finaltrain=va, this_run=vb))
        for k in sorted(set(a[0]) | set(b[0])):
            if a[0].get(k) != b[0].get(k): rows.append(dict(title=TITLE, stem=stem, run=run, what='환경 변수', key=k, finaltrain=a[0].get(k), this_run=b[0].get(k)))
        rows.append(dict(title=TITLE, stem=stem, run=run, what='이미지', key='image', finaltrain=a[2], this_run=b[2], equal=a[2] == b[2]))
        rows.append(dict(title=TITLE, stem=stem, run=run, what='포크', key='/source', finaltrain=a[1].get('/source', '').split('/')[-1], this_run=b[1].get('/source', '').split('/')[-1]))
        fa = (FT/'runs'/site/f'ft_{prior}_s0/attempt1/model/cfg_args').read_text().replace('/out/runs/'+site+f'/ft_{prior}_s0/attempt1/model', 'M')
        fb = (O/'runs'/stem/run/'model/cfg_args').read_text().replace(f'/gt/runs/{stem}/{run}/model', 'M') if (O/'runs'/stem/run/'model/cfg_args').exists() else None
        summ.append(dict(title=TITLE, stem=stem, run=run, train_args_equal=same, train_args_different=diff, cfg_args_equal_except_model_path=fa == fb, image_equal=a[2] == b[2]))
table('cmd_diff', rows); table('cmd_diff_summary', summ); print('CMD', len(rows), summ, flush=True)
