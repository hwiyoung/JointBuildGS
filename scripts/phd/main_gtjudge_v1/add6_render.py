"""New unmarked panels, with the exact distance palette and source meshes."""
from add6_common import *
from add4_render import rays
from cylinder import Cylinder

def palette(ids,signed,tau):
 good=ids>=0;far=good&np.isfinite(signed)&(abs(signed)>tau);out=np.full((*ids.shape,3),255,'u1');t=np.minimum(abs(signed[far]),1)[:,None]
 out[far]=np.rint(255*(1-t)+np.where((signed[far]>0)[:,None],np.array([216,55,48]),np.array([42,120,214]))*t).astype('u1');out[good&~np.isfinite(signed)]=[140,149,163];return out

def make_camera():
 c=case('c3');rec=selected(c);line=np.array(rec['annotation_xyz']);ref=loadz(O/'reference'/c['site']/'dense.npz',['xyz']);q=xyuv(ref['xyz']);uvline=xyuv(line);lo=uvline.min(0)-8;hi=uvline.max(0)+8;P=ref['xyz'][((q>=lo)&(q<=hi)).all(1)];P=P[::max(1,len(P)//12000)];center=np.r_[uvxy((lo+hi)/2),np.median(P[:,2])];V,F=read_surface(meshpath(c,'mvs'));sc=MeshScene(V,F);candidates=[]
 for el in A6['c3_camera']['elevation_candidates_deg']:
  for az in [0,90,180,270]:
   horizontal=np.r_[np.cos(np.deg2rad(az))*BASIS[0]+np.sin(np.deg2rad(az))*BASIS[1],0.];horizontal-=UP*(horizontal@UP);horizontal/=np.linalg.norm(horizontal);origin=center+180*(np.cos(np.deg2rad(el))*horizontal+np.sin(np.deg2rad(el))*UP);forward=center-origin;forward/=np.linalg.norm(forward);right=np.cross(forward,UP);right/=np.linalg.norm(right);down=np.cross(forward,right);rot=np.stack([right,down,forward]);t=-rot@origin;W,H=1600,2000;coords=np.vstack([P,line])@rot.T+t;uv=coords[:,:2]/coords[:,2,None];mn,mx=uv.min(0),uv.max(0);f=.86*min(W/(mx[0]-mn[0]),H/(mx[1]-mn[1]));mid=(mn+mx)/2
   cam=dict(name=f'add6_c3_el{el}_az{az}',source_type='synthetic camera for original meshes',training_camera=False,parameters=[f,f,W/2-f*mid[0],H/2-f*mid[1],0,0,0,0,0,0,0,0],R=rot.tolist(),t=t.tolist(),centre=origin.tolist(),crop_xyxy_px=[0,0,W,H],output_size_px=[W,H],source_size_px=[W,H],elevation_deg=el,azimuth_basis_deg=az,angle_definition='synthetic_optical_axis_elevation_frozen_gravity',calibration_model='synthetic pinhole zero distortion',context_bounds_uv=[lo.tolist(),hi.tolist()])
   di=line-origin;distance=np.linalg.norm(di,axis=1);di/=distance[:,None];hit=sc.cast(np.broadcast_to(origin,di.shape),di);pos=origin+hit[:,None]*di;severe=np.isfinite(hit)&(hit<distance-2)&(pos[:,2]>line[:,2]+2)
   candidates.append(dict(camera=cam,severe_occluded_count=int(severe.sum()),mean_clearance=float(np.mean(np.where(severe,distance-hit,0)))))
 chosen=min(candidates,key=lambda x:(x['severe_occluded_count'],x['mean_clearance'],A6['c3_camera']['elevation_candidates_deg'].index(x['camera']['elevation_deg']),x['camera']['azimuth_basis_deg']))
 dump(W6/'c3_camera.json',dict(selected=chosen['camera'],candidates=candidates,selection_rule='fewest severe foreground occlusions; smallest obstruction distance; prefer 60,70,45 degrees then azimuth 0,90,180,270; not selected using any result method',severe_occlusion='surface at least 2m ahead of annotation and at least 2m above it; sub-2m MVS discrepancies are retained',sources=[proof(meshpath(c,'mvs')),proof(W6/'selected'/f"{c['id']}.json"),proof(GRAVITY)],scientific_verdict=None));print('ADD6_CAMERA',chosen['camera']['name'],chosen['severe_occluded_count'],flush=True)

def camera(c):return json.loads((W6/'c3_camera.json').read_text())['selected'] if c['id'].startswith('c3') else getcase(c)['camera']

def render(key,method):
 c=case(key);cam=camera(c);rec=selected(c);path=meshpath(c,method);V,F=read_surface(path);sc=MeshScene(V,F);removed=[]
 if c['id'].startswith('c3'):
  line=np.array(rec['annotation_xyz']);direction=line-np.array(cam['centre']);distance=np.linalg.norm(direction,axis=1);direction/=distance[:,None];rr=np.c_[np.broadcast_to(cam['centre'],direction.shape),direction].astype('f4');hit=sc.sc.cast_rays(sc.o3d.core.Tensor(rr));depth=hit['t_hit'].numpy();pos=rr[:,:3]+depth[:,None]*rr[:,3:];mask=np.isfinite(depth)&(depth<distance-2)&(pos[:,2]>line[:,2]+2);removed=np.unique(hit['primitive_ids'].numpy()[mask]).astype(int).tolist()
  if removed:
   keep=np.ones(len(F),bool);keep[removed]=False;del sc;gc.collect();sc=MeshScene(V,F[keep])
 refpath=O/'reference'/c['site']/'dense.npz';ref=loadz(refpath);tree=cKDTree(ref['xyz']);cy=Cylinder(ref['xyz']);W,H=cam['output_size_px'];ids=np.full((H,W),-1,'i4');signed=np.full((H,W),np.nan,'f4');tau=np.full((H,W),np.nan,'f4')
 with (R/'docs/experiments/phd/main_release_v1/tables/stage0/tau_values.csv').open() as f:tr=next(x for x in csv.DictReader(f) if x['site']==c['site'] and x['prior']==c['prior'])
 for y in range(0,H,100):
  rr,di=rays(cam,y,min(y+100,H));hit=sc.sc.cast_rays(sc.o3d.core.Tensor(rr));dep=hit['t_hit'].numpy();good=np.isfinite(dep);fi=hit['primitive_ids'].numpy().astype('i8');fi[~good]=-1;h=min(y+100,H)-y;ids[y:y+h]=fi.reshape(h,W)
  if good.any():
   point=rr[good,:3].astype(float)+dep[good,None]*rr[good,3:];n=hit['primitive_normals'].numpy()[good].astype(float);n/=np.linalg.norm(n,axis=1)[:,None];near=tree.query(point,workers=2)[1];rn=ref['normal'][near].copy()
   if c['prior']=='ALS':rn[rn[:,2]<0]*=-1
   n*=np.where((n*rn).sum(1)<0,-1,1)[:,None];wall=ref['wall'][near] if c['prior']=='LoD2' else np.zeros(len(near),bool);sv,_=cy.query(point,n,np.where(wall,5.,10.),float(ref['radius']));signed[y:y+h].reshape(-1)[good]=-sv;tau[y:y+h].reshape(-1)[good]=np.where(wall,float(tr['wall_tau_m']),float(tr['roof_tau_m']))
  if y%500==0:print('ADD6_RENDER',c['id'],method,y,H,flush=True)
 cy.close();anno=annotation(c,cam,sc);name=c['id']+('_wrong_dist_v2' if method=='mvs' else '_result_dist_'+method)
 meta=dict(case=c['id'],method=method,camera=cam,mesh=proof(path),distance_sampling='visible_pixel_surface_point',distance_color_rule='same addendum4 oriented triangle-normal cylinder query; result minus reference; white within tau, red above, blue below, saturation 1m, missing #8C95A3',radius_m=float(ref['radius']),reference_triangulated=False,display_only_no_scoring_changes=True,removed_original_triangle_ids=removed,removed_triangle_rule='only original triangles directly blocking annotation rays, at least 2m ahead and 2m above; no new triangles',**anno)
 png(Image.fromarray(palette(ids,signed,tau)),name,meta,[path,refpath,W6/'selected'/f"{c['id']}.json",Path(__file__)]+([W6/'c3_camera.json'] if c['id'].startswith('c3') else [AW/'cases'/f"{c['id']}.json"]))
 savez(W6/'render_cache'/f'{name}.npz',face_id=ids,signed=signed,tau=tau);print('ADD6_RENDER_DONE',name,len(removed),flush=True)

def unmarked(key):
 c=case(key);rec=selected(c);old=getcase(c);cam=camera(c);P=loadz(root_of(c)/'rows.npz',['xyz'])['xyz'];lab=loadz(root_of(c)/'stage1_cells.npz',['case_id'])['case_id'];path,z,extent=ortho(c['site']);uv=xyuv(P);source_top=AF/f"{c['id']}_top_crop.json";b0=json.loads(source_top.read_text())['bounds_uv'];variants=[('top_crop_noline',b0)]
 if key=='c3':
  box=np.array(old['box_corners_uv']);variants.append(('top_crop_noline_v2',aspect_bounds(box.min(0)-5,box.max(0)+5,1.25)))
 for tag,bounds in variants:
  im=orthocrop(z,bounds);px=pixels(uv,bounds,im.size);radius=.125*im.width/(bounds[1]-bounds[0]);overlay=Image.new('RGBA',im.size);draw=ImageDraw.Draw(overlay);inside=(px[:,0]>=-radius)&(px[:,0]<im.width+radius)&(px[:,1]>=-radius)&(px[:,1]<im.height+radius);ordered=np.flatnonzero(inside)[np.argsort(P[inside,2],kind='stable')]
  for k in A6['paint_order_case_ids']:
   rgb=tuple(bytes.fromhex(A6['case_colors'][str(k)][1:]));alpha=round(255*(.35 if k==0 else .55))
   for i in ordered[lab[ordered]==k]:x,y=px[i];draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=(*rgb,alpha))
  im=Image.alpha_composite(im.convert('RGBA'),overlay).convert('RGB');line=pixels(xyuv(rec['annotation_xyz']),bounds,im.size);inside_line=((line>=0)&(line<=im.size)).all(1);meta=dict(case=c['id'],bounds_uv=bounds,case_colors=A6['case_colors'],paint_order_case_ids=A6['paint_order_case_ids'],point_alpha={'0':.35,'other':.55},point_diameter_m=.25,A_px=line[0].tolist(),Aprime_px=line[-1].tolist(),line_polyline_px=line.tolist(),line_occluded=[False]*len(line),occlusion_rule='plan-view annotation; no perspective surface occlusion',line_points_inside_image=inside_line.tolist(),line_drawn=False,box_corners_px=pixels(old['box_corners_uv'],bounds,im.size).tolist())
  png(im,c['id']+'_'+tag,meta,[path,root_of(c)/'rows.npz',root_of(c)/'stage1_cells.npz',source_top,W6/'selected'/f"{c['id']}.json",Path(__file__)])
 if key in ['c1','c2']:
  cache=AW/'renders'/f"{c['id']}_pixel_distance.npz";data=loadz(cache);arr=palette(data['face_id'],data['signed_result_minus_reference_m'],data['tau']);V,F=read_surface(meshpath(c,'prior'));sc=MeshScene(V,F);anno=annotation(c,cam,sc)
  original=np.asarray(Image.open(AF/f"{c['id']}_wrong_dist.png"));oldmeta=json.loads((AF/f"{c['id']}_wrong_dist.json").read_text());maskim=Image.new('RGBA',tuple(cam['output_size_px']));draw_section(maskim,oldmeta['line_polyline_px'],np.array(oldmeta['line_visibility'][:-1])&np.array(oldmeta['line_visibility'][1:]),oldmeta.get('line_draw_mask'));mask=np.asarray(maskim)[:,:,3]>0;assert np.array_equal(original[~mask],arr[~mask])
  png(Image.fromarray(arr),c['id']+'_wrong_dist_noline',dict(case=c['id'],method='prior',camera=cam,old_nonannotation_pixels_identical=True,**anno),[cache,AF/f"{c['id']}_wrong_dist.png",W6/'selected'/f"{c['id']}.json",Path(__file__)])
 elif key=='c4':
  im=Image.open(cam['image_original']).convert('RGB').transform(tuple(cam['output_size_px']),Image.Transform.EXTENT,cam['crop_xyxy_px'],Image.Resampling.BICUBIC);V,F=read_surface(meshpath(c,'mvs'));sc=MeshScene(V,F)
  png(im,c['id']+'_oblique_noline',dict(case=c['id'],camera=cam,photograph=True,**annotation(c,cam,sc)),[cam['image_original'],AW/'cases'/f"{c['id']}.json",W6/'selected'/f"{c['id']}.json",Path(__file__)])
 print('ADD6_UNMARKED',c['id'],flush=True)

if __name__=='__main__':
 if sys.argv[1]=='camera':make_camera()
 elif sys.argv[1]=='unmarked':unmarked(sys.argv[2])
 else:render(*sys.argv[1:])
