"""Presentation-only bindings; no optimizer or inherited-output writes."""
import gc, io, json, hashlib, sys, zipfile
import numpy as np
from pathlib import Path
from common import *
from geometry_add1 import read_surface, section_segments, section_points, MeshScene
from scipy.spatial import cKDTree
from PIL import Image, ImageDraw, ImageCms

AC = json.loads((C/'addendum4.json').read_text())
assert sha(C/'addendum4.json') == json.loads((C/'addendum4.lock.json').read_text())['config_sha256']
AW = O/'addendum4'
AF = D/'figures/addendum4'
AT = D/'tables/addendum4'
for p in [AW, AF, AT]: p.mkdir(parents=True, exist_ok=True)
CH6 = PH/'ch6_support_v1/PHD-CH6-SUPPORT-v1/t3'
BOXFILE = PH/'main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1/step06/boxes_v1.json'
BOXES = json.loads(BOXFILE.read_text())['boxes']
BIDS = {'B0_b10':'B0','B173nb_b10':'B173nb','R1rep_b10':'R1rep'}
SHORT = {'B0_b10':'B0','B173nb_b10':'B173nb','R1rep_b10':'R1'}
angle = np.deg2rad(json.loads((R/'configs/phd/main_prep_measure_v1/prep_v5.json').read_text())['frame']['u_axis_angle_degrees_ccw_from_easting'])
BASIS = np.array([[np.cos(angle),np.sin(angle)],[np.sin(angle),-np.cos(angle)]])
ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
_proofs = {}

def xyuv(p): return np.asarray(p)[...,:2] @ BASIS.T
def uvxy(p): return np.asarray(p) @ BASIS.T
def case(key): return next(x for x in AC['cases'] if x['id']==key or x['id'].split('_')[0]==key)
def root_of(c): return O/'scenes'/f"{c['site']}__{c['prior']}"
def stamp(p):
    s=Path(p).stat(); return [s.st_size,s.st_mtime_ns,s.st_ino,s.st_dev]
def proof(p):
    p=Path(p); key=str(p); st=stamp(p)
    if key not in _proofs or _proofs[key]['stat']!=st:
        cache=AW/'hashes'/(hashlib.sha256(key.encode()).hexdigest()+'.json')
        rec=json.loads(cache.read_text()) if cache.exists() else None
        if not rec or rec['stat']!=st:
            rec=dict(path=key,sha256=sha(p),stat=st);dump(cache,rec)
        _proofs[key]=rec
    return {k:v for k,v in _proofs[key].items() if k!='stat'}
def savepng(im,path,meta,sources=()):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    im.save(path,icc_profile=ICC,dpi=(300,300))
    dump(path.with_suffix('.json'),dict(at=now(),size_px=list(im.size),color_space='sRGB',text_in_figure=False,
        scientific_verdict=None,crs='EPSG:25832',local_world_shift=[690953,5336071,604],
        config_sha256=sha(C/'addendum4.json'),runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),
        implementation=[proof(Path(__file__).with_name(n)) for n in ['add4_common.py','add4_prepare.py','add4_figures.py','add4_render.py']],
        sources=[proof(x) for x in dict.fromkeys(map(str,sources))],**meta))
def meshpath(c,m):
    p=root_of(c)/'distances'/f'{m}.json'
    z=json.loads(p.read_text());return Path(z['mesh'])
def getcase(c): return json.loads((AW/'cases'/f"{c['id']}.json").read_text())
def section_mask(P,s):
    a,b=np.asarray(s['start']),np.asarray(s['end']);d=(b-a)/np.linalg.norm(b-a);v=P[:,:2]-a;t=v@d
    return (t>=0)&(t<=np.linalg.norm(b-a))&(abs(v[:,0]*d[1]-v[:,1]*d[0])<=.5)
def rect(lo,hi): return np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]])
def pixels(uv,bounds,size):
    b=np.asarray(bounds);return (np.asarray(uv)-b[[0,2]])/(b[[1,3]]-b[[0,2]])*np.asarray(size)
def ortho(site):
    p=CH6/f'ortho_{site}.npz';z=loadz(p);h,w=z['rgb'].shape[:2]
    ex=[float(z['u0']),float(z['u0']+w*z['res']),float(z['v0']),float(z['v0']+h*z['res'])]
    if site!='overview':
        b=BOXES[BIDS[site]];ex=[max(ex[0],b['eval_u'][0]-5),min(ex[1],b['eval_u'][1]+5),max(ex[2],b['eval_v'][0]-5),min(ex[3],b['eval_v'][1]+5)]
    return p,z,ex
def orthocrop(z,bounds,W=1600):
    H=round(W*(bounds[3]-bounds[2])/(bounds[1]-bounds[0]));box=[(bounds[0]-z['u0'])/z['res'],(bounds[2]-z['v0'])/z['res'],(bounds[1]-z['u0'])/z['res'],(bounds[3]-z['v0'])/z['res']]
    return Image.fromarray(z['rgb']).transform((W,H),Image.Transform.EXTENT,box,Image.Resampling.BICUBIC)
def aspect_bounds(lo,hi,aspect):
    mid=(np.asarray(lo)+hi)/2;span=np.asarray(hi)-lo;w=max(span[0],span[1]*aspect);h=w/aspect
    return [mid[0]-w/2,mid[0]+w/2,mid[1]-h/2,mid[1]+h/2]
def draw_section(im,pts,visible=None,draw_mask=None):
    pts=np.asarray(pts);draw=ImageDraw.Draw(im);width=max(2,round(im.width*.006));outer=width+max(2,round(im.width*.002))
    if visible is None: visible=np.ones(len(pts)-1,bool)
    if draw_mask is None: draw_mask=np.ones(len(pts)-1,bool)
    for col,w in [('#16263D',outer),('#FCFCFA',width)]:
        for i in range(len(pts)-1):
            if draw_mask[i] and (visible[i] or (i//4)%2==0):draw.line([tuple(pts[i]),tuple(pts[i+1])],fill=col,width=w)
        for end,other in [(pts[0],pts[1]),(pts[-1],pts[-2])]:
            d=end-other;d=d/max(np.linalg.norm(d),1e-12);v=np.array([-d[1],d[0]])*width*1.8
            draw.line([tuple(end-v),tuple(end+v)],fill=col,width=w)
    return im
def section_pixels(rec,bounds,size):
    ends=pixels(xyuv([rec['section']['start'],rec['section']['end']]),bounds,size)
    box=pixels(rec['box_corners_uv'],bounds,size)
    return dict(A_px=ends[0].tolist(),Aprime_px=ends[1].tolist(),box_corners_px=box.tolist(),bounds_uv=bounds)
