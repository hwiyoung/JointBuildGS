"""Resume the documented registration guard failure without repeating MVS."""
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');S=Path(__file__).parent
for script in ['register_geometry.py','measure_all.py']:
    start=time.monotonic();print('CPU resume starting',script,flush=True)
    r=subprocess.run([sys.executable,'-B','-u',str(S/script)])
    dump(O/'gates'/f'resume_{script}.json',dict(script=script,exit_code=r.returncode,
        seconds=time.monotonic()-start,scientific_verdict=None))
    if r.returncode:raise SystemExit(r.returncode)
