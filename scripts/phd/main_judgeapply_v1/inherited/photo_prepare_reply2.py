"""One raw MVS/ALS tree per tile; packed valid height rows and image selections."""
import json,time,sys,resource
import numpy as np
from scipy.spatial import cKDTree
from preflight import C,O,Path,dump,sha,now
from geometry import loadz,savez
from photo_planes import UV,tangent,fit_mvs,same_surface_triangles,in_triangles
from photo_cameras import Cameras,choose_mvs_views
from u_core import find_face
from ring_context import W,D as DEFS
BASE=O/'r2';INPUT=O/'r1'

def fitted_normals(A,tree,centres):
    N=len(centres);norm=np.full((N,3),np.nan);rule=np.zeros(N,bool)
    for begin in range(0,N,1024):
        for j,ids in enumerate(tree.query_ball_point(centres[begin:begin+1024],2.)):
            i=begin+j;v=A[ids]-centres[i];v=v[abs(v[:,2])<=1.];dist=np.sum(v*v,1)
            for r in [.5,.75,1.,1.5,2.]:
                q=v[dist<=r*r]
                if len(q)<3:continue
                vv=q-q.mean(0);ev,vec=np.linalg.eigh(vv.T@vv)
                if ev[1]<=1e-16:continue
                n=vec[:,0];n*=1 if n[2]>=0 else -1;sd=np.std(vv@n);good=len(q)>=10 and r>=25*sd
                if good or r==2.:norm[i]=n;rule[i]=good;break
    return norm,rule

def prior_height(A,tree,c,n):
    if not np.isfinite(n).all():return np.nan,0
    probes=c+np.arange(-9.75,10,.5)[:,None]*n
    ids=np.unique(np.concatenate([np.asarray(v,int) for v in tree.query_ball_point(probes,np.hypot(.75,.25)+1e-6)]))
    q=A[ids]-c;t=q@n;rr=np.maximum(0,np.sum(q*q,1)-t*t);t=t[(rr<=.75**2)&(abs(t)<=10)]
    o,_,_=find_face(t,10,DEFS)
    if o is None:return np.nan,0
    t=t[abs(t-o)<=1.];return (float(t.mean()) if len(t)>=4 else np.nan),len(t)

def get_support_trees(buildings):
    parts={str(b):[] for b in buildings}
    for p in sorted((INPUT/'inputs').glob('*__ALS.npz')):
        with np.load(p) as z:
            bid=z['building'];c=z['centre']
            for b in parts:
                m=bid==b
                if m.any():parts[b].append(c[m])
    return {b:cKDTree(np.concatenate(v)) for b,v in parts.items() if v}

def als_mask(tree,c,n,e1,e2,heights):
    mask=np.zeros((len(heights),625),bool);b=max(abs(heights)) if len(heights) else 0
    # Any supporting core must be within square circumradius + shift + 0.18.
    ids=tree.query_ball_point(c,b+np.sqrt(2)*.24+.18+1e-8)
    if not ids:return mask
    q=tree.data[ids];t=(q-c)@n
    possible=(heights>=t.min()-.18-1e-10)&(heights<=t.max()+.18+1e-10)
    hh=np.flatnonzero(possible)
    if len(hh):
        xyz=c+heights[hh,None,None]*n+UV[None,:,0,None]*e1+UV[None,:,1,None]*e2
        mask[hh]=tree.query(xyz.reshape(-1,3),distance_upper_bound=.18)[0].reshape(-1,625)<=.18
    return mask

def mvs_mask(X,tree,c,n,e1,e2,heights):
    mask=np.zeros((len(heights),625),bool);hh=np.flatnonzero(abs(heights)<=.2+1e-10)
    if not len(hh):return mask
    # Triangle inequality and |point-to-plane|<=.1 prove no shifted sample
    # beyond .2m can have an eligible point within .1m.
    ids=tree.query_ball_point(c,np.sqrt(2)*.24+.3+1e-8);q=X[ids];q=q[abs((q-c)@n)<=.1]
    if not len(q):return mask
    st=cKDTree(q);xyz=c+heights[hh,None,None]*n+UV[None,:,0,None]*e1+UV[None,:,1,None]*e2
    mask[hh]=st.query(xyz.reshape(-1,3),distance_upper_bound=.1)[0].reshape(-1,625)<=.1
    return mask

