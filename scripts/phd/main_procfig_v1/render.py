"""No GS rendering: exact ellipse plane rasterization with per-pixel depth."""
from common import *
from measure import scope_mask
from PIL import Image,ImageDraw,ImageCms
from shapely.geometry import Polygon,shape
from shapely import vectorized
import subprocess,shutil
sys.path.insert(0,str(R))
from src.phd.prior_propagation_v6.orientation import axes_of_quat
from src.phd.metrics_v3.surface import MeshScene
ICC=ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
def color(s):return np.array([int(s[i:i+2],16) for i in [1,3,5]])/255
def frame(c,az,zoom=False):
 W,H=c['rendering']['width_px'],c['rendering']['height_px'];a,e=np.deg2rad([az,c['rendering']['elevation_degrees']]);gravity_up=np.array(c['coordinates']['up']);east=np.array([1.,0.,0.]);east-=np.dot(east,gravity_up)*gravity_up;east/=np.linalg.norm(east);north=np.cross(gravity_up,east);out=np.cos(e)*(np.cos(a)*east+np.sin(a)*north)+np.sin(e)*gravity_up;f=-out;r=np.cross(f,gravity_up);r/=np.linalg.norm(r);u=np.cross(r,f);basis=np.array([r,u,f])
 xy=np.asarray(c['scope']['zoom_box_xy']) if zoom else np.asarray(shape(c['scope']['buffered_footprint']).exterior.coords);bounds=np.array([[*xy.min(0),c['scope']['z_min']],[*xy.max(0),c['scope']['z_max']]])
 center=bounds.mean(0);corners=np.array([[x,y,z] for x,y in xy for z in bounds[:,2]]);q=(corners-center)@basis.T;span=np.ptp(q[:,:2],axis=0);width=max(span[0],span[1]*W/H)*1.08;height=width*H/W
 return dict(azimuth=az,elevation=35,elevation_reference='frozen terrain-MVS gravity up; azimuth from projected local East toward North',W=W,H=H,basis=basis.tolist(),center=center.tolist(),width_m=width,height_m=height,projection='orthographic',zoom=zoom,framing='same frozen full building Z range',scale_bar_m=5 if not zoom else 2)
def project(P,cam,delta=False):
 q=(P-(0 if delta else np.array(cam['center'])))@np.array(cam['basis']).T
 q[:,0]*=cam['W']/cam['width_m'];q[:,1]*=-cam['H']/cam['height_m']
 if not delta:q[:,:2]+=[cam['W']/2,cam['H']/2]
 return q
def save(im,path,meta,cam):
 draw=ImageDraw.Draw(im);m=cam['scale_bar_m'];px=m*cam['W']/cam['width_m'];x,y=64,im.height-58;draw.line([(x,y),(x+px,y)],fill='#333333',width=7);draw.line([(x,y-9),(x,y+9)],fill='#333333',width=3);draw.line([(x+px,y-9),(x+px,y+9)],fill='#333333',width=3)
 im.save(path,icc_profile=ICC,dpi=(300,300));dump(path.with_suffix('.json'),dict(camera=cam,scale_bar=dict(m=m,length_px=px,start_px=[x,y]),size_px=list(im.size),text_in_figure=False,color_space='sRGB',background='#FCFCFA',config_sha256=sha(C/'procfig_v1.json'),display_fix1_sha256=cfg().get('display_fix1_sha256'),scientific_verdict=None,**meta))
def raster(primitives,path,cam,opaque,meta):
 p=O/'work/render.bin';out=O/'work/render.rgb';np.asarray(primitives,'<f8').tofile(p)
 c=cfg();poly=shape(c['scope']['buffered_footprint'])
 if cam['zoom']:poly=poly.intersection(Polygon(c['scope']['zoom_box_xy']))
 polygons=[poly] if poly.geom_type=='Polygon' else list(poly.geoms);rings=[np.array(r.coords) for pol in polygons for r in [pol.exterior,*pol.interiors]];clip=O/'work/render_clip.txt'
 with clip.open('w') as f:
  vals=[*cam['center'],*np.array(cam['basis']).ravel(),cam['width_m'],cam['height_m'],c['scope']['z_min'],c['scope']['z_max'],len(rings)];f.write(' '.join(map(str,vals))+'\n')
  for ring in rings:f.write(str(len(ring))+' '+' '.join(map(str,ring.ravel()))+'\n')
 cp=subprocess.run([str(O/'work/discs'),str(cam['W']),str(cam['H']),str(int(opaque)),str(p),str(out),str(clip)],check=True,capture_output=True,text=True)
 im=Image.frombytes('RGB',(cam['W'],cam['H']),out.read_bytes());save(im,path,dict(meta,rasterizer=cp.stdout.strip(),depth='exact affine plane depth at each covered pixel; front-to-back alpha compositing for transparency',disc_radius='activated tangent scale times display factor; finite flat disc, not Gaussian tail'),cam)
