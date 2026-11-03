"""Lock the actually completed endpoint before rendering or scoring."""
from r8_screen_prepare import *
import datetime
root=O/'rfix_continue/attempt2';out=O/'rfix_continue/final_endpoint';out.mkdir(exist_ok=False);stop=root/'STOP_LoD2.json';model=root/'runs/r8_LoD2_rfix/model'
if stop.exists():
 r=j(stop);assert r['ordinary_resume_ready'];it=r['completed_iteration'];checkpoint=local(r['stop_dir'])/'checkpoint.pth';ply=checkpoint.with_name('point_cloud.ply');snapshot=checkpoint.with_name('snapshot_'+str(r['attempted_iteration'])+'.npz');status=r['status']
else:
 assert (root/'TRAINING_COMPLETE.json').exists();it=30000;checkpoint=model/'jbgs_complete/iteration_30000/checkpoint.pth';ply=checkpoint.with_name('point_cloud.ply');snapshot=model/'target_monitor/snapshot_30000.npz';status='COMPLETED_30000'
row=dict(next(r for r in j(C/'rfix.json')['states'] if r['key']=='r8_LoD2_stop'))
scene_model=model;scene_it=it
if not (model/f'point_cloud/iteration_{it}/point_cloud.ply').exists():
 scene_model=O/'r8_recorded_continue/runs/tg_B173nb_b10_LoD2_s0_r8/model';scene_it=14000
row.update(key='r8_LoD2_rfix',iteration=it,scene_iteration=scene_it,model=docker(scene_model),actual_training_model=docker(model),checkpoint=docker(checkpoint),ply=docker(ply),snapshot=docker(snapshot))
c=dict(at=datetime.datetime.now().astimezone().isoformat(),state=row,status=status,extension=j(C/'rfix_continue.json')['extension'],inputs='/out/screen_sim/inputs/index.json',mesh='current TSDF0.05; sdf0.25,depth300,stride4; all203; same box',scoring='unchanged AXES71v2 12GTcells+3sums+all, precisionE',scientific_verdict=None)
dump(C/'rfix_final.json',c);paths=[C/'rfix_final.json',checkpoint,ply,snapshot,local(c['inputs']),local(c['extension']),C/'screen_sim_mesh.lock.json'];paths+=list((R/'scripts/phd/main_target_v1').glob('rfix_final*.py'));dump(C/'rfix_final.lock.json',dict(at=c['at'],files={docker(p):sha(p) for p in paths},scientific_verdict=None));print('ENDPOINT_LOCKED',it,status)
