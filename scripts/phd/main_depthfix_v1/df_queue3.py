"""Host queue v3 (2026-11-24 09:40, user decision: two GPUs, base extraction first, up to two extraction lanes; else as v2). Original docstring: Host queue v2 (replaces df_queue.py from 2026-11-24 09h; same run order, same training command via df_train.train).
Changes: (1) admission counts the docker-workloads slice as anon + shmem (memory.stat), not memory.current, which includes reclaimable page cache
(issues 18: the v1 rule kept every extraction waiting for 2 h with 34.5 GiB of cache); (2) at start it adopts runs whose folder exists without a receipt
(trainings started by v1 keep running in their own containers): it waits until the container is gone and writes the same receipt as df_train;
(3) the extraction queue = every completed run (receipt COMPLETED) with a missing score, in config run order; one extraction at a time.
Admission: training if slice used + 15 GiB <= 56 GiB, MemAvailable >= 20 GiB, disk >= 40 GiB, GPU free >= 7 GiB, >= 4 min since last start, < max_trainings;
an extraction waiting keeps the third training slot free; extraction if slice used + 20 GiB <= 56 GiB, GPU free >= 4 GiB."""
import json, os, shutil, subprocess, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from launch import O, C, now, dump
import df_train
SLICE = Path('/sys/fs/cgroup/docker.slice/docker-workloads.slice'); CAP = 56 << 30; G = 1 << 30
cfg = json.loads((C/'depthfix_v1.json').read_text()); RUNS = cfg['runs']; GPUS = cfg['concurrency']['gpus']; MAXT = cfg['concurrency']['max_trainings']
Q = O/'queue'; LOCK = threading.Lock(); ACTIVE = {}; MESHING = []; VARS = ['base', 'occl10', 'occlga']
def note(**k):
    with LOCK, (Q/'status.jsonl').open('a') as f: f.write(json.dumps(dict(at=now(), queue='v3.6', **k), ensure_ascii=False)+'\n')
def used():
    st = dict(l.split() for l in (SLICE/'memory.stat').read_text().splitlines()); return int(st['anon']) + int(st['shmem'])
def avail():
    for l in open('/proc/meminfo'):
        if l.startswith('MemAvailable'): return int(l.split()[1]) << 10
GPU_OF = {}   # active training key -> gpu
def gpu_free(g): return int(subprocess.check_output(['nvidia-smi', f'--id={g}', '--query-gpu=memory.free', '--format=csv,noheader,nounits'], text=True).strip()) << 20
def pick_gpu(need):
    c = [(sum(1 for v in GPU_OF.values() if v == g), -gpu_free(g), g) for g in GPUS if gpu_free(g) >= need]; return min(c)[2] if c else None
def ok_train(): return used() + 15*G <= CAP and avail() >= 20*G and shutil.disk_usage(O).free >= 40*G and pick_gpu(7*G) is not None
def ok_mesh(): return used() + 20*G <= CAP and avail() >= 22*G and shutil.disk_usage(O).free >= 30*G and pick_gpu(4*G) is not None
def running(name): return name in subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).split()
def gpu_of_container(name):
    try: return json.loads(subprocess.check_output(['docker', 'inspect', name], text=True))[0]['HostConfig']['DeviceRequests'][0]['DeviceIDs'][0]
    except Exception: return None
def adopt(arm, stem, seed):
    run = f'{arm}_s{seed}'; root = O/'runs'/stem/run; name = f'jbgs-depthfix-train-{stem}-{run}'
    while running(name): time.sleep(60)
    done = (root/'TRAINING_COMPLETE.json').exists(); stopf = root/'model/target_monitor/STOP.json'
    st = 'COMPLETED' if done else ('HEALTH_STOP' if stopf.exists() else 'ERROR')
    dump(root/'receipt.json', dict(at=now(), arm=arm, stem=stem, run=run, seed=seed, exit_code=None, seconds=None, status=st, adopted_by='df_queue2',
         health=json.loads(stopf.read_text()) if stopf.exists() else None, scientific_verdict=None))
    note(step='train_end', arm=arm, stem=stem, seed=seed, status=st, adopted=True)
    with LOCK: ACTIVE.pop(run+stem, None); GPU_OF.pop(run+stem, None)
def do_train(arm, stem, seed, gpu):
    note(step='train_start', arm=arm, stem=stem, seed=seed, gpu=gpu)
    try: rc = df_train.train(arm, stem, seed, gpu)
    except Exception as e: rc = -1; note(step='train_exception', arm=arm, stem=stem, seed=seed, error=repr(e))
    rec = O/'runs'/stem/f'{arm}_s{seed}'/'receipt.json'; st = json.loads(rec.read_text())['status'] if rec.exists() else 'NO_RECEIPT'
    note(step='train_end', arm=arm, stem=stem, seed=seed, rc=rc, status=st, gpu=gpu)
    with LOCK: ACTIVE.pop(f'{arm}_s{seed}'+stem, None); GPU_OF.pop(f'{arm}_s{seed}'+stem, None)
