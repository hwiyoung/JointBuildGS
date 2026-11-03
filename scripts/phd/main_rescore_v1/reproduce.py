"""One legacy recount from the exact saved per-point distances and bound meshes."""
from common import *
from metrics import four,inherited_result_mask
def main():
 start=time.monotonic();c=cfg();rows=[]
 for key,root,expect in [('r8_ALS_30000',TG/'r8/scoring/r8_ALS_30000/current',c['reproduction']['method']),('base_ALS_30000',TG/'r7_continue/scoring/base_ALS_30000/current',c['reproduction']['baseline'])]:
  p=root/'dist'/f'B173nb_b10_ALS__{key}.npz';xp=p.with_name(p.stem+'__x.npz');z=loadz(p,['s_d','q_patch','q_tau']);x=loadz(xp,['ndist','lat']);binding=json.loads((root/'binding.json').read_text());mesh=Path(binding['mesh'].replace('/ph/',str(PH)+'/').replace('/target/',str(TG)+'/'))
  assert sha(mesh)==binding['mesh_sha256']
  v=four(z['s_d'],x['ndist'],.147,.147,result_mask=inherited_result_mask(x['ndist'],x['lat']))
  actual=[v['completeness']*100,v['accuracy']*100,v['gt_mean_m']*100,v['result_mean_m']*100];delta=[a-b for a,b in zip(actual,expect)]
  rows.append(dict(key=key,**v,actual_pct_pct_cm_cm=actual,expected_pct_pct_cm_cm=expect,delta_pp_pp_cm_cm=delta,pass_tolerance=all(abs(a)<=.1 for a in delta),over_stop_tolerance=any(abs(a)>1 for a in delta),source=str(p),source_sha256=sha(p),normal_source=str(xp),normal_source_sha256=sha(xp),mesh=str(mesh),mesh_sha256=sha(mesh),n_result_before_reference_eligibility=len(x['ndist']),method='saved per-point distances recounted by new four(); geometric distance computation reused, not independently rerun',source_tag='[이 발주에서 냄]'))
 table('reproduction',rows);timing('legacy_reproduction',start)
 print('REPRODUCTION',[(x['key'],x['actual_pct_pct_cm_cm'],x['pass_tolerance']) for x in rows])  # Addendum 1 removes the stop.
if __name__=='__main__':main()
