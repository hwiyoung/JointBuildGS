"""Frozen train cameras. Image/depth reads are batched by camera."""
import json,struct,zipfile
from pathlib import Path
import numpy as np
import cv2
W=Path('/art/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2')
RAW=Path('/art/phase-payloads/p0-audit/data')

def poses(path):
    out={}
    with path.open('rb') as f:
        count,=struct.unpack('<Q',f.read(8))
        for _ in range(count):
            iid,=struct.unpack('<i',f.read(4));q=struct.unpack('<4d',f.read(32));t=struct.unpack('<3d',f.read(24));cid,=struct.unpack('<i',f.read(4));name=bytearray()
            while True:
                c=f.read(1)
                if c==b'\0':break
                if not c:raise ValueError('truncated pose')
                name.extend(c)
            n,=struct.unpack('<Q',f.read(8));f.seek(n*24,1);out[name.decode()]=(q,t)
    return out

def rotation(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
        [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
        [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

def read_depth(path):
    raw=path.read_bytes();end=0
    for _ in range(3):end=raw.find(b'&',end,100)+1
    w,h,c=map(int,raw[:end].split(b'&')[:3]);assert c==1
    return np.frombuffer(raw,dtype='<f4',offset=end,count=w*h).reshape((w,h),order='F').T

class Cameras:
    def __init__(self):
        split=json.loads((W/'image_split.json').read_text());self.names=sorted(split['train']);assert not set(self.names)&set(split['evaluation'])
        lines=[l for l in (RAW/'work/mvs/colmap_input_db_ids/cameras.txt').read_text().splitlines() if l and not l.startswith('#')]
        row=lines[0].split();assert len(lines)==1 and row[1]=='FULL_OPENCV';self.w,self.h=map(int,row[2:4]);self.p=np.array(row[4:],float)
        old=poses(RAW/'work/mvs/colmap_dense/sparse/images.bin');new=poses(W/'mvs/full/sparse/images.bin')
        self.R=np.array([rotation(old[n][0]) for n in self.names]);self.t=np.array([old[n][1] for n in self.names]);self.centres=-np.einsum('nij,ni->nj',self.R,self.t)
        self.M=np.tile(np.eye(4,dtype='f4'),(len(self.names),1,1))
        for j,n in enumerate(self.names):
            assert np.allclose(old[n][0],new[n][0],atol=1e-7,rtol=0) and np.allclose(old[n][1],new[n][1],atol=1e-7,rtol=0)
            self.M[j,:3,:3]=rotation(new[n][0]);self.M[j,:3,3]=new[n][1]
        with (W/'mvs/full/sparse/cameras.bin').open('rb') as f:
            nc,=struct.unpack('<Q',f.read(8));cid,model,iw,ih=struct.unpack('<iiQQ',f.read(24));assert nc==1 and model==1
            params=np.array(struct.unpack('<4d',f.read(32)))*[1024/iw,741/ih,1024/iw,741/ih]
        fx,fy,cx,cy=params;cx-=.5;cy-=.5;f32=np.float32
        fx=float(f32(f32(512)*f32(2*fx/1024)));fy=float(f32(f32(741/2)*f32(2*fy/741)))
        cx=float(f32(f32(f32(512)*f32((2*cx+1-1024)/1024))+f32(1023/2)))
        cy=float(f32(f32(f32(741/2)*f32((2*cy+1-741)/741))+f32(740/2)))
        self.K=np.array([[fx,0,cx],[0,fy,cy],[0,0,1]])
        inv={r['name']:r['original_zip_member'] for r in json.loads((W/'inputs/image_inventory.json').read_text())['rows']}
        self.members=[inv[n] for n in self.names];self.archive=None
    def project(self,X,j):
        Q=X@self.R[j].T+self.t[j];z=Q[...,2]
        with np.errstate(divide='ignore',invalid='ignore',over='ignore'):
            x=Q[...,0]/z;y=Q[...,1]/z;fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=self.p;r=x*x+y*y
            radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
            pin=np.stack([fx*x+cx,fy*y+cy],-1)
            uv=np.stack([fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx,fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy],-1)
        valid=(z>0)&np.isfinite(uv).all(-1)&(pin[...,0]>=-200)&(pin[...,0]<=self.w+200)&(pin[...,1]>=-200)&(pin[...,1]<=self.h+200)&(np.linalg.norm(uv-pin,axis=-1)<400)
        return uv,z,valid
    def depth(self,j):
        path=W/'mvs/full/stereo/depth_maps'/f'{self.names[j]}.geometric.bin'
        return read_depth(path) if path.exists() else None
    def gray_pyramid(self,j,levels):
        if self.archive is None:self.archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip')
        im=cv2.imdecode(np.frombuffer(self.archive.read(self.members[j]),np.uint8),cv2.IMREAD_COLOR)
        assert im.shape[:2]==(self.h,self.w)
        im=cv2.cvtColor(im,cv2.COLOR_BGR2RGB);gray=cv2.transform(im.astype(np.float32),np.array([[.299,.587,.114]],np.float32));del im
        out={}
        for level in range(max(levels)+1):
            if level in levels:out[level]=gray
            if level<max(levels):gray=cv2.resize(gray,(gray.shape[1]//2,gray.shape[0]//2),interpolation=cv2.INTER_AREA)
        return out

def choose_mvs_views(centres,normals,t1,t2,cam,valid):
    N=len(centres);ok=np.zeros((N,len(cam.names)),bool);corners=np.array([[-.25,-.25],[.25,-.25],[.25,.25],[-.25,.25]])
    X=centres[:,None]+corners[None,:,0,None]*t1[:,None]+corners[None,:,1,None]*t2[:,None]
    for j in range(len(cam.names)):
        v=cam.centres[j]-centres;dist=np.linalg.norm(v,axis=1);v/=dist[:,None]
        ix=np.flatnonzero(valid&(np.einsum('ij,ij->i',v,normals)>=.5))
        if not len(ix):continue
        uv,z,guard=cam.project(X[ix],j);good=guard.all(1)&(uv[:,:,0]>=20).all(1)&(uv[:,:,0]<cam.w-20).all(1)&(uv[:,:,1]>=20).all(1)&(uv[:,:,1]<cam.h-20).all(1)
        ix=ix[good]
        if not len(ix):continue
        q=centres[ix]@cam.M[j,:3,:3].T+cam.M[j,:3,3];z=q[:,2]
        uv=q[:,:2]/z[:,None]*[cam.K[0,0],cam.K[1,1]]+[cam.K[0,2],cam.K[1,2]]
        inside=(z>0)&np.isfinite(uv).all(1)&(uv[:,0]>=0)&(uv[:,0]<1024)&(uv[:,1]>=0)&(uv[:,1]<741);ix=ix[inside];q=q[inside];uv=uv[inside];z=z[inside]
        if not len(ix):continue
        dep=cam.depth(j)
        if dep is None:continue
        px=np.rint(uv).astype(int);good=(px[:,0]<1024)&(px[:,1]<741);ix=ix[good];px=px[good];q=q[good];z=z[good]
        dd=dep[px[:,1],px[:,0]];distance=np.linalg.norm(q,axis=1)
        # COLMAP stores axial Z; compare Euclidean range after conversion.
        visible=np.isfinite(dd)&(dd>0)&(distance<=dd*distance/z+.3);ok[ix[visible],j]=True
    selected=np.full((N,10),-1,np.int32)
    for i in range(N):
        choices=np.flatnonzero(ok[i])
        if not len(choices):continue
        v=cam.centres[choices]-centres[i];v/=np.linalg.norm(v,axis=1)[:,None];pick=[int(np.argmax(v@normals[i]))];sim=v@v[pick[0]];sim[pick]=np.inf
        for _ in range(min(len(choices),10)-1):
            k=int(np.argmin(sim));pick.append(k);sim=np.maximum(sim,v@v[k]);sim[pick]=np.inf
        selected[i,:len(pick)]=choices[pick]
    return selected
