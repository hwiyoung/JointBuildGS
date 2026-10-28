import numpy as np
from numba import njit

@njit(cache=True)
def find(p,x):
    r=x
    while p[r]!=r: r=p[r]
    while p[x]!=r:
        nx=p[x]; p[x]=r; x=nx
    return r

@njit(cache=True)
def union_mask(n,E,mask):
    p=np.arange(n)
    for k in range(E.shape[0]):
        if mask[k]:
            a=find(p,E[k,0]); b=find(p,E[k,1])
            if a!=b: p[b]=a
    for x in range(n): p[x]=find(p,x)
    return p

@njit(cache=True)
def srm(n,E,order,z,w,hasm,allow,thr_k_sigma):
    # statistical region merging on z; w = effective count per patch (area/Ac)
    p=np.arange(n); S=np.zeros(n); W=np.zeros(n); A=np.zeros(n)
    for x in range(n):
        if hasm[x]:
            S[x]=w[x]*z[x]; W[x]=w[x]
    for t in range(order.shape[0]):
        k=order[t]
        if not allow[k]: continue
        i=E[k,0]; j=E[k,1]
        a=find(p,i); b=find(p,j)
        if a==b: continue
        if hasm[i]!=hasm[j]: continue
        if not hasm[i]:
            p[b]=a; continue
        m1=S[a]/W[a]; m2=S[b]/W[b]
        ne1=max(1.0,W[a]); ne2=max(1.0,W[b])
        if abs(m1-m2)<=thr_k_sigma*np.sqrt(1.0/ne1+1.0/ne2):
            p[b]=a; S[a]+=S[b]; W[a]+=W[b]
    for x in range(n): p[x]=find(p,x)
    return p

@njit(cache=True)
def best_partner(nreg,ru,rv,dE):
    best=np.full(nreg,-1); bval=np.zeros(nreg)
    for k in range(ru.shape[0]):
        a=ru[k]; b=rv[k]; v=dE[k]
        if v<0:
            if best[a]==-1 or v<bval[a]: best[a]=b; bval[a]=v
            if best[b]==-1 or v<bval[b]: best[b]=a; bval[b]=v
    return best

def ms_merge(n,E,z,w,hasm,allow,sigma,lam,max_rounds=400):
    # greedy piecewise-constant Mumford-Shah (Potts) region merging, mutual-best rounds
    # region-level adjacency list (pairs + shared edge counts) re-aggregated each round
    W=np.where(hasm,w,0.0).astype(np.float64); S=np.where(hasm,w*z,0.0)
    valid=allow&(hasm[E[:,0]]==hasm[E[:,1]])
    Ev=E[valid]
    root=np.arange(n)
    def agg(u,v,c):
        m=u!=v; u=u[m]; v=v[m]; c=c[m]
        lo=np.minimum(u,v).astype(np.int64); hi=np.maximum(u,v).astype(np.int64)
        key=lo*n+hi; uk,inv=np.unique(key,return_inverse=True)
        cc=np.bincount(inv,weights=c)
        return (uk//n).astype(np.int64),(uk%n).astype(np.int64),cc
    a,b,cnt=agg(Ev[:,0],Ev[:,1],np.ones(len(Ev)))
    rnd=0
    for rnd in range(max_rounds):
        if len(a)==0: break
        Wa=W[a]; Wb=W[b]; both=(Wa>0)&(Wb>0)
        dm=np.zeros(len(a)); dm[both]=S[a[both]]/Wa[both]-S[b[both]]/Wb[both]
        h=np.zeros(len(a)); h[both]=Wa[both]*Wb[both]/(Wa[both]+Wb[both])
        dE=h*dm*dm/(sigma*sigma)-lam*cnt
        best=best_partner(n,a,b,dE)
        mutual=(best[a]==b)&(best[b]==a)&(dE<0)
        if not mutual.any(): break
        ma=a[mutual]; mb=b[mutual]
        W[ma]+=W[mb]; S[ma]+=S[mb]; W[mb]=0; S[mb]=0
        remap=np.arange(n); remap[mb]=ma
        root=remap[root]
        a,b,cnt=agg(remap[a],remap[b],cnt)
    return root, rnd
