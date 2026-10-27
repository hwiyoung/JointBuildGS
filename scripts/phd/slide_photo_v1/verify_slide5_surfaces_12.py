"""R12: replay input geometry, calibrated photo support, annotations and delivery."""
import ctypes
import hashlib
import json
import platform
import zipfile
from pathlib import Path

import numpy as np
import PIL
from PIL import Image
from matplotlib.path import Path as MPath

from common import CFG,DOC,PAY,REPO,RAW,geometry,load,dump,sha,now
import slide5_surfaces_revision_12 as R

OUT=R.OUT;CACHE=R.CACHE


def reviews():
    answers=[
        ('round1','roof','/root/r12_roof_blind','현재 사진에서 지정한 지붕의 같은 구역을 항공 LiDAR 사전 정보와 영상 기반 MVS 표면에서 표시하고, 같은 시점·축척·표면 표현으로 형상을 비교한 그림입니다.','PARTIAL: recognized shape comparison, not height difference'),
        ('round1','wall','/root/r12_wall_blind','같은 건물 벽면에서 LoD2 사전 정보는 현재 드론 LiDAR 참조에 대체로 가깝지만, MVS 영상 깊이는 더 큰 거리 차이를 보인다.','PASS: recognized larger MVS distance'),
        ('round2','roof','/root/r12_roof_final_blind','같은 지붕 구역에서 사전 항공 LiDAR의 지붕은 현재 드론 LiDAR 참조 높이보다 높게 나타나고, 영상으로 복원한 MVS 지붕은 참조 높이에 가깝게 나타납니다.','PASS: recognized prior height excess and MVS/reference proximity'),
        ('round2','wall','/root/r12_wall_final_blind','표시된 벽면 구간에서 사전 LoD2는 현재 드론 LiDAR 참조와 대체로 가깝고, 영상 기반 MVS 깊이는 더 큰 거리 차이를 보인다.','PASS: recognized larger MVS distance')]
    rows=[]
    for round_name,key,agent,answer,assessment in answers:
        name='slide5_roof_surfaces' if key=='roof' else 'slide5_wall_distances'
        p=OUT/'qa'/round_name/f'{name}_blind.png'
        rows.append(dict(round=round_name,case=key,agent=agent,image=str(p.relative_to(OUT)),image_sha256=sha(p),
            prompt='이 그림이 보여 주는 것을 한 문장으로',answer=answer,assessment=assessment,
            context='New agent, no conversation fork, one image only. Main claim title and summary metrics masked; source labels and visual guides retained.'))
    dump(OUT/'qa/blind_reviews.json',dict(scientific_verdict=None,reviews=rows,limitation='A reader check supports readability only; it does not establish temporal cause, material cause, or independent geometric truth.'))
    return rows


