"""Addendum 10: export saved scores, render geometry and reference IDs only."""
from add9_common import *
import gzip
import copy
import ctypes
import subprocess
from add4_render import rays as perspective_rays

W10=O/'addendum10';F10=D/'figures/addendum10';T10=D/'tables/addendum10'
for folder in [W10,F10,T10]:folder.mkdir(parents=True,exist_ok=True)
A10=json.loads((C/'addendum10.json').read_text())
assert sha(C/'addendum10.json')==json.loads((C/'addendum10.lock.json').read_text())['config_sha256']

def proof(p):
 p=Path(p);q=W10/'hashes'/(hashlib.sha256(str(p).encode()).hexdigest()+'.json');st=stamp(p);old=json.loads(q.read_text()) if q.exists() else {}
 if old.get('stat')!=st:old=dict(path=str(p),sha256=sha(p),stat=st);dump(q,old)
 return {k:old[k] for k in ['path','sha256']}

def record(meta,sources=()):
 return dict(at=now(),scientific_verdict=None,crs='EPSG:25832',local_world_shift=SHIFT.tolist(),config_sha256=sha(C/'addendum10.json'),sources=[proof(p) for p in dict.fromkeys(map(str,sources))],runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),**meta)

def camera_jobs(key):
 c=case(key);f8=D/'figures/addendum8';method={'c1':'prior','c2':'prior','c3':'mvs','c4':'FINALTRAIN_30000'}[key];p=f8/(c['id']+'_'+method+'_dist_shaded.json');old=json.loads(p.read_text());assert not old.get('removed_original_triangle_ids') and not old['camera'].get('display_clip')
 cam=copy.deepcopy(old['camera']);cam['projection']='perspective';out=[dict(id='b_render' if key=='c3' else 'a_render',camera=cam,source=str(p),matched_image=str(p.with_suffix('.png')))]
 if key=='c3':
  p=F9/'c3_closeup_photo.json';base=json.loads(p.read_text())['camera']
  for scale in [1,2]:
   cam=copy.deepcopy(base);cam['output_size_px']=[804*scale,1072*scale];cam['projection']='perspective';out.insert(scale-1,dict(id='a_closeup'+('_2x' if scale==2 else ''),camera=cam,source=str(p),matched_image=str(p.with_suffix('.png'))))
 else:
  p=F6/(c['id']+'_top_crop_noline.json');old=json.loads(p.read_text());row,_=data(c);height=float(row['xyz'][:,2].max()+100)
  cam=dict(name=key+'_top_orthographic',projection='orthographic',bounds_uv=old['bounds_uv'],output_size_px=old['size_px'],origin_z_m=height,direction_unit_xyz=[0.,0.,-1.],uv_basis=BASIS.tolist(),pixel_origin='top-left; u and v increase right and down as inherited raster')
  out.append(dict(id='b_top',camera=cam,source=str(p),matched_image=str(p.with_suffix('.png'))))
  if key=='c4':
   p=F6/(c['id']+'_oblique_noline.json');cam=copy.deepcopy(json.loads(p.read_text())['camera']);cam['projection']='perspective';out.append(dict(id='c_photo',camera=cam,source=str(p),matched_image=str(p.with_suffix('.png'))))
 return out

def ray_rows(cam,y0,y1):
 W,H=cam['output_size_px']
 if cam['projection']=='orthographic':
  b=cam['bounds_uv'];xx,yy=np.meshgrid(b[0]+(np.arange(W)+.5)*(b[1]-b[0])/W,b[2]+(np.arange(y0,y1)+.5)*(b[3]-b[2])/H);xy=uvxy(np.c_[xx.ravel(),yy.ravel()]);origin=np.c_[xy,np.full(len(xy),cam['origin_z_m'])];direction=np.tile([0.,0.,-1.],(len(xy),1))
 else:
  rr,direction=perspective_rays(cam,y0,y1);origin=rr[:,:3].astype(float);direction/=np.linalg.norm(direction,axis=1)[:,None]
 return origin,direction

def project(P,cam):
 if cam['projection']=='orthographic':return pixels(xyuv(P),cam['bounds_uv'],cam['output_size_px']),cam['origin_z_m']-P[:,2]
 return camera_projection(P,cam)

class ReferenceIndex:
 def __init__(self,points,normals):
  self.points=np.ascontiguousarray(points,'f8');self.normals=np.ascontiguousarray(normals,'f8');source=Path(__file__).with_name('add10_geometry.cpp');lib=W10/('geometry_'+sha(source)[:16]+'.so')
  if not lib.exists():subprocess.run(['g++','-O3','-std=c++17','-fopenmp','-shared','-fPIC',str(source),'-o',str(lib)],check=True)
  self.lib=ctypes.CDLL(str(lib));self.lib.build.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int];self.lib.build.restype=ctypes.c_void_p;self.lib.destroy.argtypes=[ctypes.c_void_p]
  for name in ['assign_rows','disc_rows']:getattr(self.lib,name).argtypes=[ctypes.c_void_p]*3+[ctypes.c_int,ctypes.c_double,ctypes.c_void_p,ctypes.c_void_p]
  self.tree=self.lib.build(self.points.ctypes.data,self.normals.ctypes.data,len(points))
 def query(self,name,p,n,radius):
  p=np.ascontiguousarray(p,'f8');n=np.ascontiguousarray(n,'f8');idx=np.full(len(p),-1,'i4');distance=np.full(len(p),np.inf)
  getattr(self.lib,name)(self.tree,p.ctypes.data,n.ctypes.data,len(p),radius,idx.ctypes.data,distance.ctypes.data)
  return idx,distance
 def close(self):self.lib.destroy(self.tree)

def stored_scores(c):
 out={}
 for p in sorted((root_of(c)/'distances').glob('*.npz')):
  if p.with_suffix('.json').exists():out[p.stem]=p
 for p in sorted((AW/'keep_scores'/f"{c['site']}__{c['prior']}").glob('*.npz')):out[p.stem]=p
 return out

def strip_coord(P):
 s=selected(case('c3'))['section'];dr=(np.array(s['end'])-s['start'])/s['length_m'];delta=np.asarray(P)[:,:2]-s['start'];return delta@dr,delta@np.array([-dr[1],dr[0]])
