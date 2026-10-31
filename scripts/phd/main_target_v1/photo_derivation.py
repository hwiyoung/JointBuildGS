"""Verbatim CANDPICK-v2 derive function; only config lookup is task-local."""
import numpy as np
from common import REPO,json

def config():
    source=REPO/'configs/phd/main_photocheck_v1/photocheck_v1.json'
    return {'photo':{'inherited_judgments':json.loads(source.read_text())['judgments']}}

def derive(p,bound):
    """Only the support interval changes. Preserve original range-independent peaks."""
    h=p['heights'];s=p['curve'].astype(np.float32);good=np.isfinite(h)&np.isfinite(s)
    inside=good&(np.abs(h)<=(bound+1e-8).astype(h.dtype)[:,None])
    outside=good&~inside&(p['peak_mask']|(np.abs(h)>(bound+.3).astype(h.dtype)[:,None]))
    outside&=np.isfinite(bound)[:,None]
    result={}
    for label,mask in [('in',inside),('out',outside)]:
        score=np.max(np.where(mask,s,-np.inf),axis=1)
        height=np.min(np.where(mask&(s==score[:,None]),h,np.inf),axis=1)
        score[~np.isfinite(score)]=np.nan;height[~np.isfinite(height)]=np.nan
        result['s_'+label]=score;result['h_'+label]=height
    difference=result['s_in']-result['s_out'];j=np.full((len(h),15),2,np.int8)
    for k,c in enumerate(config()['photo']['inherited_judgments']['candidates']):
        support=(difference>=c['delta'])&(result['s_in']>=c['s_min'])
        contradict=(difference<=-c['delta'])&(result['s_out']>=c['s_min'])
        j[support,k]=0;j[contradict,k]=1
        j[np.isfinite(p['texture'])&(p['texture']<5),k]=3
        j[p['selected_count']<3,k]=4
    result.update(difference=difference,judgment=j)
    return result