def main():
    c,s=R.lock();meta=load(OUT/'geometry.json');roof=load(OUT/'roof.json');wall=load(OUT/'wall.json');r=load(OUT/'render.json')
    checks={};details={}
    assert r['script_sha256']==sha(Path(R.__file__)) and r['raster_sha256']==sha(Path(R.__file__).with_name('surface_raster_12.cpp'))
    assert r['config_sha256']==sha(R.CONFIG)==meta['config_sha256']
    checks['frozen_sources_config_display_and_render_script']=True
    # Replay every source face in chunks; exact retained membership and coordinates.
    path=MPath(np.array(meta['crop_polygon_xy']));poly=np.array(meta['crop_polygon_xy']);lo=poly.min(0);hi=poly.max(0)
    for key in ['prior','mvs']:
        a=R.tris(key,meta);ix=np.memmap(CACHE/f'{key}_faces.bin',mode='r',dtype='<i8');offset=0
        assert sha(CACHE/f'{key}_triangles.bin')==meta[key]['triangles_sha256'];assert sha(CACHE/f'{key}_faces.bin')==meta[key]['face_ids_sha256']
        for tri,ids in R.mesh_chunks(s,key):
            quick=np.all((tri[:,:,:2]>=lo)&(tri[:,:,:2]<=hi),axis=(1,2));tri=tri[quick];ids=ids[quick]
            keep=path.contains_points(tri[:,:,:2].reshape(-1,2)).reshape(-1,3).all(1);tri=tri[keep];ids=ids[keep]
            assert np.array_equal(a[offset:offset+len(tri)],tri)
            assert np.array_equal(ix[offset:offset+len(ids)],ids);offset+=len(ids)
        assert offset==len(a)==len(ix);details[key+'_exact_replayed_triangles']=offset
        print('REPLAY',key,offset,flush=True)
    checks['all_crop_members_and_original_source_coordinates_replayed']=True
    v=roof['panels']['prior']['camera'];assert v==roof['panels']['mvs']['camera'];rot=np.array(v['rotation'])
    assert np.allclose(rot@rot.T,np.eye(3)) and np.isclose(np.linalg.det(rot),1)
    assert np.isclose(v['scale_px_per_m'],min((v['size'][0]-100)/np.ptp(np.array(v['bounds'])[:,0]),(v['size'][1]-120)/np.ptp(np.array(v['bounds'])[:,1])))
    for key in ['prior','mvs']:
        pix=np.load(CACHE/f'roof_{key}_pixels.npz');owner=pix['owner'];depth=pix['depth'];ids=np.flatnonzero(owner.ravel()>=0)
        chosen=ids[np.linspace(0,len(ids)-1,128,dtype=int)];y,x=np.unravel_index(chosen,owner.shape);tri=R.tris(key,meta)[owner[y,x]];q=R.project(tri,v)
        aa,bb,cc=q[:,0],q[:,1],q[:,2];den=(bb[:,1]-cc[:,1])*(aa[:,0]-cc[:,0])+(cc[:,0]-bb[:,0])*(aa[:,1]-cc[:,1])
        wa=((bb[:,1]-cc[:,1])*(x+.5-cc[:,0])+(cc[:,0]-bb[:,0])*(y+.5-cc[:,1]))/den
        wb=((cc[:,1]-aa[:,1])*(x+.5-cc[:,0])+(aa[:,0]-cc[:,0])*(y+.5-cc[:,1]))/den;wc=1-wa-wb
        assert min(wa.min(),wb.min(),wc.min())>-1e-8
        err=np.max(abs(wa*aa[:,2]+wb*bb[:,2]+wc*cc[:,2]-depth[y,x]));assert err<1e-8;details[key+'_raster_depth_replay_error_m']=float(err)
    checks['same_rigid_camera_equal_metric_scale_and_raster_depth']=True
    lib=ctypes.CDLL(str(CACHE/'surface_raster_12.so'));lib.raster.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int64]
    q=np.array([[[1,1,1],[8,1,1],[1,8,1]],[[1,1,2],[8,1,2],[1,8,2]]],dtype='float64');colour=np.array([[10,20,30],[60,70,80]],dtype='float32')
    d=np.full((10,10),-np.inf);rgb=np.zeros((10,10,3),np.float32);owner=np.full((10,10),-1,np.int64)
    lib.raster(q.ctypes.data,colour.ctypes.data,2,10,10,d.ctypes.data,rgb.ctypes.data,owner.ctypes.data,0)
    assert d[2,2]==2 and owner[2,2]==1 and np.array_equal(rgb[2,2],[60,70,80]) and owner[9,9]==-1
    build=load(CACHE/'raster_build.json');assert build['binary_sha256']==sha(CACHE/'surface_raster_12.so') and build['source_sha256']==r['raster_sha256']
    checks['near_surface_occludes_far_surface_and_empty_space_stays_empty']=True
    ex=load(s['roof_example'])['examples'][0];bins=np.array(ex['bin_centres_m']);H=np.array(ex['heights_model_m']);k=int(np.argmin(abs(bins-ex['length_m']/2)))
    assert k==roof['midpoint_bin'];u=np.array(ex['end_xy'])-ex['start_xy'];u/=np.linalg.norm(u);xy=ex['start_xy']+bins[k]*u
    for key,j in [('prior',0),('mvs',1)]:assert np.array_equal(roof['anchors'][key],[*xy,H[k,j]])
    assert np.array_equal(roof['reference_anchor'],[*xy,H[k,2]])
    assert np.isclose(roof['reference_guide_canvas_y_px'],R.project(np.array([roof['reference_anchor']]),v)[0,1]+450)
    assert roof['reference_value_cm']==ex['values']['prior_minus_gt_cm']
    details['roof_local_arrow_m']=roof['local_prior_minus_reference_m'];details['roof_separate_region_median_cm']=roof['reference_value_cm']
    checks['height_guide_fixed_midpoint_not_confused_with_region_median']=True
    row=load(s['wall_candidates'])['selected'];geo=geometry(row['tiles'][0],row['prior']);m=np.load(s['wall_mvs']);g=np.load(s['wall_gt']);z=np.load(CACHE/'wall_support.npz')
    ri=z['mvs_rows'];ix=z['patch_indices'];vi=wall['view_index'];assert m['view_names'][vi]==wall['photo']['view']
    expected=np.flatnonzero(np.isin(geo['patch_id'][m['patch_index']],row['patch_ids'])&np.isfinite(m['per_view_signed'][:,vi]))
    assert np.array_equal(ri,expected) and np.array_equal(ix,m['patch_index'][ri]) and np.all(g['eligible'][ix])
    assert np.array_equal(z['prior_cm'],g['prior_abs'][ix]*100) and np.array_equal(z['mvs_cm'],m['mvs_abs'][ri]*100)
    A=geo['tangent1'][ix];B=geo['tangent2'][ix];X=g['representative'][ix]
    squares=np.stack([X+a*A+b*B for a,b in [(-.125,-.125),(.125,-.125),(.125,.125),(-.125,.125)]],axis=1)
    assert np.array_equal(squares,z['squares_xyz']);uv,_=R.photo_project(squares.reshape(-1,3),wall['photo']);uv=uv.reshape(-1,4,2)
    q=(uv-np.array(wall['crop'])[:2])*wall['photo_fit']['scale_xy']+wall['photo_fit']['offset'];assert np.allclose(q,z['squares_px'],atol=1e-8)
    assert q[:,:,0].min()>=0 and q[:,:,0].max()<1740 and q[:,:,1].min()>=0 and q[:,:,1].max()<1200
    assert sha(CACHE/'wall_support.npz')==wall['support_sha256']
    for key in ['prior','mvs']:assert np.median(z[key+'_cm'])==wall['median_cm'][key]
    details['wall_shown_patches']=len(ix);details['wall_median_cm']=wall['median_cm'];details['wall_projection_max_error_px']=float(np.max(abs(q-z['squares_px'])))
    checks['identical_wall_patches_original_values_visibility_and_calibrated_support']=True
    for src,fit in [(roof['photo_source'],roof['photo_fit']),(wall['photo'],wall['photo_fit'])]:
        with zipfile.ZipFile(RAW) as arch:assert hashlib.sha256(arch.read(src['original_member'])).hexdigest()==src['original_sha256']
        sx,sy=fit['scale_xy'];assert abs(sx/sy-1)<.002
    checks['original_photo_bytes_and_aspect_preserved']=True
    for name in ['slide5_roof_surfaces','slide5_wall_distances']:
        assert Image.open(OUT/'figures'/f'{name}.png').size==(3840,2160)
        assert Image.open(OUT/'previews'/f'{name}.png').size==(1920,1080)
        assert np.array_equal(np.array(Image.open(OUT/'previews'/f'{name}.png')),np.array(Image.open(OUT/'qa/round2'/f'{name}_full.png')))
    checks['delivered_previews_match_final_reviewed_figures']=True
    rows=reviews();checks['original_and_revised_blind_answers_retained']=len(rows)==4
    files={str(p.relative_to(OUT)):dict(sha256=sha(p),bytes=p.stat().st_size) for folder in ['figures','previews','qa'] for p in sorted((OUT/folder).rglob('*.png'))}
    dump(OUT/'verification.json',dict(task_id=c['task_id'],scientific_verdict=None,status='PASS',verified_at=now(),checks=checks,details=details,files=files,
        versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=PIL.__version__,compiler=build['compiler']),
        scope='Technical provenance, geometry, photo support and delivery. No scientific verdict or material-cause conclusion.'))
    package(c)
    print('PASS: source geometry, photos, distance cells, height guides, reader records and archive',flush=True)


