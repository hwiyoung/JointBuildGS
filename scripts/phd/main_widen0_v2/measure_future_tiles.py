"""Compute the last twelve tiles in reverse; the primary driver owns exports."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');S=Path(__file__).parent
started=time.monotonic()
tiles=json.loads((O/'inputs/tiles.json').read_text())[12:][::-1]
for t in tiles:
    for prior in ['LoD2','ALS']:
        for data in ['gt','mvs_a']+(['als'] if prior=='ALS' else []):
            cmd=[sys.executable,'-B','-u',str(S/'u_worker.py'),t['id'],prior,data]
            if data!='gt':cmd+=['1.5']
            subprocess.run(cmd+['--workers','64'],check=True)
    print('future tile work complete',t['id'],flush=True)
dump(O/'gates/parallel_future_tiles.json',dict(status='PASS',tiles=len(tiles),workers_per_job=64,
    seconds=time.monotonic()-started,export_owner='primary measure_all.py',scientific_verdict=None))
