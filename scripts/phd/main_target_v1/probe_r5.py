from common import *
import numpy as np
mp=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1';w=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2'
for p in [mp/'patch_table/ALS_patch_table.npz',next((OUT/'r2/stage0/development').glob('*__ALS.npz')),next((JN/'core_points').glob('*__ALS.npz')),OUT/'r2/targets/B173nb_b10_ALS.npz',next((OUT/'r2/stage0/core_stats').glob('*.npz')),OUT/'r2/stage1/B173nb_b10_ALS/seeds.npz',S1/'regions_v3/regions_ext_v3_B173nb_b10_ALS.npz']:
 with np.load(p) as z:
  print(str(p),[(k,z[k].shape,str(z[k].dtype)) for k in z.files],flush=True)
print('CASES',{p:list(v) for p,v in json.loads((mp/'received/track_a_v3/results/cases.json').read_text()).items()})
for p in [w/'holdout/patch_values',JN/'holdout/core_points',OUT/'holdout/r2/stage0']:
 print('FILES',p,[x.name for x in p.glob('*.npz')][:5])
for prior in ['ALS','LoD2']:
 model=OUT/'r4n/runs'/f'tg_B173nb_b10_{prior}_s0'/'model';cmd=json.loads((model.parent/'command.json').read_text());files=sorted(str(x.relative_to(model)) for x in model.rglob('*') if x.is_file() and (x.suffix in ['.pt','.pth','.ckpt'] or 'checkpoint' in x.name))
 fields={}
 for p in sorted((model/'target_monitor').glob('snapshot_*.npz')):
  with np.load(p) as z:fields[p.name]=z.files
 assert not files and '--checkpoint_iterations' not in cmd and '--start_checkpoint' not in cmd
 dump(OUT/'r5'/f'resume_audit_{prior}.json',dict(at=stamp(),status='NOT_RUN_NO_OPTIMIZER_STATE',checkpoint_files=files,snapshot_fields=fields,checkpoint_cli_present=False,reason='checkpoint_iterations default []; only scene PLY and target-monitor snapshots saved. Neither contains Adam moment buffers or parameter-group state. Reinitializing Adam would not resume optimizer state.',source_sha256=sha(REPO/'src/phd/forks/GeoGS-conf-guided-v1-r19/train.py'),scientific_verdict=None))
