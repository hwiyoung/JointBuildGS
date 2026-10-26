"""Independent numerical checks of projection, NCC, and candidate decisions."""
import cv2
import torch
from common import *
from cameras import Cameras
from curves import project_torch,height_array
from features import derive

def main():
    cam=Cameras();rng=np.random.default_rng(20261026);K=np.array([[cam.p[0],0,cam.p[2]],[0,cam.p[1],cam.p[3]],[0,0,1.]])
    Q=np.c_[rng.uniform(-10,10,(100,2)),rng.uniform(40,80,100)];X=(Q-cam.t[0])@cam.R[0]
    expected,_=cv2.projectPoints(Q,np.zeros(3),np.zeros(3),K,cam.p[4:]);uv,_,_=cam.project(X,0)
    err=np.max(np.abs(expected.reshape(-1,2)-uv));assert err<1e-7
    u,v,_=project_torch(torch.tensor(X,dtype=torch.float32),torch.tensor(cam.R[0],dtype=torch.float32),torch.tensor(cam.t[0],dtype=torch.float32),torch.tensor(cam.p,dtype=torch.float32),cam.w,cam.h)
    err32=np.max(abs(np.c_[u.numpy(),v.numpy()]-uv));assert err32<.003
    ncc=[]
    for count in range(3,11):
        a=rng.normal(size=(count,625));a-=a.mean(1,keepdims=True);a/=np.linalg.norm(a,axis=1,keepdims=True)
        matrix=np.corrcoef(a);reference=matrix[np.triu_indices(count,1)].mean();equiv=((a.sum(0)**2).sum()-(a*a).sum())/(count*(count-1));ncc.append(abs(reference-equiv))
    assert max(ncc)<1e-12
    h=height_array(dict(centre=np.zeros((5,3)),mvs_p=np.array([0,0,0,0,7.])))
    assert np.isfinite(h).sum(1).tolist()==[141,141,141,141,148]
    score=np.exp(-((h-.0)/.05)**2);score[1]=np.exp(-((h[1]-1.2)/.05)**2)
    f=derive(h,score,np.ones(5)*.1,np.zeros(5),np.array([20,20,2,20,20]),np.array([5,5,5,2,5]))
    assert np.array_equal(f['judgment'][:4,4],[0,1,3,4])
    for k in range(15):assert f['judgment'][0,k]==0 and f['judgment'][1,k]==1
    # Float16 storage changes are bounded; classifications derive from float32 before serialization.
    dump(O/'gates/core.json',dict(status='PASS',opencv_max_error_px=err,float32_projection_max_error_px=err32,ncc_pairwise_max_error=max(ncc),synthetic_candidate_cases=60,environment=env()))
    print('core numerical checks PASS',err,err32,max(ncc))
if __name__=='__main__':main()
