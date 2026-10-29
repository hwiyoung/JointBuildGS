"""Requested photo / grey mesh / signed reference-point plates, CPU only."""
import argparse,gc
import open3d as o3d
from scipy.spatial import cKDTree
from PIL import Image,ImageDraw,ImageFont
from interview_common import *
from interview_meshio import crop

def geom_functions():
    ns=dict(np=np,o3d=o3d,S1=S1)
    p=R/'scripts/phd/main_floatdiag_v1/geometry.py'
    for name in ['reference','camera','render_context','render']:frozen_function(p,name,ns)
    return ns

def projection(points,cam):
    d=points-np.asarray(cam['eye']);depth=-(d@np.asarray(cam['direction']))
    focal=cam['width']/(2*np.tan(np.deg2rad(cam['fov_x_deg'])/2))
    x=(d@np.asarray(cam['right']))/np.maximum(depth,1e-8)*focal+(cam['width']-1)/2
    y=-(d@np.asarray(cam['up']))/np.maximum(depth,1e-8)*focal+(cam['height']-1)/2
    return x,y,depth

def points_image(points,delta,cam):
    W,H=cam['width'],cam['height'];image=np.full((H,W,3),248,np.uint8)
    colors=np.full((len(points),3),160,np.uint8);good=np.isfinite(delta);t=np.clip(np.abs(delta[good])/.5,0,1)
    end=np.where((delta[good]>=0)[:,None],np.array([210,55,55]),np.array([40,95,190]))
    colors[good]=np.rint(255*(1-t[:,None])+end*t[:,None]).astype(np.uint8)
    x,y,d=projection(points,cam);x=np.rint(x).astype(int);y=np.rint(y).astype(int)
    ok=(d>0)&(x>=0)&(x<W)&(y>=0)&(y<H);ids=np.flatnonzero(ok);ids=ids[np.argsort(d[ids])[::-1]]
    for dx,dy in [(0,0),(1,0),(0,1),(1,1)]:
        xx=np.minimum(x[ids]+dx,W-1);yy=np.minimum(y[ids]+dy,H-1);image[yy,xx]=colors[ids]
    return image

def photo(case,e):
    site=case['site'];prior=case['prior'];root=FD/'renders'/site/'nojudge_ALS_s0/iteration_30000'
    quality=root/'quality.json'
    if not quality.exists():return None,dict(status='UNAVAILABLE',reason='기존 학습 사진 카메라 기록 없음')
    meta=json.loads(quality.read_text());xyz=e['centre'][case['patch_indices']];weights=e['area'][case['patch_indices']]
    pairs=S0/'s61/box'/site/prior/'unit_view_pairs.npz'
    units=pairs.with_name('units.npz')
    if not pairs.exists():return None,dict(status='UNAVAILABLE',reason='기존 가시성 쌍이 없어 사진의 보이는 자리 확인 불가')
    with np.load(units) as u:assert np.array_equal(u['loc_center'],e['centre'])
    selected=np.zeros(len(e['area']),bool);selected[case['patch_indices']]=True
    with np.load(pairs) as f:
        use=selected[f['loc']]&(f['npix']>0);loc=f['loc'][use];view=f['view'][use]
        names=[Path(str(n)).stem for n in f['views']]
    coverage_by_view=np.bincount(view,weights=e['area'][loc],minlength=len(names))/weights.sum()
    visible_coverage=dict(zip(names,coverage_by_view))
    candidates=[]
    for cam in meta['train']:
        image_path=FD/'photos'/site/(cam['view']+'.png')
        if not image_path.exists():continue
        ext=np.array(cam['world_to_camera']);K=np.array(cam['intrinsic']);pc=xyz@ext[:3,:3].T+ext[:3,3];q=pc@K.T
        uv=q[:,:2]/q[:,2,None];xy=np.rint(np.nan_to_num(uv,nan=-1e6)).astype(int)
        on=(pc[:,2]>0)&np.isfinite(uv).all(1)&(xy[:,0]>=0)&(xy[:,0]<cam['width'])&(xy[:,1]>=0)&(xy[:,1]<cam['height'])
        coverage=float(visible_coverage.get(cam['view'],0));angle=float(np.degrees(np.arccos(np.clip(abs(ext[2,2]),0,1))))
        if coverage>0 and on.any():candidates.append((coverage,-angle,cam['view'],cam,uv[on],image_path))
    if not candidates:return None,dict(status='UNAVAILABLE',reason='기존 원 학습 사진 없음')
    candidates.sort(key=lambda x:(-x[0],-x[1],x[2]));coverage,_,view,cam,uv,p=candidates[0]
    if not len(uv):return None,dict(status='UNAVAILABLE',reason='사례가 기존 사진 화면 밖')
    lo=np.maximum(np.floor(uv.min(0)-35),[0,0]).astype(int);hi=np.minimum(np.ceil(uv.max(0)+35),[cam['width'],cam['height']]).astype(int)
    im=Image.open(p).convert('RGB').crop((*lo,*hi))
    return im,dict(status='PHOTO_CONTEXT',view=view,stored_visible_patch_area_fraction=coverage,crop_xyxy=[*lo,*hi],source=source(p),visibility_source=source(pairs),
        camera=cam,rule='Existing original training photo and saved positive-pixel visibility pairs; largest visible patch area, then lowest angle, then filename. No new visibility calculation.',human_structure_review='모름')

