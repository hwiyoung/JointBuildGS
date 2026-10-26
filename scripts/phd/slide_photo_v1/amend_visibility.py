from common import *
import shutil
config();p=CFG/'amendment_03_front_visibility.json'
if not p.exists():dump(p,dict(at=now(),task_id='PHD-SLIDE-PHOTO-v1',before_material_review=True,before_any_candidate_photo_was_viewed_by_the_agent=True,
 reason='Numerical audit found wall errors of 14-74m dominated by views from behind the surface. A sparse same-pixel GT z-buffer alone does not establish that the camera observes the front face. This is a visibility implementation defect.',
 correction='Require dot(outward_patch_normal, camera_centre - GT_point) > 0 before visible/accepted counts. Keep all original error, density, area and material rules unchanged.',
 previous_attempt='task0/mvs and first contact crops are invalidated, not used for selection. Recompute all 24 tiles under task0/mvs_v2.',scientific_verdict=None))
old=DOC/'figures/task0_crops';archive=PAY/'task0/invalidated_contact_v1'
if old.exists() and not archive.exists():shutil.move(str(old),str(archive))
(DOC/'figures/task0_crops').mkdir(exist_ok=True)
for name in ['task0_contact_sheet.png','task0_contact_sheet.json']:
    src=DOC/'figures'/name
    if src.exists() and not (archive/name).exists():shutil.move(str(src),str(archive/name))
p=PAY/'task0/components.json'
if p.exists():p.rename(PAY/'task0/components_invalidated_v1.json')
print('Visibility correction locked',sha(CFG/'amendment_03_front_visibility.json'))
