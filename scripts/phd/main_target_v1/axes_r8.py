"""AXES71-v2 functions on each requested mesh, without mixed-mesh cell substitution."""
import sys,json,time,gc,hashlib
from pathlib import Path
import numpy as np
sys.path.insert(0,'/repo/scripts/phd/main_meshpatch_v1')
from axes_adapter import ax,aa,a3,a4,inputs,distances
from mesh_common import dump,sha,now
import mesh_worker as MW,mesh_common as MC
O=Path('/target');C=Path('/cfg');D=Path('/docs')
def main():
 key,kind=sys.argv[1:3];p=C/'scoring_r8.json';assert sha(p)==json.loads((C/'scoring_r8.lock.json').read_text())['config_sha256'];cfg=json.loads(p.read_text());row=next(r for r in cfg['rows'] if r['key']==key)
 for path,h in cfg['source_files'].items():assert sha(path)==h,path
 root=O/'r8/scoring'/key/kind;root.mkdir(parents=True,exist_ok=True);result=root/'values.json'
 if result.exists():assert json.loads(result.read_text())['status']=='PASS';return
 mesh=Path(row['current_mesh']) if kind=='current' else O/'r8/meshes'/key/'final.ply'
 if str(mesh) in row['existing_inputs']:assert sha(mesh)==row['existing_inputs'][str(mesh)]
 mh=sha(mesh);dump(root/'binding.json',dict(at=now(),mesh=str(mesh),mesh_sha256=mh,config_sha256=sha(p),script_sha256=sha(__file__),scientific_verdict=None));start=time.monotonic();site,prior=row['site'],row['prior'];print('AXES_INPUTS',key,kind,flush=True);ctx=inputs(site,prior)
 prefix=root/'dist'/f'{site}_{prior}__{key}';paths=(prefix.with_suffix('.npz'),prefix.with_name(prefix.name+'__x.npz'),None)
 if not all(p.exists() for p in paths[:2]):print('AXES_DISTANCES',key,kind,flush=True);paths=distances(site,prior,key,mesh,root/'dist',ctx)
 print('AXES_AGGREGATE',key,kind,flush=True);A=aa.arrays(site,prior,key,ctx['cells'],paths=paths);blocks={}
 for cell in ['all']+ax.KEYS:
  g=A['scene'] if cell=='all' else aa.sel(A['rows'],aa.cell_sel(A['rows']['cell'],cell,ax.SUMS));s=A['smp'] if cell=='all' else aa.sel(A['smp'],aa.cell_sel(A['smp']['cell'],cell,ax.SUMS));gb=aa.gt_block(g,with05=cell=='all');rb=aa.res_block(s,place=cell!='all',with05=cell=='all');blocks[cell]=dict(status='있음' if gb['n_gt'] else '참값 없음',mesh_kind=kind,gt=gb,res=rb,both=aa.combine(gb,rb))
 bins=a4.bins_of(site,prior,ctx['cells']);axes={line:{str(i):a4.value([A],line,i,[bins]) for i in list(range(len(a4.labels(axis))))+([99] if line=='axis2_mask' else [])} for line,axis in a4.LINES}
 CL=dict(np.load(ax.WORK/f'clumps_{site}_{prior}.npz'));clumps={};K=ax.CFG['clumps'];g=A['rows'];pa=g['patch'];cl=CL['clump'][pa];ca=CL['clump_area'][pa]
 for cell in ax.CELLS:
  m=g['cell']==ax.CID[cell];ids,inv=np.unique(cl[m],return_inverse=True);n=np.bincount(inv);hit=np.bincount(inv,weights=(g['d'][m]<=g['tau'][m]).astype(float))/np.maximum(n,1);means=np.bincount(inv,weights=g['d'][m])/np.maximum(n,1)*100;area=np.zeros(len(ids));area[inv]=ca[m];keep=area>=1
  clumps[cell]=dict(clump=ids[keep],area=area[keep],rows=n[keep],R_tau=hit[keep],mean_cm=means[keep],hits={f'ge_{th:g}':dict(clumps=int((area>=th).sum()),hit=int(((area>=th)&(hit>K['hit_share'])).sum()),rate=float((hit[area>=th]>K['hit_share']).mean()) if (area>=th).any() else None) for th in [K['object_min_m2'],K['object_big_m2']]},size_bins={})
  edges=[float('inf') if v=='inf' else float(v) for v in K['size_bins_m2']]
  for i in range(len(edges)-1):
   sel=m&(ca>=edges[i])&(ca<edges[i+1]);clumps[cell]['size_bins'][str(i)]=aa.gt_block(aa.sel(g,sel))
 # Same first-hit arithmetic; divide only by the frozen twelve GT cells here.
 del A;gc.collect();import open3d as o3d
 e=ctx['ev'];v=dict(np.load(ax.PH/'main_losstrain_v1/PHD-MAIN-LOSSTRAIN-v1/direct_stage1_v2'/f'{site}__{prior}/values.npz'));print('AXES_FIRST_HIT',key,kind,flush=True);m=o3d.io.read_triangle_mesh(str(mesh));z=MW.first_hit(m,e,v);cat=MC.classes(e,z);del m;gc.collect();np.savez_compressed(root/'patch_z.npz',**z,category=cat,gt_cell=ctx['cells']['cell']);cellareas={}
 for cell in ['all']+ax.CELLS:
  scope=np.ones(len(e['area']),bool) if cell=='all' else ctx['cells']['cell']==ax.CID[cell];sel=scope&e['in_eval']&e['scoring_allowed'];area=float(e['area'][sel].sum());cellareas[cell]=dict(patches=int(sel.sum()),area_m2=area,unscorable_area_m2=float(e['area'][scope&e['in_eval']&~e['scoring_allowed']].sum()),floating_area_m2=float(e['area'][sel&(cat==1)].sum()),no_surface_area_m2=float(e['area'][sel&z['no_surface']].sum()),floating_fraction=float(e['area'][sel&(cat==1)].sum()/area) if area else None,no_surface_fraction=float(e['area'][sel&z['no_surface']].sum()/area) if area else None)
 resultdata=dict(status='PASS',at=now(),key=key,row=row,mesh_kind=kind,mesh_sha256=mh,metrics=blocks,axes=axes,clumps=clumps,surface=cellareas,metric_rule=cfg['axes'],seconds=time.monotonic()-start,scientific_verdict=None);dump(result,resultdata);dump(D/'tables/r8'/f'{key}_{kind}.json',resultdata);print('AXES_COMPLETE',key,kind,resultdata['seconds'],flush=True)
if __name__=='__main__':main()
