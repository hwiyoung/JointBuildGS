"""Freeze explicit missing-value handling before patch outcomes exist."""
import datetime as dt
import json
from pathlib import Path
from preflight import sha,dump
p=Path('/cfg/widen0_v2.json');c=json.loads(p.read_text())
assert not any(Path('/out/holdout/internal/work').glob('gt_*.npz'))
assert not any(a.get('id')=='availability_detail' for a in c['amendments'])
old=sha(p);p.with_name(f'widen0_v2.snapshot_{old[:12]}.json').write_bytes(p.read_bytes())
c['grid']['ownership']='Unregistered patch centre in core (lower inclusive, upper exclusive) and common support; registered coordinates used for measurements. Boundary ownership never moves with fitted shifts.'
c['cells']['availability']='Prior comparison requires inherited GT status 0 and finite gt_p. Other GT states enter no_gt with the original reason, including no face, insufficient points and plane failure; they are never reported as all zero-point cases. MVS correctness uses finite actual error e even when the ring fit or uncertainty is unavailable. Nonfinite e enters the appropriate no_mvs cell; a finite e with missing mvs_p remains in its correctness cell but is absent from difference distributions, whose missing area is reported.'
c['figures']['photo_margin_detail']='Project component patch corners moved by gt_p along normal; dilate their original-image outline by the projection of 3 m in the patch tangent plane for crop bounds. Retain image-edge clipping and missing-photo reasons.'
when=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()
c['amendments'].append(dict(id='availability_detail',at=when,before_patch_outcomes=True,previous_config_sha256=old,reason='Clarify exclusive cells when inherited GT or ring fit fails; retain finite actual errors independently of uncertainty availability. Make tile boundary ownership and photo margin explicit. No outcome inspected.'))
dump(p,c);dump(p.with_name('widen0_v2.lock.json'),dict(task_id=c['task_id'],locked_at=when,config_sha256=sha(p),before_patch_measurements=True,existing_building_split_unchanged=True,existing_image_split_unchanged=True,previous_config_sha256=old,scientific_verdict=None))
print(sha(p))
