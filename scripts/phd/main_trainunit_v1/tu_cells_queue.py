"""Addendum 3: finish 판 다. Resume cell0/cell1 (ALS) from their saved complete states, start the other cells, ALS then LoD2,
on any GPU with no other compute process (TRAINERR priority). One same-command retry on error.

  nohup python3 tu_cells_queue.py <gpu> &
"""
import json
import subprocess
import sys
import time

from tu_host import TU, command, dump, gpu_busy, issue, now, progress, train_args

RESUME = {('ALS', 0): 12700, ('ALS', 1): 5600}


def jobs():
    out = []
    for prior in ['ALS', 'LoD2']:
        for k in [0, 1, 2, 3]:
            out.append(dict(prior=prior, cell=k, name=f'cells_{prior}_s0_cell{k}', run=TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{k}'))
    # resumed cells first inside the ALS stage
    out.sort(key=lambda j: (j['prior'] != 'ALS', (j['prior'], j['cell']) not in RESUME, j['cell']))
    return out


def claim(job):
    lock = job['run'] / 'addendum3_claim'
    try:
        lock.mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        return False


def run(gpu, job):
    run_dir = job['run']
    old = json.loads((run_dir / 'receipt.json').read_text()) if (run_dir / 'receipt.json').exists() else None
    if old is not None:
        dump(run_dir / 'receipt_before_addendum3.json', old)
    n0 = len(old['attempts']) if old else 0
    resume = RESUME.get((job['prior'], job['cell']))
    ckpt = None
    if resume is not None:
        ckpt = f'/tu/runs/cells/cells_{job["prior"]}_s0/cell{job["cell"]}/attempt1/model/jbgs_complete/iteration_{resume}/checkpoint.pth'
    attempts = []
    for i in [1, 2]:
        a = n0 + i
        root = run_dir / f'attempt{a}'
        root.mkdir()
        model = '/tu/' + str((root / 'model').relative_to(TU))
        extra = ['--jbgs_resume_full', ckpt] if ckpt else []
        args = [job['name'], *train_args(f'/tu/scenes/cell{job["cell"]}/scene_{job["prior"]}', model, f'/tu/stage1/cell{job["cell"]}__{job["prior"]}', 0, 30000, extra)]
        cmd = command(gpu, f'jbgs-trainunit-{job["name"].replace("_", "-").lower()}-a{a}', 'tu_train_entry.py', args,
                      f'/tu/scenes/cell{job["cell"]}/split.json', '48g')
        dump(root / 'command.json', cmd)
        dump(root / 'launch.json', dict(at=now().isoformat(), gpu=gpu, job={k: str(v) for k, v in job.items()}, attempt=a, resume_from=ckpt,
                                       addendum=3, nvidia_smi_compute_apps=gpu_busy(gpu), scientific_verdict=None))
        progress(f'{job["name"]} 시도 {a} 시작, GPU {gpu}' + (f' (상태 {resume}회에서 이어 돌림)' if ckpt else ''))
        start = time.monotonic()
        with (root / 'train.log').open('x') as f:
            rc = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT).returncode
        sec = time.monotonic() - start
        trace = root / 'model/jbgs_trace.jsonl'
        last = json.loads(trace.read_text().strip().splitlines()[-1]) if trace.exists() and trace.read_text().strip() else None
        if rc == 0 and (root / 'TRAINING_COMPLETE.json').exists():
            st = 'TRAINING_COMPLETE'
        elif (root / 'DEADLINE_STOP.json').exists():
            st = 'DEADLINE_STOP_SAVED'
        elif (root / 'model/target_monitor/STOP.json').exists():
            st = 'HEALTH_STOP'
        else:
            st = 'EXECUTION_ERROR'
        err = json.loads((root / 'ERROR.json').read_text()) if (root / 'ERROR.json').exists() else None
        rec = dict(at=now().isoformat(), attempt=a, gpu=gpu, exit_code=rc, seconds=sec, status=st, error=err, last_trace=last, model=model,
                   resume_from=ckpt, scientific_verdict=None)
        dump(root / 'receipt.json', rec)
        attempts.append(rec)
        progress(f'{job["name"]} 시도 {a} 끝: {st}, {sec/3600:.2f}시간' + (f', 오류 {err["error"][:160]}' if err else ''))
        if st != 'EXECUTION_ERROR':
            break
    final_status = attempts[-1]['status'] if attempts[-1]['status'] != 'EXECUTION_ERROR' else 'NO_RESULT'
    all_attempts = (old['attempts'] if old else []) + attempts
    dump(run_dir / 'receipt.json', dict(at=now().isoformat(), name=job['name'], status=final_status, attempts=all_attempts,
         addendum=3, scientific_verdict=None))
    if final_status == 'NO_RESULT':
        issue(f'{job["name"]}: 덧붙임 3에서 두 번 실패 → 결과 없음. 마지막 기록 {attempts[-1].get("last_trace")}, 오류 {attempts[-1].get("error")}')


def main(gpu):
    gpu = int(gpu)
    progress(f'덧붙임 3 칸 대기열 시작 GPU {gpu}.')
    while True:
        if (TU / 'control' / f'CELLS_STOP_{gpu}').exists():
            progress(f'덧붙임 3 칸 대기열 GPU {gpu} 멈춤 파일로 끝.')
            return
        todo = [j for j in jobs() if not (j['run'] / 'addendum3_claim').exists()]
        if not todo:
            progress(f'덧붙임 3 칸 대기열 GPU {gpu}: 남은 칸 없음, 끝.')
            return
        busy = gpu_busy(gpu)
        if busy:
            time.sleep(600)
            continue
        job = todo[0]
        if not claim(job):
            continue
        try:
            run(gpu, job)
        except Exception as e:
            issue(f'덧붙임 3 칸 대기열 GPU {gpu} {job["name"]} 실행기 오류: {type(e).__name__}: {e}')


if __name__ == '__main__':
    main(sys.argv[1])
