"""Snapshot an additive R1-R5 comparison task and start CPU input preparation."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

repo=Path(__file__).resolve().parents[3]
artifacts=(repo/'../JointBuildGS-artifacts').resolve()
task='PHD-R1R5-COMPARISON-v1'
owner=artifacts/'phase-payloads/phd/r1r5_comparison_v1'/task
owner.mkdir(parents=True,exist_ok=True)
attempt=Path(tempfile.mkdtemp(prefix=time.strftime('attempt_%Y%m%dT%H%M%SZ_',time.gmtime()),dir=owner))
def dump(path,obj): path.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
audit_relative='phase-payloads/phd/region_view_support_v1/PHD-R1R5-VIEW-SUPPORT-v1/attempt_20260915T130845Z_TkeMtl'
audit=artifacts/audit_relative
members=json.loads((audit/'result/candidate_memberships.json').read_text())['regions']
config=dict(task_id=task,artifact_root=str(artifacts),audit_relative=audit_relative,
    camera_relative='phase-payloads/p0-audit/data/work/mvs/colmap_dense',regions=['R1','R2','R3','R4','R5'],
    prepare_regions=['R2','R3','R4','R5'],scientific_verdict=None,
    conditions=['prior','mvs','anchor','mvs_geogs','da3_geogs','local_prior0'],
    local_prior0='Only reviewed correction surfaces; all other prior pixels retain .005; native protection retained',
    sky_steam_policy='Existing unmasked baseline policy shared; no new sky/steam preprocessing factor',
    authorization='2026-09-17 user requested unified six-panel R1-R5 comparison, DA3 branch, and per-region reviewed correction areas with local prior depth weight zero; background preparation/training/extraction authorized by this request.',
    r1_prep_relative='phase-payloads/phd/r1_mvs_control_v1/PHD-R1-MVS-CONTROL-PREP-v1/attempt_20260916T130151Z_jm4gu7vc',
    r1_run_relative='phase-payloads/phd/r1_mvs_control_run_v1/PHD-R1-MVS-CONTROL-RUN-v1/attempt_20260916T141804Z_0zDUJ0xj')
dump(attempt/'config.json',config)
configs=repo/'configs/phd/r1r5_comparison_v1';configs.mkdir(exist_ok=True)
for region in config['prepare_regions']:
    m=members[region]; counts=dict(all=len(m['candidates']),train=len(m['train']),evaluation=len(m['evaluation']))
    p=json.loads((repo/'configs/phd/r1_mvs_control_v1/preparation_v1.json').read_text())
    p.update(task_id=task,region=region,expected_counts=counts,authorization=config['authorization'])
    p['baseline']['condition_id']=region+'_MVS_D005_Pnative';p.pop('observation_draft')
    p['baseline']['same_anchor_future_branches']=f'Share new complete {region} Anchor8k across MVS, DA3 and local prior0'
    r=json.loads((repo/'configs/phd/r1_mvs_control_v1/runtime_v1.json').read_text())
    r.update(task_id=task,regions=[region],expected_counts=counts)
    for name,value in [(region+'_preparation.json',p),(region+'_runtime.json',r)]:
        path=configs/name
        if path.exists(): raise FileExistsError(path)
        dump(path,value)
snapshot=attempt/'snapshot';snapshot.mkdir()
for rel in ['scripts/phd/r1r5_comparison_v1','scripts/phd/r1_mvs_control_v1','scripts/phd/geogs_p1p2p3_v1/input',
    'scripts/phd/wu_vallet_p3_v2','src/phd/region_view_support_v1.py','src/phd/geogs_mvs_pgsr_v1',
    'src/phd/wu_vallet_p3_v1','src/phd/wu_vallet_p3_v2','configs/phd/r1r5_comparison_v1',
    'configs/phd/mvs_als_source_relation_v1/run_v1.json']:
    source=repo/rel;dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True)
    if source.is_dir():shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__'))
    else:shutil.copy2(source,dest)
dump(attempt/'source_hashes.json',{str(p.relative_to(snapshot)):hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.rglob('*') if p.is_file()})
(attempt/'commit.txt').write_bytes(subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']))
dump(attempt/'images.json',json.loads(subprocess.check_output(['docker','image','inspect','sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774'])))
unit='jbgs-r1r5-prep-'+attempt.name
(attempt/'preparation_unit.txt').write_text(unit+'\n')
subprocess.run(['systemd-run','--user','--unit',unit,'--property=Type=exec','--property=RemainAfterExit=yes',
    '/usr/bin/python3',str(snapshot/'scripts/phd/r1r5_comparison_v1/prepare_queue.py'),str(attempt)],check=True)
print(attempt)
