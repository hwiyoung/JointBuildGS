"""Freeze measurement membership and inherited metric definitions before calculation."""
import json,subprocess
from run_pilot_r7 import REPO,PH,OUT,CFG,stamp,dump
from lock_continue_r7 import sha

def main():
 p=CFG/'scoring_continue_r7.json';assert not p.exists();rows=[]
 for prior in ['ALS','LoD2']:
  for family,it in [('r6',7000),('base',7000),('r7',7000),('r7',15000),('r7',30000),('base',30000)]:
   key=f'{family}_{prior}_{it}'
   if family=='base' and it==30000:
    root=PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10'/f'nojudge_{prior}_s0';current=root/'post/mesh_tsdf.ply';virtual=root/'gpu/virtual/mesh_virtual.ply';render=OUT/'r5/baselines'/f'depth_{prior}';model=root/'model'
   else:
    root=OUT/('r7_continue/attempt2' if it>7000 else ('r7' if family=='base' else family))/('baselines' if family=='base' else 'runs')/(f'base7k_B173nb_b10_{prior}_s0' if family=='base' else f'tg_B173nb_b10_{prior}_s0_{family}')
    model=root/'model';render=model/f'check{it}';current=root/f'post{it}/merged.ply';virtual=None
   def cp(x):return str(x).replace(str(REPO),'/repo').replace(str(PH),'/ph') if x else None
   inputs=[model/f'point_cloud/iteration_{it}/point_cloud.ply',current]+([virtual] if virtual else [])
   rows.append(dict(key=key,site='B173nb_b10',prior=prior,family=family,iteration=it,model=cp(model),current_mesh=cp(current),existing_virtual=cp(virtual),renders=cp(render),existing_inputs={cp(x):sha(x) for x in inputs if x.exists()}))
 files=[REPO/'configs/phd/main_axes71_v2/axes71_v2.json',REPO/'configs/phd/main_meshpatch_v1/mesh_targets_v1.json',REPO/'configs/phd/main_target_v1/post7000_r4.json',PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/received/geogs_original/utils/mesh_utils.py']
 for d in ['main_axes71_v2','main_dist71_v1']:
  files+=list((REPO/'scripts/phd'/d).glob('*.py'))
 files += [REPO/'scripts/phd/main_meshpatch_v1'/n for n in ['axes_adapter.py','mesh_common.py','mesh_worker.py']]
 files += [REPO/'scripts/phd/main_stage1_v1/gpu_s1.py',REPO/'src/phd/streamed_tsdf.py']
 for prior in ['ALS','LoD2']:
  files += [PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/work'/f'{kind}_B173nb_b10_{prior}.npz' for kind in ['cells','clumps']]
  files += [PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'B173nb_b10__{prior}'/n for n in ['evaluation.npz','values.npz']]
 files += [PH/'main_axes71_v2/PHD-MAIN-AXES71-v2/tables'/n for n in ['a3_metrics.json','a4_axes.json','a6_clumps.json']]
 c=dict(task_id='PHD-MAIN-TARGET-v1',at=stamp(),authority='decision_20261101_2115_continue_r7.md',rows=rows,
  source_files={str(x).replace(str(REPO),'/repo').replace(str(PH),'/ph'):sha(x) for x in files},
  axes=dict(source='PHD-MAIN-AXES71-v2',regions='frozen GT twelve cells only',counts='A through F; displayed default E',distance_unit='cm',each_mesh_independent=True,invisible_cells='use the specified mesh for every cell, no mixed-mesh rows; existing AXES rows retain original mixed-view provenance',clumps='reuse frozen clump IDs and area, apply same hit definitions to every GT cell including invisible cells'),
  current_mesh=dict(voxel=.05,sdf_trunc=.25,depth_trunc=300,views='all 203 training views',cleanup=False),
  final_mesh=dict(voxel=.10,sdf_trunc=.5,depth_trunc=300,views='203 training plus frozen 16 virtual views at original unseen.centre',subset='original gpu_s1 box',active_sh_degree=0,cleanup='original post_process_mesh(cluster_to_keep=50), ties retained',crop='all triangle vertices inside exact frozen eval_u/eval_v rectangle in original local BASIS'),
  als_diagnostic=dict(revisions=['r6','r7'],iteration=7000,counterfactual='original r6 Euclidean 0.5m query on r7 valid target points; original r6 targets also shown as separate reference',floating_pixels='project first-hit floating patch centres to saved training views; require depth agreement <=0.25m and alpha>1e-5; unique pixels per view; exact saved argmax alpha*T Gaussian; counts plus unavailable mapping',dominance='mean rendered contribution across visible first-hit correspondences >=0.5; ties by background/released/patch channel order; mixed and unavailable explicit',width='target patch halfwidth=1.96sigma; bins [0,.1),[.1,.5),[.5,1],(1,inf); no valid target is unavailable',area='sum frozen patch area, evaluate ranges only; 0~3 and full eligible reported'),
  other_six='NOT_STARTED',scientific_verdict=None)
 dump(p,c);dump(CFG/'scoring_continue_r7.lock.json',dict(at=stamp(),config_sha256=sha(p),scientific_verdict=None));print('SCORING_LOCKED',len(rows),flush=True)
if __name__=='__main__':main()
