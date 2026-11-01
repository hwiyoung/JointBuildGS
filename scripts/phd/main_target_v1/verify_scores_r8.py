"""Independent arithmetic over saved distances, fixed cells, clumps and surface arrays."""
import sys,json
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from axes_adapter import ax,aa,a4
from mesh_common import dump,sha,now
O=Path('/target');D=Path('/docs')
def equal(a,b,label):
 if a is None or b is None:assert a is None and b is None,(label,a,b)
 else:assert np.isclose(a,b,rtol=1e-10,atol=1e-9),(label,a,b)
def gverify(g,b):
 d,t=g['d'],g['tau'];assert len(d)==b['n_gt']
 equal(float(np.count_nonzero(d<=t)/len(d)) if len(d) else None,b.get('R_tau'),'R')
 equal(float(np.sum(d)/len(d)*100) if len(d) else None,b.get('mean'),'gt mean')
def sverify(s,b):
 n=len(s['tau']);assert n==b['n_res_all']
 for count in 'ABCDEF':
  if count in 'ABCD':
   d=s['dA'];ok={'A':np.ones(n,bool),'B':s['has_gt'],'C':s['spacing']<=s['tau'],'D':s['spacing']<=.5*s['tau']}[count]
  else:d=s['nE'];ok=np.isfinite(d)&np.isfinite(s['lE'])&(s['lE']<=(.5 if count=='E' else 1))
  nn=int(np.count_nonzero(ok));r=b[count];assert nn==r['n'] and n-nn==r['excluded']
  equal(float(np.count_nonzero(d[ok]<=s['tau'][ok])/nn) if nn else None,r.get('P_tau'),'P '+count)
  equal(float(np.sum(d[ok])/nn*100) if nn else None,r.get('mean'),'result mean '+count)
def main():
 key,kind=sys.argv[1:3];root=O/'r8/scoring'/key/kind;p=root/'values.json';r=json.loads(p.read_text());assert r['status']=='PASS' and r['scientific_verdict'] is None;row=r['row'];site,prior=row['site'],row['prior'];C=aa.cells(site,prior);prefix=root/'dist'/f'{site}_{prior}__{key}';files=[prefix.with_suffix('.npz'),prefix.with_name(prefix.name+'__x.npz')];A=aa.arrays(site,prior,key,C,paths=(*files,None));checked=0
 for cell,b in r['metrics'].items():
  g=A['scene'] if cell=='all' else aa.sel(A['rows'],aa.cell_sel(A['rows']['cell'],cell,ax.SUMS));s=A['smp'] if cell=='all' else aa.sel(A['smp'],aa.cell_sel(A['smp']['cell'],cell,ax.SUMS));gverify(g,b['gt']);sverify(s,b['res']);checked+=1
 # Axes use frozen bucket memberships, independent counts and sums.
 bins=a4.bins_of(site,prior,C)
 for line,blocks in r['axes'].items():
  for bi,b in blocks.items():
   g=aa.sel(A['rows'],bins[line][A['rows']['patch']]==int(bi));s=aa.sel(A['smp'],bins[line][A['smp']['patch']]==int(bi));d=s['nE'];ok=np.isfinite(d)&np.isfinite(s['lE'])&(s['lE']<=.5);nn=int(ok.sum());assert len(g['d'])==b['n_gt'] and nn==b['n_res'];gverify(g,dict(n_gt=b['n_gt'],R_tau=b['R_tau'],mean=b['mean']));equal(float((d[ok]<=s['tau'][ok]).mean()) if nn else None,b['P_tau'],'axis P');equal(float(d[ok].mean()*100) if nn else None,b['res_mean'],'axis mean')
 CL=np.load(ax.WORK/f'clumps_{site}_{prior}.npz');g=A['rows'];pa=g['patch'];cc=CL['clump'][pa];area=CL['clump_area'][pa]
 for cell,b in r['clumps'].items():
  m=g['cell']==ax.CID[cell];ids,ix=np.unique(cc[m],return_inverse=True);n=np.bincount(ix);hits=np.bincount(ix,weights=(g['d'][m]<=g['tau'][m]))/np.maximum(n,1);ar=np.zeros(len(ids));ar[ix]=area[m]
  for th in [2.5,10]:
   mask=ar>=th;q=b['hits'][f'ge_{th:g}'];assert q['clumps']==int(mask.sum()) and q['hit']==int((mask&(hits>.5)).sum());equal(float((hits[mask]>.5).mean()) if mask.any() else None,q['rate'],'clump')
 e=np.load(ax.PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{site}__{prior}/evaluation.npz');z=np.load(root/'patch_z.npz');assert np.array_equal(z['gt_cell'],C['cell']);allowed=e['in_eval']&e['scoring_allowed']
 for cell,b in r['surface'].items():
  m=allowed if cell=='all' else allowed&(C['cell']==ax.CID[cell]);a=float(e['area'][m].sum());f=float(e['area'][m&(z['category']==1)].sum());v=float(e['area'][m&z['no_surface']].sum());assert b['patches']==int(m.sum());equal(a,b['area_m2'],'area');equal(f,b['floating_area_m2'],'float area');equal(v,b['no_surface_area_m2'],'missing area');equal(f/a if a else None,b['floating_fraction'],'float fraction');equal(v/a if a else None,b['no_surface_fraction'],'missing fraction')
 for field in ['area_m2','floating_area_m2','no_surface_area_m2']:equal(sum(r['surface'][c][field] for c in ax.CELLS),r['surface']['all'][field],'cell area conservation '+field)
 binding=json.loads((root/'binding.json').read_text());assert sha(binding['mesh'])==binding['mesh_sha256']==r['mesh_sha256']
 for typ in ['cells','axes','clumps']:
  fp=D/'figures'/f'r8_{key}_{kind}_{typ}.json';assert fp.exists() and fp.with_suffix('.png').exists();figure=json.loads(fp.read_text());assert figure['values']['source_sha256']==sha(p)
 result=dict(at=now(),status='PASS_INDEPENDENT_SAVED_ARITHMETIC',key=key,kind=kind,metric_blocks=checked,counts='GT and result A-F; empty denominators preserved',axes='All frozen bins; independent arithmetic',clumps='Frozen IDs and 50% strict hit share',surface='GT-cell joins, numerator/denominator and area conservation',files={str(x):sha(x) for x in files+[p,root/'patch_z.npz']},mesh_sha256=r['mesh_sha256'],scientific_verdict=None);dump(root/'verification.json',result);dump(D/'tables/r8'/f'{key}_{kind}_verification.json',result);print('SCORE_VERIFIED',key,kind,checked,flush=True)
if __name__=='__main__':main()
