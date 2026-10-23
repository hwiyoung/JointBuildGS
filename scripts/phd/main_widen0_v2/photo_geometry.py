"""Original-resolution FULL_OPENCV projection, with verified camera-pose lineage."""
import json
from pathlib import Path
import numpy as np
from preflight import images,DENSE,dump,sha
from image_inventory import rotation
ROOT=Path('/art/phase-payloads/p0-audit/data/work/mvs/colmap_input_db_ids')
def calibration():
    lines=[x for x in (ROOT/'cameras.txt').read_text().splitlines() if x and not x.startswith('#')]
    assert len(lines)==1
    v=lines[0].split();assert v[1]=='FULL_OPENCV'
    return int(v[2]),int(v[3]),np.array(v[4:],float)
def project(X,q,t,p):
    Q=X@rotation(q).T+t;z=Q[:,2];x=Q[:,0]/z;y=Q[:,1]/z
    fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=p;r2=x*x+y*y
    radial=(1+k1*r2+k2*r2**2+k3*r2**3)/(1+k4*r2+k5*r2**2+k6*r2**3)
    xd=x*radial+2*p1*x*y+p2*(r2+2*x*x);yd=y*radial+p1*(r2+2*y*y)+2*p2*x*y
    return np.column_stack([fx*xd+cx,fy*yd+cy]),z
def verify():
    target=images(DENSE/'sparse/images.bin');src={};lines=(ROOT/'images.txt').read_text().splitlines();i=0
    while i<len(lines):
        ln=lines[i];i+=1
        if not ln or ln.startswith('#'):continue
        v=ln.split();src[v[9]]=dict(q=np.array(v[1:5],float),t=np.array(v[5:8],float));i+=1
    diffs=[]
    for name,v in target.items():
        assert name in src;diffs.append(max(np.max(np.abs(src[name]['q']-v['q'])),np.max(np.abs(src[name]['t']-v['t']))))
    assert max(diffs)<1e-7,max(diffs)
    w,h,p=calibration();x=np.array([[1.,2,10],[-2,1,5.]])
    # Validate rational distortion against OpenCV using the same documented coefficients.
    import cv2
    uv,z=project(x,[1,0,0,0],np.zeros(3),p);K=np.array([[p[0],0,p[2]],[0,p[1],p[3]],[0,0,1.]])
    check,_=cv2.projectPoints(x,np.zeros(3),np.zeros(3),K,p[4:])
    assert np.allclose(uv,check.reshape(-1,2),atol=1e-9)
    # A text/binary pose difference is retained rather than labelled byte equality.
    ground=np.array([[a,b,-50.] for a in [-100.,0.,100.] for b in [-100.,0.,100.]])
    pixel=[]
    for name,v in target.items():
        u,z=project(ground,v['q'],v['t'],p);u0,z0=project(ground,src[name]['q'],src[name]['t'],p)
        m=(z>0)&(u[:,0]>=0)&(u[:,0]<w)&(u[:,1]>=0)&(u[:,1]<h)
        if m.any():pixel.append(float(np.max(np.abs(u[m]-u0[m]))))
    assert pixel and max(pixel)<.001,max(pixel)
    dump(Path('/out/gates/photo_geometry.json'),dict(status='PASS',images=len(target),max_pose_difference=max(diffs),sampled_in_frame_projection_difference_px=max(pixel),camera_model='FULL_OPENCV',width=w,height=h,
        calibration_sha256=sha(ROOT/'cameras.txt'),pose_sha256=sha(ROOT/'images.txt'),opencv_max_pixel_difference=float(np.max(np.abs(uv-check.reshape(-1,2)))),scientific_verdict=None))
    print('original photo calibration and poses PASS',len(target),flush=True)
if __name__=='__main__':verify()
