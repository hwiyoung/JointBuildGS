"""Exact original-mesh rays and analytic reference discs; never re-score."""
from add10_common import *

def annotate(cam,c,scene):
 line=line9(c['id'].split('_')[0]);P=np.array(line['annotation_xyz']);box=np.array(json.loads((T10/(c['id'].split('_')[0]+'_boxes.json')).read_text())['panel1_box_corners_local_xyz']);W,H=cam['output_size_px']
 def values_at(Q):
  uv,z=project(Q,cam)
  if cam['projection']=='orthographic':origin=Q.copy();origin[:,2]=cam['origin_z_m'];direction=np.tile([0.,0.,-1.],(len(Q),1));distance=origin[:,2]-Q[:,2]
  else:origin=np.broadcast_to(cam['centre'],Q.shape).copy();direction=Q-origin;distance=np.linalg.norm(direction,axis=1);direction/=distance[:,None]
  hit=scene.cast(origin,direction);oc=np.isfinite(hit)&(hit<distance-.15);inside=(z>0)&((uv>=0)&(uv<[W,H])).all(1)
  return uv,oc,inside,~np.isfinite(hit)
 px,oc,inside,unknown=values_at(P);bp,bo,bi,bu=values_at(box);drawmask=getcase(c).get('annotation_display_mask',np.ones(len(P)-1,bool).tolist()) if c['id'].startswith('c2') else np.ones(len(P)-1,bool).tolist()
 return dict(A_px=px[0].tolist(),Aprime_px=px[-1].tolist(),line_polyline_px=px.tolist(),line_local_xyz=P.tolist(),line_occluded=oc.tolist(),line_points_inside_image=inside.tolist(),line_visibility_unknown=unknown.tolist(),line_draw_mask=drawmask,box_corners_px=bp.tolist(),box_corners_local_xyz=box.tolist(),box_corner_occluded=bo.tolist(),box_corners_inside_image=bi.tolist(),box_visibility_unknown=bu.tolist(),occlusion_rule='original stage1 MVS proxy, hit more than 0.15m before annotation; no mesh hit separately marked unknown',line_drawn=False,box_drawn=False)

def refmap(key,job,index,radius):
 stem=key+'_'+job['id'];path=F10/(stem+'_refrow.npz');cam=job['camera'];W,H=cam['output_size_px']
 if path.exists():return
 ids=np.full((H,W),-1,'i4');depth=np.full((H,W),np.inf,'f4')
 for y in range(0,H,64):
  y1=min(y+64,H);origin,direction=ray_rows(cam,y,y1);idx,dd=index.query('disc_rows',origin,direction,radius);ids[y:y1]=idx.reshape(y1-y,W);depth[y:y1]=dd.reshape(y1-y,W)
 savez(path,row_id=ids);savez(W10/'refdepth'/(stem+'.npz'),depth_m=depth)
 dump(F10/(stem+'_camera.json'),record(dict(case=key,camera_id=job['id'],camera=cam,crop=cam.get('crop_xyxy_px'),matched_image=job['matched_image'],reference_disc_radius_m=radius,disc_rule=A10['reference_disc'],refrow_file=path.name,refrow_npz_key='row_id',row_id_dtype='int32',pixel_origin='top-left; sample at x+0.5,y+0.5',refrow_hit_pixels=int((ids>=0).sum()),size_px=[W,H],text_in_figure=False),[Path(job['source']),root_of(case(key))/'rows.npz']))
 print('ADD10_REFDISC',stem,int((ids>=0).sum()),flush=True)

