"""Task-local CPU geometry. COLMAP binary parsing adapted from main_stage0_v1/common.py;
projection/GT visibility conventions from main_photofig_v1/pf_geo.py and t_a_images.py.
No training/result reads. Native FULL_OPENCV projection retains original photo pixels.
"""
import datetime as dt
import hashlib
import json
import struct
import zipfile
from pathlib import Path
import numpy as np

PH = Path('/art/phase-payloads/phd')
S0 = PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
S1 = PH/'main_stage1_v1/PHD-MAIN-STAGE1-v1'
U = PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1'
DENSE = Path('/art/phase-payloads/p0-audit/data/work/mvs')
RAW = Path('/art/phase-payloads/p0-audit/data/raw/uav/Images.zip')
PAY = Path('/payload')
DOC = Path('/docs')
CFG = Path('/cfg')

def now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat()

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(4<<20),b''): h.update(b)
    return h.hexdigest()

def clean(x):
    if isinstance(x,dict): return {str(k):clean(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)): return [clean(v) for v in x]
    if isinstance(x,(np.floating,float)): return float(x) if np.isfinite(x) else None
    if isinstance(x,np.integer): return int(x)
    if isinstance(x,np.bool_): return bool(x)
    if isinstance(x,Path): return str(x)
    return x

def dump(p,x):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(clean(x),ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def load(p): return json.loads(Path(p).read_text())

def qR(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                     [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                     [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

def cameras(p):
    out={}
    with open(p,'rb') as f:
        for _ in range(struct.unpack('<Q',f.read(8))[0]):
            cid,m,w,h=struct.unpack('<iiQQ',f.read(24))
            n={0:3,1:4,2:4,3:5,4:8,5:8,6:12}[m]
            out[cid]=dict(model=m,w=w,h=h,p=np.array(struct.unpack('<'+'d'*n,f.read(8*n))))
    return out

def poses(p):
    out={}
    with open(p,'rb') as f:
        for _ in range(struct.unpack('<Q',f.read(8))[0]):
            iid=struct.unpack('<i',f.read(4))[0]
            q=np.array(struct.unpack('<dddd',f.read(32))); t=np.array(struct.unpack('<ddd',f.read(24)))
            cid=struct.unpack('<i',f.read(4))[0]; name=b''
            while True:
                b=f.read(1)
                if not b: raise ValueError('truncated images.bin')
                if b==b'\0': break
                name+=b
            n=struct.unpack('<Q',f.read(8))[0];f.seek(n*24,1)
            out[Path(name.decode()).stem]=dict(id=iid,R=qR(q),t=t,cam=cid,name=name.decode())
    return out

def project(X,pose,cam):
    x=np.asarray(X)@pose['R'].T+pose['t']; z=x[...,2]
    xy=x[...,:2]/z[...,None]; a,b=xy[...,0],xy[...,1]
    p=cam['p']; fx,fy,cx,cy=p[:4]
    if cam['model']==6:
        k1,k2,p1,p2,k3,k4,k5,k6=p[4:];r=a*a+b*b
        rad=(1+k1*r+k2*r*r+k3*r*r*r)/(1+k4*r+k5*r*r+k6*r*r*r)
        a,b=a*rad+2*p1*a*b+p2*(r+2*a*a),b*rad+p1*(r+2*b*b)+2*p2*a*b
    else: assert cam['model']==1
    return np.stack([fx*a+cx,fy*b+cy],-1),z

def tilt(pose): return float(np.degrees(np.arccos(np.clip(-pose['R'][2,2],-1,1))))

def gt_crop(path,start,end,pad):
    """Stream compressed NPY in bounded chunks; retain only section bounding box +10 m."""
    lo=np.minimum(start,end)-pad;hi=np.maximum(start,end)+pad; kept=[]; n=0
    with zipfile.ZipFile(path) as z, z.open('xyz.npy') as f:
        ver=np.lib.format.read_magic(f)
        shape,order,dtype=np.lib.format._read_array_header(f,ver)
        assert not order and len(shape)==2 and shape[1]==3
        for off in range(0,shape[0],100000):
            count=min(100000,shape[0]-off)
            raw=f.read(count*3*dtype.itemsize)
            x=np.frombuffer(raw,dtype=dtype).reshape(-1,3)
            m=np.all((x[:,:2]>=lo)&(x[:,:2]<=hi),axis=1)
            kept.append(x[m].astype(np.float64));n+=len(x)
    return np.concatenate(kept),dict(total=n,kept=sum(len(k) for k in kept),xy_min=lo,xy_max=hi)

def pv(ex):
    path=U/'patch_values'/f"{ex['site']}__{ex['prior']}__R1.5.npz"
    with np.load(path) as z:
        keys=['centre','normal','roof_like','in_eval','cell','gt_p','mvs_a_p','mvs_a_status','surf']
        return {k:z[k] for k in keys},path
