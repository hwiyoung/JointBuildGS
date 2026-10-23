"""Preserve historical values; report exact patch matches and changed contexts."""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from analysis_common import O,DOC,CFG,CELLS,KEYS,load,save_table,quantiles
from preflight import PH,PREP,sha
from export_values import classify
from image_inventory import depth
from distributions import site_masks
U=PH/'main_uncert_v1/PHD-MAIN-UNCERT-v1';S0=PH/'main_stage0_v1/PHD-MAIN-STAGE0-v1'
SITES=['B0_b10','B173nb_b10','R1rep_b10']

def cross(rows,prior,site,kind,a,b,area,anames,bnames):
    area=np.asarray(area,dtype=np.float64)
    assert len(a)==len(b)==len(area)
    assert np.all((a>=0)&(a<len(anames))) and np.all((b>=0)&(b<len(bnames)))
    start=len(rows)
    for ai in range(len(anames)):
        for bi in range(len(bnames)):
            m=(a==ai)&(b==bi)
            rows.append(dict(prior=prior,site=site,comparison=kind,from_cell=anames[ai],to_cell=bnames[bi],patches=int(m.sum()),area_m2=float(area[m].sum())))
    assert sum(r['patches'] for r in rows[start:])==len(a)
    assert np.isclose(sum(r['area_m2'] for r in rows[start:]),np.sum(area),rtol=1e-12)

