"""Finish presentation review fixes and native-photo checks after run_reports."""
import json
from pathlib import Path
import subprocess
import sys
import time
from preflight import sha,dump
O=Path('/out');S=Path(__file__).parent
assert json.loads((O/'gates/public_artifacts.json').read_text())['status']=='PASS'
for name in ['distributions.py','validate_photo_crops.py','receipt.py','markdown_tables.py','final_report.py','validate_public.py']:
    print('final review step',name,flush=True);start=time.monotonic()
    result=subprocess.run([sys.executable,'-B','-u',str(S/name)])
    dump(O/'gates'/f'finish_{name}.json',dict(script=name,exit_code=result.returncode,seconds=time.monotonic()-start,scientific_verdict=None))
    if result.returncode:raise SystemExit(result.returncode)
for r in json.loads((O/'gates/empty_axis_before.json').read_text())['files']:
    assert sha(Path('/docs')/r['file'])==r['sha256'],r['file']
dump(O/'gates/empty_axis_numeric_identity.json',dict(status='PASS',figure_data_files=6,scientific_verdict=None))
# This audit JSON is refreshed above; regenerate its derived CSV as well.
p=Path('/docs/tables/public_validation.csv')
if p.exists():p.unlink()
subprocess.run([sys.executable,'-B','-u',str(S/'markdown_tables.py')],check=True)
print('final review checks complete',flush=True)
