"""Host queue (python stdlib only): trainings in the locked order of config 'runs', then per finished run its three extractions
(base, occl10, occlga). One GPU (config concurrency.gpu), at most config concurrency.max_trainings trainings at once.
Admission (PRESCRIBE-v1 traps): docker-workloads.slice memory.current + need <= SLICE_CAP, host MemAvailable >= 20 GiB, disk >= 40 GiB,
GPU free >= 7 GiB for a training, >= 4 min since the last training start. Mesh lane: one at a time, needs 22 GiB slice headroom; a waiting extraction keeps the third training slot free (steady state 2 trainings + 1 extraction).
usage: python3 df_queue.py [first_index] [last_index]   (indices into config runs; default all)
State: O/queue/{status.jsonl,running.json}. A run whose folder already exists is skipped (never overwritten)."""
import json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from launch import O, C, now
import df_train
SLICE = Path('/sys/fs/cgroup/docker.slice/docker-workloads.slice'); SLICE_CAP = 56 << 30; G = 1 << 30
cfg = json.loads((C/'depthfix_v1.json').read_text()); runs = cfg['runs']; GPU = cfg['concurrency']['gpu']; MAXT = cfg['concurrency']['max_trainings']
Q = O/'queue'; Q.mkdir(parents=True, exist_ok=True); LOCK = threading.Lock(); ACTIVE = {}; MESHQ = []; MESHING = []
def note(**k):
    with LOCK, (Q/'status.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), **k), ensure_ascii=False)+'\n')
def slice_used(): return int((SLICE/'memory.current').read_text())
def mem_avail():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable'): return int(l.split()[1]) << 10
def disk_free(): return shutil.disk_usage(O).free
def gpu_free():
    out = subprocess.check_output(['nvidia-smi', f'--id={GPU}', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True); return int(out.strip()) << 20
def ok_train(): return slice_used() + 15*G <= SLICE_CAP and mem_avail() >= 20*G and disk_free() >= 40*G and gpu_free() >= 7*G
def ok_mesh(): return slice_used() + 22*G <= SLICE_CAP and mem_avail() >= 24*G and disk_free() >= 30*G and gpu_free() >= 4*G
def do_train(arm, stem, seed):
    run = f'{arm}_s{seed}'; note(step='train_start', arm=arm, stem=stem, seed=seed)
    try: rc = df_train.train(arm, stem, seed, GPU)
    except Exception as e: rc = -1; note(step='train_exception', arm=arm, stem=stem, seed=seed, error=repr(e))
    rec = O/'runs'/stem/run/'receipt.json'; st = json.loads(rec.read_text())['status'] if rec.exists() else 'NO_RECEIPT'
    note(step='train_end', arm=arm, stem=stem, seed=seed, rc=rc, status=st)
    with LOCK:
        ACTIVE.pop(run+stem, None)
        if st == 'COMPLETED': MESHQ.extend([f'{stem}:{run}:{v}' for v in ['base', 'occl10', 'occlga']])
def do_mesh(spec):
    note(step='mesh_start', spec=spec)
    rc = subprocess.run([sys.executable, str(Path(__file__).parent/'df_mesh.py'), '1', spec], stdout=open(O/'logs'/f'mesh_{spec.replace(":", "_")}.log', 'a'), stderr=subprocess.STDOUT).returncode
    stem, run, v = spec.split(':'); ok = (O/'meshes'/f'{stem}__df_{run}_{v}'/'score.json').exists()
    note(step='mesh_end', spec=spec, rc=rc, scored=ok)
    with LOCK: MESHING.remove(spec)
def main(a=0, b=None):
    todo = [r for r in runs[int(a):(int(b)+1 if b is not None else None)]]; last = 0
    note(step='queue_start', runs=todo, pid=os.getpid())
    while todo or ACTIVE or MESHQ or MESHING:
        with LOCK: nact = len(ACTIVE); mesh_wait = bool(MESHQ) and not MESHING
        if todo and nact < MAXT and not (mesh_wait and nact >= MAXT - 1) and time.time() - last >= 240 and ok_train():
            arm, stem, seed = todo.pop(0); run = f'{arm}_s{seed}'
            if (O/'runs'/stem/run).exists(): note(step='skip_exists', arm=arm, stem=stem, seed=seed); continue
            with LOCK: ACTIVE[run+stem] = True
            threading.Thread(target=do_train, args=(arm, stem, seed), daemon=False).start(); last = time.time(); continue
        with LOCK: can = MESHQ and not MESHING
        if can and ok_mesh():
            with LOCK: spec = MESHQ.pop(0); MESHING.append(spec)
            threading.Thread(target=do_mesh, args=(spec,), daemon=False).start(); time.sleep(30); continue
        (Q/'running.json').write_text(json.dumps(dict(at=now(), active=list(ACTIVE), todo=todo, meshq=MESHQ, meshing=MESHING, slice_gib=slice_used()/G, disk_gib=disk_free()/G), ensure_ascii=False))
        time.sleep(30)
    note(step='queue_done')
if __name__ == '__main__': main(*sys.argv[1:])