def mesh_render(key,job,m,scene,index,path):
 stem=key+'_'+job['id']+'_'+m;meta_path=F10/(stem+'.json');cam=job['camera'];W,H=cam['output_size_px']
 if meta_path.exists():return
 ids=np.full((H,W),-1,'i4');depth=np.full((H,W),np.inf,'f4');shade=np.full((H,W),255,'u1');maxside=0.;hitcount=0;unmapped=0
 for y in range(0,H,64):
  y1=min(y+64,H);origin,direction=ray_rows(cam,y,y1);rr=np.c_[origin,direction].astype('f4');z=scene.sc.cast_rays(scene.o3d.core.Tensor(rr));t=z['t_hit'].numpy();ok=np.isfinite(t);nr=z['primitive_normals'].numpy()[ok].astype(float);nr/=np.linalg.norm(nr,axis=1)[:,None]
  # Query at the actual float32 mesh-ray hit, not a recomputed double ray.
  Q=rr[ok,:3].astype(float)+t[ok,None]*rr[ok,3:].astype(float);ri,side=index.query('assign_rows',Q,nr,A10['row_cylinder_radius_m']);tmp=np.full(len(t),-1,'i4');tmp[ok]=ri;ids[y:y1]=tmp.reshape(y1-y,W)
  actual=t.astype(float)*np.linalg.norm(rr[:,3:].astype(float),axis=1);depth[y:y1]=actual.reshape(y1-y,W);sh=np.full(len(t),255,'u1');sh[ok]=np.rint(255*(.55+.45*np.clip(abs(np.einsum('ij,ij->i',nr,direction[ok])),0,1))).astype('u1');shade[y:y1]=sh.reshape(y1-y,W);hitcount+=int(ok.sum());unmapped+=int((ri<0).sum());maxside=max(maxside,float(side[np.isfinite(side)].max(initial=0)))
 hit=np.isfinite(depth);Image.fromarray((hit*255).astype('u1')).save(F10/(stem+'_hit.png'),dpi=(300,300));Image.fromarray(shade).save(F10/(stem+'_shade.png'),dpi=(300,300));savez(F10/(stem+'_depth.npz'),depth_m=depth);savez(F10/(stem+'_row.npz'),row_id=ids)
 dump(meta_path,record(dict(case=key,method=m,camera_id=job['id'],camera_metadata=key+'_'+job['id']+'_camera.json',size_px=[W,H],mesh=proof(path),mesh_changed=False,removed_triangles=0,hit_pixels=hitcount,hit_without_reference_row=unmapped,row_query_radius_m=.3,row_query_objective=A10['row_objective'],tie_break=A10['row_tie_break'],maximum_selected_side_distance_m=maxside,depth_definition=A10['depth'],npz_keys={'depth':'depth_m','row':'row_id'},shade_definition=A10['shade'],light_direction='negative normalized per-pixel camera ray; two-sided',pixel_center=[.5,.5],no_hit_row_id=-1,new_scoring_distances=False,saved_stage1_scores_source=proof(stored_scores(case(key))[m]),photo_background=False,line_drawn=False,text_in_figure=False),[path,Path(__file__),Path(__file__).with_name('add10_geometry.cpp')]))
 print('ADD10_MESH',stem,hitcount,unmapped,flush=True)

def main(key):
 c=case(key);row,_=data(c);info=json.loads((W10/(key+'_scene.json')).read_text());jobs=json.loads((W10/(key+'_cameras.json')).read_text());index=ReferenceIndex(row['xyz'],row['normal']);radius=info['radius_m']
 for job in jobs:refmap(key,job,index,radius)
 for m in A10['render_methods']+(A10['c4_extra'] if key=='c4' else []):
  path=meshpath(c,m);expected=json.loads((root_of(c)/'distances'/(m+'.json')).read_text())['mesh_sha256'];assert proof(path)['sha256']==expected;V,F=read_surface(path);scene=MeshScene(V,F);del V,F;gc.collect()
  for job in jobs:
   mesh_render(key,job,m,scene,index,path)
   if m=='mvs':
    p=F10/(key+'_'+job['id']+'_camera.json');meta=json.loads(p.read_text());meta.update(annotate(job['camera'],c,scene));meta['occlusion_mesh']=proof(path);dump(p,meta)
  del scene;gc.collect()
 index.close();print('ADD10_CASE_RENDER_DONE',key,flush=True)

if __name__=='__main__':main(sys.argv[1])