def main():
    comparisons=[];taurows=[];twelve=[];gtrows=[];depthrows=[]
    oldcells=json.loads(Path('/repo/configs/phd/main_uncert_v1/uncert_v1.json').read_text())['cells']['order']
    for prior in ['LoD2','ALS']:
        new=load(prior);tree=cKDTree(new['raw_centre'])
        for site in SITES:
            f=U/'patch_values'/f'{site}__{prior}__R1.5.npz'
            with np.load(f) as z:old={k:z[k] for k in z.files}
            meta=json.loads((S0/'s61/box'/site/prior/'summary.json').read_text());shift=np.array(meta['store_frame_shift'])
            raw=old['centre']-shift;ev=old['in_eval'].astype(bool);ids=np.flatnonzero(ev)
            dist,idx=tree.query(raw[ids],workers=8);dot=np.sum(old['normal'][ids]*new['normal'][idx],axis=1)
            match=(dist<=1e-5)&(dot>=1-1e-5)
            geometry_candidates=int(match.sum());building_mismatch=0
            if prior=='LoD2':
                same_building=old['building'][ids]==new['building'][idx]
                building_mismatch=int((match&~same_building).sum());match&=same_building
            uu,nn=np.unique(idx[match],return_counts=True)
            ambiguous=match&np.isin(idx,uu[nn>1]);match&=~ambiguous
            a=ids[match];b=idx[match];assert len(np.unique(b))==len(b)
            values={}
            for oldkey,newkey in [('gt_p','gt_p'),('mvs_a_p','mvs_p'),('mvs_a_u','u_mvs'),('mvs_a_e','mvs_a_e')]+([('als_u','u_prior'),('als_e','prior_error')] if prior=='ALS' else []):
                x=old[oldkey][a];y=new[newkey][b];valid=np.isfinite(x)&np.isfinite(y)
                values[oldkey]=dict(paired=int(valid.sum()),old=quantiles(x[valid]),new=quantiles(y[valid]),new_minus_old=quantiles(y[valid]-x[valid]),
                    exact_equal=int((x[valid]==y[valid]).sum()))
            comparisons.append(dict(site=site,prior=prior,old_eval_patches=len(ids),exact_raw_geometry_matches=int(match.sum()),
                unique_new_matches=len(np.unique(b)),unmatched=int((~match).sum()),nearest_raw_distance_m=quantiles(dist),
                geometry_candidates_before_identity_check=geometry_candidates,building_mismatch_excluded=building_mismatch,
                duplicate_new_correspondence_excluded=int(ambiguous.sum()),
                building_identity_checked=(prior=='LoD2'),
                centre_shift_difference_m=quantiles(np.linalg.norm(new['centre'][b]-old['centre'][a],axis=1)),values=values,
                historical_source=str(f),historical_sha256=sha(f),old_frame_shift_m=shift.tolist(),
                context_changes=['new 100 m tiling and 10 m halo','training-only full-area image pool and name-order split','tile-index and patch-index RNG context',
                    'per-tile registration instead of historical fixed exploration-region shift','nadir only; historical B0 may include manual LiDAR']+
                    (['historical ALS patch table lacks assigned building IDs; exact geometry and unique correspondence required'] if prior=='ALS' else []),scientific_verdict=None))
            # Both tau tables use the same values within each table: first old
            # measurements on all old evaluation patches, then new exact matches.
            for label,g,p,e,t,ar in [
                ('historical_values_all_old_eval',old['gt_status'][ids],old['gt_p'][ids],old['mvs_a_e'][ids],old['tau'][ids],old['area'][ids]),
                ('new_values_exact_geometry_matches',new['gt_status'][b],new['gt_p'][b],new['mvs_a_e'][b],old['tau'][a],new['area'][b])]:
                ca=classify(g,p,e,t);cb=classify(g,p,e,CFG['tau_m'][prior]);cross(taurows,prior,site,label,ca,cb,ar,CELLS,CELLS)
            ca=old['cell'][ids];cb=classify(old['gt_status'][ids],old['gt_p'][ids],old['mvs_a_e'][ids],CFG['tau_m'][prior])
            cross(twelve,prior,site,'old_twelve_to_seven_old_values_fixed_tau',ca,cb,old['area'][ids],oldcells,CELLS)
            cross(twelve,prior,site,'old_twelve_to_seven_new_exact_matches',old['cell'][a],classify(new['gt_status'][b],new['gt_p'][b],new['mvs_a_e'][b],CFG['tau_m'][prior]),new['area'][b],oldcells,CELLS)
    newnames=set(json.loads((O/'image_split.json').read_text())['train'])
    for site in SITES:
        od=PREP/'mvs'/('box_'+site)/'stereo/depth_maps'
        files=sorted(p for p in od.glob('*.geometric.bin') if p.name.removesuffix('.geometric.bin') in newnames)
        samples=[files[i] for i in np.unique(np.linspace(0,len(files)-1,min(3,len(files))).round().astype(int))] if files else []
        for oldf in samples:
            newf=O/'mvs/full/stereo/depth_maps'/oldf.name
            if not newf.exists():depthrows.append(dict(site=site,image=oldf.name,status='new depth missing'));continue
            a=depth(oldf);b=depth(newf);assert a.shape==b.shape
            av=np.isfinite(a)&(a>0);bv=np.isfinite(b)&(b>0);m=av&bv
            depthrows.append(dict(site=site,image=oldf.name,old_sha256=sha(oldf),new_sha256=sha(newf),byte_equal=sha(oldf)==sha(newf),
                old_valid=int(av.sum()),new_valid=int(bv.sum()),both_valid=int(m.sum()),validity_differ=int((av!=bv).sum()),
                abs_depth_difference_m=quantiles(np.abs(b[m]-a[m])),signed_depth_difference_m=quantiles(b[m]-a[m]),
                old_source=str(oldf),new_source=str(newf),source_pool_changed=True))
        gf=U/'points'/site/'gt_xyz.npy'
        if not gf.exists():gtrows.append(dict(site=site,status='historical GT point file not found',source=str(gf)));continue
        oldgt=np.load(gf,mmap_mode='r');mask=site_masks(oldgt)[site];ii=np.flatnonzero(mask)
        ii=ii[np.linspace(0,len(ii)-1,min(10000,len(ii))).round().astype(int)] if len(ii) else ii
        X=oldgt[ii];nearest=np.full(len(X),np.inf)
        for tile in json.loads((O/'inputs/tiles.json').read_text()):
            x0,y0,x1,y1=np.array(tile['buffer_global'])-[690953.,5336071.,690953.,5336071.]
            m=(X[:,0]>=x0)&(X[:,0]<x1)&(X[:,1]>=y0)&(X[:,1]<y1)
            if not m.any():continue
            y=np.load(O/'holdout/internal/points'/tile['id']/'gt_xyz.npy',mmap_mode='r')
            if len(y):nearest[m]=np.minimum(nearest[m],cKDTree(y).query(X[m],workers=8)[0])
        gtrows.append(dict(site=site,old_eval_points=int(mask.sum()),sampled_points=len(X),nearest_new_GT_distance_m=quantiles(nearest),
            within_1mm=int((nearest<=.001).sum()),outside_new_support=int((~np.isfinite(nearest)).sum()),old_source=str(gf),
            point_precision='old float32 versus new raw-derived float64',nadir_only_new=True,manual_mix_difference=(site=='B0_b10')))
    save_table('맞춰보기_패치와값',comparisons);save_table('맞춰보기_tau_교차표',taurows);save_table('맞춰보기_열두칸_교차표',twelve)
    save_table('맞춰보기_MVS깊이',depthrows);save_table('맞춰보기_참값점',gtrows)
    print('historical comparisons complete',flush=True)
if __name__=='__main__':main()
