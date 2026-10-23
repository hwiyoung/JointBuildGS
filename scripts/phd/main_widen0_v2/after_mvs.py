"""One-task CPU continuation after the authorized MVS process finishes."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');p=O/'mvs/full/colmap_receipt.json'
while not p.exists():time.sleep(20)
r=json.loads(p.read_text());assert r['exit_code']==0,r
for name in ['mvs_points.py','register_geometry.py','measure_all.py']:
    print('CPU continuation starting',name,flush=True)
    ret=subprocess.run([sys.executable,'-B','-u',str(Path(__file__).parent/name)])
    dump(O/'gates'/f'continuation_{name}.json',dict(script=name,exit_code=ret.returncode,scientific_verdict=None))
    if ret.returncode:raise SystemExit(ret.returncode)
print('CPU continuation complete',flush=True)
