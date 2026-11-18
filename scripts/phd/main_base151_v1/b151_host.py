#!/usr/bin/env python3
"""PHD-MAIN-BASE151-v1 training queue on GPU 1 (host side; only stdlib, docker and nvidia-smi).

  nohup python3 b151_host.py queue > OUT/logs/queue.log 2>&1 &
  python3 b151_host.py status

Rules (configs/phd/main_base151_v1/base151_v1.json gpu, rerun_rule):
  - one cell at a time on GPU 1, runs in config training_order, cells 0, 1, 2, 3; only runs whose method has a ready marker
    OUT/scenes/<method>[_<prior>]/READY.json are taken (inputs of the other methods are still being built);
  - launch when GPU 1 has >= 12 GiB free and host MemAvailable >= 45 GB; the CUDA cap of the attempt = GPU 1 free at launch - 2 GiB;
  - watchdog every 10 s: host MemAvailable < 25 GB -> stop this task's post-processing containers; < 20 GB -> kill the training
    container (snapshot recorded); GPU 1 free < 1.5 GiB -> STOP file (the entry saves and exits); < 0.75 GiB -> kill;
  - a paused cell resumes from its checkpoint (not a stop); a host-guard stop or a CUDA out-of-memory is rerun once with the same setting,
    a second stop is final ('NO_RESULT'); any other error stops the queue (QUEUE_HALTED.json) for the cause check (order 1.9);
  - no launch (new cell or resume) at or after 2026-11-24 00:00 KST; control/QUEUE_STOP ends the queue after the running cell;
    control/HOLD_GPU holds new launches while this task's own GPU preprocessing (DA3) runs on GPU 1.
  - when the four cells of a run are complete: merge (CPU container) -> OUT/runs/<run>/merged/point_cloud.ply.
scientific_verdict: null
"""
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[3]
C = W / 'configs/phd/main_base151_v1'
D = W / 'docs/experiments/phd/main_base151_v1'
ART = (W.parent / 'JointBuildGS-artifacts').resolve()
PH = ART / 'phase-payloads/phd'
OUT = PH / 'main_base151_v1/PHD-MAIN-BASE151-v1'
TU1 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
SCRIPTS = W / 'scripts/phd/main_base151_v1'
KST = dt.timezone(dt.timedelta(hours=9))
GPU = 1
START_GB, FLOOR_GB, POST_FLOOR_GB = 45, 20, 25
NEED_MIB, PAUSE_MIB, KILL_MIB, MARGIN_MIB = 12 * 1024, 1536, 768, 2048
DEADLINE = dt.datetime(2026, 11, 24, 0, 0, tzinfo=KST)


def now():
    return dt.datetime.now(KST)


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(8 << 20), b''):
            h.update(b)
    return h.hexdigest()


def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=1) + '\n')
    os.replace(tmp, p)


def progress(s):
    with (D / 'progress.md').open('a') as f:
        f.write(f'- {now().isoformat(timespec="seconds")}: {s}\n')


def issue(s):
    with (D / 'issues.md').open('a') as f:
        f.write(f'- {now().isoformat(timespec="seconds")}: {s}\n')


def cfg():
    lock = json.loads((C / 'base151_v1.lock.json').read_text())
    assert sha(C / 'base151_v1.json') == lock['config_sha256'], 'base151_v1.json changed after lock'
    return json.loads((C / 'base151_v1.json').read_text())


def gpu_free_mib(gpu=GPU):
    out = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    return int(out.strip().splitlines()[0])


def gpu_apps(gpu=GPU):
    uuid = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=uuid', '--format=csv,noheader'], capture_output=True, text=True).stdout.strip()
    out = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_memory,process_name', '--format=csv,noheader'], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.startswith(uuid)]


def avail_gb():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable'):
            return int(line.split()[1]) / 2 ** 20
    return 0.0


def running(name):
    r = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', name], capture_output=True, text=True)
    return r.stdout.strip() == 'true'


def snapshot():
    st = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.Name}}\t{{.MemUsage}}'], capture_output=True, text=True).stdout
    ps = subprocess.run(['ps', '-eo', 'pid,rss,comm', '--sort=-rss'], capture_output=True, text=True).stdout.splitlines()[:15]
    return dict(docker=st.splitlines()[:40], ps=ps)


def stop_post_containers():
    names = subprocess.run(['docker', 'ps', '--format', '{{.Names}}'], capture_output=True, text=True).stdout.split()
    hit = [n for n in names if n.startswith(('jbgs-b151-cpu-', 'jbgs-b151-post-'))]
    for n in hit:
        subprocess.run(['docker', 'kill', n], capture_output=True)
    return hit


# ---------------------------------------------------------------- jobs

