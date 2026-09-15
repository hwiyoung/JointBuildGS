"""Host stdlib orchestration; numerical preparation runs only in isolated Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import time
import traceback

CPU_IMAGE = 'sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'

def write(path, value):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temp.replace(path)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('attempt'); args = ap.parse_args()
    attempt = Path(args.attempt).resolve(); config = json.loads((attempt/'config.json').read_text())
    artifacts = Path(config['artifact_root']); snapshot = attempt/'snapshot'
    source = artifacts/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/sources'
    audit = artifacts/config['audit_relative']
    def run(region, stage, output, mounts, argv):
        state = dict(region=region, stage=stage, state='RUNNING', updated_unix=time.time(), scientific_verdict=None)
        write(attempt/'preparation_status.json',state)
        command=['docker','run','--rm','--runtime','runc','--network','none','--cpus','4','--memory','12g',
            '--user',f'{os.getuid()}:{os.getgid()}', '-e','PYTHONDONTWRITEBYTECODE=1','-e','PYTHONPATH=/repo',
            '-e','OPENBLAS_NUM_THREADS=1','-e','OMP_NUM_THREADS=4','-e','NVIDIA_VISIBLE_DEVICES=void',
            '-e','CUDA_VISIBLE_DEVICES=','-e','MPLCONFIGDIR=/tmp/mpl',
            '--mount',f'type=bind,source={snapshot},target=/repo,readonly',
            '--mount',f'type=bind,source={output},target=/output']
        for host,target in mounts: command+=['--mount',f'type=bind,source={host},target={target},readonly']
        command+=['--entrypoint','python',CPU_IMAGE]+argv
        write(output/(stage+'_command.json'),command)
        with (output/(stage+'.log')).open('x') as log:
            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    for region in config['prepare_regions']:
        output=attempt/region; output.mkdir()
        run(region,'prepare',output,[(audit,'/audit'),(artifacts/config['camera_relative'],'/cameras'),
            (artifacts/'phase-payloads/p0-audit/data/raw/als','/als'),(source/'GeoGS','/geogs_original')],
            ['/repo/scripts/phd/r1_mvs_control_v1/prepare.py','--config',f'/repo/configs/phd/r1r5_comparison_v1/{region}_preparation.json','--output','/output/preparation'])
        run(region,'finalize',output,[(output/'preparation/input','/input'),(source/'GeoGS-state-camera-v1','/anchor_source'),
            (artifacts/'phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/sources/GeoGS-mvs-pgsr-v1','/refinement_source')],
            ['/repo/scripts/phd/r1_mvs_control_v1/finalize_preparation.py','--config',f'/repo/configs/phd/r1r5_comparison_v1/{region}_runtime.json','--output','/output/runtime'])
        write(output/'preparation_complete.json',dict(status='PASS',scientific_verdict=None,region=region,
            input_manifest_sha256=hashlib.sha256((output/'preparation/input/input_manifest.json').read_bytes()).hexdigest()))
    write(attempt/'preparation_status.json',dict(state='COMPLETE',scientific_verdict=None,updated_unix=time.time()))

if __name__=='__main__':
    try: main()
    except Exception:
        if len(os.sys.argv)>1:
            root=Path(os.sys.argv[1]); write(root/'preparation_failure.json',dict(state='FAILED',error=traceback.format_exc(),scientific_verdict=None))
            write(root/'preparation_status.json',dict(state='FAILED',scientific_verdict=None))
        raise
