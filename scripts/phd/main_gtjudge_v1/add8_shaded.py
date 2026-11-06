"""Add shading to exact saved distance-render pixels; no new distances or cameras."""
from add6_common import *
from add6_render import palette
from add4_render import rays
from add4_viewclip import faces

A8=json.loads((C/'addendum8.json').read_text())
assert sha(C/'addendum8.json')==json.loads((C/'addendum8.lock.json').read_text())['config_sha256']
W8=O/'addendum8';F8=D/'figures/addendum8';T8=D/'tables/addendum8'
for folder in [W8,F8,T8]:folder.mkdir(parents=True,exist_ok=True)

def binding(job):
 c=case(job['case']);method=job['method'];stem=c['id']+('_wrong_dist_noline' if method=='prior' else '_wrong_dist_v2' if method=='mvs' else '_result_dist_'+method)
 meta_path=F6/(stem+'.json');meta=json.loads(meta_path.read_text());cache=AW/'renders'/f"{c['id']}_pixel_distance.npz" if method=='prior' else W6/'render_cache'/f'{stem}.npz';path=meshpath(c,method)
 mesh_meta=json.loads((root_of(c)/'distances'/f'{method}.json').read_text());assert proof(path)['sha256']==mesh_meta['mesh_sha256']
 if method=='prior':
  prior_meta=json.loads((AF/f"{c['id']}_wrong_dist.json").read_text());assert prior_meta['camera']==meta['camera'];assert next(x['sha256'] for x in prior_meta['sources'] if x['path']==str(path))==mesh_meta['mesh_sha256']
 else:assert meta['mesh']['path']==str(path) and meta['mesh']['sha256']==mesh_meta['mesh_sha256']
 assert meta['camera']['name']==job['camera_name'];assert meta['line_drawn'] is False
 return c,method,stem,meta_path,meta,cache,path

def classify(ids,signed,tau):
 good=ids>=0;assert np.isfinite(tau[good]).all();out=np.zeros(ids.shape,'u1');finite=good&np.isfinite(signed)
 out[finite&(abs(signed)<=tau)]=1;out[finite&(signed>tau)]=2;out[finite&(signed < -tau)]=3;out[good&~np.isfinite(signed)]=4;assert np.array_equal(out>0,good)
 return out

def render(job):
 c,method,stem,meta_path,meta,cache,path=binding(job);cam=meta['camera'];z=loadz(cache);ids=z['face_id'];signed=z['signed_result_minus_reference_m'] if method=='prior' else z['signed'];tau=z['tau'];W,H=cam['output_size_px'];assert ids.shape==(H,W);category=classify(ids,signed,tau);good=category>0
 base=palette(ids,signed,tau);old=np.asarray(Image.open(F6/(stem+'.png')).convert('RGB'));assert np.array_equal(old,base),'Saved distances must reproduce every original unmarked pixel'
 V,F=read_surface(path)
 if method=='prior':F=faces(V,F,cam)
 removed=meta.get('removed_original_triangle_ids',[])
 if removed:keep=np.ones(len(F),bool);keep[removed]=False;F=F[keep]
 assert ids[good].min()>=0 and ids[good].max()<len(F);V=np.asarray(V,'f4');shade=np.ones((H,W),'f4');ambient,diffuse=A8['lighting']['ambient'],A8['lighting']['diffuse']
 for y in range(0,H,100):
  y1=min(y+100,H);part=ids[y:y1].ravel();take=part>=0;_,direction=rays(cam,y,y1);tri=V[F[part[take]]];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);size=np.linalg.norm(normal,axis=1);assert np.isfinite(size).all() and (size>0).all();normal/=size[:,None];light=-direction[take]/np.linalg.norm(direction[take],axis=1)[:,None];lambert=np.clip(abs((normal*light).sum(1)),0,1);shade[y:y1].reshape(-1)[take]=ambient+diffuse*lambert
 arr=np.full_like(base,255);arr[good]=np.rint(base[good].astype(float)*shade[good,None]).clip(0,255).astype('u1');outstem=c['id']+'_'+method+'_dist_shaded';p=F8/(outstem+'.png');assert not p.exists(),'Preserve an existing delivered image'
 Image.fromarray(arr).save(p,icc_profile=ICC,dpi=(300,300));counts={name:int((category==i).sum()) for i,name in enumerate(['background','within_tau','above','below','no_reference'])};visible=int(good.sum());percent={k:100*v/visible for k,v in counts.items() if k!='background'};_,directions=rays(cam,H//2,H//2+1);center=-directions[W//2];center/=np.linalg.norm(center)
 sources=[path,cache,F6/(stem+'.png'),meta_path,C/'addendum8.json',Path(__file__),Path(__file__).with_name('add4_render.py'),Path(__file__).with_name('add6_render.py')]
 record=dict(at=now(),case=c['id'],method=method,size_px=[W,H],camera=cam,mesh=proof(path),source_render=proof(F6/(stem+'.png')),source_render_metadata=proof(meta_path),saved_pixel_cache=proof(cache),removed_original_triangle_ids=removed,display_clip=cam.get('display_clip'),light_direction=dict(model='camera headlight, per-pixel direction toward the camera, inherited from addendum4',source_local_xyz=cam['centre'],center_pixel_toward_light_unit_xyz=center.tolist(),direction_rule='negative normalized original camera ray',two_sided=True),shading_brightness_range=[.55,1.0],actual_visible_brightness_range=[float(shade[good].min()),float(shade[good].max())],lighting_formula='0.55 + 0.45 * abs(unit_triangle_normal dot unit_direction_toward_camera)',rgb_rule='multiply the exact original 8-bit sRGB pixel by brightness; within-tau base [255,255,255] becomes gray; background remains white',base_color_rule='same saved oriented normal-cylinder distances: white within tau, red above, blue below, saturation at abs 1m, no reference #8C95A3',base_palette={'within_tau':'#FFFFFF','positive_endpoint':'#D83730','negative_endpoint':'#2A78D6','no_reference':'#8C95A3','background':'#FFFFFF'},pixel_counts=counts,visible_mesh_pixels=visible,pixel_percent_visible_mesh=percent,pixel_percent_whole_image={k:100*v/(W*H) for k,v in counts.items()},original_unshaded_pixels_exact=True,classifications_identical_to_original=True,reference_distances_reused=True,new_distances_calculated=False,scoring_values_changed=False,line_drawn=False,text_in_figure=False,new_camera=False,color_space='sRGB',crs='EPSG:25832',local_world_shift=SHIFT.tolist(),runtime=dict(image=os.environ.get('GTJUDGE_IMAGE'),source_commit=os.environ.get('GTJUDGE_COMMIT'),python=sys.version,numpy=np.__version__),config_sha256=sha(C/'addendum8.json'),sources=[proof(x) for x in sources],scientific_verdict=None)
 dump(p.with_suffix('.json'),record);savez(W8/'pixels'/f'{outstem}.npz',brightness=shade,category=category);print('ADD8_SHADED',outstem,json.dumps(percent),flush=True)

def main():
 inputs=[C/'addendum8.json',Path(__file__),Path(__file__).with_name('add4_render.py'),Path(__file__).with_name('add6_render.py')]
 for job in A8['jobs']:
  c,method,stem,mp,meta,cache,path=binding(job);inputs.extend([mp,cache,path,F6/(stem+'.png')])
 dump(W8/'input_lock.json',dict(at=now(),sources=[proof(p) for p in dict.fromkeys(inputs)],config_sha256=sha(C/'addendum8.json'),scientific_verdict=None))
 for job in A8['jobs']:render(job);gc.collect()

if __name__=='__main__':main()
