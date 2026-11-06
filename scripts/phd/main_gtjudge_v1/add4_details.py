"""Supplementary c3 input comparison; original full-range sections stay intact."""
from add4_common import *
from add4_render import rays
from add4_viewclip import faces

def section_detail():
 c=case('c3');rec=getcase(c);s=rec['section'];root=root_of(c);row=loadz(root/'rows.npz');P=section_points(row['xyz'],s)
 W,H=1600,600;scale=2;left,top,right,bottom=60,40,1540,560;px_per_m=(right-left)/s['length_m'];zspan=(bottom-top)/px_per_m;mid=float(np.median(P[:,1]));bounds=[0,s['length_m'],mid-zspan/2,mid+zspan/2]
 im=Image.new('RGBA',(W*scale,H*scale));d=ImageDraw.Draw(im);sources=[root/'rows.npz',AW/'cases'/f"{c['id']}.json"];clipped={}
 def project(q):
  q=np.asarray(q);return np.stack([left+q[...,0]*px_per_m,top+(bounds[3]-q[...,1])*px_per_m],-1)*scale
 def clip_edge(a,b):
  t0,t1=0.,1.;delta=b-a
  for k,lo,hi in [(0,bounds[0],bounds[1]),(1,bounds[2],bounds[3])]:
   if abs(delta[k])<1e-12:
    if a[k]<lo or a[k]>hi:return None
   else:
    u,v=sorted([(lo-a[k])/delta[k],(hi-a[k])/delta[k]]);t0=max(t0,u);t1=min(t1,v)
    if t0>t1:return None
  return np.array([a+t0*delta,a+t1*delta])
 for m in ['prior','mvs']:
  cp=AW/'sections'/c['id']/f'{m}.npz';seg=loadz(cp)['segments'];sources.extend([cp,meshpath(c,m),root/'distances'/f'{m}.npz']);shown=0;cropped=0
  for a,b in seg:
   e=clip_edge(a,b)
   if e is None:continue
   shown+=1;cropped+=int(not np.allclose(e,[a,b]));d.line([tuple(v) for v in project(e)],fill=AC['method_colors'][m],width=3*scale)
  clipped[m]=dict(total_segments=len(seg),visible_segments=shown,partly_clipped_segments=cropped,fully_outside_segments=len(seg)-shown)
 inside=(P[:,0]>=0)&(P[:,0]<=s['length_m'])&(P[:,1]>=bounds[2])&(P[:,1]<=bounds[3])
 for xy in project(P[inside]):
  r=2.5*scale;d.ellipse([xy[0]-r,xy[1]-r,xy[0]+r,xy[1]+r],fill='#3a3a3a')
 x,y=85*scale,65*scale;d.line([(x,y),(x+2*px_per_m*scale,y)],fill='#16263D',width=2*scale);d.line([(x,y),(x,y+px_per_m*scale)],fill='#16263D',width=2*scale)
 audit=D/'verification/addendum4_c3_audit.json';sources.append(audit)
 meta=dict(case=c['id'],panel='input_section_detail',section=s,axis_bounds=bounds,plot_bounds_px=[left,top,right,bottom],vertical_exaggeration=1.,supplementary=True,
  original_full_range_sections_unchanged=True,viewport_rule='centred on median reference-strip height; equal metric x/z scale; geometry outside this supplemental viewport is clipped',
  clipped_geometry=clipped,reference_points_total=len(P),reference_points_visible=int(inside.sum()),reference_points_outside=int((~inside).sum()),
  colors={'prior':AC['method_colors']['prior'],'mvs':AC['method_colors']['mvs'],'reference':'#3a3a3a'},
  A_px=[left,top+(bounds[3]-rec['line_xyz'][0][2])*px_per_m],Aprime_px=[right,top+(bounds[3]-rec['line_xyz'][0][2])*px_per_m],box_corners_px=[[left,top],[right,top],[right,bottom],[left,bottom]],
  scale_bar=dict(horizontal_m=2,vertical_m=1,horizontal_px=2*px_per_m,vertical_px=px_per_m,origin_px=[85,65]),scientific_interpretation=None)
 savepng(im.resize((W,H),Image.Resampling.LANCZOS),AF/f"{c['id']}_input_section_detail.png",meta,sources+[Path(__file__)])
 print('ADD4_INPUT_DETAIL',clipped,flush=True)

def prior_view():
 c=case('c3');rec=getcase(c);cam=rec['camera'];projection=json.loads((AW/'cameras'/f"{c['id']}_projection.json").read_text());p=meshpath(c,'prior');V,F=read_surface(p);F=faces(V,F,cam);sc=MeshScene(V,F);W,H=cam['output_size_px'];arr=np.full((H,W,3),255,'u1')
 for y in range(0,H,100):
  rr,di=rays(cam,y,min(y+100,H));hit=sc.sc.cast_rays(sc.o3d.core.Tensor(rr));good=np.isfinite(hit['t_hit'].numpy());norm=hit['primitive_normals'].numpy();unit=di/np.linalg.norm(di,axis=1)[:,None];shade=np.rint(207*(.35+.65*abs((norm*unit).sum(1)))).astype('u1');arr[y:min(y+100,H)].reshape(-1,3)[good]=shade[good,None]
 im=Image.fromarray(arr);draw_section(im,np.array(projection['line_polyline_px']),np.array(projection['line_visibility'][:-1])&np.array(projection['line_visibility'][1:]),projection.get('line_draw_mask'))
 base={k:projection[k] for k in ['A_px','Aprime_px','box_corners_px','line_polyline_px','line_visibility','line_draw_mask']}
 savepng(im,AF/f"{c['id']}_prior_gray.png",dict(case=c['id'],panel='prior_gray_supplement',method='prior',camera=cam,geometry_render='complete original ALS prior triangles inside explicit camera.display_clip; exact shared camera and ray shading',**base),[p,AW/'cases'/f"{c['id']}.json",Path(__file__),Path(__file__).with_name('add4_viewclip.py')])
 print('ADD4_PRIOR_VIEW',flush=True)

if __name__=='__main__':
 section_detail()
 if len(sys.argv)<2 or sys.argv[1]!='section':prior_view()
