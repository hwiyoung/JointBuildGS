"""CPU-only raw-depth photo reprojection walkthrough; never selects a winner."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import shutil
import sys
import time

import numpy as np
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def valid(a):
    return np.isfinite(a) & (a > 0)


def uv_grid(center, size):
    radius = size // 2
    yy, xx = np.mgrid[center[1]-radius:center[1]+radius+1,
                      center[0]-radius:center[0]+radius+1]
    return np.stack((xx, yy), axis=-1).astype(float)


def bilinear(array, uv, positive=False):
    h, w = array.shape[:2]
    finite = np.isfinite(uv).all(axis=-1)
    q = np.nan_to_num(uv, nan=-10, posinf=-10, neginf=-10)
    x, y = q[..., 0], q[..., 1]
    inside = finite & (x >= 0) & (y >= 0) & (x <= w-1) & (y <= h-1)
    x0 = np.floor(np.clip(x, 0, w-1)).astype(int)
    y0 = np.floor(np.clip(y, 0, h-1)).astype(int)
    x1, y1 = np.minimum(x0+1, w-1), np.minimum(y0+1, h-1)
    a, b, c, d = array[y0, x0], array[y0, x1], array[y1, x0], array[y1, x1]
    good = np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & np.isfinite(d)
    if positive:
        good &= (a > 0) & (b > 0) & (c > 0) & (d > 0)
    if array.ndim == 3:
        good = good.all(axis=-1)
    mask = inside & good
    dx, dy = x-x0, y-y0
    if array.ndim == 3:
        dx, dy = dx[..., None], dy[..., None]
    result = (1-dx)*(1-dy)*a + dx*(1-dy)*b + (1-dx)*dy*c + dx*dy*d
    result = np.where(mask[..., None] if array.ndim == 3 else mask, result, np.nan)
    return result, mask


def project(uv, depth, ref, neighbor):
    pix = np.concatenate((uv, np.ones(uv.shape[:-1]+(1,))), axis=-1)
    ray = pix @ np.linalg.inv(np.asarray(ref['K'])).T
    cam = ray * depth[..., None]
    world = (cam - np.asarray(ref['t'])) @ np.asarray(ref['R'])
    other = world @ np.asarray(neighbor['R']).T + np.asarray(neighbor['t'])
    homogeneous = other @ np.asarray(neighbor['K']).T
    with np.errstate(invalid='ignore', divide='ignore'):
        target = homogeneous[..., :2]/homogeneous[..., 2:3]
    return target, other[..., 2], world


def gray(rgb):
    return np.asarray(rgb, float) @ np.array([.299, .587, .114])


def score(reference, warped, mask, eps):
    a, b = gray(reference)[mask], gray(warped)[mask]
    result = dict(common_count=int(mask.sum()), zncc=None, cost=None,
                  mean_reference=None, mean_warp=None, std_reference=None, std_warp=None)
    residual = np.full(mask.shape, np.nan)
    if len(a) < 2:
        result['status'] = 'UNDEFINED_INSUFFICIENT_COMMON_PIXELS'
        return result, residual
    ma, mb, sa, sb = float(a.mean()), float(b.mean()), float(a.std()), float(b.std())
    result.update(mean_reference=ma, mean_warp=mb, std_reference=sa, std_warp=sb)
    if sa <= eps or sb <= eps:
        result['status'] = 'UNDEFINED_FLAT_PATCH'
        return result, residual
    za, zb = (a-ma)/sa, (b-mb)/sb
    zncc = float(np.mean(za*zb))
    require(-1-1e-12 <= zncc <= 1+1e-12, 'ZNCC outside mathematical range')
    result.update(zncc=float(np.clip(zncc, -1, 1)), cost=float((1-np.clip(zncc, -1, 1))/2), status='DEFINED_DESCRIPTIVE_ONLY')
    residual[mask] = za-zb
    return result, residual


def independent_score(reference, warped, mask):
    # Separate scalar centered cross-product implementation, not the normalized helper.
    aa, bb = [], []
    for y, x in zip(*np.where(mask)):
        aa.append(sum(float(reference[y,x,k])*v for k,v in enumerate((.299,.587,.114))))
        bb.append(sum(float(warped[y,x,k])*v for k,v in enumerate((.299,.587,.114))))
    ma, mb = sum(aa)/len(aa), sum(bb)/len(bb)
    cross = sum((a-ma)*(b-mb) for a,b in zip(aa,bb))
    norm = math.sqrt(sum((a-ma)**2 for a in aa)*sum((b-mb)**2 for b in bb))
    return cross/norm


def self_checks():
    cam = dict(K=[[10.,0,5],[0,10,5],[0,0,1]], R=np.eye(3).tolist(), t=[0.,0,0])
    neighbor = dict(cam, t=[-1.,0,0])
    uv = uv_grid((5,5), 3); dep = np.full((3,3), 10.)
    projected, z, _ = project(uv, dep, cam, neighbor)
    require(np.allclose(projected, uv-np.array([1,0]), atol=1e-13), 'Translation projection fixture')
    identity, _, _ = project(uv, dep, cam, cam)
    require(np.allclose(identity, uv, atol=1e-13), 'Equal camera identity')
    ramp = np.arange(16., dtype=float).reshape(4,4)
    value, mask = bilinear(ramp, np.array([[[1.25,1.5],[-1.,0]]]))
    require(value[0,0] == 7.25 and not mask[0,1] and np.isnan(value[0,1]), 'Bilinear independent fixture/OOB')
    rgb = np.repeat(ramp[...,None]/16, 3, axis=-1); full = np.ones((4,4), bool)
    same, _ = score(rgb, rgb.copy(), full, 1e-12)
    require(abs(same['cost']) < 1e-14, 'Equal source score invariant')
    renamed = {name: score(rgb, rgb.copy(), full, 1e-12)[0] for name in ['prior','da3','arbitrary_source']}
    require(renamed['prior'] == renamed['arbitrary_source'] == renamed['da3'], 'Source rename invariant')
    flat, _ = score(np.zeros_like(rgb), rgb, full, 1e-12)
    empty, _ = score(rgb, rgb, np.zeros_like(full), 1e-12)
    require(flat['status'] == 'UNDEFINED_FLAT_PATCH' and flat['cost'] is None, 'Flat must be undefined')
    require(empty['cost'] is None, 'No support must be undefined')
    inverse, _ = score(rgb, 1-rgb, full, 1e-12)
    require(abs(inverse['zncc']+1) < 1e-14 and abs(inverse['cost']-1) < 1e-14, 'Inverse pattern cost')
    return dict(status='PASS', checks=['camera_identity','analytic_translated_projection','bilinear_scalar_fixture',
        'out_of_bounds','equal_sources','source_rename','flat_undefined','empty_support_undefined','inverted_pattern'])


def load_mvs(path, meta):
    with path.open('rb') as f:
        header = b''
        while header.count(b'&') < 3:
            header += f.read(1)
            require(len(header) <= 100, 'Bad MVS header')
        w,h,c = map(int, header.decode().split('&')[:3])
        require((w,h,c) == (meta['width'],meta['height'],1), 'MVS dimensions differ')
        require(len(header) == meta['header_bytes'], 'MVS header differs')
        a = np.frombuffer(f.read(), dtype='<f4')
    require(a.size == w*h, 'MVS payload size differs')
    return a.reshape((w,h), order='F').T.copy()


def sampled_sources(uv, arrays, ref):
    result = {}
    p, pm = bilinear(arrays['prior'], uv-.5, positive=True)
    result['prior'] = (p, pm, uv-.5)
    x, y = uv[...,0].astype(int), uv[...,1].astype(int)
    d = arrays['da3'][y,x]
    result['da3'] = (np.where(valid(d),d,np.nan), valid(d), uv)
    K = np.asarray(ref['K']); Km = np.asarray(ref['maps']['depth']['K'])
    ray = np.concatenate((uv, np.ones(uv.shape[:-1]+(1,))),axis=-1) @ np.linalg.inv(K).T
    native = ray @ Km.T; native = native[...,:2]/native[...,2:3]
    xx, yy = np.floor(native[...,0]+.5).astype(int), np.floor(native[...,1]+.5).astype(int)
    h,w = arrays['mvs'].shape
    inside = (xx >= 0)&(xx < w)&(yy >= 0)&(yy < h)
    m = arrays['mvs'][np.clip(yy,0,h-1), np.clip(xx,0,w-1)]
    mm = inside & valid(m)
    result['mvs'] = (np.where(mm,m,np.nan), mm, native)
    return result


def camera_center(c):
    return -np.asarray(c['R']).T @ np.asarray(c['t'])


def pick_centers(arrays, ref, cfg):
    rows, chosen = [], {}
    margin = cfg['context_size']//2+1
    for y in range(margin, ref['height']-margin, cfg['grid_spacing_px']):
        for x in range(margin, ref['width']-margin, cfg['grid_spacing_px']):
            sampled = sampled_sources(uv_grid((x,y),cfg['patch_size']), arrays, ref)
            p, pm, _ = sampled['prior']; d, dm, _ = sampled['da3']
            both = pm&dm
            delta = float(np.median(np.abs(p[both]-d[both]))) if both.any() else None
            row = dict(center_uv=[x,y],prior_count=int(pm.sum()),da3_count=int(dm.sum()),
                mvs_count=int(sampled['mvs'][1].sum()), median_prior_da3_disagreement_m=delta)
            rows.append(row)
            label = None
            if both.all() and delta <= cfg['disagreement_bands_m']['low_max']:
                label='low_disagreement'
            elif both.all() and delta >= cfg['disagreement_bands_m']['high_min']:
                label='high_disagreement'
            elif not pm.any() and dm.all():
                label='prior_hole'
            if label and label not in chosen:
                chosen[label] = dict(row, selection_reason=label)
            if both.all() and not sampled['mvs'][1].all() and 'mvs_hole' not in chosen:
                chosen['mvs_hole'] = dict(row, selection_reason='mvs_hole')
    return rows, chosen


def save_rgb(path, rgb, mask=None):
    array = np.clip(np.nan_to_num(rgb)*255,0,255).round().astype(np.uint8)
    if mask is not None:
        array[~mask] = [180,180,180]
    Image.fromarray(array).save(path)


def save_mask(path, mask):
    Image.fromarray((mask*255).astype(np.uint8)).save(path)


def save_residual(path, residual):
    cmap = plt.get_cmap('coolwarm').copy(); cmap.set_bad('#b4b4b4')
    rgba = cmap(np.ma.masked_invalid(np.clip((residual+3)/6,0,1)))
    Image.fromarray((rgba*255).round().astype(np.uint8)).save(path)


def save_standardized(path, values):
    cmap = plt.get_cmap('gray').copy(); cmap.set_bad('#b4b4b4')
    rgba = cmap(np.ma.masked_invalid(np.clip((values+3)/6,0,1)))
    Image.fromarray((rgba*255).round().astype(np.uint8)).save(path)


def perimeter(q):
    return np.concatenate((q[0],q[1:,-1],q[-1,-2::-1],q[-2:0:-1,0]),axis=0)


def overlay(photo, path, polygons, center=None):
    im = Image.fromarray(photo.copy()); draw = ImageDraw.Draw(im)
    for points, color in polygons:
        # Draw segments separately; missing/out-of-image samples remain gaps.
        for a,b in zip(points, np.roll(points,-1,axis=0)):
            if np.isfinite(a).all() and np.isfinite(b).all() and np.max(np.abs([a,b])) < 1e5:
                draw.line([tuple(a),tuple(b)],fill=color,width=3)
    if center is not None:
        x,y = center; draw.line([(x-7,y),(x+7,y)],fill='#ffffff',width=2);draw.line([(x,y-7),(x,y+7)],fill='#ffffff',width=2)
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage', choices=['plan','execute'], required=True)
    for arg in ['inputs','config','binding','launcher','output']:
        ap.add_argument('--'+arg,type=Path,required=True)
    args=ap.parse_args(); require(Path('/.dockerenv').exists(),'Docker required')
    out=args.output; started=time.time(); inputs={}; cases=[]; score_rows=[]; checks=[]
    def bind(path, expected=None):
        h=sha(path); require(expected is None or h==expected,'Input hash differs: '+str(path))
        inputs[str(path)]=dict(path=str(path),sha256=h,bytes=path.stat().st_size)
        return path
    try:
        cfg=read(bind(args.config)); binding=read(bind(args.binding))
        require(cfg['scientific_verdict'] is None and binding['scientific_verdict'] is None,'Verdict forbidden')
        require(cfg['scope']=='INTERNAL_FIT_DIAGNOSTIC' and cfg['q_computed'] is False,'Scope differs')
        for path in [Path(__file__),args.launcher,args.config,args.binding]:
            bind(path)
            destination=out/('config.json' if path==args.config else path.name)
            if args.stage=='plan': shutil.copyfile(path,destination)
            else: require(sha(path)==sha(destination),'Plan/execute source drift')
        unit=self_checks()
        prior_plan=read(out/'plan.json') if args.stage=='execute' else None
        neighbor_mounts=set(); region_plans=[]
        for spec in cfg['references']:
            region,name=spec['region'],spec['camera']; root=args.inputs/region
            manifest=read(bind(root/'input_manifest.json',binding['regions'][region]['manifest']['sha256']))
            seals={r['path']:r['sha256'] for r in manifest['files']}
            def sealed(relative):
                require(relative in seals,'Unsealed region input: '+relative)
                return bind(root/relative,seals[relative])
            split=read(sealed('scene/split_manifest_da3_v2.json'))
            views={v['name']:v for v in split['train']}
            require(name in views,'Reference is not train member')
            ref=views[name]
            require(ref['camera_model']=='PINHOLE','Unexpected camera model')
            arrays={source:np.load(sealed(source+'/raw_depth/'+Path(name).stem+'.npy'),allow_pickle=False)
                    for source in ['prior','da3']}
            require(all(a.shape==(ref['height'],ref['width']) for a in arrays.values()),'Target dimensions differ')
            mmeta=ref['maps']['depth']; mpath=bind(root/'mvs.geometric.bin',mmeta['sha256'])
            arrays['mvs']=load_mvs(mpath,mmeta)
            grid, chosen=pick_centers(arrays,ref,cfg)
            candidates=[]
            for other in views.values():
                if other['name']==name:continue
                distance=float(np.linalg.norm(camera_center(ref)-camera_center(other)))
                angle=float(np.degrees(np.arccos(np.clip(np.asarray(ref['R'])[2]@np.asarray(other['R'])[2],-1,1))))
                if distance>=cfg['minimum_baseline_m'] and angle<=cfg['maximum_optical_axis_angle_deg']:
                    candidates.append(dict(camera_id=other['name'],baseline_m=distance,optical_axis_angle_deg=angle))
            candidates.sort(key=lambda x:(x['baseline_m'],x['camera_id']))
            selected=candidates[:cfg['maximum_neighbors']]
            require(selected,'No geometry-selected train neighbor')
            plan=dict(region=region,ref_camera=name,grid=grid,chosen=chosen,neighbors=selected,
                all_geometric_candidates=candidates,missing_selection_strata=sorted(set(['low_disagreement','high_disagreement','prior_hole','mvs_hole'])-set(chosen)),
                mvs_original_path=mmeta['path'],mvs_native_shape=list(arrays['mvs'].shape))
            region_plans.append(plan)
            for camera in [name]+[r['camera_id'] for r in selected]: neighbor_mounts.add((region,camera))
            if args.stage=='plan':continue
            require(plan==next(p for p in prior_plan['regions'] if p['region']==region),'Selection changed after plan')
            photos={n:np.asarray(Image.open(sealed('scene/images/'+n)).convert('RGB'))
                    for n in [name]+[r['camera_id'] for r in selected]}
            require(all(v.shape==(views[n]['height'],views[n]['width'],3) for n,v in photos.items()),'Photo dimensions differ')
            for label,center_info in chosen.items():
                center=center_info['center_uv']; cid=region+'_'+label; folder=out/'cases'/cid;folder.mkdir(parents=True,exist_ok=False)
                def url(path):return str(path.relative_to(out))
                context_uv=uv_grid(center,cfg['context_size']); patch_uv=uv_grid(center,cfg['patch_size'])
                radius=cfg['context_size']//2; pr=cfg['patch_size']//2;slice9=(slice(radius-pr,radius+pr+1),)*2
                ref_context=photos[name][context_uv[...,1].astype(int),context_uv[...,0].astype(int)]/255.
                ref_patch=ref_context[slice9]
                save_rgb(folder/'ref_patch.png',ref_patch);save_rgb(folder/'ref_context.png',ref_context)
                overlay(photos[name],folder/'ref_full_overlay.png',[(perimeter(context_uv),'#ffffff'),(perimeter(patch_uv),'#ff2060')],center)
                sampled=sampled_sources(context_uv,arrays,ref)
                depths={s:(float(values[0][radius,radius]) if values[1][radius,radius] else None) for s,values in sampled.items()}
                p4=arrays['prior'][center[1]-1:center[1]+1,center[0]-1:center[0]+1]
                case=dict(case_id=cid,label=region+' '+label,region=region,ref_camera=name,
                    center_uv=center,selection=center_info,ref_patch_url=url(folder/'ref_patch.png'),
                    ref_context_url=url(folder/'ref_context.png'),ref_full_overlay_url=url(folder/'ref_full_overlay.png'),
                    exact_patch_size=cfg['patch_size'],context_patch_size=cfg['context_size'],context_used_for_score=False,
                    depths=depths,center_prior_four_samples_m=[[float(v) if np.isfinite(v) else None for v in row] for row in p4],
                    center_prior_four_sample_range_m=float(np.ptp(p4)) if valid(p4).all() else None,
                    colors=cfg['colors'],reference_camera_model=ref,neighbors=[],scope=cfg['scope'],scientific_verdict=None)
                for ni,geom in enumerate(selected):
                    neighbor=views[geom['camera_id']];nf=folder/f'neighbor_{ni+1:02d}';nf.mkdir()
                    entry=dict(camera_id=neighbor['name'],selection_geometry=geom,neighbor_camera_model=neighbor,
                        visibility_status='unknown',sources={},comparisons={})
                    cache={};polygons=[];npz={'reference_uv':context_uv,'reference_rgb':ref_context}
                    for source,(dep,dm,native_uv) in sampled.items():
                        target,z,world=project(context_uv,dep,ref,neighbor)
                        warped,inside=bilinear(photos[neighbor['name']]/255.,target)
                        mask=dm & inside & np.isfinite(z)&(z>0)
                        warped[~mask]=np.nan
                        save_rgb(nf/(source+'_warped_context.png'),warped,mask)
                        save_rgb(nf/(source+'_warped_patch.png'),warped[slice9],mask[slice9])
                        save_mask(nf/(source+'_valid_mask.png'),mask[slice9])
                        polygon=perimeter(target);polygons.append((polygon,cfg['colors'][source]))
                        overlay(photos[neighbor['name']],nf/(source+'_full_overlay.png'),[(polygon,cfg['colors'][source]),(perimeter(target[slice9]),cfg['colors'][source])])
                        source_record=dict(warped_patch_url=url(nf/(source+'_warped_patch.png')),
                            warped_context_url=url(nf/(source+'_warped_context.png')),
                            full_overlay_url=url(nf/(source+'_full_overlay.png')),valid_mask_url=url(nf/(source+'_valid_mask.png')),
                            raw_target_valid_count=int(dm[slice9].sum()),projectable_sample_count=int(mask[slice9].sum()),
                            context_projectable_sample_count=int(mask.sum()),visibility_status='unknown',
                            projected_context_polygon_uv=[[float(v) if np.isfinite(v) else None for v in point] for point in polygon],
                            color=cfg['colors'][source],native_query_convention=cfg['pixel_conventions'][source if source!='da3' else 'reference_rgb_and_da3'])
                        def finite_list(a):
                            return [float(v) if np.isfinite(v) else None for v in np.ravel(a)]
                        ray_center=np.linalg.solve(np.asarray(ref['K']),np.r_[center,1.])
                        world_center=world[radius,radius]
                        neighbor_center=np.asarray(neighbor['R'])@world_center+np.asarray(neighbor['t'])
                        center_steps=dict(reference_uv=center,native_depth_query_uv=finite_list(native_uv[radius,radius]),
                            reference_camera_ray_xyz=finite_list(ray_center),depth_m=depths[source],
                            reference_camera_xyz=finite_list(ray_center*dep[radius,radius]),world_xyz=finite_list(world_center),
                            neighbor_camera_xyz=finite_list(neighbor_center),projected_uv=finite_list(target[radius,radius]),
                            projectable=bool(mask[radius,radius]),rgb_sample_0_1=finite_list(warped[radius,radius]),
                            bilinear_neighbor_pixels=None,bilinear_weights=None)
                        if mask[radius,radius]:
                            tx,ty=target[radius,radius];ix,iy=int(np.floor(tx)),int(np.floor(ty))
                            jx,jy=min(ix+1,neighbor['width']-1),min(iy+1,neighbor['height']-1)
                            dx,dy=float(tx-ix),float(ty-iy)
                            coords=[(ix,iy),(jx,iy),(ix,jy),(jx,jy)]
                            weights=[(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy]
                            pixels=[photos[neighbor['name']][y,x]/255. for x,y in coords]
                            center_steps['bilinear_neighbor_pixels']=[dict(uv=list(q),rgb_0_1=p.tolist()) for q,p in zip(coords,pixels)]
                            center_steps['bilinear_weights']=weights
                            scalar=np.array([sum(w*float(p[channel]) for w,p in zip(weights,pixels)) for channel in range(3)])
                            bilinear_error=float(np.max(np.abs(scalar-warped[radius,radius])))
                            require(bilinear_error<1e-14,'Actual independent bilinear mismatch')
                            checks.append(dict(case_id=cid,neighbor=neighbor['name'],source=source,center_bilinear_max_abs_error=bilinear_error))
                        source_record['center_projection_steps']=center_steps
                        entry['sources'][source]=source_record;cache[source]=(warped[slice9],mask[slice9])
                        for key,a in [('depth',dep),('raw_valid',dm),('native_query_uv',native_uv),('projected_uv',target),('neighbor_camera_z',z),('world_xyz',world),('warped_rgb',warped),('projectable_mask',mask)]:npz[source+'_'+key]=a
                        # Independent per-ray matrix solve and reprojection for actual inputs.
                        max_error=0.
                        for yy,xx in zip(*np.where(dm[slice9])):
                            y,x=yy+radius-pr,xx+radius-pr
                            ray=np.linalg.solve(np.asarray(ref['K']),np.r_[context_uv[y,x],1.])
                            X=np.linalg.solve(np.asarray(ref['R']),ray*dep[y,x]-np.asarray(ref['t']))
                            Q=np.asarray(neighbor['K'])@(np.asarray(neighbor['R'])@X+np.asarray(neighbor['t']))
                            if Q[2]>0:max_error=max(max_error,float(np.max(np.abs(Q[:2]/Q[2]-target[y,x]))))
                        require(max_error<1e-8,'Actual independent projection mismatch')
                        checks.append(dict(case_id=cid,neighbor=neighbor['name'],source=source,projection_max_abs_error_px=max_error))
                    overlay(photos[neighbor['name']],nf/'all_sources_full_overlay.png',polygons)
                    entry['full_overlay_url']=url(nf/'all_sources_full_overlay.png')
                    for image_source in ['da3','mvs']:
                        pair='prior_'+image_source;common=cache['prior'][1]&cache[image_source][1]
                        save_mask(nf/(pair+'_common_mask.png'),common)
                        comp=dict(common_valid_mask_url=url(nf/(pair+'_common_mask.png')),common_count=int(common.sum()),
                            total_patch_pixels=cfg['patch_size']**2,scores={},normalized_residual_urls={},
                            standardized_reference_url=url(nf/(pair+'_standardized_reference.png')),standardized_source_urls={},
                            normalization_formula='z=(gray-mean_on_pair_common_mask)/population_std_on_pair_common_mask',visual_clip=[-3,3],
                            residual_definition='(gray_reference-mean_reference)/std_reference - (gray_warp-mean_warp)/std_warp; pairwise common mask only',
                            residual_display_range=[-3,3],status='DEFINED_DESCRIPTIVE_ONLY',visibility_status='unknown')
                        for source in ['prior',image_source]:
                            s,residual=score(ref_patch,cache[source][0],common,cfg['numeric_flat_epsilon'])
                            comp['scores'][source]=s
                            save_residual(nf/(pair+'_'+source+'_normalized_residual.png'),residual)
                            comp['normalized_residual_urls'][source]=url(nf/(pair+'_'+source+'_normalized_residual.png'))
                            npz[pair+'_'+source+'_normalized_residual']=residual
                            zr=np.full(common.shape,np.nan);zw=np.full(common.shape,np.nan)
                            if s['std_reference'] is not None and s['std_reference']>cfg['numeric_flat_epsilon']:
                                zr[common]=(gray(ref_patch)[common]-s['mean_reference'])/s['std_reference']
                            if s['std_warp'] is not None and s['std_warp']>cfg['numeric_flat_epsilon']:
                                zw[common]=(gray(cache[source][0])[common]-s['mean_warp'])/s['std_warp']
                            if source=='prior':save_standardized(nf/(pair+'_standardized_reference.png'),zr)
                            save_standardized(nf/(pair+'_'+source+'_standardized.png'),zw)
                            comp['standardized_source_urls'][source]=url(nf/(pair+'_'+source+'_standardized.png'))
                            npz[pair+'_standardized_reference']=zr;npz[pair+'_'+source+'_standardized_warp']=zw
                            if s['zncc'] is not None:
                                independent=independent_score(ref_patch,cache[source][0],common)
                                error=abs(independent-s['zncc']);require(error<1e-11,'Independent ZNCC mismatch')
                                checks.append(dict(case_id=cid,neighbor=neighbor['name'],pair=pair,source=source,zncc_abs_error=error))
                            else:comp['status']='PARTIAL_OR_UNDEFINED_SEE_SOURCE_STATUS'
                            score_rows.append(dict(case_id=cid,neighbor=neighbor['name'],comparison=pair,source=source,visibility_status='unknown',**s))
                        npz[pair+'_common_mask']=common;entry['comparisons'][pair]=comp
                    np.savez_compressed(nf/'numeric_arrays.npz',**npz)
                    entry['numeric_arrays_url']=url(nf/'numeric_arrays.npz')
                    # A standalone, readable per-neighbor panel; context is never scored.
                    fig,ax=plt.subplots(3,4,figsize=(13,9),constrained_layout=True)
                    fig.suptitle(f'{cid} | reference {name}\nneighbor {neighbor["name"]} | 9x9 scores; 65x65 context only | visibility UNKNOWN',fontsize=10)
                    for si,source in enumerate(['prior','da3','mvs']):
                        ax[si,0].imshow(ref_context);ax[si,0].set_title('Reference context (not scored)')
                        ax[si,1].imshow(np.nan_to_num(npz[source+'_warped_rgb'],nan=.7));ax[si,1].set_title(source+' warped context')
                        ax[si,2].imshow(ref_patch,interpolation='nearest');ax[si,2].set_title('Exact reference 9x9')
                        ax[si,3].imshow(np.nan_to_num(cache[source][0],nan=.7),interpolation='nearest');ax[si,3].set_title(source+' exact warped 9x9')
                    for a in ax.ravel():a.set_xticks([]);a.set_yticks([])
                    fig.savefig(nf/'walkthrough.png',dpi=120);plt.close(fig)
                    entry['walkthrough_url']=url(nf/'walkthrough.png');case['neighbors'].append(entry)
                write(folder/'case.json',case);cases.append(dict(case_id=cid,label=case['label'],path=url(folder/'case.json')))
        if args.stage=='plan':
            write(out/'plan.json',dict(schema='jbgs.photometric_walkthrough.plan.v3.2',created_utc=datetime.now(timezone.utc).isoformat(),
                regions=region_plans,inputs=list(inputs.values()),tests=unit,selection_before_rgb_scores=True,scientific_verdict=None))
            (out/'neighbor_names.tsv').write_text(''.join(region+'\t'+name+'\n' for region,name in sorted(neighbor_mounts)))
            print(json.dumps(dict(stage='plan',status='PASS',output=str(out),cases=sum(len(p['chosen']) for p in region_plans))))
            return
        with (out/'scores.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(score_rows[0]));writer.writeheader();writer.writerows(score_rows)
        write(out/'validation.json',dict(status='PASS',synthetic=unit,actual_checks=checks,scientific_verdict=None))
        write(out/'manifest.json',dict(schema='jbgs.photometric_walkthrough.manifest.v3.2',scope=cfg['scope'],cases=cases,
            colors=cfg['colors'],score_definition=cfg['score'],pixel_conventions=cfg['pixel_conventions'],
            context_used_for_score=False,winner_selection=False,q_computed=False,scientific_verdict=None,
            limitations=['Existing source generation may include these same train photos: internal fit, not independent validation.',
                'Projection in image is not visibility; occlusion and correspondence are UNKNOWN.',
                'Prior half-pixel alignment uses four-valid bilinear depth queries; discontinuities can mix surfaces.',
                'MVS native nearest lookup preserves holes but adds raster quantization; no new depth inference.',
                'Two historical reference cameras are contextual choices; new patch centers use only fixed grid and raw input masks/disagreement.',
                'A mathematically defined cost is not a texture/support/quality gate and does not select a source.',
                'No GT, model output, q, training, CUDA, or Gaussian update is used.']))
        for p,row in inputs.items():require(sha(p)==row['sha256'],'Input changed during diagnostic: '+p)
        # stdout remains open until process exit; never promise an immutable hash for it.
        outputs=[dict(path=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='execute.log']
        write(out/'receipt.json',dict(schema='jbgs.photometric_walkthrough.receipt.v3.2',status='PASS_INTERNAL_FIT_DIAGNOSTIC',
            scope=cfg['scope'],scientific_verdict=None,inputs=list(inputs.values()),outputs=outputs,config=cfg,command=sys.argv,
            tests=unit,actual_numeric_checks=len(checks),case_count=len(cases),score_row_count=len(score_rows),
            unsealed_live_log='execute.log (stdout closes after receipt creation; not scientific input/output)',
            change_record='Add independent MVS-hole grid category and center projection/bilinear details; exclude active stdout from output seal. Earlier six-case attempt is preserved.',
            wall_seconds=time.time()-started,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            versions=dict(python=platform.python_version(),numpy=np.__version__,pillow=Image.__version__,matplotlib=matplotlib.__version__),
            runtime=dict(image_id=os.environ['JBGS_RUNTIME_IMAGE_ID'],cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip(),memory_max=Path('/sys/fs/cgroup/memory.max').read_text().strip()),
            input_pre_post_hashes_equal=True,gt_mounted=False,model_payload_mounted=False,gpu_used=False))
        print(json.dumps(dict(status='PASS_INTERNAL_FIT_DIAGNOSTIC',output=str(out),cases=len(cases),score_rows=len(score_rows))))
    except Exception as exc:
        write(out/('failure_'+args.stage+'.json'),dict(status='FAIL',error=repr(exc),stage=args.stage,inputs=list(inputs.values()),scientific_verdict=None))
        raise


if __name__=='__main__':main()
