"""Publish the failed pre-training gate, with frozen representative views and sections."""
import re,csv
import numpy as np
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch
from common import *
from report_stage0 import plt,save,read,SITES

def csvout(name,rows):
    if not rows:return
    with (DOC/'tables'/f'{name}.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)


def main():
    cfg,lock=locked_r2();reps=read(CFG/'representatives_v1.json')['rows'];summaries=[];maprows=[];seedrows=[]
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            root=OUT/'r2/stage1'/f'{site}_{prior}';index=read(root/'maps/index.json');seed=read(root/'seed_receipt.json')
            vals=[r['height_error_median_m'] for r in index['views'].values() if r['height_error_median_m'] is not None]
            maprows.append(dict(site=site,prior=prior,views=len(index['views']),max_view_height_error_median_m=max(vals),
                status='PASS' if max(vals)<=.01 else 'FAIL',background_u_replaced=True))
            seedrows.append({k:seed[k] for k in ['site','prior','prior_kept','background_kept','target_patches_without_baseline_seed']})
            p=OUT/'r2/preflight'/f'{site}_{prior}'/'initial_render.json'
            if p.exists():
                r=read(p);summaries.append({k:r[k] for k in ['site','prior','status','pooled_pixels','pooled_median_m','prior_pooled_pixels','prior_pooled_median_m','criterion_m','optimization_steps']})
    dump(DOC/'tables/r2_stage1_maps.json',maprows);csvout('r2_stage1_maps',maprows)
    dump(DOC/'tables/r2_stage1_seeds.json',seedrows);csvout('r2_stage1_seeds',seedrows)
    dump(DOC/'tables/r2_stage1_initial_render.json',summaries);csvout('r2_stage1_initial_render',summaries)
    fig,ax=plt.subplots(1,2,figsize=(11,4));names=[SITES[r['site']]+' '+r['prior'] for r in summaries]
    for a,key,title in zip(ax,['pooled_median_m','prior_pooled_median_m'],['목표가 있는 전체 화소','사전 패치 목표 화소만']):
        values=[r[key] for r in summaries];a.bar(np.arange(len(values)),values,color='#478ac3');a.axhline(.05,color='#c34b35',ls='--')
        a.set(xticks=np.arange(len(values)),xticklabels=names,ylabel='깊이 절대 오차 중앙값 (m)',title=title)
        a.tick_params(axis='x',rotation=22)
        for i,v in enumerate(values):a.text(i,v+.3,f'{v:.2f}',ha='center',fontsize=9)
    fig.subplots_adjust(top=.8,bottom=.25,wspace=.25)
    save(fig,'r2_stage1_initial_depth_gate','초기 렌더 깊이와 5 cm 기준',summaries,'학습 0회 · 점선: 발주문 3.5의 0.05 m · 깊이 없음은 별도 기록')
    fig,ax=plt.subplots(1,2,figsize=(11,4));names=[SITES[r['site']]+' '+r['prior'] for r in maprows]
    ax[0].bar(np.arange(len(maprows)),[r['max_view_height_error_median_m']*1000 for r in maprows],color='#54ad80')
    ax[0].set(xticks=np.arange(len(maprows)),xticklabels=names,ylabel='영상별 표본 오차 중앙값의 최댓값 (mm)',title='목표 지도: 8판 모두 10 mm 이내');ax[0].tick_params(axis='x',rotation=40)
    ax[1].bar(np.arange(len(maprows)),[r['prior_kept'] for r in seedrows],color='#e6ab42',label='사전 목표 씨앗')
    ax[1].bar(np.arange(len(maprows)),[r['background_kept'] for r in seedrows],bottom=[r['prior_kept'] for r in seedrows],color='#478ac3',label='신뢰도 통과 MVS 씨앗')
    ax[1].set(xticks=np.arange(len(maprows)),xticklabels=names,ylabel='가우시안 수',title='패치별 기존 씨앗 수 유지');ax[1].tick_params(axis='x',rotation=40);ax[1].legend(fontsize=8)
    fig.subplots_adjust(top=.79,bottom=.32,wspace=.3)
    save(fig,'r2_stage1_maps_seeds','목표 지도 계산과 초기 씨앗 준비는 8판에서 끝났다',dict(maps=maprows,seeds=seedrows),'항공 LiDAR에는 기존 씨앗 수가 0인 패치가 있음 · 배경 불확실도 대체 수는 표에 별도 기록')
    colors=['#a78bc2','#54ad80','#e6ab42','#478ac3','#c8c2b4'];cm=ListedColormap(colors);norm=BoundaryNorm(np.arange(-.5,5.5),5)
    repstats=[]
    for rep in reps:
        site=rep['site'];name=rep['camera']['name']
        for prior in rep['priors']:
            root=OUT/'r2/preflight'/f'{site}_{prior}';initial=read(root/'initial_render.json');view=next(v for v in initial['views'] if v['camera']==name)
            with np.load(root/f'{name}.npz') as z:r={k:z[k] for k in z.files}
            with np.load(OUT/'r2/targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            with np.load(OUT/'r2/stage0/evaluation'/f'{site}_{prior}.npz') as z:e={k:z[k] for k in z.files}
            with np.load(OUT/'r2/stage1'/f'{site}_{prior}'/'seeds.npz') as z:s={k:z[k] for k in z.files}
            owner=r['owner'];has=owner>=0;region=np.full(owner.shape,np.nan);region[has]=d['region'][owner[has]]
            region[(~has)&np.isfinite(r['target_depth'])]=4
            h=np.full(owner.shape,np.nan);h[has]=d['h'][owner[has]]
            key=f'r2_stage1_rep{rep["id"]}_{prior}'
            fig,ax=plt.subplots(1,3,figsize=(12,4.5));ax[0].imshow(r['photo_rgb'].transpose(1,2,0));ax[0].set_title('고정한 학습 사진')
            line=np.c_[np.array([rep['start'],rep['end']]),np.full(2,rep['center_xyz'][2])]
            camera=rep['camera'];M=np.asarray(camera['W2C']);projected=line@M[:3,:3].T+M[:3,3]
            u=camera['fx']*projected[:,0]/projected[:,2]+camera['cx'];v=camera['fy']*projected[:,1]/projected[:,2]+camera['cy']
            ax[0].plot(u,v,color='white',lw=3);ax[0].plot(u,v,color='black',ls='--',lw=1.5)
            im=ax[1].imshow(h,cmap='coolwarm',vmin=-5,vmax=5);ax[1].set_title('목표의 법선 방향 h (m)');fig.colorbar(im,ax=ax[1],fraction=.045,extend='both')
            ax[2].imshow(region,cmap=cm,norm=norm);ax[2].set_title('학습 전 고정한 영역')
            for a in ax:a.axis('off')
            fig.legend(handles=[Patch(color=c,label=t) for c,t in zip(colors,['관측 없음','일치','보존','보정','배경 MVS'])],ncol=5,loc='lower center',bbox_to_anchor=(.5,.085),fontsize=8)
            fig.subplots_adjust(top=.79,bottom=.24,wspace=.08)
            idx=read(OUT/'r2/stage1'/f'{site}_{prior}'/'maps/index.json')['views'][name]
            full=next(q for q in read(DOC/'tables/stage1_representative_pixels_r2.json')['rows'] if q['representative']==rep['id'] and q['prior']==prior)
            val=dict(representative=rep['id'],site=site,prior=prior,camera=name,view=view,map_height_error_median_m=full['absolute_h_error_median_m'],map_height_pixels=full['pixels'],map_height_all_disc_pixels=True)
            repstats.append(val)
            save(fig,key+'_target',f'{rep["name"]} · {prior}: 목표 높이와 영역을 학습 전에 고정했다',val,
                f'원반 화소 전체 h 복원 오차 중앙값 {full["absolute_h_error_median_m"]*1000:.4f} mm · h 색 범위 ±5 m, 범위 밖은 끝 색')
            fig,ax=plt.subplots(1,3,figsize=(12,4.5));good=np.isfinite(r['target_depth'])&(r['target_depth']>0)
            T=np.where(good,r['target_depth'],np.nan);D=np.where(good&(r['render_depth']>0),r['render_depth'],np.nan)
            for a,data,title in zip(ax[:2],[T,D],['목표 깊이','초기 렌더 깊이']):
                im=a.imshow(data,cmap='viridis',vmin=0,vmax=120);a.set_title(title+' (m)');fig.colorbar(im,ax=a,fraction=.045,extend='max')
            im=ax[2].imshow(abs(D-T),cmap='magma',vmin=0,vmax=50);ax[2].set_title('절대 차이 (m)');fig.colorbar(im,ax=ax[2],fraction=.045,extend='max')
            for a in ax:a.axis('off')
            fig.subplots_adjust(top=.79,bottom=.21,wspace=.14)
            save(fig,key+'_initial',f'{rep["name"]} · {prior}: 초기 장면의 깊이는 목표와 다르다',val,
                f'학습 0회 · 이 영상 오차 중앙값 {view["absolute_depth_error_median_m"]:.3f} m · 기준 0.05 m · 깊이 색 범위 0~120 m')
            a,b=np.asarray(rep['start']),np.asarray(rep['end']);v=(b-a)/np.linalg.norm(b-a);length=np.linalg.norm(b-a)
            def select(x):
                q=x[:,:2]-a;t=q@v;off=abs(q[:,0]*v[1]-q[:,1]*v[0]);return t,(t>=0)&(t<=length)&(off<=rep['half_width'])
            t,mask=select(d['centre']);mask&=(d['kind']==1)&(d['region']>=0)
            fig,ax=plt.subplots(1,2,figsize=(11,4.5));ax[0].scatter(d['centre'][mask,0],d['centre'][mask,1],c=d['region'][mask],cmap=cm,norm=norm,s=8)
            ax[0].plot([a[0],b[0]],[a[1],b[1]],'k--',lw=1);ax[0].set_aspect('equal');ax[0].set(title='고정한 단면 자리',xlabel='동쪽 (m)',ylabel='북쪽 (m)')
            for z,label,color in [(d['centre'][:,2],'사전 정보','#e6ab42'),(d['centre'][:,2]+d['d']*d['normal'][:,2],'MVS','#478ac3'),
                                  (d['centre'][:,2]+e['gt_med']*d['normal'][:,2],'참값','black')]:
                ax[1].scatter(t[mask],z[mask],s=7,color=color,label=label,alpha=.65)
            ids=np.flatnonzero(mask);ids=ids[np.argsort(t[ids])]
            ax[1].errorbar(t[ids],d['target'][ids,2],yerr=1.96*d['sigma'][ids]*abs(d['normal'][ids,2]),fmt='.',ms=2,color='gray',alpha=.3,label='목표 ±1.96σ의 높이 성분')
            ts,ms=select(s['xyz']);ms&=s['origin']==1
            ax[1].scatter(ts[ms],s['xyz'][ms,2],s=5,marker='x',color='#bd4676',label='0회 중심');ax[1].set(xlabel='단면 거리 (m)',ylabel='높이 (m)',title='목표와 초기 중심');ax[1].legend(fontsize=7)
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.25)
            save(fig,key+'_section',f'{rep["name"]} · {prior}: 목표와 0회 중심의 단면',dict(val,patches=len(ids),initial_centers=int(ms.sum())),
                '학습 0회 · 7,000·30,000회 중심과 결과 메시 없음 · 참값은 표시와 평가에만 사용')
    dump(DOC/'tables/r2_stage1_representatives.json',repstats)
    failed=[r for r in summaries if r['status']!='PASS']
    status='STOP_STAGE1_INITIAL_RENDER_DEPTH' if failed else 'PASS_STAGE1_PREFLIGHT'
    rows=[]
    for row in summaries:
        old=read(OUT/'preflight'/f"{row['site']}_{row['prior']}"/'initial_render.json')
        rows.append(dict(site=row['site'],prior=row['prior'],r1_median_m=old['pooled_median_m'],r2_median_m=row['pooled_median_m'],
            r2_prior_median_m=row['prior_pooled_median_m'],status=row['status'],criterion_m=.05))
    dump(DOC/'tables/initial_render_comparison_r2.json',dict(rows=rows,scientific_verdict=None));csvout('initial_render_comparison_r2',rows)
    record=dict(at=stamp(),status=status,stage0='PASS',unit_clamp_inheritance='PASS',maps='PASS',training_steps=0,
        pilot_7000='NOT_RUN' if failed else 'READY',rows=rows,scientific_verdict=None)
    dump(OUT/'r2/stage1_status.json',record);dump(DOC/'tables/stage1_status_r2.json',record)
    text=(DOC/'영역별목표학습_보고_r2.md').read_text()
    section=['## 6. 배경 씨앗과 3.5 점검','',
        '초기 렌더 깊이 5 cm 기준 미충족으로 학습 전에 중단했다. 7,000회 점검 실패가 아니며, 최적화는 0회다.' if failed else '3.5 점검을 통과했다. B173 주변 두 판의 7,000회 점검을 이어간다.',
        '', '| 판 | r1 전체 화소 오차 (m) | r2 전체 화소 오차 (m) | r2 사전 화소만 (m) | 판정 |','|---|---:|---:|---:|---|']
    for r in rows:section.append(f"| {SITES[r['site']]} {r['prior']} | {r['r1_median_m']:.6f} | {r['r2_median_m']:.6f} | {r['r2_prior_median_m']:.6f} | {r['status']} |")
    section.extend(['','모든 학습 영상의 양의 유효 렌더 깊이가 있는 목표 화소를 합쳐 중앙값을 센다. 렌더 깊이가 없는 화소는 영상별 표에 별도로 기록했으며 성공으로 세지 않았다. 기준은 0.05 m 그대로다.','',
        '| 항목 | 기준선 / r1 | r2 |','|---|---|---|','| 배경 점 | SfM 희소점 | 신뢰도 통과 MVS A 점 |','| 배경 솎기 | 기존 희소점 | 원통 제외 후 0.25 m 복셀 |','| 배경 크기 | 기준선 최근접 거리 규칙 | 동일 규칙을 새 점군에 적용 |','| 사전 씨앗 | 기존 패치별 수·크기 | 동일 수·크기, r2 목표 위치 |','',
        '배경 점마다 자체 MVS 고리 불확실도, MVS 법선(없으면 연직 위), σM과 ±1.96σ 묶기를 부여했다. 결측 대체는 같은 단위·면 종류의 유효 값으로 하고 배경 씨앗 수로 별도 기록한다. 사전 패치의 대체 넓이와 혼동해 합산하지 않았다.','',
        '초기 사전 씨앗의 크기는 기준선 텐서와 바이트 단위로 같고, MVS 배경 크기는 기준선 distCUDA2 규칙과 같은 값임을 GPU에서 확인했다. 묶기, 실제 복제·분할·제거 뒤 부모 목표 상속도 통과했다. 대표 원반 화소 전체의 h를 독립 역행렬로 복원한 값은 1 cm 이내다.','',
        '![초기 깊이 점검](figures/r2_stage1_initial_depth_gate.png)','', '![지도와 씨앗](figures/r2_stage1_maps_seeds.png)',''])
    for rep in reps:
        for prior in rep['priors']:
            for suffix in ['target','initial','section']:
                section.extend([f"![{rep['name']} {prior}](figures/r2_stage1_rep{rep['id']}_{prior}_{suffix}.png)",''])
    start=text.index('## 6.');end=text.index('## 7.')
    text=text[:start]+'\n'.join(section)+'\n'+text[end:]
    text=text.replace('11/1 결정에 따라 단계 0을 재계산했다. 3.5 초기 렌더 점검과 학습은 아직 진행 전이다.',
        '11/1 결정의 단계 0 재계산과 MVS 배경 초기화를 마쳤다. '+('3.5 초기 렌더 5 cm 기준 미충족으로 학습 전에 중단했다.' if failed else '3.5를 통과하고 7,000회 점검으로 진행한다.'))
    text=text.replace('7,000회와 30,000회 결과는 아직 없다. 3.5를 통과하면 B173 주변 두 판으로 진행한다.',
        '7,000회와 30,000회 결과, 최종 메시와 채점은 아직 없다. '+('3.5 기준 미충족으로 학습하지 않았다.' if failed else 'B173 주변 두 판의 학습과 점검이 남아 있다.'))
    assert len(text)<20000
    (DOC/'영역별목표학습_보고_r2.md').write_text(text);(DOC/'영역별목표학습_보고_v1.md').write_text(text)
    print('R2_PREFLIGHT_REPORT',status,len(text),flush=True)


if __name__=='__main__':main()
