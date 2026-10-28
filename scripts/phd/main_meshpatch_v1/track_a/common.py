import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, json
from units_lib import union_mask
W='/home/claude/work/cache'
def load(prior):
    d=dict(np.load(f'{W}/{prior}.npz')); x=dict(np.load(f'{W}/{prior}_x.npz'))
    E=np.load(f'{W}/{prior}_edges.npy').astype(np.int64)
    U=dict(np.load(f'{W}/{prior}_units.npz'))
    cases=json.load(open(f'{W}/cases.json'))[prior]
    return d,x,E,U,cases
def truth_comp(d,E):
    p=f'{W}/truthcomp_{len(d["cell"])}.npy'
    if os.path.exists(p): return np.load(p)
    cell=d['cell']; i,j=E[:,0],E[:,1]
    T=union_mask(len(cell),E,cell[i]==cell[j]); np.save(p,T); return T
def score(lab,d,T,cases=None):
    cell=d['cell'].astype(int); a=d['area'].astype(float); gtv=cell!=6
    _,lab=np.unique(lab,return_inverse=True); K=lab.max()+1
    M=np.zeros((K,6)); np.add.at(M,(lab[gtv],cell[gtv]),a[gtv])
    tot=M.sum(1); has=tot>0
    purity=float(M[has].max(1).sum()/tot[has].sum())
    gidx=np.where(gtv)[0]; key=T[gidx].astype(np.int64)*K+lab[gidx]
    o=np.argsort(key,kind='stable'); k=key[o]; w=a[gidx][o]
    st=np.r_[0,np.where(k[1:]!=k[:-1])[0]+1]; s=np.add.reduceat(w,st); t=k[st]//K
    o2=np.lexsort((-s,t)); first=np.r_[True,t[o2][1:]!=t[o2][:-1]]
    OS=float(1-s[o2][first].sum()/w.sum()); US=1-purity
    maj=M.argmax(1); minority=gtv&(cell!=maj[lab])
    uarea=np.bincount(lab,weights=a,minlength=K)
    out={'groups':int(K),'per100':float(K/(a.sum()/100)),'mix':US,'split':OS,'D':float(np.sqrt((OS**2+US**2)/2))}
    if cases:
        cs={}
        for nm,idx in cases.items():
            idx=np.array(idx); ca=np.bincount(lab[idx],weights=a[idx],minlength=K); mu=int(ca.argmax())
            cs[nm]=(round(float(ca[mu]/a[idx].sum())*100),round(float(ca[mu]/uarea[mu])*100),int((ca>0).sum()))
        out['cases']=cs
    return out, minority
