"""One queue for logging arms and conditional intervention arms.

No repeated log polling. The next-stage gate is an explicit committed JSON.
"""
import concurrent.futures as futures,ctypes,json,os,select,subprocess,sys,traceback
from gpu_job import R,O,D,dump,now,train
SCRIPT=R/'scripts/phd/main_release_v1'
def event(message):
    with (D/'progress.md').open('a') as f:f.write(f'- {now()}: {message}\n')
    print(message,flush=True)
def cpu(tag,script,*args):
    subprocess.run(['bash',str(SCRIPT/'run_cpu.sh'),tag,script,*map(str,args)],cwd=R,check=True)
def arm(site,prior,gpu,rule,stage):
    train(str(gpu),site,prior,rule,stage)
    event(f'{site} {prior} {rule} 단계 {stage} 학습 종료; 영수증 저장.')
    subprocess.run([sys.executable,str(SCRIPT/'post_run.py'),site,prior,rule,str(stage)],cwd=R,check=True)
def pair(site,rule,stage):
    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks=[pool.submit(arm,site,p,g,rule,stage) for g,p in [(0,'ALS'),(1,'LoD2')]]
        for task in futures.as_completed(tasks):
            try:task.result()
            except Exception as exc:
                event('실행 문제: '+str(exc))
                with (D/'issues.md').open('a') as f:f.write(f'- {now()}: 대기열 판 후처리 문제 {exc}\n')
def gate_wait():
    path=D/'단계3_판정.json';libc=ctypes.CDLL(None);fd=libc.inotify_init1(os.O_NONBLOCK)
    if fd<0:raise OSError('inotify_init1')
    libc.inotify_add_watch(fd,os.fsencode(D),0x100|0x80|0x8)
    try:
        while not path.exists():
            select.select([fd],[],[])
            try:os.read(fd,65536)
            except BlockingIOError:pass
    finally:os.close(fd)
    # Publishing writes an explicit commit receipt last; JSON existence alone
    # does not release the training gate.
    receipt=O/'delivery/stage3_gate.json'
    if not receipt.exists():raise RuntimeError('Gate JSON exists but committed gate receipt is absent; queue will not train')
    return json.loads(path.read_text())
def main():
    dump(O/'QUEUE.json',dict(at=now(),pid=os.getpid(),state='STAGE2',scientific_verdict=None))
    pair('R1rep_b10','release',2)
    dump(O/'QUEUE.json',dict(at=now(),pid=os.getpid(),state='WAIT_STAGE1_GATE',scientific_verdict=None))
    gate=gate_wait()
    if not gate['stage3_authorized']:
        dump(O/'QUEUE.json',dict(at=now(),state='STAGE3_NOT_AUTHORIZED_BY_MEASUREMENTS',scientific_verdict=None));return
    for rule in ['pull','delete','mix']:
        dump(O/'QUEUE.json',dict(at=now(),pid=os.getpid(),state='STAGE3_R1',rule=rule,scientific_verdict=None));pair('R1rep_b10',rule,3)
    subprocess.run([sys.executable,str(SCRIPT/'select_rule.py')],cwd=R,check=True)
    selection=json.loads((D/'단계3_고른규칙.json').read_text());rule=selection['selected_rule']
    if rule is None:return
    for site in ['B173nb_b10','B0_b10']:pair(site,rule,3)
    dump(O/'QUEUE.json',dict(at=now(),state='TRAINING_QUEUE_COMPLETE',scientific_verdict=None))
if __name__=='__main__':
    try:main()
    except BaseException as exc:
        dump(O/'QUEUE_FAILURE.json',dict(at=now(),error=str(exc),traceback=traceback.format_exc(),scientific_verdict=None));raise
