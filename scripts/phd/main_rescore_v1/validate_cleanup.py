"""Single parity check against the inherited cleanup on disconnected/tied components."""
from common import *
from bounded_cleanup import cleanup
import open3d as o3d,ast,copy

def main():
 start=time.monotonic();V=[];F=[]
 # 60 separated strips; triangle count varies, including a cutoff tie.
 for k in range(60):
  base=len(V);n=25+k%7
  for i in range(n+1):V.extend([[130+k*.4,114+i*.005,-10.],[130+k*.4+.15,114+i*.005,-10.]])
  for i in range(n):a=base+2*i;F.extend([[a,a+1,a+2],[a+1,a+3,a+2]])
 m=o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector(np.array(V)),o3d.utility.Vector3iVector(np.array(F)));m.vertex_colors=o3d.utility.Vector3dVector(np.ones((len(V),3))*.5);root=O/'validation/cleanup';root.mkdir(parents=True,exist_ok=True);raw=root/'raw.ply';o3d.io.write_triangle_mesh(str(raw),m)
 source=PH/'main_meshpatch_v1/PHD-MAIN-MESHPATCH-v1/received/geogs_original/utils/mesh_utils.py';fn=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='post_process_mesh');ns=dict(np=np,o3d=o3d,copy=copy);exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns);expected=ns['post_process_mesh'](m,cluster_to_keep=50)
 config=json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text());a=np.deg2rad(config['frame']['u_axis_angle_degrees_ccw_from_easting']);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]]);tr=loadz(S1/'defs/B173nb_b10/top_raster.npz',['eval_u','eval_v']);uv=np.asarray(expected.vertices)[:,:2]@basis.T;inside=(uv[:,0]>=tr['eval_u'][0])&(uv[:,0]<=tr['eval_u'][1])&(uv[:,1]>=tr['eval_v'][0])&(uv[:,1]<=tr['eval_v'][1]);expected.remove_triangles_by_mask(~inside[np.asarray(expected.triangles)].all(1));expected.remove_unreferenced_vertices()
 out=root/'final.ply';cleanup('B173nb_b10',raw,out);actual=o3d.io.read_triangle_mesh(str(out));assert np.array_equal(np.asarray(actual.vertices),np.asarray(expected.vertices));assert np.array_equal(np.asarray(actual.triangles),np.asarray(expected.triangles));assert len(actual.triangles)>0
 dump(root/'validation.json',dict(status='PASS_EXACT_VERTICES_AND_TRIANGLES',triangles=len(actual.triangles),source_sha256=sha(source),scientific_verdict=None));timing('cleanup_validation',start)
if __name__=='__main__':main()
