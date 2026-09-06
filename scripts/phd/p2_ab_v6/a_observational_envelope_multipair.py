"""Measure all admissible frozen P2 decision-image pairs and robust group envelopes."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,time,traceback
from pathlib import Path
from datetime import datetime,timezone
import cv2
import numpy as np
from scipy.spatial import cKDTree
from scripts.phd.p2_ab_v2.sample_depth_mapping import read_colmap_array,sample_depth_rays
from src.phd.p2_ab_v6.a_observational_envelope import native_anchors,map_same_patch,choose_pairs,plane_samples,zncc_profiles,observational_envelopes


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False,ensure_ascii=False)+'\n')


def load_decision_views(rows,cfg,input_hashes):
    ids=sum(cfg['view_groups'],[]);by_id={r['image_id']:r for r in rows};views={}
    for image_id in ids:
        row=by_id[image_id]
        if row['role']!='decision':raise ValueError('A may only read decision-image membership')
        for path,expected in [(row['path'],row['sha256']),(row['valid_mask_path'],row['valid_mask_sha256']),(row['geometric_depth']['path'],row['geometric_depth']['sha256'])]:
            h=sha(path)
            if h!=expected:raise ValueError('input hash mismatch '+path)
            input_hashes[path]=h
        rgb=cv2.imread(row['path']);gray=cv2.cvtColor(rgb,cv2.COLOR_BGR2GRAY).astype(np.float32)/255
        valid=cv2.imread(row['valid_mask_path'],cv2.IMREAD_GRAYSCALE)
        h,w=gray.shape;factor=min(1.,cfg['maximum_view_dimension_px']/max(h,w));nw,nh=round(w*factor),round(h*factor)
        if factor<1:
            gray=cv2.resize(gray,(nw,nh),interpolation=cv2.INTER_AREA)
            valid=cv2.resize(valid,(nw,nh),interpolation=cv2.INTER_NEAREST)
        K=np.asarray(row['K'],np.float64);K[0]*=nw/w;K[1]*=nh/h
        yy,xx=np.mgrid[:nh,:nw];depth=read_colmap_array(Path(row['geometric_depth']['path']))
        mapping=sample_depth_rays(row,np.stack((xx+.5,yy+.5),axis=-1),current_K=K,depth=depth)
        R=np.asarray(row['R'],np.float64);t=np.asarray(row['t'],np.float64)
        views[image_id]=dict(image_id=image_id,gray=gray,valid=(valid>0).astype(np.float32),K=K,R=R,t=t,center=-R.T@t,
            context_depth=mapping['footprint_max_z'].astype(np.float32),width=nw,height=nh)
        print('loaded A view',image_id,nw,nh,flush=True)
    return views


def matched_als(seed,anchor,als,radius):
    out=np.full(len(anchor),-1,np.int64);distance=np.full(len(anchor),np.inf,np.float32)
    for unit in np.unique(seed['unit_index'][anchor]):
        ii=np.flatnonzero(seed['unit_index'][anchor]==unit);jj=np.flatnonzero(als['unit_index']==unit)
        if not len(jj):continue
        d,k=cKDTree(als['xyz'][jj,:2]).query(seed['xyz'][anchor[ii],:2])
        good=d<=radius;out[ii[good]]=jj[k[good]];distance[ii]=d
    return out,distance


def single_pair_historical_reference(seed,anchor,als,als_rows,views,cfg):
    xyz=seed['xyz'][anchor];normal=seed['normals'][anchor];offset=np.asarray(cfg['offsets_m'],np.float32)
    costs=np.full((len(anchor),2,len(offset)),np.nan,np.float32);als_costs=costs.copy();paired_mvs=costs.copy();paired_als=costs.copy()
    pixels=np.zeros((len(anchor),2),np.int16);als_pixels=pixels.copy();paired_pixels=pixels.copy()
    pairs=np.full((len(anchor),2,2),-1,np.int32);angles=np.zeros((len(anchor),2),np.float32)
    for g,group in enumerate(cfg['view_groups']):
        groupviews=[views[i] for i in group]
        ref,target,angle=choose_pairs(xyz,normal,groupviews,cfg);angles[:,g]=angle
        for ri,ti in sorted(set(zip(ref[ref>=0].tolist(),target[ref>=0].tolist()))):
            selected=np.flatnonzero((ref==ri)&(target==ti));a=groupviews[ri];b=groupviews[ti]
            pairs[selected,g]=[a['image_id'],b['image_id']]
            # Bounded batch keeps all raw samples available for matched source comparisons.
            for start in range(0,len(selected),256):
                ii=selected[start:start+256]
                refgray,targetgray,mask=plane_samples(xyz[ii],xyz[ii],normal[ii],offset,a,b,cfg)
                cost,n,_=zncc_profiles(refgray,targetgray,mask,cfg);costs[ii,g]=cost;pixels[ii,g]=n
                paired=np.flatnonzero(als_rows[ii]>=0)
                if len(paired):
                    jj=ii[paired];aa=als_rows[jj]
                    ar,at,am=plane_samples(xyz[jj],als['xyz'][aa],als['normals'][aa],offset,a,b,cfg)
                    ac,an,_=zncc_profiles(ar,at,am,cfg);als_costs[jj,g]=ac;als_pixels[jj,g]=an
                    common=mask[paired]&am
                    mc,pn,_=zncc_profiles(refgray[paired],targetgray[paired],common,cfg)
                    ac,_,_=zncc_profiles(ar,at,common,cfg)
                    paired_mvs[jj,g]=mc;paired_als[jj,g]=ac;paired_pixels[jj,g]=pn
        print('group',g,'paired anchors',int((ref>=0).sum()),'valid MVS profiles',int(np.isfinite(costs[:,g]).all(1).sum()),flush=True)
    return dict(costs=costs,als_costs=als_costs,paired_mvs=paired_mvs,paired_als=paired_als,pixels=pixels,als_pixels=als_pixels,paired_pixels=paired_pixels,pairs=pairs,angles=angles)


def save_profiles(path,costs,offset,seed_ids,**kwargs):
    np.savez_compressed(path,offsets_m=offset,cost=np.nan_to_num(costs.transpose(1,0,2),nan=1.),valid=np.isfinite(costs).transpose(1,0,2),seed_id=seed_ids,**kwargs)


def main(config_path):
    out=Path('/output')
    if any(out.iterdir()):raise ValueError('new empty output required')
    start=time.monotonic();cfg=json.loads(Path(config_path).read_text());cv2.setNumThreads(1)
    write(out/'STARTED.json',dict(utc=datetime.now(timezone.utc).isoformat(),scientific_verdict=None))
    try:
        source=Path(cfg['source_run']);common=Path(cfg['common_root'])
        inputs=[source/'mvs_source_seeds.npz',source/'als_source_seeds.npz',source/'image_only/gaussians_initial.npz',common/'views.json']
        input_hashes={str(p):sha(p)for p in inputs}
        seed=dict(np.load(inputs[0],allow_pickle=False));als=dict(np.load(inputs[1],allow_pickle=False));g0=np.load(inputs[2],allow_pickle=False)
        if not np.array_equal(seed['xyz'],g0['xyz']) or not np.array_equal(seed['seed_id'],g0['seed_id']):raise ValueError('MVS G0 lineage mismatch')
        rows=json.loads((common/'views.json').read_text())['views']
        decision=set(sum(cfg['view_groups'],[]));train=[r['image_id'] for r in rows if r['role']=='train'];ev=[r['image_id'] for r in rows if r['role']=='appearance_eval']
        if len(decision)!=22 or decision&set(train+ev) or set(cfg['view_groups'][0])&set(cfg['view_groups'][1]):raise ValueError('view separation failed')
        write(out/'view_split.json',dict(A_groups=cfg['view_groups'],B_train=train,B_eval=ev,note='Disjoint optimization/evidence views; MVS already shares image lineage. Not independent sensors or untouched confirmatory samples.'))
        sources=[Path(__file__),Path('src/phd/p2_ab_v6/a_observational_envelope.py'),Path('src/phd/p2_ab_v6/a_multipair_profiles.py'),Path(config_path),Path('scripts/phd/p2_ab_v6/a_observational_envelope_multipair_docker.sh'),Path('tests/phd/test_p2_ab_v6_a_envelope.py'),Path('tests/phd/test_p2_ab_v6_a_multipair.py'),Path('docs/experiments/phd/p2_ab_v6/A_MULTIPAIR_METHOD_ko_v6.md'),Path('scripts/phd/p2_ab_v2/sample_depth_mapping.py')]
        source_hashes={str(p):sha(p) for p in sources}
        for p in sources:
            dest=out/'source_snapshot'/str(p).lstrip('/');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        write(out/'config.json',cfg)
        anchors=native_anchors(seed,cfg['anchor_voxel_m']);print('native MVS anchors',len(anchors),flush=True)
        als_rows,als_dist=matched_als(seed,anchors,als,cfg['als_xy_radius_m'])
        views=load_decision_views(rows,cfg,input_hashes)
        from src.phd.p2_ab_v6.a_multipair_profiles import profile_source
        p=profile_source(seed,anchors,als,als_rows,views,cfg);offset=np.asarray(cfg['offsets_m'],np.float32)
        env=observational_envelopes(p['costs'],offset,cfg)
        mapping,distance=map_same_patch(seed,anchors,cfg['mapping_max_distance_m'],cfg['mapping_min_normal_cosine'])
        handoff=dict(seed_id=seed['seed_id'],anchor_id=mapping,anchor_distance_m=distance,normal=seed['normals'],native_patch_id=seed['native_patch_id'])
        for key in ['observation_low_m','observation_high_m','target_m','allowed_low_m','allowed_high_m','observable','initial_eligible','correction_needed','initial_max_use_error_m']:
            values=env[key][np.maximum(mapping,0)].copy();values[mapping<0]=False if values.dtype==bool else 0
            handoff[key]=values
        handoff['observable']&=mapping>=0
        np.savez_compressed(out/'handoff_mvs.npz',**handoff)
        np.savez_compressed(out/'anchors.npz',seed_index=anchors,seed_id=seed['seed_id'][anchors],xyz=seed['xyz'][anchors],normal=seed['normals'][anchors],patch_id=seed['native_patch_id'][anchors],unit_index=seed['unit_index'][anchors],als_row=als_rows,als_xy_distance_m=als_dist,**env)
        save_profiles(out/'mvs_profiles.npz',p['costs'],offset,seed['seed_id'][anchors],valid_pair_count=p['valid_pair_count'].T,common_patch_pixel_visits=p['pixels'].T)
        save_profiles(out/'als_profiles.npz',p['als_costs'],offset,seed['seed_id'][anchors],als_seed_row=als_rows,common_patch_pixels=p['als_pixels'].T)
        save_profiles(out/'paired_mvs_profiles.npz',p['paired_mvs'],offset,seed['seed_id'][anchors],common_patch_pixels=p['paired_pixels'].T)
        save_profiles(out/'paired_als_profiles.npz',p['paired_als'],offset,seed['seed_id'][anchors],common_patch_pixels=p['paired_pixels'].T)
        np.savez_compressed(out/'all_pair_profiles.npz',offsets_m=offset,seed_id=seed['seed_id'][anchors],pair_image_ids=p['pairs'].transpose(1,0,2,3),pair_angle_deg=p['angles'].transpose(1,0,2),
            mvs_cost=np.nan_to_num(p['pair_cost'].transpose(1,0,2,3),nan=1.),mvs_valid=np.isfinite(p['pair_cost']).transpose(1,0,2,3),
            als_cost=np.nan_to_num(p['als_pair_cost'].transpose(1,0,2,3),nan=1.),als_valid=np.isfinite(p['als_pair_cost']).transpose(1,0,2,3),
            common_mvs_cost=np.nan_to_num(p['common_pair_mvs_cost'].transpose(1,0,2,3),nan=1.),common_als_cost=np.nan_to_num(p['common_pair_als_cost'].transpose(1,0,2,3),nan=1.),common_valid=np.isfinite(p['common_pair_mvs_cost']).transpose(1,0,2,3),
            mvs_pixel_count=p['pair_pixels'].transpose(1,0,2),als_pixel_count=p['als_pair_pixels'].transpose(1,0,2),common_pixel_count=p['common_pair_pixels'].transpose(1,0,2))
        unit_rows=[]
        for unit in np.unique(seed['unit_index'][anchors]):
            ii=np.flatnonzero(seed['unit_index'][anchors]==unit)
            valid=np.isfinite(p['paired_mvs'][ii]).all((1,2))&np.isfinite(p['paired_als'][ii]).all((1,2));jj=ii[valid]
            m=p['paired_mvs'][jj].min(2).mean(1);a=p['paired_als'][jj].min(2).mean(1)
            unit_rows.append(dict(unit_index=int(unit),anchors=len(ii),paired_valid=len(jj),MVS_min_cost_median=float(np.median(m))if len(jj)else None,ALS_min_cost_median=float(np.median(a))if len(jj)else None,MVS_lower_cost_count=int((m<a).sum()),ALS_lower_cost_count=int((a<m).sum()),observable_anchors=int(env['observable'][ii].sum())))
        write(out/'source_unit_comparison.json',dict(units=unit_rows,interpretation='Same reference pixels and same view pairs only when both source profiles valid; nearest same-unit XY is a candidate proposal, not proven physical correspondence; no automatic source authority/fusion.',scientific_verdict=None))
        reason_names={0:'two_group_bounded_basin',1:'missing_or_untextured_pair',2:'high_minimum_cost',3:'search_boundary_or_flat',4:'multimodal',5:'group_disagreement',6:'use_error_budget_empty'}
        receipt=dict(status='COMPLETED_CONDITIONAL_OBSERVATIONAL_ENVELOPES',source='actual P2 current images and native MVS/ALS candidates',native_mvs_gaussians=len(seed['xyz']),anchors=len(anchors),observable_anchors=int(env['observable'].sum()),mapped_gaussians=int((mapping>=0).sum()),observable_gaussians=int(handoff['observable'].sum()),initial_eligible_gaussians=int(handoff['initial_eligible'].sum()),correction_needed_gaussians=int(handoff['correction_needed'].sum()),reason_counts={reason_names[k]:int((env['reason_code']==k).sum())for k in reason_names},paired_source_valid_anchors=sum(r['paired_valid']for r in unit_rows),systematic_error_calibrated=False,absolute_source_authority_status='ABSTAIN_UNCALIBRATED',normal_use_error_epsilon_m=cfg['normal_use_error_epsilon_m'],source_hashes=source_hashes,input_hashes=input_hashes,source_git_head=os.environ.get('JBGS_SOURCE_GIT_HEAD'),container_image=os.environ.get('JBGS_CONTAINER_IMAGE_ID'),runtime_seconds=time.monotonic()-start,versions=dict(numpy=np.__version__,opencv=cv2.__version__),limitations=['Normal-only finite grid; no tangential/pose/registration or systematic-error calibration.','Two disjoint raw-image groups still share camera/MVS lineage; no independent-likelihood multiplication.','Nearest same-patch transfer within declared distance/normal angle assumes locally shared offset; not per-point error certification.','Conditional epsilon is a development tolerance; not empirically calibrated accuracy.','No reference UAS/LoD2 read for fitting.','This is measured A-to-B displacement evidence, not a completed joint-error source-selection method.'],scientific_verdict=None)
        if any(sha(p)!=h for p,h in input_hashes.items()):raise ValueError('input changed during execution')
        receipt['output_hashes']={p.name:sha(p)for p in out.iterdir()if p.is_file() and p.name!='technical_receipt.json'}
        receipt['pair_protocol']=dict(selection=cfg['pair_selection'],aggregation=cfg['group_aggregation'],minimum_valid_pairs_per_group=cfg['minimum_valid_pairs_per_group'],valid_pair_count_quantiles=np.quantile(p['valid_pair_count'],[0,.5,.9,1]).tolist())
        write(out/'technical_receipt.json',receipt);write(out/'receipt.json',receipt);print(json.dumps({k:receipt[k]for k in ['status','anchors','observable_anchors','observable_gaussians','initial_eligible_gaussians','correction_needed_gaussians','reason_counts','runtime_seconds']},indent=2),flush=True)
    except Exception:
        write(out/'FAILED.json',dict(traceback=traceback.format_exc(),scientific_verdict=None));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True);main(parser.parse_args().config)
