"""The inherited JPEG projection/pyramid with the exact regional training cameras."""
from common import *
from inherit import functions
import struct,zipfile,cv2
RAW=Path('/art/phase-payloads/p0-audit/data')
scope=dict(np=np,struct=struct,json=json,zipfile=zipfile,cv2=cv2,Path=Path,W=W,RAW=RAW)
poses,rotation,BaseCameras=functions('photo_cameras.py',['poses','rotation','Cameras'],scope)
class Cameras(BaseCameras):
    def __init__(self,site):
        self.site=site;f=S0/'fork_inputs/s61'/site
        split=json.loads((f/'split.json').read_text());self.names=sorted(split['train'])
        lines=[l for l in (RAW/'work/mvs/colmap_input_db_ids/cameras.txt').read_text().splitlines() if l and not l.startswith('#')]
        row=lines[0].split();assert len(lines)==1 and row[1]=='FULL_OPENCV';self.w,self.h=map(int,row[2:4]);self.p=np.array(row[4:],float)
        data={Path(k).stem:v for k,v in poses(f/'scene_LoD2/sparse/0/images.bin').items()}
        self.R=np.array([rotation(data[n][0]) for n in self.names]);self.t=np.array([data[n][1] for n in self.names]);self.centres=-np.einsum('nij,ni->nj',self.R,self.t)
        self.M=np.tile(np.eye(4,dtype='f4'),(len(self.names),1,1));self.M[:,:3,:3]=self.R;self.M[:,:3,3]=self.t
        cal=json.loads((f/'scene_LoD2/jbgs_calibration.json').read_text());self.Ks=[]
        for n in self.names:
            cc=cal['images'][n];assert (cc['width'],cc['height'])==(1024,741);k=np.array(cc['K']);f32=np.float32
            fx=float(f32(f32(512)*f32(2*k[0,0]/1024)));fy=float(f32(f32(741/2)*f32(2*k[1,1]/741)))
            cx=float(f32(f32(f32(512)*f32((2*k[0,2]+1-1024)/1024))+f32(1023/2)))
            cy=float(f32(f32(f32(741/2)*f32((2*k[1,2]+1-741)/741))+f32(740/2)))
            self.Ks.append(np.array([[fx,0,cx],[0,fy,cy],[0,0,1.]]))
        assert all(np.array_equal(k,self.Ks[0]) for k in self.Ks);self.K=self.Ks[0]
        inv={Path(r['name']).stem:r['original_zip_member'] for r in json.loads((W/'inputs/image_inventory.json').read_text())['rows']}
        self.members=[inv[n] for n in self.names];self.archive=None
    def depth(self,j):
        p=S0/'s61/export'/self.site/'LoD2/mvs'/f'{self.names[j]}.npy';cp=p.parent.parent/'conf'/p.name
        d=np.load(p).astype(float);c=np.load(cp);return np.where((c>0)&np.isfinite(d)&(d>0),d,np.nan)
    def sight_cameras(self):return [dict(name=n,W=1024,H=741,K=self.K,W2C=self.M[i]) for i,n in enumerate(self.names)]
