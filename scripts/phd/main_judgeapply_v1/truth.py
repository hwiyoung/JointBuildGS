"""Evaluation-only GT axis positions. Decisions must already be sealed to disk."""
from common import *
from inherit import functions
from scipy.spatial import cKDTree
import types,multiprocessing as mp
scope=dict(np=np);functions('u_core.py',[n.name for n in __import__('ast').parse((HERE/'inherited/u_core.py').read_text()).body if isinstance(n,__import__('ast').FunctionDef)],scope)
kernel=types.SimpleNamespace(**scope)
unc=json.loads((R/'configs/phd/main_uncert_v1/uncert_v1.json').read_text());defs=unc['defs'];G={}
U=types.SimpleNamespace(CFG=unc,SITE_ID={s:i for i,s in enumerate(['B0_b10','B173nb_b10','R1rep_b10'])},SET_ID={'LoD2':0,'ALS':1},DATA_ID={'gt':3},R_ID={1.5:1})
env=dict(np=np,time=time,C=kernel,U=U,D=defs,RI=defs['inner_radius_m'],G=G)
functions('ring_kernel.py',['column','ring_points','one_patch'],env)
def chunk(ids):return [(int(i),env['one_patch'](int(i))[0]) for i in ids]
def main(site):
    start=time.monotonic()
    for prior in cfg()['priors']:
      p=O/'decisions'/f'{site}__{prior}.npz';before=sha(p);d=loadz(p);N=len(d['n']);g=np.full(N,np.nan);status=np.full(N,9,np.int8);ii=d['source_index']
      if prior=='LoD2':
        original=loadz(UN/'work'/f'gt_{site}_LoD2.npz',['p','status']);g=original['p'][ii].astype(float);status=original['status'][ii]
      else:
        X=np.load(UN/'points'/site/'gt_xyz.npy').astype(float);tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False)
        G.update(X=X,tree=tree,c=d['centre'],n=d['normal'],roof=d['kind']==1,data='gt',site=site,pset=prior,original_index=ii)
        ids=np.flatnonzero(np.isfinite(d['normal']).all(1));blocks=[ids[i:i+100] for i in range(0,len(ids),100)];done=0
        with mp.get_context('fork').Pool(4) as pool:
          for result in pool.imap_unordered(chunk,blocks):
            for i,r in result:status[i]=r['status'];g[i]=r.get('p',np.nan)
            done+=len(result)
            if done%2000<100:print('GT_EVALUATION',site,prior,done,len(ids),'seconds',time.monotonic()-start,flush=True)
        G.clear();del X,tree
      tau=np.array([cfg()['geometry']['tau_m'][site][prior+('_roof' if k==1 else '_wall')] for k in d['kind']]);cell=np.full(N,6,np.int8)
      usable=(status==0)&np.isfinite(g)&np.isfinite(d['prior_height_m'])&np.isfinite(d['normal']).all(1)
      pg=abs(d['prior_height_m']-g)<=tau;observed=(d['n']>=4)&np.isfinite(d['mvs_mean_m']);mg=abs(d['mvs_mean_m']-g)<=tau
      cell[usable&observed&pg&mg]=0;cell[usable&observed&~pg&mg]=1;cell[usable&observed&pg&~mg]=2;cell[usable&observed&~pg&~mg]=3
      cell[usable&~observed&pg]=4;cell[usable&~observed&~pg]=5
      invalid=~np.isfinite(d['prior_height_m'])|~np.isfinite(d['normal']).all(1);cell[invalid]=9
      oracle=np.full(N,9,np.int8)
      for a,b in [(0,0),(1,2),(2,1),(4,4)]:oracle[cell==a]=b
      d['region'][6]=oracle;d.update(gt_p=g,gt_status=status,cell=cell,tau_m=tau)
      assert sha(p)==before;savez(O/'core_points'/f'{site}__{prior}.npz',**d)
    dump(O/'timing'/f'{site}_truth.json',dict(at=now(),seconds=time.monotonic()-start,scientific_verdict=None));print('TRUTH_COMPLETE',site,flush=True)
if __name__=='__main__':main(sys.argv[1])
