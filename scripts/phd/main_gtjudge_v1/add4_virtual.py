"""Actual colored MVS geometry in a free camera, explicitly not a photograph."""
from add4_common import *
from add4_figures import camera_projection
from add4_render import rays
from add4_viewclip import faces
import open3d as o3d

def setup(key,variant,profile=False):
 c=case(key);rec=getcase(c);cand=json.loads((AW/'context_candidates'/f"{c['id']}.json").read_text());refpath=O/'reference'/c['site']/'dense.npz';ref=loadz(refpath);lo,hi=np.array(cand['context_bounds_uv']);P=ref['xyz'];q=xyuv(P);take=((q>=lo)&(q<=hi)).all(1)&(~ref['wall']);Q=P[take];Q=Q[::max(1,len(Q)//10000)];line=np.array(cand['line_xyz']);supported=np.array(cand['height_supported'])
 if key=='c3':
  supported&=abs(line[:,2]-rec['line_xyz'][0][2])<1.;line[~supported,2]=rec['line_xyz'][0][2]+.03
 elif key=='c2':
  row=loadz(root_of(c)/'rows.npz');band=section_mask(row['xyz'],rec['section'])&(row['row_kind']==1);roof_floor=np.percentile(row['xyz'][band,2],10)-1;supported&=line[:,2]>=roof_floor
 context_Q=Q.copy()
 if key=='c3' and profile:
  box=np.asarray(rec['box_corners_uv']);lo=box.min(0)-1;hi=box.max(0)+1;roof_z=rec['line_xyz'][0][2]
  take=((q>=lo)&(q<=hi)).all(1)&(~ref['wall'])&(abs(P[:,2]-roof_z)<2.5);Q=P[take];Q=Q[::max(1,len(Q)//10000)]
 center=np.r_[uvxy((lo+hi)/2),np.median(Q[:,2])]
 if key=='c1':horizontal=-BASIS[1]
 else:
  high=context_Q[context_Q[:,2]>np.percentile(context_Q[:,2],75)];horizontal=line.mean(0)[:2]-high[:,:2].mean(0);horizontal/=np.linalg.norm(horizontal)
 angle=np.deg2rad(([-45,0,45] if key=='c1' else [10,35,60])[variant] if profile else [-35,0,35][variant]);rot=np.array([[np.cos(angle),-np.sin(angle)],[np.sin(angle),np.cos(angle)]]);horizontal=rot@horizontal
 gravity=PH.parent/'p0-audit/data/work/gate_s0/freeze_recovery_v1/P2-GATE-S0-FREEZE-RECOVERY-v1/checkpoints/030-dense_mvs_and_gravity.json';up=np.array(json.loads(gravity.read_text())['payload']['gravity']['up']);up/=np.linalg.norm(up)
 horizontal=np.r_[horizontal,0.];horizontal-=up*(horizontal@up);horizontal/=np.linalg.norm(horizontal);el=np.deg2rad(30 if profile else (65 if key!='c3' else 75));distance=max(100,np.linalg.norm(hi-lo)*3);origin=center+distance*(np.cos(el)*horizontal+np.sin(el)*up)
 forward=center-origin;forward/=np.linalg.norm(forward);right=np.cross(forward,up);right/=np.linalg.norm(right);down=np.cross(forward,right);Rcam=np.stack([right,down,forward]);t=-Rcam@origin;W,H=1600,1280
 coords=np.vstack([Q,line])@Rcam.T+t;uv=coords[:,:2]/coords[:,2,None];mn,mx=uv.min(0),uv.max(0);frame_fill=.72 if key=='c1' else .90;f=frame_fill*min(W/(mx[0]-mn[0]),H/(mx[1]-mn[1]));mid=(mn+mx)/2;cx=W/2-f*mid[0];cy=H/2-f*mid[1]
 camera=dict(name='MVS_virtual_'+key+'_'+str(variant)+('_profile30' if profile else ''),source_type='colored MVS render, not a photograph',training_camera=False,parameters=[f,f,cx,cy,0,0,0,0,0,0,0,0],R=Rcam.tolist(),t=t.tolist(),centre=origin.tolist(),crop_xyxy_px=[0,0,W,H],output_size_px=[W,H],source_size_px=[W,H],calibration_model='synthetic pinhole zero distortion',angle_definition='synthetic_optical_axis_elevation_frozen_gravity',elevation_deg=float(np.degrees(el)),azimuth_deg=float(np.degrees(np.arctan2(-horizontal[0],-horizontal[1]))%360),selection_fallback=True,crop_policy='whole_context_MVS_user_authorized',captured_at=None,context_variant=variant,context_bounds_uv=[lo.tolist(),hi.tolist()])
 camera['frame_fill_fraction']=frame_fill
 if key=='c3' and profile:
  camera['display_clip']=dict(bounds_uv=[lo.tolist(),hi.tolist()],z_bounds_local_m=[roof_z-1.5,roof_z+1.5],rule='local cutaway: keep complete original triangles whose three vertices lie inside the UV/Z box; original reference points use the same box; no vertex moves or new triangles; clipped boundaries are not source holes')
  camera['crop_policy']='low_flat_roof_local_cutaway';camera['source_type']='colored MVS local cutaway, not a photograph';camera['name']+='_cutaway'
 return c,rec,camera,line,supported,refpath,gravity

def main(key,variant=None,profile=False):
 profile=bool(profile)
 c=case(key);path=meshpath(c,'mvs');mesh=o3d.io.read_triangle_mesh(str(path));V=np.asarray(mesh.vertices);F=np.asarray(mesh.triangles);Cmesh=np.asarray(mesh.vertex_colors);assert len(Cmesh)==len(V);cam0=setup(key,0,profile)[2];F=faces(V,F,cam0);sc=MeshScene(V,F)
 variants=range(3) if variant in [None,'preview'] else [int(variant)];panels=[]
 for v in variants:
  c,rec,cam,line,supported,refpath,gravity=setup(key,v,profile);full=variant is not None and variant!='preview';W,H=cam['output_size_px'];working=dict(cam)
  if not full:working['output_size_px']=[600,480];W,H=working['output_size_px']
  arr=np.full((H,W,3),255,'u1')
  for y in range(0,H,100):
   rr,_=rays(working,y,min(H,y+100));hit=sc.sc.cast_rays(sc.o3d.core.Tensor(rr));ok=np.isfinite(hit['t_hit'].numpy());fid=hit['primitive_ids'].numpy()[ok];bary=hit['primitive_uvs'].numpy()[ok];weights=np.c_[1-bary.sum(1),bary];col=(Cmesh[F[fid]]*weights[:,:,None]).sum(1);view=arr[y:min(H,y+100)].reshape(-1,3);view[ok]=np.rint(255*np.clip(col,0,1)).astype('u1')
  uv,_=camera_projection(line,working);directions=line-np.array(cam['centre']);ranges=np.linalg.norm(directions,axis=1);directions/=ranges[:,None];depth=sc.cast(np.broadcast_to(cam['centre'],directions.shape),directions);visible=~np.isfinite(depth)|(depth>=ranges-.15)
  # Never join the line vertically between two separate roof levels.
  draw_mask=supported[:-1]&supported[1:]&(abs(np.diff(line[:,2]))<.7)
  im=Image.fromarray(arr);draw_section(im,uv,visible[:-1]&visible[1:],draw_mask)
  if not full:panels.append(im);continue
  rec.update(camera=cam,annotation_line_xyz=line.tolist(),annotation_reference=proof(refpath),annotation_display_mask=draw_mask.tolist(),context_revision='user requested views matched to roof height, eaves, and low flat roof errors; colored MVS replaces unsuitable photograph; no geometry modification',line_altitude_rule='original reference roof point heights for annotation only; discontinuities not connected; source section XY and scores unchanged');dump(AW/'cases'/f"{c['id']}.json",rec);old=loadz(AW/'cases'/f"{c['id']}.npz");old['line_xyz']=line;savez(AW/'cases'/f"{c['id']}.npz",**old)
  corners=np.c_[rec['box_corners_xy'],np.full(4,rec['line_xyz'][0][2])];bp,_=camera_projection(corners,cam);meta=dict(case=c['id'],panel='colored_MVS_context',photograph=False,camera=cam,A_px=uv[0].tolist(),Aprime_px=uv[-1].tolist(),box_corners_px=bp.tolist(),line_polyline_px=uv.tolist(),line_visibility=visible.tolist(),line_draw_mask=draw_mask.tolist(),occlusion_rule='exact MVS ray visibility; disconnected roof levels not joined',original_section_unchanged=True)
  meta['geometry_display']='local cutaway' if cam.get('display_clip') else 'full source mesh'
  savepng(im,AF/f"{c['id']}_oblique.png",meta,[path,refpath,gravity,AW/'cases'/f"{c['id']}.json",Path(__file__),Path(__file__).with_name('add4_viewclip.py')]);dump(AW/'cameras'/f"{c['id']}_projection.json",meta)
 if variant in [None,'preview']:
  sheet=Image.new('RGB',(1800,480),'white')
  for i,im in enumerate(panels):sheet.paste(im,(i*600,0))
  out=AW/'context_candidates'/f"{c['id']}_MVS{'_profile30' if profile else ''}.png";sheet.save(out);print(str(out),flush=True)
 else:print('MVS_CONTEXT_SELECTED',key,variant,flush=True)
if __name__=='__main__':main(*sys.argv[1:])
