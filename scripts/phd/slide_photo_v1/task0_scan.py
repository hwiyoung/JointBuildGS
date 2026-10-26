"""Recompute candidate evidence from input arrays only, never WIDEN outcomes.

Public NPZ geometry is read via an explicit allowlist. No path under holdout is
opened. All derived values are new measurements for this order.
"""
import sys,time,json
from concurrent.futures import ProcessPoolExecutor
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from PIL import Image
from common import *
_s=importlib.util.spec_from_file_location('face_core','/repo/scripts/phd/main_uncert_v1/u_core.py')
core=importlib.util.module_from_spec(_s);_s.loader.exec_module(core)
DT=np.dtype([('x','<f8'),('y','<f8'),('z','<f8'),('cls','u1'),('multi','u1')])

def points(tile):
    p=W/'inputs/points'/tile/'uls.bin';a=np.memmap(p,mode='r',dtype=DT)
    x=np.column_stack([a[k] for k in ['x','y','z']])
    shift=load(S1/'v3/align/common_shift.json')['common_shift_m'];x[:,2]+=shift
    return x

def gt_tile(tile):
    started=time.monotonic();c=config();out=PAY/'task0/gt';out.mkdir(parents=True,exist_ok=True)
    X=points(tile);tree=cKDTree(X);print('GT begin',tile,len(X),flush=True)
    for prior in ['ALS','LoD2']:
        target=out/f'{tile}_{prior}.npz'
        if target.exists():continue
        z=geometry(tile,prior);C=z['centre'];n=len(C)
        gp=np.full(n,np.nan);ga=np.full(n,np.nan);gn=np.zeros(n,np.int32);gr=np.zeros(n,np.int8);rep=np.full((n,3),np.nan)
        for face in np.unique(z['face_ext']):
            ix=np.flatnonzero((z['face_ext']==face)&z['normal_defined'])
            if not len(ix):continue
            P=C[ix];normal=np.median(z['normal'][ix],axis=0);normal/=max(np.linalg.norm(normal),1e-9)
            e1,e2=core.in_plane_basis(normal);cent=(P.min(0)+P.max(0))/2
            H=10. if np.median(z['roof_like'][ix]) else 3.
            ids=tree.query_ball_point(cent,np.linalg.norm(P.max(0)-P.min(0))/2+H+.3)
            if not len(ids):continue
            Q=X[ids];pq=Q-cent;pc=P-cent
            d,j=cKDTree(np.c_[pc@e1,pc@e2]).query(np.c_[pq@e1,pq@e2],distance_upper_bound=.19)
            ok=np.isfinite(d);Q=Q[ok];j=ix[j[ok]];V=Q-C[j]
            t=np.einsum('ij,ij->i',V,z['normal'][j]);a=np.einsum('ij,ij->i',V,z['tangent1'][j]);b=np.einsum('ij,ij->i',V,z['tangent2'][j])
            ok=(np.abs(a)<=.1250001)&(np.abs(b)<=.1250001)&(np.abs(t)<=H)
            Q,j,t=Q[ok],j[ok],t[ok];order=np.argsort(j,kind='stable');Q,j,t=Q[order],j[order],t[order]
            cut=np.r_[0,np.flatnonzero(np.diff(j))+1,len(j)]
            for lo,hi in zip(cut[:-1],cut[1:]):
                if hi==lo:continue
                k=j[lo];tt=t[lo:hi]
                o,runs,total=core.find_face(tt,H,dict(layer_thickness_m=.3,layer_step_m=.05,layer_share=.2));gr[k]=min(runs,127)
                if o is None:continue
                keep=np.abs(tt-o)<=.1500001;v=tt[keep]
                if not len(v):continue
                gp[k]=np.median(v);ga[k]=np.median(np.abs(v));gn[k]=len(v)
                qq=Q[lo:hi][keep];rep[k]=qq[np.argmin(np.abs(v-gp[k]))]
        density=gn/np.maximum(z['area'],1e-12)
        eligible=(density>=np.where(z['roof_like'],100,30))&(ga<=c['task0']['tau_m'][prior])&(gr==1)
        # LoD2 is a fallback only where no ALS support exists, regardless of ALS outcome.
        if prior=='LoD2':
            az=geometry(tile,'ALS')
            if len(az['centre']):
                for face in np.unique(z['face_ext'][eligible]):
                    li=np.flatnonzero(eligible&(z['face_ext']==face));ai=np.flatnonzero(az['face_ext']==face)
                    if not len(ai):continue
                    nn=np.median(z['normal'][li],axis=0);nn/=max(np.linalg.norm(nn),1e-9);e1,e2=core.in_plane_basis(nn)
                    da,_=cKDTree(np.c_[az['centre'][ai]@e1,az['centre'][ai]@e2]).query(np.c_[C[li]@e1,C[li]@e2])
                    eligible[li[da<=.36]]=False
        np.savez_compressed(target,gt_signed=gp,prior_abs=ga,gt_count=gn,gt_density=density,gt_runs=gr,representative=rep,eligible=eligible)
        print('GT',tile,prior,'patches',n,'eligible',int(eligible.sum()),'seconds',round(time.monotonic()-started),flush=True)
    return tile

