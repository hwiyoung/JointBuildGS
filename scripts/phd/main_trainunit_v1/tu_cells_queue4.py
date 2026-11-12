"""Addendum 4 (user '이어 돌리기'): finish 판 다 with the FINALTRAIN count rule recorded, not enforced.

Every cell that is not TRAINING_COMPLETE continues from the latest complete state in its own attempt lineage
(jbgs_complete/iteration_N, N < 30,000; none -> from iteration 0). ALS cells first, then LoD2 cells, on a GPU with no other
compute process (TRAINERR priority). One same-command retry on error. Waits until the addendum-3 queues have exited.

  nohup python3 tu_cells_queue4.py <gpu> &
"""
import json
import subprocess
import sys
import time
from pathlib import Path

from tu_host import TU, command, dump, gpu_busy, issue, now, progress, train_args

COUNT = 'count_gt_3x_6000'


def old_queue_running():
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            cmd = (p / 'cmdline').read_bytes().split(b'\0')
        except OSError:
            continue
        if any(c.endswith(b'tu_cells_queue.py') for c in cmd):
            return True
    return False


def lineage_resume(run_dir):
    best = None
    for att in run_dir.glob('attempt*'):
        for d in (att / 'model/jbgs_complete').glob('iteration_*'):
            n = int(d.name.split('_')[1])
            if n < 30000 and (d / 'checkpoint.pth').is_file() and (best is None or n > best[0]):
                best = (n, d / 'checkpoint.pth')
    return best


def stop_reason(run_dir, rec):
    att = rec['attempts'][-1]['attempt'] if rec.get('attempts') else None
    p = run_dir / f'attempt{att}' / 'model/target_monitor/STOP.json'
    return json.loads(p.read_text()).get('reason') if att and p.exists() else None


def jobs():
    out = []
    for prior in ['ALS', 'LoD2']:
        for k in [0, 1, 2, 3]:
            run = TU / 'runs/cells' / f'cells_{prior}_s0' / f'cell{k}'
            rec = json.loads((run / 'receipt.json').read_text()) if (run / 'receipt.json').exists() else None
            if rec and rec['status'] == 'TRAINING_COMPLETE':
                continue
            if rec and rec['status'] == 'NO_RESULT':
                continue
            if rec and rec['status'] == 'HEALTH_STOP' and stop_reason(run, rec) != COUNT:
                continue  # other health rules unchanged; reported, not resumed
            out.append(dict(prior=prior, cell=k, name=f'cells_{prior}_s0_cell{k}', run=run))
    # ALS stage first; inside a stage, the cell with the most saved progress first
    out.sort(key=lambda j: (j['prior'] != 'ALS', -(lineage_resume(j['run']) or (0,))[0], j['cell']))
    return out


def claim(job):
    try:
        (job['run'] / 'addendum4_claim').mkdir(parents=True, exist_ok=False)
        return True
    except FileExistsError:
        return False


def run(gpu, job):
    run_dir = job['run']
    old = json.loads((run_dir / 'receipt.json').read_text()) if (run_dir / 'receipt.json').exists() else None
    if old is not None:
        dump(run_dir / 'receipt_before_addendum4.json', old)
    n0 = max([a['attempt'] for a in old['attempts']] + [0]) if old and old.get('attempts') else 0
    best = lineage_resume(run_dir)
    resume, ckpt = (best[0], '/tu/' + str(best[1].relative_to(TU))) if best else (None, None)
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
                                       resume_iteration=resume, addendum=4, nvidia_smi_compute_apps=gpu_busy(gpu), scientific_verdict=None))
        progress(f'{job["name"]} 시도 {a} 시작, GPU {gpu}' + (f' (상태 {resume}회에서 이어 돌림, 덧붙임 4)' if ckpt else ' (처음부터, 덧붙임 4)'))
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
        ov = root / 'model/target_monitor/health_override.jsonl'
        overrides = [json.loads(l) for l in ov.read_text().splitlines() if l.strip()] if ov.exists() else []
        rec = dict(at=now().isoformat(), attempt=a, gpu=gpu, exit_code=rc, seconds=sec, status=st, error=err, last_trace=last, model=model,
                   resume_from=ckpt, resume_iteration=resume, health_overrides=overrides, addendum=4, scientific_verdict=None)
        dump(root / 'receipt.json', rec)
        attempts.append(rec)
        progress(f'{job["name"]} 시도 {a} 끝: {st}, {sec/3600:.2f}시간' + (f', 수 3배 규칙 기록 {len(overrides)}회' if overrides else '')
                 + (f', 오류 {err["error"][:160]}' if err else ''))
        if st != 'EXECUTION_ERROR':
            break
    final_status = attempts[-1]['status'] if attempts[-1]['status'] != 'EXECUTION_ERROR' else 'NO_RESULT'
    all_attempts = (old['attempts'] if old else []) + attempts
    dump(run_dir / 'receipt.json', dict(at=now().isoformat(), name=job['name'], status=final_status, attempts=all_attempts,
         addendum=4, scientific_verdict=None))
    if final_status == 'NO_RESULT':
        issue(f'{job["name"]}: 덧붙임 4에서 두 번 실패 → 결과 없음. 마지막 기록 {attempts[-1].get("last_trace")}, 오류 {attempts[-1].get("error")}')
    if final_status == 'HEALTH_STOP':
        issue(f'{job["name"]}: 덧붙임 4에서도 다른 건강 규칙으로 멈춤 ({stop_reason(run_dir, dict(attempts=attempts))}); 이어 돌리지 않음, 사용자에게 알림.')


def main(gpu):
    gpu = int(gpu)
    progress(f'덧붙임 4 칸 대기열 GPU {gpu}: 덧붙임 3 대기열이 끝나기를 기다림.')
    while old_queue_running():
        time.sleep(60)
    progress(f'덧붙임 4 칸 대기열 시작 GPU {gpu}.')
    while True:
        if (TU / 'control' / f'CELLS4_STOP_{gpu}').exists():
            progress(f'덧붙임 4 칸 대기열 GPU {gpu} 멈춤 파일로 끝.')
            return
        todo = [j for j in jobs() if not (j['run'] / 'addendum4_claim').exists()]
        if not todo:
            progress(f'덧붙임 4 칸 대기열 GPU {gpu}: 남은 칸 없음, 끝.')
            return
        if gpu_busy(gpu):
            time.sleep(600)
            continue
        job = todo[0]
        if not claim(job):
            continue
        try:
            run(gpu, job)
        except Exception as e:
            issue(f'덧붙임 4 칸 대기열 GPU {gpu} {job["name"]} 실행기 오류: {type(e).__name__}: {e}')


if __name__ == '__main__':
    main(sys.argv[1])
