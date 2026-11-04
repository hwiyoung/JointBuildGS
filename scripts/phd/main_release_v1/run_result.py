"""Per-arm jobs and tables, using the frozen RESCORE metrics and new cells."""
from common import *
import sys
sys.path.append('/repo/scripts/phd/main_rescore_v1')
from metrics import four,inherited_result_mask
from scipy.spatial import cKDTree
def main(action,site,prior,rule):
 cfg();name=f'rl_{rule}_{prior}_s0';key=f'{site}__{prior}__{name}';run=O/'runs'/site/name;rec=json.loads((run/'receipt.json').read_text());assert rec['status']=='COMPLETED_30000'
 if action=='prepare':
  v=score_root(site)/'views'/f'{site}.json'
  if not v.exists():v=BASE/'views'/f'{site}.json'
  out=O/'views'/v.name
  if not out.exists():out.write_bytes(v.read_bytes())
  views=json.loads(out.read_text());model=Path(rec['attempts'][-1]['model']);dump(O/'jobs'/f'{key}.json',dict(site=site,prior=prior,family='FINALTRAIN_30000',key=key,views=len(views['views']),box=views['box'],ply=str(model/'point_cloud/iteration_30000/point_cloud.ply'),scientific_verdict=None));return
 z=loadz(O/'scores'/key/'points.npz');v=json.loads((O/'scores'/key/'values.json').read_text());cell=loadz(O/'stage0'/f'{site}__{prior}'/'cells.npz');assert np.array_equal(z['row_owner'],cell['row_owner']);owner=cell['row_owner'];valid=owner>=0;ids=np.flatnonzero(valid);tree=cKDTree(np.c_[owner[valid].astype(float)*100000.,cell['xyz'][valid]])
 near=np.full(len(z['sample_owner']),-1,'i8');inside=z['sample_owner']>=0
 for start in range(0,len(near),200000):
  take=np.arange(start,min(start+200000,len(near)));take=take[inside[take]]
  if len(take):
   ix=ids[tree.query(np.c_[z['sample_owner'][take].astype(float)*100000.,z['sample_xyz'][take]],workers=2)[1]];ok=owner[ix]==z['sample_owner'][take];near[take[ok]]=ix[ok]
 qcell=np.full(len(near),-1,'i1');qcell[near>=0]=cell['score_cell_1p0'][near[near>=0]];rows=[]
 original=[dict(**r,cell_basis='original',method=rule) for r in v['cells'] if r['cell'] in [0,1,2,4]];rows.extend(original)
 for k in [0,1,2,4]:
  metrics=four(z['row_distance_m'],z['sample_region_distance_m'],z['row_tau_m'],z['sample_tau_m'],cell['score_cell_1p0']==k,(qcell==k)&inherited_result_mask(z['sample_region_distance_m'],z['sample_region_lat_m']));rows.append(dict(cell=k,cell_basis='score',method=rule,**metrics))
 with (D/'tables/stage0'/f'{site}__{prior}_table4.csv').open() as f:
  old=[r for r in csv.DictReader(f) if float(r['tau_multiplier'])==1 and int(r['cell']) in [0,1,2,4]]
 for mode in ['original','score']:
  for k in [0,1,2,4]:
   subset=[r for r in old if r['cell_basis']==mode and int(r['cell'])==k];comparisons=[r for r in subset if r['method'] not in ['FINALTRAIN_30000','judgment_mesh'] and r['completeness']];best=max(comparisons,key=lambda r:float(r['completeness'])) if comparisons else None
   for r in subset:
    if r['method'] in ['FINALTRAIN_30000','judgment_mesh'] or r is best:
     rows.append(dict(cell=k,cell_basis=mode,method=r['method'],n_gt=int(r['n_gt']),n_result=int(r['n_result']),**{k:float(r[k]) if r[k] else None for k in ['completeness','accuracy','gt_mean_m','result_mean_m']}))
 for r in rows:r['small']='적음' if r['n_gt']<1000 else ''
 table('runs/'+key+'/table4',rows)
 scene=[dict(method=rule,**v['scene'])]
 for method in ['FINALTRAIN_30000','judgment_mesh']:
  oldv=json.loads((score_dir(site,prior,method)/'values.json').read_text());scene.append(dict(method=method,**oldv['scene']))
 table('runs/'+key+'/table3',scene)
 health=[]
 for it in [7000,15000,30000]:
  p=Path(rec['attempts'][-1]['model'])/f'target_monitor/health_{it}.json'
  if p.exists():health.append(json.loads(p.read_text()))
 table('runs/'+key+'/health',health)
 changes=[]
 for r in original:
  oldr=next(x for x in rows if x['method']=='FINALTRAIN_30000' and x['cell_basis']=='original' and x['cell']==r['cell']);changes.append(dict(cell=r['cell'],n_gt=r['n_gt'],completeness_delta_pp=100*(r['completeness']-oldr['completeness']) if r['completeness'] is not None else None))
 dump(D/'runs'/f'{key}.json',dict(at=now(),site=site,prior=prior,rule=rule,status='PASS_SCORE',changes=changes,scene=v['scene'],V0_scene=scene[1],seconds=rec['attempts'][-1]['seconds'],gaussians=health[-1]['gaussians'] if health else None,scores_sha256=sha(O/'scores'/key/'values.json'),scientific_verdict=None))
if __name__=='__main__':main(*sys.argv[1:])
