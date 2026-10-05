"""Frozen R1-R5 UAS evaluation and localization of masked-ray deterioration."""
import gc
import json
import time
from pathlib import Path
import laspy
import numpy as np
from PIL import Image
from matplotlib.path import Path as Polygon
from matplotlib.collections import LineCollection
import matplotlib.pyplot as plt
from analyze_final_surfaces import read, write, sha, cropped_mesh, distances, stats, self_test

OUT = Path('/out'); CFG = read(OUT/'config.json'); ART = Path('/art')
ROOT = ART/CFG['attempt_relative']; ANALYSIS = ROOT/CFG['analysis']
theta = np.deg2rad(70); BASIS = np.array([[np.cos(theta),np.sin(theta)],[np.sin(theta),-np.cos(theta)]])
START = time.time()


def progress(stage, **kw):
    x = dict(stage=stage, elapsed_seconds=time.time()-START, scientific_verdict=None, **kw)
    write(OUT/'status.json', x)
    with (OUT/'progress.jsonl').open('a') as f: f.write(json.dumps(x)+'\n')
    print(json.dumps(x), flush=True)


def zones_for(region):
    path = ART/CFG['r1_review_relative']/'config.json' if region == 'R1' else ROOT/region/'review_zones.json'
    return read(path)['zones']


def zone_ids(uv, zones):
    result = np.zeros(len(uv), np.uint8)
    for z in zones[1:]:
        result[Polygon(z['polygon']).contains_points(uv, radius=1e-9)] = int(z['id'][1:])
    return result


def draw_zones(ax, zones):
    for z in zones[1:]:
        p = np.array(z['polygon']); ax.plot(*np.vstack([p,p[0]]).T, c='0.45', lw=.7)
        ax.text(*p.mean(0), z['id'], fontsize=8, ha='center', bbox=dict(facecolor='white',alpha=.8,edgecolor='none'))
    ax.set_aspect('equal'); ax.set_xlabel('object u [m]'); ax.set_ylabel('object v [m]'); ax.invert_yaxis()


def localize_r1():
    run = read(ROOT/'config.json'); inp = ART/run['r1_prep_relative']/'result/input'
    legacy = ART/run['r1_run_relative']; extract0 = legacy/read(legacy/'mesh_recovery.json')['relative']/'extract_final'
    override = read(ROOT/'execution/artifact_overrides.json')
    extract1 = ROOT/override.get('R1',{}).get('extract_local_prior0','R1/extract_local_prior0')
    views = sorted(read(inp/'scene/split_manifest.json')['train'],key=lambda v:v['name'])
    maskrec = read(ROOT/'R1/masks/receipt.json'); counts = {r['name']:r['pixels'] for r in maskrec['masks']}
    data = []; camera_rows = []; zones = zones_for('R1')
    for i,v in enumerate(views):
        name = Path(v['name']).stem
        if not counts[name]: continue
        mask = np.load(ROOT/'R1/masks'/(name+'.npy')); y,x = np.nonzero(mask)
        md = np.load(inp/'mvs_rgb/raw_depth'/(name+'.npy'))[mask]
        d0 = np.asarray(Image.open(extract0/'model/train/ours_30000/vis'/('depth_%05d.tiff'%i)))[mask]
        d1 = np.asarray(Image.open(extract1/'model/train/ours_30000/vis'/('depth_%05d.tiff'%i)))[mask]
        rays = np.column_stack([x,y,np.ones(len(x))])@np.linalg.inv(v['K']).T
        xyz = (rays*md[:,None]-v['t'])@np.array(v['R'])
        uv = xyz[:,:2]@BASIS.T; delta = abs(d1-md)-abs(d0-md)
        assert np.isfinite(delta).all() and len(x) == counts[name]
        data.append(np.column_stack([uv,xyz[:,2],delta,abs(d0-md),abs(d1-md),np.full(len(x),i)]))
        camera_rows.append(dict(name=name,n=len(x),worse_over_1m=int((delta>1).sum()),
                                mean_absolute_control=float(abs(d0-md).mean()),mean_absolute_release=float(abs(d1-md).mean())))
    a = np.concatenate(data); assert len(a) == maskrec['total_pixels']
    cells = np.floor(a[:,:2]/2).astype(int); keys, inverse = np.unique(cells,axis=0,return_inverse=True)
    rows = []
    for k,xy in enumerate(keys):
        sel = inverse == k; b = a[sel]
        rows.append(dict(uv_min=(xy*2).tolist(),n=len(b),views=len(np.unique(b[:,6])),
                         mean_delta=float(b[:,3].mean()),median_delta=float(np.median(b[:,3])),
                         worse_over_1m=int((b[:,3]>1).sum()),median_local_z=float(np.median(b[:,2]))))
    zid = zone_ids(a[:,:2],zones)
    summary = dict(status='PASS_MASKED_RAY_LOCALIZATION',scientific_verdict=None,observations=len(a),
                   location='Backprojection of the input MVS target, not the rendered floater position.',
                   zone_counts={str(z):dict(n=int((zid==z).sum()),worse_over_1m=int(((zid==z)&(a[:,3]>1)).sum())) for z in np.unique(zid)},
                   cells=rows,top_views=sorted(camera_rows,key=lambda r:r['worse_over_1m'],reverse=True)[:8],
                   mask_receipt_sha256=sha(ROOT/'R1/masks/receipt.json'))
    write(OUT/'R1_masked_localization.json',summary)
    base = np.load(ANALYSIS/'R1_paired_samples.npz'); xy = base['xyz'][base['source']==0,:2]@BASIS.T
    fig,axs = plt.subplots(1,2,figsize=(15,7))
    for ax in axs: ax.scatter(xy[:,0],xy[:,1],s=.4,c='0.85'); draw_zones(ax,zones)
    cxy = keys*2+1
    sc=axs[0].scatter(*cxy.T,c=[r['mean_delta'] for r in rows],s=28,marker='s',cmap='coolwarm',vmin=-1,vmax=1)
    fig.colorbar(sc,ax=axs[0],label='Mean change in absolute MVS depth residual [m]')
    sc=axs[1].scatter(*cxy.T,c=[100*r['worse_over_1m']/r['n'] for r in rows],s=28,marker='s',cmap='magma',vmin=0,vmax=50)
    fig.colorbar(sc,ax=axs[1],label='Observations with residual worsening > 1m [%]')
    axs[0].set_title('R1: affected observations mapped to MVS target surface')
    axs[1].set_title('Repeated views included; 2m cells; not independent accuracy')
    fig.tight_layout();fig.savefig(OUT/'R1_masked_localization.png',dpi=150);plt.close(fig)
    progress('R1_MASK_LOCALIZED', zone_counts=summary['zone_counts'])


