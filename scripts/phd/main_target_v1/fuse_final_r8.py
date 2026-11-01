"""Original bounded TSDF and original cleanup(50), then fixed evaluation crop."""
import sys,ast,copy,time
import numpy as np,open3d as o3d
from common import *
def main():
 key=sys.argv[1];p=CFG/'scoring_r8.json';assert sha(p)==json.loads((CFG/'scoring_r8.lock.json').read_text())['config_sha256'];cfg=json.loads(p.read_text());row=next(r for r in cfg['rows'] if r['key']==key);root=OUT/'r8/meshes'/key;root.mkdir(parents=True,exist_ok=True);assert not (root/'receipt.json').exists();start=time.monotonic()
 if row['existing_virtual']:
  source=Path(row['existing_virtual']);assert sha(source)==row['existing_inputs'][str(source)];mesh=o3d.io.read_triangle_mesh(str(source));binding=dict(existing_virtual=str(source),sha256=sha(source))
 else:
  rr=root/'render';r=json.loads((rr/'receipt.json').read_text());assert r['status']=='PASS';volume=o3d.pipelines.integration.ScalableTSDFVolume(voxel_length=.1,sdf_trunc=.5,color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
  for i,v in enumerate(r['views']):
   path=rr/v['file'];assert sha(path)==v['sha256'];z=np.load(path);rgbd=o3d.geometry.RGBDImage.create_from_color_and_depth(o3d.geometry.Image(np.ascontiguousarray(z['rgb'])),o3d.geometry.Image(np.ascontiguousarray(z['depth'])),depth_scale=1.,depth_trunc=300.,convert_rgb_to_intensity=False);k=np.asarray(v['K']);intr=o3d.camera.PinholeCameraIntrinsic(v['width'],v['height'],k[0,0],k[1,1],k[0,2],k[1,2]);volume.integrate(rgbd,intr,np.asarray(v['W2C']))
   if i%40==0:print('FINAL_TSDF',key,i+1,len(r['views']),flush=True)
  mesh=volume.extract_triangle_mesh();del volume;assert o3d.io.write_triangle_mesh(str(root/'virtual_raw.ply'),mesh);binding=dict(render_receipt_sha256=sha(rr/'receipt.json'))
 raw_tri=len(mesh.triangles);source=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/received/geogs_original/utils/mesh_utils.py';assert sha(source)==cfg['source_files'][str(source).replace('/art/phase-payloads/phd','/ph')];tree=ast.parse(source.read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='post_process_mesh');ns=dict(np=np,o3d=o3d,copy=copy);exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns);mesh=ns['post_process_mesh'](mesh,cluster_to_keep=50);clean_tri=len(mesh.triangles)
 pcfg=json.loads((REPO/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text());a=np.deg2rad(pcfg['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]]);tr=np.load(S1/'defs'/row['site']/'top_raster.npz');uv=np.asarray(mesh.vertices)[:,:2]@basis.T;inside=(uv[:,0]>=tr['eval_u'][0])&(uv[:,0]<=tr['eval_u'][1])&(uv[:,1]>=tr['eval_v'][0])&(uv[:,1]<=tr['eval_v'][1]);remove=~inside[np.asarray(mesh.triangles)].all(1);mesh.remove_triangles_by_mask(remove);mesh.remove_unreferenced_vertices();assert len(mesh.triangles)>0;path=root/'final.ply';assert o3d.io.write_triangle_mesh(str(path),mesh)
 dump(root/'receipt.json',dict(status='PASS',at=stamp(),row=row,binding=binding,raw_triangles=raw_tri,cleanup_triangles=clean_tri,final_triangles=len(mesh.triangles),final_vertices=len(mesh.vertices),mesh_sha256=sha(path),eval_range=dict(u=tr['eval_u'].tolist(),v=tr['eval_v'].tolist()),config_sha256=sha(p),script_sha256=sha(__file__),seconds=time.monotonic()-start,scientific_verdict=None));print('FINAL_COMPLETE',key,flush=True)
if __name__=='__main__':main()
