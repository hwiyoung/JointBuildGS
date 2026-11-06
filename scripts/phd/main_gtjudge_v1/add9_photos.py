"""Select real training photographs, undistort their crops, project saved cases."""
from add9_common import *
from preservation import cameras,full_image
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.vectorized import contains
from scipy.spatial import ConvexHull
import cv2

def native(P,cam,j):
 Q=np.asarray(P)@cam.R[j].T+cam.t[j];uv=Q[:,:2]/Q[:,2,None]*cam.p[:2]+cam.p[2:4];return uv,Q[:,2]
def visibility(P,origin,scene):
 dr=np.asarray(P)-origin;length=np.linalg.norm(dr,axis=1);hit=scene.cast(np.broadcast_to(origin,dr.shape),dr/length[:,None]);return np.isfinite(hit)&(hit<length-.15),~np.isfinite(hit)
def bounds_crop(uv,w,h,padding=1.06):
 lo,hi=uv.min(0),uv.max(0);mid=(lo+hi)/2;cw=max(hi[0]-lo[0],(hi[1]-lo[1])*1.25)*padding;ch=cw/1.25
 if cw<=w and ch<=h:mid=np.clip(mid,[cw/2,ch/2],[w-cw/2,h-ch/2])
 return np.r_[mid-[cw/2,ch/2],mid+[cw/2,ch/2]]
def undistort_crop(cam,j,crop,size):
 im,source=full_image(cam,j);original=np.asarray(im);W,H=size;x,y=np.meshgrid(crop[0]+(np.arange(W)+.5)*(crop[2]-crop[0])/W,crop[1]+(np.arange(H)+.5)*(crop[3]-crop[1])/H)
 fx,fy,cx,cy,k1,k2,p1,p2,k3,k4,k5,k6=cam.p;x=(x-cx)/fx;y=(y-cy)/fy;r=x*x+y*y;radial=(1+k1*r+k2*r*r+k3*r**3)/(1+k4*r+k5*r*r+k6*r**3);u=fx*(x*radial+2*p1*x*y+p2*(r+2*x*x))+cx;v=fy*(y*radial+p1*(r+2*y*y)+2*p2*x*y)+cy
 valid=(u>=0)&(u<cam.w-1)&(v>=0)&(v<cam.h-1);out=cv2.remap(original,u.astype('f4'),v.astype('f4'),cv2.INTER_CUBIC,borderMode=cv2.BORDER_CONSTANT,borderValue=(255,255,255));source['undistorted_valid_pixel_fraction']=float(valid.mean());return Image.fromarray(out),source

def projection(P,cam):return camera_projection(P,cam)
def annotation9(c,line,cam,scene):
 P=np.array(line['annotation_xyz']);uv,depth=projection(P,cam);oc,unk=visibility(P,np.array(cam['centre']),scene);inside=(depth>0)&((uv>=0)&(uv<cam['output_size_px'])).all(1);box=box9(c,line['section']);bp,_=projection(box,cam);edges=[]
 for a,b in zip(box,np.roll(box,-1,axis=0)):
  q=np.linspace(a,b,65);occ,unknown=visibility(q,np.array(cam['centre']),scene);px,_=projection(q,cam);edges.append(dict(polyline_px=px.tolist(),occluded=occ.tolist(),visibility_unknown=unknown.tolist()))
 return dict(A_px=uv[0].tolist(),Aprime_px=uv[-1].tolist(),line_polyline_px=uv.tolist(),line_xyz=P.tolist(),line_occluded=oc.tolist(),line_visibility_unknown=unk.tolist(),line_points_inside_image=inside.tolist(),line_draw_mask=(getcase(c)['annotation_display_mask'] if c['id'].startswith('c2') else [True]*(len(P)-1)),box_corners_px=bp.tolist(),box_corners_local_xyz=box.tolist(),box_edges=edges,box_corner_occluded=visibility(box,np.array(cam['centre']),scene)[0].tolist(),occlusion_rule='original MVS ray hit more than 0.15m before target; no hit is not occluded but flagged unknown')