def main():
 c=cfg();subprocess.run(['g++','-O3','-std=c++17',str(Path(__file__).with_name('discs.cpp')),'-o',str(O/'work/discs')],check=True)
 ref=loadz(O/'work/reference_building.npz');points=ref['xyz'][ref['case_id']==1];mesh=MeshScene.from_ply(c['sources']['result_mesh']);candidates=[]
 for az in c['rendering']['azimuth_degrees']:
  cam=frame(c,az);f=np.array(cam['basis'])[2];orig=points-100*f;hit=mesh.cast(orig,f);visible=~np.isfinite(hit)|(hit>=100-.15);candidates.append(dict(azimuth=az,case1_points=len(points),visible_points=int(visible.sum()),fraction=float(visible.mean()) if len(points) else None,camera=cam))
 candidates.sort(key=lambda r:(-(r['fraction'] if r['fraction'] is not None else -1),r['azimuth']));dump(D/'camera_ranking.json',dict(candidates=candidates,rule=c['rendering']['visibility_rule'],scientific_verdict=None));del mesh
 light=np.array(c['rendering']['light_direction']);light/=np.linalg.norm(light);prior=loadz(O/'work/prior_clipped.npz')['triangles'];mvs=loadz(O/'work/mvs_building.npz')['xyz'];zoompoly=Polygon(c['scope']['zoom_box_xy'])
 jobs=[]
 for rank,entry in enumerate(candidates[:3],1):
  for style in c['rendering']['rank_styles'][str(rank)]:jobs.append((rank,style,False,entry['camera']))
 for style in c['rendering']['zoom_styles']:jobs.append((1,style,True,frame(c,candidates[0]['azimuth'],True)))
 inventory=[]
 for rank,style,zoom,cam in jobs:
  if 'd_only' in sys.argv and style!='d':continue
  prefix='proc_zoom' if zoom else 'proc';suffix=style if zoom else f'{rank}_{style}'
  # Input panel is identical for the display styles; retain every requested file.
  name=f'{prefix}_input_{suffix}';T=prior
  # Every triangle is clipped per fragment, including triangles crossing zoom edges.
  cr=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]);cr/=np.maximum(np.linalg.norm(cr,axis=1)[:,None],1e-20);shade=.55+.45*abs(cr@light);col=color('#D85A30')[None]*shade[:,None]
  prim=np.c_[np.ones(len(T)),project(T[:,0],cam),project(T[:,1]-T[:,0],cam,True),project(T[:,2]-T[:,0],cam,True),col,np.full(len(T),.35)]
  P=mvs
  if zoom:P=P[vectorized.contains(zoompoly,P[:,0],P[:,1])]
  pp=np.c_[np.zeros(len(P)),project(P,cam),np.tile([1.2,0,0],(len(P),1)),np.tile([0,1.2,0],(len(P),1)),np.tile(color('#1D9E75'),(len(P),1)),np.ones(len(P))]
  first=O/'figures'/f'{prefix}_input_{"a" if zoom else str(rank)+"_a"}.png'
  path=O/'figures'/(name+'.png');meta=dict(panel='input',style=style,gaussians_drawn=0,mvs_points=len(P),prior_triangles=len(T),sources={k:dict(path=c['sources'][k],sha256=json.loads((D/'input_lock.json').read_text())['sources'][k]['sha256']) for k in ['prior','mvs_points']})
  if style!='a' and first.exists():
   shutil.copyfile(first,path);old=json.loads(first.with_suffix('.json').read_text());old['style']=style;dump(path.with_suffix('.json'),old)
  else:raster(np.r_[prim,pp],path,cam,False,meta)
  inventory.append(path.name)
  for it in c['iterations']:
   path=O/'figures'/f'{prefix}_{it}_{suffix}.png';g=loadz(O/'gaussians'/f'{it}.npz');take=np.ones(len(g['xyz']),bool)
   if zoom:take&=vectorized.contains(zoompoly,g['xyz'][:,0],g['xyz'][:,1])
   if style=='d':take&=g['opacity']>=.1
   g={k:v[take] for k,v in g.items()};a,b,n=axes_of_quat(g['rotation']);factor=c['rendering']['styles'][style]['scale'];col=np.tile(color('#B4B2A9'),(len(n),1))
   for reg in [0,1,2,4]:col[g['judgment']==reg]=color(c['rendering']['colors'][str(reg)])
   col[g['group33']==1]=color('#C2378A');col*= (.55+.45*abs(n@light))[:,None];alpha=g['opacity'] if style=='c' else np.ones(len(n))
   prim=np.c_[np.zeros(len(n)),project(g['xyz'],cam),project(a*g['scale'][:,0,None]*factor,cam,True),project(b*g['scale'][:,1,None]*factor,cam,True),col,alpha]
   raster(prim,path,cam,style!='c',dict(panel=it,style=style,gaussians_drawn=len(n),wrong_lineage_gaussians=int((g['group33']==1).sum()),sources={str(O/'gaussians'/f'{it}.npz'):sha(O/'gaussians'/f'{it}.npz')},fixed_light_direction=light.tolist(),display_factor=factor));inventory.append(path.name)
  print('RENDERED_JOB',rank,style,zoom,flush=True)
 if 'd_only' not in sys.argv:dump(D/'figure_inventory.json',dict(figures=inventory,count=len(inventory),scientific_verdict=None))
if __name__=='__main__':main()
