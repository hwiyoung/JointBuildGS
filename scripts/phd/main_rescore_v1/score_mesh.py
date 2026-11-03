"""Frozen RESCORE mesh scorer. No training or GT-dependent geometry construction."""
import sys,gc,argparse
from scipy.spatial import cKDTree
from common import *
from geometry import context,columns,result_sample,MeshScene,closest
from metrics import four,inherited_result_mask

def normal_wall_distance(scene,points,normals,wall):
 q,dist=closest(scene,points)
 good=wall&np.isfinite(normals).all(1)
 dist[good]=abs(np.einsum('ij,ij->i',q[good]-points[good],normals[good]))
 return dist

def subset_metrics(ctx,rd,nd,rowtau,qtau,owner,good):
 core=ctx['core'];cell=ctx['v2']['cell_v2'];rowowner=ctx['row_owner'];rowok=rowowner>=0;inside=owner>=0;blocks=[]
 def masks(patch):
  gm=np.zeros(len(rd),bool);gm[rowok]=patch[rowowner[rowok]]
  qm=np.zeros(len(nd),bool);qm[inside]=patch[owner[inside]];qm&=good
  return gm,qm
 for j in [0,1,2,4,3]:
  gm,qm=masks(cell==j);blocks.append(dict(cell=j,patches=int((cell==j).sum()),area_m2=float(core['area'][cell==j].sum()),**four(rd,nd,rowtau,qtau,gm,qm)))
 band=np.zeros(len(cell),bool)
 if (cell==3).any():band=np.isin(cell,[0,1,2,4])&(cKDTree(core['centre'][cell==3]).query(core['centre'],workers=4)[0]<=2.)
 gm,qm=masks(band);v=four(rd,nd,rowtau,qtau,gm,qm);bandrow=dict(area_m2=float(core['area'][band].sum()),patches=int(band.sum()),n_gt=v['n_gt'],completeness=v['completeness'])
 offsets=[]
 for j,k in [(1,'prior_height_m'),(2,'mvs_mean_m')]:
  delta=abs(core[k]-core['gt_p'])
  for lo,hi in zip([0.,.5,1.,2.,4.],[.5,1.,2.,4.,np.inf]):
   take=(cell==j)&(delta>=lo)&(delta<hi);gm,qm=masks(take);v=four(rd,nd,rowtau,qtau,gm,qm)
   offsets.append(dict(cell=j,lower_m=lo,upper_m=None if np.isinf(hi) else hi,n_gt=v['n_gt'],completeness=v['completeness'],patches=int(take.sum())))
 return blocks,bandrow,offsets