TRAIN_LEFT = {'n': 1}
def mesh_todo():
    out = []
    # v3.2 (user 11-24 14:00): base extraction only while any training is queued or running; occl10 / occlga after every training and base extraction
    vars_now = ['base']   # v3.6: no occlusion-excluded extractions (user 11-24 22h)
    for v in VARS:
        if v not in vars_now: continue
        for arm, stem, seed in RUNS:
            run = f'{arm}_s{seed}'; rec = O/'runs'/stem/run/'receipt.json'
            if rec.exists() and json.loads(rec.read_text())['status'] == 'COMPLETED' and not (O/'meshes'/f'{stem}__df_{run}_{v}'/'score.json').exists(): out.append(f'{stem}:{run}:{v}')
    return [s for s in out if s not in MESHING]
def running_meshes():
    out = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True).stdout.splitlines()
    return [l.split()[-1] for l in out if 'df_mesh.py' in l and 'python' in l.split()[0]]
def do_mesh(spec, gpu):
    note(step='mesh_start', spec=spec, gpu=gpu)
    with open(O/'logs'/f'mesh_{spec.replace(":", "_")}.log', 'a') as lf:
        rc = subprocess.run([sys.executable, str(Path(__file__).parent/'df_mesh.py'), '1', spec], stdout=lf, stderr=subprocess.STDOUT, env=dict(os.environ, DF_MESH_GPU=str(gpu))).returncode
    stem, run, v = spec.split(':'); note(step='mesh_end', spec=spec, rc=rc, scored=(O/'meshes'/f'{stem}__df_{run}_{v}'/'score.json').exists())
    with LOCK: MESHING.remove(spec)
def wait_mesh(spec):
    while spec in running_meshes(): time.sleep(30)
    stem, run, v = spec.split(':'); note(step='mesh_end', spec=spec, adopted=True, scored=(O/'meshes'/f'{stem}__df_{run}_{v}'/'score.json').exists())
    with LOCK: MESHING.remove(spec)
def main():
    todo = []
    for arm, stem, seed in RUNS:
        root = O/'runs'/stem/f'{arm}_s{seed}'
        if not root.exists(): todo.append((arm, stem, seed))
        elif not (root/'receipt.json').exists():
            ACTIVE[f'{arm}_s{seed}'+stem] = True; threading.Thread(target=adopt, args=(arm, stem, seed)).start()
    for arm, stem, seed in RUNS:
        k = f'{arm}_s{seed}'+stem
        if k in ACTIVE: GPU_OF[k] = int(gpu_of_container(f'jbgs-depthfix-train-{stem}-{arm}_s{seed}') or 0)
    for spec in running_meshes():
        MESHING.append(spec); threading.Thread(target=wait_mesh, args=(spec,)).start()
    note(step='queue_start', adopted=list(ACTIVE), adopted_gpu=GPU_OF, adopted_meshes=list(MESHING), todo=todo, pid=os.getpid()); last = time.time(); failed = {}
    while todo or ACTIVE or mesh_todo() or MESHING:
        with LOCK:
            nact = len(ACTIVE); TRAIN_LEFT['n'] = len(todo) + nact
            if TRAIN_LEFT['n'] == 0 and any(x.endswith(':base') for x in mesh_todo()): TRAIN_LEFT['n'] = 0
            mt = mesh_todo(); base_left = any(x.endswith(':base') for x in mt)
            if TRAIN_LEFT['n'] == 0 and base_left: mt = [x for x in mt if x.endswith(':base')]
            waiting = [s for s in mt if failed.get(s, 0) < 2]
        if waiting and len(MESHING) < (2 if nact <= 1 else 1) and ok_mesh():   # v3.1: one extraction lane while 2+ trainings run (issues 22)
            spec = waiting[0]; failed[spec] = failed.get(spec, 0) + 1; g = pick_gpu(4*G)
            with LOCK: MESHING.append(spec)
            threading.Thread(target=do_mesh, args=(spec, g)).start(); time.sleep(60); continue
        def startable(x): return x[0] not in ('p9', 'p10', 'p11') or ((Q/'gate_cells_sent').exists() and (O/'arms'/x[0]/'stage1'/x[1]/'ready.json').exists() and (x[0] != 'p10' or (Q/'gate_p10_ok').exists()))
        # v3.4: 판 10 waits for the user's answer (issues 28); meanwhile the next startable run in order (판 11) may go first
        if todo and not startable(todo[0]):
            j_ = next((j for j, x in enumerate(todo) if x[0] in ('p2', 'p3', 'p4') and startable(x)), None) if todo[0][0] == 'p10' else None   # v3.5: while 판 10 waits, remaining 판 2·3·4 (user 11-24 16h)
            if j_ is not None: todo.insert(0, todo.pop(j_))
        nxt_ok = bool(todo) and startable(todo[0])
        if todo and nxt_ok and nact < MAXT and time.time() - last >= 240 and ok_train():
            arm, stem, seed = todo.pop(0); g = pick_gpu(7*G)
            with LOCK: ACTIVE[f'{arm}_s{seed}'+stem] = True; GPU_OF[f'{arm}_s{seed}'+stem] = g
            threading.Thread(target=do_train, args=(arm, stem, seed, g)).start(); last = time.time(); continue
        (Q/'running.json').write_text(json.dumps(dict(at=now(), queue='v3.6', active=list(ACTIVE), todo=todo, meshq=mt, meshing=MESHING, used_gib=used()/G,
                                                  disk_gib=shutil.disk_usage(O).free/G), ensure_ascii=False))
        time.sleep(30)
    note(step='queue_done')
if __name__ == '__main__': main()
