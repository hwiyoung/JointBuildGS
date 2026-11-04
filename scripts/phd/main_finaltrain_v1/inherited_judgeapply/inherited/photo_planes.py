"""Two candidate planes and exact masks for the frozen timing sample. CPU only."""
import json,time,zipfile,sys
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,D,O,Path,sha,dump,now
from geometry import loadz,savez,fit_normals
from cylinder import run
from selected_npz import selected
from prepare import array
from u_core import find_face
from ring_context import D as DEFINITIONS,W
from photo_cameras import Cameras,choose_mvs_views
BASE=O/'r1'
UV=np.stack(np.meshgrid(np.arange(25)*.02-.24,np.arange(25)*.02-.24,indexing='xy'),-1).reshape(625,2)

def tangent(n):
    a=np.array([1.,0.,0.]) if abs(n[0])<.9 else np.array([0.,1.,0.])
    e=a-n*(a@n);e/=np.linalg.norm(e)
    return e,np.cross(n,e)

def plane(q,reference):
    if len(q)<3:return None
    c=q.mean(0);v=q-c;val,vec=np.linalg.eigh(v.T@v)
    if val[1]<=1e-16:return None
    n=vec[:,0];n*=1 if n@reference>=0 else -1
    return c,n

def column(X,tree,c,n):
    probes=c+np.arange(-9.75,10,.5)[:,None]*n
    ids=np.unique(np.concatenate([np.asarray(a,int) for a in tree.query_ball_point(probes,np.hypot(.5,.25)+1e-6)]))
    v=X[ids]-c;t=v@n;rho2=np.maximum(0,np.sum(v*v,1)-t*t)
    keep=(rho2<=.25)&(abs(t)<=10);ids=ids[keep];t=t[keep]
    o,_,_=find_face(t,10,DEFINITIONS)
    if o is None:return np.empty((0,3))
    return X[ids[abs(t-o)<=1.]]

def fit_mvs(X,tree,c,n,hp,dbar):
    q=column(X,tree,c,n);q=q[abs((q-c)@n-hp-dbar)<=.3]
    count0=len(q)
    if count0<20:return None,dict(initial_count=count0,point_count=0,reason='fewer_than_20_initial')
    p=plane(q,n)
    if p is None:return None,dict(initial_count=count0,point_count=0,reason='degenerate_initial')
    pc,pn=p;res=(q-pc)@pn;nmad=1.4826*np.median(abs(res-np.median(res)))
    q=q[abs(res)<=3*nmad]
    if len(q)<20:return None,dict(initial_count=count0,point_count=len(q),reason='fewer_than_20_after_trim')
    p=plane(q,n)
    if p is None:return None,dict(initial_count=count0,point_count=len(q),reason='degenerate_final')
    pc,pn=p;den=pn@n
    if abs(den)<1e-12:return None,dict(initial_count=count0,point_count=len(q),reason='axis_parallel')
    h=((pc-c)@pn)/den;mc=c+h*n;res=(q-pc)@pn
    meta=dict(initial_count=count0,point_count=len(q),reason='available',height_m=float(h),
        residual_nmad_m=float(1.4826*np.median(abs(res-np.median(res)))),
        normal_angle_deg=float(np.degrees(np.arccos(np.clip(pn@n,-1,1)))))
    return (mc,pn),meta

def same_surface_triangles(tile,surfs):
    path=W/'holdout/internal/prior_tiles'/tile/'lod2_mesh.npz'
    with zipfile.ZipFile(path) as z:
        membership=array(z,'tri_surface');keep=np.isin(membership,surfs)
        F=selected(z,'F',keep);members=membership[keep]
        with z.open('V.npy') as f:
            ver=np.lib.format.read_magic(f);shape,_,_=np.lib.format._read_array_header(f,ver)
        ids=np.unique(F);mask=np.zeros(shape[0],bool);mask[ids]=True;V=selected(z,'V',mask)
    shift=np.array(json.loads((W/'holdout/internal/registration'/tile/'LoD2'/'summary.json').read_text())['registration']['shift_applied'])
    tri=(V+shift)[np.searchsorted(ids,F)]
    return {int(s):tri[members==s] for s in surfs}

