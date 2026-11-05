"""Count every eligible training view at each wall patch, CPU ray queries only."""
from common import *
from photos import cameras
from measure import component
import open3d as o3d

def prior_scene(site,tile=None,prior='LoD2'):
    scene=o3d.t.geometry.RaycastingScene(nthreads=4);sources=[]
    folder=DR/'s02_box'/site if site!='outside' else W/'holdout/internal/prior_tiles'/tile
    for model in [prior]+(['ALS'] if prior=='LoD2' else []):
        path=folder/('lod2_mesh.npz' if model=='LoD2' else 'als_mesh.npz');m=loadz(path)
        reg=S0/'s61/box'/site/model/'summary.json' if site!='outside' else W/'holdout/internal/registration'/tile/model/'summary.json'
        shift=np.asarray(json.loads(reg.read_text())['registration']['shift_applied']);F=m['F']
        if model=='ALS' and prior=='LoD2':F=F[(m['cls'][F]==2).sum(1)>=2]
        scene.add_triangles(o3d.core.Tensor((m['V']+shift).astype('f4')),o3d.core.Tensor(F.astype('u4')))
        sources.extend([source(path),source(reg)])
    return scene,sources

def visible(P,N,cam,j,scene,corners=None):
    v=cam.centres[j]-P;dist=np.linalg.norm(v,axis=1);unit=v/dist[:,None]
    ii=np.flatnonzero(np.einsum('ij,ij->i',unit,N)>=np.cos(np.deg2rad(80)))
    if not len(ii):return ii
    uv,_,guard=cam.project(P[ii],j);ok=guard&(uv[:,0]>=20)&(uv[:,0]<cam.w-20)&(uv[:,1]>=20)&(uv[:,1]<cam.h-20);ii=ii[ok]
    if not len(ii):return ii
    rays=np.c_[np.broadcast_to(cam.centres[j],(len(ii),3)),-unit[ii]].astype('f4');hit=scene.cast_rays(o3d.core.Tensor(rays),nthreads=4)['t_hit'].numpy()
    return ii[dist[ii]<=hit+.3]

def wall_data(stem):
    if stem.startswith('outside'):
        d=loadz(O/'data'/f'{stem}.npz',['xyz','normal','t1','t2','surf','kind','area','building','patch_id','tile']);d['centre']=d.pop('xyz');d['tangent1']=d.pop('t1');d['tangent2']=d.pop('t2')
    else:
        d=loadz(O/'patches'/f'{stem}.npz');d['centre']=d['centre']+np.nan_to_num(d['prior_height_m'])[:,None]*d['normal']
    return d

def main(stem,force_only=False):
    cfg();site=stem.split('__')[0];out=O/'visibility'/f'{stem}{"_face53" if force_only else ""}.npz'
    if out.exists():return
    d=wall_data(stem);n=len(d['kind']);selected=np.zeros(n,bool);candidates=[]
    if not force_only:
        metrics=json.loads((O/'metrics'/f'{stem}.json').read_text())['rows']
        for r in metrics:
            count=sum([r['c1_roof_m2']>=4,r['c2_m2']>=4,r['c3a_m2']>=4,r['c3b_m']>=3])
            if count>=2:candidates.append(r['building'])
        selected=(d['kind']==2)&np.isin(d['building'],candidates)
    if site=='B173nb_b10':selected|=(d['kind']==2)&(d['surf']==53)
    indices=np.flatnonzero(selected);cam=cameras(site);bits=np.zeros((len(indices),len(cam.names)),bool);counts=np.full(n,-1,'i4');sources=[]
    tiles=[None] if site!='outside' else sorted(np.unique(d['tile'][indices]));started=time.monotonic()
    for tile in tiles:
        sub=np.arange(len(indices)) if tile is None else np.flatnonzero(d['tile'][indices]==tile)
        if not len(sub):continue
        scene,ss=prior_scene(site,tile);sources.extend(ss);ids=indices[sub];P=d['centre'][ids];N=d['normal'][ids]
        for j in range(len(cam.names)):
            ok=visible(P,N,cam,j,scene);bits[sub[ok],j]=True
        del scene;gc.collect();print('WALL_VIEWS',stem,tile,len(sub),'seconds',round(time.monotonic()-started,1),flush=True)
    counts[indices]=bits.sum(1)
    savez(out,count=counts,indices=indices,packed_views=np.packbits(bits,axis=1),camera_names=np.asarray(cam.names))
    meta=dict(at=now(),stem=stem,candidates=candidates,measured_patches=len(indices),sources=sources,angle_max_deg=80,image_margin_px=20,occlusion_tolerance_m=.3,
        rule='inherited centre projection with original FULL_OPENCV; exact registered prior triangle ray intersection plus inherited class-2 terrain; all training cameras; no ten-view cap',scientific_verdict=None)
    if site=='B173nb_b10':
        mask=(d['surf']==53)&(d['kind']==2);v=counts[mask]
        meta['face53']=dict(patches=len(v),minimum=int(v.min()),maximum=int(v.max()),zero_patches=int((v==0).sum()),all_zero=bool((v==0).all()),area_m2=float(d['area'][mask].sum()),visible_camera_names=[cam.names[j] for j in np.flatnonzero(bits[(d['surf'][indices]==53)].any(0))])
    dump(out.with_suffix('.json'),meta);print('VISIBILITY_DONE',stem,len(indices),meta.get('face53',{}),flush=True)
if __name__=='__main__':main(sys.argv[1],len(sys.argv)>2)
