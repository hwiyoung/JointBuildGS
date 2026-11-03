"""B173-only scene scores; unavailable JA regions remain unavailable."""
import sys,gc
from common import *
from geometry import SiteGT,Ref,result_sample,MeshScene
from score_mesh import normal_wall_distance
from metrics import four,inherited_result_mask
from surface_tau import RULE
def main(prior,key,mesh):
 import open3d as o3d
 cfg();start=time.monotonic();site='B173_b0';gt=SiteGT(site);normalfile=O/'reference'/f'normals_{site}.npz';z=loadz(normalfile);N=np.full_like(gt.X[0],np.nan);N[z['use_0']]=z['normal_0'];N=N[gt.bs_idx];ref=Ref(gt.Gb,N);wall=gt.G['vert_gt_points'][gt.bs_idx].astype(bool);mesh=Path(mesh)
 if mesh.suffix=='.npz':a=loadz(mesh,['V','F']);V,F=a['V'],a['F'];m=None
 else:m=o3d.io.read_triangle_mesh(str(mesh));V,F=np.asarray(m.vertices),np.asarray(m.triangles)
 sample=result_sample(V,F,gt);scene=MeshScene(V,F);del m,V,F;gc.collect();gd=normal_wall_distance(scene,gt.Gb,N,wall);del scene;gc.collect();_,nd,lat,near=ref.query(sample);taurows=json.loads((D/'tables/table1_tau.json').read_text())['rows'];rr=[r for r in taurows if r['search_region']=='R2' and r['prior']==prior];lookup={str(r['kind']):r['new_tau_m'] for r in rr}
 if prior=='ALS':roof=walltau=rr[0]['new_tau_m']
 else:
  roof=next(r['new_tau_m'] for r in rr if str(r['kind']) in ['roof','지붕','1']);walltau=next(r['new_tau_m'] for r in rr if str(r['kind']) in ['wall','벽','2'])
 gt_tau=np.where(wall,walltau,roof);qtau=np.where(wall[near],walltau,roof);good=inherited_result_mask(nd,lat);metrics=four(gd,nd,gt_tau,qtau,result_mask=good);root=O/'scores'/key;savez(root/'points.npz',sample_xyz=sample,sample_distance_m=nd,sample_lat_m=lat,sample_tau_m=qtau,scene_distance_m=gd,scene_tau_m=gt_tau)
 dump(root/'values.json',dict(site=site,prior=prior,key=key,status='PASS_SCENE_ONLY',mesh=str(mesh),mesh_sha256=sha(mesh),scene=metrics,cells=[],diagnostic=dict(n_result=len(sample),outside_column_fraction=None,multiple_column_fraction=None,roof_column_nearest_wall_fraction=None,reference_unavailable_fraction=float((~good).mean())),regional_status='확인 불가: JUDGEAPPLY 핵심점 파일 없음',provenance=dict(tau_assignment=RULE,tau_source=str(D/'tables/table1_tau.json'),reference_normals=str(normalfile),reference_normals_sha256=sha(normalfile),sampling_density_m2=400,sampling_seed=0,config_sha256=sha(C/'rescore_v1.json'),scorer_sha256=sha(__file__),optimization_steps=0,crs='EPSG:25832'),source_tag='[이 발주에서 냄]',scientific_verdict=None));timing('score_'+key,start)
if __name__=='__main__':main(*sys.argv[1:])
