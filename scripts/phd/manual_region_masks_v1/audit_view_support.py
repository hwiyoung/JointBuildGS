"""Separate raw current-depth observation from a source-conditioned mask draft."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import time

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manual_region_masks_v1 import unproject, project, nearest_indices
from mvs_depth import checked_bytes, read_colmap_depth


def save_json(path, data):
    with Path(path).open('x') as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    cfg = json.loads(args.config.read_text())
    if not Path('/.dockerenv').exists() or Path('/artifacts/JointBuildGS').exists():
        raise RuntimeError('Isolated Docker required')
    start = time.monotonic()
    out = args.output
    out.mkdir(exist_ok=False)
    binding = json.loads(checked_bytes('/mvs_input/bindings.json',cfg['binding_sha256']))
    prior = json.loads(checked_bytes('/masks/receipt.json',cfg['parent_receipt_sha256']))
    views = binding['train']
    rows0 = {r['name']:r for r in prior['views']}
    output_hashes = {r['path']:r['sha256'] for r in prior['outputs']}
    ref = views[cfg['reference_train_index']]
    depth0 = read_colmap_depth(Path('/mvs_input')/ref['local_depth'],ref['maps']['depth'])
    xyz0 = unproject(depth0,np.asarray(ref['maps']['depth']['K']),ref['R'],ref['t'])
    path0 = rows0[ref['name']]['folder']+'/native_masks.npz'
    checked_bytes(Path('/masks')/path0,output_hashes[path0])
    with np.load(Path('/masks')/path0,allow_pickle=False) as data:
        r1 = data['region_id'] == 1
    valid0 = np.isfinite(depth0) & (depth0 > 0)
    roi = valid0.copy()
    for i,key in enumerate(('x','y','z')):
        lo,hi = cfg['original_p1_roi'][key]
        roi &= (xyz0[...,i]>=lo)&(xyz0[...,i]<=hi)
    union = roi|r1
    yy,xx = np.nonzero(union)
    points = xyz0[union]
    reference_pixels = np.column_stack((xx,yy))
    subsets = {'whole_r1':r1[union], 'r1_in_original_p1':(r1&roi)[union], 'original_p1_all_surfaces':roi[union]}
    other_support = np.zeros(len(points), np.uint16)
    other_depth_available = np.zeros(len(points), np.uint16)
    names, support_per_view, rows = [], [], []
    for index,view in enumerate(views):
        depth = read_colmap_depth(Path('/mvs_input')/view['local_depth'],view['maps']['depth'])
        meta = view['maps']['depth']
        uv,z,front = project(points,meta['K'],view['R'],view['t'])
        y,x,frame = nearest_indices(uv,depth.shape)
        in_frame = frame&front
        observed = depth[y,x]
        has_depth = in_frame&np.isfinite(observed)&(observed>0)
        residual = observed-z
        near = has_depth&(residual < -cfg['depth_tolerance_m'])
        far = has_depth&(residual > cfg['depth_tolerance_m'])
        close = has_depth&(np.abs(residual)<=cfg['depth_tolerance_m'])
        relaxed = has_depth&(np.abs(residual)<=cfg['sensitivity_tolerance_m'])
        source_rays = np.column_stack((x,y,np.ones(len(x)))) @ np.linalg.inv(meta['K']).T
        source_xyz = (source_rays*np.where(has_depth,observed,0)[:,None]-np.asarray(view['t']))@np.asarray(view['R'])
        back_uv,_,back_front = project(source_xyz,ref['maps']['depth']['K'],ref['R'],ref['t'])
        roundtrip = np.linalg.norm(back_uv-reference_pixels,axis=1)
        agree = close&back_front&(roundtrip<=cfg['reference_roundtrip_native_px'])
        rel = rows0[view['name']]['folder']+'/native_masks.npz'
        checked_bytes(Path('/masks')/rel,output_hashes[rel])
        with np.load(Path('/masks')/rel,allow_pickle=False) as data:
            retained = has_depth&(data['region_id'][y,x] == 1)
        all_xyz = unproject(depth,np.asarray(meta['K']),view['R'],view['t'])
        own_roi = np.isfinite(depth)&(depth>0)
        for i,key in enumerate(('x','y','z')):
            lo,hi=cfg['original_p1_roi'][key]
            own_roi &= (all_xyz[...,i]>=lo)&(all_xyz[...,i]<=hi)
        base = {'train_index':index,'name':view['name'],
                'raw_native_points_in_original_p1_prism':int(own_roi.sum()),
                'final_native_r1_pixels':rows0[view['name']]['native_counts']['1'],
                'final_rgb_r1_pixels':rows0[view['name']]['rgb_counts']['1']}
        for key,subset in subsets.items():
            n=int(subset.sum())
            base[key]={'reference_sample_count':n}
            for measure,mask in [('in_frame',in_frame),('has_depth',has_depth),('nearer',near),('farther',far),('depth_close',close),('depth_close_1m',relaxed),('depth_and_roundtrip',agree),('final_r1',retained)]:
                base[key][measure]=int((mask&subset).sum())
                base[key][measure+'_fraction']=float((mask&subset).sum()/n) if n else None
            assert base[key]['has_depth'] == base[key]['nearer']+base[key]['farther']+base[key]['depth_close']
        if index != cfg['reference_train_index']:
            other_support+=agree.astype(np.uint16)
            other_depth_available+=has_depth.astype(np.uint16)
        names.append(view['name']); support_per_view.append(agree)
        rows.append(base)
    totals={}
    for key,subset in subsets.items():
        count=other_support[subset]
        totals[key]={'reference_samples':int(subset.sum()),
                    'any_other_view_has_depth_fraction':float((other_depth_available[subset]>0).mean()),
                    'any_other_view_agrees_fraction':float((count>0).mean()),
                    'at_least_two_other_views_agree_fraction':float((count>=2).mean()),
                    'at_least_three_other_views_agree_fraction':float((count>=3).mean()),
                    'no_other_view_agrees_fraction':float((count==0).mean())}
    native_r1=sum(r['final_native_r1_pixels'] for r in rows)
    rgb_r1=sum(r['final_rgb_r1_pixels'] for r in rows)
    summary={'task_id':cfg['task_id'],'status':'PASS_READ_ONLY_VIEW_SUPPORT_AUDIT','scientific_verdict':None,
             'config':cfg,'mask_dependence':{'native_r1_source0_fraction':rows[0]['final_native_r1_pixels']/native_r1,
                                           'rgb_r1_source0_fraction':rows[0]['final_rgb_r1_pixels']/rgb_r1,
                                           'raw_views_with_any_original_p1_points':sum(r['raw_native_points_in_original_p1_prism']>0 for r in rows)},
             'common_reference_sample_support':totals,'views':rows,
             'runtime_seconds':time.monotonic()-start,
             'limits':['Source-0 current-MVS surface is the coordinate reference, not independent truth.',
                       'All fractions query identical reference native sample IDs; they are not physical-area estimates or confidence scores.',
                       'Valid depth along a query ray can belong to an occluder; nearer/farther residuals also include MVS errors.',
                       'Forward reference queries are a separate diagnostic from the inverse per-target mask propagation.',
                       'Repeated nearby camera views and MVS estimates are correlated; count is not independent support.']}
    save_json(out/'receipt.json',summary)
    np.savez_compressed(out/'reference_sample_support.npz',source_native_xy=reference_pixels,source_xyz=points,
                        support_per_view=np.stack(support_per_view),other_support=other_support,
                        other_depth_available=other_depth_available,**subsets)
    ranked=sorted(rows[1:],key=lambda r:r['r1_in_original_p1']['depth_and_roundtrip_fraction'],reverse=True)[:10]
    font_manager.fontManager.addfont(cfg['font_path'])
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=cfg['font_path']).get_name(),'axes.unicode_minus':False})
    fig,ax=plt.subplots(figsize=(12,7))
    y=np.arange(len(ranked))
    for shift,metric,label,color in [(-.25,'has_depth','투영 위치에 depth 존재','#D5DADD'),(0,'depth_and_roundtrip','기준면 depth·재투영 일치','#397CAC'),(.25,'final_r1','현재 초안에서 보정 영역으로 남음','#D59625')]:
        ax.barh(y+shift,[r['r1_in_original_p1'][metric+'_fraction']*100 for r in ranked],height=.23,label=label,color=color)
    ax.set_yticks(y,[f'{r["train_index"]:02d} | '+r['name'][12:-4] for r in ranked])
    ax.invert_yaxis();ax.set_xlim(0,100)
    ax.set_xlabel('동일한 기준면 표본 중 비율 (%)');ax.legend(loc='lower right',frameon=False)
    ax.set_title('P1 보정 지면 · 0100_D 외 시점의 MVS 관측과 마스크',loc='left',fontsize=16,pad=18)
    for spine in ('top','right'):ax.spines[spine].set_visible(False)
    fig.text(.02,.035,'기준: 0100_D의 현재 MVS 중 기존 P1 안의 보정 지면. 다른 시점의 일치율 상위 10개. 0.5m / 2px 진단 기준.',fontsize=10)
    fig.text(.02,.012,'depth 존재는 지면 관측을 보증하지 않음. 기준면과의 일치는 정확도·독립 다중시점 증거를 뜻하지 않음.',fontsize=10)
    fig.subplots_adjust(left=.19,right=.97,top=.88,bottom=.16)
    fig.savefig(out/'other_view_support.png',dpi=140);plt.close(fig)
    fields=['train_index','name','raw_native_points_in_original_p1_prism','final_native_r1_pixels','final_rgb_r1_pixels']
    with (out/'view_support.csv').open('x',newline='') as stream:
        metrics=['in_frame','has_depth','nearer','farther','depth_close','depth_and_roundtrip','final_r1']
        writer=csv.DictWriter(stream,fieldnames=fields+[m+'_fraction' for m in metrics])
        writer.writeheader()
        for row in rows:
            writer.writerow({**{k:row[k] for k in fields},**{m+'_fraction':row['r1_in_original_p1'][m+'_fraction'] for m in metrics}})
    print(json.dumps({'mask_dependence':summary['mask_dependence'],'common_reference_sample_support':totals,
                      'ranked_other_views':[{k:r[k] for k in ['train_index','name','r1_in_original_p1']} for r in ranked]},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
