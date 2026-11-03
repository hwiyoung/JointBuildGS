"""Assemble table 9 from saved scores with missing 30k states explicit."""
from common import *
def main():
 rows=[];site='B173nb_b10'
 for prior in ['ALS','LoD2']:
  for family in ['r8_30000','baseline_30000']:
   key=f'{site}__{prior}__{family}'
   for mode in ['train','coarse','final']:
    scorekey=key if mode=='final' else key+'__'+mode;p=O/'scores'/scorekey/'values.json'
    if prior=='LoD2' and family=='r8_30000':rows.append(dict(site=site,prior=prior,key=key,mode=mode,status='확인 불가',reason='r8 LoD2 30,000회 저장 상태 없음; 7,000회로 대체하지 않음'));continue
    assert p.exists(),p;v=json.loads(p.read_text());missing=next(x for x in v['cells'] if x['cell']==4)
    rows.append(dict(site=site,prior=prior,key=key,mode=mode,status='PASS',provisional=family.startswith('r8'),label='옛 판단으로 학습한 임시값' if family.startswith('r8') else '기준선',**v['scene'],cell4_n_gt=missing['n_gt'],cell4_completeness=missing['completeness'],surface=v['mesh'],surface_sha256=v['mesh_sha256'],source=str(p),far_surface_train_vs_virtual_fraction=None,far_surface_origin_status='확인 불가: TSDF 혼합 면에는 시점별 기여가 저장되지 않음',source_tag='[이 발주에서 냄]'))
 for family in ['fusion_old','fusion']:
  p=O/'scores'/f'{site}__ALS__{family}/values.json';assert p.exists(),p;v=json.loads(p.read_text());rows.append(dict(site=site,prior='ALS',key=v['key'],mode=family,status='PASS',**v['scene'],surface=v['mesh'],surface_sha256=v['mesh_sha256'],source=str(p),source_tag='[이 발주에서 냄]'))
 table('table9',rows)
 for prior in ['ALS','LoD2']:
  p=O/'diagnostics'/f'{site}_jobs.json';jobs=json.loads(p.read_text())['jobs'];compare=[]
  for job in jobs:
   if job['prior']!=prior:continue
   for mode,key in [('final',job['key']),('train',job['score_key'])]:
    v=json.loads((O/'scores'/key/'values.json').read_text());c=next(x for x in v['cells'] if x['cell']==0);compare.append(dict(key=job['key'],mode=mode,cell0=c,scene=v['scene'],mesh=v['mesh'],source_tag='[이 발주에서 냄]'))
  table('low_cell0_mesh_comparison_'+prior,compare)
if __name__=='__main__':main()