def measure_points(path,points,e):
    valid=eligible(e)&np.isfinite(e['p_gt']);idx=np.flatnonzero(valid)
    ref=e['centre'][idx]+e['p_gt'][idx,None]*e['normal'][idx]
    _,j=cKDTree(ref).query(points,workers=2);pi=idx[j];n=e['normal'][pi]
    dm=np.nan_to_num(e['p_mvs'][pi],nan=0.);dg=e['p_gt'][pi]
    start=np.maximum(6.,np.maximum(dm+.5,dg+.5));end=np.minimum(-6.,np.minimum(dm-.5,dg-.5))
    a=points+(start-dg)[:,None]*n;b=points+(end-dg)[:,None]*n
    low=np.minimum(a.min(0),b.min(0))-.01;high=np.maximum(a.max(0),b.max(0))+.01
    mesh=crop(path,low,high,intersect=True);delta=np.full(len(points),np.nan)
    if len(mesh.triangles):
        sc=o3d.t.geometry.RaycastingScene(nthreads=8);sc.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
        for st in range(0,len(points),50000):
            sl=slice(st,st+50000);hit=sc.cast_rays(o3d.core.Tensor(np.c_[a[sl],-n[sl]].astype(np.float32)))['t_hit'].numpy().astype(float)
            good=np.isfinite(hit)&(hit<=start[sl]-end[sl]);ix=np.arange(len(points))[sl][good]
            delta[ix]=start[sl][good]-hit[good]-dg[sl][good]
    return delta,pi

