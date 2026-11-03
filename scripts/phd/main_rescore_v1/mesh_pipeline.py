"""Bounded TSDF production. Each command is a separate <=32 GiB process."""
import sys,copy,ast,resource
from common import *
sys.path.insert(0,'/repo')
from src.phd import streamed_tsdf as T

def prepare(job,mode):
 start=time.monotonic();key=job['key'];root=O/'meshes'/key;wd=root/(mode+'_work');dest=wd/'inputs';dest.mkdir(parents=True,exist_ok=True)
 rr=Path(job.get('cache',O/'renders'/key));r=json.loads((rr/'receipt.json').read_text());assert r['status']=='PASS'
 if 'ply' in job:assert sha(job['ply'])==r['model_sha256']
 views=r['views'];canonical=json.loads((O/'views'/f"{job['site']}.json").read_text())['views'];assert len(views)==len(canonical)
 for a,b in zip(views,canonical):
  assert a['name']==b['name'] and a['virtual']==b['virtual']
  assert np.array_equal(a['K'],b['K']) and np.array_equal(a['W2C'],b['W2C'])
 if mode=='train':views=[v for v in views if not v['virtual']]
 H,W=views[0]['height'],views[0]['width'];depth=np.lib.format.open_memmap(dest/'depth_masked.npy','w+',dtype='f4',shape=(len(views),H,W));rgb=np.lib.format.open_memmap(dest/'rgb.npy','w+',dtype='u1',shape=(len(views),H,W,3));intr=[];extr=[];fractions=[]
 for i,v in enumerate(views):
  p=rr/v['file'];assert sha(p)==v['sha256'];z=loadz(p);depth[i]=z['depth'];rgb[i]=z['rgb'];k=np.array(v['K']);intr.append([k[0,0],k[1,1],k[0,2],k[1,2]]);extr.append(v['W2C']);fractions.append(float((z['depth']>0).mean()))
 depth.flush();rgb.flush();np.savez(dest/'cams.npz',names=[v['name'] for v in views],intr=intr,wh=[[W,H]]*len(views),extrinsic=extr)
 dump(dest/'meta.json',dict(site=job['site'],result=key,prior_scene=job['prior'],depth_dir=str(rr),box=r['box'],height=H,width=W,views=len(views),views_without_depth=[],mean_share_of_pixels_in_box=None,mean_share_of_pixels_with_depth=float(np.mean(fractions)),seconds=time.monotonic()-start,scientific_verdict=None))
 dump(wd/'binding.json',dict(job=job,receipt_sha256=sha(rr/'receipt.json'),view_list_sha256=sha(O/'views'/f"{job['site']}.json"),mode=mode,scientific_verdict=None));timing(key+'_'+mode+'_prepare',start)

def finish(job,mode):
 from bounded_cleanup import cleanup
 start=time.monotonic();root=O/'meshes'/job['key'];raw=root/(mode+'_work/merged.ply');out=root/(mode+'.ply')
 if mode=='train':
  if not out.exists():os.link(raw,out)
  dump(root/(mode+'.json'),dict(status='PASS',job=job,mode=mode,mesh_sha256=sha(out),voxel_m=T.VOXEL,trunc_m=T.TRUNC,cluster_to_keep=None,scientific_verdict=None))
 else:
  cleanup(job['site'],raw,out);p=out.with_suffix('.json');rec=json.loads(p.read_text());rec.update(job=job,mode=mode,voxel_m=T.VOXEL,trunc_m=T.TRUNC);dump(p,rec)
 timing(job['key']+'_'+mode+'_finish',start);print('MESH_COMPLETE',job['key'],mode,flush=True)

def main():
 cfg();job=json.loads(Path(sys.argv[1]).read_text());mode,cmd=sys.argv[2:4];wd=O/'meshes'/job['key']/(mode+'_work');start=time.monotonic()
 if mode=='coarse':T.VOXEL=.1;T.TRUNC=.5;T.L=T.VOXEL*16;T.M=2*T.L
 if cmd=='prepare':prepare(job,mode)
 elif cmd=='plan':T.plan(wd,'auto:18');T.order(wd)
 elif cmd=='tile':T.tile(wd,int(sys.argv[4]))
 elif cmd=='merge':T.merge(wd,wd/'merged.ply',wd/'merged.json')
 elif cmd=='finish':finish(job,mode)
 else:raise ValueError(cmd)
 if cmd not in ['prepare','finish']:timing(job['key']+'_'+mode+'_'+cmd+(''.join(sys.argv[4:])),start)
if __name__=='__main__':main()
