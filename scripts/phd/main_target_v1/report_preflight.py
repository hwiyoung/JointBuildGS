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
    cfg,lock=training_locked();reps=read(CFG/'representatives_v1.json')['rows'];summaries=[];maprows=[];seedrows=[]
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            root=OUT/'stage1'/f'{site}_{prior}';index=read(root/'maps/index.json');seed=read(root/'seed_receipt.json')
            vals=[r['height_error_median_m'] for r in index['views'].values() if r['height_error_median_m'] is not None]
            maprows.append(dict(site=site,prior=prior,views=len(index['views']),max_view_height_error_median_m=max(vals),
                status='PASS' if max(vals)<=.01 else 'FAIL',background_u_replaced=True))
            seedrows.append({k:seed[k] for k in ['site','prior','original','kept','prior_kept','background_kept','background_u_replaced','target_patches_without_baseline_seed']})
            p=OUT/'preflight'/f'{site}_{prior}'/'initial_render.json'
            if p.exists():
                r=read(p);summaries.append({k:r[k] for k in ['site','prior','status','pooled_pixels','pooled_median_m','prior_pooled_pixels','prior_pooled_median_m','criterion_m','optimization_steps']})
    dump(DOC/'tables/stage1_maps.json',maprows);csvout('stage1_maps',maprows)
    dump(DOC/'tables/stage1_seeds.json',seedrows);csvout('stage1_seeds',seedrows)
    dump(DOC/'tables/stage1_initial_render.json',summaries);csvout('stage1_initial_render',summaries)
    fig,ax=plt.subplots(1,2,figsize=(11,4));names=[SITES[r['site']]+' '+r['prior'] for r in summaries]
    for a,key,title in zip(ax,['pooled_median_m','prior_pooled_median_m'],['목표가 있는 전체 화소','사전 패치 목표 화소만']):
        values=[r[key] for r in summaries];a.bar(np.arange(len(values)),values,color='#478ac3');a.axhline(.05,color='#c34b35',ls='--')
        a.set(xticks=np.arange(len(values)),xticklabels=names,ylabel='깊이 절대 오차 중앙값 (m)',title=title)
        a.tick_params(axis='x',rotation=22)
        for i,v in enumerate(values):a.text(i,v+.3,f'{v:.2f}',ha='center',fontsize=9)
    fig.subplots_adjust(top=.8,bottom=.25,wspace=.25)
    save(fig,'stage1_initial_depth_gate','초기 렌더 깊이는 5 cm 기준을 통과하지 못했다',summaries,'학습 0회 · 점선: 발주문 3.5의 0.05 m · 깊이 없음은 별도 기록')
    fig,ax=plt.subplots(1,2,figsize=(11,4));names=[SITES[r['site']]+' '+r['prior'] for r in maprows]
    ax[0].bar(np.arange(8),[r['max_view_height_error_median_m']*1000 for r in maprows],color='#54ad80')
    ax[0].set(xticks=np.arange(8),xticklabels=names,ylabel='영상별 표본 오차 중앙값의 최댓값 (mm)',title='목표 지도: 8판 모두 10 mm 이내');ax[0].tick_params(axis='x',rotation=40)
    ax[1].bar(np.arange(8),[r['prior_kept'] for r in seedrows],color='#e6ab42',label='사전 목표 씨앗')
    ax[1].bar(np.arange(8),[r['background_kept'] for r in seedrows],bottom=[r['prior_kept'] for r in seedrows],color='#478ac3',label='기존 영상 씨앗')
    ax[1].set(xticks=np.arange(8),xticklabels=names,ylabel='가우시안 수',title='패치별 기존 씨앗 수 유지');ax[1].tick_params(axis='x',rotation=40);ax[1].legend(fontsize=8)
    fig.subplots_adjust(top=.79,bottom=.32,wspace=.3)
    save(fig,'stage1_maps_seeds','목표 지도 계산과 초기 씨앗 준비는 8판에서 끝났다',dict(maps=maprows,seeds=seedrows),'항공 LiDAR에는 기존 씨앗 수가 0인 패치가 있음 · 배경 불확실도 대체 수는 표에 별도 기록')
    colors=['#a78bc2','#54ad80','#e6ab42','#478ac3','#c8c2b4'];cm=ListedColormap(colors);norm=BoundaryNorm(np.arange(-.5,5.5),5)
    repstats=[]
    for rep in reps:
        site=rep['site'];name=rep['camera']['name']
        for prior in rep['priors']:
            root=OUT/'preflight'/f'{site}_{prior}';initial=read(root/'initial_render.json');view=next(v for v in initial['views'] if v['camera']==name)
            with np.load(root/f'{name}.npz') as z:r={k:z[k] for k in z.files}
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in z.files}
            with np.load(OUT/'stage0_r1/evaluation'/f'{site}_{prior}.npz') as z:e={k:z[k] for k in z.files}
            with np.load(OUT/'stage1'/f'{site}_{prior}'/'seeds.npz') as z:s={k:z[k] for k in z.files}
            owner=r['owner'];has=owner>=0;region=np.full(owner.shape,np.nan);region[has]=d['region'][owner[has]]
            region[(~has)&np.isfinite(r['target_depth'])]=4
            h=np.full(owner.shape,np.nan);h[has]=d['h'][owner[has]]
            key=f'stage1_rep{rep["id"]}_{prior}'
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
            idx=read(OUT/'stage1'/f'{site}_{prior}'/'maps/index.json')['views'][name]
            full=next(q for q in read(DOC/'tables/stage1_representative_pixels.json')['rows'] if q['representative']==rep['id'] and q['prior']==prior)
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
    dump(DOC/'tables/stage1_representatives.json',repstats)
    # Preserve the completed stage-0 text, replace only the pending stage text.
    report=DOC/'영역별목표학습_보고_v1.md';text=(DOC/'revisions/r1/영역별목표학습_보고_v1.md').read_text();text=text[:text.index('## 2. 단계 1')]
    text=text.replace('0.3 m 층','0.3 m 구간')
    text=text.replace('# 영역별 목표 학습 보고 v1 · 개정 단계 0','# 영역별 목표 학습 보고 v1 · 초기 렌더 점검 중단')
    text=text.replace('7,000회 점검: 아직 학습 전. 구현과 단위 점검이 남음.','7,000회 점검: 미실행. 학습 전 3.5의 초기 렌더 깊이 5 cm 기준 미충족.')
    text=text.replace('단계 0 입력·T2·목표 계산 완료. `scientific_verdict: null`.','단계 0 통과, 목표 지도·묶기·상속 통과. 최적화 0회. `scientific_verdict: null`.')
    text=text.replace('## 1. 단계 0','## 2. 단계 0');text=text.replace('\n\n판단 정확도:','\n\n## 1. 현재 결과\n\n판단 정확도:',1)
    text+='''## 3. 단계 1: 학습 전 중단

발주문 3.5의 **초기 렌더 깊이 오차 중앙값 5 cm 이하**를 충족하지 못했다. 7,000회 건강 점검 실패가 아니다. 학습과 본 채점은 시작하지 않았다. 묶기는 폭 밖 중심을 끝으로 옮기고 폭 안·접선 성분을 유지했다. 실제 GaussianModel의 복제·분할·제거 뒤 부모 목표 인덱스도 유지됐다.

| 판 | 전체 목표 화소 오차 중앙값 m | 사전 패치 화소만 m | 기준 |
|---|---:|---:|---|
'''
    for r in summaries:text+=f'| {SITES[r["site"]]} {r["prior"]} | {r["pooled_median_m"]:.6f} | {r["prior_pooled_median_m"]:.6f} | 0.05 m 이하, 미충족 |\n'
    text+='''
![초기 깊이](figures/stage1_initial_depth_gate.png)

전체 목표 화소는 학습 영상 전체에서 양의 유효 깊이가 있는 화소를 합쳐 센 값이다. 렌더 깊이가 없는 비율은 영상별 원표에 따로 남겼고 성공으로 세지 않았다. 사전 패치만 따로 보아도 기준 미충족이다.

![지도와 씨앗](figures/stage1_maps_seeds.png)

목표 지도는 8판 전부 완료했다. 모든 학습 영상에서 고정 간격으로 뽑은 약 2,000개 화소의 h 복원 오차 중앙값이 1 cm 이내다. 대표 자리 넷의 5개 보기·사전 정보 조합은 원반 화소 전체를 별도 역행렬 계산으로 검사했고 모두 1 cm 기준을 통과했다. [전체 화소 검산](tables/stage1_representative_pixels.json)에 화소 수와 오차를 기록했다. 대표 자리의 정확한 단면과 학습 영상은 렌더 전에 representatives_v1.json으로 잠갔다. 판단이 틀린 보존 자리는 LoD2 지붕 칸 1의 최대 연결 넓이로 정했으며 표시 전용이다.

바탕은 r18의 현재 실제 파일 109개다. 마지막 추적 커밋은 f614090ab5444090182890c6c43505a3a4e5af8f이며, 추적하지 않은 상속 파일도 fork_r19_base.json의 개별 해시로 고정했다. 새 판 r19에서 train.py에 목표 초기화·깊이 손실·갱신 뒤 묶기·기록 연결을 넣고 jbgs_target.py를 추가했다. 원 r18은 변경하지 않았다. 렌더러도 기존 기준선의 diff_surfel_rasterization을 유지했다.

깊이 손실은 기존 MVS 항과 같은 화소 전체 수 분모의 가중 절대 차이와 λ=0.05다. 지도는 CPU 고정 메모리에 두고 한 영상만 GPU로 옮긴다. --jbgs_target 기본값은 off다. 새 경로는 옛 판단·사진 보정·다중 보기 모듈을 끄고 목표를 고정한다. 실제 최적화 실행은 0회이므로 30,000회 동작 검증을 마쳤다는 뜻은 아니다.

### 초기 오차의 확인된 원인과 범위

카메라 행렬 차이는 0이고, 목표에 놓인 씨앗 위치 차이는 float32 수준이다. 법선을 회전 행렬로 복원한 값도 일치한다. 카메라 깊이 50 m인 합성 평면의 렌더 중앙값 오차는 0.001 m 미만이었다.

B173 주변에서 기존 영상 씨앗 중 [135.327545, 72.262688, 21.422825]의 가우시안 크기는 42.538944 m였다. 이 한 원반만 렌더해도 고정 영상의 목표 화소 전체를 덮으며 약 11.33 m 깊이를 낸다. 항공 LiDAR 고정 영상에서 전체 초기 장면의 사전 패치 화소 오차 중앙값은 4.855858 m다. 진단용으로 배경 씨앗을 모두 제외하면 유효 깊이가 남은 사전 화소의 중앙값은 0.039948 m로 줄지만, 일부 화소에 깊이가 없어지고 평가 분모도 달라진다. 따라서 이 진단은 5 cm 기준 통과로 인정하지 않았다. 배경 씨앗을 제외한 초기화로 학습하지 않았다.

기존 기준선의 영상 씨앗 파일은 MVS 작업공간의 sparse/0/points3D.ply에 있는 SfM 희소점이다. 조밀한 MVS 깊이와 같은 점 집합이 아니다. 이번 구현은 '기존 기준선과 같이'를 따라 그 씨앗과 크기를 유지했다. 초기 배경 씨앗을 신뢰도 통과 MVS 점으로 바꾸거나, 큰 씨앗을 제거·크기 제한하거나, 깊이 정의·5 cm 기준을 바꾸는 일은 아직 적용하지 않았다. 이 중 어떤 변경을 허용할지 결정이 필요하다.

## 4. 단계 2

8판 최적화 0회, 7,000·30,000회 모델 0개. 네 값, 칸/영역별 채점, 뜬 면, 면 없음, 판단 맞음·틀림 결과, 목표 직접 메시 비교는 **확인 불가**다. 초기 6판과 추가 B173 2판의 목표만 준비됐다. B173 자체 고리 계산 완료가 학습 완료를 뜻하지 않는다.

## 5. 비교 방법

기존 결과를 다시 학습하지 않았다. 이번 학습 결과와 같은 최종 메시·채점 비교표는 확인 불가다. 메모리 보류 CDGS도 확인 불가를 유지한다.

## 6. 대표 자리의 학습 전 증거

아래는 잠근 같은 보기의 실제 사진, 목표 h·영역, 초기 렌더 깊이와 단면이다. 결과 메시와 7,000·30,000회 장면이 없으므로 해당 그림을 만들거나 추정하지 않았다. B0는 앞 작업의 평가 중심을 통과하는 사전 지붕 주축으로 단면을 고정했다. 약 15 cm라는 발주 기대값을 자리 선택이나 통과 기준에 쓰지 않았다.

'''
    for rep in reps:
        for prior in rep['priors']:
            for suffix in ['target','initial','section']:
                text+=f'![{rep["name"]} {prior} {suffix}](figures/stage1_rep{rep["id"]}_{prior}_{suffix}.png)\n\n'
    text+='''## 7. 미리 정한 물음과 관측

판단이 한 자료만 믿을 때보다 틀린 넓이를 줄이는지는 단계 0의 원값/대체별 비교 줄에 수치로 제시했다. 학습의 목표 따름, 작은 판단 오류의 변화, GS와 직접 메시의 비교, 다른 방법보다 나은지, B173의 뜬 면 변화는 학습 전 중단으로 확인 불가다. 과학적 결론은 내리지 않는다.

## 8. 바뀐 것, 검증 범위와 자원

사용자 10/31 결정 1~6을 r0에 덧붙여 r1로 잠갔다. 단계 1의 씨앗·지도·손실 구현 선택은 첫 계산 전에 별도 잠갔으며, 단계 0 설정은 revisions/r1에 보존했다. 법선 누락은 대체하지 않았고 u=0도 사용하지 않았다. 배경의 u 결측 대체는 기존 패치의 대체 넓이와 구분해 씨앗 수로 기록했다.

단계 0 원통 독립 비교 960건의 최대 차이는 4.44e-15였다. 목표 8판 각각 512개를 독립 스칼라 식으로 확인하고 넓이 보존을 점검했다. 목표 지도와 초기 렌더는 같은 소스 카메라를 사용했다. 단위 점검·좌표 검사·합성 평면 검사는 기술 검증이며, 사용자 시각 수용이나 과학적 결론이 아니다.

CPU 고리·지도 계산은 Docker 안에서 4코어와 최대 22 GiB 제한으로 실행했다. GPU 초기 렌더와 진단은 RTX 3090, 컨테이너당 24 GiB 메모리 제한으로 실행했고 역전파·최적화는 하지 않았다. 각 실행 시간은 실행 영수증에 있다. 환경·스키마·호출 오류와 수정은 issues.md에 남겼다. 다음 학습의 소요 시간은 이번 실패 상태에서 확정하지 않는다.

scientific_verdict: null
'''
    assert len(text)<20000;report.write_text(text.rstrip()+'\n')
    status=dict(at=stamp(),status='STOP_STAGE1_INITIAL_RENDER_DEPTH',gate='order 3.5 initial rendered depth median <= 0.05m',
        stage0='PASS',unit_clamp_inheritance='PASS',maps='PASS',training_steps=0,pilot_7000='NOT_RUN',main_training='NOT_RUN',
        rows=summaries,scientific_verdict=None)
    dump(OUT/'stage1_status.json',status);dump(DOC/'tables/stage1_status.json',status)
    (DOC/'progress.md').write_text('# PHD-MAIN-TARGET-v1 진행\n\n'+f'- {stamp()}: 단계 0 통과, 단계 1 초기 렌더 깊이 5 cm 기준 미충족으로 학습 전 중단.\n'+
        '- 목표 8판, 목표 지도 8판, B173 자체 불확실도 완료. 묶기·상속 단위 점검 통과.\n- 학습 0회, 7,000회 점검과 본 채점은 확인 불가.\n- 배경 초기 씨앗 변경 또는 초기 기준 변경에 대한 사용자 결정 필요.\n- scientific_verdict: null\n')
    print('PREFLIGHT_REPORT',len(text),'characters',flush=True)

if __name__=='__main__':main()
