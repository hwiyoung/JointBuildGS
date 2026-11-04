"""ALS wall variants: original MVS triangles steeper than 60 degrees; no reference reads.
Reuse the existing wall/roof orientation boundary abs(n_z)<0.5 in AXES a8_check,
and the inherited local coordinate frame. Do not transfer LoD2/GT wall labels.
"""
from common import *
from geometry import MeshScene
import open3d as o3d
SITE='B173nb_b10';BASE=Path('/out')
def main():
 cfg();start=time.monotonic();v=json.loads((BASE/'scores'/f'{SITE}__ALS__mvs/values.json').read_text());source=Path(v['mesh']);mesh=o3d.io.read_triangle_mesh(str(source));V=np.asarray(mesh.vertices);F=np.asarray(mesh.triangles);keep=np.zeros(len(F),bool)
 for i in range(0,len(F),500000):
  p=V[F[i:i+500000]];n=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);length=np.linalg.norm(n,axis=1);keep[i:i+len(n)]=(length>0)&(abs(n[:,2])<.5*length)
 before=len(F);mesh.remove_triangles_by_mask(~keep);mesh.remove_unreferenced_vertices();scene=MeshScene(np.asarray(mesh.vertices),np.asarray(mesh.triangles));wall=O/'walls/mvs_wall.ply';wall.parent.mkdir(exist_ok=True);assert o3d.io.write_triangle_mesh(str(wall),mesh);count=len(mesh.triangles)
 view_record=json.loads((BASE/'views'/f'{SITE}.json').read_text());views=[x for x in view_record['views'] if not x['virtual']];assert len(views)==203
 original=json.loads((BASE/'renders'/f'{SITE}__ALS__fusion/receipt.json').read_text());box=np.array(original['box']);families=['fusion','judgment_mesh','oracle'];rows={x:[] for x in families}
 for v in views:
  K=np.array(v['K']);W,H=v['width'],v['height'];inv=np.linalg.inv(v['W2C']);depth=np.zeros((H,W),'f4')
  for y in range(0,H,128):
   yy,xx=np.meshgrid(np.arange(y,min(y+128,H)),np.arange(W),indexing='ij');dr=np.stack([(xx-K[0,2])/K[0,0],(yy-K[1,2])/K[1,1],np.ones_like(xx)],-1).reshape(-1,3)@inv[:3,:3].T;origin=np.broadcast_to(inv[:3,3],dr.shape);t=scene.cast(origin,dr);P=origin+t[:,None]*dr;good=np.isfinite(t)&(t>0)&((P>=box[0])&(P<=box[1])).all(1);depth[y:y+len(yy)]=np.where(good,t,0).reshape(yy.shape)
  for family in families:
   key=f'{SITE}__ALS__{family}_mvswalls';root=O/'renders'/key;root.mkdir(parents=True,exist_ok=True);p=root/f"{v['index']:04d}.npz"
   if not p.exists():
    old=BASE/'renders'/f'{SITE}__ALS__{family}'/p.name;z=loadz(old);a=z['depth'];merged=np.where((depth>0)&((a<=0)|(depth<a)),depth,a);savez(p,depth=merged,rgb=z['rgb'])
   rows[family].append(dict(v,file=p.name,sha256=sha(p)))
  if v['index']%40==0:print('WALL_RENDER',v['index']+1,len(views),flush=True)
 for family in families:
  key=f'{SITE}__ALS__{family}_mvswalls';root=O/'renders'/key
  dump(root/'receipt.json',dict(status='PASS',views=rows[family],box=box.tolist(),family=family+'_mvswalls',wall_surface=str(wall),wall_sha256=sha(wall),original_mvs=str(source),original_mvs_sha256=v.get('mesh_sha256') or sha(source),wall_triangles=count,mvs_triangles=before,rule='MVS triangle abs(n_z)<0.5; all ALS decision patches are roof kind=1; nearest positive ray hit of original patch surface and these MVS wall triangles; same evaluation box',threshold_source='/repo/scripts/phd/main_axes71_v2/a8_check.py',GT_read=False,optimization_steps=0,scientific_verdict=None))
  dump(O/'jobs'/f'{key}.json',dict(site=SITE,prior='ALS',family=family+'_mvswalls',key=key,cache=str(root),box=box.tolist(),scientific_verdict=None))
 timing('MVS_wall_variants_depth',start)
if __name__=='__main__':main()