def in_triangles(points,tri,c,e1,e2):
    xy=np.stack([(points-c)@e1,(points-c)@e2],-1)
    tv=np.stack([(tri-c)@e1,(tri-c)@e2],-1);inside=np.zeros(len(points),bool)
    for v in tv:
        a=v[1]-v[0];b=v[2]-v[0];det=a[0]*b[1]-a[1]*b[0]
        if abs(det)<1e-16:continue
        q=xy-v[0];u=(q[:,0]*b[1]-q[:,1]*b[0])/det;w=(a[0]*q[:,1]-a[1]*q[:,0])/det
        inside|=(u>=-1e-10)&(w>=-1e-10)&(u+w<=1+1e-10)
    return inside

def main():
    started=time.monotonic();selection=json.loads((BASE/'photo_benchmark_selection.json').read_text());sample=selection['sample']
    calibration=json.loads((BASE/'geometry_calibration.json').read_text());radius=calibration['als_selected_radius_m']
    lock=dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),selection_sha256=sha(BASE/'photo_benchmark_selection.json'),
        source_sha256={f:sha(Path(__file__).parent/f) for f in ['photo_planes.py','photo_cameras.py']},
        als_photo_plane='Apply section 3.3 to the unchanged original photo centre; use globally selected ALS radius',
        mvs_band='original-centre axis distance minus photo ALS cylinder height within core median d +/-0.3m',
        least_squares='orthogonal PCA, one abs(residual)>3*NMAD trim, refit',
        sweep='integer multiples of 0.02m within [-b,b], includes zero; no off-grid endpoints',
        masks='re-evaluate every shifted sample; LoD2 projected same-surf triangle union; ALS 3D distance to retained same-building roof cores; MVS 3D distance to raw points within 0.1m of fitted plane',
        unavailable_plane_photo_count=0,truth_opened=False,scientific_verdict=None)
    dump(C/'photo_planes.reply1.lock.json',lock)
    sources={};rows=[]
    for r in sample:
        if r['file'] not in sources:sources[r['file']]=loadz(BASE/'photo_targets'/r['file'])
        g=sources[r['file']];i=r['index'];tile,prior,kind=r['file'].removesuffix('.npz').split('__')
        rows.append(dict(tile=tile,prior=prior,kind=int(kind),index=i,file=r['file'],point_id=r['point_id'],
            centre=g['centre'][i],normal=g['normal'][i],tangent1=g['tangent1'][i],tangent2=g['tangent2'][i],
            building=g['building'][i],surf=g['surf'][i],b=float(g['b_m'][i]),dbar=float(g['core_d_median_m'][i]),
            selected=g['selected_images'][i]))
    # Only retained development cores contribute to the ALS support mask.
    wanted={str(r['building']) for r in rows if r['prior']=='ALS'};parts={b:[] for b in wanted}
    for p in sorted((BASE/'inputs').glob('*__ALS.npz')):
        with np.load(p) as z:
            bid=z['building'];xyz=z['centre'];kind=z['kind']
            for b in wanted:
                ix=(bid==b)&(kind==1)
                if ix.any():parts[b].append(xyz[ix])
    als_trees={b:cKDTree(np.concatenate(v)) for b,v in parts.items() if v}
    N=len(rows);centres=np.full((N,2,3),np.nan);normals=centres.copy();t1=centres.copy();t2=centres.copy();available=np.zeros((N,2),bool)
    nh=[int(np.floor(r['b']/.02+1e-12))*2+1 for r in rows];H=max(nh);heights=np.full((N,H),np.nan);masks=np.zeros((N,2,H,625),bool);metadata=[]
    for i,r in enumerate(rows):heights[i,:nh[i]]=np.arange(-(nh[i]//2),nh[i]//2+1)*.02
    for tile in sorted({r['tile'] for r in rows}):
        ix=[i for i,r in enumerate(rows) if r['tile']==tile];tile_start=time.monotonic()
        aa=[i for i in ix if rows[i]['prior']=='ALS'];hp={i:0. for i in ix}
        if aa:
            apath=W/'holdout/internal/points'/tile/'als_xyz.npy';A=np.load(apath);c=np.array([rows[i]['centre'] for i in aa]);nn=fit_normals(A,c)
            for k,i in enumerate(aa):rows[i]['normal']=nn['normal'][k];rows[i]['normal_rule_met']=bool(nn['normal_rule_met'][k])
            del A
            val=run(apath,c,nn['normal'],[radius],BASE/'photo_benchmark/als'/f'{tile}.bin')
            for k,i in enumerate(aa):hp[i]=float(val[k,1,0,1]) if val[k,1,0,0]>=4 else np.nan
            del val
        surfs=[int(rows[i]['surf']) for i in ix if rows[i]['prior']=='LoD2'];tris=same_surface_triangles(tile,surfs) if surfs else {}
        X=np.load(W/'holdout/internal/points'/tile/'mvs_a_xyz.npy').astype(float);tree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False)
        for i in ix:
            r=rows[i];c=r['centre'];n=r['normal'];meta=dict(sample_index=i,point_id=r['point_id'],prior=r['prior'],kind=r['kind'],prior_height_m=hp[i] if np.isfinite(hp[i]) else None)
            if not np.isfinite(n).all() or not np.isfinite(hp[i]):meta['reason']='prior_plane_unavailable';metadata.append(meta);continue
            pc=c+hp[i]*n;centres[i,0]=pc;normals[i,0]=n
            if r['prior']=='LoD2':e1,e2=r['tangent1'],r['tangent2']
            else:e1,e2=tangent(n)
            t1[i,0]=e1;t2[i,0]=e2;available[i,0]=True
            mp,mm=fit_mvs(X,tree,c,n,hp[i],r['dbar']);meta.update(mm)
            if mp is not None:
                centres[i,1],normals[i,1]=mp;t1[i,1],t2[i,1]=tangent(mp[1]);available[i,1]=True
                # Candidate neighbourhood includes every shifted 50cm square.
                ids=tree.query_ball_point(mp[0],r['b']+np.sqrt(2)*.25+.1+1e-6)
                support=X[ids];support=support[abs((support-mp[0])@mp[1])<=.1]
                stree=cKDTree(support) if len(support) else None
            for k in range(2):
                if not available[i,k]:continue
                xx=centres[i,k]+heights[i,:nh[i],None,None]*normals[i,k]+UV[None,:,0,None]*t1[i,k]+UV[None,:,1,None]*t2[i,k]
                flat=xx.reshape(-1,3)
                if k==1:mask=stree.query(flat,distance_upper_bound=.1)[0]<=.1 if stree is not None else np.zeros(len(flat),bool)
                elif r['prior']=='ALS':mask=als_trees[str(r['building'])].query(flat,distance_upper_bound=.18)[0]<=.18
                else:mask=in_triangles(flat,tris[int(r['surf'])],pc,e1,e2)
                masks[i,k,:nh[i]]=mask.reshape(nh[i],625)
            metadata.append(meta)
        del tree,X
        print('PHOTO_PLANES',tile,len(ix),'seconds',time.monotonic()-tile_start,flush=True)
    preparation=time.monotonic()-started;cam=Cameras();vstart=time.monotonic()
    selected_images=np.full((N,2,10),-1,np.int32);selected_images[:,0]=np.array([r['selected'] for r in rows])
    selected_images[:,1]=choose_mvs_views(centres[:,1],normals[:,1],t1[:,1],t2[:,1],cam,available[:,1])
    target=BASE/'photo_benchmark/planes.npz';savez(target,centres=centres,normals=normals,tangent1=t1,tangent2=t2,
        available=available,heights=heights,masks=masks,selected_images=selected_images,point_id=np.array([r['point_id'] for r in rows]))
    dump(BASE/'photo_benchmark/preparation.json',dict(at=now(),planes_sha256=sha(target),points=N,max_heights=H,
        plane_preparation_seconds=preparation,visibility_seconds=time.monotonic()-vstart,total_seconds=time.monotonic()-started,
        available_planes=available.sum(0).tolist(),metadata=metadata,truth_opened=False,scientific_verdict=None))
    print('PREPARED',N,'HEIGHTS',H,'SECONDS',time.monotonic()-started,flush=True)

if __name__=='__main__':main()