def method_spec(c, run):
    r = next(x for x in c['runs'] if x['name'] == run)
    m = r['method']
    spec = dict(run=run, method=m, prior=r['prior'], cells=r['cells'])
    if m == '2DGS':
        spec.update(ready=OUT / 'scenes/2DGS/READY.json', dim='2D', image=c['methods']['2DGS']['image'],
                    source=ART / c['methods']['2DGS']['source']['path'], args=c['methods']['2DGS']['train_args'][1:],
                    cpus='16', memory='48g', shm='8g')
    else:
        add = C / f'inputs_{m}.json'
        spec.update(ready=OUT / 'scenes' / f'{m}_{r["prior"]}' / 'READY.json', addendum=add)
    return spec


def cell_mounts(spec, k):
    m = spec['method']
    if m == '2DGS':
        scene = OUT / 'scenes/2DGS' / f'cell{k}'
        (scene / 'images').mkdir(exist_ok=True)   # mount point of the campus images (read-only)
        return [(scene, '/scene', 'ro'), (TU1 / 'scenes/campus/images', '/scene/images', 'ro'), (scene / 'split.json', '/split.json', 'ro')], \
            ['JBGS_SPLIT_JSON=/split.json']
    add = json.loads(spec['addendum'].read_text())   # inputs_<method>.json: per-cell mounts and env, locked before use
    lk = json.loads((C / f'inputs_{m}.lock.json').read_text())
    assert sha(spec['addendum']) == lk['config_sha256'], f'inputs_{m}.json changed after lock'
    run_spec = add['runs'][spec['run']]
    spec.update(dim=add['dim'], image=add['image'], source=ART / add['source'], args=run_spec['args'], cpus=add['cpus'], memory=add['memory'], shm=add['shm'],
                no_alloc_conf=bool(add.get('no_alloc_conf')), attempt_scene=run_spec.get('attempt_scene'))
    mounts = [(ART / p if not str(p).startswith('/') else Path(p), d, mode) for p, d, mode in
              [(x[0].replace('<k>', str(k)), x[1], x[2]) for x in run_spec['mounts']]]
    return mounts, [e.replace('<k>', str(k)) for e in run_spec.get('env', [])]


def command(spec, k, attempt_dir, cap_gib, resume=None):
    mounts, env = cell_mounts(spec, k)
    if spec.get('attempt_scene'):
        # CDGS writes plydummy/ and confidence_map/ into its scene: a per-attempt copy of the template with links to the read-only inputs
        import shutil
        a = spec['attempt_scene']
        shutil.copytree(ART / a['template'].replace('<k>', str(k)), attempt_dir / 'scene')
        for nm, target in a['links'].items():
            os.symlink(target, attempt_dir / 'scene' / nm)
    name = f'jbgs-b151-train-{spec["run"]}-cell{k}-{attempt_dir.name}'.replace('_', '-').lower()
    cmd = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--user', f'{os.getuid()}:{os.getgid()}', '--gpus', f'device={GPU}',
           '--cpus', spec['cpus'], '--memory', spec['memory'], '--memory-swap', spec['memory'], '--shm-size', spec['shm'], '--oom-score-adj', '300']
    base = ['PYTHONUNBUFFERED=1', 'PYTHONDONTWRITEBYTECODE=1', 'HOME=/tmp', 'MPLCONFIGDIR=/tmp/mpl', 'OMP_NUM_THREADS=16', 'TORCH_HOME=/tmp/torch',
            f'JBGS_GPU_CAP_GIB={cap_gib:.3f}', 'TZ=Asia/Seoul']
    if not spec.get('no_alloc_conf'):
        base.append('PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True')
    keys = {e.split('=', 1)[0] for e in env}
    for e in [b for b in base if b.split('=', 1)[0] not in keys] + env:
        cmd += ['-e', e]
    for s, d, mode in [(spec['source'], '/source', 'ro')] + mounts + [(attempt_dir, '/o', 'rw'), (SCRIPTS, '/b151s', 'ro'), (OUT / 'control', '/control', 'ro')] + \
            ([(resume.parent.parent, '/prev', 'ro')] if resume else []):
        cmd += ['-v', f'{s}:{d}:{mode}']
    args = list(spec['args'])
    if resume:
        args += ['--start_checkpoint', f'/prev/{resume.parent.name}/{resume.name}']
    cmd += ['-w', '/source', '--entrypoint', 'python', spec['image'], '-u', '/b151s/b151_entry.py', spec['run'], str(k), spec['dim'], 'train.py'] + args
    return name, cmd


def cell_dir(run, k):
    return OUT / 'runs' / run / f'cell{k}'


def receipt(run, k):
    p = cell_dir(run, k) / 'receipt.json'
    return json.loads(p.read_text()) if p.exists() else dict(name=f'{run}_cell{k}', status='PENDING', attempts=[])


