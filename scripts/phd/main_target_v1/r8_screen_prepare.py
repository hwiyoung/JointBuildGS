"""Lock a new read-only diagnostic. Never writes model, source, or old evidence."""
from pathlib import Path
import json,hashlib,datetime,subprocess
R=Path(__file__).resolve().parents[3];A=R.parent/'JointBuildGS-artifacts';PH=A/'phase-payloads/phd';O=PH/'main_target_v1/PHD-MAIN-TARGET-v1';C=R/'configs/phd/main_target_v1'
def j(p):return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def local(p):
 for pre,root in [('/repo',R),('/out',O),('/ph',PH),('/art',A),('/cfg',C)]:
  if p.startswith(pre+'/'):return root/p[len(pre)+1:]
 return Path(p)
def docker(p):
 p=Path(p).resolve()
 for root,pre in [(R,'/repo'),(O,'/out'),(PH,'/ph'),(A,'/art')]:
  if p.is_relative_to(root):return pre+'/'+str(p.relative_to(root))
 raise ValueError(str(p))
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 rec=O/'r8_recorded_continue';model=rec/'runs/tg_B173nb_b10_LoD2_s0_r8/model';broot=PH/'main_baselines_v1/PHD-MAIN-BASELINES-v1';sources=[]
 for label,receipt in [('baseline_ALS',PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10/nojudge_ALS_s0/receipt.json'),('baseline_LoD2',PH/'main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/B173nb_b10/nojudge_LoD2_s0/receipt.json'),('image_only_2DGS',broot/'runs/B173nb_b10/imgonly_2dgs_s0/receipt.json'),('GeoGS_ALS',broot/'runs/B173nb_b10/geogs_ALS_fix1/receipt.json'),('GeoGS_LoD2',PH/'main_fix_v1/PHD-MAIN-FIX-v1/runs/B173nb_b10/trust_LoD2_fix1/receipt.json')]:
  d=j(receipt);sources.append(dict(name=label,source=docker(d['source']),receipt=docker(receipt),model=docker(receipt.parent/'model'),executed=True,command=d.get('command'),image=d.get('image'),image_id=d.get('image_id')))
 sources += [dict(name='r22_r8',source='/repo/src/phd/forks/GeoGS-conf-guided-v1-r22',receipt='/out/r8_recorded_continue/STOP_LoD2.json',model=docker(model),executed=True),dict(name='original_2DGS',source=docker(broot/'sources/2d-gaussian-splatting'),executed=False,commit=subprocess.check_output(['git','-C',str(broot/'sources/2d-gaussian-splatting'),'rev-parse','HEAD'],text=True).strip(),url='https://github.com/hbb1/2d-gaussian-splatting'),dict(name='CDGS_prepared_only',source=docker(broot/'sources/cdgs-release-adapters-v2'),executed=False,receipt=docker(broot/'prep/cdgs/READY.json'),note='Prior preparation gate stopped all CDGS training; do not claim enabled in a completed run')]
 cause=j(C/'cause_r8_lod2.json');keys=['base_LoD2_30000','r7_LoD2_30000','r8_ALS_30000'];states=[dict(key=k,arrays=f'/out/r8_lod2_cause/states/{k}/arrays.npz',**{kk:vv for kk,vv in next(r for r in cause['rows'] if r['key']==k).items() if kk in ['checkpoint','model']}) for k in keys]
 states.append(dict(key='r8_LoD2_stop',arrays=docker(rec/'stop_diagnostic/arrays.npz'),checkpoint=j(rec/'STOP_LoD2.json')['stop_dir']+'/checkpoint.pth',model=docker(model)))
 config=dict(at=datetime.datetime.now().astimezone().isoformat(),task_id='PHD-MAIN-TARGET-v1',authority='2026-11-02 user screen-size cleanup read-only diagnosis',sources=sources,states=states,record_root=docker(rec),model=docker(model),original_7000=j(C/'r8_record_continue.json')['checkpoint'],camera_index='/out/r7/stage1/B173nb_b10_LoD2/maps/index.json',boundaries='/out/r8_lod2_cause/boundaries.json',heavy_camera='DJI_20241217102535_0020_D',top_fraction=.01,top_definition='each saved-state all rows, ceil(N*.01), descending tiles then saved index; stopped top1 initial seed cohort separately',camera_distance='horizontal Euclidean distance to fixed evaluation rectangle; additional 3D centre-to-Gaussian radius <=30m',camera_radius_m=30,near_center_m=.2,alpha_definition='max over image pixels of accepted alpha*T; zero may be proven by exact all-zero alpha of full selected-subset forward and nonnegative compositing',survival='same-iteration pre/post density retained-original prefix according to unmodified rules, validate immutable IDs and exact saved row parameters; no immediate-parent ID invention',history='Python RNG and camera stack replay only, verify every saved end RNG/stack and every100 trace; no optimization or scene evolution',training=False,code_changes=False,scientific_verdict=None)
 cfg=C/'r8_screen.json';assert not cfg.exists();dump(cfg,config);paths=[cfg,local(config['camera_index']),local(config['boundaries']),local(config['original_7000']),model/'cameras.json',model/'recording/forward_100.jsonl',model/'recording/after_iteration_100.jsonl',model/'jbgs_trace.jsonl',rec/'heavy/subset/top1.npz',rec/'heavy/states/r8_14031_stop/arrays.npz',rec/'heavy/states/r8_14031_stop'/f'{config["heavy_camera"]}.npz']
 for row in sources:
  source=local(row['source']);paths.extend(source/r for r in ['train.py','scene/gaussian_model.py','scene/__init__.py','scene/dataset_readers.py','arguments/__init__.py'] if (source/r).exists())
  if row.get('receipt'):paths.append(local(row['receipt']))
  if row.get('model') and (local(row['model'])/'cameras.json').exists():paths.append(local(row['model'])/'cameras.json')
 for i in range(8000,14001,1000):
  paths += [model/f'jbgs_complete/iteration_{i}/checkpoint.pth',model/f'jbgs_complete/iteration_{i}/point_cloud.ply',model/f'point_cloud/iteration_{i}/point_cloud.ply',model/f'recording/pre_densification/iteration_{i}/gradient.npz',model/f'target_monitor/snapshot_{i}.npz',rec/f'heavy/states/r8_{i}_pre/arrays.npz',rec/f'heavy/states/r8_{i}_pre/{config["heavy_camera"]}.npz']
 for row in states:paths += [local(row['arrays']),local(row['checkpoint'])]
 paths += [rec/'runtime/train_recorded.py',rec/'runtime/rasterizer/cuda_rasterizer/forward.cu',rec/'runtime/rasterizer/cuda_rasterizer/auxiliary.h',R/'scripts/phd/main_target_v1/r8_record_hooks.py']
 paths += list((R/'scripts/phd/main_target_v1').glob('r8_screen*.py'))
 dump(C/'r8_screen.lock.json',dict(at=config['at'],config_sha256=sha(cfg),files={docker(p):sha(p) for p in sorted(set(paths))},scientific_verdict=None));print('SCREEN_LOCKED',len(set(paths)),flush=True)
if __name__=='__main__':main()
