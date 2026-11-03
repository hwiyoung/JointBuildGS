"""Independent counts/sums over frozen distance arrays and surface categories."""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from axes_adapter import ax,aa
from mesh_common import dump,sha,now
from verify_scores_r8 import equal,gverify,sverify
ROOT=Path('/target/rfix_continue/final_endpoint');KEY='r8_LoD2_rfix_current';SITE='B173nb_b10';PRIOR='LoD2'
def main():
 root=ROOT/'scores/r8_LoD2_rfix/current/LoD2';p=root/'values.json';r=json.loads(p.read_text());C=aa.cells(SITE,PRIOR);prefix=root/'dist'/f'{SITE}_{PRIOR}__{KEY}';files=[prefix.with_suffix('.npz'),prefix.with_name(prefix.name+'__x.npz')];A=aa.arrays(SITE,PRIOR,KEY,C,paths=(*files,None));checked=0
 for cell,b in r['metrics'].items():
  g=A['scene'] if cell=='all' else aa.sel(A['rows'],aa.cell_sel(A['rows']['cell'],cell,ax.SUMS));s=A['smp'] if cell=='all' else aa.sel(A['smp'],aa.cell_sel(A['smp']['cell'],cell,ax.SUMS));gverify(g,b['gt']);sverify(s,b['res']);checked+=1
 assert checked==16
 e=np.load(ax.PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{SITE}__{PRIOR}/evaluation.npz');z=np.load(root/'patch_z.npz');assert np.array_equal(z['gt_cell'],C['cell']);allowed=e['in_eval']&e['scoring_allowed'];t=np.load('/target/r7/targets/B173nb_b10_LoD2.npz');assert np.allclose(e['centre'],t['centre'],atol=1e-8,rtol=0)
 for cell,b in r['surface'].items():
  m=allowed if cell=='all' else allowed&aa.cell_sel(C['cell'],cell,ax.SUMS);a=float(e['area'][m].sum());f=float(e['area'][m&(z['category']==1)].sum());v=float(e['area'][m&z['no_surface']].sum());assert b['patches']==int(m.sum());equal(a,b['area_m2'],'area');equal(f,b['floating_area_m2'],'float area');equal(v,b['no_surface_area_m2'],'missing area');equal(f/a if a else None,b['floating_fraction'],'float fraction');equal(v/a if a else None,b['no_surface_fraction'],'missing fraction')
 for field in ['area_m2','floating_area_m2','no_surface_area_m2']:equal(sum(r['surface'][c][field] for c in ax.CELLS),r['surface']['all'][field],'cell area conservation '+field)
 for b in json.loads((root/'result_vs_target.json').read_text())['rows']:
  m=allowed&(t['region']==b['region'])
  if b['replacement']=='original':m &= ~t['any_replaced']
  if b['replacement']=='replaced':m &= t['any_replaced']
  area=float(e['area'][m].sum());equal(area,b['area_m2'],'target area');equal(float(e['area'][m&(z['category']==0)].sum()/area) if area else None,b['result_within_tau_fraction'],'target result')
 mesh=ROOT/'meshes/r8_LoD2_rfix/current/merged.ply';assert sha(mesh)==r['mesh_sha256'];dump(ROOT/'verification.json',dict(at=now(),status='PASS_INDEPENDENT_SAVED_ARITHMETIC',metric_blocks=checked,result_definitions='A-F including requested E',surface='12cells,3sums,all,area conservation',target='exact evaluation centre join and result-within-tau sums',files={str(f):sha(f) for f in files+[p,root/'patch_z.npz']},scientific_verdict=None));print('ENDPOINT_VERIFY_PASS',checked)
if __name__=='__main__':main()
