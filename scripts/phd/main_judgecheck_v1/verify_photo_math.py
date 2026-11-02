"""Independent pairwise NCC and projected polygon checks before benchmark."""
import numpy as np
import torch
from photo_score import ncc_vectors,project
from photo_planes import in_triangles,fit_mvs
from photo_cameras import Cameras
from scipy.spatial import cKDTree
from preflight import C,O,Path,dump,sha,now

def main():
    rng=np.random.default_rng(20261102);checks=[]
    for pixels in [313,400,625]:
        x=rng.normal(size=(5,625)).astype('f4');mask=np.zeros((5,625),bool);mask[:,:pixels]=True
        v,sd,n=ncc_vectors(torch.tensor(x),torch.tensor(mask));agg=((v.sum(0)**2).sum()-(v**2).sum())/20
        direct=np.mean([np.corrcoef(x[i,:pixels],x[j,:pixels])[0,1] for i in range(5) for j in range(i)])
        assert abs(float(agg)-direct)<2e-7;checks.append(dict(test='pairwise_ncc',pixels=pixels,error=abs(float(agg)-direct)))
    tri=np.array([[[0,0,0],[1,0,0],[1,1,0]],[[0,0,0],[1,1,0],[0,1,0]]],float)
    inside=in_triangles(np.array([[.5,.5,.8],[1.1,.5,0],[0,0,0]]),tri,np.zeros(3),np.array([1,0,0]),np.array([0,1,0]))
    assert inside.tolist()==[True,False,True];checks.append(dict(test='surface_union_and_normal_shift',pass_=True))
    cam=Cameras();X=cam.centres[0]+np.array([[0,0,-40],[1,2,-40],[2,-1,-40]])
    uv,z,valid=cam.project(X,0);u,v,g=project(torch.tensor(X),torch.tensor(cam.R[0]),torch.tensor(cam.t[0]),torch.tensor(cam.p),cam.w,cam.h)
    assert np.allclose(np.c_[u.numpy(),v.numpy()],uv,atol=1e-8,rtol=0);assert np.array_equal(g.numpy(),valid)
    checks.append(dict(test='native_camera_numpy_torch_parity',pass_=True,cameras=len(cam.names)))
    q=rng.uniform(-.4,.4,(1000,3));q[:,2]=.15+.1*q[:,0]+rng.normal(0,.001,len(q));p,meta=fit_mvs(q,cKDTree(q),np.zeros(3),np.array([0,0,1.]),0,.15)
    assert p is not None and abs(p[0][2]-.15)<.002 and meta['point_count']>=20
    checks.append(dict(test='tilted_plane_axis_intersection',height_m=float(p[0][2]),pass_=True))
    dump(O/'r1/photo_benchmark/math_verification.json',dict(at=now(),status='PASS',checks=checks,source_sha256=sha(Path(__file__)),scientific_verdict=None))
    print('PASS_PHOTO_MATH',len(checks))

if __name__=='__main__':main()
