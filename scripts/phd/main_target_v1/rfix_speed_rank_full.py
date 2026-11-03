"""Repeat two saved-state gradient checks with an exact global row ranking."""
from concurrent.futures import ThreadPoolExecutor
import sys
import numpy as np
POOL=ThreadPoolExecutor(max_workers=4)

def differences(a,b,c):
 assert a.shape==b.shape==c.shape
 def chunk(start):
  x,y,z=[v[start:start+65536].reshape(len(v[start:start+65536]),-1) for v in [a,b,c]]
  finite=bool(np.array_equal(np.isfinite(x),np.isfinite(y)) and np.array_equal(np.isfinite(x),np.isfinite(z)))
  mask=np.isfinite(x)&np.isfinite(y)&np.isfinite(z);xx=np.where(mask,x,0).astype('f8');yb=np.where(mask,y,0);zc=np.where(mask,z,0)
  da=abs(xx-yb);dc=abs(xx-zc);rd=dc.max(axis=1);ids=np.arange(start,start+len(rd));order=np.lexsort((ids,-rd))[:65]
  return float(da.max()),float(dc.max()),float((xx*xx).sum()),float((dc*dc).sum()),int((rd>0).sum()),[(float(rd[i]),int(ids[i])) for i in order if rd[i]>0],finite
 jitter=delta=nl2=dl2=0.;count=0;worst=[];finite_ok=True
 for ji,de,n,d,ct,top,finite in POOL.map(chunk,range(0,len(a),65536)):
  jitter=max(jitter,ji);delta=max(delta,de);nl2+=n;dl2+=d;count+=ct;worst.extend(top);finite_ok &= finite
 worst.sort(key=lambda v:(-v[0],v[1]));rel=(dl2/max(nl2,1e-300))**.5
 return dict(jitter_max_abs=jitter,fixed_max_abs=delta,relative_l2=rel,different_rows=count,nonfinite_masks_equal=finite_ok,pass_=finite_ok and rel<=1e-4,historical_jitter_pass=finite_ok and delta<=jitter,worst_rows=worst[:64],first_omitted_row=worst[64] if len(worst)>64 else None,ranking='exact global64: every chunk supplies65; delta descending, row ascending')

def main():
 from common import OUT,CFG,json,sha,dump,stamp
 if sys.argv[1]=='--unit':
  n=140000;a=np.zeros((n,2),'f4');b=a.copy();c=a.copy();c[100:200,0]=np.arange(100,0,-1);c[70000:70100,0]=50
  result=differences(a,b,c);rd=abs(c.astype('f8')).max(1);ids=np.arange(n);expected=np.lexsort((ids,-rd))[:65]
  assert result['worst_rows']==[(float(rd[i]),int(i)) for i in expected[:64]]
  assert result['first_omitted_row']==(float(rd[expected[64]]),int(expected[64]))
  dump(OUT/'rfix_speed/rank_refinement/unit.json',dict(at=stamp(),status='PASS',rows=n,case='more than64 extremes in one chunk, cross-chunk ties, exact full-array reference',scientific_verdict=None));return
 import rfix_gradient as G
 from rfix_speed_measure import speed
 cfg=json.loads((CFG/'rfix_speed_rank_full.json').read_text());assert sys.argv[1] in cfg['states']
 for p,h in json.loads((CFG/'rfix_speed_rank_full.lock.json').read_text())['files'].items():assert sha(p)==h,p
 G.ROOT=OUT/'rfix_speed/rank_refinement';G.extension=speed;G.differences=differences;G.main()
if __name__=='__main__':main()
