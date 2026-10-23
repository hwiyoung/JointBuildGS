"""After the last twelve tiles finish, use that worker for missing earlier jobs."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');R=O/'holdout/internal';S=Path(__file__).parent
assert json.loads((O/'gates/parallel_future_tiles.json').read_text())['status']=='PASS'
started=time.monotonic();requested=skipped=0
for tile in json.loads((O/'inputs/tiles.json').read_text())[:12][::-1]:
    tid=tile['id']
    for prior in ['LoD2','ALS']:
        for data in ['gt','mvs_a']+(['als'] if prior=='ALS' else []):
            path=R/'work'/(f'gt_{tid}_{prior}.npz' if data=='gt' else f'val_{tid}_{prior}_{data}_R1.5.npz')
            receipt=R/'work'/(f'run_gt_{tid}_{prior}.json' if data=='gt' else f'run_{tid}_{prior}_{data}_1.5.json')
            if path.exists() and receipt.exists():
                skipped+=1;continue
            cmd=[sys.executable,'-B','-u',str(S/'u_worker.py'),tid,prior,data]
            if data!='gt':cmd+=['1.5']
            subprocess.run(cmd+['--workers','64'],check=True);requested+=1
    print('earlier tile jobs available',tid,flush=True)
dump(O/'gates/parallel_remaining_tiles.json',dict(status='PASS',jobs_requested_under_lock=requested,
    already_complete_skipped=skipped,seconds=time.monotonic()-started,
    scope='first twelve frozen tiles in reverse; missing jobs only',export_owner='primary measure_all.py',scientific_verdict=None))
