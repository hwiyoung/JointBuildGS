"""Host side (no project dependency runs on host): Docker commands, job table and the per-GPU queue.

  nohup python3 tu_host.py queue <gpu> > PH/.../logs/queue_gpu<gpu>.log 2>&1 &
"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[3]
ART = Path('/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts')
PH = ART / 'phase-payloads/phd'
TU = PH / 'main_trainunit_v1/PHD-MAIN-TRAINUNIT-v1'
FT = PH / 'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
S0 = PH / 'main_stage0_v1/PHD-MAIN-STAGE0-v1'
C = R / 'configs/phd/main_trainunit_v1'
D = R / 'docs/experiments/phd/main_trainunit_v1'
KST = dt.timezone(dt.timedelta(hours=9))
IMAGE = 'sha256:ff4eba02c450573e3258ec4946b9c536f32c213dde9abc83ee2969aaf18384be'
SITES = ['B0_b10', 'R1rep_b10', 'B173nb_b10']
MIN_SECONDS = {'ALS': 4468, 'LoD2': 6557}


def now():
    return dt.datetime.now(KST)


def dump(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def progress(s):
    with (D / 'progress.md').open('a') as f:
        f.write(f'- {now().isoformat()}: {s}\n')


def issue(s):
    with (D / 'issues.md').open('a') as f:
        f.write(f'- {now().isoformat()}: {s}\n')


def deadline():
    return dt.datetime.fromisoformat(json.loads((C / 'trainunit_v1.json').read_text())['gpu']['deadline'])


def command(gpu, name, script, args, split, memory='40g'):
    cmd = ['docker', 'run', '--rm', '--read-only', '--network', 'none', '--name', name, '--gpus', f'device={gpu}',
           '--user', f'{os.getuid()}:{os.getgid()}', '--cpus', '8', '--memory', memory, '--memory-swap', memory, '--shm-size', '4g']
    for e in ['PYTHONDONTWRITEBYTECODE=1', 'PYTHONUNBUFFERED=1', 'OMP_NUM_THREADS=4', 'OPENBLAS_NUM_THREADS=1',
              'PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True', f'JBGS_SPLIT_JSON={split}',
              'TMPDIR=/tu/tmp', 'MPLCONFIGDIR=/tu/tmp/mpl', 'XDG_CACHE_HOME=/tu/tmp/cache', 'TORCH_HOME=/weights/torch', 'TZ=Asia/Seoul']:
        cmd += ['-e', e]
    mounts = [(R, '/repo', 'ro'), (ART, '/art', 'ro'), (ART, '/artifacts/JointBuildGS', 'ro'), (PH, '/ph', 'ro'),
              (S0, '/p', 'ro'), (FT, '/ft', 'ro'), (TU, '/tu', 'rw'),
              (R / 'src/phd/forks/GeoGS-conf-guided-v1-r23', '/source', 'ro'),
              (PH / 'geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/runtime/weights', '/weights', 'ro')]
    for src, dst, mode in mounts:
        cmd += ['-v', f'{src}:{dst}:{mode}']
    return cmd + ['-w', '/source', '--entrypoint', 'python', IMAGE, '-B', '-u', f'/repo/scripts/phd/main_trainunit_v1/{script}', *map(str, args)]


def train_args(scene, model, target_dir, seed, iterations, extra=()):
    caps = [7000, 15000, 30000] if iterations == 30000 else [28000, 60000, 120000]
    return ['-s', scene, '-m', model, '--eval', '-r', '1', '--data_device', 'cpu',
            '--lod_depth_path', '/p/fork_none', '--da_depth_path', '/p/fork_none', '--stage_switch_iter', '0',
            '--lambda_lod_init', '0', '--lambda_lod_anchor', '0', '--lambda_da_depth', '0', '--jbgs_judgment', 'off',
            '--jbgs_target', 'on', '--jbgs_target_rev', 'r8', '--jbgs_finaltrain', 'on',
            '--jbgs_capture_iterations', *map(str, caps), '--jbgs_target_dir', target_dir,
            '--jbgs_target_lambda', '.05', '--jbgs_seed', str(seed), '--iterations', str(iterations),
            '--test_iterations', *map(str, caps), '--save_iterations', *map(str, caps), *extra]


def jobs():
    """Ordered job table. Each job: name, run dir, prior, split, scene, target dir, seed, iterations, ready file."""
    out = []
    for prior in ['ALS', 'LoD2']:
        out.append(dict(kind='ga', name=f'campus30k_{prior}_s0', prior=prior, run=TU / 'runs/campus' / f'campus30k_{prior}_s0',
                        scene=f'/tu/scenes/campus/scene_{prior}', split='/tu/scenes/campus/split.json',
                        target_dir=f'/tu/stage1/campus__{prior}', seed=0, iterations=30000,
                        ready=TU / 'stage1' / f'campus__{prior}' / 'ready.json', memory='64g', gpu_pref=0))
    cells = json.loads((TU / 'cells/cells.json').read_text())['cells'] if (TU / 'cells/cells.json').exists() else []
    for prior in ['ALS', 'LoD2']:
        for c in (cells or [dict(id=k) for k in range(4)]):
            k = c['id']
            out.append(dict(kind='da', name=f'cells_{prior}_s0_cell{k}', prior=prior, run=TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{k}',
                            scene=f'/tu/scenes/cell{k}/scene_{prior}', split=f'/tu/scenes/cell{k}/split.json',
                            target_dir=f'/tu/stage1/cell{k}__{prior}', seed=0, iterations=30000,
                            ready=TU / 'stage1' / f'cell{k}__{prior}' / 'ready.json', memory='48g', gpu_pref=1))
    for site in SITES:
        for prior in ['ALS', 'LoD2']:
            out.append(dict(kind='seed1', name=f'seed1_{site}_{prior}', prior=prior, run=TU / 'runs' / site / f'seed1_{prior}',
                            scene=f'/p/fork_inputs/s61/{site}/scene_{prior}', split=f'/p/fork_inputs/s61/{site}/split.json',
                            target_dir=f'/ft/stage1/{site}__{prior}', seed=1, iterations=30000,
                            ready=FT / 'stage1' / f'{site}__{prior}' / 'ready.json', memory='40g', gpu_pref=None))
    return out


def gpu_busy(gpu):
    out = subprocess.run(['nvidia-smi', '-i', str(gpu), '--query-compute-apps=pid,process_name,used_memory', '--format=csv,noheader'],
                         capture_output=True, text=True).stdout.strip().splitlines()
    procs = [l for l in out if l.strip() and not any(x in l for x in ['gnome', 'Xorg', 'xorg'])]
    return procs


def status(job):
    p = job['run'] / 'receipt.json'
    return json.loads(p.read_text())['status'] if p.exists() else None


def run_job(gpu, job):
    run = job['run']
    run.mkdir(parents=True, exist_ok=True)
    attempts = []
    for attempt in [1, 2]:
        root = run / f'attempt{attempt}'
        if root.exists():
            rec = json.loads((root / 'receipt.json').read_text()) if (root / 'receipt.json').exists() else None
            if rec:
                attempts.append(rec)
                if rec['status'] != 'EXECUTION_ERROR':
                    break
                continue
            raise RuntimeError(f'{root} exists without receipt; manual check needed')
        root.mkdir()
        model = '/tu/' + str((root / 'model').relative_to(TU))
        args = [job['name'], *train_args(job['scene'], model, job['target_dir'], job['seed'], job['iterations'], job.get('extra', ()))]
        cmd = command(gpu, f'jbgs-trainunit-{job["name"].replace("_", "-").lower()}-a{attempt}', 'tu_train_entry.py', args, job['split'], job['memory'])
        dump(root / 'command.json', cmd)
        dump(root / 'launch.json', dict(at=now().isoformat(), gpu=gpu, job={k: str(v) for k, v in job.items()}, attempt=attempt,
                                       nvidia_smi_compute_apps=gpu_busy(gpu), scientific_verdict=None))
        progress(f'{job["name"]} 시도 {attempt} 시작, GPU {gpu}.')
        start = time.monotonic()
        with (root / 'train.log').open('x') as f:
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
        seconds = time.monotonic() - start
        trace = root / 'model/jbgs_trace.jsonl'
        last = None
        if trace.exists():
            lines = trace.read_text().strip().splitlines()
            last = json.loads(lines[-1]) if lines else None
        stop = root / 'model/target_monitor/STOP.json'
        if rc == 0 and (root / 'TRAINING_COMPLETE.json').exists():
            st = 'TRAINING_COMPLETE'
        elif (root / 'TIME_STOP.json').exists():
            st = 'TIME_STOP_500'
        elif (root / 'DEADLINE_STOP.json').exists():
            st = 'DEADLINE_STOP_SAVED'
        elif stop.exists():
            st = 'HEALTH_STOP'
        else:
            st = 'EXECUTION_ERROR'
        err = json.loads((root / 'ERROR.json').read_text()) if (root / 'ERROR.json').exists() else None
        rec = dict(at=now().isoformat(), attempt=attempt, gpu=gpu, exit_code=rc, seconds=seconds, status=st, error=err,
                   last_trace=last, model=model, scientific_verdict=None)
        dump(root / 'receipt.json', rec)
        attempts.append(rec)
        progress(f'{job["name"]} 시도 {attempt} 끝: {st}, {seconds/3600:.2f}시간' + (f', 오류 {err["error"][:160]}' if err else ''))
        if st != 'EXECUTION_ERROR':
            break
    final_status = attempts[-1]['status'] if attempts[-1]['status'] != 'EXECUTION_ERROR' else 'NO_RESULT'
    final = dict(at=now().isoformat(), name=job['name'], status=final_status, attempts=attempts, scientific_verdict=None)
    dump(run / 'receipt.json', final)
    if final_status == 'NO_RESULT':
        issue(f'{job["name"]}: 두 번 실패 → 결과 없음. 마지막 기록 {attempts[-1].get("last_trace")}, 오류 {attempts[-1].get("error")}')
    return final


def claim(job):
    try:
        (job['run']).mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        return False


def pick(gpu):
    table = jobs()
    t = now()
    dl = deadline()
    idle = (TU / 'control/IDLE_FILL_UNTIL').read_text().strip() if (TU / 'control/IDLE_FILL_UNTIL').exists() else None
    idle_until = dt.datetime.fromisoformat(idle) if idle else None
    primary_pending = []
    prim = [j for j in table if j['kind'] != 'seed1']
    # ALS stage (가·다) before LoD2 stage; inside a stage this GPU's preferred unit first
    prim = sorted(prim, key=lambda j: (j['prior'] != 'ALS', j['gpu_pref'] != gpu))
    for job in prim:
        if job['run'].exists():
            continue
        if not job['ready'].exists():
            primary_pending.append(job)
            continue
        if t + dt.timedelta(seconds=MIN_SECONDS[job['prior']]) > dl:
            continue
        return job
    for job in table:
        if job['kind'] != 'seed1' or job['run'].exists() or not job['ready'].exists():
            continue
        end = t + dt.timedelta(seconds=MIN_SECONDS[job['prior']])
        if end > dl:
            continue
        if primary_pending and not (idle_until and end <= idle_until):
            continue
        return job
    return None


def queue(gpu):
    gpu = int(gpu)
    (TU / 'control').mkdir(parents=True, exist_ok=True)
    progress(f'GPU {gpu} 대기열 시작 (pid {os.getpid()}).')
    waited_since = None
    while True:
        if (TU / 'control' / f'QUEUE2_STOP_{gpu}').exists():
            progress(f'GPU {gpu} 대기열 멈춤 파일로 끝.')
            return
        if now() >= deadline():
            progress(f'GPU {gpu} 대기열: 11/12 11:00 지남, 새 판을 걸지 않고 끝.')
            return
        job = pick(gpu)
        if job is None:
            time.sleep(600)
            continue
        busy = gpu_busy(gpu)
        if busy:
            if waited_since is None:
                waited_since = now()
                progress(f'GPU {gpu}: 다른 프로세스 있음 {busy}, {job["name"]} 기다림.')
            time.sleep(600)
            continue
        waited_since = None
        if not claim(job):
            continue
        try:
            run_job(gpu, job)
        except Exception as e:
            issue(f'GPU {gpu} 대기열 {job["name"]} 실행기 오류: {type(e).__name__}: {e}')
        post = TU / 'control/post_requests'
        post.mkdir(parents=True, exist_ok=True)
        dump(post / f'{job["name"]}.json', dict(at=now().isoformat(), name=job['name'], run=str(job['run'])))


def prepare_na():
    """판 나: prepared commands only (120,000 iterations; densify from/until/interval and opacity reset x4). Not queued."""
    cfgv = json.loads((C / 'trainunit_v1.json').read_text())['runs']['na']
    sch = cfgv['schedule_x4']
    extra = ['--densify_from_iter', str(sch['densify_from_iter']), '--densify_until_iter', str(sch['densify_until_iter']),
             '--densification_interval', str(sch['densification_interval']), '--opacity_reset_interval', str(sch['opacity_reset_interval'])]
    for prior in ['ALS', 'LoD2']:
        name = f'campus120k_{prior}_s0'
        root = TU / 'prepared' / name
        model = f'/tu/runs/campus/{name}/attempt1/model'
        args = [name, *train_args(f'/tu/scenes/campus/scene_{prior}', model, f'/tu/stage1/campus__{prior}', 0, 120000, extra)]
        cmd = command('<gpu>', f'jbgs-trainunit-{name.replace("_", "-").lower()}-a1', 'tu_train_entry.py', args, '/tu/scenes/campus/split.json', '64g')
        dump(root / 'command.json', cmd)
        dump(root / 'prepared.json', dict(at=now().isoformat(), name=name, iterations=120000, schedule=sch, checkpoints=cfgv['checkpoints'],
             note='launch: replace <gpu>, run through tu_host.run_job with this job; inputs are the campus inputs of 판 가',
             unchanged=cfgv['unchanged_note'], fixed_iteration_checks_in_code='health check at 7000 and count check until 15000 stay at the code iterations',
             scientific_verdict=None))
    print('NA_PREPARED', flush=True)


def deadline_watch():
    while now() < deadline():
        time.sleep(60)
    names = []
    for job in jobs():
        run = job['run']
        if run.exists() and not (run / 'receipt.json').exists():
            (TU / 'control' / f'STOP_{job["name"]}').write_text(now().isoformat())
            names.append(job['name'])
    progress(f'11:00 마감: 도는 판 {names or "없음"}에 멈춤 파일(다음 100회 배수에서 상태 저장 뒤 멈춤).')


if __name__ == '__main__':
    mode = sys.argv[1]
    if mode == 'queue':
        queue(sys.argv[2])
    elif mode == 'prepare_na':
        prepare_na()
    elif mode == 'deadline_watch':
        deadline_watch()
    elif mode == 'jobs':
        for j in jobs():
            print(j['name'], j['ready'].exists(), status(j))
    else:
        raise ValueError(mode)
