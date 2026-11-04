"""Bound full-scope judgment computation to one hour per region."""
import os,signal,subprocess,sys,time
from common import *
site=sys.argv[1];root=O/'outside'/site;root.mkdir(parents=True,exist_ok=True)
assert not (root/'budget_receipt.json').exists()
start=time.monotonic()
with (root/'worker.log').open('x') as f:
    proc=subprocess.Popen([sys.executable,'-B','-u',str(Path(__file__).with_name('outside_worker.py')),site],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    try:rc=proc.wait(timeout=cfg()['targets']['outside_timeout_seconds']);status='PASS' if rc==0 else 'EXECUTION_ERROR'
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        rc=proc.returncode;status='TIME_LIMIT_BACKGROUND_FALLBACK'
rec=dict(at=now(),site=site,status=status,seconds=time.monotonic()-start,exit_code=rc,scientific_verdict=None)
dump(root/'budget_receipt.json',rec);progress(f'{site} 평가 범위 밖 판단: {status}, {rec["seconds"]:.1f}초.')
if status=='EXECUTION_ERROR':issue(f'{site} 판단 확장 실행 오류. worker.log 보존. 고친 뒤 같은 조건으로 재시도 필요.');raise SystemExit(1)
print(rec,flush=True)
