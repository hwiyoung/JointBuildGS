"""Extrapolate from the completed first production mesh, without a timing probe."""
from common import *
def main():
 c=cfg();first=O/'meshes/B173nb_b10__ALS__r8_30000/final.json';assert json.loads(first.read_text())['status']=='PASS'
 measured=[json.loads(p.read_text()) for p in sorted((O/'timing').glob('first_mesh_*.json'))]
 seconds=sum(x['seconds'] for x in measured);selected={}
 for r in json.loads((O/'inventory.json').read_text())['rows']:
  if r['family']=='r7':continue
  k=(r['site'],r['prior'],r['family'])
  if r['iteration']==30000 or r['iteration']==7000 and k not in selected:selected[k]=r
 unique={r['model']:r for r in selected.values()};jobs=[]
 for model,r in unique.items():jobs.append(dict(site=r['site'],prior=r['prior'],family=r['family'],iteration=r['iteration'],model=model,type='trained_final'))
 for site in SITES[:3]:
  for prior in ['LoD2','ALS']:
   for family in ['fusion','judgment_mesh','oracle']:jobs.append(dict(site=site,prior=prior,family=family,type='patch_final'))
 for j in jobs:
  split=S0/'fork_inputs/s61'/j['site']/'split.json';n=len(json.loads(split.read_text())['train']);j.update(train_views=n,virtual_views=16,views=n+16,equivalent_first_mesh=(n+16)/219,estimated_seconds=seconds*(n+16)/219,view_source=str(split))
 subtotal=sum(j['estimated_seconds'] for j in jobs);stop=False  # User addendum 1 removes the time stop.
 result=dict(at=now(),status='ESTIMATE_ONLY_ADDENDUM1_NO_STOP',first_mesh_seconds=seconds,measured_terms=measured,first_mesh_path=str(first),first_mesh_receipt_sha256=sha(first),mesh_jobs=len(jobs),trained_unique_models=len(unique),patch_mesh_jobs=18,scoring_arms=len(selected),estimated_mesh_hours=subtotal/3600,threshold_hours=None,
 assumptions=['same first-mesh preparation, TSDF, merge and cleanup workload per view; actual triangle/volume complexity may differ by method and region','sequential CPU containers, nice 19, at most 32 GiB each; same execution policy as first mesh','2DGS shared across two evaluation priors: counted once per region','unavailable B173-only JUDGEAPPLY core files: no invented patch meshes'],
 not_yet_estimated=['new renderer work where no matching depth cache exists','training-view meshes not already available with identical rules','old-setting diagnostic meshes if unavailable','new column ownership and all metric tables','figures and packaging'],
 estimate_scope='mesh production subtotal only; omitted items are not assumed zero or completed; workload scaling is an estimate, not a bound on actual time',jobs=jobs,scientific_verdict=None)
 dump(O/'time_gate.json',result);dump(D/'tables/time_gate.json',result)
 progress(f'첫 최종 메시 실제 계산 합계 {seconds:.1f}초. 최종 메시 {len(jobs)}개를 시점 수로 환산한 제작 시간 어림 {subtotal/3600:.3f}시간. 나머지 채점·그림 시간은 미산정. {result["status"]}.')
 if stop:dump(O/'STOP_TOTAL_TIME_ESTIMATE.json',result)
 print('TIME_GATE',result['status'],seconds,subtotal/3600,len(jobs))
if __name__=='__main__':main()
