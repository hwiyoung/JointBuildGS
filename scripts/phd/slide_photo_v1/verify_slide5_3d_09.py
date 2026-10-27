"""Replay displayed R9 coordinates and verify the bounded delivery archive."""
import hashlib
import json
import zipfile
import numpy as np
from PIL import Image

from common import CFG, DOC, PAY, REPO, load, dump, sha, now


def main():
    out=DOC/'revision_09'; cache=PAY/'revision_09'
    cfg=CFG/'slide5_3d_revision_09.json'
    c=load(cfg); lock=load(out/'input_lock.json'); meta=load(out/'geometry.json')
    assert sha(cfg)==lock['config_sha256']==meta['config_sha256']
    for name,rec in lock['sources'].items():
        assert sha(rec['path'])==rec['sha256'], name
    assert sha(cache/'geometry.npz')==meta['geometry_sha256']
    data=np.load(cache/'geometry.npz'); results={}
    roof=meta['roof']; basis=np.asarray(roof['basis']); origin=np.asarray(roof['origin'])
    lo=np.asarray(roof['crop_min_xyz']); hi=np.asarray(roof['crop_max_xyz'])
    for key,source in [('mvs','roof_mvs'),('gt','roof_reference')]:
        raw=np.load(c['sources'][source],mmap_mode='r')
        ids=data['roof_'+key+'_source_ids']; replay=data['roof_'+key]@basis+origin
        err=float(np.max(np.abs(replay-np.asarray(raw[ids],dtype=np.float64))))
        assert err<1e-10
        chunks=[]
        for start in range(0,len(raw),250000):
            block=raw[start:start+250000]
            chunks.append(start+np.flatnonzero(np.all((block>=lo)&(block<=hi),axis=1)))
        crop_ids=np.concatenate(chunks)
        cells=np.floor(np.asarray(raw[crop_ids],dtype=np.float64)/c['roof_display_voxel_m']).astype(np.int64)
        _,first=np.unique(cells,axis=0,return_index=True)
        assert np.array_equal(ids,crop_ids[np.sort(first)])
        assert len(crop_ids)==roof['point_counts'][key]['in_fixed_volume']
        results['roof_'+key]=dict(raw_coordinate_max_error_m=err,crop_points=len(crop_ids),display_points=len(ids),first_original_point_per_voxel=True)
    mesh=np.load(c['sources']['roof_prior_mesh'])
    parents=(mesh['V']+np.asarray(roof['registration_shift']))[mesh['F'][data['roof_source_faces']]]
    triangles=data['roof_tri']@basis+origin
    normal=np.cross(parents[:,1]-parents[:,0],parents[:,2]-parents[:,0])
    length=np.linalg.norm(normal,axis=1); valid=length>1e-12
    distances=np.abs(np.sum((triangles[valid]-parents[valid,:1])*normal[valid,None],axis=2))/length[valid,None]
    plane_error=float(distances.max()); assert plane_error<1e-8
    assert np.all(triangles>=lo-1e-10) and np.all(triangles<=hi+1e-10)
    assert np.all(triangles>=parents.min(1)[:,None]-1e-10) and np.all(triangles<=parents.max(1)[:,None]+1e-10)
    results['roof_mesh']=dict(original_plane_max_error_m=plane_error,clipped_triangles=len(triangles),degenerate_parent_count=int((~valid).sum()))
    wall=meta['wall']; basis=np.asarray(wall['basis']); origin=np.asarray(wall['origin'])
    raw=np.load(c['sources']['wall_cloud']); section=load(c['sources']['wall_section'])
    for key in ['prior','gt','mvs']:
        ids=data['wall_'+key+'_source_ids']
        assert np.array_equal(ids,section['series'][key]['point_indices'])
        replay=data['wall_'+key]@basis+origin
        err=float(np.max(np.abs(replay-raw[key][ids]))); assert err<1e-10
        results['wall_'+key]=dict(raw_coordinate_max_error_m=err,all_frozen_points_retained=True,display_points=len(ids))
    render=load(out/'render.json')
    for key in ['roof','wall']:
        base=render['views_by_step']['prior'][key]
        for mode in ['mvs','all']:
            view=render['views_by_step'][mode][key]
            for field in ['basis','centre','lo','hi','display_rotation_from_frozen_frame']:
                assert base[field]==view[field]
        for field in ['basis','display_rotation_from_frozen_frame']:
            R=np.asarray(base[field]); assert np.allclose(R@R.T,np.eye(3)) and np.isclose(np.linalg.det(R),1)
    gif=Image.open(out/'figures/slide5_3d_steps.gif')
    assert gif.n_frames==3 and gif.size==(1920,1080) and gif.info['loop']==0
    durations=[]; quantization_error=[]
    for i,mode in enumerate(['prior','mvs','all']):
        gif.seek(i); durations.append(gif.info['duration'])
        png=Image.open(out/f'previews/slide5_3d_{mode}.png').convert('RGB')
        assert png.size==gif.size
        mean_abs=float(np.abs(np.asarray(gif.convert('RGB'),dtype=np.float32)-np.asarray(png,dtype=np.float32)).mean())
        assert mean_abs<3, (mode,mean_abs)
        quantization_error.append(mean_abs)
    assert durations==[1800,1800,3200]
    assert Image.open(out/'figures/slide5_3d_overlay.png').size==(3840,2160)
    verification=load(out/'verification.json')
    assert sha(REPO/'scripts/phd/slide_photo_v1/slide5_3d_revision_09.py')==verification['script_sha256']
    for name,rec in verification['files'].items():
        assert sha(out/name)==rec['sha256']
    review=load(out/'qa/blind_reviews.json')['reviews'][-1]
    assert review['stage']=='final_display' and review['intended_message_read']
    assert sha(out/review['image_path'])==review['image_sha256']
    dump(out/'source_replay.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),status='PASS',
        source_replays=results,same_camera_and_metric_scale_across_steps=True,
        animation=dict(frames=3,duration_ms=durations,mean_absolute_palette_error_rgb_255=quantization_error),
        audit_script_sha256=sha(REPO/'scripts/phd/slide_photo_v1/verify_slide5_3d_09.py'),
        all_source_hashes_unchanged=True,output_hashes_verified=True,final_blind_review_hash_matches=True))
    code_paths=[
        'configs/phd/slide_photo_v1/slide5_3d_revision_09.json',
        'scripts/phd/slide_photo_v1/run_slide5_3d_09.sh',
        'scripts/phd/slide_photo_v1/slide5_3d_revision_09.py',
        'scripts/phd/slide_photo_v1/verify_slide5_3d_09.py',
        'scripts/phd/slide_photo_v1/slide5_draft_revision_08.py',
        'scripts/phd/slide_photo_v1/common.py',
        'scripts/phd/main_regionfig_v1/common.py']
    members={str(p.relative_to(REPO)):p for p in [REPO/name for name in code_paths]}
    for p in sorted(out.rglob('*')):
        if p.is_file() and p.name!='handover.json':
            members['docs/experiments/phd/slide_photo_v1/revision_09/'+str(p.relative_to(out))]=p
    members['payload/revision_09/geometry.npz']=cache/'geometry.npz'
    manifest={name:dict(sha256=sha(p),bytes=p.stat().st_size) for name,p in sorted(members.items())}
    archive=cache/'PHD-SLIDE-PHOTO-v1_part_R9_slide5_3d.zip'
    pending=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(dict(task_id=c['task_id'],scientific_verdict=None,members=manifest),ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(pending) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(manifest)|{'MANIFEST.json'}
        for name,rec in manifest.items():
            content=z.read(name)
            assert len(content)==rec['bytes'] and hashlib.sha256(content).hexdigest()==rec['sha256']
    pending.replace(archive)
    dump(out/'handover.json',dict(task_id=c['task_id'],scientific_verdict=None,verified_at=now(),status='PASS',
        artifact_root_relative_path='phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1/revision_09/'+archive.name,
        archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,member_count=len(manifest)+1,
        crc_verified=True,all_member_hashes_verified=True,contents=manifest))
    print('PASS: raw coordinate replay, frozen selection, original mesh planes, common cameras, PNG/GIF, blind-review hash and delivery archive')


if __name__=='__main__':
    main()
