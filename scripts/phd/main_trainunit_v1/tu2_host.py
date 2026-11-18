"""PHD-MAIN-TRAINUNIT-v2 host side (only docker/nvidia-smi/stdlib on the host).

  nohup python3 tu2_host.py queue > PH2/logs/queue.log 2>&1 &     # GPU 1 only, one run at a time, ORDER below
  python3 tu2_host.py jobs

Queue rules (trainunit_v2.json gpu): start only when nvidia-smi -i 1 shows no compute process (display excepted) and host
MemAvailable >= 45 GB; follow the container; host guard kills this task's container below 20 GB (snapshot of memory users
recorded); order v2 1.8: a host-guard stop gets one rerun with the same config; any other stop is left for the cause check
(no automatic rerun) and the queue goes on; a second stop of a run is final ('결과 없음').
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import tu_host as H
from tu_host import FT, IMAGE, PH, R, S0, dump, gpu_busy, now, train_args

TU1 = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
TU = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v2'
D = R / 'docs/experiments/phd/main_trainunit_v1/v2'
GPU = 1
FLOOR_GB, START_GB = 20, 45
# GPU 1 shared with TRAINERR (user 2026-11-17): start when GPU 1 has >= 14 GiB free; this task's CUDA memory capped at 9 GiB
# (TRAINERR starts a run only on a GPU with >= 14 GiB free); watchdog: free < 1.5 GiB -> save state at the next 100 and stop,
# free < 0.75 GiB -> kill; a paused run resumes from its saved state later (not counted as a stop under order 1.8).
NEED_MIB, CAP_GIB, PAUSE_MIB, KILL_MIB = 14 * 1024, 9, 1536, 768


def gpu_free_mib(gpu=1):
    out = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-gpu=memory.free', '--format=csv,noheader,nounits'], capture_output=True, text=True).stdout
    return int(out.strip().splitlines()[0])
H.D = D   # tu_host.progress / issue write the v2 docs


def progress(s):
    D.mkdir(parents=True, exist_ok=True)
    with (D / 'progress.md').open('a') as f:
        f.write(f'- {now().isoformat()}: {s}\n')


def issue(s):
    with (D / 'issues.md').open('a') as f:
        f.write(f'- {now().isoformat()}: {s}\n')


SITE = dict(B0='B0_b10', R1rep='R1rep_b10', B173nb='B173nb_b10')
# cells with most training images first (cells.json images_per_cell), then the building-unit LoD2 runs
CELL_ORDER = [4, 1, 7, 6, 8, 5, 3, 0, 2]
# user decision 2026-11-17: cells outside every evaluation box are not trained (configs/.../trainunit_v2_skip.json)
SKIP9 = json.loads((Path(__file__).resolve().parents[3] / 'configs/phd/main_trainunit_v1/trainunit_v2_skip.json').read_text())['skip_cells9']
CELL_ORDER = [k for k in CELL_ORDER if k not in SKIP9]
LOD2 = [f'{s}ef_LoD2_s{seed}' for seed in [0, 1] for s in ['R1rep', 'B173nb', 'B0']]
LOD2_KEYS = [f'{"ef" if r.endswith("s0") else "efs1"}_{SITE[r.split("ef_")[0]]}_LoD2' for r in LOD2]
# user decision 2026-11-17: the six building-unit LoD2 runs are not trained (existing no-filter runs are the LoD2 reference)
_SK = json.loads((Path(__file__).resolve().parents[3] / 'configs/phd/main_trainunit_v1/trainunit_v2_skip.json').read_text())
LOD2_Q, LOD2_KEYS_Q = ([], []) if _SK.get('skip_lod2_building') else (LOD2, LOD2_KEYS)
# POST steps run in the queue so that no mesh job overlaps a training (host memory, v1 lesson); render needs GPU 1 free
ORDER = (['POST:render:campusef30k_ALS_s0', 'POST:finish:campusef30k_ALS_s0'] + [f'cells9ef_ALS_s0_cell{k}' for k in CELL_ORDER]
         + ['POST:merge9', 'POST:render:cells9ef_ALS_s0', 'POST:finish:cells9ef_ALS_s0', 'POST:tables:ga'] + LOD2_Q
         + [f'POST:render:{k}' for k in LOD2_KEYS_Q] + [f'POST:finish:{k}' for k in LOD2_KEYS_Q] + ['POST:tables:final'])
JOBS = {f'cells9ef_ALS_s0_cell{k}': dict(scene=f'/tu/scenes/cell{k}/scene_ALS', split=f'/tu/scenes/cell{k}/split.json', target=f'/tu/stage1/cell{k}__ALS',
                                         ready=TU / f'stage1/cell{k}__ALS/ready.json', memory='48g', seed=0) for k in range(9)}
JOBS |= {f'{s}ef_LoD2_s{seed}': dict(scene=f'/p/fork_inputs/s61/{SITE[s]}/scene_LoD2', split=f'/p/fork_inputs/s61/{SITE[s]}/split.json',
                                     target=f'/ft/stage1/{SITE[s]}__LoD2', ready=FT / f'stage1/{SITE[s]}__LoD2/ready.json', memory='40g', seed=seed)
         for s in SITE for seed in [0, 1]}


def cap_of(name):
    """GPU cap of a run: control/gpu_cap_by_run.json overrides CAP_GIB (3.5 fix of cells9ef_ALS_s0_cell8 attempt 1, 2026-11-18:
    the 9 GiB cap of the GPU sharing stopped it with 14 GiB of GPU 1 free; not a method value)."""
    f = TU / 'control/gpu_cap_by_run.json'
    return json.loads(f.read_text()).get(name, CAP_GIB) if f.exists() else CAP_GIB


def command(gpu, name, script, args, split, memory, cap=None):
    """tu_host.command with /tu = v2 payload (rw), /tu1 = v1 payload (ro) and the v2 entry; everything else unchanged."""
    cmd = H.command(gpu, name, script, args, split, memory)
    j = cmd.index('--shm-size') + 2
    cmd[j:j] = ['-e', f'JBGS_GPU_CAP_GIB={CAP_GIB if cap is None else cap}']
    i = cmd.index(f'{H.TU}:/tu:rw')
    cmd[i] = f'{TU}:/tu:rw'
    cmd[i + 1:i + 1] = ['-v', f'{TU1}:/tu1:ro']
    assert f'{H.TU}:/tu:rw' not in cmd and f'{TU1}:/tu1:ro' in cmd
    return cmd


def avail_gb():
    for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable'):
            return int(line.split()[1]) / 1048576
    return 0.


def running(cname):
    r = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', cname], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip() == 'true'


def memory_snapshot():
    st = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{.Name}}\t{{.MemUsage}}'], capture_output=True, text=True).stdout
    ps = subprocess.run(['ps', '-eo', 'pid,rss,comm', '--sort=-rss'], capture_output=True, text=True).stdout.splitlines()[:15]
    mi = {l.split(':')[0]: l.split(':')[1].strip() for l in open('/proc/meminfo') if l.split(':')[0] in ('MemTotal', 'MemAvailable', 'Cached', 'Shmem', 'SwapFree')}
    return dict(at=now().isoformat(), docker_stats=st.strip().splitlines(), top_rss=ps, meminfo=mi)


def next_attempt(run):
    return 1 + max([int(p.name[7:]) for p in run.glob('attempt*') if p.name[7:].isdigit()] + [0])


def attempt(name, run, a):
    j = JOBS[name]
    root = run / f'attempt{a}'
    root.mkdir(parents=True)
    model = '/tu/' + str((root / 'model').relative_to(TU))
    resume = latest_state(run) if paused_before(run) else None
    extra = ['--jbgs_resume_full', '/tu/' + str(resume.relative_to(TU))] if resume else []
    args = [name, *train_args(j['scene'], model, j['target'], j['seed'], 30000, extra)]
    stopfile = TU / 'control' / f'STOP_{name}'
    if stopfile.exists():
        stopfile.unlink()
    cname = f'jbgs-trainunit2-{name.replace("_", "-").lower()}-a{a}'
    cap = cap_of(name)
    cmd = command(GPU, cname, 'tu2_train_entry.py', args, j['split'], j['memory'], cap)
    dump(root / 'command.json', cmd)
    dump(root / 'launch.json', dict(at=now().isoformat(), gpu=GPU, name=name, attempt=a, seed=j['seed'], nvidia_smi_compute_apps=gpu_busy(GPU),
                                   gpu_free_MiB=gpu_free_mib(), cap_GiB=cap, resume_from=str(resume) if resume else None,
                                   host_available_GiB=avail_gb(), scientific_verdict=None))
    progress(f'{name} 시도 {a} 시작, GPU {GPU}')
    start = time.monotonic()
    guard, client_lost, min_avail = None, False, avail_gb()
    gpause = gkill = None
    min_free = gpu_free_mib()
    with (root / 'train.log').open('x') as f:
        proc = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        time.sleep(20)
        while proc.poll() is None or running(cname):
            if proc.poll() is not None:
                client_lost = True
            time.sleep(10)
            av = avail_gb()
            min_avail = min(min_avail, av)
            if av < FLOOR_GB and guard is None:
                guard = dict(at=now().isoformat(), available_GiB=av, floor_GiB=FLOOR_GB, snapshot=memory_snapshot())
                subprocess.run(['docker', 'kill', cname], capture_output=True)
            fr = gpu_free_mib()
            min_free = min(min_free, fr)
            if fr < PAUSE_MIB and gpause is None:
                gpause = dict(at=now().isoformat(), gpu_free_MiB=fr, apps=gpu_busy(GPU))
                stopfile.write_text(now().isoformat())    # tu_train_entry: complete state at the next multiple of 100, then stop
            if fr < KILL_MIB and gkill is None:
                gkill = dict(at=now().isoformat(), gpu_free_MiB=fr, apps=gpu_busy(GPU))
                subprocess.run(['docker', 'kill', cname], capture_output=True)
        rc = proc.returncode
    sec = time.monotonic() - start
    err = json.loads((root / 'ERROR.json').read_text()) if (root / 'ERROR.json').exists() else None
    etext = (err or {}).get('error', '')
    if (root / 'TRAINING_COMPLETE.json').exists():
        st = 'TRAINING_COMPLETE'
    elif gkill:
        st = 'GPU_SHARE_KILL'
    elif gpause and (root / 'DEADLINE_STOP.json').exists():
        st = 'GPU_SHARE_PAUSE_SAVED'
    elif guard:
        st = 'HOST_GUARD_STOP'
    elif 'BINNING_GUARD' in etext or 'out of memory' in etext.lower():
        st = 'GPU_MEMORY_STOP'
    elif (root / 'model/target_monitor/STOP.json').exists() or 'HEALTH_STOP' in etext:
        st = 'HEALTH_STOP'
    elif rc == 137:
        st = 'KILLED_137'
    else:
        st = 'EXECUTION_ERROR'
    trace = root / 'model/jbgs_trace.jsonl'
    lines = trace.read_text().strip().splitlines() if trace.exists() else []
    rec = dict(at=now().isoformat(), attempt=a, gpu=GPU, exit_code=rc, docker_client_lost_container=client_lost, seconds=sec, status=st,
               error=err, last_trace=json.loads(lines[-1]) if lines else None, host_guard=guard, min_host_available_GiB=min_avail,
               gpu_pause=gpause, gpu_kill=gkill, min_gpu_free_MiB=min_free, resume_from=str(resume) if resume else None,
               model=model, scientific_verdict=None)
    if st != 'TRAINING_COMPLETE' and not guard:
        rec['snapshot_after_stop'] = memory_snapshot()
    dump(root / 'receipt.json', rec)
    progress(f'{name} 시도 {a} 끝: {st}, {sec / 3600:.2f}시간' + (f', 오류 {etext[:160]}' if etext else '')
             + (f', 호스트 가용 {guard["available_GiB"]:.1f} GB로 멈춤' if guard else ''))
    return rec


def run_one(name):
    run = TU / 'runs' / name
    old = json.loads((run / 'receipt.json').read_text())['attempts'] if (run / 'receipt.json').exists() else []
    rec = attempt(name, run, next_attempt(run))
    attempts = old + [rec]
    st = rec['status']
    # an attempt whose cause was a fixed config/code fault (order v2 1.8, receipt field 'fixed') is not counted as a stop
    stops = [r for r in attempts if r['status'] not in ('TRAINING_COMPLETE', 'GPU_SHARE_PAUSE_SAVED', 'GPU_SHARE_KILL') and not r.get('fixed')]
    if st == 'TRAINING_COMPLETE':
        final = st
    elif st in ('GPU_SHARE_PAUSE_SAVED', 'GPU_SHARE_KILL'):
        final = 'PAUSED'            # GPU sharing protection: resume later from the saved state
    elif len(stops) >= 2:
        final = 'NO_RESULT'
    elif st == 'HOST_GUARD_STOP':
        final = 'RERUN_QUEUED'      # order v2 1.8: cause = host memory of other users (snapshot); one rerun, same config
    else:
        final = 'CAUSE_CHECK'       # order v2 1.8: cause first (3.5), then fix or one rerun by hand
    dump(run / 'receipt.json', dict(at=now().isoformat(), name=name, status=final, attempts=attempts, scientific_verdict=None))
    if final in ('RERUN_QUEUED', 'PAUSED'):
        (run / 'claim').rmdir()
    if final in ('NO_RESULT', 'CAUSE_CHECK'):
        issue(f'{name}: {final} ({st}). 마지막 기록 {rec.get("last_trace")}, 오류 {(rec.get("error") or {}).get("error", "")[:300]}')


def post_ready(n):
    if n in ('POST:merge9',):
        return all(json.loads(p.read_text())['status'] == 'TRAINING_COMPLETE' if (p := TU / 'runs' / f'cells9ef_ALS_s0_cell{k}' / 'receipt.json').exists() else False for k in CELL_ORDER)
    if n.endswith(':cells9ef_ALS_s0'):
        return (TU / 'runs/cells9ef_ALS_s0/merged/point_cloud.ply').exists()
    for r, k in zip(LOD2, LOD2_KEYS):
        if n.endswith(':' + k):
            p = TU / 'runs' / r / 'receipt.json'
            return p.exists() and json.loads(p.read_text())['status'] == 'TRAINING_COMPLETE'
    return True


def post_blocked(n):
    """A POST step whose runs ended without result is skipped (recorded); one whose runs still train waits."""
    if n == 'POST:merge9' or n.endswith(':cells9ef_ALS_s0'):
        recs = [TU / 'runs' / f'cells9ef_ALS_s0_cell{k}' / 'receipt.json' for k in CELL_ORDER]
        return any(p.exists() and json.loads(p.read_text())['status'] == 'NO_RESULT' for p in recs)
    for r, k in zip(LOD2, LOD2_KEYS):
        if n.endswith(':' + k):
            p = TU / 'runs' / r / 'receipt.json'
            return p.exists() and json.loads(p.read_text())['status'] == 'NO_RESULT'
    return False


def run_post(n):
    here = Path(__file__).resolve().parent
    _, step, *rest = n.split(':')
    log = TU / 'logs' / f'post-{step}-{"-".join(rest) or "x"}.log'
    if step == 'merge9':
        cmd = ['bash', str(here / 'run2_cpu.sh'), 'merge9', '8', '48g', 'tu2_cells.py', 'merge']
    elif step in ('render', 'finish'):
        cmd = ['python3', str(here / 'tu2_post.py'), step, rest[0]]
    else:
        cmd = ['bash', str(here / 'tu2_tables.sh'), rest[0]]
    start = time.monotonic()
    with log.open('a') as f:
        f.write(f'### {now().isoformat()} {n}\n'); f.flush()
        rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=here).returncode
    dump(TU / 'control/post_done' / f'{n.replace(":", "_")}.json', dict(at=now().isoformat(), step=n, exit_code=rc, seconds=time.monotonic() - start, scientific_verdict=None))
    progress(f'{n}: 끝 (exit {rc}, {(time.monotonic() - start) / 60:.1f}분)')
    if rc:
        issue(f'{n}: exit {rc} (기록 {log})')


def paused_before(run):
    p = run / 'receipt.json'
    return p.exists() and json.loads(p.read_text())['status'] == 'PAUSED'


def latest_state(run):
    c = []
    for f in run.glob('attempt*/model/jbgs_complete/iteration_*/checkpoint.pth'):
        c.append((int(f.parent.name.split('_')[1]), f))
    return max(c)[1] if c else None


def claim(run):
    try:
        (run / 'claim').mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        return False


def queue():
    (TU / 'control').mkdir(parents=True, exist_ok=True)
    progress(f'v2 대기열 시작 (GPU {GPU}, pid {os.getpid()}). 차례 {ORDER}')
    waiting = None
    while True:
        if (TU / 'control/QUEUE_STOP').exists():
            progress('v2 대기열 멈춤 파일로 끝.')
            return
        left = [n for n in ORDER if not (TU / 'runs' / n / 'claim').exists() and not (TU / 'control/post_done' / f'{n.replace(":", "_")}.json').exists()]
        if not left:
            progress('v2 대기열: 남은 판 없음, 끝.')
            return
        if left[0].startswith('POST'):
            n = left[0]
            if post_blocked(n):
                dump(TU / 'control/post_done' / f'{n.replace(":", "_")}.json', dict(at=now().isoformat(), step=n, skipped='a run ended without result', scientific_verdict=None))
                issue(f'{n}: 건너뜀(판 결과 없음)')
                continue
            if post_ready(n) and not any((TU / 'runs' / m / 'claim').exists() and not (TU / 'runs' / m / 'receipt.json').exists() for m in JOBS):
                run_post(n)
                continue
            # not ready (runs of this step still in the queue): trainings ahead in ORDER may go on
        todo = [n for n in left if not n.startswith('POST') and JOBS[n]['ready'].exists()]
        busy = gpu_busy(GPU) if gpu_free_mib() < NEED_MIB else []
        if not todo or busy or avail_gb() < START_GB:
            why = 'inputs' if not todo else ('gpu' if busy else 'host')
            if waiting != why:
                progress(f'v2 대기열 기다림: {dict(inputs="입력 준비 중", gpu=f"GPU {GPU}에 다른 프로세스 {busy}", host=f"호스트 가용 {avail_gb():.1f} GB < {START_GB}")[why]}')
                waiting = why
            time.sleep(60)
            continue
        waiting = None
        n = todo[0]
        if not claim(TU / 'runs' / n):
            continue
        try:
            run_one(n)
        except Exception as e:
            issue(f'v2 대기열 {n} 실행기 오류: {type(e).__name__}: {e}')


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'queue':
        queue()
    elif mode == 'jobs':
        for n in ORDER:
            if n.startswith('POST'):
                p = TU / 'control/post_done' / f'{n.replace(":", "_")}.json'
                print(n, post_ready(n), json.loads(p.read_text()) if p.exists() else None)
                continue
            r = TU / 'runs' / n / 'receipt.json'
            print(n, JOBS[n]['ready'].exists(), json.loads(r.read_text())['status'] if r.exists() else None)
    elif mode == 'prepare_lod2':
        # order v2 section 4: commands only. 전체 and 넷 read the v1 LoD2 inputs (/tu1); 아홉 needs its LoD2 inputs first
        # (tu_campus.py seeds/maps/index cell<k> LoD2 through run2_cpu.sh, as tu2_prep.sh does for ALS).
        prep = []
        P = dict(campusef30k_LoD2_s0=dict(scene='/tu1/scenes/campus/scene_LoD2', split='/tu1/scenes/campus/split.json', target='/tu1/stage1/campus__LoD2', memory='64g'))
        P |= {f'cellsef_LoD2_s0_cell{k}': dict(scene=f'/tu1/scenes/cell{k}/scene_LoD2', split=f'/tu1/scenes/cell{k}/split.json', target=f'/tu1/stage1/cell{k}__LoD2', memory='48g') for k in range(4)}
        P |= {f'cells9ef_LoD2_s0_cell{k}': dict(scene=f'/tu/scenes/cell{k}/scene_LoD2', split=f'/tu/scenes/cell{k}/split.json', target=f'/tu/stage1/cell{k}__LoD2', memory='48g',
                                               inputs_first=[f'bash run2_cpu.sh seeds-cell{k}-lod2 8 32g tu_campus.py seeds cell{k} LoD2'] + [f'bash run2_cpu.sh maps-cell{k}-lod2-{p} 3 14g tu_campus.py maps cell{k} LoD2 {p} 3' for p in range(3)]
                                               + [f'bash run2_cpu.sh index-cell{k}-lod2 4 12g tu_campus.py index cell{k} LoD2']) for k in range(9)}
        for name, j in P.items():
            cmd = command('<gpu>', f'jbgs-trainunit2-{name.replace("_", "-").lower()}-a1', 'tu2_train_entry.py',
                          [name, *train_args(j['scene'], f'/tu/runs/{name}/attempt1/model', j['target'], 0, 30000)], j['split'], j['memory'])
            dump(TU / 'prepared' / name / 'command.json', cmd)
            dump(TU / 'prepared' / name / 'prepared.json', dict(at=now().isoformat(), name=name, inputs_first=j.get('inputs_first'),
                 same_as=name.replace('LoD2', 'ALS'), launch='not launched (order v2 section 4); replace <gpu> with 1 and run through tu2_host.attempt',
                 merge='넷: v1 tu_postcpu.merge rule; 아홉: tu2_cells.merge rule (both keep xy in the original cell)', scientific_verdict=None))
            prep.append(name)
        print('PREPARED', prep)
    elif mode == 'cmd':
        j = JOBS[sys.argv[2]]
        print(json.dumps(command(GPU, 'x', 'tu2_train_entry.py', [sys.argv[2], *train_args(j['scene'], '/tu/runs/x/model', j['target'], j['seed'], 30000)], j['split'], j['memory'])))
    else:
        raise ValueError(mode)