def main(tile):
    if tile=='benchmark':tile=json.loads((BASE/'target_census.json').read_text())['benchmark_tile']
    dest=BASE/'photo_prepared'/f'{tile}.npz'
    if dest.with_suffix('.complete.json').exists():print('PREPARED_REUSE',tile);return
    start=time.monotonic();sourcefiles=[];parts=[]
    for group,(prior,kind) in enumerate([('ALS',1),('LoD2',1),('LoD2',2)]):
        p=BASE/'photo_targets'/f'{tile}__{prior}__{kind}.npz'
        if not p.exists():continue
        g=loadz(p);ix=np.flatnonzero(g['target_type']>0)
        if not len(ix):continue
        keys=['centre','normal','tangent1','tangent2','building','surf','b_m','core_d_median_m','selected_images','point_id','target_type_bits','sweep_defined']
        part={k:g[k][ix] for k in keys};part.update(group=np.full(len(ix),group,np.int8),source_index=ix,source_file=np.full(len(ix),p.name))
        parts.append(part);sourcefiles.append(dict(path=str(p),sha256=sha(p)))
    g={k:np.concatenate([p[k] for p in parts]) for k in parts[0]};N=len(g['point_id']);del parts
    lock=C/'photo_prepare.reply2.lock.json';sources={p.name:sha(p) for p in [Path(__file__),Path(__file__).parent/'photo_planes.py',Path(__file__).parent/'photo_cameras.py']}
    if not lock.exists():dump(lock,dict(at=now(),config_sha256=sha(C/'judgecheck_v1.json'),sources=sources,
        inherited_methods='reply1 float64 planes and masks unchanged; exact pruning of impossible MVS/ALS mask shifts; packed heights without padding',
        raw_trees='one ALS tree reused for normals and cylinder height; one MVS tree reused for all target planes and masks per tile',scientific_verdict=None))
    else:assert json.loads(lock.read_text())['sources']==sources
    shared_start=time.monotonic();als=np.flatnonzero(g['group']==0);hp=np.zeros(N);norm=g['normal'].copy();normalrule=np.ones(N,bool);priorn=np.full(N,-1,np.int32)
    atree=None;A=None;support=get_support_trees(set(g['building'][als])) if len(als) else {}
    if len(als):A=np.load(W/'holdout/internal/points'/tile/'als_xyz.npy');atree=cKDTree(A,leafsize=32,balanced_tree=False,compact_nodes=False)
    X=np.load(W/'holdout/internal/points'/tile/'mvs_a_xyz.npy').astype(float);mtree=cKDTree(X,leafsize=32,balanced_tree=False,compact_nodes=False)
    surfs=np.unique(g['surf'][g['group']>0]);tris=same_surface_triangles(tile,surfs) if len(surfs) else {}
    shared_seconds=time.monotonic()-shared_start;work_start=time.monotonic()
    if len(als):
        norm[als],normalrule[als]=fitted_normals(A,atree,g['centre'][als])
        for i in als:hp[i],priorn[i]=prior_height(A,atree,g['centre'][i],norm[i])
        del atree,A
    centres=np.full((N,2,3),np.nan);normals=centres.copy();e1=centres.copy();e2=centres.copy();available=np.zeros((N,2),bool)
    nfit=np.zeros(N,np.int32);ninitial=nfit.copy();residual=np.full(N,np.nan);angle=residual.copy();reason=np.full(N,'sweep_unavailable',dtype='<U32')
    row_plane=[];row_h=[];row_masks=[];ptr=[0];mask_fractions=np.full((N,2),np.nan)
    for i in range(N):
        if not g['sweep_defined'][i] or not np.isfinite(norm[i]).all() or not np.isfinite(hp[i]):
            ptr.extend([ptr[-1],ptr[-1]]);continue
        c=g['centre'][i];n=norm[i];pc=c+hp[i]*n;centres[i,0]=pc;normals[i,0]=n;available[i,0]=True
        e1[i,0],e2[i,0]=(g['tangent1'][i],g['tangent2'][i]) if g['group'][i]>0 else tangent(n)
        fitted,meta=fit_mvs(X,mtree,c,n,hp[i],g['core_d_median_m'][i]);nfit[i]=meta['point_count'];ninitial[i]=meta['initial_count'];reason[i]=meta['reason']
        if fitted is not None:
            centres[i,1],normals[i,1]=fitted;available[i,1]=True;e1[i,1],e2[i,1]=tangent(fitted[1]);residual[i]=meta['residual_nmad_m'];angle[i]=meta['normal_angle_deg']
        width=int(np.floor(g['b_m'][i]/.02+1e-12));hh=np.arange(-width,width+1)*.02
        for j in range(2):
            if not available[i,j]:ptr.append(ptr[-1]);continue
            cc=centres[i,j];nn=normals[i,j];a=e1[i,j];b=e2[i,j]
            if j==1:mask=mvs_mask(X,mtree,cc,nn,a,b,hh)
            elif g['group'][i]==0:mask=als_mask(support[str(g['building'][i])],cc,nn,a,b,hh)
            else:
                flat=cc+UV[:,0,None]*a+UV[:,1,None]*b
                m=in_triangles(flat,tris[int(g['surf'][i])],cc,a,b);mask=np.broadcast_to(m,(len(hh),625))
            row_plane.append(np.full(len(hh),2*i+j,np.int32));row_h.append(hh);row_masks.append(np.packbits(mask,axis=1));ptr.append(ptr[-1]+len(hh))
            mask_fractions[i,j]=mask[width].mean()
        if i%1000==0:print('PREPARE_TILE',tile,i,N,'point_work_seconds',time.monotonic()-work_start,flush=True)
    variable_seconds=time.monotonic()-work_start;del X,mtree,support
    view_start=time.monotonic();cam=Cameras();selected=np.full((N,2,10),-1,np.int32);selected[:,0]=g['selected_images']
    selected[:,1]=choose_mvs_views(centres[:,1],normals[:,1],e1[:,1],e2[:,1],cam,available[:,1]);view_seconds=time.monotonic()-view_start
    rr=np.concatenate(row_plane) if row_plane else np.empty(0,np.int32);hh=np.concatenate(row_h) if row_h else np.empty(0)
    packed=np.concatenate(row_masks) if row_masks else np.empty((0,79),np.uint8)
    assert len(ptr)==2*N+1 and ptr[-1]==len(hh)==len(rr)==len(packed)
    savez(dest,point_id=g['point_id'],group=g['group'],source_file=g['source_file'],source_index=g['source_index'],target_type_bits=g['target_type_bits'],
        centres=centres,normals=normals,tangent1=e1,tangent2=e2,available=available,selected_images=selected,
        row_plane=rr,row_height=hh,mask_bits=packed,plane_row_ptr=np.array(ptr,np.int64),mask_fraction_at_zero=mask_fractions,
        prior_height_m=hp,prior_normal_rule_met=normalrule,prior_n=priorn,mvs_fit_count=nfit,mvs_initial_count=ninitial,mvs_fit_nmad_m=residual,
        mvs_normal_angle_deg=angle,mvs_fit_reason=reason,b_m=g['b_m'])
    rec=dict(at=now(),tile=tile,target_count=N,packed_height_rows=len(hh),group_counts={str(k):int((g['group']==k).sum()) for k in np.unique(g['group'])},
        shared_load_and_tree_seconds=shared_seconds,per_point_geometry_seconds=variable_seconds,visibility_seconds=view_seconds,total_seconds=time.monotonic()-start,
        available_planes=available.sum(0).tolist(),peak_rss_gib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024**2,
        sources=sourcefiles,output_sha256=sha(dest),truth_read=False,scientific_verdict=None)
    dump(dest.with_suffix('.complete.json'),rec);print('PREPARED_TILE_COMPLETE',json.dumps({k:v for k,v in rec.items() if k!='sources'}),flush=True)

if __name__=='__main__':main(sys.argv[1])