def building_support(c):
 bp=PH/'main_widen0_v2/PHD-MAIN-WIDEN0-v2/inputs/lod2_buildings.json';bid=selected(c)['selection']['building_identity'];b=next(b for b in json.loads(bp.read_text()) if b['id']==bid);pol=unary_union([Polygon(np.asarray(p['ext'])[:,:2]-SHIFT[:2],[np.asarray(h)[:,:2]-SHIFT[:2] for h in p['holes'] if len(h)>3]).buffer(0) for p in b['surfaces']['ground']]);row,_=data(c);P=row['xyz'];mask=contains(pol.buffer(.25),P[:,0],P[:,1]);part=P[mask];support=part;order=np.argsort(-part[:,2],kind='stable');_,uniq=np.unique(np.floor(part[order,:2]/.75).astype('i8'),axis=0,return_index=True);roof=part[order[uniq]];roof=roof[np.linspace(0,len(roof)-1,min(2000,len(roof))).astype(int)];savez(W9/'building_support'/f"{c['id']}.npz",roof=roof);hull=ConvexHull(support);return support[hull.vertices],dict(building_id=bid,source=proof(bp),support_rule='3D convex hull of stage1 reference rows within GroundSurface XY buffered 0.25m; raw LoD2 Z never used, footprint identity only',n_reference_support=int(mask.sum()))

