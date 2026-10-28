"""Gaussian population membership, birth-sidecar lineage, and display point files."""
import argparse
import csv
import json
import gc
from pathlib import Path
import numpy as np
from plyfile import PlyData
from scipy.spatial import cKDTree
from scipy.special import expit
import open3d as o3d
from common import *
from recount import load_eval,classes
from geometry import write_points,rgb

def membership(xyz,opacity,e,z):
    valid=e['in_eval']&e['scoring_allowed']&(e['cell']>=0)&(e['cell']<=3)
    cat=classes(e,z);patch_types=[valid&(cat==1),valid&(cat==0)]
    masks=[];mapped=[]
    # Exact per-patch 0.25m horizontal squares. cKDTree limits candidates only;
    # query_ball_point ensures overlapping cells are never silently discarded.
    for typ,pm in enumerate(patch_types):
        ids=np.flatnonzero(pm);tree=cKDTree(e['centre'][ids,:2])
        take=np.zeros(len(xyz),bool);owner=np.full(len(xyz),-1,np.int32)
        if len(ids):
            gt=e['centre'][ids,2]+e['p_gt'][ids]*e['normal'][ids,2]
            outer=e['centre'][ids,2]+z['z'][ids]*e['normal'][ids,2]
            bottom=gt+e['tau'][ids] if typ==0 else gt-e['tau'][ids]
            top=outer+.25 if typ==0 else gt+e['tau'][ids]
            candidates=np.flatnonzero((opacity>=.1)&(xyz[:,2]>=np.nanmin(bottom))&(xyz[:,2]<=np.nanmax(top)))
            for start in range(0,len(candidates),20000):
                q=candidates[start:start+20000]
                neighbours=tree.query_ball_point(xyz[q,:2],np.sqrt(2)*.125+1e-8,workers=2)
                for gi,local in zip(q,neighbours):
                    if not local:continue
                    ix=np.asarray(local,int);pi=ids[ix]
                    on=(np.abs(e['centre'][pi,:2]-xyz[gi,:2])<=.125+1e-8).all(1)&(xyz[gi,2]>=bottom[ix])&(xyz[gi,2]<=top[ix])
                    if on.any():
                        candidates2=pi[on]
                        # Save one deterministic owner for indexing only; membership
                        # is the union across every matching patch.
                        best=candidates2[np.argmin(np.linalg.norm(e['centre'][candidates2,:2]-xyz[gi,:2],axis=1))]
                        take[gi]=True;owner[gi]=best
        masks.append(take);mapped.append(owner)
    return masks,mapped

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--site',required=True);ap.add_argument('--prior',default='ALS');a=ap.parse_args()
    cfg=config();e,_=load_eval(a.site,a.prior)
    cases=json.loads((CFG/f'geometry_{a.site}_{a.prior}.json').read_text())['cases'];rows=[];inputs=[]
    for result in [f'{p}_{a.prior}_s0' for p in ['nojudge','lt_dyngt','lt_dynnow']]:
        model=model_path(a.site,result);p=model/'point_cloud/iteration_30000/point_cloud.ply'
        d=PlyData.read(str(p),mmap='r')['vertex'].data
        xyz=np.column_stack([d[k] for k in ['x','y','z']]);opacity=expit(d['opacity'].astype(float))
        scale=np.exp(np.column_stack([d[k] for k in d.dtype.names if k.startswith('scale_')])).max(1)
        colour=np.clip(.5+.28209479177387814*np.column_stack([d[f'f_dc_{k}'] for k in range(3)]),0,1)*255
        origin=d['origin'].astype(np.int8) if 'origin' in d.dtype.names else np.full(len(d),-1,np.int8)
        lineage=np.full(len(d),3,np.uint8)
        birth=model/'monitor/losstrain_birth_30000.npz'
        if birth.exists():
            with np.load(birth) as b:survivor=b['initial_survivor']
            assert len(survivor)==len(d)
            lineage[~survivor]=0;lineage[survivor&(origin==1)]=1;lineage[survivor&(origin==0)]=2
        with np.load(LT/'patch_z'/f'{a.site}__{a.prior}__{result}.npz') as f:z={k:f[k] for k in f.files}
        masks,owners=membership(xyz,opacity,e,z)
        payload=OUT/'gaussians'/a.site/result;payload.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(payload/'membership.npz',floating=masks[0],roof=masks[1],floating_patch=owners[0],roof_patch=owners[1],
            opacity=opacity.astype(np.float32),max_axis_m=scale.astype(np.float32),lineage=lineage,origin=origin)
        sources=dict(model=str(p),model_sha256=sha(p),birth_sidecar=str(birth) if birth.exists() else None,
            birth_sha256=sha(birth) if birth.exists() else None)
        inputs.append(sources)
        scope=[('전체',np.ones(len(d),bool))]
        palette=np.array([rgb(cfg['colours']['lineage'][k]) for k in ['densified','initial_prior','initial_image','unrecorded']])
        for c in cases:
            keep=((xyz>=c['crop_min'])&(xyz<=c['crop_max'])).all(1);scope.append((c['id'],keep))
            display=keep&(opacity>=.1);dest=OUT/'3d'/c['id']
            write_points(dest/(result+'__gaussian_colour.ply'),xyz[display]-c['translation'],colour[display])
            write_points(dest/(result+'__gaussian_lineage.ply'),xyz[display]-c['translation'],palette[lineage[display]])
        for name,region in scope:
            for kind,m in zip(['floating','roof'],masks):
                ids=np.flatnonzero(m&region);w=opacity[ids];total=float(w.sum());lin=lineage[ids]
                r=dict(site=a.site,prior=a.prior,result=result,case=name,kind=kind,count=len(ids),opacity_weight_sum=total,
                    opacity_median=float(np.median(w)) if len(ids) else None,max_axis_median_m=float(np.median(scale[ids])) if len(ids) else None,
                    birth_iteration=None,birth_iteration_status='기록 없음: initial_survivor는 생성 반복을 저장하지 않음',
                    photo_centre_gradient_median=None,depth_centre_gradient_median=None,depth_over_photo=None,
                    gradient_status='미계산',sample_status='표본 부족' if len(np.unique(owners[['floating','roof'].index(kind)][ids]))<100 else 'PASS',
                    source=str(payload/'membership.npz'),origin_label='[이 발주에서 냄]')
                for k,key in enumerate(['densified','initial_prior','initial_image','unrecorded']):
                    r[key+'_opacity_fraction']=float(w[lin==k].sum()/total) if total and (k==3 or birth.exists()) else None
                rows.append(r)
        print(a.site,result,'Gaussian groups',[(k,int(m.sum())) for k,m in zip(['floating','roof'],masks)],flush=True)
        del d,xyz,opacity,scale,colour,origin,lineage,masks,owners;gc.collect()
    save(DOC/'tables'/f'gaussians_{a.site}_{a.prior}.json',dict(rows=rows,inputs=inputs,scientific_verdict=None))
    with (DOC/'tables'/f'gaussians_{a.site}_{a.prior}.csv').open('w') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    lines=['# 가우시안과 계보','','[이 발주에서 냄]. 판정 끔의 origin·init_id는 생성 여부를 구분하지 못하므로 계보는 기록 없음이다.','',
        '| 결과 | 사례 | 구분 | N | 불투명도 중앙값 | 최대 축 중앙값 m | 밀도 제어 생성 비율 |','|---|---|---|---:|---:|---:|---:|']
    fmt=lambda x:'확인 불가' if x is None else f'{x:.6f}'
    for r in rows:lines.append(f"| {r['result']} | {r['case']} | {r['kind']} | {r['count']} | {fmt(r['opacity_median'])} | {fmt(r['max_axis_median_m'])} | {fmt(r['densified_opacity_fraction'])} |")
    (DOC/'tables'/f'gaussians_{a.site}_{a.prior}.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
