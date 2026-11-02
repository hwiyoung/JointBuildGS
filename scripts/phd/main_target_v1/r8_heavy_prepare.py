"""Host stdlib: lock additive no-training heavy-view readout before calculation."""
import json,hashlib,datetime
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R.parent/'JointBuildGS-artifacts';O=A/'phase-payloads/phd/main_target_v1/PHD-MAIN-TARGET-v1';C=R/'configs/phd/main_target_v1';D=R/'docs/experiments/phd/main_target_v1'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def host(p):
 for pre,root in [('/repo',R),('/out',O),('/ph',A/'phase-payloads/phd'),('/art',A),('/cfg',C)]:
  if p==pre or p.startswith(pre+'/'):return root/p[len(pre)+1:]
 raise ValueError(p)
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat();root='/out/r8_recorded_continue';model=root+'/runs/tg_B173nb_b10_LoD2_s0_r8/model';old='/out/r8/runs/tg_B173nb_b10_LoD2_s0_r8/model';stop=json.loads((O/'r8_recorded_continue/STOP_LoD2.json').read_text());cam=stop['camera'];rows=[]
 for i in range(8000,14001,1000):
  for stage in ['pre','post']:
   rows.append(dict(key=f'r8_{i}_{stage}',iteration=i,stage=stage,family='r8',model=old,scene_iteration=7000,ply=model+(f'/point_cloud/iteration_{i}/point_cloud.ply' if stage=='pre' else f'/jbgs_complete/iteration_{i}/point_cloud.ply'),snapshot=model+f'/target_monitor/snapshot_{i}.npz' if stage=='pre' else None,checkpoint=model+f'/jbgs_complete/iteration_{i}/checkpoint.pth' if stage=='post' else None,cameras=[cam]))
 top=json.loads((O/'r8_recorded_continue/stop_diagnostic/renders/summary.json').read_text())['top5'];sd=stop['stop_dir']
 rows.append(dict(key='r8_14031_stop',iteration=14031,completed_iteration=14030,stage='before_attempt',family='r8',model=old,scene_iteration=7000,ply=sd+'/point_cloud.ply',snapshot=sd+'/snapshot_14031.npz',checkpoint=None,cameras=[r['camera'] for r in top]))
 base=next(r for r in json.loads((C/'cause_r8_lod2.json').read_text())['rows'] if r['key']=='base_LoD2_30000')
 rows.append(dict(key='base_LoD2_30000',iteration=30000,stage='saved_PLY',family='base',model=base['model'],scene_iteration=30000,ply=base['ply'],snapshot=None,checkpoint=None,cameras=[cam]))
 conf=dict(at=now,task_id='PHD-MAIN-TARGET-v1',authority='2026-11-02 user no additional training; saved-state heavy-view diagnosis',training=False,optimization_steps=0,heavy_camera=cam,rows=rows,boundaries='/out/r8_lod2_cause/boundaries.json',top_fractions=[.01,.1],denominator='all Gaussian rows including zero overlaps; ceil(fraction*N); descending tiles then ascending saved row index',quantiles=[0,1,5,25,50,75,95,99,100],histogram_edges=dict(camera_distance_m=[0,.2,.5,1,2,5,10,20,50,100,200,500,1000,5000,None],longest_axis_m=[0,.01,.025,.05,.1,.25,.5,1,2,5,10,20,50,100,500,None],opacity=[0,.01,.05,.1,.2,.4,.6,.8,1.0000001],radius_pixels=[-.5,.5,1.5,2.5,4.5,8.5,16.5,32.5,64.5,128.5,256.5,512.5,1024.5,2048.5,4096.5,8192.5,16384.5,None]),ancestor='immutable init_id and initial origin; immediate parent links were not saved',readout_capacity_fraction=.95,training_guard_unchanged=.5,scientific_verdict=None)
 cp=C/'r8_heavy.json';assert not cp.exists();dump(cp,conf)
 paths=[str(p) for row in rows for k,p in row.items() if k in ['ply','snapshot','checkpoint'] and p]+[conf['boundaries'],'/out/r8/stage1/B173nb_b10_LoD2/seeds.npz','/out/r7/stage1/B173nb_b10_LoD2/maps/index.json','/cfg/r8_heavy.json']
 paths += ['/repo/scripts/phd/main_target_v1/'+p.name for p in sorted((R/'scripts/phd/main_target_v1').glob('r8_heavy*.py'))]
 dump(C/'r8_heavy.lock.json',dict(at=now,files={p:sha(host(p)) for p in sorted(set(paths))},scientific_verdict=None));print('HEAVY_LOCKED',sha(cp),flush=True)
if __name__=='__main__':main()