def choose(keys):
 assert sha(C/'addendum9_photo_angle_fallback.json')==json.loads((C/'addendum9_photo_angle_fallback.lock.json').read_text())['config_sha256']
 assert sha(C/'addendum9_photo_frame.json')==json.loads((C/'addendum9_photo_frame.lock.json').read_text())['config_sha256']
 c=case(keys[0]);cam=cameras(c['site']);support,supportmeta=building_support(c);lines=[line9(k) for k in keys];mesh=meshpath(c,'mvs');V,F=read_surface(mesh);scene=MeshScene(V,F);top=float(V[:,2].max()+1);del V,F;gc.collect();candidates=[]
 fallback=json.loads((C/'addendum9_photo_fallback.json').read_text());assert sha(C/'addendum9_photo_fallback.json')==json.loads((C/'addendum9_photo_fallback.lock.json').read_text())['config_sha256']
 def drape(q):
  q=np.asarray(q).copy();origin=q.copy();origin[:,2]=top;hit=scene.cast(origin,np.tile([0.,0.,-1.],(len(q),1)));good=np.isfinite(hit);q[good,2]=top-hit[good]+.03;return q,good
 roof,roofhit=drape(loadz(W9/'building_support'/f"{c['id']}.npz")['roof']);roof=roof[roofhit];proxies=[drape(l['annotation_xyz'])[0] for l in lines]
 for j,name in enumerate(cam.names):
  el=float(np.degrees(np.arcsin(np.clip(-cam.R[j,2]@UP,-1,1))))
  if not 30<=el<=70:continue
  uv,depth=native(support,cam,j);inside=(depth>0)&((uv>=0)&(uv<[cam.w,cam.h])).all(1)
  if not inside.any():continue
  crop=bounds_crop(uv,cam.w,cam.h);fits=(crop[0]>=0 and crop[1]>=0 and crop[2]<=cam.w and crop[3]<=cam.h);target_inside=[];target_visibility=[];proxy_visible=[]
  roofocc,_=visibility(roof,cam.centres[j],scene);roof_visibility=float((~roofocc).mean())
  for proxy in proxies:
   proxyocc,_=visibility(proxy,cam.centres[j],scene);proxy_visible.append(float((~proxyocc).mean()))
  for line in lines:
   pts=np.array(line['annotation_xyz']);q,z=native(pts,cam,j);inside_line=(z>0)&((q>=0)&(q<[cam.w,cam.h])).all(1);oc,_=visibility(pts,cam.centres[j],scene);target_inside.append(float(inside_line.mean()));target_visibility.append(float((~oc&inside_line).mean()))
  if not min(target_inside):continue
  area=float(ConvexHull(uv).volume) if len(uv)>=3 else 0.;occupancy=area/((crop[2]-crop[0])*(crop[3]-crop[1]));candidates.append(dict(j=j,name=name,optical_axis_elevation_deg=el,building_in_image_fraction=float(inside.mean()),whole_building_in_image=bool(inside.all() and fits),crop_xyxy_px=crop.tolist(),crop_fits=bool(fits),building_occupancy=occupancy,target_inside=target_inside,target_visible=target_visibility,target_unoccluded=bool(min(target_visibility)==1),MVS_roof_visible_fraction=roof_visibility,MVS_proxy_target_visible=proxy_visible))
 assert candidates,'no optical elevation candidate'
 strict=[r for r in candidates if r['optical_axis_elevation_deg']<=60 and r['whole_building_in_image'] and r['target_unoccluded'] and r['MVS_roof_visible_fraction']>=.98]
 targetfull=[r for r in candidates if min(r['target_inside'])==1]
 if strict:best=max(strict,key=lambda r:(r['building_occupancy'],-r['j']));rule='all requested constraints; greatest building occupancy'
 else:
  pool=targetfull or candidates;best=max(pool,key=lambda r:(r['whole_building_in_image'],min(r['MVS_proxy_target_visible'])>=.98,r['MVS_roof_visible_fraction']>=.98,min(r['MVS_proxy_target_visible']),r['MVS_roof_visible_fraction'],-max(r['optical_axis_elevation_deg']-60,0),r['building_occupancy'],-r['j']));rule='no strict view; whole-building frame, MVS-draped target and roof >=98% visibility, then proxy target visibility, roof coverage, occupancy'
 j=best['j'];crop=np.array(best['crop_xyxy_px'])
 if not best['crop_fits']:
  w=min(cam.w,cam.h*1.25);h=w/1.25;mid=np.mean(np.concatenate([native(np.array(l['annotation_xyz']),cam,j)[0] for l in lines]),axis=0);mid=np.clip(mid,[w/2,h/2],[cam.w-w/2,cam.h-h/2]);crop=np.r_[mid-[w/2,h/2],mid+[w/2,h/2]]
 image,source=undistort_crop(cam,j,crop,[1600,1280]);params=np.r_[cam.p[:4],np.zeros(8)];meta=dict(name=cam.names[j],j=j,parameters=params.tolist(),original_FULL_OPENCV_parameters=cam.p.tolist(),R=cam.R[j].tolist(),t=cam.t[j].tolist(),centre=cam.centres[j].tolist(),crop_xyxy_px=crop.tolist(),source_size_px=[cam.w,cam.h],output_size_px=[1600,1280],calibration_model='undistorted pinhole with original fx fy cx cy',optical_axis_elevation_deg=best['optical_axis_elevation_deg'],source=source,training_camera=True,selection=best,selection_rule=rule,strict_candidates=len(strict),eligible_training_candidates=len(candidates),building_support=supportmeta,fallback_policy=proof(C/'addendum9_photo_fallback.json'),framing_policy=proof(C/'addendum9_photo_frame.json'),angle_fallback_policy=proof(C/'addendum9_photo_angle_fallback.json'))
 dump(W9/('photo_selection_'+keys[0]+'.json'),dict(selected=meta,candidates=candidates,scientific_verdict=None));print('ADD9_PHOTO_CHOICE',keys,meta['name'],best['target_visible'],rule,flush=True)
 for key,line in zip(keys,lines):
  cc=case(key);row,lab=data(cc);uv,depth=projection(row['xyz'],meta);inside=(depth>0)&((uv>=0)&(uv<[1600,1280])).all(1);ids=np.flatnonzero(inside);oc,unk=visibility(row['xyz'][ids],cam.centres[j],scene);vis=ids[~oc];counts={str(k):dict(visible=int((lab[vis]==k).sum()),occluded=int((lab[ids[oc]]==k).sum()),outside_image=int(((lab==k)&~inside).sum()),unknown_depth_visible=int((lab[ids[~oc&unk]]==k).sum())) for k in range(5)};ann=annotation9(cc,line,meta,scene);base=dict(case=cc['id'],camera=meta,visibility_mesh=proof(mesh),case_point_counts=counts,case_colors=A9['case_colors'],paint_order_case_ids=A9['paint_order'],point_diameter_px=6,point_alpha=.6,**ann);sources=[root_of(cc)/'rows.npz',root_of(cc)/'stage1_cells.npz',mesh,Path(__file__)];save9(image,key+'_photo',dict(**base,case_points_drawn=False),sources);color=circles(image,uv[vis],lab[vis],A9['case_colors'],A9['paint_order']);save9(color,key+'_photo_cases',dict(**base,case_points_drawn=True),sources);desat=ImageEnhance.Color(image).enhance(.35);save9(circles(desat,uv[vis],lab[vis],A9['case_colors'],A9['paint_order']),key+'_photo_cases_desat',dict(**base,case_points_drawn=True,saturation=.35),sources);savez(W9/'photo_points'/f'{key}.npz',visible_row_ids=vis,occluded_row_ids=ids[oc],pixel_xy=uv[vis]);dump(W9/(key+'_camera.json'),meta)
 del scene;gc.collect()
if __name__=='__main__':
 if 'angles' in sys.argv:
  for site in SITES:
   cam=cameras(site);el=np.degrees(np.arcsin(np.clip(-cam.R[:,2]@UP,-1,1)));print(site,len(el),np.percentile(el,[0,10,25,50,75,90,100]).tolist(),int(((el>=30)&(el<=60)).sum()),flush=True)
  sys.exit(0)
 groups=[['c1'],['c2','c3'],['c4']] if len(sys.argv)==1 else [['c2','c3']]
 for keys in groups:choose(keys)
