"""Seal a two-GPU scheduler without modifying live experiment source or outputs."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument('attempt', type=Path)
args = ap.parse_args()
root = args.attempt.resolve()
status = json.loads((root / 'execution/status.json').read_text())
assert (status['state'], status['region'], status['job']) == ('RUNNING', 'R3', 'da3')
old = root / status['recovery']
unit = json.loads((old / 'plan.json').read_text())['unit'] + '.service'
pid = int(subprocess.check_output(['systemctl', '--user', 'show', unit,
                                 '-p', 'MainPID', '--value'], text=True))
containers = json.loads(subprocess.check_output(['docker', 'inspect', *subprocess.check_output(
    ['docker', 'ps', '-q'], text=True).split()], text=True))
matched = [c for c in containers if any(m['Destination'] == '/output' and
           m['Source'] == str(root / 'R3/da3') for m in c['Mounts'])]
assert len(matched) == 1 and matched[0]['State']['Running']
pending = [['R1', 'local_prior0'], ['R4', 'da3'], ['R2', 'local_prior0'],
           ['R5', 'da3'], ['R3', 'local_prior0'], ['R4', 'local_prior0'], ['R5', 'local_prior0']]
for region, branch in pending:
    for label in [branch, branch + '_preflight', 'extract_' + branch]:
        assert not (root / region / label).exists(), (region, label)
    if branch == 'da3':
        assert not (root / region / 'da3_input').exists()
        assert not (root / region / 'da3_inference').exists()
    else:
        assert json.loads((root / region / 'masks/receipt.json').read_text())['status'] == 'PASS'
folder = root / ('parallel_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
folder.mkdir()
shutil.copy2(root / 'execution/status.json', folder / 'previous_status.json')
shutil.copytree(old / 'source', folder / 'source', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
shutil.copy2(Path(__file__).with_name('parallel_queue.py'), folder / 'source/parallel_queue.py')
for p in (folder / 'source').rglob('*.py'):
    ast.parse(p.read_text(), filename=str(p))
plan = dict(unit='jbgs-r1r5-' + folder.name.replace('_', '-'), old_unit=unit,
    scheduler_pid=pid, scheduler_start_ticks=Path(f'/proc/{pid}/stat').read_text().split()[21],
    container_id=matched[0]['Id'],
    adopted_started_unix=json.loads((root / 'R3/da3/process.json').read_text())['started_unix'],
    pending=pending, gpus=[0, 1], ram_reservation_budget_gib=64,
    authorization='2026-09-18 user requested faster completion of the authorized background experiments',
    change='Two independent GPU workers; adopt live R3 DA3 container without interrupting training',
    fixed=['inputs', 'Anchor8k', 'iterations', 'resolution', 'losses', 'masks', 'seed',
           'densification', 'native protection', 'cudaMallocAsync allocator', 'TSDF parameters'],
    held_condition='R2/da3: previous OOM; no new retry', scientific_verdict=None)
(folder / 'plan.json').write_text(json.dumps(plan, indent=2))
(folder / 'source_hashes.json').write_text(json.dumps({str(p.relative_to(folder / 'source')):
    hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder / 'source').rglob('*') if p.is_file()}, indent=2))
launch = ['systemd-run', '--user', '--unit', plan['unit'], '--property=Type=exec',
          '--property=RemainAfterExit=yes', '--setenv=PYTHONDONTWRITEBYTECODE=1', '/usr/bin/python3',
          str(folder / 'source/parallel_queue.py'), str(root), str(folder)]
(folder / 'launch.json').write_text(json.dumps(launch, indent=2))
print(folder)
