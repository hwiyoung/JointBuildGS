"""Host-only Docker orchestration for small preflight checks; no experiment runs."""
import json
import os
from pathlib import Path
import subprocess
import sys

R=Path(__file__).resolve().parents[3]
ART=R.parent/'JointBuildGS-artifacts'
O=ART/'phase-payloads/phd/main_gtjudge_v1/PHD-MAIN-GTJUDGE-v1'
C=R/'configs/phd/main_gtjudge_v1'
D=R/'docs/experiments/phd/main_gtjudge_v1'

def run(label,fork,mode):
    cfg=json.loads((C/'gtjudge_v1.json').read_text())
    image=cfg['docker_images']['jointbuildgs:geogs-conf-guided-v1']
    cmd=['docker','run','--rm','--read-only','--network','none','--gpus','device=0',
        '--name','jbgs-gtjudge-check-'+label,'--user',f'{os.getuid()}:{os.getgid()}',
        '--cpus','4','--memory','8g','--memory-swap','8g',
        '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONUNBUFFERED=1',
        '-e','OMP_NUM_THREADS=2','-e','OPENBLAS_NUM_THREADS=1',
        '-e','TMPDIR=/gtjudge/tmp','-e','XDG_CACHE_HOME=/gtjudge/tmp/cache',
        '-e','CUBLAS_WORKSPACE_CONFIG=:4096:8']
    for src,dst,access in [(R,'/repo','ro'),(ART,'/art','ro'),(O,'/gtjudge','rw'),
        (C,'/cfg','ro'),(D,'/docs','rw'),(R/'src/phd/forks'/fork,'/source','ro')]:
        cmd+=['-v',f'{src}:{dst}:{access}']
    cmd+=['-w','/source','--entrypoint','python',image,'-B','-u',
        '/repo/scripts/phd/main_gtjudge_v1/unit_gpu.py',mode,label]
    with (O/'logs'/f'{label}.log').open('w') as f:
        result=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT)
    print(label,'exit',result.returncode,flush=True)
    if result.returncode:
        lines=(O/'logs'/f'{label}.log').read_text().splitlines()
        print('\n'.join(lines[-30:]))
    return result.returncode

def main():
    failures=[]
    for label,fork,mode in [('r23','GeoGS-conf-guided-v1-r23','default'),
        ('r25','GeoGS-conf-guided-v1-r25','default'),
        ('r25-fs','GeoGS-conf-guided-v1-r25','primitives'),
        ('r25-compare','GeoGS-conf-guided-v1-r25','compare')]:
        if run(label,fork,mode):failures.append(label)
    if failures:raise SystemExit('Failed checks: '+','.join(failures))

if __name__=='__main__':main()
