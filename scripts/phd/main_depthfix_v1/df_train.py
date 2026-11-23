"""Host side: one training run. train <arm> <stem> <seed> <gpu> [stop_after] [run]
Arguments = FINALTRAIN-v1 command (attempt1/command.json of the same stem) with only -m, --jbgs_target_dir and --jbgs_seed changed."""
import json, re, sys
from pathlib import Path
from launch import O, C, command, run, dump, now

def ft_args(stem):
    site, prior = stem.split('__')
    cmd = json.loads((O.parent.parent/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1/runs'/site/f'ft_{prior}_s0/attempt1/command.json').read_text())
    i = cmd.index('/repo/scripts/phd/main_finaltrain_v1/train_entry.py'); a = cmd[i+3:]
    assert a[0] == '-s'; return a

def train(arm, stem, seed, gpu, stop_after='0', run_name=None):
    seed = int(seed); stop = int(stop_after); run_name = run_name or f'{arm}_s{seed}'
    root = O/'runs'/stem/run_name; root.mkdir(parents=True, exist_ok=False); model = f'/df/runs/{stem}/{run_name}/model'
    a = ft_args(stem); base = list(a)
    a[a.index('-m')+1] = model; a[a.index('--jbgs_target_dir')+1] = f'/df/arms/{arm}/stage1/{stem}'; a[a.index('--jbgs_seed')+1] = str(seed)
    diff = [dict(i=i, finaltrain=x, this=y) for i, (x, y) in enumerate(zip(base, a)) if x != y]
    cmd = command(re.sub(r'[^a-zA-Z0-9_.-]', 'x', f'jbgs-depthfix-train-{stem}-{run_name}'), 'df_entry.py', [arm, stem, run_name, str(stop)] + a, gpu=int(gpu), cpus=8, memory='40g',
                  split_site=stem.split('__')[0])
    dump(root/'command.json', cmd); dump(root/'launch.json', dict(at=now(), gpu=int(gpu), arm=arm, stem=stem, run=run_name, seed=seed, stop_after=stop, args_diff_vs_finaltrain=diff, scientific_verdict=None))
    rc, s = run(cmd, root/'train.log'); stopf = root/'model/target_monitor/STOP.json'
    done = (root/'TRAINING_COMPLETE.json').exists() or (root/'PROBE_COMPLETE.json').exists()
    status = 'COMPLETED' if rc == 0 and done else ('HEALTH_STOP' if stopf.exists() else 'ERROR')
    rec = dict(at=now(), arm=arm, stem=stem, run=run_name, seed=seed, exit_code=rc, seconds=s, status=status, health=json.loads(stopf.read_text()) if stopf.exists() else None, scientific_verdict=None)
    dump(root/'receipt.json', rec); print(json.dumps(rec, ensure_ascii=False), flush=True); return rc
