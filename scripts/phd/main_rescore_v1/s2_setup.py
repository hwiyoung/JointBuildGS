"""Bind stage 2 to existing training cameras, input scores and comparison meshes."""
from common import *
BASE=Path('/out');FT=PH/'main_finaltrain_v1/PHD-MAIN-FINALTRAIN-v1'
SITES2=['B0_b10','R1rep_b10']
def link(source,dest):
 dest.parent.mkdir(parents=True,exist_ok=True)
 if not dest.exists():dest.symlink_to(source,target_is_directory=source.is_dir())
def main():
 cfg();jobs=[];bindings={};availability=[]
 for folder in ['targets_v2','targets_oracle','targets_fusion']:link(BASE/folder,O/folder)
 for site in SITES2:
  p=BASE/'views'/f'{site}.json';v=json.loads(p.read_text());v['views']=[x for x in v['views'] if not x['virtual']];assert len(v['views'])>0
  split=json.loads((S0/'fork_inputs/s61'/site/'split.json').read_text());assert [x['name'] for x in v['views']]==sorted(split['train']);v.update(role='primary training-only cameras; no generated virtual camera',source=str(p),source_sha256=sha(p));dump(O/'views'/p.name,v);bindings[str(p)]=sha(p)
  for prior in ['ALS','LoD2']:
   for family in ['prior','mvs']:
    source=BASE/'scores'/f'{site}__{prior}__{family}';sv=json.loads((source/'values.json').read_text());assert sv['provenance']['cells_sha256']==sha(CELLS/f'{site}__{prior}.npz');link(source,O/'scores'/source.name);bindings[str(source/'values.json')]=sha(source/'values.json')
   for family in ['baseline_30000','GeoGS_30000','2DGS_30000','CDGS_30000','fusion','judgment_mesh','oracle']:
    key=f'{site}__{prior}__{family}';j=dict(site=site,prior=prior,family=family,key=key,views=len(v['views']),box=v['box'])
    if family.endswith('_30000'):
     raw=BASE/'meshes'/key/'train.ply';r=json.loads(raw.with_suffix('.json').read_text());assert r['views']==len(v['views']) and r['virtual_views']==0 and r['voxel_m']==.05 and r['trunc_m']==.25
     j.update(raw_train_mesh=str(raw),raw_sha256=r['mesh_sha256']);bindings[str(raw.with_suffix('.json'))]=sha(raw.with_suffix('.json'))
    else:j['cache']=str(O/'renders'/key)
    jobs.append(j);dump(O/'jobs'/f'{key}.json',j)
   model=FT/'runs'/site/f'ft_{prior}_s0/attempt1/model/point_cloud/iteration_30000/point_cloud.ply'
   availability.append(dict(site=site,prior=prior,model_30000=str(model),model_exists=model.exists(),depth_cache_exists=(FT/'meshes'/f'{site}__{prior}/render/receipt.json').exists(),source_tag='[이 발주에서 확인]'))
   bindings[str(CELLS/f'{site}__{prior}.npz')]=sha(CELLS/f'{site}__{prior}.npz')
 config=dict(task='PHD-MAIN-RESCORE-v1',addendum=3,stage=2,sites=SITES2,training=False,gpu='No GPU launched; clarification pending for stage2 inference scope',voxel_m=.05,trunc_m=.25,cluster_to_keep=50,virtual_views=0,sampling_density_m2=400,seed=0,unchanged=['judgment','tau','cells_v2','columns'],figure61_revision='four user changes; unchanged other labels/arrows; largest connected cell2 area; ALS skylight first, LoD2 fallback below 10 m2',sources=bindings,jobs=jobs,scientific_verdict=None)
 p=C/'addendum3_stage2.json';assert not p.exists();dump(p,config);dump(C/'addendum3_stage2.initial.lock.json',dict(at=now(),config_sha256=sha(p),scientific_verdict=None));table('initial_availability',availability)
 progress('단계 2 시작: B0·R1 두 사전 정보. 기존 학습 시점 메시·입력 점수 재사용, 결합·조합·상한은 고정 학습 시점의 CPU 깊이→같은 TSDF. 학습 없음. 예상 1~3시간; GPU 범위 확인 전 GPU 실행 없음. 그림 6.1 수정 병행. 이전 검증·그림 검토 반복 없음.')
 print('SETUP',len(jobs),availability,flush=True)
if __name__=='__main__':main()