def last_checkpoint(run, k):
    rec = receipt(run, k)
    for a in reversed(rec['attempts']):
        if a['status'] == 'PAUSED_SAVED':
            p = Path(a['pause']['checkpoint'].replace('/o/', str(cell_dir(run, k) / f'attempt{a["attempt"]}') + '/'))
            return p if p.exists() else None
        if a['status'] != 'PAUSED_SAVED':
            return None
    return None


def attempt(spec, k):
    c = cfg()
    run = spec['run']
    rec = receipt(run, k)
    n = len(rec['attempts']) + 1
    adir = cell_dir(run, k) / f'attempt{n}'
    adir.mkdir(parents=True, exist_ok=False)
    resume = last_checkpoint(run, k)
    free = gpu_free_mib()
    cap = (free - MARGIN_MIB) / 1024
    name, cmd = command(spec, k, adir, cap, resume)
    (OUT / 'control').mkdir(exist_ok=True)
    stopfile = OUT / 'control' / f'STOP_{run}_cell{k}'
    if stopfile.exists():
        stopfile.unlink()
    dump(adir / 'launch.json', dict(at=now().isoformat(), run=run, cell=k, attempt=n, gpu=GPU, gpu_free_MiB_at_launch=free, cap_GiB=cap,
                                    gpu_apps_at_launch=gpu_apps(), host_available_GiB=avail_gb(), resume_from=str(resume) if resume else None,
                                    command=cmd, config_sha256=sha(C / 'base151_v1.json'), scientific_verdict=None))
    log = OUT / 'logs' / f'train_{run}_cell{k}_a{n}.log'
    start = time.monotonic()
    with open(log, 'w') as f:
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
    progress(f'{run} 칸 {k} 시도 {n} 시작(GPU {GPU} 남은 {free} MiB, 상한 {cap:.2f} GiB{", 이어 돌림 " + resume.name if resume else ""})')
    guard = gpause = gkill = None
    post_stopped = []
    min_avail, min_free = avail_gb(), free
    time.sleep(20)
    while p.poll() is None:
        av = avail_gb()
        min_avail = min(min_avail, av)
        if av < POST_FLOOR_GB:
            hit = stop_post_containers()
            if hit:
                post_stopped.append(dict(at=now().isoformat(), available_GiB=av, containers=hit))
        if av < FLOOR_GB and guard is None:
            guard = dict(at=now().isoformat(), available_GiB=av, floor_GiB=FLOOR_GB, snapshot=snapshot())
            subprocess.run(['docker', 'kill', name], capture_output=True)
        fr = gpu_free_mib()
        min_free = min(min_free, fr)
        if fr < PAUSE_MIB and gpause is None:
            gpause = dict(at=now().isoformat(), gpu_free_MiB=fr, apps=gpu_apps())
            stopfile.touch()
        if fr < KILL_MIB and gkill is None:
            gkill = dict(at=now().isoformat(), gpu_free_MiB=fr, apps=gpu_apps())
            subprocess.run(['docker', 'kill', name], capture_output=True)
        time.sleep(10)
    rc = p.returncode
    secs = time.monotonic() - start
    if stopfile.exists():
        stopfile.unlink()
    err = json.loads((adir / 'ERROR.json').read_text()) if (adir / 'ERROR.json').exists() else None
    lines = (adir / 'trace1000.jsonl').read_text().splitlines() if (adir / 'trace1000.jsonl').exists() else []
    if (adir / 'TRAINING_COMPLETE.json').exists() and rc == 0:
        st = 'TRAINING_COMPLETE'
    elif (adir / 'PAUSE.json').exists():
        st = 'PAUSED_SAVED'
    elif gkill:
        st = 'GPU_SHARE_KILL'
    elif guard:
        st = 'HOST_GUARD_STOP'
    elif err and err.get('oom'):
        st = 'CUDA_OOM'
    elif rc == 137:
        st = 'KILLED_137'
    else:
        st = 'ERROR'
    a = dict(at=now().isoformat(), attempt=n, gpu=GPU, exit_code=rc, seconds=secs, status=st, error=err, cap_GiB=cap, gpu_free_MiB_at_launch=free,
             last_trace=json.loads(lines[-1]) if lines else None, host_guard=guard, post_stopped=post_stopped, min_host_available_GiB=min_avail,
             gpu_pause=gpause, gpu_kill=gkill, min_gpu_free_MiB=min_free, resume_from=str(resume) if resume else None,
             pause=json.loads((adir / 'PAUSE.json').read_text()) if (adir / 'PAUSE.json').exists() else None, log=str(log), scientific_verdict=None)
    rec['attempts'].append(a)
    rec['status'] = st
    rec['at'] = now().isoformat()
    dump(cell_dir(run, k) / 'receipt.json', rec)
    progress(f'{run} 칸 {k} 시도 {n} 끝: {st} ({secs / 3600:.2f} h, 종료 코드 {rc}, 호스트 가용 최저 {min_avail:.1f} GiB, GPU 1 남은 최저 {min_free} MiB)')
    if st not in ('TRAINING_COMPLETE', 'PAUSED_SAVED'):
        issue(f'{run} 칸 {k} 시도 {n} 멈춤: {st}' + (f' — {err["error"][:300]}' if err else '') + f' (기록 {log})')
    return st


