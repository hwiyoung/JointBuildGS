"""Recompute missing original-normal ring uncertainties with the inherited kernel."""
from common import *
import truth as K
from scipy.spatial import cKDTree
import multiprocessing as mp
K.U.DATA_ID.update(mvs_a=0)
K.scope['NMAD_K']=1.4826
def chunk(ids):return [(int(i),K.env['one_patch'](int(i))[1.5]) for i in ids]
def main(site):
    start=time.monotonic();pts=UN/'points'/site;X=np.load(pts/'mvs_a_xyz.npy').astype(float);views=np.load(pts/'mvs_a_view.npy');keys=np.load(pts/'mvs_a_key.npy')
    tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False);levels={}
    for k in range(1,6):
        n=int(np.searchsorted(keys,4.**-k))
        if n<1000:break
        levels[k]=(n,cKDTree(X[:n],leafsize=32,balanced_tree=False,compact_nodes=False))
    rows=[]
    for prior in cfg()['priors']:
      d=loadz(O/'geometry_raw'/f'{site}__{prior}.npz');missing=np.flatnonzero(~np.isfinite(d['u_mvs']));u=d['u_mvs'].copy();status=np.full(len(u),-1,np.int8)
      K.G.update(X=X,V=views,tree=tree,levels=levels,data='mvs_a',radii=[1.5],site=site,pset=prior,c=d['centre'],n=d.get('old_normal',d['normal']),roof=d['kind']==1,gt=None,original_index=d['source_index'])
      blocks=[missing[i:i+100] for i in range(0,len(missing),100)];done=0
      with mp.get_context('fork').Pool(4) as pool:
       for result in pool.imap_unordered(chunk,blocks):
        for i,r in result:status[i]=r['status'];u[i]=r.get('u',np.nan) if r['status']==0 else np.nan
        done+=len(result)
        if done%5000<100:print('RING_MISSING',site,prior,done,len(missing),flush=True)
      rec=dict(site=site,prior=prior,attempted=len(missing),recovered=int(np.isfinite(u[missing]).sum()),still_unavailable=int((~np.isfinite(u[missing])).sum()),GT_read=False)
      rows.append(rec);savez(O/'ring_recomputed'/f'{site}__{prior}.npz',patch_id=d['patch_id'],u_mvs=u,status=status)
      print('RING_RESULT',json.dumps(rec),flush=True)
    K.G.clear();dump(O/'timing'/f'{site}_ring.json',dict(at=now(),seconds=time.monotonic()-start,rows=rows,scientific_verdict=None))
if __name__=='__main__':main(sys.argv[1])
