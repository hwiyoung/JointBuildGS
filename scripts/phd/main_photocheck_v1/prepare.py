"""Freeze the specification and figure sections, then build unique point ownership."""
import time,collections,warnings
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from common import *
warnings.filterwarnings('ignore',message='All-NaN slice encountered')

def components(x,r=.36):
    if not len(x): return np.empty(0,np.int32)
    pairs=cKDTree(x).query_pairs(r,output_type='ndarray')
    g=coo_matrix((np.ones(len(pairs)),(pairs[:,0],pairs[:,1])),shape=(len(x),len(x)))
    return connected_components(g,directed=False)[1]
def subset_examples(prior):
    keys=['centre','normal','area','building','kind','cell']
    rows=[]
    for f in sorted((W/'patch_values').glob(f'*__{prior}__R1.5.npz')):
        with np.load(f) as z:
            mask=np.isin(z['building'],EXAMPLES)
            if mask.any():rows.append({k:z[k][mask] for k in keys})
    return {k:np.concatenate([d[k] for d in rows]) for k in keys}
def freeze():
    if (C/'photocheck_v1.lock.json').exists():
        assert sha(C/'photocheck_v1.json')==load(C/'photocheck_v1.lock.json')['sha256'];return
    assert load(O/'input_preflight.json')['status']=='PASS'
    sections=[dict(name='B173 날개',prior='ALS',building=EXAMPLES[0],a=[146.68,96.32],b=[136.63,99.34],half_width=.6),
      dict(name='R1 계단 지붕',prior='LoD2',building=EXAMPLES[1],a=[7.24,32.08],b=[14.98,18.08],half_width=.6),
      dict(name='60042 높은 단',prior='ALS',building=EXAMPLES[2],a=[-64.03,40.64],b=[-56.57,37.76],half_width=.5)]
    for prior in ['LoD2','ALS']:
        d=subset_examples(prior)
        for b in (EXAMPLES[3:] if prior=='LoD2' else EXAMPLES[5:]):
            m=(d['building']==b)&(d['kind']==1)
            if b!=EXAMPLES[5]:
                m&=d['cell']==2;ids=np.flatnonzero(m);lab=components(d['centre'][ids]);areas=np.bincount(lab,weights=d['area'][ids]);ids=ids[lab==np.argmax(areas)]
            else:ids=np.flatnonzero(m)
            xy=d['centre'][ids,:2];weights=d['area'][ids];c=np.average(xy,weights=weights,axis=0)
            cov=((xy-c)*weights[:,None]).T@(xy-c)/weights.sum();_,v=np.linalg.eigh(cov);long=v[:,-1];cross=np.array([-long[1],long[0]])
            if cross[0]<0:cross=-cross
            half=5. if b!=EXAMPLES[5] else np.max(np.abs((d['centre'][d['building']==b,:2]-c)@cross))+.5
            sections.append(dict(name=b.removeprefix('DEBY_LOD2_'),prior=prior,building=b,a=(c-half*cross).tolist(),b=(c+half*cross).tolist(),half_width=.6,source='section only: largest image_wrong component' if b!=EXAMPLES[5] else 'section only: roof major-axis perpendicular including slopes'))
    config=dict(task_id='PHD-MAIN-PHOTOCHECK-v1',created_at=now(),scientific_verdict=None,
      frame=dict(crs='EPSG:25832',world_shift_xyz_m=[690953,5336071,604],height_sign='outward normal positive; identical to inherited mvs_p and gt_p'),
      sources=dict(widen=str(W),patch_glob='*__<prior>__R1.5.npz',train_split=str(W/'image_split.json'),images=str(RAW/'raw/uav/Images.zip'),camera=str(CAL/'cameras.txt'),poses=str(DENSE/'sparse/images.bin'),prior_mesh='holdout/internal/prior_tiles/<tile>/<prior>_mesh.npz plus exact registration/<tile>/<prior>/summary.json shift'),
      points=dict(spacing_m=.5,patch_spacing_m=.25,group='same tile, surface, building and kind; never cross split',
        grid='LoD2: normalized source tangents; ALS: XY; origin min regular coordinate per surface; floor((coord-min)/0.5 + 1e-7)',
        grid_check='distance to nearest 0.25 m integer offset <=1e-5 m; non-grid faces use tangent plane; extras attach closest point within 0.5 m in same surface/building/kind or singleton',
        centre='area weighted',normal='unweighted unit mean',tangent1='first source tangent projected orthogonal to mean normal then normalized',
        undefined='keep patch ownership; missing source normal/tangent remains unavailable and yields no eligible photos; never infer from GT',
        sigma='median patch sigma; missing retained',mvs_p='median finite patch mvs_p',u_mvs_gate='median finite inherited raw u_mvs'),
      uncertainty=dict(unit='metre',floor_m=.0275,MVS='sqrt(u_mvs^2+floor^2)',ALS='sqrt(u_prior^2+floor^2)',LoD2_roof={'1000':.166,'2100':.098,'3100':.223,'3200':.114,'3900':.238,'other':.11},LoD2_wall=.144),
      heights=dict(base_m=np.r_[np.arange(-50,-5)*.1,np.arange(-25,26)*.02,np.arange(6,51)*.1].round(8).tolist(),extra_offsets_m=[-.3,-.2,-.1,0,.1,.2,.3],extra_if_abs_mvs_gt_m=5.),
      photos=dict(train_images=819,max_images=10,min_images=3,margin_px=20,angle_max_deg=60,occlusion_tolerance_m=.3,
        visibility='CPU exact ray depth at continuous projected centre through identical registered prior tile mesh; ray depth expressed in metres; no hit = no represented blocker; same fixed photo set at every h',
        selection='least incidence first; maximize minimum angular separation iteratively; ties sorted image name',
        projection='FULL_OPENCV; world to camera; pinhole within image +/-200 px and distortion change vector norm <400 px',
        candidate_extent='all 819 train cameras tested; all four 0.5m square corners plus centre satisfy projection guards',
        mesh_context='exact inherited tile mesh including 10m buffered prior context; no unregistered substitution',
        parallax='max pair norm of (d-dot(d,n)n)/abs(dot(d,n))'),
      score=dict(square_m=.5,samples_per_side=25,sample_step_m=.02,sample_offsets_m=(np.arange(25)*.02-.24).round(8).tolist(),
        grayscale=[.299,.587,.114],pyramid='repeated 2x area reduction; choose level closest to 0.02 m per pixel when distance/sqrt(fx*fy)<0.02; centre-aligned resize mapping (u+0.5)/scale-0.5',
        interpolation='bilinear',NCC='population standardization; mean over all selected valid image pairs; zero-variance vectors have NCC undefined, not fabricated',
        score='equivalent normalized-vector identity (norm(sum vectors)^2 - sum squared norms)/(m*(m-1)); height missing if fewer than 3 images',
        dtype_compute='float32 (verify against float64 pairwise reference)',dtype_store='float16 curve plus float32 extracted values',texture='median population standard deviation at h=0',
        at_height='fixed selected cameras; exclude out-of-image or invalid projection at this h only; no new visibility test'),
      features=dict(inside='abs(h)<=3*sigma',peak='maximum within +/-0.1m; global endpoints excluded; plateau center tie',competitor='outside peak OR abs(h)>3*sigma+0.3m',ties='first ascending h',s_mvs='nearest finite sampled h to mvs_p',missing='nonfinite required features => ambiguous; missing sigma => ambiguous'),
      judgments=dict(order=LABELS,candidates=[dict(delta=d,s_min=s) for d in [.05,.10,.15,.20,.30] for s in [0,.3,.5]],texture_min=5,display=dict(delta=.10,s_min=.3,index=4)),
      examples=EXAMPLES,sections=sections,seed=20261026,
      projection_gate=dict(agree_abs_mvs_lt=.05,raw_u_mvs_lt=.03,texture_min=5,min_images=3,min_points=100,pass_abs_h_max_le=.1,pass_fraction_gt=.5,fallback_n=1000),
      figures=dict(dpi=300,colors=['#238b45','#d73027','#929292'],scope='development only; holdout grey hatching only',curve_example_points=2,random_points_per_judgment=3,montage_max_per_building=3,montage_n=20,photo_margin_m=3.,no_cause_labels=True),
      evaluation=dict(gt='gt_status==0 and finite gt_p; abs(gt_p)<=3*patch_sigma',unexplained='abs(mvs_p)/sqrt(patch_sigma^2+sigma_mvs^2)>3',components_radius_m=.36,component_min_area_m2=1.),
      execution=dict(training=False,cpu_nice=19,process_memory_limit_gib=32,gpu='curve sampling/NCC only; device selected only while no compute process uses it',gpu_wait_seconds=0.,gpu_stop_hours=48,cpu_stop_hours=72,archive_max_bytes=399000000,
        allowed=['configs/phd/main_photocheck_v1/','scripts/phd/main_photocheck_v1/','docs/experiments/phd/main_photocheck_v1/','PH/main_photocheck_v1/PHD-MAIN-PHOTOCHECK-v1/']),
      source_tag='[이 발주에서 냄]',amendments=[])
    assert len(config['heights']['base_m'])==141
    dump(C/'photocheck_v1.json',config);dump(C/'photocheck_v1.lock.json',dict(at=now(),sha256=sha(C/'photocheck_v1.json'),before_first_curve=True,source_order_sha256=sha(D/'발주문_v1.txt'),environment=env()))

