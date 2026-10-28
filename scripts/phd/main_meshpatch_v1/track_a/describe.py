import numpy as np
def element_frame(lab,C):
    _,lab=np.unique(lab,return_inverse=True); K=lab.max()+1
    cnt=np.bincount(lab,minlength=K).astype(float)
    mu=np.stack([np.bincount(lab,weights=C[:,k],minlength=K) for k in range(3)],1)/cnt[:,None]
    X=C-mu[lab]; cov=np.zeros((K,3,3))
    for p in range(3):
        for q in range(p,3):
            v=np.bincount(lab,weights=X[:,p]*X[:,q],minlength=K)/cnt; cov[:,p,q]=v; cov[:,q,p]=v
    ev,evec=np.linalg.eigh(cov)
    s=(X*evec[:,:,2][lab]).sum(1); t=(X*evec[:,:,1][lab]).sum(1)
    sd=np.sqrt(np.maximum(ev[:,2],1e-6)); s=s/sd[lab]*1.0; t=t/np.sqrt(np.maximum(ev[:,1],1e-6))[lab]   # normalised coords
    return lab,K,s,t,ev,mu
def fit_poly(lab,K,s,t,r,uc,hasm,order,min_n,iters=8,k_huber=2.0):
    n=len(r)
    feats=[np.ones(n)] + ([s,t] if order>=1 else []) + ([s*s,s*t,t*t] if order>=2 else [])
    F=np.stack(feats,1); P=F.shape[1]
    w0=np.where(hasm,1.0/uc**2,0.0); w=w0.copy()
    nm=np.bincount(lab,weights=hasm.astype(float),minlength=K)
    low=nm<min_n
    for it in range(iters):
        A=np.zeros((K,P,P)); b=np.zeros((K,P))
        for p in range(P):
            b[:,p]=np.bincount(lab,weights=w*F[:,p]*r,minlength=K)
            for q in range(p,P):
                v=np.bincount(lab,weights=w*F[:,p]*F[:,q],minlength=K); A[:,p,q]=v; A[:,q,p]=v
        Wt=np.maximum(A[:,0,0],1e-12)
        # ridge: tiny everywhere; huge on non-constant terms for elements with too few MVS patches
        for p in range(1,P): A[:,p,p]+=np.where(low,1e6,1e-3)*Wt
        A[:,0,0]=np.maximum(A[:,0,0],1e-12)
        beta=np.linalg.solve(A,b[:,:,None])[:,:,0]
        rh=(F*beta[lab]).sum(1)
        rho=np.abs(r-rh)/uc
        w=w0*np.minimum(1.0,k_huber/np.maximum(rho,1e-9))
    return beta,rh
