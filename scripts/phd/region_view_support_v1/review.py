#!/usr/bin/env python3
"""Independent CSV/array checks, historical P1 roundtrip comparison, and figures."""
import argparse
import csv
import json
from pathlib import Path
import sys
import numpy as np
from scipy import sparse
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle
sys.path.insert(0, '/repo')
from src.phd.region_view_support_v1 import read_depth, sha256, object_basis


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+'\n')


def project(points, view):
    camera = points @ np.asarray(view['R']).T + np.asarray(view['t'])
    uvz = camera @ np.asarray(view['native_K']).T
    return uvz[:,:2] / np.where(camera[:,2] > 0, camera[:,2], 1)[:,None], camera[:,2]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();root=Path(args.result);out=Path(args.output);out.mkdir(exist_ok=False)
    cfg=json.loads((root/'config.json').read_text());summary=json.loads((root/'summary.json').read_text())
    receipt=json.loads((root/'receipt.json').read_text())
    for name, record in receipt['output_files'].items():
        assert sha256(root/name)==record['sha256'], name
    memberships=json.loads((root/'candidate_memberships.json').read_text())
    names=memberships['names'];all_views=json.loads((root/'camera_bindings.json').read_text())['cameras']
    tables=[];plot_data={};verified=[]
    for region in cfg['regions']:
        rid=region['id'];s=summary['regions'][rid];selection=memberships['regions'][rid]
        rows=list(csv.DictReader((root/(rid+'_views.csv')).open()))
        assert [r['name'] for r in rows]==names
        values=np.array([int(r['rgb_pixels'])/max(1,int(r['full_valid_rgb_pixels'])) for r in rows])
        np.testing.assert_allclose(values,[float(r['support_mass']) for r in rows],rtol=0,atol=1e-12)
        train=np.array(selection['train']);rank=np.argsort(-values[train]);weight=values[train][rank]
        weight/=weight.sum();curve=weight.cumsum()
        n90=int(np.flatnonzero(curve>=.9)[0]+1)
        assert n90==s['train']['n_cumulative']['0.9']
        assert abs(weight[0]-s['train']['top1_fraction'])<1e-12
        with np.load(root/(rid+'_point_support.npz')) as data:
            assert data['names'].tolist()==names
            supports=np.unpackbits(data['packed'],axis=2)[...,:int(data['point_count'])].astype(bool)
        assert supports.shape[1]==937
        for j,key in enumerate(('agree_025','agree_05','agree_10')):
            np.testing.assert_array_equal(supports[j].sum(axis=1),[int(r[key]) for r in rows])
        point_count=supports[1,train].sum(axis=0)
        assert abs(float((point_count==0).mean())-s['train']['same_point_support']['0.5']['zero_fraction'])<1e-12
        csr=sparse.load_npz(root/(rid+'_rgb_voxel_counts.npz'))
        np.testing.assert_array_equal(csr.sum(axis=1).A.ravel(),[int(r['rgb_pixels']) for r in rows])
        ref=np.load(root/(rid+'_reference_points.npz'))['xyz']
        plot_data[rid]=dict(curve=curve,ref=ref,point_count=point_count)
        top_name=names[train[rank[0]]]
        tables.append(dict(region=rid,candidates=s['candidate_count'],train_candidates=len(train),
            evaluation_candidates=s['evaluation_candidate_count'],
            valid_mvs_views=s['train']['native_views_at_least']['1'],
            mvs_views_ge_100=s['train']['native_views_at_least']['100'],
            mvs_views_ge_1000=s['train']['native_views_at_least']['1000'],
            main_views_90pct=n90,top1_percent=100*weight[0],top_view=top_name,
            same_point_zero_percent=100*float((point_count==0).mean()),
            same_point_one_percent=100*float((point_count==1).mean()),
            local_one_view_percent=100*s['local_voxels']['one_view_fraction']))
        verified.append(rid+': CSV counts, full-frame denominator, N90, packed same-point counts, and voxel totals agree')

    # Repeat the historical P1 criterion exactly on identical source point IDs.
    with np.load('/p1_ground/reference_sample_support.npz') as old:
        ground_mask=old['r1_in_original_p1'];points=old['source_xyz'][ground_mask]
        reference_pixels=old['source_native_xy'][ground_mask]
        historical_support=old['support_per_view'][:,ground_mask]
    source_name='DJI_20241217084553_0100_D.JPG';source=all_views[names.index(source_name)]
    support=np.zeros((937,len(points)),dtype=bool)
    for i,view in enumerate(all_views):
        depth,meta=read_depth(Path('/cameras/stereo/depth_maps')/(view['name']+'.geometric.bin'))
        assert meta['sha256']==view['native_depth']['sha256']
        uv,z=project(points,view);xy=np.floor(uv+.5).astype(np.int64)
        frame=(z>0)&(xy[:,0]>=0)&(xy[:,0]<depth.shape[1])&(xy[:,1]>=0)&(xy[:,1]<depth.shape[0])
        x=np.clip(xy[:,0],0,depth.shape[1]-1);y=np.clip(xy[:,1],0,depth.shape[0]-1)
        observed=depth[y,x];has=frame&np.isfinite(observed)&(observed>0)
        rays=np.column_stack((x,y,np.ones(len(x))))@np.linalg.inv(view['native_K']).T
        target_xyz=(rays*np.where(has,observed,0)[:,None]-np.asarray(view['t']))@np.asarray(view['R'])
        back_uv,back_z=project(target_xyz,source)
        support[i]=has&(np.abs(observed-z)<=.5)&(back_z>0)&(np.linalg.norm(back_uv-reference_pixels,axis=1)<=2.)
        if i%200==0:print('P1 depth + roundtrip:',i+1,'/937',flush=True)
    old_binding=json.loads(Path('/bindings/P1.json').read_text())
    oldids=[names.index(v['name']) for v in old_binding['train']]
    np.testing.assert_array_equal(support[oldids],historical_support)
    verified.append('P1 original-98 strict depth<=0.5m + roundtrip<=2px: every saved boolean reproduced on identical point IDs')
    ground_results={}
    groups={'original_98':oldids,'R1_all_candidates':memberships['regions']['R1']['candidates'],
            'R1_train_candidates':memberships['regions']['R1']['train'],'all_937':list(range(937))}
    for label,ids in groups.items():
        other=[i for i in ids if names[i]!=source_name];counts=support[other].sum(axis=0)
        rank=sorted(other,key=lambda i:-int(support[i].sum()))
        ground_results[label]=dict(views=len(ids),source_0100_included=names.index(source_name) in ids,
            no_other_pct=100*float((counts==0).mean()),any_other_pct=100*float((counts>0).mean()),
            at_least_two_others_pct=100*float((counts>=2).mean()),at_least_three_others_pct=100*float((counts>=3).mean()),
            other_views_ge_1pct_of_ground=int(sum(support[i].mean()>=.01 for i in other)),
            other_views_ge_10pct_of_ground=int(sum(support[i].mean()>=.1 for i in other)),
            top_other_views=[dict(name=names[i],ground_support_percent=100*float(support[i].mean())) for i in rank[:15]])
    np.savez_compressed(out/'P1_ground_strict_point_support.npz',packed=np.packbits(support,axis=1),point_count=len(points),names=np.array(names))
    save(out/'P1_ground_strict_summary.json',dict(depth_tolerance_m=.5,roundtrip_native_px=2.,
        source_0100=source_name,samples=len(points),scientific_verdict=None,groups=ground_results))
    with (out/'region_summary.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=tables[0].keys());writer.writeheader();writer.writerows(tables)
    overlaps=[]
    for j,a in enumerate(cfg['regions']):
        for b in cfg['regions'][j+1:]:
            area=float(np.prod([max(0,min(a[k][1],b[k][1])-max(a[k][0],b[k][0])) for k in ('u_m','v_m')]))
            common=len(set(memberships['regions'][a['id']]['train'])&set(memberships['regions'][b['id']]['train']))
            overlaps.append(dict(first=a['id'],second=b['id'],xy_overlap_m2=area,shared_train_candidates=common))
    save(out/'region_overlap.json',overlaps)

    font_manager.fontManager.addfont('/font/NotoSansCJK-Regular.ttc')
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname='/font/NotoSansCJK-Regular.ttc').get_name(),
                         'axes.unicode_minus':False,'font.size':11,'savefig.dpi':160})
    basis=object_basis(cfg['frame']['u_axis_angle_degrees_ccw_from_easting'])
    xyz=np.load(root/'overview_input_points.npz')['xyz'];uv=xyz[:,:2]@basis.T
    fig,ax=plt.subplots(figsize=(15,7.4));ax.set_facecolor('#111923')
    ax.scatter(uv[:,0],uv[:,1],s=.07,color='#298feb',rasterized=True)
    for region in cfg['regions']:
        u0,u1=region['u_m'];v0,v1=region['v_m'];color=region['color']
        ax.add_patch(Rectangle((u0,v0),u1-u0,v1-v0,fill=False,lw=2.4,edgecolor=color))
        ax.text(u0+3,v0+4,region['id'],ha='left',va='top',color='white',fontweight='bold',
                bbox=dict(facecolor=color,edgecolor='none',pad=4))
    for old,p in cfg['legacy_prisms'].items():
        corner=np.array([[p['x'][0],p['y'][0]],[p['x'][1],p['y'][0]],[p['x'][1],p['y'][1]],[p['x'][0],p['y'][1]],[p['x'][0],p['y'][0]]])@basis.T
        ax.plot(corner[:,0],corner[:,1],color='white',lw=1.1,ls='--')
        center=corner[:4].mean(axis=0);ax.text(*center,old,color='white',fontsize=10,ha='center')
    ax.set(xlim=(-140,335),ylim=(135,-100),aspect='equal',xlabel='객체 축 u (m)',ylabel='객체 직교 축 v (m)',
           title='R1–R5 좌표 기준 v1 · 실제 MVS 입력 위의 영역\n점은 입력 형상 확인용 표본 · 흰 점선은 기존 P1/P2/P3')
    fig.tight_layout();fig.savefig(out/'regions_overview.png');plt.close(fig)

    fig,axes=plt.subplots(1,5,figsize=(18,4.9),squeeze=False)
    colors=['#929ba5','#c74643','#e7ab43','#247f68'];labels=['0개','1개','2개','3개 이상']
    for ax,region in zip(axes[0],cfg['regions']):
        data=plot_data[region['id']];uv=data['ref'][:,:2]@basis.T;levels=np.minimum(data['point_count'],3)
        for level in (3,2,1,0):
            m=levels==level;ax.scatter(uv[m,0],uv[m,1],s=1,c=colors[level],label=labels[level],rasterized=True)
        ax.set(xlim=region['u_m'],ylim=region['v_m'][::-1],aspect='equal',title=region['id'])
        ax.tick_params(labelsize=8)
    handles,labels2=axes[0,0].get_legend_handles_labels();fig.legend(handles[::-1],labels2[::-1],loc='lower center',ncol=4,markerscale=5)
    fig.suptitle('동일한 입력 MVS 표면점과 깊이 차이 ≤0.5m인 학습 후보 영상 수\n입력끼리의 일치이며, 정답·물리적 면적·독립 관측 수가 아님',fontsize=13)
    fig.tight_layout(rect=(0,.1,1,.86));fig.savefig(out/'same_point_support.png');plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(12,4.8))
    for region in cfg['regions']:
        curve=plot_data[region['id']]['curve'];axes[0].plot(np.arange(1,len(curve)+1),curve*100,label=region['id'],color=region['color'],lw=2)
    axes[0].axhline(90,color='#87909a',ls='--',lw=1);axes[0].legend(frameon=False,ncol=3)
    axes[0].set(xlabel='감독 계수량이 큰 순서의 영상 수',ylabel='누적 감독 계수량 (%)',ylim=(0,102),title='영역 전체의 기여 집중도')
    for i,row in enumerate(tables):
        vals=[row['same_point_zero_percent'],row['same_point_one_percent'],100-row['same_point_zero_percent']-row['same_point_one_percent']]
        left=0
        for value,color,label in zip(vals,[colors[0],colors[1],colors[3]],['일치 없음','한 영상','두 영상 이상']):
            axes[1].barh(i,value,left=left,color=color,label=label if i==0 else None);left+=value
    axes[1].set(yticks=range(5),yticklabels=[r['region'] for r in tables],xlim=(0,100),xlabel='공통 입력 표본 중 비율 (%)',title='동일 지점의 지원은 별도 확인')
    axes[1].invert_yaxis();axes[1].legend(loc='lower center',bbox_to_anchor=(.5,-.33),ncol=3,frameon=False)
    fig.tight_layout();fig.savefig(out/'supervision_concentration.png',bbox_inches='tight');plt.close(fig)
    save(out/'validation.json',dict(status='PASS',scientific_verdict=None,checks=verified,
        input_receipt_sha256=sha256(root/'receipt.json'),review_script_sha256=sha256(__file__),
        old_p1_probe_sha256=sha256('/p1_ground/reference_sample_support.npz'),
        output_files={p.name:dict(sha256=sha256(p),bytes=p.stat().st_size) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(dict(regions=tables,P1_ground=ground_results),indent=2,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