def group(d,prior,tile):
    sp,sm=sigmas(d,prior);n=len(d['centre']);owner=np.full(n,-1,np.int32);rows=[];audit=[]
    if not n:return {},owner,audit
    groupkeys=np.array([f'{s}:{b}:{k}' for s,b,k in zip(d['surf'],d['building'],d['kind'])])
    for key in np.unique(groupkeys):
        ids=np.flatnonzero(groupkeys==key);regular=ids[~d['source_extra'][ids]];extras=ids[d['source_extra'][ids]]
        t=d['tangent1'][regular[0]] if len(regular) else d['tangent1'][ids[0]]
        t=t/max(np.linalg.norm(t),1e-15);t2=d['tangent2'][regular[0]] if len(regular) else d['tangent2'][ids[0]];t2=t2/max(np.linalg.norm(t2),1e-15)
        xy=d['centre'][regular,:2] if prior=='ALS' else np.c_[d['centre'][regular]@t,d['centre'][regular]@t2]
        fallback=False;groups=[]
        if len(regular):
            delta=xy-xy.min(0);residual=np.max(np.abs(delta/.25-np.rint(delta/.25)))*.25
            if residual>1e-5:
                fallback=True;xy=np.c_[d['centre'][regular]@t,d['centre'][regular]@t2];delta=xy-xy.min(0)
            uv=np.floor(delta/.5+1e-7).astype(np.int64);_,inv=np.unique(uv,axis=0,return_inverse=True)
            order=np.argsort(inv,kind='stable');groups=[regular[g].tolist() for g in np.split(order,np.flatnonzero(np.diff(inv[order]))+1)]
        for j in extras:
            if groups:
                cent=np.array([np.average(d['centre'][g],weights=d['area'][g],axis=0) for g in groups]);dist=np.linalg.norm(cent-d['centre'][j],axis=1);q=int(np.argmin(dist))
                if dist[q]<=.5:groups[q].append(int(j));continue
            groups.append([int(j)])
        audit.append(dict(surface_group=key,patches=len(ids),area_m2=d['area'][ids].sum(),tangent_fallback=fallback))
        for g in groups:
            g=np.asarray(g);weights=d['area'][g];centre=np.average(d['centre'][g],weights=weights,axis=0)
            normal=d['normal'][g].mean(0);norm=np.linalg.norm(normal);normal=normal/max(norm,1e-15)
            e=d['tangent1'][g[0]];e=e-normal*np.dot(e,normal);ln=np.linalg.norm(e);e=e/max(ln,1e-15);e2=np.cross(normal,e)
            ok=norm>1e-8 and ln>1e-8
            def med(v):return float(np.nanmedian(v)) if np.isfinite(v).any() else np.nan
            idx=len(rows);owner[g]=idx
            rows.append(dict(point_id=f'{prior}:{tile}:point:{idx}',tile=tile,prior=prior,building=d['building'][g[0]],holdout=d['holdout'][g[0]],kind=d['kind'][g[0]],surf=d['surf'][g[0]],centre=centre,normal=normal,tangent1=e,tangent2=e2,geometry_valid=ok,sigma=med(sp[g]),mvs_p=med(d['mvs_p'][g]),raw_u_mvs=med(d['u_mvs'][g]),sigma_mvs=med(sm[g]),area=weights.sum(),patch_count=len(g)))
    assert (owner>=0).all();return {k:np.array([r[k] for r in rows]) for k in rows[0]},owner,audit

