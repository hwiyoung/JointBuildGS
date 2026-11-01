"""Independent brute-force validation of length boundaries and face-repair behavior."""
import numpy as np
from common import *
from cylinder_runtime import run


def reference(t,H):
    t=np.sort(t);o=None;best=-1;mode=None
    for top in H-.05*np.arange(round((2*H-.3)/.05)+1):
        count=int(((t>=top-.3-1e-9)&(t<=top+1e-9)).sum())
        if count>best:best=count;mode=top-.15
        if o is None and count>=.2*len(t):o=top-.15
    if not len(t):return np.array([0,np.nan,np.nan,np.nan,np.nan,np.nan,0.])
    old=t[np.abs(t-o)<=1] if o is not None else np.empty(0)
    if len(old)<4 and len(t)>=4:o=mode
    s=t[(t>=o-1)&(t<=o+1)] if o is not None else np.empty(0)
    v=np.array([len(s),np.nan,np.nan,np.nan,np.nan,np.nan,len(t)],float)
    if len(s):
        med=np.median(s);v[1:6]=[np.mean(s),med,np.std(s,ddof=1) if len(s)>1 else np.nan,1.4826*np.median(abs(s-med)),o]
    return v


def main():
    cfg,lock=locked_r2();root=OUT/'r2/verification';root.mkdir(exist_ok=True)
    rng=np.random.default_rng(1101)
    # +5.6m true point surface, diffuse no-20-percent cylinder, sparse and empty columns.
    x=np.r_[np.c_[rng.uniform(-.06,.06,(100,2)),rng.normal(5.6,.02,100)],
            np.c_[rng.uniform(-.06,.06,(120,2))+[2,0],np.linspace(-4.9,4.9,120)],
            [[4,0,0],[4,0,.1],[4,0,.2]]].astype('f4')
    p=root/'synthetic.npy';np.save(p,x);c=np.array([[0,0,0],[2,0,0],[4,0,0],[6,0,0]],float);n=np.tile([0.,0.,1.],(4,1))
    f=root/'synthetic.bin';run(p,c,n,f,OUT/'r2/cylinders')
    a=np.memmap(f,dtype='<f8',mode='r',shape=(4,3,10,7));count=0;maximum=0
    for i in range(4):
        delta=x.astype(float)-c[i];t=delta[:,2];r2=(delta[:,:2]**2).sum(1)
        for h,H in enumerate([5.,3.,10.]):
            for r,R in enumerate(cfg['cylinder']['radii_m']):
                expected=reference(t[(abs(t)<=H)&(r2<=R*R)],H);got=a[i,h,r]
                assert np.allclose(got,expected,rtol=1e-10,atol=1e-10,equal_nan=True),(i,h,r,got,expected)
                maximum=max(maximum,float(np.max(abs(got[np.isfinite(expected)]-expected[np.isfinite(expected)]))));count+=1
    assert a[0,0,1,0]==0 and a[0,2,1,0]>=4
    assert a[1,0,1,0]>=4 and a[2,0,1,0]==3 and a[3,0,1,0]==0
    dump(root/'cylinders.json',dict(status='PASS',cases=count,max_abs_difference=maximum,config_sha256=lock['config_sha256'],scientific_verdict=None))
    print('R2_CYLINDER_VERIFIED',count,maximum,flush=True)


if __name__=='__main__':main()
