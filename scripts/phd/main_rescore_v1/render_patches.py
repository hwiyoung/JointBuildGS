"""Reference-free patch-quads -> frozen-view depth; CPU ray casting, no training."""
import sys
from common import *
from geometry import patch_basis
from src.phd.metrics_v3.surface import MeshScene

def main(site,prior,family):
 start=time.monotonic();cfg();keys=['patch_id','centre','normal','tangent1','tangent2','kind','prior','prior_height_m','mvs_mean_m','region'];core=loadz(JA/'core_points'/f'{site}__{prior}.npz',keys)
 if family=='fusion':
  region=core['region'][4];height=np.where(np.isin(region,[1,4]),core['prior_height_m'],np.where(region==2,core['mvs_mean_m'],np.nan));savez(O/'targets_fusion'/f'{site}__{prior}.npz',patch_id=core['patch_id'],region=region,target_height_m=height,surface_exists=np.isfinite(height))
 else:
  folder='targets_v2' if family=='judgment_mesh' else 'targets_oracle';target=loadz(O/folder/f'{site}__{prior}.npz');assert np.array_equal(target['patch_id'],core['patch_id']);height=target['target_height_m']
 a,b,n=patch_basis(core);keep=np.isfinite(height)&np.isfinite(n).all(1);c=core['centre'][keep]+height[keep,None]*n[keep];a=a[keep]*.125;b=b[keep]*.125;V=np.stack([c-a-b,c+a-b,c+a+b,c-a+b],1).reshape(-1,3);F=(np.arange(len(c))[:,None,None]*4+np.array([[0,1,2],[0,2,3]])).reshape(-1,3);scene=MeshScene(V,F);key=f'{site}__{prior}__{family}';root=O/'renders'/key;root.mkdir(parents=True,exist_ok=True);savez(root/'patch_geometry.npz',patch_id=core['patch_id'][keep],vertices=V,triangles=F,target_height_m=height[keep]);view_record=json.loads((O/'views'/f'{site}.json').read_text());views=view_record['views']
 if 'box' in view_record:box=view_record['box']
 else:
  assert site=='B173nb_b10';box=json.loads((O/'meshes/B173nb_b10__ALS__r8_30000/final_work/inputs/meta.json').read_text())['box']
 box=np.array(box);records=[]
 for i,v in enumerate(views):
  K=np.array(v['K']);W,H=v['width'],v['height'];inv=np.linalg.inv(v['W2C']);depth=np.zeros((H,W),'f4')
  for y in range(0,H,128):
   yy,xx=np.meshgrid(np.arange(y,min(y+128,H)),np.arange(W),indexing='ij');D=np.stack([(xx-K[0,2])/K[0,0],(yy-K[1,2])/K[1,1],np.ones_like(xx)],-1).reshape(-1,3)@inv[:3,:3].T;origin=np.broadcast_to(inv[:3,3],D.shape);t=scene.cast(origin,D);P=origin+t[:,None]*D;good=np.isfinite(t)&(t>0)&((P>=box[0])&(P<=box[1])).all(1);depth[y:y+yy.shape[0]]=np.where(good,t,0).reshape(yy.shape)
  p=root/f'{i:04d}.npz';savez(p,depth=depth,rgb=np.zeros((H,W,3),'u1'));records.append(dict(v,file=p.name,sha256=sha(p)))
  if i%40==0:print('PATCH_RENDER',key,i+1,len(views),flush=True)
 dump(root/'receipt.json',dict(status='PASS',views=records,box=box.tolist(),family=family,patches=int(keep.sum()),source_sha256=sha(__file__),source_core_sha256=sha(JA/'core_points'/f'{site}__{prior}.npz'),seconds=time.monotonic()-start,GT_read=False if family!='oracle' else 'oracle target exception only',optimization_steps=0,scientific_verdict=None));dump(O/'jobs'/f'{key}.json',dict(site=site,prior=prior,family=family,key=key,box=box.tolist(),scientific_verdict=None));timing('render_'+key,start)
if __name__=='__main__':main(*sys.argv[1:])
