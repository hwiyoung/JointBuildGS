"""Host stdlib launcher; every scientific calculation runs in a bounded Docker container.
Only the exact container created by this invocation may be stopped by the monitor.
"""
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import subprocess as sp
import time
import uuid

REPO = Path(__file__).resolve().parents[3]
ART = (REPO.parent / 'JointBuildGS-artifacts').resolve()
PAY = ART / 'phase-payloads/phd/main_regionfig_v2/PHD-MAIN-REGIONFIG-v2'
CFG = REPO / 'configs/phd/main_regionfig_v2'
DOC = REPO / 'docs/experiments/phd/main_regionfig_v2'
LOCK = ART / 'phase-payloads/phd/main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/checks/tsdf.lock'

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def available():
    for line in Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'):
            return int(line.split()[1]) / 1048576
    raise RuntimeError('MemAvailable missing')

def busy():
    # Probe only: never retain the shared lock or change the other task's files.
    if not LOCK.is_file():
        return 'postprocess lock missing; cannot establish exclusion'
    with LOCK.open('r') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'postprocess or large scoring holds lock'
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    names = sp.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
    active = [n for n in names if n.startswith('jbgs-lt-') and ('-post-' in n or '-axes-' in n or n.endswith(('-mesh', '-fates')))]
    return ','.join(active) if active else None

def main():
    p = argparse.ArgumentParser()
    p.add_argument('tag')
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    policy = json.loads((CFG / 'resource_approval.json').read_text())
    assert policy['status'] == 'AUTHORIZED' and policy['minimum_host_available_GiB'] == 24
    assert args.command and all(c.isalnum() or c in '-_' for c in args.tag)
    for d in [PAY/'logs', PAY/'tmp', PAY/'cache', DOC, CFG]:
        d.mkdir(parents=True, exist_ok=True)
    ident = dt.datetime.now().strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    name = 'jbgs-regionfig-v2-' + ident.lower()
    source_head = sp.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = dict(task_id='PHD-MAIN-REGIONFIG-v2', tag=args.tag, started_at=now(), scientific_verdict=None,
                   source_base_head=source_head,
                   name=name, command=args.command, admission_samples=[])
    rp = PAY/'logs'/f'{ident}-{args.tag}.json'
    log = PAY/'logs'/f'{ident}-{args.tag}.log'
    def save():
        rp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    for attempt in range(7):
        mem, reason = available(), busy()
        receipt['admission_samples'].append(dict(at=now(), available_GiB=mem, busy=reason))
        save()
        if mem >= 24 and not reason:
            break
        print(f'WAIT available={mem:.2f} GiB busy={reason}', flush=True)
        if attempt == 6:
            receipt.update(status='WAITING_FOR_RESOURCES', finished_at=now()); save(); return 75
        time.sleep(10)
    command = ['docker','run','--name',name,'--label','jbgs.task=PHD-MAIN-REGIONFIG-v2',
               '--runtime','runc','--network','none','--read-only','--user',f'{os.getuid()}:{os.getgid()}',
               '--cpus','2','--memory','4g','--memory-swap','4g','--pids-limit','128',
               '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONUNBUFFERED=1','-e','CUDA_VISIBLE_DEVICES=',
               '-e',f'JBGS_SOURCE_HEAD={source_head}',
               '-e','NVIDIA_VISIBLE_DEVICES=void','-e','OMP_NUM_THREADS=1','-e','OPENBLAS_NUM_THREADS=1',
               '-e','MPLCONFIGDIR=/payload/cache/mpl','-e','XDG_CACHE_HOME=/payload/cache','-e','TMPDIR=/payload/tmp',
               '-v',f'{REPO}:/repo:ro','-v',f'{ART}:/art:ro','-v',f'{PAY}:/payload',
               '-v',f'{CFG}:/cfg','-v',f'{DOC}:/docs','-v','/usr/share/fonts/opentype/noto:/fonts:ro',
               '-w','/repo/scripts/phd/main_regionfig_v2','--entrypoint','nice','jointbuildgs:dev','-n','19','ionice','-c','3',*args.command]
    receipt.update(docker_command=command, status='RUNNING', monitor=[]); save()
    interrupted = None
    try:
        with log.open('w') as f:
            process = sp.Popen(['ionice','-c','3',*command],stdout=f,stderr=sp.STDOUT)
            while process.poll() is None:
                time.sleep(5)
                if process.poll() is not None:
                    break
                mem, reason = available(), busy()
                receipt['monitor'].append(dict(at=now(), available_GiB=mem, busy=reason)); save()
                if mem < 16 or reason:
                    interrupted = reason or f'available {mem:.2f} GiB < 16'
                    sp.run(['docker','stop','--time','2',name],check=False,stdout=sp.DEVNULL)
                    break
            rc = process.wait()
        info = json.loads(sp.check_output(['docker','inspect',name],text=True))[0]
        receipt.update(docker_state=info['State'], image_id=info['Image'],
                       host_config={k:info['HostConfig'][k] for k in ['Memory','MemorySwap','NanoCpus','DeviceRequests','Runtime']})
        assert info['Config']['Labels']['jbgs.task']=='PHD-MAIN-REGIONFIG-v2'
        sp.run(['docker','rm',name],check=True,stdout=sp.DEVNULL)
        receipt.update(exit_code=rc, finished_at=now(), interrupted=interrupted,
                       status='INTERRUPTED_INVALID_OUTPUT' if interrupted else 'PASS' if rc==0 else 'FAILED')
        save()
        print(log.read_text(), end='')
        print('RECEIPT',rp,receipt['status'],flush=True)
        return 75 if interrupted else rc
    except BaseException as e:
        receipt.update(status='LAUNCHER_ERROR', error=repr(e), finished_at=now()); save()
        # Exact unique name belongs to this invocation; never touch other containers.
        sp.run(['docker','stop','--time','2',name],check=False,stdout=sp.DEVNULL,stderr=sp.DEVNULL)
        raise

if __name__ == '__main__':
    raise SystemExit(main())
