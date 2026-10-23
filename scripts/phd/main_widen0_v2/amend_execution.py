"""Record execution dependencies before any patch-error measurement."""
import datetime as dt
import json
from pathlib import Path
from preflight import sha,dump
C=Path('/cfg');p=C/'widen0_v2.json';cfg=json.loads(p.read_text())
if any(a.get('id')=='execution_dependency' for a in cfg['amendments']):raise SystemExit('already recorded')
oldsha=sha(p);snapshot=C/f'widen0_v2.snapshot_{oldsha[:12]}.json';snapshot.write_bytes(p.read_bytes())
old=cfg['components']['groups'];cfg['components']['groups']=['prior','cell']
cfg['components']['building_note']='Connectivity follows same-cell distance only; components crossing buildings retain all building IDs and per-building areas. Development and holdout are always processed separately.'
cfg['seed_rule']='Inherited numpy default_rng scheme; full-area site index = sorted 100 m tile index. Prior index LoD2=0 ALS=1; data mvs_a=0 als=2 gt=3; ring=1 for 1.5 m and 9 for GT. Record changed context and indices in historical comparison.'
cfg['ground_truth']['height_shift_source']='Use exact stage-1 v3 frozen common_shift_m from v3/align/common_shift.json for nadir ULS; no new GT alignment fit.'
cfg['execution']['stage_dependency']='Stage A input/scope/split and prior meshes on CPU. New-area registered-prior errors require training-only MVS absent outside historical boxes. State this in the intermediate report, then complete CPU prior-error measurements after authorized stage B MVS; no evaluated-image MVS substituted.'
when=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
cfg['amendments'].append(dict(id='execution_dependency',at=when,before_patch_outcomes=True,
    reason='Preserve same-cell connectivity without adding a building/roof barrier; record random indices for new tiles and inherited GT shift. New-area prior registration needs training-only depth, so CPU error tables follow MVS rather than using evaluation-contaminated old depth.',
    previous_component_groups=old,previous_config_sha256=oldsha))
dump(p,cfg)
dump(C/'widen0_v2.lock.json',dict(task_id=cfg['task_id'],locked_at=when,config_sha256=sha(p),before_patch_measurements=True,
    existing_building_split_unchanged=True,existing_image_split_unchanged=True,previous_config_sha256=oldsha,scientific_verdict=None))
print(sha(p))
