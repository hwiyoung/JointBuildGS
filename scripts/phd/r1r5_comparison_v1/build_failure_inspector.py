"""Evaluation-only all-region census and native-surface inspection. Run in Docker."""
import csv
import time
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from analyze_final_surfaces import read, write, sha, mesh_arrays, distances

OUT = Path('/out')
CFG = read(OUT/'config.json')
ROOT = Path('/art')/CFG['attempt_relative']
UAS = ROOT/CFG['uas_folder']
ANA = ROOT/CFG['analysis']
theta = np.deg2rad(70)
BASIS = np.array([[np.cos(theta), np.sin(theta)], [np.sin(theta), -np.cos(theta)]])
CATEGORIES = ['prior_near_baseline_far', 'both_far', 'prior_far_baseline_near', 'both_near', 'intermediate']
TITLES = ['Prior near / baseline far: preservation review', 'Both far: cause and correction need unresolved',
          'Prior far / baseline near: correction retained', 'Both near: non-degradation comparison',
          'Intermediate distance bands: unclassified']


def zones_for(r):
    return read(Path('/art')/CFG['r1_review_relative']/'config.json' if r == 'R1' else ROOT/r/'review_zones.json')['zones']


def census():
    result = dict(role='EVALUATION_ONLY_NOT_TRAINING_LABELS', scientific_verdict=None, regions={},
                  bands=dict(near_m=.25, far_m=1., cell_m=2.),
                  method='All frozen UAS reference samples; categories partition samples. No semantic or causal labels.')
    assert read(UAS/'receipt.json')['status'] == 'PASS_UAS_REFERENCE_DISTANCE_DIAGNOSTIC'
    for r in CFG['regions']:
        ref = np.load(UAS/(r+'_reference.npz'))['xyz']; uv = ref[:,:2]@BASIS.T
        ds = np.load(UAS/(r+'_uas_distances.npz')); p = np.load(UAS/(r+'_uas_to_prior.npy')); b = ds['mvs']
        masks = [(p<=.25)&(b>1), (p>1)&(b>1), (p>1)&(b<=.25), (p<=.25)&(b<=.25)]
        masks.append(~np.logical_or.reduce(masks)); assert np.all(np.sum(masks, axis=0)==1)
        uvz = np.column_stack([uv,ref[:,2]])
        keys, inv = np.unique(np.floor(uvz/2).astype(np.int32), axis=0, return_inverse=True)
        n = np.bincount(inv); counts = [np.bincount(inv,weights=m,minlength=len(n)).astype(int) for m in masks]
        zones = zones_for(r); nz=max(int(z['id'][1:]) for z in zones)+1
        dominant = np.bincount(inv*nz+ds['zone'],minlength=len(n)*nz).reshape(-1,nz).argmax(1)
        # Every occupied 3D cell is retained, including small/ambiguous/non-building cells.
        with (OUT/(r+'_all_cells.csv')).open('w') as f:
            w=csv.writer(f); w.writerow(['u_min','v_min','local_z_min','uas_points','dominant_xy_zone',*CATEGORIES])
            for j,k in enumerate(keys):w.writerow([*(k*2),n[j],f'Z{dominant[j]:02}',*[c[j] for c in counts]])
        xy = np.floor(uv/2).astype(int); low=xy.min(0); high=xy.max(0)+1; shape=tuple(high-low)
        flat=(xy[:,0]-low[0])*shape[1]+xy[:,1]-low[1]
        totals=np.bincount(flat,minlength=np.prod(shape)).reshape(shape)
        fig,axs=plt.subplots(2,3,figsize=(16,9)); extent=[low[0]*2,high[0]*2,low[1]*2,high[1]*2]
        matrices=[np.where(totals>0,np.log10(np.maximum(totals,1)),np.nan)]
        for m in masks:
            c=np.bincount(flat,weights=m,minlength=np.prod(shape)).reshape(shape)
            matrices.append(np.divide(c,totals,out=np.full(shape,np.nan),where=totals>0))
        for j,(ax,values) in enumerate(zip(axs.flat,matrices)):
            im=ax.imshow(values.T,origin='lower',extent=extent,interpolation='nearest',cmap='viridis' if j==0 else 'magma',vmin=0,vmax=None if j==0 else 1)
            for z in zones[1:]:
                poly=np.array(z['polygon']); ax.plot(*np.vstack([poly,poly[0]]).T,c='#5ab4ac',lw=.6)
                ax.text(*poly.mean(0),z['id'],fontsize=7,ha='center',bbox=dict(facecolor='white',alpha=.75,edgecolor='none'))
            if r=='R1': ax.plot(43,15,'+',color='cyan',markersize=12,markeredgewidth=2)
            ax.invert_yaxis(); ax.set_aspect('equal');ax.set_xlabel('object u [m]');ax.set_ylabel('object v [m]')
            ax.set_title('Reference coverage: log10 point count' if j==0 else TITLES[j-1],fontsize=10)
            fig.colorbar(im,ax=ax,shrink=.8,label='log10(n)' if j==0 else 'Fraction of UAS samples in XY cell')
        fig.suptitle(f'{r}: full fixed reference cohort; XY projection includes all heights / classes; white = no reference',fontsize=12)
        fig.tight_layout(); fig.savefig(OUT/(r+'_census.png'),dpi=130);plt.close(fig)
        result['regions'][r]=dict(n=len(ref),occupied_3d_cells=len(n),cells_with_at_least_20_points=int((n>=20).sum()),
            category_counts={k:int(m.sum()) for k,m in zip(CATEGORIES,masks)},baseline_over_1m=int((b>1).sum()),
            inputs_sha256={x:sha(UAS/x) for x in [r+'_reference.npz',r+'_uas_distances.npz',r+'_uas_to_prior.npy']})
        print('CENSUS',r,result['regions'][r]['category_counts'],flush=True)
    write(OUT/'census.json',result)


