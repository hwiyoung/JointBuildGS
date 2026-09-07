"""Host stdlib process supervisor. All scientific processing runs inside Docker."""
import datetime,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
REPO=Path(__file__).resolve().parents[3]
ART=(REPO/'../JointBuildGS-artifacts').resolve()
T=ART/'phase-payloads/phd/geogs_roof_bias_v1/GEOGS-ROOF-BIAS-20260921'
OLD=ART/'phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1'
IMAGE='sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e'
DEV=subprocess.check_output(['docker','image','inspect','jointbuildgs:dev','--format','{{.Id}}'],text=True).strip()
CONDITIONS=['N','B+0.25','B+0.5','B+1.0','B-1.0']
uid=f'{os.getuid()}:{os.getgid()}'
state={'task_id':T.name,'status':'RUNNING','phase':'WAIT_N','conditions':{},'scientific_verdict':None,'pid':os.getpid()}
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def status():
 state['updated_at']=stamp();p=T/'status.tmp';p.write_text(json.dumps(state,indent=2));p.replace(T/'status.json')
def call(name,phase,command,dev=False,gpu=False,expected=None):
 state.update(condition=name,phase=phase);status();root=T/'conditions'/name
 cname='roof-'+name.replace('+','p').replace('-','m').replace('.','_')+'-'+phase.replace('_','-')
 cmd=['docker','run','--rm','--name',cname,'--network','none','--user',uid,'--cpus','8','--shm-size','4g',
      '-e','PYTHONUNBUFFERED=1','-e','OMP_NUM_THREADS=8','-e','OPENBLAS_NUM_THREADS=8','-e','MPLCONFIGDIR=/tmp/mpl',
      '-e','TORCH_HOME=/weights/torch','-e','GEOGS_SOURCE=/source','-e','GEOGS_OBSERVATIONS=/output/observations',
      '-v',str(T)+':/task','-v',str(root)+':/output','-v',str(T/'scripts')+':/audit:ro',
      '-v',str(T/'sources/GeoGS')+':/source:ro','-v',str(OLD/'native_example/scene')+':/scene:ro',
      '-v',str(OLD/'native_example/scene')+':/original_scene:ro',
      '-v',str(OLD/'native_example/scene')+':/artifacts/JointBuildGS/'+str((OLD/'native_example/scene').relative_to(ART))+':ro',
      '-v',str(OLD/'runtime/weights')+':/weights:ro','-w','/source','--entrypoint','']
 if phase in ['crop','eval3d','analyze','export']:
  cmd+=['-v',str(OLD/'native_example/evaluation_reference')+':/reference:ro']
 if gpu:cmd+=['--gpus','"device=1"']
 cmd+=[DEV if dev else IMAGE]+command
 start=stamp();t=time.monotonic()
 with (root/(phase+'.log')).open('w') as log:
  rc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT).returncode
 okay=rc==0 and (expected is None or (T/expected).exists())
 receipt={'condition':name,'phase':phase,'command':cmd,'started_at':start,'finished_at':stamp(),'seconds':time.monotonic()-t,'exit_code':rc,'status':'PASS' if okay else 'FAILED','expected':expected,'scientific_verdict':None}
 (root/(phase+'_receipt.json')).write_text(json.dumps(receipt,indent=2))
 state['conditions'].setdefault(name,{})[phase]=receipt['status'];status()
 if not okay:
  with (T/'logs/issues.jsonl').open('a') as f:f.write(json.dumps(receipt)+'\n')
 return okay

status()
# Pin supervisor and scripts; the source checkout must remain byte-identical.
assert subprocess.check_output(['git','-C',str(T/'sources/GeoGS'),'rev-parse','HEAD'],text=True).strip()=='db40c95c657ec03ff21c83cb99cf39f4e90247a6'
assert not subprocess.check_output(['git','-C',str(T/'sources/GeoGS'),'status','--porcelain'],text=True).strip()
(T/'provenance/image_ids.json').write_text(json.dumps({'training':IMAGE,'analysis':DEV},indent=2))
subprocess.run(['docker','wait','jbgs-geogs-roof-bias-n-20260921'],check=False)
for name in CONDITIONS:
 root=T/'conditions'/name;root.mkdir(exist_ok=True)
 scene='/scene' if name=='N' else f'/task/conditions/{name}/scene'
 if name!='N':
  ok=call(name,'prepare_pcd',['python','/audit/run_seeded.py','/source/data/generate_pcd.py','--mesh_path',scene+'/lod2_biased.obj','--reference_frame_path','/task/provenance/reference_frame.json','--colmap_dir',scene+'/sparse_txt','--output_dir',scene+'/sparse_lod/0'],expected=f'conditions/{name}/scene/sparse_lod/0/points3D.txt')
  ok2=call(name,'prepare_depth',['python','/audit/run_seeded.py','/source/LoD2Depth/main.py','--mesh_path',scene+'/lod2_biased.obj','--reference_frame_path','/task/provenance/reference_frame.json','--reference_frame_path_building','/task/provenance/reference_frame.json','--colmap_dir',scene+'/sparse_txt','--building_name',name,'--generate_maps','--subset_images_dir',scene+'/images','--output_path',scene+'/transformed.obj','--output_building_path',scene+'/transformed_building.obj','--depth_normal_dir',scene+'/lod2_prior'],expected=f'conditions/{name}/scene/lod2_prior/raw_depth')
  if not (ok and ok2):continue
  trained=call(name,'train',['python','/audit/observe_train.py','-s',scene,'-m','/output/model','--lod_depth_path',scene+'/lod2_prior','--da_depth_path',scene+'/da3_prior','--lod2_pcd_path',scene+'/lod2_pcd.ply','--eval','--lod_init','--freeze_onlybldg','--protect_bldg','--dynamic_depth_weight'],gpu=True,expected=f'conditions/{name}/model/point_cloud/iteration_30000/point_cloud.ply')
 else:
  trained=(root/'train.exit').exists() and (root/'train.exit').read_text().strip()=='0'
  state['conditions']['N']={'train':'PASS' if trained else 'FAILED'};status()
 if trained:
  rendered=call(name,'render',['python','/source/render.py','-s',scene,'-m','/output/model','--iteration','30000','--mesh_res','1024'],gpu=True,expected=f'conditions/{name}/model/train/ours_30000/fuse_post.ply')
  call(name,'metrics',['python','/source/metrics.py','-m','/output/model'],gpu=True,expected=f'conditions/{name}/model/results.json')
  if rendered and call(name,'crop',['python','/audit/crop_mesh.py',name],dev=True,expected=f'conditions/{name}/evaluation/fuse_post_cropped.ply'):
   call(name,'eval3d',['bash','/audit/eval_3d.sh',name],expected=f'conditions/{name}/evaluation/native_results/eval_pred_points/statistics.txt')
 if trained:
  call(name,'mask8000',['python','/audit/native_mask.py',name],gpu=True,expected=f'conditions/{name}/analysis/native_mask8000.npy')
 call(name,'analyze',['python','/audit/analyze.py',name],dev=True,expected=f'conditions/{name}/analysis/summary.json')
 call(name,'export',['python','/audit/export.py'],dev=True,expected='report.md')
state['status']='COMPLETE' if all(all(x=='PASS' for x in state['conditions'].get(c,{}).values()) and 'analyze' in state['conditions'].get(c,{}) for c in CONDITIONS) else 'PARTIAL'
state['phase']='FINISHED';status()
# Final report reads final state.
call(CONDITIONS[-1],'export',['python','/audit/export.py'],dev=True,expected='report.md')
state['phase']='FINISHED';status()
