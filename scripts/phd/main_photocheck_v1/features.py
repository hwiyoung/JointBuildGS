"""Extract all candidates without truth inputs."""
from common import *
def derive(h,score,sigma,mvs,texture,count):
    n=len(score);keys=['s0','s_in','h_in','s_out','h_out','s_mvs','s_max','h_max','s_med','difference']
    out={k:np.full(n,np.nan,np.float32) for k in keys};peakmask=np.zeros(score.shape,bool)
    cfg=load(C/'photocheck_v1.json');judgments=np.full((n,15),2,np.int8)
    for i in range(n):
        valid=np.isfinite(h[i])&np.isfinite(score[i]);hh=h[i,valid];ss=score[i,valid]
        if len(hh):
            order=np.argsort(hh);hh=hh[order];ss=ss[order]
            j=np.argmax(ss);out['s_max'][i]=ss[j];out['h_max'][i]=hh[j];out['s_med'][i]=np.median(ss)
            zero=np.flatnonzero(np.abs(hh)<1e-7)
            if len(zero):out['s0'][i]=ss[zero[0]]
            if np.isfinite(mvs[i]):out['s_mvs'][i]=ss[np.argmin(abs(hh-mvs[i]))]
            peaks=np.zeros(len(hh),bool)
            for k in range(1,len(hh)-1):
                nearby=abs(hh-hh[k])<=.100001
                if ss[k]>=np.max(ss[nearby]):
                    tied=np.flatnonzero(nearby&(ss==ss[k]));peaks[k]=k==tied[len(tied)//2]
            source_indices=np.flatnonzero(valid)[order];peakmask[i,source_indices[peaks]]=True
            if np.isfinite(sigma[i]):
                inside=abs(hh)<=3*sigma[i]+1e-8;outside=(~inside)&(peaks|(abs(hh)>3*sigma[i]+.3))
                for mask,sname,hname in [(inside,'s_in','h_in'),(outside,'s_out','h_out')]:
                    ids=np.flatnonzero(mask)
                    if len(ids):j=ids[np.argmax(ss[ids])];out[sname][i]=ss[j];out[hname][i]=hh[j]
        d=out['s_in'][i]-out['s_out'][i];out['difference'][i]=d
        for k,c in enumerate(cfg['judgments']['candidates']):
            if count[i]<3:judgments[i,k]=4
            elif np.isfinite(texture[i]) and texture[i]<5:judgments[i,k]=3
            elif d>=c['delta'] and out['s_in'][i]>=c['s_min']:judgments[i,k]=0
            elif d<=-c['delta'] and out['s_out'][i]>=c['s_min']:judgments[i,k]=1
    out['judgment']=judgments;out['peak_mask']=peakmask
    return out
