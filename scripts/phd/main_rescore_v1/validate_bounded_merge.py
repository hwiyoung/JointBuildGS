"""One byte-for-byte implementation check against the original merger."""
from common import *
import bounded_merge as B
T=B.T
def main():
 rows=[];B.CHUNK=1
 for unsettled in [False,True]:
  root=O/'validation/bounded_merge'/('unsettled' if unsettled else 'clean');(root/'tiles').mkdir(parents=True,exist_ok=True);(root/'order').mkdir(exist_ok=True);dump(root/'plan/layout.json',dict(nx=2,ny=1,tiles=[dict(k=0),dict(k=1)]));dump(root/'inputs/meta.json',dict(site='fixture',result='fixture',prior_scene='ALS',depth_dir='fixture',box=[[0,0,0],[2,2,2]],views=2,views_without_depth=[],mean_share_of_pixels_in_box=1.,mean_share_of_pixels_with_depth=1.,seconds=0.));np.array([[1,0,0],[0,0,0]],np.int32).tofile(root/'order/ord_onepiece.i32')
  for k in [0,1]:
   V=np.array([[.8,0,0],[.8,.1,0],[.7 if k==0 else .9,0,0],[.7 if k==0 else .9,.1,0]]);F=np.array([[0,1,2],[1,3,2]],np.int32);e=F.astype(np.int8);vc=np.array([10,20,30+20*k,40+20*k],np.int64)
   if unsettled:vc[0]=-1;e[e==0]=-1
   savez(root/f'tiles/tile{k}.npz',V=V,F=F,C=np.tile([.25,.5,1.],(4,1)),gcode=np.array([100+k,100+k]),e=e,vcode=vc,keys=np.array([[k,0,0]],np.int32),lens=np.array([2]));dump(root/f'tiles/tile{k}.json',dict(k=k,kept=dict(vertices=4,triangles=2),seconds=dict(all=0),peak_host_gb=0,cgroup_peak_gb=0))
  T.merge(root,root/'original.ply',root/'original.json');B.merge(root,root/'bounded.ply',root/'bounded.json');a=sha(root/'original.ply');b=sha(root/'bounded.ply');assert a==b,(unsettled,a,b);va=json.loads((root/'original.json').read_text())['tiled']['vertices'];vb=json.loads((root/'bounded.json').read_text())['tiled']['vertices'];assert va==vb;rows.append(dict(unsettled=unsettled,original_sha256=a,bounded_sha256=b,status='PASS_EXACT_BYTES_AND_VERTEX_METADATA'))
 dump(O/'validation/bounded_merge/validation.json',dict(rows=rows,source_sha256=sha(Path(B.__file__)),scientific_verdict=None));print('BOUNDED_MERGE_PARITY_PASS')
if __name__=='__main__':main()