def cameras_depth():
    poses=G.poses(W/'mvs/full/sparse/images.bin');cams=G.cameras(W/'mvs/full/sparse/cameras.bin')
    cam=dict(next(iter(cams.values())));p=cam['p'].copy();p[[0,2]]*=1024/cam['w'];p[[1,3]]*=741/cam['h'];cam.update(p=p,w=1024,h=741)
    return poses,cam

def mvs_tile(tile):
    started=time.monotonic();c=config();out=PAY/'task0/mvs_v4';out.mkdir(parents=True,exist_ok=True)
    if (out/f'{tile}.json').exists():return tile
    from fast_zbuffer import fast
    assert load(PAY/'zbuffer_replay.json')['status']=='PASS'
    poses,cam=cameras_depth();data={};allq=[]
    global_meta=load(PAY/'task0/global_visibility/complete.json');global_index={n:i for i,n in enumerate(global_meta['names'])};global_buf=np.load(PAY/'task0/global_visibility/zbuffer.npy',mmap_mode='r')
    for prior in ['ALS','LoD2']:
        z=geometry(tile,prior);gg=dict(np.load(PAY/'task0/gt'/f'{tile}_{prior}.npz'));ix=np.flatnonzero(gg['eligible'])
        data[prior]=dict(z=z,g=gg,ix=ix,offset=len(allq));allq.extend(gg['representative'][ix])
    if not len(allq):dump(out/f'{tile}.json',dict(tile=tile,views=[],candidates=0));return tile
    Q=np.array(allq);N=np.concatenate([v['z']['normal'][v['ix']] for v in data.values()]);names=[]
    # Frustum eligibility depends only on input GT coordinates and camera poses.
    for name,p in sorted(poses.items()):
        uv,d=G.project(Q,p,cam);ij=np.floor(uv).astype(int);ok=(d>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741)
        if ok.any() and (W/'mvs/full/stereo/depth_maps'/f'{p["name"]}.geometric.bin').exists():names.append(name)
    err=np.full((len(Q),len(names)),np.nan,np.float32);rgb=np.full((len(Q),len(names),3),np.nan,np.float32);seen=np.zeros(len(Q),np.int32);passed=np.zeros(len(Q),np.int32)
    for vi,name in enumerate(names):
        p=poses[name];uv,zq=G.project(Q,p,cam);ij=np.floor(uv).astype(int);ok=(zq>0)&(ij[:,0]>=0)&(ij[:,0]<1024)&(ij[:,1]>=0)&(ij[:,1]<741)
        camera_centre=-p['R'].T@p['t'];ok &= np.einsum('ij,ij->i',N,camera_centre-Q)>0
        buf=global_buf[global_index[name]]
        ids=np.flatnonzero(ok);ids=ids[zq[ids]<=buf[ij[ids,1]*1024+ij[ids,0]]+.25]
        from solid_visibility import visible as solid_visible
        ids=ids[solid_visible(Q[ids],p,zq[ids])]
        seen[ids]+=1
        im=W/'mvs/full/images'/p['name']
        if im.exists():
            image=np.asarray(Image.open(im).convert('RGB').resize((1024,741),Image.Resampling.LANCZOS))/255.
            rgb[ids,vi]=image[ij[ids,1],ij[ids,0]]
        D=depth(W/'mvs/full/stereo/depth_maps'/f'{p["name"]}.geometric.bin');dd=D[ij[ids,1],ij[ids,0]];valid=np.isfinite(dd)&(dd>0);ids=ids[valid];dd=dd[valid]
        passed[ids]+=1
        fx,fy,cx,cy=cam['p'];uvc=ij[ids]+.5
        rays=np.c_[(uvc[:,0]-cx)/fx,(uvc[:,1]-cy)/fy,np.ones(len(ids))]@p['R']
        C=-p['R'].T@p['t'];M=C+rays*dd[:,None]
        err[ids,vi]=np.einsum('ij,ij->i',M-Q[ids],N[ids])
        if vi%40==0:print('MVS',tile,vi,len(names),'patches',len(Q),flush=True)
    import warnings
    def packed(a):
        finite=np.isfinite(a if a.ndim==2 else a[:,:,0]);ri,ci=np.nonzero(finite);counts=np.bincount(ri,minlength=len(a));starts=np.r_[0,np.cumsum(counts)[:-1]];rank=np.arange(len(ri))-np.repeat(starts,counts)
        out=np.full((len(a),max(1,int(counts.max())),*a.shape[2:]),np.nan,a.dtype);out[ri,rank]=a[ri,ci];return out
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        er=packed(err);rg=packed(rgb);absolute=np.nanmedian(np.abs(er),axis=1);signed=np.nanmedian(er,axis=1)
        colour=np.nanmedian(np.linalg.norm(rg-np.nanmedian(rg,axis=1)[:,None,:],axis=2),axis=1)
        check=np.linspace(0,len(Q)-1,min(512,len(Q)),dtype=int)
        assert np.allclose(absolute[check],np.nanmedian(abs(err[check]),axis=1),equal_nan=True)
        raw_colour=np.nanmedian(np.linalg.norm(rgb[check]-np.nanmedian(rgb[check],axis=1)[:,None,:],axis=2),axis=1)
        assert np.allclose(colour[check],raw_colour,equal_nan=True)
    count=0;offset=0
    for prior,v in data.items():
        num=len(v['ix']);sl=slice(offset,offset+num);threshold=max(.2,c['task0']['tau_m'][prior])
        cand=(absolute[sl]>threshold)&(passed[sl]>=2);count+=int(cand.sum())
        np.savez_compressed(out/f'{tile}_{prior}.npz',patch_index=v['ix'],mvs_abs=absolute[sl],mvs_signed=signed[sl],seen=seen[sl],passed=passed[sl],colour_scatter=colour[sl],candidate=cand,per_view_signed=err[sl],view_names=np.array(names))
        offset+=num
    dump(out/f'{tile}.json',dict(tile=tile,views=names,candidates=count,seconds=time.monotonic()-started,scientific_verdict=None))
    print('MVS DONE',tile,'candidates',count,'seconds',round(time.monotonic()-started),flush=True)
    return tile