def main():
    freeze();start=time.monotonic();totals=[]
    for seal in [False,True]:
        base=paths(seal);source=W/('holdout/patch_values' if seal else 'patch_values')
        for f in sorted(source.glob('*.npz')):
            tile,prior,_=f.stem.split('__');dest=base/'geometry'/f'{tile}__{prior}.npz'
            if dest.exists():continue
            raw=npz(f);take=(raw['kind']==1)|((raw['kind']==2)&(raw['building']==EXAMPLES[5])&~raw['holdout'])
            d={k:v[take] for k,v in raw.items()};points,owner,audit=group(d,prior,tile)
            if not points:points={k:np.empty((0,3)) if k in ['centre','normal','tangent1','tangent2'] else np.empty(0) for k in ['point_id','tile','prior','building','holdout','kind','surf','centre','normal','tangent1','tangent2','geometry_valid','sigma','mvs_p','raw_u_mvs','sigma_mvs','area','patch_count']}
            np.savez_compressed(dest,**points)
            np.savez_compressed(base/'geometry'/f'{tile}__{prior}__mapping.npz',patch_id=d['patch_id'],point_index=owner,source_index=np.flatnonzero(take),kind=d['kind'])
            rec=dict(tile=tile,prior=prior,holdout=seal,points=len(points['point_id']),patches=len(owner),area_m2=float(d['area'].sum()),roof_points=int((points['kind']==1).sum()),roof_patches=int((d['kind']==1).sum()),roof_area_m2=float(d['area'][d['kind']==1].sum()),point_patch_count_distribution=dict(zip(*np.unique(points['patch_count'],return_counts=True))),source_sha256=sha(f),config_sha256=sha(C/'photocheck_v1.json'),surface_audit=audit,scientific_verdict=None)
            dump(dest.with_suffix('.json'),rec);print('geometry',seal,tile,prior,len(owner),len(points['point_id']),flush=True)
    # Allowed public holdout totals only. No point values or judgment areas.
    for seal in [False,True]:
        base=paths(seal)
        for prior in ['LoD2','ALS']:
            rr=[load(p) for p in (base/'geometry').glob(f'*__{prior}.json')]
            totals.append(dict(prior=prior,holdout=seal,points=sum(r['roof_points'] for r in rr),patches=sum(r['roof_patches'] for r in rr),area_m2=sum(r['roof_area_m2'] for r in rr)))
    dump(O/'geometry_summary.json',dict(rows=totals,seconds=time.monotonic()-start,environment=env()));print(json.dumps(clean(totals)))
if __name__=='__main__':main()