def stops(run, k):
    # GPU_SHARE_KILL is GPU sharing protection (TRAINUNIT-v2: not a stop under order 1.9)
    return [a for a in receipt(run, k)['attempts'] if a['status'] not in ('TRAINING_COMPLETE', 'PAUSED_SAVED', 'GPU_SHARE_KILL') and not a.get('fixed')]


def merge(run):
    out = OUT / 'runs' / run / 'merged/point_cloud.ply'
    if out.exists():
        return True
    log = OUT / 'logs' / f'merge_{run}.log'
    with open(log, 'a') as f:
        rc = subprocess.run(['bash', str(SCRIPTS / 'run_cpu.sh'), f'merge-{run}'.replace('_', '-').lower(), '8', '48g', 'b151_post.py', 'merge', run],
                            stdout=f, stderr=subprocess.STDOUT).returncode
    progress(f'{run} 합치기 {"끝" if rc == 0 else "실패"}')
    return rc == 0


def wait_launch():
    held = False
    while True:
        if (OUT / 'control/QUEUE_STOP').exists() or now() >= DEADLINE:
            return False
        if list((OUT / 'control').glob('HOLD_GPU*')):   # this task's own short GPU job (DA3, smoke test) has GPU 1; no cell launch meanwhile
            if not held:
                progress('대기열: HOLD_GPU — 이 작업의 GPU 전처리가 끝날 때까지 새 칸을 걸지 않음')
                held = True
            time.sleep(60)
            continue
        fr, av = gpu_free_mib(), avail_gb()
        if fr >= NEED_MIB and av >= START_GB:
            return True
        time.sleep(60)


def queue():
    c = cfg()
    dump(OUT / 'jobs/queue_start.json', dict(at=now().isoformat(), pid=os.getpid(), order=c['training_order'], scientific_verdict=None))
    progress(f'대기열 시작 (pid {os.getpid()})')
    while True:
        did = False
        for run in c['training_order']:
            spec = method_spec(c, run)
            if not spec['ready'].exists():
                continue
            for k in spec['cells']:
                while True:
                    rec = receipt(run, k)
                    if rec['status'] in ('TRAINING_COMPLETE', 'NO_RESULT', 'NEEDS_CHECK'):
                        break
                    if not wait_launch():
                        progress('대기열: 멈춤 파일 또는 11/24 00:00 — 새 칸을 걸지 않음')
                        return
                    st = attempt(spec, k)
                    did = True
                    if st in ('TRAINING_COMPLETE', 'PAUSED_SAVED', 'GPU_SHARE_KILL'):
                        continue
                    if st == 'ERROR':
                        rec = receipt(run, k)
                        rec['status'] = 'NEEDS_CHECK'
                        dump(cell_dir(run, k) / 'receipt.json', rec)
                        dump(OUT / 'control/QUEUE_HALTED.json', dict(at=now().isoformat(), run=run, cell=k, reason='non-OOM error: cause check (order 1.9)',
                                                                     scientific_verdict=None))
                        progress(f'대기열 멈춤: {run} 칸 {k} 오류 — 까닭 확인 필요')
                        return
                    if len(stops(run, k)) >= 2:
                        rec = receipt(run, k)
                        rec['status'] = 'NO_RESULT'
                        dump(cell_dir(run, k) / 'receipt.json', rec)
                        progress(f'{run} 칸 {k}: 두 번째 멈춤 → 결과 없음')
                        break
            recs = [receipt(run, k) for k in spec['cells']]
            if all(r['status'] == 'TRAINING_COMPLETE' for r in recs):
                merge(run)
        if not did:
            if all(method_spec(c, r)['ready'].exists() and all(receipt(r, k)['status'] in ('TRAINING_COMPLETE', 'NO_RESULT', 'NEEDS_CHECK')
                                                                for k in method_spec(c, r)['cells']) for r in c['training_order']):
                progress('대기열: 모든 판 끝')
                return
            if (OUT / 'control/QUEUE_STOP').exists() or now() >= DEADLINE:
                return
            time.sleep(300)


def status():
    c = cfg()
    for run in c['training_order']:
        for k in [0, 1, 2, 3]:
            r = receipt(run, k)
            print(run, k, r['status'], [(a['attempt'], a['status'], round(a['seconds'] / 3600, 2)) for a in r['attempts']])


if __name__ == '__main__':
    dict(queue=queue, status=status)[sys.argv[1]]()
