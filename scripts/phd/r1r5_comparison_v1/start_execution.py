"""Seal the execution drivers and launch the authorized background queue once."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[3];root=Path(sys.argv[1]).resolve();source=root/'execution/source';source.mkdir(parents=True)
for p in (repo/'scripts/phd/r1r5_comparison_v1').glob('*.py'):shutil.copy2(p,source/p.name)
shutil.copy2(repo/'scripts/phd/geogs_mvs_pgsr_v1/run_phase.py',source/'legacy_validation.py')
shutil.copytree(repo/'scripts/phd/geogs_p1p2p3_v1/da3',source/'da3',ignore=shutil.ignore_patterns('__pycache__'))
for src,dest in [('experiment_v1.json','da3_config.json'),('da3_batch_revision_v2.json','da3_policy.json')]:
    shutil.copy2(repo/'configs/phd/geogs_p1p2p3_v1'/src,source/dest)
c=json.loads((source/'da3_config.json').read_text());c['task_id']='PHD-R1R5-COMPARISON-v1';(source/'da3_config.json').write_text(json.dumps(c,indent=2))
(source/'hashes.json').write_text(json.dumps({str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()},indent=2))
unit='jbgs-r1r5-execution-'+root.name
(root/'execution/unit.txt').write_text(unit+'\n')
subprocess.run(['systemd-run','--user','--unit',unit,'--property=Type=exec','--property=RemainAfterExit=yes',
    '/usr/bin/python3',str(source/'run_queue.py'),str(root)],check=True)
print(unit)
