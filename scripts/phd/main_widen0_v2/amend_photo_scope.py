"""Correct photo coverage before any patch outcomes: missing MVS must remain in scope."""
import datetime as dt
import json
import shutil
from pathlib import Path
from preflight import sha, dump

C,O,D=Path('/cfg'),Path('/out'),Path('/docs')
p=C/'widen0_v2.json'
cfg=json.loads(p.read_text())
assert not (O/'patch_values').exists()
snapshot=C/'widen0_v2.before_photo_scope_correction.json'
if snapshot.exists():
    archive=O/'invalidated_input_scope_r0'
    assert archive.is_dir() and cfg['amendments'], 'incomplete amendment needs inspection'
    if (D/'tables/scope_split.json').exists() and not (O/'building_split.lock.json').exists():
        shutil.move(str(D/'tables/scope_split.json'),str(archive/'public_scope_split.json'))
    dump(archive/'INVALIDATED.json',dict(at=cfg['amendments'][-1]['at'],reason=cfg['amendments'][-1]['reason'],patch_outcomes_read=False,scientific_verdict=None))
    print('amendment finalized',sha(p))
    raise SystemExit(0)
snapshot.write_bytes(p.read_bytes())
(C/'widen0_v2.before_photo_scope_correction.lock.json').write_bytes((C/'widen0_v2.lock.json').read_bytes())
before=cfg['scope'].copy()
cfg['scope']['rule']='Intersection of photographic ground coverage, nadir ULS XY support, ALS XY support and raw LoD2 tile coverage. No MVS availability or patch outcome enters selection.'
cfg['scope']['coverage_source']='Raw full nadir extent; 0.5 m grid; ALS point occupancy; photographic coverage by projection into posed images of ALS class-2 ground height (nearest filled where empty).'
cfg['scope']['image_support']='Camera frustum on ALS terrain: grid centre in front and inside native 1400 x 1013 undistorted image. No MVS-depth requirement. Existing MVS occupancy is inventory only.'
when=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
cfg['amendments'].append(dict(at=when,before_patch_outcomes=True,reason='MVS-derived coverage would remove MVS-absent places requested by the order. Replace it with geometric photograph coverage and invalidate the preliminary building split before any outcomes.',previous_scope=before,previous_config_sha256=sha(p)))
dump(p,cfg)
dump(C/'widen0_v2.lock.json',dict(task_id=cfg['task_id'],locked_at=when,config_sha256=sha(p),before_patch_measurements=True,before_building_split=True,
    previous_lock_sha256=sha(C/'widen0_v2.before_photo_scope_correction.lock.json'),scientific_verdict=None))
archive=O/'invalidated_input_scope_r0';archive.mkdir()
for name in ['building_split.json','building_split.lock.json','scope_split.json','inputs']:
    src=O/name
    if src.exists():src.rename(archive/name)
if (D/'tables/scope_split.json').exists():
    shutil.move(str(D/'tables/scope_split.json'),str(archive/'public_scope_split.json'))
dump(archive/'INVALIDATED.json',dict(at=when,reason=cfg['amendments'][-1]['reason'],patch_outcomes_read=False,scientific_verdict=None))
print('amended',sha(p))
