from common import *
from visibility import wall_data,prior_scene,visible
from photos import cameras
import open3d as o3d
d=wall_data('B173nb_b10__LoD2');v=loadz(O/'visibility/B173nb_b10__LoD2_face53.npz');cam=cameras('B173nb_b10');ids=np.flatnonzero((d['surf']==53)&(v['count']>0));scene,sources=prior_scene('B173nb_b10');rows=[]
for j in np.flatnonzero(np.unpackbits(v['packed_views'],axis=1)[:,:len(cam.names)].any(0)):
    P=d['centre'][ids];N=d['normal'][ids];vec=cam.centres[j]-P;dist=np.linalg.norm(vec,axis=1);unit=vec/dist[:,None];angle=np.degrees(np.arccos(np.clip((unit*N).sum(1),-1,1)));uv,_,guard=cam.project(P,int(j));rays=np.c_[np.broadcast_to(cam.centres[j],P.shape),-unit].astype('f4');hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=4)['t_hit'].numpy()
    rows.append(dict(camera=cam.names[j],patches=len(P),incidence_min_degrees=float(angle.min()),incidence_max_degrees=float(angle.max()),under_60_degrees=int((angle<=60).sum()),range_minus_hit_min_m=float((dist-hit).min()),range_minus_hit_max_m=float((dist-hit).max()),pixel_bounds=[uv.min(0).tolist(),uv.max(0).tolist()],height_range_m=[float(P[:,2].min()),float(P[:,2].max())]))
dump(D/'provenance/face53_check.json',dict(at=now(),source=source(O/'visibility/B173nb_b10__LoD2_face53.npz'),rows=rows,scientific_verdict=None));print(json.dumps(rows,ensure_ascii=False))