def package(c):
    members={'docs/experiments/phd/slide_photo_v1/revision_12/'+str(p.relative_to(OUT)):p for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='handover.json'}
    for p in CFG.glob('slide5_surfaces_revision_12*.json'):members['configs/phd/slide_photo_v1/'+p.name]=p
    for name in ['slide5_surfaces_revision_12.py','verify_slide5_surfaces_12.py','run_slide5_surfaces_12.sh','surface_raster_12.cpp','slide5_draft_revision_08.py','common.py']:
        p=REPO/'scripts/phd/slide_photo_v1'/name;members[str(p.relative_to(REPO))]=p
    for p in [REPO/'scripts/phd/main_regionfig_v1/common.py',REPO/'scripts/phd/main_axes71_v2/mvs_surface.py',CFG/'slide5_3d_revision_09.json',DOC/'revision_09/geometry.json']:
        members[str(p.relative_to(REPO)) if str(p).startswith('/repo/') else 'referenced_metadata/'+p.name]=p
    members['payload/wall_support.npz']=CACHE/'wall_support.npz';members['payload/raster_build.json']=CACHE/'raster_build.json'
    pins={name:dict(sha256=sha(p),bytes=p.stat().st_size) for name,p in sorted(members.items())}
    path=CACHE/'PHD-SLIDE-PHOTO-v1_R12_surface_comparison.zip';tmp=path.with_suffix('.zip.tmp')
    with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):z.write(p,name)
        z.writestr('MANIFEST.json',json.dumps(dict(task_id=c['task_id'],scientific_verdict=None,members=pins,
            external_inputs='Raw source datasets and large derived triangle caches stay in the existing artifact root. Exact paths and hashes are in input_lock.json and geometry.json.'),ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(tmp) as z:
        assert z.testzip() is None and set(z.namelist())==set(pins)|{'MANIFEST.json'}
        for name,pin in pins.items():assert hashlib.sha256(z.read(name)).hexdigest()==pin['sha256']
    tmp.replace(path)
    dump(OUT/'handover.json',dict(task_id=c['task_id'],scientific_verdict=None,archive_name=path.name,
        artifact_root_relative_path='phase-payloads/phd/slide_photo_v1/PHD-SLIDE-PHOTO-v1/revision_12/'+path.name,
        sha256=sha(path),bytes=path.stat().st_size,members=len(pins)+1,crc_verified=True,member_hashes_verified=True,verified_at=now()))


if __name__=='__main__':main()
