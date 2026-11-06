"""Addendum 6 outputs are separate from every previously delivered figure."""
from add4_common import *
from add4_figures import camera_projection
from normal_line import values

A6=json.loads((C/'addendum6.json').read_text())
assert sha(C/'addendum6.json')==json.loads((C/'addendum6.lock.json').read_text())['config_sha256']
W6=O/'addendum6';F6=D/'figures/addendum6';T6=D/'tables/addendum6'
for p in [W6,F6,T6]:p.mkdir(parents=True,exist_ok=True)
SHIFT=np.array([690953,5336071,604.])
GRAVITY=PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json'
UP=np.array(json.loads(GRAVITY.read_text())['payload']['gravity']['up']);UP/=np.linalg.norm(UP)

def methods(c):
 return ['prior','mvs','fusion','GeoGS_30000','FINALTRAIN_30000']+(['judgment_mesh','A1'] if c['id'].startswith('c4') else [])

def selected(c):return json.loads((W6/'selected'/f"{c['id']}.json").read_text())

def png(im,name,meta,sources):
 p=F6/(name+'.png');im.save(p,icc_profile=ICC,dpi=(300,300))
 dump(p.with_suffix('.json'),dict(at=now(),size_px=list(im.size),color_space='sRGB',text_in_figure=False,scientific_verdict=None,crs='EPSG:25832',local_world_shift=SHIFT.tolist(),config_sha256=sha(C/'addendum6.json'),
  runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),sources=[proof(x) for x in dict.fromkeys(map(str,sources))],**meta))

def status(s,tau):return np.where(~np.isfinite(s),'none',np.where(abs(s)<=tau,'in','far'))

def clip_segments(seg,length):
 seg=seg.copy()
 for j in range(2):
  out=(seg[:,j,0]<0)|(seg[:,j,0]>length)
  if out.any():
   a=seg[out,j].copy();b=seg[out,1-j].copy();den=b[:,0]-a[:,0];good=abs(den)>1e-12;t=np.zeros(len(a));t[good]=(np.clip(a[good,0],0,length)-a[good,0])/den[good];seg[out,j]=a+t[:,None]*(b-a)
 return seg

def annotation(c,cam,scene=None):
 rec=selected(c);line=np.array(rec['annotation_xyz']);uv,depth=camera_projection(line,cam);origin=np.array(cam['centre']);direction=line-origin;distance=np.linalg.norm(direction,axis=1);direction/=distance[:,None]
 if scene is None:visible=None;occluded=None
 else:
  hit=scene.cast(np.broadcast_to(origin,direction.shape),direction);visible=(~np.isfinite(hit))|(hit>=distance-.15);occluded=(~visible).tolist()
 return dict(A_px=uv[0].tolist(),Aprime_px=uv[-1].tolist(),line_polyline_px=uv.tolist(),line_xyz=line.tolist(),line_occluded=occluded,occlusion_rule='ray hit more than 0.15m before the reference-height annotation',line_points_inside_image=((depth>0)&(uv[:,0]>=0)&(uv[:,0]<=cam['output_size_px'][0])&(uv[:,1]>=0)&(uv[:,1]<=cam['output_size_px'][1])).tolist(),line_drawn=False)

def table6(name,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r));p=T6/(name+'.csv')
 with p.open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
 return p
