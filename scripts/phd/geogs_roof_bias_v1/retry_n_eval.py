"""Retry native N evaluation after correcting only the writable working directory."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import time

T = Path(__file__).resolve().parents[1]
root = T / 'conditions/N'
receipt_path = root / 'eval3d_receipt.json'
original = json.loads(receipt_path.read_text())
command = original['command']
command[command.index('--name') + 1] = 'roof-N-eval3d-retry'
start = datetime.datetime.now(datetime.timezone.utc).isoformat()
clock = time.monotonic()
with (root / 'eval3d_retry.log').open('w') as log:
    rc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT).returncode
receipt = dict(original, command=command, started_at=start,
               finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
               seconds=time.monotonic()-clock, exit_code=rc,
               status='PASS' if rc == 0 and (T/original['expected']).exists() else 'FAILED',
               retry_reason='py4dgeo log CWD changed to writable evaluation directory; method unchanged')
(root / 'eval3d_initial_receipt.json').write_text(json.dumps(original, indent=2))
receipt_path.write_text(json.dumps(receipt, indent=2))
export_command = json.loads((root/'export_receipt.json').read_text())['command']
export_command[export_command.index('--name')+1] = 'roof-N-export-retry'
with (root/'export_retry.log').open('w') as log:
    subprocess.run(export_command, stdout=log, stderr=subprocess.STDOUT)
# The live queue owns status.json. Reconcile its cached initial failure only after
# its process exits; do not interrupt training or race its final export.
while True:
    state = json.loads((T/'status.json').read_text())
    try:
        os.kill(state['pid'], 0)
    except ProcessLookupError:
        break
    time.sleep(30)
if state.get('phase') == 'FINISHED':
    state['conditions']['N']['eval3d'] = receipt['status']
    if all(len(state['conditions'].get(c, {})) > 0 and
           'analyze' in state['conditions'][c] and
           all(v == 'PASS' for v in state['conditions'][c].values())
           for c in ['N','B+0.25','B+0.5','B+1.0','B-1.0']):
        state['status'] = 'COMPLETE'
    state['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state['evaluation_retry_receipt'] = 'conditions/N/eval3d_receipt.json'
    tmp = T/'status.retry.tmp'
    tmp.write_text(json.dumps(state, indent=2)); tmp.replace(T/'status.json')
    with (root/'export_retry_final.log').open('w') as log:
        rc = subprocess.run(export_command, stdout=log, stderr=subprocess.STDOUT).returncode
    if rc:
        state['status'] = 'PARTIAL'
        state['final_retry_export_exit'] = rc
        tmp.write_text(json.dumps(state, indent=2)); tmp.replace(T/'status.json')
