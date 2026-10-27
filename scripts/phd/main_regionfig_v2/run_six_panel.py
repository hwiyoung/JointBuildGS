"""Host-stdlib launcher for the explicitly approved, capped static-figure overlap.

The original run_cpu.py policy and protected jobs remain unchanged.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess as sp
import time
import uuid
from run_cpu import REPO, ART, PAY, CFG, DOC, available, busy, now


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['prepare', 'render', 'verify', 'finish', 'package'])
    p.add_argument('id', nargs='?', choices=[str(i) for i in range(1, 9)])
    a = p.parse_args()
    assert (a.stage == 'render') == (a.id is not None)
    policy = json.loads((CFG/'six_panel_v3/resource_approval.json').read_text())
    assert policy['status'] == 'AUTHORIZED' and policy['authority']
    assert policy['container_limit_GiB'] == 2 and policy['cpus'] == 1
    assert policy['minimum_host_available_GiB'] == 32 and policy['interrupt_below_available_GiB'] == 24
    assert a.stage in policy['allowed_stages']
    for folder in [PAY/'logs', PAY/'tmp', PAY/'cache', DOC/'six_panel_v3']:
        folder.mkdir(parents=True, exist_ok=True)
    ident = dt.datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
    name = 'jbgs-regionfig-six3-'+ident.lower()
    tag = 'six3-'+a.stage+('-'+a.id if a.id else '')
    rp, log = PAY/'logs'/f'{ident}-{tag}.json', PAY/'logs'/f'{ident}-{tag}.log'
    head = sp.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = dict(task_id='PHD-MAIN-REGIONFIG-v2-SIX3', tag=tag, started_at=now(), name=name,
                   source_head=head, resource_policy=policy, admission_samples=[], monitor=[], scientific_verdict=None)
    def save():
        rp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    for attempt in range(7):
        mem, other = available(), busy()
        receipt['admission_samples'].append(dict(at=now(), available_GiB=mem, protected_job_state=other)); save()
        if mem >= 32:
            break
        print(f'WAIT available={mem:.2f} GiB; minimum=32', flush=True)
        if attempt == 6:
            receipt.update(status='WAITING_FOR_MEMORY', finished_at=now()); save(); return 75
        time.sleep(10)
    command = ['docker', 'run', '--name', name, '--label', 'jbgs.task=PHD-MAIN-REGIONFIG-v2-SIX3',
               '--runtime', 'runc', '--network', 'none', '--read-only', '--user', f'{os.getuid()}:{os.getgid()}',
               '--cpus', '1', '--memory', '2g', '--memory-swap', '2g', '--pids-limit', '128',
               '-e', 'PYTHONDONTWRITEBYTECODE=1', '-e', 'PYTHONUNBUFFERED=1', '-e', 'CUDA_VISIBLE_DEVICES=',
               '-e', 'NVIDIA_VISIBLE_DEVICES=void', '-e', 'OMP_NUM_THREADS=1', '-e', 'OPENBLAS_NUM_THREADS=1',
               '-e', f'JBGS_SOURCE_HEAD={head}', '-e', 'MPLCONFIGDIR=/payload/cache/mpl',
               '-e', 'XDG_CACHE_HOME=/payload/cache', '-e', 'TMPDIR=/payload/tmp',
               '-v', f'{REPO}:/repo:ro', '-v', f'{ART}:/art:ro', '-v', f'{PAY}:/payload',
               '-v', f'{CFG}:/cfg', '-v', f'{DOC}:/docs', '-v', '/usr/share/fonts/opentype/noto:/fonts:ro',
               '-w', '/repo/scripts/phd/main_regionfig_v2', '--entrypoint', 'nice', 'jointbuildgs:dev',
               '-n', '19', 'ionice', '-c', '3', 'python', 'six_panel_revision03.py', a.stage]
    if a.id:
        command.append(a.id)
    receipt.update(status='RUNNING', docker_command=command); save()
    interruption = None
    try:
        with log.open('w') as f:
            process = sp.Popen(['ionice', '-c', '3', *command], stdout=f, stderr=sp.STDOUT)
            while process.poll() is None:
                time.sleep(5)
                if process.poll() is not None:
                    break
                mem = available()
                receipt['monitor'].append(dict(at=now(), available_GiB=mem, protected_job_state=busy())); save()
                if mem < 24:
                    interruption = f'available {mem:.2f} GiB below 24'
                    sp.run(['docker', 'stop', '--time', '2', name], stdout=sp.DEVNULL, check=False)
                    break
            rc = process.wait()
        state = json.loads(sp.check_output(['docker', 'inspect', name], text=True))[0]
        assert state['Config']['Labels']['jbgs.task'] == 'PHD-MAIN-REGIONFIG-v2-SIX3'
        receipt.update(docker_state=state['State'], image_id=state['Image'],
                       host_config={k:state['HostConfig'][k] for k in ['Memory', 'MemorySwap', 'NanoCpus', 'DeviceRequests', 'Runtime']})
        sp.run(['docker', 'rm', name], check=True, stdout=sp.DEVNULL)
        status = 'INTERRUPTED_INVALID_OUTPUT' if interruption else 'OOM_STOP' if state['State'].get('OOMKilled') else 'PASS' if rc == 0 else 'FAILED'
        receipt.update(status=status, finished_at=now(), exit_code=rc, interruption=interruption); save()
        print(log.read_text(), end=''); print('RECEIPT', rp, status, flush=True)
        return 75 if interruption else rc
    except BaseException as exc:
        receipt.update(status='LAUNCHER_ERROR', error=repr(exc), finished_at=now()); save()
        sp.run(['docker', 'stop', '--time', '2', name], stdout=sp.DEVNULL, stderr=sp.DEVNULL, check=False)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