def transform(x):
    return np.column_stack([x[:,:2]@BASIS[0], -x[:,:2]@BASIS[1], x[:,2]])


def buffers(stem, a, dtype):
    a=np.asarray(a,dtype=dtype); path=OUT/(stem+'.bin'); a.tofile(path)
    return dict(url=path.name,bytes=path.stat().st_size,sha256=sha(path),shape=list(a.shape),dtype=dtype)


def crop(xyz,faces,lo,hi):
    parts=[]
    for start in range(0,len(faces),250000):
        f=faces[start:start+250000]; tri=xyz[f]
        mask=(tri.max(1)>=lo).all(1)&(tri.min(1)<=hi).all(1)
        if mask.any():parts.append(f[mask])
    chosen=np.concatenate(parts);ids,inv=np.unique(chosen,return_inverse=True)
    return xyz[ids],inv.reshape(-1,3).astype(np.uint32)


def export_case():
    case=read(UAS/'case_locations.json')['regions']['R1']['top_cells']['prior_near_baseline_far'][0]
    assert case['uvz_min']==[42,14,-34]
    lo=np.array([35,-19,-38]);hi=np.array([51,-11,-28]); meshes={}
    prior_info=read(UAS/'R1_prior_reference.json');pp=Path(prior_info['source']);assert sha(pp)==prior_info['sha256']
    prior=np.load(pp);x,t=crop(transform(prior['xyz']),prior['faces'],lo,hi)
    meshes['prior']=(x,t,prior_info)
    for b,info in read(ANA/'R1_summary.json')['metadata']['models'].items():
        path=Path(info['path']);assert sha(path)==info['sha256']
        verts,faces=mesh_arrays(path);xyz=transform(np.column_stack([verts[k] for k in 'xyz']))
        x,t=crop(xyz,faces['indices'],lo,hi);meshes[b]=(x,t,info)
        print('MESH',b,len(x),len(t),flush=True)
    ref=np.load(UAS/'R1_reference.npz')['xyz'];display=transform(ref)
    use=((display>=lo)&(display<=hi)).all(1);points=display[use]
    cell=((display>=[42,-16,-34])&(display<[44,-14,-32])).all(1)
    # v sign reverses half-open endpoints; no sample lies at these exact cell boundaries here.
    uv=ref[:,:2]@BASIS.T;originalcell=((uv>=[42,14])&(uv<[44,16])).all(1)&(ref[:,2]>=-34)&(ref[:,2]<-32)
    assert np.array_equal(cell,originalcell) and int(cell.sum())==case['n']
    frozen=np.load(UAS/'R1_uas_distances.npz');dp=np.load(UAS/'R1_uas_to_prior.npy')
    manifest=dict(scientific_verdict=None,case=case,display_box=[lo.tolist(),hi.tolist()],
        frame='x=u, y=-v, z=local source z; metres; no vertical exaggeration',models={},
        uas=buffers('uas',points,'<f4'),role='REFERENCE_ONLY_DIAGNOSTIC_NOT_TRAINING_INPUT')
    checks=[]
    for b,(x,t,info) in meshes.items():
        # The local export must contain the actual closest native triangles for all scored samples.
        d,_=distances(x.astype(np.float32),t,display[cell].astype(np.float32),10.)
        expected=dp[cell] if b=='prior' else frozen[b][cell]
        max_delta=float(abs(d-expected).max());assert max_delta<.001,(b,max_delta)
        manifest['models'][b]=dict(xyz=buffers(b+'_xyz',x,'<f4'),indices=buffers(b+'_indices',t,'<u4'),
            vertices=len(x),triangles=len(t),median_m=float(np.median(expected)),source=info)
        checks.append(dict(branch=b,max_reference_distance_delta_m=max_delta,n=len(d)))
    # Bind the location to the existing RGB viewer geometry, rather than assuming its crop retained it.
    info=CFG['existing_viewer_mesh'];xyz=np.fromfile(Path('/art')/info['xyz'],dtype='<f4').reshape(-1,3)
    faces=np.fromfile(Path('/art')/info['indices'],dtype='<u4').reshape(-1,3)
    x,t=crop(xyz,faces,lo,hi);d,_=distances(x.astype(np.float32),t,display[cell].astype(np.float32),10.)
    delta=float(abs(d-frozen['mvs'][cell]).max());assert delta<.001,delta
    checks.append(dict(check='Existing RGB viewer contains same baseline surface at scored location',max_distance_delta_m=delta,n=len(d)))
    manifest['validation']=checks
    segments=np.load(UAS/'R1_Z07_case_segments.npz'); manifest['sections']={}
    for b in meshes:
        s=segments[b];segxyz=np.stack([s[:,:,0],np.full(s.shape[:2],-15.),s[:,:,1]],axis=-1)
        manifest['sections'][b]=buffers(b+'_section',segxyz,'<f4')
    write(OUT/'case.json',manifest);print('CASE VALIDATION',checks,flush=True)


if __name__=='__main__':
    started=time.time()
    try:
        census();export_case()
        write(OUT/'receipt.json',dict(status='PASS_FULL_REFERENCE_CENSUS_AND_NATIVE_CASE_EXPORT',scientific_verdict=None,
            elapsed_seconds=time.time()-started,config_sha256=sha(OUT/'config.json'),files={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ('.csv','.png','.bin','.json') and p.name!='receipt.json'}))
    except Exception as e:
        write(OUT/'receipt.json',dict(status='FAIL',scientific_verdict=None,error=repr(e)));raise
