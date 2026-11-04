"""Addendum 3, B173 only: preserve the original delivery and bind immutable caches."""
from common import *
import shutil
BASE=Path('/out');FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1';SITE='B173nb_b10'
def link(a,b):
 b.parent.mkdir(parents=True,exist_ok=True)
 if not b.exists():b.symlink_to(a,target_is_directory=a.is_dir())
def main():
 cfg();jobs=[];sources={}
 for folder in ['views','targets_v2','targets_oracle','targets_fusion']:link(BASE/folder,O/folder)
 for prior in ['ALS','LoD2']:
  for family in ['prior','mvs']:link(BASE/'scores'/f'{SITE}__{prior}__{family}',O/'scores'/f'{SITE}__{prior}__{family}')
  for family in ['baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','fusion','judgment_mesh','oracle','FINALTRAIN_30000']:
   key=f'{SITE}__{prior}__{family}';j=dict(site=SITE,prior=prior,family=family,key=key)
   if family=='FINALTRAIN_30000':
    cache=FT/'meshes'/f'{SITE}__{prior}'/'render';j['cache']=str(cache)
    model=FT/'runs'/SITE/f'ft_{prior}_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply';assert model.exists();j['ply']=str(model)
    r=json.loads((cache/'receipt.json').read_text());assert sha(model)==r['model_sha256'];sources[str(model)]=r['model_sha256']
   else:
    old=json.loads((BASE/'jobs'/f'{key}.json').read_text());j.update(old);j['cache']=str(BASE/'renders'/key)
   if family in ['baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000']:
    raw=BASE/'meshes'/key/'train.ply';rr=raw.with_suffix('.json');r=json.loads(rr.read_text());assert r['views']==203 and r['virtual_views']==0 and r['voxel_m']==.05 and r['trunc_m']==.25
    j['raw_train_mesh']=str(raw);j['raw_sha256']=r['mesh_sha256'];sources[str(rr)]=sha(rr)
   else:sources[j['cache']+'/receipt.json']=sha(Path(j['cache'])/'receipt.json')
   jobs.append(j);dump(O/'jobs'/f'{key}.json',j)
 for prior in ['ALS','LoD2']:sources[str(CELLS/f'{SITE}__{prior}.npz')]=sha(CELLS/f'{SITE}__{prior}.npz')
 config=dict(task='PHD-MAIN-RESCORE-v1',addendum=3,stage=1,sites=[SITE],priors=['ALS','LoD2'],training=False,views=203,virtual_views=0,voxel_m=.05,trunc_m=.25,cluster_to_keep=50,evaluation_crop=True,sampling_density_m2=400,seed=0,tau_cells_columns='unchanged',r8_in_primary_tables=False,previous_final_scores='mesh-rule diagnostic, preserved',stage2='explicit user start only; no polling',jobs=jobs,sources=sources,scientific_verdict=None)
 p=C/'addendum3_stage1.json';assert not p.exists();dump(p,config);dump(C/'addendum3_stage1.initial.lock.json',dict(at=now(),config_sha256=sha(p),scientific_verdict=None))
 progress('덧붙임 3 단계 1 시작: B173 주변만; 입력 점수 재사용, 학습 시점 203개, 가상 시점 0, 0.05/0.25 m, 덩어리 50, 평가 범위 자르기. 기존 묶음 보존. 기존 재현 검사 반복 없음. 예상 2~4시간(기존 TSDF 판당 약 10분, 채점·그림 포함). 단계 2 상태 조회 없음.')
 print('SETUP',len(jobs))
if __name__=='__main__':main()
