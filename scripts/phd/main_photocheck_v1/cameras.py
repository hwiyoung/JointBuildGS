"""Fixed training cameras and CPU visibility. No GT or evaluation camera inputs."""
import sys,io,zipfile,uuid
import cv2
from common import *
sys.path.insert(0,'/repo/scripts/phd/main_widen0_v2')
from preflight import images
from image_inventory import rotation
from photo_geometry import calibration

class Cameras:
    def __init__(self):
        self.names=sorted(load(W/'image_split.json')['train']);self.w,self.h,self.p=calibration()
        poses=images(DENSE/'sparse/images.bin');self.R=np.array([rotation(poses[n]['q']) for n in self.names]);self.t=np.array([poses[n]['t'] for n in self.names])
        self.centres=-np.einsum('nij,ni->nj',self.R,self.t)
        ir={r['name']:r for r in load(W/'inputs/image_inventory.json')['rows']};self.members=[ir[n]['original_zip_member'] for n in self.names]
        self.archive=None
    def project(self,X,j):
        Q=X@self.R[j].T+self.t[j];z=Q[...,2];x=Q[...,0]/z;y=Q[...,1]/z
        fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=self.p;r=x*x+y*y
        radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3)
        pin=np.stack([fx*x+cx,fy*y+cy],-1)
        uv=np.stack([fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx,fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy],-1)
        valid=(z>0)&np.isfinite(uv).all(-1)&(pin[...,0]>=-200)&(pin[...,0]<=self.w+200)&(pin[...,1]>=-200)&(pin[...,1]<=self.h+200)&(np.linalg.norm(uv-pin,axis=-1)<400)
        return uv,z,valid
    def rgb(self,j):
        if self.archive is None:self.archive=zipfile.ZipFile(RAW/'raw/uav/Images.zip')
        image=cv2.imdecode(np.frombuffer(self.archive.read(self.members[j]),np.uint8),cv2.IMREAD_COLOR)
        assert image.shape[:2]==(self.h,self.w)
        return cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
    def gray(self,j,level):
        folder=O/'image_cache';folder.mkdir(exist_ok=True);path=folder/f'{j:04d}_L{level}.npy'
        if not path.exists():
            # Image-at-a-time processing; original RGB is released before next image.
            im=self.rgb(j);gray=cv2.transform(im.astype(np.float32),np.array([[.299,.587,.114]],np.float32));del im
            for _ in range(level):gray=cv2.resize(gray,(gray.shape[1]//2,gray.shape[0]//2),interpolation=cv2.INTER_AREA)
            temporary=folder/f'.{path.stem}_{uuid.uuid4().hex}.npy'
            np.save(temporary,gray);temporary.replace(path)
        return np.load(path,mmap_mode='r')

def mesh_scene(tile,prior):
    import open3d as o3d
    md=W/'holdout/internal/prior_tiles'/tile
    m=npz(md/('lod2_mesh.npz' if prior=='LoD2' else 'als_mesh.npz'))
    shift=np.array(load(W/'holdout/internal/registration'/tile/prior/'summary.json')['registration']['shift_applied'])
    scene=o3d.t.geometry.RaycastingScene(nthreads=8)
    scene.add_triangles(o3d.core.Tensor((m['V']+shift).astype(np.float32)),o3d.core.Tensor(m['F'].astype(np.uint32)))
    return scene

def select_photos(g,cam,tile,prior):
    import open3d as o3d
    n=len(g['centre']);ok=np.zeros((n,len(cam.names)),bool);c=g['centre'];scene=mesh_scene(tile,prior)
    corners=c[:,None,:]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,0,None]*.25*g['tangent1'][:,None,:]+np.array([[-1,-1],[1,-1],[1,1],[-1,1]])[None,:,1,None]*.25*g['tangent2'][:,None,:]
    for j in range(len(cam.names)):
        v=cam.centres[j]-c;distance=np.linalg.norm(v,axis=1);v/=distance[:,None]
        possible=g['geometry_valid']&(np.einsum('ij,ij->i',v,g['normal'])>=.5)
        ids=np.flatnonzero(possible)
        if not len(ids):continue
        uv,_,guard=cam.project(corners[ids],j)
        valid=guard.all(1)&(uv[:,:,0]>=20).all(1)&(uv[:,:,0]<cam.w-20).all(1)&(uv[:,:,1]>=20).all(1)&(uv[:,:,1]<cam.h-20).all(1)
        ids=ids[valid]
        if not len(ids):continue
        uv,_,guard=cam.project(c[ids],j);ids=ids[guard]
        rays=np.c_[np.broadcast_to(cam.centres[j],(len(ids),3)),-v[ids]].astype(np.float32)
        depth=scene.cast_rays(o3d.core.Tensor(rays),nthreads=8)['t_hit'].numpy()
        ok[ids,j]=distance[ids]<=depth+.3
    selected=np.full((n,10),-1,np.int32);eligible=ok.sum(1).astype(np.int32);count=np.minimum(eligible,10).astype(np.int8)
    maxangle=np.zeros(n,np.float32);parallax=np.zeros(n,np.float32)
    for i in range(n):
        choices=np.flatnonzero(ok[i]);
        if not len(choices):continue
        v=cam.centres[choices]-c[i];v/=np.linalg.norm(v,axis=1,keepdims=True)
        incidence=v@g['normal'][i];pick=[int(np.argmax(incidence))];similarity=v@v[pick[0]];similarity[pick]=np.inf
        for _ in range(min(len(choices),10)-1):
            q=int(np.argmin(similarity));pick.append(q);similarity=np.maximum(similarity,v@v[q]);similarity[pick]=np.inf
        selected[i,:len(pick)]=choices[pick];vv=v[pick]
        maxangle[i]=np.degrees(np.arccos(np.clip(np.min(vv@vv.T),-1,1)))
        dn=-vv;dot=dn@g['normal'][i];o=(dn-dot[:,None]*g['normal'][i])/np.abs(dot[:,None]);parallax[i]=np.max(np.linalg.norm(o[:,None]-o[None,:],axis=-1))
    return dict(selected_images=selected,eligible_images=eligible,selected_count=count,max_direction_angle_deg=maxangle,parallax=parallax)
