"""Snapshot an allocator-only bounded retry and retain prior failed outputs."""
import argparse,ast,hashlib,json,shutil
from datetime import datetime,timezone
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('attempt',type=Path);a=ap.parse_args();root=a.attempt.resolve()
prior=json.loads((root/'execution/status.json').read_text())
assert (prior['state'],prior['region'],prior['job'])==('FAILED','R2','da3')
assert 'torch.cuda.OutOfMemoryError' in (root/'R2/da3/process.log').read_text()
recovery=root/('resource_recovery_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));recovery.mkdir()
shutil.copy2(root/'execution/status.json',recovery/'previous_status.json')
source=recovery/'source';shutil.copytree(root/prior['recovery']/'source',source,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
here=Path(__file__).resolve().parent
for n in ['run_queue.py','phase.py','resource_recovery_queue.py']:shutil.copy2(here/n,source/n)
for p in source.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
overrides={'R2':{n:f'R2/{n}_{recovery.name}' for n in ['da3_preflight','da3']}}
for rel in overrides['R2'].values():assert not (root/rel).exists()
unit='jbgs-r1r5-'+recovery.name.replace('_','-')
plan=dict(unit=unit,artifact_overrides=overrides,scientific_verdict=None,
          change='CUDA allocator only: native max_split_size_mb:128 -> cudaMallocAsync',
          fixed=['same Anchor8k','image membership and resolution','all loss weights','densification','random seed','native protection'],
          scope='One fresh R2 DA3 attempt, then each remaining independent condition once; failures recorded, no retry loop')
(recovery/'plan.json').write_text(json.dumps(plan,indent=2))
(recovery/'source_hashes.json').write_text(json.dumps({str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()},indent=2))
(recovery/'launch.json').write_text(json.dumps(['systemd-run','--user','--unit',unit,'--property=Type=exec','--property=RemainAfterExit=yes','--setenv=PYTHONDONTWRITEBYTECODE=1','/usr/bin/python3',str(source/'resource_recovery_queue.py'),str(root),str(recovery)],indent=2))
print(recovery)