def crop_reference():
    spec=CFG['reference']; path=ART/spec['relative']; assert path.stat().st_size==spec['bytes']; assert sha(path)==spec['sha256']
    regions={r:zones_for(r) for r in CFG['regions']}; kept={r:[] for r in regions}; ids={r:[] for r in regions}; classes={r:[] for r in regions}
    bounds={r:(np.min(z[0]['polygon'],axis=0),np.max(z[0]['polygon'],axis=0)) for r,z in regions.items()}
    offset=0
    with laspy.open(path) as reader:
        assert reader.header.point_count==spec['point_count']
        geokeys=[dict(key_id=int(k.id),value_offset=int(k.value_offset)) for v in reader.header.vlrs if hasattr(v,'geo_keys') for k in v.geo_keys]
        source_epsg=next((k['value_offset'] for k in geokeys if k['key_id']==3072),None)
        assert source_epsg == 32632
        header=dict(point_count=reader.header.point_count,mins=reader.header.mins.tolist(),maxs=reader.header.maxs.tolist(),
                    source_epsg=source_epsg,geokeys=geokeys,scales=reader.header.scales.tolist(),offsets=reader.header.offsets.tolist())
        for chunk in reader.chunk_iterator(2_000_000):
            xyz=np.column_stack([np.asarray(chunk.x),np.asarray(chunk.y),np.asarray(chunk.z)])-CFG['world_shift']
            uv=xyz[:,:2]@BASIS.T
            for r,(lo,hi) in bounds.items():
                mask=((uv>=lo)&(uv<hi)).all(1)&(xyz[:,2]>=-90)&(xyz[:,2]<80)
                kept[r].append(xyz[mask].astype(np.float32)); ids[r].append(np.flatnonzero(mask)+offset); classes[r].append(np.asarray(chunk.classification)[mask])
            offset+=len(chunk)
            if offset%20_000_000==0:progress('UAS_STREAM',raw_points=offset)
    records={}
    for r in regions:
        xyz=np.concatenate(kept[r]); raw=np.concatenate(ids[r]); cls=np.concatenate(classes[r]); n=len(xyz)
        # One actual native row per fixed 3D voxel; no point averaging or outcome-dependent selection.
        _,select=np.unique(np.floor(xyz/CFG['reference_voxel_m']).astype(np.int32),axis=0,return_index=True);select=np.sort(select)
        xyz=xyz[select]; raw=raw[select]; cls=cls[select]
        np.savez_compressed(OUT/(r+'_reference.npz'),xyz=xyz,raw_rows=raw,classification=cls)
        records[r]=dict(native_count=n,sampled_count=len(xyz),classes={str(k):int(v) for k,v in zip(*np.unique(cls,return_counts=True))},
                        sha256=sha(OUT/(r+'_reference.npz')))
    write(OUT/'reference_receipt.json',dict(status='PASS_REFERENCE_CROPS',scientific_verdict=None,source=spec,header=header,regions=records,
          transform='Raw numeric XYZ minus shared shift only. No fitted alignment. Source EPSG:32632; inherited working EPSG:25832; datum/epoch accuracy uncalibrated.',
          sampling='First native row per fixed 0.25m 3D voxel, identical queries for every condition; all classes retained.'))
    del kept,ids,classes;gc.collect();progress('REFERENCE_READY',regions=records)


