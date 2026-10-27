"""Replay source geometry, projection, anchors, frozen inputs and R11 delivery."""
import hashlib
import json
import platform
import shutil
import zipfile

import numpy as np
import PIL
from PIL import Image
import scipy
import matplotlib

from common import CFG,DOC,PAY,REPO,RAW,G,load,dump,sha,now


def main():
    out=DOC/'revision_11';cache=PAY/'revision_11';cfg=CFG/'slide5_overlay_revision_11.json'
    c=load(cfg);lock=load(out/'input_lock.json');r=load(out/'render.json');checks={};details={}
    assert sha(cfg)==lock['config_sha256']==r['config_sha256']
    assert sha(REPO/'scripts/phd/slide_photo_v1/slide5_overlay_revision_11.py')==r['script_sha256']
    for v in lock['sources'].values():assert sha(v['path'])==v['sha256']
    dl=load(out/'display_lock.json');assert sha(dl['path'])==dl['sha256']
    s=load(c['source_config'])['sources'];data=np.load(PAY/'revision_10/geometry.npz');old=np.load(PAY/'revision_09/geometry.npz')
    meta=load(DOC/'revision_10/geometry.json');oldmeta=load(DOC/'revision_09/geometry.json')['roof']
    assert load(DOC/'revision_10/verification.json')['status']=='PASS'
    checks['source_locks_and_r10_coordinate_audit_unchanged']=True
    tri=old['roof_tri']@np.asarray(meta['roof_basis'])+meta['roof_origin']
    raw=np.load(s['roof_prior_mesh']);parent=(raw['V']+meta['roof_registration_shift'])[raw['F'][old['roof_source_faces']]]
    n=np.cross(parent[:,1]-parent[:,0],parent[:,2]-parent[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    residual=np.abs(np.sum((tri-parent[:,:1])*n[:,None],axis=2));assert residual.max()<1e-7
    assert np.all(tri>=np.asarray(oldmeta['crop_min_xyz'])-1e-8) and np.all(tri<=np.asarray(oldmeta['crop_max_xyz'])+1e-8)
    details['prior_original_triangle_plane_max_error_m']=float(residual.max())
    mvs=np.load(s['roof_mvs'],mmap_mode='r');ids=data['roof_mvs_ids'];assert np.array_equal(data['roof_mvs'],mvs[ids])
    core=np.all((data['roof_mvs']>=meta['highlight_min_xyz'])&(data['roof_mvs']<=meta['highlight_max_xyz']),axis=1)
    assert np.array_equal(core,data['roof_mvs_core']);assert r['roof']['mvs_points']==int(core.sum())
    assert r['roof']['triangle_count']==len(tri)
    checks['prior_original_planes_and_mvs_original_coordinates']=True
    view=r['roof']['view'];R=np.asarray(view['rotation']);origin=np.asarray(view['origin'])
    assert np.allclose(R@R.T,np.eye(3)) and np.isclose(np.linalg.det(R),1)
    q=(np.concatenate([tri.reshape(-1,3),data['roof_mvs'][core]])-origin)@R.T
    lo=q[:,:2].min(0);hi=q[:,:2].max(0);w,h=view['canvas']
    assert np.allclose([lo,hi],view['bounds'])
    assert np.isclose(view['scale_px_per_m'],min((w-120)/(hi[0]-lo[0]),(h-160)/(hi[1]-lo[1])))
    checks['camera_is_rigid_and_scale_is_equal_on_all_axes']=True
    ex=load(s['roof_example'])['examples'][0];bins=np.asarray(ex['bin_centres_m']);H=np.asarray(ex['heights_model_m'])
    k=int(np.argmin(abs(bins-ex['length_m']/2)));u=np.asarray(ex['end_xy'])-ex['start_xy'];u/=np.linalg.norm(u)
    xy=np.asarray(ex['start_xy'])+bins[k]*u;expected=np.array([[*xy,H[k,0]],[*xy,H[k,1]]])
    a=r['roof']['annotation'];assert a['bin_index']==k and np.array_equal(expected,a['endpoints_xyz'])
    assert a['prior_minus_mvs_m']==H[k,0]-H[k,1]
    checks['roof_arrow_uses_fixed_midpoint_source_values']=True
    cloud=np.load(s['wall_cloud']);section=load(s['wall_section'])
    for key in ['prior','mvs','gt']:
        idx=np.asarray(section['series'][key]['point_indices']);err=np.max(np.abs(data['wall_'+key]-cloud[key][idx]));assert err<1e-10
        assert r['wall']['points'][key]==len(idx)
        details['wall_'+key+'_max_coordinate_error_m']=float(err)
    wall=r['wall'];u=np.asarray(wall['horizontal_axis']);n=np.asarray(wall['normal_axis'])
    assert np.isclose(np.linalg.norm(u),1) and np.isclose(np.linalg.norm(n),1) and abs(u@n)<1e-8 and abs(u[2])<1e-8
    checks['wall_all_fixed_points_retained_with_equal_top_view_axes']=True
    photos=r['composition']['overlay']['photos']
    for key in ['roof','wall']:
        pm=load(s[key+'_photo'])['photo'];src=pm['source']['photo'];p=photos[key]
        with zipfile.ZipFile(RAW) as z:jpg=z.read(src['original_member'])
        assert hashlib.sha256(jpg).hexdigest()==src['original_sha256']==p['source_sha256']
        X=np.asarray(pm['section_line_xyz' if key=='roof' else 'section_centre_line_xyz']);assert np.array_equal(X,p['section_line_xyz'])
        pose=dict(src['pose'],R=np.asarray(src['pose']['R']),t=np.asarray(src['pose']['t']));uv,_=G.project(X,pose,src['camera'])
        if p['rotation']==90:uv=np.c_[uv[:,1],src['camera']['w']-uv[:,0]]
        crop=np.asarray(p['crop']);scale=np.asarray(p['photo_content_size'])/(crop[2:]-crop[:2])
        expected=(uv-crop[:2])*scale+p['content_offset'];err=float(np.max(np.abs(expected-p['section_line_px'])));assert err<1e-8
        assert abs(scale[0]/scale[1]-1)<.003;details[key+'_photo_projection_max_error_px']=err
    checks['original_photo_bytes_and_calibrated_ab_projection']=True
    for mode in ['prior','mvs','overlay']:
        assert Image.open(out/f'figures/slide5_{mode}.png').size==(3840,2160)
        assert Image.open(out/f'previews/slide5_{mode}.png').size==(1920,1080)
        assert r['composition'][mode]['photos']==photos
    full=Image.open(out/'previews/slide5_overlay.png');blind=Image.open(out/'qa/without_explanations.png')
    for box in [(60,213,580,537),(610,183,1860,592),(60,730,580,1010),(650,710,1800,985)]:
        assert np.array_equal(np.asarray(full.crop(box)),np.asarray(blind.crop(box))),box
    checks['export_sizes_and_explanation_mask_preserves_figure_panels']=True
    reviews=load(out/'qa/blind_reviews.json')
    for review in reviews['reviews']:assert sha(out/review['image_path'])==review['image_sha256']
    checks['blind_review_image_hash_matches']=True
    for name in ['roof_overlay.png','wall_overlay.png']:
        shutil.copyfile(cache/name,out/'figures'/name)
        assert sha(cache/name)==sha(out/'figures'/name)
    checks['standalone_panels_match_rendered_components']=True
    files={str(p.relative_to(out)):dict(sha256=sha(p),bytes=p.stat().st_size) for folder in ['figures','previews','qa'] for p in sorted((out/folder).glob('*.png'))}
    dump(out/'verification.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),status='PASS',checks=checks,details=details,files=files,
        audit_script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/verify_slide5_overlay_11.py'),
        versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,scipy=scipy.__version__,matplotlib=matplotlib.__version__),
        scope='Technical provenance and geometry only; reader judgement is separate. Two illustrative cases, no performance or causal-material verdict.'))
    members={}
    for revision in ['revision_10','revision_11']:
        for p in sorted((DOC/revision).rglob('*')):
            if p.is_file() and p.name!='handover.json':members['docs/experiments/phd/slide_photo_v1/'+revision+'/'+str(p.relative_to(DOC/revision))]=p
    for pattern in ['slide5_context_revision_10*.json','slide5_overlay_revision_11*.json','slide5_3d_revision_09.json']:
        for p in CFG.glob(pattern):members['configs/phd/slide_photo_v1/'+p.name]=p
    for name in ['slide5_overlay_revision_11.py','run_slide5_overlay_11.sh','verify_slide5_overlay_11.py','slide5_context_revision_10.py','run_slide5_context_10.sh','verify_slide5_context_10.py','slide5_3d_revision_09.py','slide5_draft_revision_08.py','common.py']:
        p=REPO/'scripts/phd/slide_photo_v1'/name;members[str(p.relative_to(REPO))]=p
    p=REPO/'scripts/phd/main_regionfig_v1/common.py';members[str(p.relative_to(REPO))]=p
    for rev in ['revision_09','revision_10']:
        p=PAY/rev/'geometry.npz';members[f'payload/{rev}/geometry.npz']=p
    manifest={name:dict(sha256=sha(p),bytes=p.stat().st_size) for name,p in sorted(members.items())}
    archive=cache/'PHD-SLIDE-PHOTO-v1_R11_slide5_overlay.zip';tmp=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(dict(task_id=c['task_id'],scientific_verdict=None,members=manifest),ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None and set(z.namelist())==set(manifest)|{'MANIFEST.json'}
        for name,v in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==v['sha256']
    tmp.replace(archive)
    dump(out/'handover.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),archive_name=archive.name,
        artifact_root_relative_path='phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1/revision_11/'+archive.name,
        sha256=sha(archive),bytes=archive.stat().st_size,members=len(manifest)+1,crc_verified=True,member_hashes_verified=True))
    print('PASS: frozen inputs, source geometry, projections, midpoint, panels, reader hash, archive CRC and member hashes')


if __name__=='__main__':main()
