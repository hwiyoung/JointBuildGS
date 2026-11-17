"""Host queue for the addendum-5 record runs (addendum5_b.json, locked): the addendum-4 sb5 command (kind sbsigned) with the addendum-5 region files.
Each run starts on a GPU with >= 14 GiB free and no other addendum-4/5 training (own queue + running containers); waits and writes receipts per run.
  python3 a5_train.py queue <run> [<run> ...]"""
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addendum4'))
import a4_launch as A, a4_train as T
A5O = A.O/'addendum5'
CFG = json.loads((A.R/'configs/phd/main_trainerr_v1/addendum5_b.json').read_text())
def args_for(run):
    r = CFG['runs'][run]; T.RUNS[run] = (r['site'], r['prior'], 'sbsigned'); T.SB_REGION[run] = r['region']
    a, env, site = T.args_for(run); i = a.index('-m'); a[i+1] = f'/te/addendum5/runs/{site}/{run}/attempt1/model'
    a += EXTRA.get(run, []); return a, env, site
EXTRA = {}
def running():
    out = set()
    for base, pre in [(A.A4O, 'jbgs-te-a4-'), (A5O, 'jbgs-te-a5-')]:
        for l in (base/'runs').glob('*/*/attempt1/launch.json'):
            if subprocess.run(['docker', 'ps', '-q', '-f', f'name=^{pre}{l.parent.parent.name}$'], capture_output=True, text=True).stdout.strip(): out.add(json.loads(l.read_text())['gpu'])
    return out
def free(busy):
    busy = set(busy) | running(); q = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout.split('\n')
    return [int(i) for i, f in (x.split(', ') for x in q if x.strip()) if int(f) >= 14*1024 and int(i) not in busy]
def one(run, gpu):
    args, env, site = args_for(run); root = A5O/'runs'/site/run/'attempt1'; root.mkdir(parents=True, exist_ok=False)
    cmd = A.command(f'jbgs-te-a5-{run}', 'addendum5/a5_train_entry.py', args, gpu=gpu, env=env, split_site=site)
    cmd = [x.replace('=/te/addendum4/tmp', '=/te/addendum5/tmp') for x in cmd]
    A.dump(root/'command.json', cmd); A.dump(root/'launch.json', dict(at=A.now(), gpu=gpu, run=run, rule=CFG['gpu_rule'], scientific_verdict=None))
    f = (root/'train.log').open('x'); return subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT), f, root
def queue(runs):
    procs = []; todo = list(runs)
    while todo or any(p.poll() is None for _, p, *_ in procs):
        for gpu, p, run, root, t0, f in procs:
            if p.poll() is not None and not (root/'receipt.json').exists():
                f.close(); ok = p.returncode == 0 and (root/'TRAINING_COMPLETE.json').exists()
                A.dump(root/'receipt.json', dict(at=A.now(), exit_code=p.returncode, seconds=time.monotonic()-t0, status='COMPLETED' if ok else 'ERROR', scientific_verdict=None)); print('DONE', run, p.returncode, flush=True)
        if todo:
            g = free({g for g, p, *_ in procs if p.poll() is None})
            if g:
                run = todo.pop(0); p, f, root = one(run, g[0]); procs.append((g[0], p, run, root, time.monotonic(), f)); print('STARTED', run, 'gpu', g[0], A.now(), flush=True); time.sleep(120); continue
        time.sleep(60)
    for gpu, p, run, root, t0, f in procs:
        if not (root/'receipt.json').exists():
            f.close(); ok = p.returncode == 0 and (root/'TRAINING_COMPLETE.json').exists()
            A.dump(root/'receipt.json', dict(at=A.now(), exit_code=p.returncode, seconds=time.monotonic()-t0, status='COMPLETED' if ok else 'ERROR', scientific_verdict=None)); print('DONE', run, p.returncode, flush=True)
if __name__ == '__main__':
    assert sys.argv[1] == 'queue'; queue(sys.argv[2:])