def main():
    ap=argparse.ArgumentParser();ap.add_argument('slug');arg=ap.parse_args();config()
    case=next(c for c in json.loads((IDOC/'cases.json').read_text())['cases'] if c['slug']==arg.slug)
    job='fig-'+arg.slug;dest=IDOC/'figures'/arg.slug;dest.mkdir(parents=True,exist_ok=True)
    e,v,base=evaluation(case['site'],case['prior']);ns=geom_functions();gt,gpath=ns['reference'](case['site'])
    low,high=np.array(case['crop_min']),np.array(case['crop_max']);points=gt[((gt>=low)&(gt<=high)).all(1)];del gt
    assert len(points);ids=np.asarray(case['patch_indices']);mask=np.zeros(len(e['area']),bool);mask[ids]=True
    photo_img,photo_info=photo(case,e);rows=[];frames={};sources=[]
    # Two original low-angle FLOATDIAG views; both are supplied, same camera per row/arm.
    cams=[case['cameras'][4],case['cameras'][5]]
    for result in case['results']:
        path,receipt=scored_mesh(case['site'],case['prior'],result)
        if not path.exists():raise FileNotFoundError(path)
        if receipt.get('expected_sha256'):assert sha(path)==receipt['expected_sha256']
        z,zp=patch_values(case['site'],case['prior'],result,e)
        rows.append(summary(e,z,mask,site=case['site'],prior=case['prior'],case=case['id'],slug=arg.slug,result=result,domain=case['domain']))
        mesh=crop(path,low,high);colors=np.full((len(mesh.triangles),3),174,np.uint8)
        grey=[ns['render'](mesh,colors,cam) if len(mesh.triangles) else np.full((600,720,3),248,np.uint8) for cam in cams]
        del mesh;gc.collect()
        delta,pi=measure_points(path,points,e);colored=[points_image(points,delta,cam) for cam in cams]
        frames[result]=(grey,colored);sources.append(dict(result=result,mesh=source(path),patch_values=source(zp)))
        data=IOUT/'figures'/arg.slug;data.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(data/(result+'_gt_distance.npz'),xyz=points,signed_normal_distance_m=delta,patch_index=pi)
    font=ImageFont.truetype('/fonts/NotoSansCJK-Regular.ttc',27);small=ImageFont.truetype('/fonts/NotoSansCJK-Regular.ttc',22)
    W,H=720,600;left=560;N=len(case['results']);footer=160
    for vi,cam in enumerate(cams):
        plate=Image.new('RGB',(left+N*W,2*H+footer+100),'white');d=ImageDraw.Draw(plate)
        d.text((22,12),case['id']+f' · 시점 {vi+1}',font=font,fill='#222222')
        if photo_img is not None:
            ph=photo_img.copy();ph.thumbnail((left-30,H*2-100));plate.paste(ph,((left-ph.width)//2,145))
            d.text((20,85),'학습 사진 · '+photo_info['view'],font=small,fill='#222222')
        else:d.text((20,145),'학습 사진: 확인 불가',font=font,fill='#555555')
        for j,result in enumerate(case['results']):
            x=left+j*W;d.text((x+16,65),method_name(result),font=font,fill='#222222')
            plate.paste(Image.fromarray(frames[result][0][vi]),(x,110));plate.paste(Image.fromarray(frames[result][1][vi]),(x,H+110))
            row=rows[j];fmt=lambda v:'확인 불가' if v is None else f'{v:.2f}%'
            d.text((x+14,2*H+120),f"τ 안 {fmt(row['within_tau_pct'])} · 뜬 면 {fmt(row['floating_pct'])}",font=small,fill='#222222')
        d.text((20,2*H+165),'위: 회색 음영 메시   아래: 참값 점 → 결과 첫 면의 법선 거리 · 파랑 −0.5 m / 흰색 0 / 빨강 +0.5 m · 면 없음 회색',font=small,fill='#333333')
        d.text((20,2*H+200),f"수치 범위: {case['domain']} · {rows[0]['area_m2']:.2f} m²"+(' · 실제 구조 여부(사람): 모름' if case['kind']=='inheritance' else ''),font=small,fill='#333333')
        tmp=dest/f'view_{vi+1}.tmp.png';plate.save(tmp,optimize=True);tmp.replace(dest/f'view_{vi+1}.png')
    write_table('figure_'+arg.slug,rows,[case['domain']])
    dump(dest/'provenance.json',dict(case=case,cameras=cams,sources=sources,photo=safe(photo_info),gt=source(gpath),
        gt_points=len(points),distance_definition=config()['figures']['distance_definition'],human_structure_review=case.get('human_structure_review'),scientific_verdict=None))
    record(job,status='PASS' if photo_img is not None else 'PARTIAL',figures=2,rows=rows,photo_status=photo_info['status'],human_structure_review=case.get('human_structure_review'))

if __name__=='__main__':main()
