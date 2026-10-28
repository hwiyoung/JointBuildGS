# Representative plane segmentation on MVS points (one point per patch):
#  rg_smooth : region growing with smoothness constraint (Rabbani et al. 2006; PCL RegionGrowing)
#  rg_plane  : region growing against the region's plane (Vosselman et al. 2004 style; 3DBAG uses region growing)
#  ransac    : efficient-RANSAC-like extraction with connectivity check (Schnabel et al. 2007), per building
import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, time, json
from numba import njit
from scipy.spatial import cKDTree
from common import *
from units_lib import union_mask

@njit(cache=True)
def rg_smooth(n,indptr,indices,N,curv,order,cth,cos_th):
    lab=np.full(n,-1,np.int64); q=np.empty(n,np.int64); r=0
    for s in order:
        if lab[s]>=0 or curv[s]>cth: continue
        lab[s]=r; h=0; t=0; q[t]=s; t+=1
        while h<t:
            c=q[h]; h+=1
            for k in range(indptr[c],indptr[c+1]):
                b=indices[k]
                if lab[b]>=0: continue
                if abs(N[c,0]*N[b,0]+N[c,1]*N[b,1]+N[c,2]*N[b,2])>cos_th:
                    lab[b]=r
                    if curv[b]<=cth:
                        q[t]=b; t+=1
        r+=1
    return lab

@njit(cache=True)
def plane_from_sums(S1,S2,m):
    c=S1/m; C=S2/m-np.outer(c,c)
    w,v=np.linalg.eigh(C)
    return c,v[:,0].copy()

@njit(cache=True)
def rg_plane(n,indptr,indices,P,N,curv,order,cth,cos_th,eps,minsize):
    lab=np.full(n,-1,np.int64); tried=np.zeros(n,np.bool_); q=np.empty(n,np.int64); r=0
    for s in order:
        if lab[s]>=0 or tried[s] or curv[s]>cth: continue
        tried[s]=True
        p0=P[s].copy(); nn=N[s].copy()
        S1=np.zeros(3); S2=np.zeros((3,3)); m=0
        lab[s]=r; h=0; t=0; q[t]=s; t+=1
        S1+=P[s]; S2+=np.outer(P[s],P[s]); m+=1; nextfit=8
        while h<t:
            c=q[h]; h+=1
            for k in range(indptr[c],indptr[c+1]):
                b=indices[k]
                if lab[b]>=0: continue
                d=(P[b,0]-p0[0])*nn[0]+(P[b,1]-p0[1])*nn[1]+(P[b,2]-p0[2])*nn[2]
                if abs(d)<eps[b] and abs(N[b,0]*nn[0]+N[b,1]*nn[1]+N[b,2]*nn[2])>cos_th:
                    lab[b]=r; q[t]=b; t+=1
                    S1+=P[b]; S2+=np.outer(P[b],P[b]); m+=1
                    if m>=nextfit:
                        p0,nn=plane_from_sums(S1,S2,m); nextfit=m*2
        if t<minsize:
            for k in range(t): lab[q[k]]=-1
        else:
            r+=1
    return lab

@njit(cache=True)
def ransac_building(ids,indptr,indices,P,N,eps,cos_al,minsize,nhyp,nsub,seed,start_label,lab):
    np.random.seed(seed)
    rem=ids.copy(); nrem=len(rem); r=start_label; fails=0
    inl=np.zeros(len(lab),np.bool_); comp=np.full(len(lab),-1,np.int64); q=np.empty(len(ids),np.int64)
    while nrem>=minsize and fails<5:
        best=-1; bscore=-1
        ns=min(nsub,nrem)
        sub=np.empty(ns,np.int64)
        for k in range(ns): sub[k]=rem[np.random.randint(nrem)]
        for hcount in range(nhyp):
            i=rem[np.random.randint(nrem)]
            sc=0
            for k in range(ns):
                b=sub[k]
                d=(P[b,0]-P[i,0])*N[i,0]+(P[b,1]-P[i,1])*N[i,1]+(P[b,2]-P[i,2])*N[i,2]
                if abs(d)<eps and abs(N[b,0]*N[i,0]+N[b,1]*N[i,1]+N[b,2]*N[i,2])>cos_al: sc+=1
            if sc>bscore:
                bscore=sc; best=i
        p0=P[best].copy(); nn=N[best].copy(); ok=True; bestc=-1; bests=0
        for it in range(2):
            for k in range(nrem):
                b=rem[k]; comp[b]=-1
                d=(P[b,0]-p0[0])*nn[0]+(P[b,1]-p0[1])*nn[1]+(P[b,2]-p0[2])*nn[2]
                inl[b]=abs(d)<eps and abs(N[b,0]*nn[0]+N[b,1]*nn[1]+N[b,2]*nn[2])>cos_al
            ncomp=0; bestc=-1; bests=0
            for k in range(nrem):
                b=rem[k]
                if (not inl[b]) or comp[b]>=0: continue
                comp[b]=ncomp; h=0; t=0; q[t]=b; t+=1
                while h<t:
                    c=q[h]; h+=1
                    for kk in range(indptr[c],indptr[c+1]):
                        e=indices[kk]
                        if inl[e] and comp[e]<0:
                            comp[e]=ncomp; q[t]=e; t+=1
                if t>bests:
                    bests=t; bestc=ncomp
                ncomp+=1
            if bests<3:
                ok=False; break
            if it==0:
                S1=np.zeros(3); S2=np.zeros((3,3)); m=0
                for k in range(nrem):
                    b=rem[k]
                    if comp[b]==bestc:
                        S1+=P[b]; S2+=np.outer(P[b],P[b]); m+=1
                p0,nn=plane_from_sums(S1,S2,m)
        if ok and bests>=minsize:
            k2=0
            for k in range(nrem):
                b=rem[k]
                if comp[b]==bestc and inl[b]:
                    lab[b]=r
                else:
                    rem[k2]=b; k2+=1
            nrem=k2; r+=1; fails=0
        else:
            fails+=1
        for k in range(len(ids)):
            b=ids[k]; comp[b]=-1; inl[b]=False
    return r

