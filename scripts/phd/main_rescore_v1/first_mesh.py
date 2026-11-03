"""Production r8 ALS final mesh; reuse immutable renders and exact tiled TSDF."""
import sys,ast,copy,resource
from common import *
sys.path.insert(0,'/repo')
from src.phd import streamed_tsdf as T
KEY='B173nb_b10__ALS__r8_30000'
WD=O/'meshes'/KEY/'final_work'
RR=TG/'r8/meshes/r8_ALS_30000/render'
def prepare():
 start=time.monotonic();cfg();r=json.loads((RR/'receipt.json').read_text());assert r['status']=='PASS'
 model=TG/'r8/runs/tg_B173nb_b10_ALS_s0_r8/model/point_cloud/iteration_30000/point_cloud.ply';assert sha(model)==r['model_sha256']
 src=R/'scripts/phd/main_target_v1/render_final_r8.py';assert sha(src)==r['source_sha256']
 views=r['views'];dest=WD/'inputs';dest.mkdir(parents=True,exist_ok=True);H,W=views[0]['height'],views[0]['width']
 depth=np.lib.format.open_memmap(dest/'depth_masked.npy','w+',dtype='f4',shape=(len(views),H,W));rgb=np.lib.format.open_memmap(dest/'rgb.npy','w+',dtype='u1',shape=(len(views),H,W,3));intr=[];extr=[]
 for i,v in enumerate(views):
  p=RR/v['file'];assert sha(p)==v['sha256'];z=loadz(p);depth[i]=z['depth'];rgb[i]=z['rgb'];k=np.array(v['K']);intr.append([k[0,0],k[1,1],k[0,2],k[1,2]]);extr.append(v['W2C'])
 depth.flush();rgb.flush();np.savez(dest/'cams.npz',names=[v['name'] for v in views],intr=intr,wh=[[W,H]]*len(views),extrinsic=extr)
 dump(dest/'meta.json',dict(site='B173nb_b10',result=KEY,prior_scene='ALS',depth_dir=str(RR),box=r['box'],height=H,width=W,views=len(views),views_without_depth=[],seconds=time.monotonic()-start,scientific_verdict=None))
 dump(O/'views/B173nb_b10.json',dict(views=[{k:v[k] for k in ['index','name','virtual','K','W2C','width','height']} for v in views],source=str(RR/'receipt.json'),sha256=sha(RR/'receipt.json'),scientific_verdict=None))
 dump(WD/'binding.json',dict(at=now(),model_sha256=sha(model),render_receipt_sha256=sha(RR/'receipt.json'),render_source_sha256=sha(src),config_sha256=sha(C/'rescore_v1.json'),reused_render_seconds=r['seconds'],new_gpu_seconds=0,optimization_steps=0,scientific_verdict=None))
 timing('first_mesh_prepare',start);print('FIRST_MESH_PREPARED',len(views))
def finish():
 import open3d as o3d
 start=time.monotonic();mesh=o3d.io.read_triangle_mesh(str(WD/'merged.ply'));raw=len(mesh.triangles)
 source=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/received/geogs_original/utils/mesh_utils.py'
 fn=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='post_process_mesh');ns=dict(np=np,o3d=o3d,copy=copy);exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns);mesh=ns['post_process_mesh'](mesh,cluster_to_keep=50);clean=len(mesh.triangles)
 pcfg=json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text());a=np.deg2rad(pcfg['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]]);tr=loadz(S1/'defs/B173nb_b10/top_raster.npz',['eval_u','eval_v']);uv=np.asarray(mesh.vertices)[:,:2]@basis.T;inside=(uv[:,0]>=tr['eval_u'][0])&(uv[:,0]<=tr['eval_u'][1])&(uv[:,1]>=tr['eval_v'][0])&(uv[:,1]<=tr['eval_v'][1]);mesh.remove_triangles_by_mask(~inside[np.asarray(mesh.triangles)].all(1));mesh.remove_unreferenced_vertices();p=WD.parent/'final.ply';assert o3d.io.write_triangle_mesh(str(p),mesh)
 dump(WD.parent/'final.json',dict(at=now(),status='PASS',raw_triangles=raw,cleanup_triangles=clean,final_triangles=len(mesh.triangles),mesh_sha256=sha(p),cleanup_source=str(source),cleanup_sha256=sha(source),voxel_m=.05,trunc_m=.25,cluster_to_keep=50,training=False,seconds=time.monotonic()-start,peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,scientific_verdict=None));print('FIRST_FINAL_MESH_COMPLETE',len(mesh.triangles));timing('first_mesh_finish',start)
def main():
 cfg();mode=sys.argv[1];start=time.monotonic()
 if mode=='prepare':prepare()
 elif mode=='plan':T.plan(WD,'auto:18');T.order(WD);timing('first_mesh_plan',start)
 elif mode=='tile':k=int(sys.argv[2]);T.tile(WD,k);timing(f'first_mesh_tile{k}',start)
 elif mode=='merge':T.merge(WD,WD/'merged.ply',WD/'merged.json');timing('first_mesh_merge',start)
 elif mode=='finish':finish()
 elif mode=='recover_receipt':
  import open3d as o3d
  p=WD/'merged.ply';m=o3d.io.read_triangle_mesh(str(p));tiles=[json.loads(x.read_text()) for x in sorted((WD/'tiles').glob('tile*.json'))];expected=sum(x['kept']['triangles'] for x in tiles);assert len(m.triangles)==expected
  logs=sorted((O/'logs').glob('firstmerge_*.log'));elapsed=p.stat().st_mtime-logs[0].stat().st_ctime
  dump(WD/'merged.json',dict(status='PASS_MESH_RECOVERED_RECEIPT',mesh_sha256=sha(p),triangles=len(m.triangles),vertices=len(m.vertices),expected_triangles_from_tiles=expected,original_failure='after write_triangle_mesh: missing informational mean_share_of_pixels_in_box in metadata',unavailable=['original merge peak memory and vertex identity diagnostic'],scientific_verdict=None))
  dump(O/'timing/first_mesh_merge.json',dict(stage='first_mesh_merge',seconds=max(0,elapsed),measurement='PLY mtime minus original merge log creation timestamp; wrapper failed after saving mesh',scientific_verdict=None));print('MERGE_RECOVERED',expected)
 else:raise ValueError(mode)
if __name__=='__main__':main()