def score(site,prior,key,mesh,legacy=False):
 import open3d as o3d
 start=time.monotonic();cfg();assert '/' not in key and key not in ['.','..'];root=O/'scores'/key;root.mkdir(parents=True,exist_ok=True);ctx=context(site,prior);gt=ctx['gt'];core=ctx['core'];v2=ctx['v2'];tau=v2['tau_v2_m'];cell=v2['cell_v2']
 m=o3d.io.read_triangle_mesh(str(mesh));V=np.asarray(m.vertices);F=np.asarray(m.triangles);assert len(F)>0,'EMPTY_MESH';sample=result_sample(V,F,gt);scene=MeshScene(V,F);ntri=len(F);del m,V,F;gc.collect();print('SAMPLE',key,len(sample),ntri,flush=True)
 if legacy:gd=scene.distance(gt.Gb).astype(float);rd=scene.distance(ctx['row_points']).astype(float)
 else:
  gd=normal_wall_distance(scene,gt.Gb,ctx['normals'][0][gt.bs_idx],gt.G['vert_gt_points'][gt.bs_idx].astype(bool))
  rd=normal_wall_distance(scene,ctx['row_points'],ctx['row_normals'],ctx['row_kind']==2)
 del scene;gc.collect();print('GT_DISTANCE',key,flush=True)
 _,nd,lat,near=ctx['ref'].query(sample);refgood=inherited_result_mask(nd,lat)
 if ctx['region_ref'] is ctx['ref']:region_nd,region_lat=nd,lat
 else:_,region_nd,region_lat,_=ctx['region_ref'].query(sample)
 region_good=inherited_result_mask(region_nd,region_lat)
 tree=cKDTree(core['centre']);near_q=tree.query(sample,workers=4)[1]
 if legacy:owner=near_q.astype('i4');hits=np.ones(len(sample),'i4')
 else:owner,hits=columns(sample,core,root/'columns')
 inside=owner>=0;gtowner=ctx['scene_owner'];gtin=gtowner>=0;gt_tau=tau[tree.query(gt.Gb,workers=4)[1]].copy();gt_tau[gtin]=tau[gtowner[gtin]]
 qtau=tau[near_q].copy();qtau[inside]=tau[owner[inside]]
 row_owner=ctx['row_owner'];rowok=row_owner>=0;rowtau=np.full(len(rd),np.nan);rowtau[rowok]=tau[row_owner[rowok]]
 if legacy:gt_tau[:]=.147;qtau[:]=.147;rowtau[:]=.147
 vals=four(gd,nd,gt_tau,qtau,result_mask=refgood)
 blocks,band,offsets=subset_metrics(ctx,rd,region_nd,rowtau,qtau,owner,region_good)
 roof=inside.copy();roof[inside]&=core['kind'][owner[inside]]==1;nearest_wall=gt.G['vert_gt_points'][gt.bs_idx][near].astype(bool)
 diagnostic=dict(n_result=len(sample),outside_column_fraction=float((~inside).mean()),multiple_column_fraction=float((hits>1).mean()),roof_column_points=int(roof.sum()),roof_column_nearest_wall_fraction=float(nearest_wall[roof].mean()) if roof.any() else None,reference_unavailable_fraction=float((~refgood).mean()),region_reference_unavailable_fraction=float((~region_good).mean()),undefined_cell_result_points=int((inside&np.isin(np.where(inside,cell[np.maximum(owner,0)],9),[9])).sum()))
 savez(root/'points.npz',sample_xyz=sample.astype('f4'),sample_distance_m=nd.astype('f4'),sample_lat_m=lat.astype('f4'),sample_region_distance_m=region_nd.astype('f4'),sample_region_lat_m=region_lat.astype('f4'),sample_tau_m=qtau,sample_owner=owner,sample_hits=hits,scene_distance_m=gd.astype('f4'),scene_tau_m=gt_tau,scene_owner=gtowner,row_distance_m=rd.astype('f4'),row_tau_m=rowtau,row_owner=row_owner)
 result=dict(site=site,prior=prior,key=key,mesh=str(mesh),mesh_sha256=sha(mesh),scene=vals,cells=blocks,band=band,offsets=offsets,diagnostic=diagnostic,legacy=legacy,rule='legacy_AXES_E' if legacy else 'RESCORE_v1_columns',source_tag='[이 발주에서 냄]',provenance=dict(config_sha256=sha(C/'rescore_v1.json'),cells_sha256=sha(CELLS/f'{site}__{prior}.npz'),scorer_sha256=sha(__file__),geometry_sha256=sha(Path(__file__).with_name('geometry.py')),commit=os.environ.get('RESCORE_COMMIT'),image=os.environ.get('RESCORE_IMAGE'),sampling_density_m2=400,sampling_seed=0,crs='EPSG:25832',optimization_steps=0),scientific_verdict=None)
 dump(root/'values.json',result);timing('score_'+key,start);print('SCORE_COMPLETE',key,vals,flush=True)
 return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('site');p.add_argument('prior',choices=['ALS','LoD2']);p.add_argument('key');p.add_argument('mesh',type=Path);p.add_argument('--legacy',action='store_true');a=p.parse_args();score(a.site,a.prior,a.key,a.mesh,a.legacy)
