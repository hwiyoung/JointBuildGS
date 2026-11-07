"""Brute-force checks for the two display-ID queries; not scientific rescoring."""
from add10_common import *

def main():
 rng=np.random.default_rng(10);P=rng.uniform(-5,5,(1024,3));N=rng.normal(size=P.shape);N/=np.linalg.norm(N,axis=1)[:,None];Q=rng.uniform(-5,5,(100,3));U=rng.normal(size=Q.shape);U/=np.linalg.norm(U,axis=1)[:,None];index=ReferenceIndex(P,N)
 got,dist=index.query('assign_rows',Q,U,.3);expected=[]
 for q,n in zip(Q,U):
  delta=P-q;ax=delta@n;side=np.linalg.norm(delta-ax[:,None]*n,axis=1);ids=np.flatnonzero(side<=.3);order=np.lexsort((ids,abs(ax[ids]),side[ids]));expected.append(int(ids[order[0]]) if len(ids) else -1)
 assert np.array_equal(got,expected)
 got,depth=index.query('disc_rows',Q,U,.3);expected=[];ranges=[]
 for q,n in zip(Q,U):
  den=N@n;t=np.einsum('ij,ij->i',P-q,N)/den;delta=q+t[:,None]*n-P;ok=(abs(den)>1e-12)&(t>0)&(np.linalg.norm(delta,axis=1)<=.3);ids=np.flatnonzero(ok);i=int(ids[np.argmin(t[ids])]) if len(ids) else -1;expected.append(i);ranges.append(t[i] if i>=0 else np.inf)
 assert np.array_equal(got,expected);assert np.allclose(depth,ranges);index.close()
 # A distant but better aligned row must beat the nearest point in 3D.
 P=np.array([[.1,0,0],[.01,0,1000],[0,0,-1000.]]);N=np.tile([0.,0.,1.],(3,1));index=ReferenceIndex(P,N);idx,dist=index.query('assign_rows',[[0,0,0]],[[0,0,1]],.3);assert idx[0]==2;index.close()
 dump(W10/'geometry_verification.json',record(dict(status='PASS',random_points=1024,random_queries_each=100,brute_force_cylinder_match=True,brute_force_discs_match=True,unbounded_axis_counterexample_pass=True),[Path(__file__),Path(__file__).with_name('add10_geometry.cpp')]));print('ADD10_GEOMETRY_PASS',flush=True)

if __name__=='__main__':main()