def section_segments(xyz,tri,spec):
    uv=xyz[:,:2]@BASIS.T; segments=[]
    for start in range(0,len(tri),100000):
        ids=tri[start:start+100000];d=uv[ids,1]-spec['v'];mask=(d.min(1)<0)&(d.max(1)>0)
        ids=ids[mask];d=d[mask];points=np.full((len(ids),3,2),np.nan)
        for k,(i,j) in enumerate([(0,1),(1,2),(2,0)]):
            valid=d[:,i]*d[:,j]<0; t=d[valid,i]/(d[valid,i]-d[valid,j]);ia=ids[valid,i];ib=ids[valid,j]
            points[valid,k,0]=uv[ia,0]+t*(uv[ib,0]-uv[ia,0]);points[valid,k,1]=xyz[ia,2]+t*(xyz[ib,2]-xyz[ia,2])
        valid=np.isfinite(points[:,:,0]);rows=np.where(valid.sum(1)==2)[0]
        seg=points[rows][valid[rows]].reshape(-1,2,2)
        use=(seg[:,:,0].max(1)>=spec['u'][0])&(seg[:,:,0].min(1)<=spec['u'][1]);segments.append(seg[use])
    return np.concatenate(segments) if segments else np.empty((0,2,2))


def evaluate():
    totals={};allrows=[]
    for r in CFG['regions']:
        ref=np.load(OUT/(r+'_reference.npz'))['xyz']; uv=ref[:,:2]@BASIS.T;zones=zones_for(r);zid=zone_ids(uv,zones)
        modelinfo=read(ANALYSIS/(r+'_summary.json'))['metadata']['models'];ds={};sections={}
        for branch in ['mvs','da3','local_prior0']:
            info=modelinfo[branch];path=Path(info['path']);assert sha(path)==info['sha256']
            xyz,tri,size=cropped_mesh(path,ref,10);ds[branch],_=distances(xyz,tri,ref,10)
            if r in CFG['sections']:sections[branch]=section_segments(xyz,tri,CFG['sections'][r])
            del xyz,tri;gc.collect();progress('MESH_EVALUATED',region=r,branch=branch,points=len(ref))
        run=read(ROOT/'config.json')
        priorpath=(ART/run['r1_prep_relative']/'result/input' if r=='R1' else ROOT/r/'preparation/input')/'surface/mesh_arrays.npz'
        prior=np.load(priorpath);dprior,_=distances(prior['xyz'].astype(np.float32),prior['faces'].astype(np.uint32),ref,10)
        np.save(OUT/(r+'_uas_to_prior.npy'),dprior)
        write(OUT/(r+'_prior_reference.json'),dict(scientific_verdict=None,source=str(priorpath),sha256=sha(priorpath),summary=stats(dprior),
              evaluation_only_bands={'prior_within_025m':int((dprior<=.25).sum()),
                 'prior_within_025m_baseline_over_1m':int(((dprior<=.25)&(ds['mvs']>1)).sum()),
                 'prior_over_1m_baseline_over_1m':int(((dprior>1)&(ds['mvs']>1)).sum()),
                 'prior_over_1m_baseline_within_025m':int(((dprior>1)&(ds['mvs']<=.25)).sum())},
              note='Reference discrepancy bands for descriptive evaluation only; not change truth, MVS causality, or new training labels.'))
        np.savez_compressed(OUT/(r+'_uas_distances.npz'),zone=zid,**ds)
        rows=[]
        for z in [-1]+[int(z['id'][1:]) for z in zones]:
            sel=zid==z if z>=0 else np.ones(len(ref),bool)
            for branch in ds:
                row=dict(region=r,zone='ALL' if z<0 else 'Z%02d'%z,branch=branch,**stats(ds[branch][sel]))
                row['capped_at_10m_count']=int((ds[branch][sel]>=10).sum());rows.append(row)
        write(OUT/(r+'_uas_summary.json'),dict(status='PASS_REFERENCE_DISTANCE_DIAGNOSTIC',scientific_verdict=None,rows=rows,models=modelinfo))
        allrows+=rows;totals[r]={b:stats(d) for b,d in ds.items()}
        fig,axs=plt.subplots(1,3,figsize=(18,7),sharex=True,sharey=True)
        step=max(1,len(ref)//100000)
        for ax,(b,d) in zip(axs,ds.items()):
            sc=ax.scatter(uv[::step,0],uv[::step,1],c=d[::step],s=1,cmap='viridis',vmin=0,vmax=2)
            draw_zones(ax,zones);ax.set_title(r+' '+b);fig.colorbar(sc,ax=ax,label='UAS point to mesh distance [m]')
        # sharey axes invert collectively only once
        if not axs[0].yaxis_inverted():axs[0].invert_yaxis()
        fig.suptitle('Same UAS reference points for all conditions; all heights/classes; display saturates at 2m')
        fig.tight_layout();fig.savefig(OUT/(r+'_uas_map.png'),dpi=140);plt.close(fig)
        if sections:
            spec=CFG['sections'][r];select=(abs(uv[:,1]-spec['v'])<=.25)&(uv[:,0]>=spec['u'][0])&(uv[:,0]<=spec['u'][1])
            source=np.load(ANALYSIS/(r+'_paired_samples.npz'));m=source['source']==0;mp=source['xyz'][m];muv=mp[:,:2]@BASIS.T
            msel=(abs(muv[:,1]-spec['v'])<=.5)&(muv[:,0]>=spec['u'][0])&(muv[:,0]<=spec['u'][1])
            fig,axs=plt.subplots(2,1,figsize=(13,9),gridspec_kw=dict(height_ratios=[1,2]))
            axs[0].scatter(muv[:,0],muv[:,1],s=1,c='0.65');draw_zones(axs[0],zones)
            axs[0].plot(spec['u'],[spec['v']]*2,c='red',lw=3);axs[0].set_title(r+' fixed section location')
            colors=dict(mvs='#1675be',da3='#ed8a20',local_prior0='#9b42a6')
            for b,seg in sections.items():
                axs[1].add_collection(LineCollection(seg,colors=colors[b],linewidths=1,label=b,alpha=.8))
            axs[1].scatter(uv[select,0],ref[select,2],s=5,c='black',label='UAS LiDAR (+/-0.25m strip)',zorder=4)
            axs[1].scatter(muv[msel,0],mp[msel,2],s=16,c='#2dbb56',marker='x',label='MVS input (+/-0.5m strip)',zorder=5)
            center=float(np.median(mp[msel,2])) if msel.any() else float(np.median(ref[select,2]))
            axs[1].set_xlim(spec['u']);axs[1].set_ylim(center-4,center+4);axs[1].set_xlabel('object u [m]');axs[1].set_ylabel('local z [m]')
            axs[1].grid(alpha=.3);axs[1].legend(fontsize=8);axs[1].set_title('Exact mesh-plane intersections at v=%.1fm; display zoom: input MVS median z +/-4m'%spec['v'])
            fig.tight_layout();fig.savefig(OUT/(r+'_section.png'),dpi=160);plt.close(fig)
            np.savez_compressed(OUT/(r+'_section_segments.npz'),**sections)
    import csv
    with (OUT/'uas_zone_metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(allrows[0]));w.writeheader();w.writerows(allrows)
    write(OUT/'receipt.json',dict(status='PASS_UAS_REFERENCE_DISTANCE_DIAGNOSTIC',scientific_verdict=None,regions=totals,
          reference_receipt_sha256=sha(OUT/'reference_receipt.json'),config_sha256=sha(OUT/'config.json'),script_sha256=sha(__file__),
          versions=dict(numpy=np.__version__,laspy=laspy.__version__),elapsed_seconds=time.time()-START,
          limitations=['Reference-to-mesh distance is one-way; extra surfaces can be missed.',
                       'All-height zone metrics are not roof-only accuracy. No new change/authority labels.',
                       'No reference fitting, datum calibration, source-mask updates, or new optimization.']))


if __name__ == '__main__':
    try:
        self_test();progress('STARTED')
        if CFG.get('reuse_localization'):
            import shutil
            old=ROOT/CFG['reuse_localization']
            for name,digest in CFG['localization_hashes'].items():
                assert sha(old/name)==digest;shutil.copy2(old/name,OUT/name)
            progress('LOCALIZATION_REUSED')
        else:localize_r1()
        crop_reference();evaluate();progress('COMPLETE')
    except Exception as exc:
        import traceback
        (OUT/'failure.log').write_text(traceback.format_exc());progress('FAILED',error=repr(exc));raise
