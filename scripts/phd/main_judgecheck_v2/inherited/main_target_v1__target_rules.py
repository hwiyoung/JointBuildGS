"""GT-free region decisions and uncertainty handling for the locked TARGET order."""
import numpy as np


def fill_median(values, groups, *, positive=False):
    values=np.asarray(values,float);out=values.copy();replaced=np.zeros(len(values),bool);records=[]
    valid=np.isfinite(values)&((values>0) if positive else (values>=0))
    for g in np.unique(groups):
        mask=groups==g;donors=mask&valid;missing=mask&~valid
        median=float(np.median(values[donors])) if donors.any() else None
        # Explicit zero filling is prohibited, including an all-zero donor group.
        if missing.any() and median is not None and median>0:
            out[missing]=median;replaced[missing]=True
        out[mask&~valid&~replaced]=np.nan
        records.append({'group':str(g),'donors':int(donors.sum()),'missing':int(missing.sum()),
                        'median':median,'replaced':int((mask&replaced).sum())})
    return out,replaced,records


def uncertainties(raw_u,raw_sigma,raw_a,kind,unit):
    groups=np.char.add(np.char.add(np.asarray(unit,dtype=str),':'),np.asarray(kind,dtype=str))
    u,ur,um=fill_median(raw_u,groups)
    sigma,sr,sm=fill_median(raw_sigma,groups,positive=True)
    a,ar,am=fill_median(raw_a,groups)
    return dict(u=u,sigma_p=sigma,a_sensitivity=a,u_replaced=ur,sigma_p_replaced=sr,
                any_replaced=ur|sr,a_replaced=ar),{'u':um,'sigma_p':sm,'a_sensitivity':am}


def detection(n,s,u,sigma):
    n=np.asarray(n);out=np.full(len(n),np.nan)
    ok=(n>=4)&np.isfinite(s)&np.isfinite(u)&np.isfinite(sigma)
    out[ok]=1.96*np.sqrt(s[ok]**2/n[ok]+u[ok]**2+.0275**2+sigma[ok]**2)
    return out


def fit_t2(distance,area):
    """Two area-weighted normals in log10 distance, 500 fixed EM iterations."""
    x=np.log10(np.abs(np.asarray(distance,float)));w=np.asarray(area,float);w=w/w.sum()
    order=np.argsort(x);cum=np.cumsum(w[order])
    means=np.interp([.25,.85],cum,x[order])
    var0=np.sum(w*(x-np.sum(w*x))**2)
    var=np.full(2,max(float(var0),1e-12));mix=np.array([.5,.5]);history=[]
    for it in range(500):
        lp=np.log(mix)[None,:]-.5*np.log(2*np.pi*var)[None,:]-.5*(x[:,None]-means)**2/var
        maximum=lp.max(1);prob=np.exp(lp-maximum[:,None]);norm=prob.sum(1);prob/=norm[:,None]
        ww=w[:,None]*prob;mix=ww.sum(0);means=(ww*x[:,None]).sum(0)/mix
        var=np.maximum((ww*(x[:,None]-means)**2).sum(0)/mix,1e-12)
        if it in [0,9,49,99,199,499]:history.append({'iteration':it+1,'log_likelihood':float(np.sum(w*(maximum+np.log(norm))))})
    order=np.argsort(means);means,var,mix=means[order],var[order],mix[order]
    # log(p_large/p_small) = A*x^2+B*x+C; choose the first upward crossing.
    A=.5/var[0]-.5/var[1];B=means[1]/var[1]-means[0]/var[0]
    C=np.log(mix[1]/mix[0])+.5*np.log(var[0]/var[1])+.5*means[0]**2/var[0]-.5*means[1]**2/var[1]
    roots=np.roots([A,B,C]) if abs(A)>1e-14 else np.array([-C/B]) if abs(B)>1e-14 else np.array([])
    crossings=sorted(float(v.real) for v in roots if abs(v.imag)<1e-9 and v.real>means[0] and 2*A*v.real+B>0)
    t2=10**crossings[0] if crossings else None
    return dict(T2_m=t2,means_log10=means.tolist(),centres_m=(10**means).tolist(),
        sd_log10=np.sqrt(var).tolist(),area_weights=mix.tolist(),iterations=500,history=history,
        status='STOP_T2_MIXTURE' if mix[1]<.05 or t2 is None else 'PASS_T2_MIXTURE')


def targets(n,d,DL,u,sigma_p,normal,T2,photo):
    validnormal=np.isfinite(normal).all(1)&(np.linalg.norm(normal,axis=1)>1e-6)
    available=validnormal&np.isfinite(sigma_p)&np.isfinite(u)
    label=np.full(len(n),-1,np.int8)
    label[available&(n<4)]=0
    observed=available&(n>=4)&np.isfinite(d)&np.isfinite(DL)
    label[observed&(np.abs(d)<=DL)]=1
    diff=observed&(np.abs(d)>DL)
    label[diff]=2;label[diff&((np.abs(d)>T2)|(photo==1))]=3
    sm=np.sqrt(u*u+.0275**2);h=np.full(len(n),np.nan);sigma=np.full(len(n),np.nan)
    p=(label==0)|(label==2);h[p]=0;sigma[p]=sigma_p[p]
    agree=label==1
    h[agree]=(d[agree]/sm[agree]**2)/(1/sm[agree]**2+1/sigma_p[agree]**2)
    sigma[agree]=1/np.sqrt(1/sm[agree]**2+1/sigma_p[agree]**2)
    correction=label==3;h[correction]=d[correction];sigma[correction]=sm[correction]
    return label,h,sigma
