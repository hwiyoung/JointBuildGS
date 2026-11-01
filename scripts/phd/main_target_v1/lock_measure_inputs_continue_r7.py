"""Bind inherited evaluation and virtual-camera inputs before first mesh calculation."""
from lock_continue_r7 import REPO,PH,OUT,CFG,stamp,dump,sha

def main():
 files=[];site='B173nb_b10';s1=PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1';ax=PH/'main_axes71_v2/PHD-MAIN-AXES71-v2'
 files += [s1/'defs'/site/f for f in ['unseen.npz','top_raster.npz','gt_classes.npz','bsurf.npz']]
 files += [PH/'main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1'/p for p in [f's02_box/{site}/range.json',f's52/box_gt/{site}/gt_points.npz']]
 for prior in ['ALS','LoD2']:
  files += [s1/'regions_v3'/f'regions_ext_v3_{site}_{prior}.npz',s1/'defs'/site/f'rows_{prior}.npz',s1/'v3/box_gt'/site/f'gt_owner_{prior}.npz',OUT/'r7/targets'/f'{site}_{prior}.npz',OUT/'r7/stage1'/f'{site}_{prior}/maps/index.json']
 for d in ['work','dist']:
  files += [p for p in (ax/d).glob('*B173nb*') if p.is_file() and ('normal' in p.name or 'prefilter' in p.name)]
 files += [REPO/'configs/phd/main_target_v1/target_v1.runtime.r7.lock.json',REPO/'configs/phd/main_target_v1/scoring_continue_r7.lock.json',REPO/'configs/phd/main_prep_measure_v1/prep_v5.json']
 dest=CFG/'scoring_continue_r7.inputs.lock.json';assert not dest.exists();dump(dest,dict(at=stamp(),files={str(p).replace(str(REPO),'/repo').replace(str(PH),'/ph'):sha(p) for p in files},scientific_verdict=None));print('MEASUREMENT_INPUTS_LOCKED',len(files),flush=True)
if __name__=='__main__':main()