def csr(n,E):
    a=np.r_[E[:,0],E[:,1]]; b=np.r_[E[:,1],E[:,0]]
    o=np.argsort(a,kind='stable'); a=a[o]; b=b[o]
    indptr=np.zeros(n+1,np.int64); np.add.at(indptr,a+1,1); indptr=np.cumsum(indptr)
    return indptr,b.astype(np.int64)

def finish(lab,d,E,hasm):
    # leftovers (MVS points not in any plane) -> connected components; no-MVS patches -> connected components
    n=len(lab); i,j=E[:,0],E[:,1]; sameb=d['bld'][i]==d['bld'][j]
    left=hasm&(lab<0)
    cc=union_mask(n,E,sameb&((left[i]&left[j])|((~hasm[i])&(~hasm[j]))))
    out=np.where(lab>=0,lab,n+cc).astype(np.int64)
    return out,left

if __name__=='__main__':
    prior=sys.argv[1]; methods=sys.argv[2].split(',')
    eps=float(sys.argv[3]) if len(sys.argv)>3 else 0.10
    d,x,E,U,cases=load(prior); n=len(d['cell'])
    hasm=(d['mvs_a_status']==0)&np.isfinite(d['z'])&np.isfinite(d['mvs_n'][:,0])
    C=d['centre'].astype(np.float64); Nn=d['normal'].astype(np.float64)
    P=C+Nn*np.where(hasm,d['mvs_p'],0)[:,None]
    MN=np.where(hasm[:,None],d['mvs_n'],0).astype(np.float64); MN/=np.maximum(np.linalg.norm(MN,axis=1,keepdims=True),1e-12)
    i,j=E[:,0],E[:,1]; keep=(d['bld'][i]==d['bld'][j])&hasm[i]&hasm[j]
    indptr,indices=csr(n,E[keep])
    # curvature from 16 nearest MVS points of the same building
    t0=time.time(); cp=f'{W}/{prior}_curv.npy'
    if os.path.exists(cp): curv=np.load(cp)
    else:
        curv=np.full(n,np.inf); ids=np.where(hasm)[0]; tr=cKDTree(P[ids])
        for st in range(0,len(ids),200000):
            sl=ids[st:st+200000]; dd,nb=tr.query(P[sl],k=16); nb=ids[nb]
            same=d['bld'][nb]==d['bld'][sl][:,None]
            X=P[nb]-P[sl][:,None,:]; X=np.where(same[:,:,None],X,0)
            cnt=same.sum(1)[:,None,None]; mu=X.sum(1,keepdims=True)/cnt
            Y=np.where(same[:,:,None],X-mu,0); Cv=np.einsum('nki,nkj->nij',Y,Y)/cnt
            ev=np.linalg.eigvalsh(Cv); curv[sl]=ev[:,0]/np.maximum(ev.sum(1),1e-12)
        np.save(cp,curv)
    print('curv',round(time.time()-t0,1),'s, pct',np.round(np.percentile(curv[hasm],[10,50,90]),4),flush=True)
    cth=float(np.percentile(curv[hasm],90)); order=np.argsort(np.where(hasm,curv,np.inf),kind='stable')
    R={}
    for m in methods:
        t0=time.time()
        if m=='rg_smooth':
            lab=rg_smooth(n,indptr,indices,MN,curv,order,cth,np.cos(np.radians(10)))
            lab[~hasm]=-1
        elif m=='rg_plane':
            lab=rg_plane(n,indptr,indices,P,MN,curv,order,cth,np.cos(np.radians(20)),np.full(n,eps),16)
        elif m=='rg_plane_u':
            ev=np.clip(2.5*np.where(hasm,d['u_mvs'],0.1).astype(np.float64),0.05,0.30)
            lab=rg_plane(n,indptr,indices,P,MN,curv,order,cth,np.cos(np.radians(20)),ev,16)
        elif m=='ransac':
            lab=np.full(n,-1,np.int64); r=0
            for b in np.unique(d['bld']):
                ids=np.where(hasm&(d['bld']==b))[0]
                if len(ids)==0: continue
                ids=ids[np.argsort(curv[ids])]
                r=ransac_building(ids,indptr,indices,P,MN,eps,np.cos(np.radians(20)),16,300,3000,int(b)+7,r,lab)
        out,left=finish(lab,d,E,hasm)
        key=f'{m}' if m in ('rg_smooth','rg_plane_u') else f'{m}_e{int(eps*100)}'
        U[key]=out
        print(prior,key,'planes',len(np.unique(lab[lab>=0])),'leftover MVS area %',round(float(d['area'][left].sum()/d['area'][hasm].sum()*100),1),round(time.time()-t0,1),'s',flush=True)
    np.savez_compressed(f'{W}/{prior}_units.npz',**{k:v.astype(np.int64) for k,v in U.items()})
