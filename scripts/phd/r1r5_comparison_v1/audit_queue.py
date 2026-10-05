"""Read-only regional input audits; no disagreement is promoted to a change label."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
from prepare_queue import CPU_IMAGE,write

root=Path(sys.argv[1]);cfg=json.loads((root/'config.json').read_text());art=Path(cfg['artifact_root'])
source=root/'audit_source';base=json.loads((source/'audit_base.json').read_text())
acfg=json.loads((art/cfg['audit_relative']/'result/config.json').read_text())
try:
    for r in acfg['regions'][1:]:
        region=r['id'];target=root/region
        while not (target/'preparation_complete.json').exists():
            if (root/'preparation_failure.json').exists():raise RuntimeError('Preparation failed')
            write(root/'audit_status.json',dict(state='WAITING_INPUTS',region=region));time.sleep(15)
        output=target/'audit';output.mkdir()
        c=dict(base,region=r,frame=acfg['frame'],input_manifest_sha256=hashlib.sha256((target/'preparation/input/input_manifest.json').read_bytes()).hexdigest())
        write(output/'config.json',c)
        mounts=[(root/'snapshot','/repo'),(source,'/driver'),(target/'preparation/input','/input'),
            (art/cfg['audit_relative']/'result','/audit'),(art/acfg['inputs']['fused_mvs_relative'],'/fused.ply'),
            (Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),'/font.ttf')]
        command=['docker','run','--rm','--runtime','runc','--network','none','--cpus','4','--memory','8g','--user',f'{os.getuid()}:{os.getgid()}',
            '-e','PYTHONDONTWRITEBYTECODE=1','-e','NVIDIA_VISIBLE_DEVICES=void','-e','OPENBLAS_NUM_THREADS=1','-e','OMP_NUM_THREADS=4','-e','MPLCONFIGDIR=/tmp/mpl']
        for host,dest in mounts:command+=['--mount',f'type=bind,source={host},target={dest},readonly']
        command+=['--mount',f'type=bind,source={output},target=/output','--entrypoint','python',CPU_IMAGE,
            '/driver/audit.py','--config','/output/config.json','--output','/output/result']
        write(output/'command.json',command);write(root/'audit_status.json',dict(state='RUNNING',region=region))
        with (output/'driver.log').open('x') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    write(root/'audit_status.json',dict(state='COMPLETE',scientific_verdict=None))
except Exception:
    write(root/'audit_status.json',dict(state='FAILED',error=traceback.format_exc(),scientific_verdict=None));raise
