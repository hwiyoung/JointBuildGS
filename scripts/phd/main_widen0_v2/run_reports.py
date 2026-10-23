"""Generate public artifacts after all measurements; packaging follows visual review."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import dump
O=Path('/out');S=Path(__file__).parent
def main():
    assert (O/'gates/measurements_complete.json').exists()
    for name in ['mvs_outputs.py','buffer_support_check.py','components.py','distributions.py','prior_maps.py','historical_compare.py','photos.py','seal_validate.py','receipt.py','complete_interim.py','markdown_tables.py','final_report.py','validate_public.py']:
        print('report step starting',name,flush=True);start=time.monotonic()
        r=subprocess.run([sys.executable,'-B','-u',str(S/name)])
        dump(O/'gates'/f'report_{name}.json',dict(script=name,exit_code=r.returncode,seconds=time.monotonic()-start,scientific_verdict=None))
        if r.returncode:raise SystemExit(r.returncode)
    # Include the newly written public-validation table in all three formats.
    subprocess.run([sys.executable,'-B','-u',str(S/'markdown_tables.py')],check=True)
    print('reports ready for visual review',flush=True)
if __name__=='__main__':main()