def components():
    c=config();rows=[];pool=[];offset=0
    for t in load(W/'inputs/tiles.json'):
        tile=t['id']
        for prior in ['ALS','LoD2']:
            p=PAY/'task0/mvs_v4'/f'{tile}_{prior}.npz'
            if not p.exists():continue
            z=geometry(tile,prior);g=dict(np.load(PAY/'task0/gt'/f'{tile}_{prior}.npz'));m=dict(np.load(p));ids=np.flatnonzero(m['candidate']);ix=m['patch_index'][ids]
            if not len(ix):continue
            pool.append(dict(tile=tile,prior=prior,z={k:v[ix] for k,v in z.items()},g={k:v[ix] for k,v in g.items()},m={k:m[k][ids] for k in ['mvs_abs','mvs_signed','seen','passed','colour_scatter']}))
    for prior in ['ALS','LoD2']:
        pp=[p for p in pool if p['prior']==prior]
        if not pp:continue
        z={k:np.concatenate([p['z'][k] for p in pp]) for k in GEOMETRY_KEYS};g={k:np.concatenate([p['g'][k] for p in pp]) for k in pp[0]['g']};m={k:np.concatenate([p['m'][k] for p in pp]) for k in pp[0]['m']}
        # Ext IDs are tile-local: use stable building and a 15-degree normal gate
        # plus spatial connectivity across tile boundaries; within tile require face.
        tids=np.concatenate([np.full(len(p['z']['centre']),p['tile']) for p in pp]);pairs=cKDTree(z['centre']).query_pairs(.36,output_type='ndarray')
        if len(pairs):
            a,b=pairs.T;valid=(z['building'][a]==z['building'][b])&(z['roof_like'][a]==z['roof_like'][b])&(np.einsum('ij,ij->i',z['normal'][a],z['normal'][b])>=np.cos(np.deg2rad(15)))&((tids[a]!=tids[b])|(z['face_ext'][a]==z['face_ext'][b]));pairs=pairs[valid]
        n=len(z['centre']);graph=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(n,n));nc,labels=connected_components(graph,directed=False)
        for lab in range(nc):
            ix=np.flatnonzero(labels==lab);area=float(z['area'][ix].sum())
            rows.append(dict(prior=prior,building=str(z['building'][ix[0]]),roof=bool(z['roof_like'][ix[0]]),area_m2=area,patch_count=len(ix),mvs_abs_median_m=float(np.median(m['mvs_abs'][ix])),mvs_signed_median_m=float(np.median(m['mvs_signed'][ix])),prior_abs_median_m=float(np.median(g['prior_abs'][ix])),prior_signed_median_m=float(np.median(-g['gt_signed'][ix])),pass_share=float(m['passed'][ix].sum()/m['seen'][ix].sum()),colour_scatter=float(np.nanmedian(m['colour_scatter'][ix])),gt_density_min=float(g['gt_density'][ix].min()),patch_ids=z['patch_id'][ix].tolist(),centre=z['centre'][ix].tolist(),normal=z['normal'][ix].tolist(),gt_representative=g['representative'][ix].tolist(),tiles=sorted(set(tids[ix])),tau_m=c['task0']['tau_m'][prior]))
    rows.sort(key=lambda r:(-r['area_m2'],r['building'],r['patch_ids'][0]))
    for i,r in enumerate(rows):r['component_id']=f'candidate_{i+1:04d}'
    dump(PAY/'task0/components.json',dict(task_id=c['task_id'],source='[이 발주에서 냄]',components=rows,scientific_verdict=None))
    print('COMPONENTS',len(rows),'TOP',[(r['component_id'],r['area_m2'],r['mvs_abs_median_m']) for r in rows[:10]],flush=True)

if __name__=='__main__':
    stage=sys.argv[1]
    if stage=='components':components()
    else:
        tiles=[t['id'] for t in load(W/'inputs/tiles.json')]
        if len(sys.argv)>2:tiles=[sys.argv[2]]
        with ProcessPoolExecutor(max_workers=4) as pool:list(pool.map(gt_tile if stage=='gt' else mvs_tile,tiles))
