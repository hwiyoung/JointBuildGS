"""Build inspectable prior/MVS evidence from sealed inputs, in CPU Docker only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import warnings

import numpy as np
from PIL import Image, ImageDraw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize, ListedColormap

from src.phd import mvs_evidence_v1 as core
from src.phd.geogs_mvs_pgsr_v1.mvs_depth import read_colmap_depth


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if isinstance(value, dict): return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [clean(v) for v in value]
    if isinstance(value, np.ndarray): return clean(value.tolist())
    if isinstance(value, (np.floating, float)):
        return round(float(value), 6) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    return value


def write(path, data):
    Path(path).write_text(json.dumps(clean(data), ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n')


def median(a, axis=0):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        return np.nanmedian(a, axis=axis)


def normals(uv, depths, K):
    """Least-squares source normal; no depth fill and no new supervision target."""
    rays = np.concatenate([uv, np.ones(uv.shape[:-1]+(1,))], -1) @ np.linalg.inv(K).T
    points = rays * depths[..., None]
    good = np.isfinite(points).all(-1) & (depths > 0)
    count = good.sum(1)
    mean = np.where(good[..., None], points, 0).sum(1) / np.maximum(count[:, None], 1)
    centered = np.where(good[..., None], points-mean[:, None], 0)
    cov = np.einsum('npi,npj->nij', centered, centered) / np.maximum(count[:, None, None], 1)
    vals, vec = np.linalg.eigh(cov)
    normal = vec[:, :, 0]
    normal[count < .8*depths.shape[1]] = np.nan
    normal[vals[:, 1] <= 1e-12] = np.nan
    # Sign is irrelevant to a center-anchored plane.
    return normal


def patch_uv(centers, radius):
    yy, xx = np.mgrid[-radius:radius+1, -radius:radius+1]
    return centers[:, None, :] + np.stack([xx.ravel(), yy.ravel()], -1)[None]


def profile_summary(depths, cost, excess):
    valid = np.isfinite(cost).all(1)
    width = np.full(len(cost), np.nan); modes = width.copy(); edge = np.zeros(len(cost), bool); boundary=edge.copy()
    best = width.copy(); spacing=width.copy(); minimum=width.copy()
    for i in np.flatnonzero(valid):
        k = int(np.argmin(cost[i])); near = cost[i] <= cost[i, k]+excess
        z = depths[i, near]
        width[i] = float(z.max()-z.min())
        modes[i] = int(near[0])+int(np.count_nonzero(near[1:] & ~near[:-1]))
        edge[i] = bool(cost[i,0]<=cost[i,k]+1e-12 or cost[i,-1]<=cost[i,k]+1e-12)
        boundary[i] = bool(near[0] or near[-1])
        best[i] = depths[i, k]
        spacing[i]=float(np.max(np.diff(depths[i,max(0,k-1):min(len(depths[i]),k+2)])))
        minimum[i]=float(cost[i,k])
    return dict(width=width, modes=modes, edge=edge, near_cost_touches_boundary=boundary, best=best,grid_spacing=spacing,minimum_cost=minimum)


class Builder:
    def __init__(self, args):
        self.a=args; self.out=args.output; self.bound={}; self.cache={}; self.regional={}
        self.cfg=json.loads(args.config.read_text()); self.started=time.time()
        self.out.mkdir(parents=True, exist_ok=False)
        self.bind(args.config)
        self.receipt=json.loads(self.bind(args.mvs/'receipt.json', self.cfg['input_receipt_sha256']).read_text())
        if self.receipt['status'] != 'PASS': raise ValueError('MVS binding receipt not PASS')
        self.data=dict(title='Prior–MVS 관측 단계 비교', scope=self.cfg['scope'],
                       created_at=datetime.now(timezone.utc).isoformat(), config=self.cfg, regions=[])
        self.checks=[]
        for file in [Path(__file__), Path(core.__file__), Path('/repo/src/phd/geogs_mvs_pgsr_v1/mvs_depth.py'),
                     Path('/repo/src/apps/mvs_evidence_v1/index.html'),
                     Path('/repo/tests/phd/test_mvs_evidence_v1.py'),Path('/repo/tests/phd/test_mvs_evidence_driver_v1.py')]:
            self.bind(file)
            (self.out/'source_snapshot').mkdir(exist_ok=True)
            shutil.copy2(file, self.out/'source_snapshot'/file.name)
        shutil.copy2(args.config,self.out/'config.json')
        shutil.copy2('/repo/src/apps/mvs_evidence_v1/index.html',self.out/'index.html')

    def bind(self,path,expected=None):
        path=Path(path)
        h=sha(path)
        if expected is not None and expected != h: raise ValueError('Hash mismatch: '+str(path))
        self.bound[str(path)]=dict(path=str(path),sha256=h,bytes=path.stat().st_size)
        return path

    def setup_region(self,region):
        binding=json.loads(self.bind(self.a.mvs/region/'bindings.json',self.receipt['regions'][region]['binding_sha256']).read_text())
        manifest=json.loads(self.bind(self.a.inputs/region/'input_manifest.json',binding['parent_input_manifest_sha256']).read_text())
        seals={x['path']:x['sha256'] for x in manifest['files']}
        self.regional[region]=dict(binding=binding,manifest=manifest,seals=seals,
                                  views={v['name']:v for v in binding['train']})
        if set(binding['evaluation_names']) & set(self.regional[region]['views']): raise ValueError('Eval leak')
        return binding

    def prior(self,region,name):
        path='prior/raw_depth/'+Path(name).stem+'.npy'
        file=self.bind(self.a.inputs/region/path,self.regional[region]['seals'][path])
        return np.load(file,allow_pickle=False)

    def load(self,region,name):
        key=(region,name)
        if key not in self.cache:
            view=self.regional[region]['views'][name]
            rp='scene/images/'+name
            rgb_path=self.bind(self.a.inputs/region/rp,view['sha256'])
            if self.regional[region]['seals'][rp] != view['sha256']: raise ValueError('RGB lineage mismatch')
            dp=self.bind(self.a.mvs/region/view['local_depth'],view['maps']['depth']['sha256'])
            rgb=np.asarray(Image.open(rgb_path).convert('RGB'),dtype=np.float32)/255
            self.cache[key]=dict(view=view,rgb=rgb,gray=rgb.astype(float)@np.array([.299,.587,.114]),
                                 mvs=read_colmap_depth(dp,view['maps']['depth']),prior=self.prior(region,name),photo=rgb_path)
        return self.cache[key]

    def select(self,region,binding):
        rows=[]
        for v in binding['train']:
            d=self.prior(region,v['name'])[::16,::16]
            rows.append(dict(name=v['name'],prior_samples=int((np.isfinite(d)&(d>0)).sum()),
                             neighbors=len(binding['neighbor_graph']['graph'][v['name']]['selected']),
                             center=(-np.asarray(v['R']).T@np.asarray(v['t'])).tolist()))
        eligible=sorted([r for r in rows if r['neighbors']>=2 and r['prior_samples']>0],key=lambda x:(-x['prior_samples'],x['name']))
        selected=[]
        if not eligible: raise ValueError('No supported camera in '+region)
        selected.append(eligible[0])
        pool=[r for r in eligible[1:] if r['prior_samples']>=.35*eligible[0]['prior_samples']]
        while pool and len(selected)<self.cfg['cameras_per_region']:
            pick=max(pool,key=lambda r:r['prior_samples']**.5*min(np.linalg.norm(np.array(r['center'])-s['center']) for s in selected))
            selected.append(pick);pool.remove(pick)
        if len(selected) != self.cfg['cameras_per_region']: raise ValueError('Insufficient diverse cameras')
        write(self.out/region/'camera_selection.json',dict(all_train=rows,selected=selected,policy=self.cfg['camera_selection']))
        return [r['name'] for r in selected]

    def layer(self,folder,camera,key,label,values,centers=None,vmin=0,vmax=1,cmap='viridis',description='',units=''):
        norm=Normalize(vmin,vmax,clip=True); cmap_obj=plt.get_cmap(cmap) if isinstance(cmap,str) else cmap
        height,width=camera['height'],camera['width']
        if centers is None:
            rgba=cmap_obj(norm(np.nan_to_num(values,nan=vmin)))
            rgba[...,3]=np.isfinite(values)*.87
            image=Image.fromarray((rgba*255).astype(np.uint8),'RGBA')
        else:
            image=Image.new('RGBA',(width,height),(0,0,0,0));draw=ImageDraw.Draw(image)
            radius=5 if 'ambiguity' not in key and 'profile' not in key else 8
            for (x,y),value in zip(centers,values):
                if np.isfinite(value):
                    color=tuple((np.array(cmap_obj(norm(value)))*255).astype(int)[:3])+(230,)
                    draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=color)
        path=folder/(key+'.png');image.save(path)
        stops=[dict(color=matplotlib.colors.to_hex(cmap_obj(t)),label=str(round(vmin+t*(vmax-vmin),3))) for t in (0,.5,1)]
        camera['layers'].append(dict(id=key,label=label,path=str(path.relative_to(self.out)),description=description,
                                     vmin=vmin,vmax=vmax,units=units,cmap=cmap if isinstance(cmap,str) else 'categorical',legend=stops))

    def profiles(self,centers,dp,dm,patchP,patchM,ref,neighbors):
        cfg=self.cfg;rad=cfg['patch_radius'];uv=patch_uv(centers,rad)
        normP=normals(uv,patchP,np.asarray(ref['view']['K']));normM=normals(uv,patchM,np.asarray(ref['view']['K']))
        padding=np.maximum(cfg['profile_padding_m'],.5*np.abs(dp-dm))
        low=np.maximum(.1,np.minimum(dp,dm)-padding);high=np.maximum(dp,dm)+padding
        tt=np.linspace(0,1,cfg['profile_samples'])
        depths=1/((1/low[:,None])*(1-tt)+(1/high[:,None])*tt)
        n=len(centers); allcost=[]; allgood=[]
        # Plane exploration must not synthesize evidence through source holes.
        complete_source=(np.isfinite(patchP)&(patchP>0)).all(1)&(np.isfinite(patchM)&(patchM>0)).all(1)
        for nb in neighbors[:cfg['profile_neighbors']]:
            branch=[];good=complete_source.copy()
            for normal in (normP,normM):
                scores=[]
                for j in range(cfg['profile_samples']):
                    c,texture,fraction=core.batched_patch_cost(centers,depths[:,j],ref['view'],nb['view'],ref['gray'],nb['gray'],rad,normal=normal)
                    good &= np.isfinite(c)&(fraction>=1-1e-12)&(texture>=cfg['texture_std'])
                    scores.append(c)
                branch.append(np.stack(scores,1))
            costs=np.stack(branch,1)
            costs[~good]=np.nan
            allcost.append(costs);allgood.append(good)
        raw=np.stack(allcost) if allcost else np.full((0,n,2,cfg['profile_samples']),np.nan)
        count=np.stack(allgood).sum(0) if allgood else np.zeros(n,int)
        costs=median(raw,0) if len(raw) else np.full((n,2,cfg['profile_samples']),np.nan)
        costs[count<2]=np.nan
        # Union of low-cost hypotheses across either source-normal family.
        bestfamily=np.min(costs,axis=1)
        summary=profile_summary(depths,bestfamily,cfg['profile_excess_cost'])
        return dict(depths=depths,costs=costs,per_neighbor_costs=raw,neighbor_count=count,complete_source_patch=complete_source,
                    normal_prior=normP,normal_mvs=normM,**summary)

    def camera(self,region,name,index,binding):
        cfg=self.cfg;ref=self.load(region,name);view=ref['view'];w,h=view['width'],view['height']
        folder=self.out/region/f'view_{index+1:02d}';folder.mkdir()
        neighbors=[self.load(region,n) for n in binding['neighbor_graph']['graph'][name]['selected'][:cfg['maximum_neighbors']]]
        camera=dict(id=f'{region}_{index+1}',name=name,width=w,height=h,grid_step=cfg['grid_step'],layers=[],cases=[],points=[],summary={},neighbors=[n['view']['name'] for n in neighbors])
        photo=folder/'photo.jpg';shutil.copy2(ref['photo'],photo);camera['photo']=str(photo.relative_to(self.out))
        yy,xx=np.mgrid[:h,:w];fulluv=np.stack([xx,yy],-1)
        pd,pvalid=core.sample_prior(ref['prior'],fulluv);md,mvalid=core.sample_mvs(ref['mvs'],fulluv,view)
        delta=pd-md; validity=pvalid.astype(int)+2*mvalid.astype(int)
        samevalid=pvalid&mvalid
        camera['summary'].update(full_pixels=w*h,prior_pixels=int(pvalid.sum()),mvs_pixels=int(mvalid.sum()),both_pixels=int(samevalid.sum()),
                                 candidate_counts={str(t):int((samevalid&(np.abs(delta)>t)).sum()) for t in cfg['candidate_sensitivity_m']},
                                 delta_display_clipped_pixels=int((np.abs(delta)>cfg['delta_display_limit_m']).sum()),
                                 prior_half_pixel_change_median_m=median(np.where(pvalid,np.abs(pd-ref['prior']),np.nan).ravel()),
                                 selected_neighbor_count=len(neighbors),regional_train_count=len(binding['train']),scientific_verdict=None)
        self.layer(folder,camera,'delta','1 · Prior − MVS 깊이차',delta,vmin=-5,vmax=5,cmap='PuOr_r',units='camera-Z m',description=cfg['delta_definition']+'; 전체 raster, 범위 밖 값은 색상 포화')
        self.layer(folder,camera,'validity','1 · 입력 존재 영역',validity,vmin=0,vmax=3,cmap=ListedColormap(['#9ca3af','#2563eb','#d97706','#7c3aed']),description='0 둘 다 없음 · 1 Prior만 · 2 MVS만 · 3 둘 다. 존재가 정확성을 뜻하지 않음')
        candidates=np.where(samevalid,(np.abs(delta)>cfg['candidate_threshold_m']).astype(float),np.nan)
        self.layer(folder,camera,'candidates','1 · 불일치 후보 (>0.5m)',candidates,cmap='YlOrBr',description='0.5m는 탐색 기준이며 시간 변화/오류 판정이 아님; 결손은 미표시')
        self.layer(folder,camera,'prior_depth','1 · Prior 깊이',pd,vmin=0,vmax=150,cmap='viridis',units='camera-Z m',description='반픽셀 ray를 보정한 조회; 깊이 결손 유지')
        self.layer(folder,camera,'mvs_depth','1 · MVS 깊이',md,vmin=0,vmax=150,cmap='viridis',units='camera-Z m',description='native COLMAP depth를 같은 RGB ray에서 nearest 조회; DA3 사용 없음')
        step=cfg['grid_step'];ys=np.arange(16,h-16,step);xs=np.arange(16,w-16,step)
        gy,gx=np.meshgrid(ys,xs,indexing='ij');centers=np.stack([gx.ravel(),gy.ravel()],-1).astype(float)
        xi,yi=centers[:,0].astype(int),centers[:,1].astype(int);dp,dm=pd[yi,xi],md[yi,xi]
        puv=patch_uv(centers,cfg['patch_radius']);patchP=core.sample_prior(ref['prior'],puv)[0];patchM=core.sample_mvs(ref['mvs'],puv,view)[0]
        n=len(centers); visP=[];visM=[];cross=[];roundtrip=[];parallax=[];photo=[];rawphoto=[];photo_counts=[];textures=[];sens=[]
        for ni,nb in enumerate(neighbors):
            vp=core.visibility(centers,dp,view,nb['view'],nb['prior'],cfg['depth_tolerance_m'],neighbor_kind='prior')
            vm=core.visibility(centers,dm,view,nb['view'],nb['mvs'],cfg['depth_tolerance_m'],neighbor_kind='mvs')
            cp=core.visibility(centers,dp,view,nb['view'],nb['mvs'],cfg['depth_tolerance_m'],neighbor_kind='mvs')
            visP.append(vp['status']);visM.append(vm['status']);cross.append(cp['status']);roundtrip.append(vm['roundtrip_px']);parallax.append(np.where(vm['status']>=2,vm['parallax_deg'],np.nan))
            pair=core.pair_patch_cost(centers,dp,dm,view,nb['view'],ref['gray'],nb['gray'],cfg['patch_radius'],prior_patch_depth=patchP,mvs_patch_depth=patchM,
                                      minimum_fraction=cfg['minimum_patch_fraction'],texture_std=cfg['texture_std'])
            photo.append(pair['costs']);rawphoto.append(pair['raw_costs']);photo_counts.append(pair['common_count']);textures.append(np.min(pair['texture_std'].reshape(n,-1),1))
            zres=cp['z_residual'];sens.append(np.stack([np.isfinite(zres)&(np.abs(zres)<=t) for t in cfg['depth_tolerance_sensitivity_m']]))
            print(json.dumps(dict(region=region,camera=index+1,stage='neighbor',neighbor=ni+1,total=len(neighbors))),flush=True)
        visP,visM,cross=np.stack(visP),np.stack(visM),np.stack(cross);photo=np.stack(photo)
        costs=median(photo,0);common=np.isfinite(photo).all(-1).sum(0);costs[common<2]=np.nan
        margins=photo[:,:,0]-photo[:,:,1];pos=(margins>.01).sum(0);neg=(margins<-.01).sum(0)
        rank=np.divide(np.minimum(pos,neg),pos+neg,out=np.full(n,np.nan),where=(pos+neg)>=2)
        values=dict(prior_depth=dp,mvs_depth=dm,delta=dp-dm,prior_self_visible=(visP==3).sum(0).astype(float),
                    mvs_self_consistent=(visM==3).sum(0).astype(float),prior_cross_compatible=(cross==3).sum(0).astype(float),
                    prior_occluded=(cross==4).sum(0).astype(float),mvs_occluded=(visM==4).sum(0).astype(float),
                    common_photo_views=np.where(np.isfinite(dp)&np.isfinite(dm),common.astype(float),np.nan),photo_prior=costs[:,0],photo_mvs=costs[:,1],photo_margin=costs[:,0]-costs[:,1],
                    rank_disagreement=rank,parallax_deg=median(np.stack(parallax),0),texture=median(np.stack(textures),0),
                    ambiguity_width_m=np.full(n,np.nan),ambiguity_modes=np.full(n,np.nan),profile_neighbor_count=np.full(n,np.nan),
                    profile_edge=np.full(n,np.nan),profile_low_cost_boundary=np.full(n,np.nan),profile_grid_spacing_m=np.full(n,np.nan),profile_min_cost=np.full(n,np.nan),mvs_roundtrip_px=median(np.stack(roundtrip),0),
                    prior_cross_observed=((cross>=3)&(cross<=5)).sum(0).astype(float),prior_cross_front=(cross==5).sum(0).astype(float))
        for key in ('prior_self_visible','prior_cross_compatible','prior_occluded','prior_cross_observed','prior_cross_front'): values[key][~np.isfinite(dp)]=np.nan
        for key in ('mvs_self_consistent','mvs_occluded','mvs_roundtrip_px'):values[key][~np.isfinite(dm)]=np.nan
        selected=np.flatnonzero(((xi-16)%cfg['profile_grid_step']==0)&((yi-16)%cfg['profile_grid_step']==0)&np.isfinite(dp)&np.isfinite(dm))
        print(json.dumps(dict(region=region,camera=index+1,stage='profiles',points=len(selected))),flush=True)
        profile=self.profiles(centers[selected],dp[selected],dm[selected],patchP[selected],patchM[selected],ref,neighbors)
        for key,field in [('ambiguity_width_m','width'),('ambiguity_modes','modes'),('profile_neighbor_count','neighbor_count'),('profile_edge','edge')]:values[key][selected]=profile[field]
        for key,field in [('profile_low_cost_boundary','near_cost_touches_boundary'),('profile_grid_spacing_m','grid_spacing'),('profile_min_cost','minimum_cost')]:values[key][selected]=profile[field]
        values['profile_edge'][~np.isfinite(values['ambiguity_width_m'])]=np.nan
        values['profile_low_cost_boundary'][~np.isfinite(values['ambiguity_width_m'])]=np.nan
        raw=dict(centers=centers,prior_native=ref['prior'],prior_common_ray=pd,mvs_common_ray=md,delta=delta,validity=validity,
                 prior_self_status=visP,mvs_self_status=visM,prior_to_mvs_status=cross,photo_costs_per_neighbor=photo,raw_photo_costs_per_neighbor=np.stack(rawphoto),
                 photo_common_counts=np.stack(photo_counts),cross_tolerance_counts=np.stack(sens),profile_point_indices=selected,
                 **{'point_'+k:v for k,v in values.items()},**{'profile_'+k:v for k,v in profile.items()})
        np.savez_compressed(folder/'arrays.npz',**raw);camera['arrays']=str((folder/'arrays.npz').relative_to(self.out))
        for i,center in enumerate(centers):camera['points'].append(dict(u=int(center[0]),v=int(center[1]),**{k:v[i] for k,v in values.items()}))
        definitions=[('prior_self_visible','2 · Prior 내부 깊이 일치','Prior를 이웃 Prior에 투영: ±0.5m 일치 수. 자체 모델의 가림/지원 검사',0,8,'Purples','views'),
                     ('mvs_self_consistent','2 · MVS 내부 깊이 일치','MVS를 이웃 MVS에 투영: ±0.5m 일치 수. 독립 정확도 아님',0,8,'Purples','views'),
                     ('prior_cross_compatible','2 · Prior→현재 MVS 호환','현재 MVS에 조건부인 ±0.5m 일치 수; Prior 정오/현재성 판정 아님',0,8,'Purples','views'),
                     ('prior_occluded','2 · Prior가 MVS 뒤에 있음','투영 Prior가 이웃 MVS보다 0.5m 이상 뒤: 가림 또는 표면 충돌 후보',0,8,'Oranges','views'),
                     ('prior_cross_front','2 · Prior가 MVS 앞에 있음','투영 Prior가 이웃 MVS보다 0.5m 이상 앞: 자유공간 충돌 후보, MVS 결손/오류 가능',0,8,'Blues','views'),
                     ('prior_cross_observed','2 · 이웃 MVS 관측 수','Prior 투영점에서 깊이가 있는 이웃 수. 0과 입력 결손을 구분',0,8,'Purples','views'),
                     ('mvs_roundtrip_px','2 · MVS 왕복 재투영','이웃 MVS 깊이로 되돌린 픽셀 거리; source 내부 일치 진단',0,5,'magma','px'),
                     ('common_photo_views','3 · 공통 사진 지원','두 가설에 같은 픽셀이 남고 텍스처 기준을 통과한 이웃 수; 가림 확정 검사는 아님',0,8,'Purples','views'),
                     ('photo_margin','3 · 사진 비용 차이',cfg['photo_margin_definition'],-.3,.3,'PuOr_r','ZNCC cost'),
                     ('rank_disagreement','3 · 이웃간 우열 불일치','비용차 >.01 또는 <-.01인 이웃 중 소수 방향 비율. 0.5는 반반; 최소 2개 필요',0,.5,'YlOrRd','fraction'),
                     ('parallax_deg','3 · 관측 시차각','MVS 점에서 두 카메라를 보는 광선 사이 각도의 중앙값; 높이 판별력 보조 지표',0,30,'viridis','degrees'),
                     ('ambiguity_width_m','4 · 낮은 비용 깊이 범위','48px 표본만 표시. min(cost)+.03 이내 깊이 전체 폭; 신뢰구간 아님. 0은 한 깊이 격자점만 남았다는 뜻이며 불확실성 0이 아님',0,10,'YlOrRd','m'),
                     ('ambiguity_modes','4 · 분리된 낮은 비용 구간','두 source normal 가설의 합집합에서 분리된 저비용 구간 수',0,5,'YlOrRd','intervals'),
                     ('profile_neighbor_count','4 · 비용곡선 공통 이웃','모든 깊이·두 normal에서 완전한 공통 패치가 있는 이웃 수; 2 미만은 곡선 판정 없음',0,4,'Purples','views'),
                     ('profile_min_cost','4 · 깊이 탐색 최저 비용','탐색한 깊이·normal 가설 중 최저 사진 비용; 높은 최저 비용은 어느 가설도 잘 설명하지 못함',0,1,'magma','ZNCC cost'),
                     ('profile_low_cost_boundary','4 · 저비용 구간의 범위 끝 도달','1: 낮은 비용 깊이 범위가 탐색 경계에 닿아 실제 폭이 더 넓을 수 있음',0,1,'Oranges','flag'),
                     ('profile_edge','4 · 탐색 끝 최소점','1: 최저 비용이 깊이 탐색 끝에 있어 범위가 부족할 수 있음',0,1,'Oranges','flag')]
        for key,label,description,lo,hi,cmap,units in definitions:self.layer(folder,camera,key,label,values[key],centers,lo,hi,cmap,description,units)
        camera['summary'].update(grid_points=n,profile_points=len(selected),profile_comparable_points=int((profile['neighbor_count']>=2).sum()),
                                 profile_complete_source_points=int(profile['complete_source_patch'].sum()),
                                 photo_comparable_points=int((common>=2).sum()),
                                 status_legend={'0':'source absent','1':'outside/behind camera','2':'neighbor depth absent','3':'depth compatible','4':'behind observed depth','5':'in front of observed depth'},
                                 profile_support='same neighbors and complete pixels across all depth hypotheses and both normal branches',
                                 mvs_historical_neighbors_recovered=False,independent_accuracy=False)
        self.overview(folder,camera,ref['rgb'])
        self.cases(folder,camera,ref,neighbors,centers,values,selected,profile,photo,patchP,patchM)
        write(folder/'camera.json',camera)
        return camera

    def overview(self,folder,camera,rgb):
        keys=['photo','delta','validity','prior_self_visible','mvs_self_consistent','prior_cross_compatible','photo_margin','common_photo_views','ambiguity_width_m']
        fig,axes=plt.subplots(3,3,figsize=(16,12),constrained_layout=True)
        for ax,key in zip(axes.ravel(),keys):
            ax.imshow(rgb);ax.set_xticks([]);ax.set_yticks([])
            if key=='photo':ax.set_title('Current photograph')
            else:
                layer=next(l for l in camera['layers'] if l['id']==key)
                ax.imshow(Image.open(self.out/layer['path']))
                ax.set_title(key.replace('_',' '))
                cmap=plt.get_cmap(layer['cmap']) if layer['cmap']!='categorical' else ListedColormap(['#9ca3af','#2563eb','#d97706','#7c3aed'])
                fig.colorbar(plt.cm.ScalarMappable(norm=Normalize(layer['vmin'],layer['vmax']),cmap=cmap),ax=ax,shrink=.75,label=layer['units'])
        fig.suptitle(camera['id']+' | '+camera['name']+'\nSource evidence only; dots are measured samples, blank is unobserved; no change/accuracy verdict',fontsize=12)
        fig.savefig(folder/'overview.png',dpi=130);plt.close(fig);camera['overview']=str((folder/'overview.png').relative_to(self.out))

    def cases(self,folder,camera,ref,neighbors,centers,values,selected,profile,photo,patchP,patchM):
        valid=selected[np.isfinite(values['photo_margin'][selected])]
        chosen=[]
        choices=[('large_disagreement',valid,np.abs(values['delta'])),('small_disagreement',valid,-np.abs(values['delta'])),
                 ('broad_depth_cost',selected,values['ambiguity_width_m']),('weak_photo_support',selected,-values['common_photo_views'])]
        for label,candidates,score in choices:
            pool=[int(i) for i in candidates if np.isfinite(score[i]) and all(np.linalg.norm(centers[i]-centers[j])>64 for _,j in chosen)]
            if pool:chosen.append((label,max(pool,key=lambda i:float(score[i]))))
        for ci,(label,i) in enumerate(chosen):
            point=camera['points'][i];u,v=map(int,centers[i]);casefolder=folder/f'case_{ci+1:02d}';casefolder.mkdir()
            pi=int(np.where(selected==i)[0][0]);fig,axes=plt.subplots(1,2,figsize=(12,4),constrained_layout=True)
            for family,tag,color in [(0,'Prior normal','#2563eb'),(1,'MVS normal','#d97706')]:
                for nb in range(len(profile['per_neighbor_costs'])):axes[0].plot(profile['depths'][pi],profile['per_neighbor_costs'][nb,pi,family],color=color,alpha=.15)
                axes[0].plot(profile['depths'][pi],profile['costs'][pi,family],color=color,label=tag)
            axes[0].axvline(values['prior_depth'][i],color='#2563eb',ls='--',label='Prior depth');axes[0].axvline(values['mvs_depth'][i],color='#d97706',ls='--',label='MVS depth')
            axes[0].set(xlabel='Hypothesis camera-Z (m)',ylabel='(1 - ZNCC) / 2',ylim=(0,1),title=f'Depth profile: {profile["neighbor_count"][pi]} common views');axes[0].legend(fontsize=8)
            xx=np.arange(len(neighbors));axes[1].bar(xx-.18,photo[:,i,0],width=.36,label='Prior',color='#2563eb');axes[1].bar(xx+.18,photo[:,i,1],width=.36,label='MVS',color='#d97706')
            axes[1].set(xlabel='Bound neighbor index',ylabel='Raw-depth pair photo cost',ylim=(0,1),title='Same support per neighbor; missing bars = undefined');axes[1].legend()
            fig.suptitle(f'{camera["id"]} ({u}, {v}) | {label} | descriptive selection, no GT')
            fig.savefig(casefolder/'profile.png',dpi=130);plt.close(fig)
            fig,axes=plt.subplots(2,3,figsize=(12,8),constrained_layout=True)
            radius=90;x0,x1=max(0,u-radius),min(camera['width'],u+radius);y0,y1=max(0,v-radius),min(camera['height'],v+radius)
            for ax,key in zip(axes.ravel(),['photo','delta','prior_cross_compatible','photo_margin','common_photo_views','ambiguity_width_m']):
                ax.imshow(ref['rgb'][y0:y1,x0:x1],extent=(x0,x1,y1,y0))
                if key!='photo':
                    layer=next(l for l in camera['layers'] if l['id']==key)
                    ax.imshow(np.asarray(Image.open(self.out/layer['path']))[y0:y1,x0:x1],extent=(x0,x1,y1,y0))
                ax.plot(u,v,'+',color='#ec4899',ms=12);ax.set_title(key.replace('_',' '));ax.set_xlim(x0,x1);ax.set_ylim(y1,y0)
            fig.suptitle(f'{camera["id"]} ({u}, {v}) | {label} | exact image coordinates')
            fig.savefig(casefolder/'detail.png',dpi=130);plt.close(fig)
            patchuv=patch_uv(centers[i:i+1],self.cfg['patch_radius']);side=2*self.cfg['patch_radius']+1
            reference,refvalid=core.bilinear(ref['rgb'],patchuv)
            fig,axes=plt.subplots(len(neighbors),4,figsize=(9,2.25*len(neighbors)),squeeze=False,constrained_layout=True)
            for ni,nb in enumerate(neighbors):
                warped=[];masks=[]
                for depth in (patchP[i:i+1],patchM[i:i+1]):
                    uv2,z,_=core.project(patchuv,depth,ref['view'],nb['view'])
                    pixels,good=core.bilinear(nb['rgb'],uv2)
                    masks.append(good&refvalid&np.isfinite(depth)&(depth>0)&(z>0));warped.append(pixels)
                commonmask=masks[0]&masks[1]
                for ci2,pixels in enumerate((reference,warped[0],warped[1])):
                    tile=np.where(commonmask[...,None],pixels,.5).reshape(side,side,3)
                    axes[ni,ci2].imshow(tile,interpolation='nearest',vmin=0,vmax=1);axes[ni,ci2].set_xticks([]);axes[ni,ci2].set_yticks([])
                axes[ni,3].imshow(commonmask.reshape(side,side),cmap='gray',vmin=0,vmax=1,interpolation='nearest');axes[ni,3].set_xticks([]);axes[ni,3].set_yticks([])
                axes[ni,0].set_ylabel(f'Neighbor {ni+1}')
                axes[ni,1].set_title('Prior cost '+str(clean(photo[ni,i,0])))
                axes[ni,2].set_title('MVS cost '+str(clean(photo[ni,i,1])))
            for ax,title in zip(axes[0],['Current reference','Prior raw-depth warp','MVS raw-depth warp','Identical valid mask']):ax.set_xlabel(title)
            fig.suptitle(f'{camera["id"]} ({u},{v}) | 7x7 actual pixels, nearest display; gray excluded\nNo depth-visibility gate in photo comparison; source geometry can cross boundaries',fontsize=10)
            fig.savefig(casefolder/'patches.png',dpi=120);plt.close(fig)
            case=dict(id=f'{camera["id"]}_{ci+1}',u=u,v=v,label=label,figure=str((casefolder/'detail.png').relative_to(self.out)),profile=str((casefolder/'profile.png').relative_to(self.out)),patches=str((casefolder/'patches.png').relative_to(self.out)),summary=point)
            camera['cases'].append(case);write(casefolder/'case.json',dict(**case,neighbors=camera['neighbors'],photo_costs=photo[:,i],profile_depths=profile['depths'][pi],profile_costs=profile['costs'][pi]))

    def run(self):
        tests=subprocess.run(['/opt/geogs/bin/python','-m','unittest','tests.phd.test_mvs_evidence_v1','tests.phd.test_mvs_evidence_driver_v1','-v'],cwd='/repo',text=True,capture_output=True)
        (self.out/'tests.log').write_text(tests.stdout+tests.stderr)
        if tests.returncode:raise ValueError('Numeric tests failed')
        for region in self.cfg['regions']:
            (self.out/region).mkdir();binding=self.setup_region(region);names=self.select(region,binding)
            r=dict(id=region,cameras=[],binding_sha256=sha(self.a.mvs/region/'bindings.json'),crs=self.regional[region]['manifest']['crs'])
            for index,name in enumerate(names):
                print(json.dumps(dict(region=region,camera=index+1,name=name,stage='begin')),flush=True)
                r['cameras'].append(self.camera(region,name,index,binding))
                # Limit memory to one camera and its neighbors between cases.
                self.cache.clear()
            self.data['regions'].append(r)
            write(self.out/'manifest.json',self.data)
            (self.out/'data.js').write_text('window.MVS_EVIDENCE='+json.dumps(clean(self.data),ensure_ascii=False,allow_nan=False,separators=(',',':'))+';\n')
        for row in self.bound.values():
            if sha(row['path']) != row['sha256']:raise ValueError('Source changed during run: '+row['path'])
        outputs=[dict(path=str(p.relative_to(self.out)),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(self.out.rglob('*')) if p.is_file()]
        receipt=dict(task_id=self.cfg['task_id'],status='PASS_OBSERVATION_DIAGNOSTIC',scientific_verdict=None,inputs=list(self.bound.values()),outputs=outputs,
                     runtime=dict(image_id=os.environ.get('JBGS_RUNTIME_IMAGE_ID'),python=platform.python_version(),numpy=np.__version__,cpu_max=Path('/sys/fs/cgroup/cpu.max').read_text().strip()),
                     git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd='/repo',text=True).strip(),elapsed_seconds=time.time()-self.started,
                     gt_accessed=False,training_started=False,regions=self.cfg['regions'],cameras=sum(len(r['cameras']) for r in self.data['regions']))
        write(self.out/'receipt.json',receipt)
        print(json.dumps(dict(status=receipt['status'],output=str(self.out),elapsed_seconds=receipt['elapsed_seconds'])),flush=True)


def main():
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker CPU execution required')
    ap=argparse.ArgumentParser(description=__doc__)
    for key in ('config','inputs','mvs','output'):ap.add_argument('--'+key,type=Path,required=True)
    args=ap.parse_args()
    try:Builder(args).run()
    except Exception as exc:
        if args.output.exists():write(args.output/'failure.json',dict(error=type(exc).__name__,message=str(exc),scientific_verdict=None))
        raise


if __name__=='__main__':main()
