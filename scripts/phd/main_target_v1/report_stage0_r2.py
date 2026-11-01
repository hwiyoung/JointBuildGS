"""Paired r1/r2 evidence, historical eligibility reconstruction and fixed B173 sections."""
import numpy as np
from common import *
from report_stage0 import plt,save,read,csvout,SITES,COL,LABEL,CM,NORM
from matplotlib.patches import Patch


def main():
    cfg,lock=locked_r2();audit=read(DOC/'tables/unobserved_input_audit_r2.json')
    a1=read(DOC/'tables/experimental_r1.json');a1d=read(DOC/'tables/experimental_deferred_r1.json')
    a2=read(DOC/'tables/experimental_r2.json');a2d=read(DOC/'tables/experimental_deferred_r2.json')
    old=read(DOC/'tables/T2_historical_reference_r2.json');t2=read(OUT/'r2/stage0/T2.json')
    accuracies=[dict(r,revision=rev) for rev,rs in [('r1',a1['accuracy']+a1d['accuracy']),('r2',a2['accuracy']+a2d['accuracy'])] for r in rs]
    # Build all area rows explicitly, retaining replacement and evaluation/band strata.
    areas=[dict(r,revision=rev) for rev,rs in [('r1',a1['areas']+a1d['areas']),('r2',a2['areas']+a2d['areas'])] for r in rs]
    census=[dict(r,revision=rev) for rev in ['r1','r2'] for r in read(DOC/f'tables/judgment_accuracy_{rev}.json')['rows']]
    reference=[dict(r,revision='historical_reference') for r in old['rows']]
    for name,rows in [('area_comparison_r2',areas),('accuracy_comparison_r2',accuracies+census+reference),('unobserved_input_audit_r2',audit['rows']),('historical_accuracy_r2',old['rows'])]:
        dump(DOC/f'tables/{name}.json',dict(rows=rows,scientific_verdict=None));csvout(name,rows)
    reasons=['r1_unobserved','raw_h5_positive','face_not_found_h5','selected_under_4_h5','length_h5_empty_h10_observed','still_empty_h10']
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            key=f'{site}_{prior}'
            with np.load(OUT/'r2/input_audit'/f'{key}.npz') as z:d={k:z[k] for k in z.files}
            colors=['#dddddd','#777777','#caa663','#bc5144','#9169b2','#3482b5']
            names=['기존 관측/셀 수 없음','5 m에서 빈 원통','점 1~3개','면 찾기 실패','선택 점 부족','5→10 m로 관측 확보']
            tag=np.zeros(len(d['kind']),int);tag[d['r1_unobserved']&(d['h5'][:,6]==0)]=1;tag[d['raw_h5_1_to_3']]=2
            tag[d['face_not_found_h5']]=3;tag[d['selected_under_4_h5']]=4;tag[d['length_h5_empty_h10_observed']]=5
            fig,axes=plt.subplots(1,2,figsize=(11,5))
            for ax,(name,scope) in zip(axes,[('평가 범위',d['in_eval']),('둘레 띠',~d['in_eval'])]):
                for k in range(6):
                    m=scope&(tag==k);ax.scatter(d['centre'][m,0],d['centre'][m,1],s=.55 if k==0 else 1.7,c=colors[k],rasterized=True)
                ax.set(title=name,xlabel='동쪽 (m)',ylabel='북쪽 (m)');ax.set_aspect('equal')
            fig.legend(handles=[Patch(color=c,label=n) for c,n in zip(colors,names)],ncol=3,loc='lower center',bbox_to_anchor=(.5,.02),fontsize=8)
            fig.subplots_adjust(top=.82,bottom=.22)
            save(fig,f'r2_unobserved_{key}',f'{SITES[site]} · {prior}: 관측 없음의 원인',
                 [r for r in audit['rows'] if r['site']==site and r['prior']==prior],
                 '10 m 비교는 원인 진단용 · 실제 벽 원통은 5 m 유지 · 1~3점은 점 부족으로 따로 기록')
            with np.load(OUT/'r2/targets'/f'{key}.npz') as z:new={k:z[k] for k in ['centre','region','in_eval']}
            fig=plt.figure(figsize=(11,5));ax=fig.add_subplot(121);bx=fig.add_subplot(122,projection='3d');x=new['centre'];order=np.argsort(x[:,2])
            ax.scatter(x[order,0],x[order,1],c=new['region'][order],cmap=CM,norm=NORM,s=.5,rasterized=True);ax.set_aspect('equal')
            ix=np.arange(0,len(x),max(1,len(x)//90000));bx.scatter(x[ix,0],x[ix,1],x[ix,2],c=new['region'][ix],cmap=CM,norm=NORM,s=.3,depthshade=False)
            bx.view_init(elev=35,azim=-60);bx.set_box_aspect(np.maximum(np.ptp(x,axis=0),1));ax.set_title('위에서 본 영역');bx.set_title('비스듬히 본 영역')
            fig.legend(handles=[Patch(color=c,label=n) for c,n in zip(COL,LABEL)],ncol=5,loc='lower center',bbox_to_anchor=(.5,.05));fig.subplots_adjust(top=.83,bottom=.2)
            save(fig,f'r2_regions_{key}',f'{SITES[site]} · {prior}: r2 고정 영역',[r for r in areas if r['site']==site and r['prior']==prior and r['revision']=='r2'])
    fits=[('앞 셈 · 참고',old['historical']['fit']),('r1',old['r1']['main_u']),('r2 · 판단에 사용',t2['fits']['main_u'])]
    fig,axes=plt.subplots(1,3,figsize=(12,4));grid=np.linspace(-2,1,500)
    hd,ha=[],[]
    for f in sorted((JN/'core_points').glob('*__ALS.npz')):
        with np.load(f) as z:
            mask=(z['kind']==1)&(z['judgment_after']==1);hd.extend(np.abs(z['d_mean_cm'][mask])/100);ha.extend(z['area'][mask])
    distributions=[(np.asarray(hd),np.asarray(ha))]
    for folder in ['stage0_r1','r2/stage0']:
        with np.load(OUT/folder/'t2_distribution_main_u.npz') as z:distributions.append((z['abs_d'],z['area']))
    for ax,(name,fit),(distance,area) in zip(axes,fits,distributions):
        edges=np.logspace(-2,1,71);hist,_=np.histogram(distance,bins=edges,weights=area)
        # Density is per log10 metre, matching the Gaussian curves on the horizontal log axis.
        ax.stairs(hist/(np.sum(area)*np.diff(np.log10(edges))),edges,fill=True,color='#dddddd')
        for i,col in enumerate(['#d59d3c','#438bb6']):
            mu=fit['means_log10'][i];sd=fit['sd_log10'][i];y=fit['area_weights'][i]*np.exp(-.5*((grid-mu)/sd)**2)/(sd*np.sqrt(2*np.pi));ax.plot(10**grid,y,c=col)
        ax.axvline(fit['T2_m'],color='black',ls='--');ax.set(xscale='log',xlabel='차이 |d| (m)',title=f"{name}\nT2 {fit['T2_m']:.3f} m")
    fig.subplots_adjust(top=.76,bottom=.2);save(fig,'r2_T2_comparison','앞 셈과 현재 셈은 유의 차이 모집단이 다르다',dict(fits=fits,historical_area_m2=old['historical']['area_m2']),
        '앞 셈: 참값 유래 최소 넓이 제거 후 · r1/r2: 제거 없이 전체 u · r2는 지붕 10 m와 면 찾기 보완')
    for split in ['development','holdout','experiment']:
        source=accuracies if split=='experiment' else [r for r in census if r['split']==split]
        fig,axes=plt.subplots(1,3,figsize=(12,4));data=[]
        for ax,(prior,kind,title) in zip(axes,[('ALS',1,'항공 LiDAR 지붕'),('LoD2',1,'LoD2 지붕'),('LoD2',2,'LoD2 벽')]):
            for j,(rev,col) in enumerate([('r1','#a5a5a5'),('r2','#438bb6')]):
                vals=[]
                for rep in ['all','original','replaced']:
                    rr=[r for r in source if r['revision']==rev and r['prior']==prior and r['kind']==kind and r['replacement']==rep and r['variant']=='main']
                    den=sum(r['denominator_area_m2'] for r in rr);wrong=sum(r['wrong_area_m2'] for r in rr);v=100*wrong/den if den else None
                    vals.append(np.nan if v is None else v);data.append(dict(revision=rev,prior=prior,kind=kind,replacement=rep,denominator_area_m2=den,wrong_area_m2=wrong,wrong_pct=v))
                ax.bar(np.arange(3)+(j-.5)*.3,vals,width=.3,color=col,label=rev)
            ax.set(title=title,xticks=[0,1,2],xticklabels=['전체','원값','대체'],ylim=(0,100));ax.legend()
        axes[0].set_ylabel('틀린 판단 넓이 비율 (%)');fig.subplots_adjust(top=.8,bottom=.2)
        save(fig,'r2_accuracy_'+split,{'development':'개발용','holdout':'확인용','experiment':'실험 지역'}[split]+': r1과 r2 판단 정확도',data,
            '유의 차이 중 참값 칸 0·1·2의 넓이를 분모로 사용 · 값이 없으면 막대 없음')
    rep=read(CFG/'representatives_v1.json')['rows'][0];a,b=np.array(rep['start']),np.array(rep['end']);v=(b-a)/np.linalg.norm(b-a)
    for prior in ['ALS','LoD2']:
        key=f"B173nb_b10_{prior}"
        with np.load(OUT/'targets'/f'{key}.npz') as z:r1={k:z[k] for k in z.files}
        with np.load(OUT/'r2/targets'/f'{key}.npz') as z:r2={k:z[k] for k in z.files}
        q=r2['centre'][:,:2]-a;t=q@v;off=abs(q[:,0]*v[1]-q[:,1]*v[0]);m=(t>=0)&(t<=np.linalg.norm(b-a))&(off<=rep['half_width'])&(r2['kind']==1)
        with np.load(OUT/'r2/stage0/evaluation'/f'{key}.npz') as z:gt=z['gt_med']
        fig,axes=plt.subplots(1,2,figsize=(12,4.5))
        for ax,(rev,d) in zip(axes,[('r1',r1),('r2',r2)]):
            for z,name,color in [(d['centre'][:,2],'사전 정보','#d59d3c'),(d['centre'][:,2]+d['d']*d['normal'][:,2],'MVS','#438bb6'),(d['centre'][:,2]+gt*d['normal'][:,2],'참값','black'),(d['target'][:,2],'목표','#c04d79')]:
                good=m&np.isfinite(z);ax.scatter(t[good],z[good],s=6,label=name,c=color,alpha=.7)
            ax.set(title=rev,xlabel='단면 거리 (m)',ylabel='높이 (m)');ax.legend(fontsize=8)
        lo=min(axes[0].get_ylim()[0],axes[1].get_ylim()[0]);hi=max(axes[0].get_ylim()[1],axes[1].get_ylim()[1]);[ax.set_ylim(lo,hi) for ax in axes]
        fig.subplots_adjust(top=.8,bottom=.2)
        save(fig,f'r2_B173_wing_{prior}',f'B173 날개 · {prior}: 같은 자리의 r1·r2 목표',
            dict(representative=rep['id'],patches=int(m.sum()),section_start=a.tolist(),section_end=b.tolist(),r1_unobserved=int((m&(r1['region']==0)).sum()),r2_unobserved=int((m&(r2['region']==0)).sum())),
            '고정한 단면 위치와 폭 유지 · 참값은 표시와 평가에만 사용 · 판단 이후 값을 조정하지 않음')
    lines=['# 영역별 목표 학습 보고 v1 · r2 단계 0','',
           '11/1 결정에 따라 단계 0을 재계산했다. 3.5 초기 렌더 점검과 학습은 아직 진행 전이다. `scientific_verdict: null`.','',
           '## 1. 설정과 원인','',f"r2 설정 SHA-256: `{lock['config_sha256']}`. 원통 길이는 지붕 10 m, 벽 5 m. 원래 면에서 선택한 점이 4개 이상이면 면 찾기를 바꾸지 않았다. 4개 미만이면서 원통 안에는 4개 이상인 경우에만, 같은 0.30 m 층 가운데 점이 가장 많은 층을 고르고(동률이면 바깥층) 그 층 중심의 ±1 m에서 센다. 전체 점의 20% 조건이 여러 면·분산된 점에서 실패하는 것을 보완한다. 보완 후에도 4개 미만이면 관측 없음이다.",'',
           'B173 주변 항공 LiDAR 평가 지붕에서 5 m 원통이 비고 10 m에서 관측이 확보되는 넓이는 553.782 m²다. 모든 지역·사전 정보·평가 범위/띠·면 종류의 수와 넓이는 `tables/unobserved_input_audit_r2.csv`에 있다.','',
           '## 2. 둘째 문턱','',
           '| 방식 | 유의 차이 넓이 (m²) | T2 (m) | 용도 |','|---|---:|---:|---|',
           f"| 앞 셈 | {old['historical']['area_m2']:.3f} | {old['historical']['fit']['T2_m']:.6f} | 참고만 |",
           f"| r1 전체 u | {old['r1']['main_u']['eligible_area_m2']:.3f} | {old['r1']['main_u']['T2_m']:.6f} | 이전 판단 |",
           f"| r2 전체 u | {t2['fits']['main_u']['eligible_area_m2']:.3f} | {t2['fits']['main_u']['T2_m']:.6f} | 이번 판단 |",'',
           '앞 셈은 JUDGENUM의 `judgment_after == 1`을 썼다. 이는 참값 유래 최소 넓이 제거를 거친 결과다. 제거 전 기존 a 검정의 유의 차이는 4,388.156 m²이며, 결측 중앙값 대체를 적용한 r1 a 민감도는 4,637.676 m², 전체 u를 쓰는 r1은 2,951.612 m²다. 따라서 924와 2,952의 차이는 불확실도만의 차이가 아니다. 이번 판단에는 최소 넓이 제거를 넣지 않는다. 앞 방식의 판단 정확도는 `tables/historical_accuracy_r2.csv`에 T2만과 고정 사진 판단을 더한 판으로 별도 기록했다.','',
           '![T2 비교](figures/r2_T2_comparison.png)','',
           '## 3. 영역 넓이와 관측 없음 지도','',
           'r1·r2의 영역 넓이는 `tables/area_comparison_r2.csv`에 지역·사전 정보·평가 범위/띠·지붕/벽·원값/대체별로 기록했다. 셀 수 없음 10% 기준의 분모는 평가 범위 넓이만이다.','']
    for site in cfg['sites']+cfg['deferred_sites']:
        for prior in cfg['priors']:
            lines.extend([f'![관측 없음 원인](figures/r2_unobserved_{site}_{prior}.png)',f'![영역 지도](figures/r2_regions_{site}_{prior}.png)',''])
    lines.extend(['## 4. 판단 정확도','', '모든 비교 줄과 대체 패치 별도 줄은 `tables/accuracy_comparison_r2.csv`에 있다. 확인용 상세 값은 외부 작업 폴더 `holdout/r2/`에만 저장한다.','',
        '| 구분 | 앞 셈 참고: 틀린 넓이 비율 | r1 | r2 |','|---|---:|---:|---:|'])
    for split in ['development','holdout']:
        for prior,kind,title in [('ALS',1,'항공 LiDAR 지붕'),('LoD2',1,'LoD2 지붕'),('LoD2',2,'LoD2 벽')]:
            values=[]
            for rev,variant in [('historical_reference','historical_T2_and_fixed_DL_photo'),('r1','main'),('r2','main')]:
                rr=[r for r in census+reference if r['revision']==rev and r['split']==split and r['prior']==prior and r['kind']==kind and r['replacement']=='all' and r['variant']==variant]
                den=sum(r['denominator_area_m2'] for r in rr);wrong=sum(r['wrong_area_m2'] for r in rr)
                values.append(f'{100*wrong/den:.2f}%' if den else '확인 불가')
            lines.append('| '+('개발용' if split=='development' else '확인용')+' '+title+' | '+' | '.join(values)+' |')
    lines.extend(['','앞 셈은 최소 넓이 제거 이후의 모집단이며, r1·r2와 분모가 다르다. 위 참고 행은 역사적 계산을 설명하는 값이며 이번 판단에 적용하지 않았다.',''])
    for split in ['development','holdout','experiment']:lines.extend([f'![판단 정확도](figures/r2_accuracy_{split}.png)',''])
    lines.extend(['## 5. B173 날개 단면','', '![항공 LiDAR 단면](figures/r2_B173_wing_ALS.png)','', '![LoD2 단면](figures/r2_B173_wing_LoD2.png)','',
        '## 6. 배경 씨앗과 3.5 점검','',
        '| 항목 | 기준선 / r1 | r2 |','|---|---|---|','| 배경 점 | SfM 희소점 | 신뢰도 마스크를 통과한 MVS A 점 |','| 배경 간격 | 기존 희소점 | 사전 패치 원통 제외 후 0.25 m 복셀 솎기 |','| 배경 초기 크기 | 기준선 거리 규칙 | 같은 거리 규칙을 새 초기 점군에 적용 |','| 사전 정보 씨앗 | 기존 수·크기 | 기존 수·크기 유지, r2 목표로 이동 |','| 초기 렌더 기준 | 중앙값 5 cm | 5 cm 유지 |','',
        '배경은 점 자체를 목표로 하고 MVS 법선(없으면 연직 위), σM, ±1.96σ 묶기를 사용한다. 현재 씨앗 준비 중이며 초기 렌더 통과로 표시하지 않는다.','',
        '## 7. 학습·메시·채점','', '7,000회와 30,000회 결과는 아직 없다. 3.5를 통과하면 B173 주변 두 판으로 진행한다.','',
        '## 8. 출처와 검증','',
        'LoD2 σP 출처: 2026-10-26 방법 재정리 세션이 참값 없이 구한 값이다. 정밀한 MVS(u 5 cm 이하)와 LoD2의 차 분포를 두 무리로 맞추고, 좁은 무리의 폭에서 MVS 흔들림을 뺐다. 참값으로 한 같은 셈(평지붕 17.1 cm)은 점검에만 썼다. 이 출처 설명은 사용자 제공이며 원 적합을 독립 재실행한 것은 아니다.','',
        '항공 LiDAR 띠의 상태 1 진단은 r1에서 완료했다. 빈 원통 대부분이 저장된 LiDAR 점군의 잘라낸 범위 밖에 있었다. `tables/als_status1_diagnosis_r1.json`과 `figures/r1_band_*.png`에 수·넓이·지도를 보존했다. r2는 같은 불확실도 입력과 대체 표시를 사용하며 이 원인으로 멈추지 않는다.','',
        '원통 보완은 독립 전수 원통 마스크와 층 탐색으로 만든 120개 합성 검증을 통과했다. r1 파일은 보존했다. 현재 결과는 [이 발주에서 냄]이며 과학적 판정은 하지 않는다.',''])
    (DOC/'영역별목표학습_보고_r2.md').write_text('\n'.join(lines))
    dump(OUT/'r2/stage0/report_complete.json',dict(at=stamp(),status='STAGE0_REPORT_COMPLETE',scientific_verdict=None))
    print('R2_REPORT_COMPLETE',flush=True)


if __name__=='__main__':main()
