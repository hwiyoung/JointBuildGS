"""Identical ordered CPU gradient reductions, four independent chunks at a time."""
import sys,time
from concurrent.futures import ThreadPoolExecutor
import rfix_gradient as G
from common import *
import numpy as np
POOL=ThreadPoolExecutor(max_workers=4)
def differences(a,b,c):
 assert a.shape==b.shape==c.shape
 def chunk(start):
  x,y,z=[v[start:start+65536].reshape(len(v[start:start+65536]),-1) for v in [a,b,c]];finite=bool(np.array_equal(np.isfinite(x),np.isfinite(y)) and np.array_equal(np.isfinite(x),np.isfinite(z)));mask=np.isfinite(x)&np.isfinite(y)&np.isfinite(z);xx=np.where(mask,x,0).astype('f8');yb=np.where(mask,y,0);zc=np.where(mask,z,0);da=abs(xx-yb);dc=abs(xx-zc);rowdelta=dc.max(axis=1);take=np.argsort(rowdelta)[-8:];return (float(da.max()),float(dc.max()),float((xx*xx).sum()),float((dc*dc).sum()),int((rowdelta>0).sum()),[(float(rowdelta[i]),int(start+i)) for i in take if rowdelta[i]>0],finite)
 jitter=delta=nl2=dl2=0.;different_rows=0;worst=[];finite_ok=True
 for ji,de,n,d,count,top,finite in POOL.map(chunk,range(0,len(a),65536)):
  jitter=max(jitter,ji);delta=max(delta,de);nl2+=n;dl2+=d;different_rows+=count;worst.extend(top);finite_ok &= finite
 return dict(jitter_max_abs=jitter,fixed_max_abs=delta,relative_l2=(dl2/max(nl2,1e-300))**.5,different_rows=different_rows,nonfinite_masks_equal=finite_ok,pass_=finite_ok and delta<=jitter,worst_rows=sorted(worst,reverse=True)[:16])
def main():
 root=OUT/'rfix'
 if sys.argv[1]=='--verify':
  p=next((root/'gradients/r8_LoD2_stop').glob('*_differing_rows.npz'));z=np.load(p);rows=[]
  for name in ['_xyz','_features_dc','_features_rest','_scaling','_rotation','_opacity','viewspace_points']:
   arrays=[np.tile(z[v+'_'+name],(max(1,200000//len(z['ids'])),)+ (1,)*(z[v+'_'+name].ndim-1)) for v in ['original_a','original_b','fixed']];start=time.monotonic();old=G.differences(*arrays);ot=time.monotonic()-start;start=time.monotonic();new=differences(*arrays);nt=time.monotonic()-start;assert old==new,(name,old,new);rows.append(dict(parameter=name,rows=len(arrays[0]),exact_dictionary_equal=True,serial_seconds=ot,parallel_seconds=nt))
  dump(root/'gradient_parallel_verification.json',dict(at=stamp(),status='PASS',input=str(p),input_sha256=sha(p),wrapper_sha256=sha(__file__),original_sha256=sha(G.__file__),rows=rows,scientific_verdict=None));print('PARALLEL_REDUCTION_PASS',rows,flush=True)
 else:
  receipt=json.loads((root/'gradient_parallel_verification.json').read_text());assert receipt['status']=='PASS' and receipt['wrapper_sha256']==sha(__file__) and receipt['original_sha256']==sha(G.__file__)
  dump(root/'execution'/('gradient_parallel_'+sys.argv[1]+'.lock.json'),dict(at=stamp(),files={str(Path(__file__)):sha(__file__),str(Path(G.__file__)):sha(G.__file__)},workers=4,chunk_rows=65536,ordered_reduction=True,verification_sha256=sha(root/'gradient_parallel_verification.json'),scientific_verdict=None));G.differences=differences;G.main()
if __name__=='__main__':main()
