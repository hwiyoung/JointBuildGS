"""Independent source-coordinate, projection and delivery audit for R10."""
import hashlib
import io
import json
import platform
import zipfile

import numpy as np
import PIL
from PIL import Image
import matplotlib
import scipy

from common import CFG,DOC,PAY,REPO,RAW,G,load,dump,sha,now


def main():
    out=DOC/'revision_10';cache=PAY/'revision_10';cfg=CFG/'slide5_context_revision_10.json'
    c=load(cfg);lock=load(out/'input_lock.json');meta=load(out/'geometry.json');record=load(out/'render.json')
    assert sha(cfg)==lock['config_sha256']==meta['config_sha256']==record['config_sha256']
    assert sha(REPO/'scripts/phd/slide_photo_v1/slide5_context_revision_10.py')==record['script_sha256']
    for rec in lock['sources'].values():assert sha(rec['path'])==rec['sha256']
    for name in ['display_lock.json','display_lock_02.json']:
        a=load(out/name);assert sha(a['path'])==a['sha256']
    assert sha(cache/'geometry.npz')==meta['geometry_sha256']
    sources=record['sources'];data=np.load(cache/'geometry.npz');checks={};details={}
    lo=np.asarray(meta['context_min_xyz']);hi=np.asarray(meta['context_max_xyz'])
    for key in ['prior','mvs','gt']:
        if key=='prior':raw=np.load(sources['roof_prior_mesh'])['V']+meta['roof_registration_shift']
        else:raw=np.load(sources['roof_mvs' if key=='mvs' else 'roof_reference'],mmap_mode='r')
        ids=data['roof_'+key+'_ids'];error=float(np.max(np.abs(data['roof_'+key]-raw[ids])));assert error<1e-10
        crop=[]
        for start in range(0,len(raw),250000):
            block=raw[start:start+250000];crop.append(start+np.flatnonzero(np.all((block>=lo)&(block<=hi),axis=1)))
        crop=np.concatenate(crop);cells=np.floor(np.asarray(raw[crop],float)/c['roof_display_voxel_m']).astype(np.int64)
        _,first=np.unique(cells,axis=0,return_index=True)
        assert np.array_equal(ids,crop[np.sort(first)])
        expected=np.all((data['roof_'+key]>=meta['highlight_min_xyz'])&(data['roof_'+key]<=meta['highlight_max_xyz']),axis=1)
        assert np.array_equal(expected,data['roof_'+key+'_core'])
        details['roof_'+key]=dict(coordinate_max_error_m=error,context_count=len(crop),sampled_points=len(ids),highlighted_points=int(expected.sum()))
    checks['roof_original_points_and_fixed_voxel_rule']=True
    raw=np.load(sources['wall_cloud']);section=load(sources['wall_section'])
    for key in ['prior','mvs','gt']:
        ids=data['wall_'+key+'_ids'];assert np.array_equal(ids,section['series'][key]['point_indices'])
        error=float(np.max(np.abs(data['wall_'+key]-raw[key][ids])));assert error<1e-10
        details['wall_'+key]=dict(coordinate_max_error_m=error,points=len(ids),all_frozen_points_retained=True)
    checks['wall_all_original_fixed_points_retained']=True
    render=record['render'];view=render['roof_view'];R=np.asarray(view['rotation'])
    assert np.allclose(R@R.T,np.eye(3)) and np.isclose(np.linalg.det(R),1)
    assert render['wall_views']['prior']==render['wall_views']['mvs']
    checks['orthonormal_camera_equal_metric_scale_and_matched_views']=True
    wall_bins=np.asarray(section['bin_centres_m']);wall_k=int(np.argmin(abs(wall_bins)))
    wall_origin=np.asarray(meta['wall_origin'])
    wall_u=np.asarray(section['source_view']['axis1']);wall_n=np.asarray(section['source_view']['axis2'])
    wall_endpoints=np.stack([wall_origin+wall_bins[wall_k]*wall_u+section['series'][key]['median'][wall_k]*wall_n for key in ['gt','mvs']])
    wall_ann=render['wall_views']['mvs']['midpoint_arrow']
    assert wall_ann['bin_index']==wall_k
    assert np.array_equal(np.asarray(wall_ann['endpoints_xyz']),wall_endpoints)
    checks['wall_midpoint_annotation_replayed']=True
    ex=load(sources['roof_example'])['examples'][0];bins=np.asarray(ex['bin_centres_m']);H=np.asarray(ex['heights_model_m'])
    u=np.asarray(ex['end_xy'])-ex['start_xy'];u/=np.linalg.norm(u)
    xy=np.asarray(ex['start_xy'])+bins[:,None]*u
    for key,j in [('prior',0),('mvs',1)]:
        valid=np.isfinite(H[:,j]);assert np.array_equal(np.asarray(render['roof_source_sections'][key]),np.c_[xy[valid],H[valid,j]])
    k=int(np.argmin(abs(bins-ex['length_m']/2)));ann=render['roof_midpoint_annotation'];assert ann['bin_index']==k
    assert np.array_equal(np.asarray(ann['endpoints_xyz']),np.array([[*xy[k],H[k,0]],[*xy[k],H[k,2]]]))
    checks['source_profiles_and_midpoint_annotation_replayed']=True
    photo_replay={}
    for key in ['roof','wall']:
        pm=load(sources[key+'_photo'])['photo'];source=pm['source']['photo'];p=render['photos'][key]
        with zipfile.ZipFile(RAW) as z:rawjpg=z.read(source['original_member'])
        assert hashlib.sha256(rawjpg).hexdigest()==source['original_sha256']
        X=np.asarray(pm['section_line_xyz' if key=='roof' else 'section_centre_line_xyz'])
        assert np.array_equal(np.asarray(p['section_line_xyz']),X)
        pose=dict(source['pose'],R=np.asarray(source['pose']['R']),t=np.asarray(source['pose']['t']))
        uv,_=G.project(X,pose,source['camera'])
        if p['rotation']==90:uv=np.c_[uv[:,1],source['camera']['w']-uv[:,0]]
        crop=np.asarray(p['crop']);scale=np.asarray(p['photo_content_size'])/(crop[2:]-crop[:2])
        q=(uv-crop[:2])*scale+p['content_offset'];error=float(np.max(np.abs(q-p['section_line_px'])));assert error<1e-8
        assert abs(scale[0]/scale[1]-1)<.003
        if key=='roof':assert np.array_equal(np.asarray(render['roof_guide_xyz']),X)
        photo_replay[key]=dict(projection_max_error_px=error,source_jpeg_hash_matches=True,relative_xy_scale_error=float(abs(scale[0]/scale[1]-1)))
    checks['photo_source_bytes_exact_projection_and_shared_markers']=True
    full=Image.open(out/'figures/slide5_context_pairs.png');preview=Image.open(out/'previews/slide5_context_pairs.png');blind=Image.open(out/'qa/slide5_without_explanations.png')
    assert full.size==(3840,2160) and preview.size==blind.size==(1920,1080)
    # Inside the figure panels, masking headings must leave the actual evidence intact.
    boxes=[(78,250,560,550),(610,250,1180,550),(1235,250,1810,550),(95,740,545,1015),(610,780,1180,975),(1235,780,1810,975)]
    for box in boxes:assert np.array_equal(np.asarray(preview.crop(box)),np.asarray(blind.crop(box))),box
    checks['explanation_mask_preserves_actual_figure_panels']=True
    reviews=load(out/'qa/blind_reviews.json')
    for review in reviews['reviews']:assert sha(out/review['image_path'])==review['image_sha256']
    checks['blind_review_image_hashes_match']=True
    checks['source_and_config_hashes_unchanged']=True
    files={str(p.relative_to(out)):dict(sha256=sha(p),bytes=p.stat().st_size) for root in ['figures','previews','qa'] for p in sorted((out/root).glob('*.png'))}
    dump(out/'verification.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),status='PASS',checks=checks,
         coordinate_replay=details,photo_replay=photo_replay,files=files,
         audit_script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/verify_slide5_context_10.py'),
         versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,matplotlib=matplotlib.__version__,scipy=scipy.__version__),
         scientific_scope='Two illustrative input cases only; no training or method result; reader judgement stored separately'))
    paths=[p for p in sorted(out.rglob('*')) if p.is_file() and p.name!='handover.json']
    members={'docs/experiments/phd/slide_photo_v1/revision_10/'+str(p.relative_to(out)):p for p in paths}
    for pattern in ['slide5_context_revision_10*.json']:
        for p in CFG.glob(pattern):members['configs/phd/slide_photo_v1/'+p.name]=p
    for name in ['run_slide5_context_10.sh','slide5_context_revision_10.py','verify_slide5_context_10.py','slide5_3d_revision_09.py','slide5_draft_revision_08.py','common.py']:
        p=REPO/'scripts/phd/slide_photo_v1'/name;members[str(p.relative_to(REPO))]=p
    p=REPO/'scripts/phd/main_regionfig_v1/common.py';members[str(p.relative_to(REPO))]=p
    p=CFG/'slide5_3d_revision_09.json';members['configs/phd/slide_photo_v1/'+p.name]=p
    members['payload/revision_10/geometry.npz']=cache/'geometry.npz'
    manifest={name:dict(sha256=sha(p),bytes=p.stat().st_size) for name,p in sorted(members.items())}
    archive=cache/'PHD-SLIDE-PHOTO-v1_part_R10_slide5_context.zip';pending=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(dict(task_id=c['task_id'],scientific_verdict=None,members=manifest),ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(pending) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(manifest)|{'MANIFEST.json'}
        for name,rec in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==rec['sha256']
    pending.replace(archive)
    dump(out/'handover.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),archive_name=archive.name,
          artifact_root_relative_path='phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1/revision_10/'+archive.name,
          sha256=sha(archive),bytes=archive.stat().st_size,members=len(manifest)+1,crc_verified=True,member_hashes_verified=True))
    print('PASS: source coordinates, selection, matched views, exact photo projection, review hashes, masked evidence, archive CRC and hashes')


if __name__=='__main__':main()
