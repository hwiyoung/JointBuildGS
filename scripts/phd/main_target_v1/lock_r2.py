"""Prospective r2 amendment after input-count audit, before revised decisions."""
import os, shutil
from common import *


def main():
    dest=CFG/'revisions/r1_stage1'; assert not dest.exists()
    dest.mkdir()
    for name in ['target_v1.json','target_v1.stage0.lock.json','target_v1.stage1.lock.json']:
        shutil.copy2(CFG/name,dest/name)
    olddoc=DOC/'revisions/r1_stage1';olddoc.mkdir()
    for name in ['영역별목표학습_보고_v1.md','progress.md']:
        if (DOC/name).exists():shutil.copy2(DOC/name,olddoc/name)
    archive=OUT/'revisions/r1_stage1_source';archive.mkdir(parents=True)
    shutil.copytree(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19',archive/'fork')
    shutil.copytree(REPO/'scripts/phd/main_target_v1',archive/'scripts')
    cfg=json.loads((CFG/'target_v1.json').read_text());previous=sha(CFG/'target_v1.json')
    old=cfg['cylinder'].copy()
    cfg['revision']='r2_user_decision_20261101'
    cfg['cylinder'].update(half_length_m={'roof':10.,'wall':5.},
        missing_face='retain raw count; zero points versus 1-3 selected points versus face failure recorded separately',
        face_implementation='scripts/phd/main_target_v1/cylinders_r2.cpp',
        fallback={'trigger':'inherited selected n<4 and raw column n>=4',
                  'rule':'densest existing 0.30m layer on the same 0.05m scan grid; outermost on ties; select its +/-1m slab; n<4 remains unobserved',
                  'reason':'global 20 percent share can fail when a cylinder contains several surfaces or distributed points; maximum local support is GT-free; do not change inherited n>=4 faces',
                  'source_sha256':sha(Path(__file__).with_name('cylinders_r2.cpp'))})
    cfg['stage1']['initialization'].update(
        source='retained original prior seeds plus confidence-masked own training MVS A points',
        image_exclusion='union of prior patch cylinders with frozen radius by prior/kind and half lengths roof10m/wall5m; exclude before thinning',
        background='MVS points; deterministic 0.25m cubic voxel thinning, first point in original UNCERT random-key order; source training view supplies RGB and finite-difference MVS normal; normal missing => vertical up',
        background_scale='same baseline log(sqrt(clamp_min(distCUDA2(initial combined XYZ),1e-7))) rule for new MVS seeds; retained prior seed scales unchanged',
        comparison_difference='baseline background uses SfM sparse points; r2 uses confidence-masked MVS points; record in report and comparison table')
    cfg['amendments'].append(dict(at=stamp(),authority='user 2026-11-01 stage1-stop decision',
        previous_config_sha256=previous,previous_cylinder=old,
        reason='user-authorized MVS background and observation repair; input-only audit; no r2 judgments or accuracy inspected',
        input_audit_sha256=sha(OUT/'r2/input_audit/counts.json')))
    cfg['stage_status']={'stage0':'R2_LOCKED_BEFORE_RECOMPUTATION','stage1':'NOT_RETESTED','stage2':'NOT_STARTED'}
    dump(CFG/'target_v1.json',cfg)
    r2=CFG/'revisions/r2';r2.mkdir();shutil.copy2(CFG/'target_v1.json',r2/'target_v1.json')
    lock=dict(at=stamp(),revision='r2',config_sha256=sha(CFG/'target_v1.json'),previous_config_sha256=previous,
        source_commit=os.environ.get('TARGET_COMMIT'),image_id=os.environ.get('TARGET_IMAGE'),
        pre_computation=True,scientific_verdict=None)
    dump(CFG/'target_v1.r2.lock.json',lock)
    print(json.dumps(lock),flush=True)


if __name__=='__main__':main()
