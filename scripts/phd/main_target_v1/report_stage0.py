"""Source-bound stage-0 figures, tables and progress report; no scientific verdict."""
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap,BoundaryNorm
from matplotlib.patches import Patch,Rectangle
from matplotlib.ticker import MaxNLocator
from common import *

font_manager.fontManager.addfont('/fonts/NotoSansCJK-Regular.ttc')
plt.rcParams.update({'font.family':'Noto Sans CJK JP','font.size':9,'axes.unicode_minus':False})
F=DOC/'figures';F.mkdir(exist_ok=True)
COL=['#9b9b9b','#a78bc2','#54ad80','#e6ab42','#478ac3']
LABEL=['셀 수 없음','관측 없음','일치','보존','보정']
CM=ListedColormap(COL);NORM=BoundaryNorm(np.arange(-1.5,4.5),CM.N)
SITES={'B0_b10':'B0','B173nb_b10':'B173 주변','R1rep_b10':'R1','B173_b0':'B173만'}
def read(p):return json.loads(Path(p).read_text())
def save(fig,key,title,values,note=''):
    fig.suptitle(title,fontsize=14,y=.98)
    if note:fig.text(.04,.025,note,fontsize=8)
    fig.savefig(F/(key+'.png'),dpi=220,bbox_inches='tight');plt.close(fig)
    dump(F/(key+'.json'),dict(title=title,values=values,note=note,scientific_verdict=None,source_tag='[이 발주에서 냄]'))
def csvout(name,rows):
    if not rows:return
    with (DOC/'tables'/f'{name}.csv').open('w') as f:
        w=csv.DictWriter(f,list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def main():
    c,lock=locked();t=read(OUT/'stage0_r1/T2.json');fig,axes=plt.subplots(1,2,figsize=(11,4))
    for ax,name,title in zip(axes,['main_u','sensitivity_a'],['고리 불확실도 전체 · 판단에 사용','고리 어긋남만 · 민감도']):
        fit=t['fits'][name];f=OUT/'stage0_r1'/f't2_distribution_{name}.npz'
        with np.load(f) as z:
            print('mixture fields',z.files,flush=True)
            distance=z['abs_d'];area=z['area']
        x=np.log10(abs(distance));grid=np.linspace(min(x),max(x),500)
        ax.hist(x,bins=70,weights=area,density=True,color='#ddd',label='넓이 분포')
        for i,color in enumerate(['#e6ab42','#478ac3']):
            mu=fit['means_log10'][i];sd=fit['sd_log10'][i]
            y=fit['area_weights'][i]*np.exp(-.5*((grid-mu)/sd)**2)/(sd*np.sqrt(2*np.pi))
            ax.plot(grid,y,color=color,lw=2)
        ax.axvline(np.log10(fit['T2_m']),color='black',ls='--');ax.set(title=title,xlabel='차이 |d| (m, 로그 눈금)',ylabel='넓이 밀도')
        ticks=np.array([.05,.1,.2,.5,1,2,5,10]);ax.set_xticks(np.log10(ticks),[str(x) for x in ticks]);ax.set_xlim(-1.5,1.2)
    fig.subplots_adjust(top=.80,bottom=.20,wspace=.25)
    save(fig,'r1_T2','둘째 문턱은 0.530 m로 정해졌다',t['fits'],f"전체 u: {t['fits']['main_u']['T2_m']:.6f} m · a만: {t['fits']['sensitivity_a']['T2_m']:.6f} m · 발주 참고값: 0.855 m")
    areas=[];accuracy=[];join=[]
    for name in ['experimental_r1','experimental_deferred_r1']:
        r=read(DOC/'tables'/f'{name}.json');areas+=r['areas'];accuracy+=r['accuracy'];join+=r['photo_join']
    census=read(DOC/'tables/judgment_accuracy_r1.json')['rows']
    inputs=read(DOC/'tables/input_gate_r1.json')['rows']+read(DOC/'tables/input_gate_deferred_r1.json')['rows']
    for name,rows in [('area_r1',areas),('experimental_accuracy_r1',accuracy),('judgment_accuracy_r1',census),('photo_join_r1',join),('replacement_area_r1',inputs)]:csvout(name,rows)
    for site in c['sites']+c['deferred_sites']:
        for prior in c['priors']:
            with np.load(OUT/'targets'/f'{site}_{prior}.npz') as z:d={k:z[k] for k in ['centre','region','area','in_eval','any_replaced']}
            fig=plt.figure(figsize=(11,5));ax=fig.add_subplot(121);b=fig.add_subplot(122,projection='3d');x=d['centre']
            order=np.argsort(x[:,2]);ax.scatter(x[order,0],x[order,1],c=d['region'][order],cmap=CM,norm=NORM,s=.65,rasterized=True)
            stride=max(1,len(x)//90000);ix=np.arange(0,len(x),stride)
            b.scatter(x[ix,0],x[ix,1],x[ix,2],c=d['region'][ix],cmap=CM,norm=NORM,s=.3,depthshade=False,rasterized=True)
            ax.set_aspect('equal');ax.set(title='위에서 본 영역',xlabel='동쪽 (m)',ylabel='북쪽 (m)')
            b.view_init(elev=35,azim=-60);b.set(title='비스듬히 본 영역',xlabel='동쪽 (m)',ylabel='북쪽 (m)',zlabel='높이 (m)')
            b.set_box_aspect(np.maximum(np.ptp(x,axis=0),1));fig.legend(handles=[Patch(color=cc,label=ll) for cc,ll in zip(COL,LABEL)],ncol=5,loc='lower center',bbox_to_anchor=(.5,.075))
            for axis in [b.xaxis,b.yaxis,b.zaxis]:axis.set_major_locator(MaxNLocator(3))
            fig.subplots_adjust(top=.83,bottom=.22,wspace=.1)
            rr=[r for r in areas if r['site']==site and r['prior']==prior]
            save(fig,f'r1_regions_{site}_{prior}',f'{SITES[site]} · {prior}: 학습 전에 영역별 목표를 고정했다',rr,'좌표: EPSG:25832에서 고정 원점 차감 · 모든 사전 패치 · 회색은 목표 없음')
    variants=['main','prior_only','mvs_only','T2_only','photo_only','sensitivity_a'];vko=['본 규칙','사전만','MVS만','T2만','사진만','a 민감도']
    for split in ['development','holdout','experiment']:
        source=accuracy if split=='experiment' else [r for r in census if r['split']==split]
        fig,axes=plt.subplots(1,3,figsize=(12,4),sharey=True);vals=[]
        for ax,(prior,kind,title) in zip(axes,[('ALS',1,'항공 LiDAR 지붕'),('LoD2',1,'LoD2 지붕'),('LoD2',2,'LoD2 벽')]):
            for j,(replacement,color) in enumerate([('all','#343b46'),('original','#478ac3'),('replaced','#e6ab42')]):
                percentages=[]
                for var in variants:
                    rr=[r for r in source if r['prior']==prior and r['kind']==kind and r['replacement']==replacement and r['variant']==var]
                    den=sum(r['denominator_area_m2'] for r in rr);wrong=sum(r['wrong_area_m2'] for r in rr)
                    pct=100*wrong/den if den else None;percentages.append(np.nan if pct is None else pct)
                    vals.append(dict(prior=prior,kind=kind,replacement=replacement,variant=var,denominator_area_m2=den,wrong_area_m2=wrong,wrong_pct=pct))
                ax.bar(np.arange(6)+(j-1)*.24,percentages,width=.24,color=color,label={'all':'전체','original':'원값','replaced':'대체'}[replacement])
            ax.set(title=title,xticks=np.arange(6),xticklabels=vko,ylim=(0,100));ax.tick_params(axis='x',rotation=35)
        axes[0].set_ylabel('틀린 판단 넓이 / 유의 차이 칸 0·1·2 (%)');axes[-1].legend(fontsize=8)
        fig.subplots_adjust(top=.8,bottom=.25,wspace=.15)
        save(fig,'r1_accuracy_'+split,{'development':'개발용','holdout':'확인용','experiment':'실험 지역'}[split]+': 원값과 대체 패치를 나누어 판단을 센다',vals,'대체: u 또는 σP를 같은 단위·면 종류의 중앙값으로 채움 · 분모가 없으면 막대를 그리지 않음')
    diag=read(DOC/'tables/als_status1_diagnosis_r1.json')
    for site in c['sites']+c['deferred_sites']:
        with np.load(OUT/'stage0_r1'/f'als_diagnosis_{site}.npz') as z:d={k:z[k] for k in z.files}
        row=next(r for r in diag['rows'] if r['site']==site and r['range']=='band')
        a=np.radians(70);basis=np.array([[np.cos(a),np.sin(a)],[np.sin(a),-np.cos(a)]])
        uv=d['centre'][:,:2]@basis.T;fig,axes=plt.subplots(1,2,figsize=(10,4))
        axes[0].scatter(uv[:,0],uv[:,1],s=.5,c=np.where(d['state1'],'#bd4c38','#91a6b2'),rasterized=True)
        lo,hi=np.array(row['crop_uv']);axes[0].add_patch(Rectangle(lo,*(hi-lo),fill=False,ec='black',lw=1.5));axes[0].set_aspect('equal');axes[0].set(title='빨강: 상태 1 · 사각형: 저장 점군 범위',xlabel='u (m)',ylabel='v (m)')
        m=(~d['in_eval'])&d['state1']&d['empty_column'];axes[1].hist(d['nearest_XY'][m],bins=40,color='#bd4c38');axes[1].set(title='빈 원통의 가장 가까운 저장 LiDAR 점',xlabel='수평 거리 (m)',ylabel='패치 수')
        fig.subplots_adjust(top=.8,bottom=.2,wspace=.3)
        save(fig,'r1_band_'+site,f'{SITES[site]}: 띠 패치가 저장 점군 범위를 벗어난다',row,f"빈 원통 {row['empty_column_patches']:,}개 중 {row['empty_outside_crop_by_gt_05m']:,}개가 잘라낸 범위에서 0.5 m 이상 벗어남")
    text=['# 영역별 목표 학습 보고 v1 · 개정 단계 0','',
        '판단 정확도: 개발용·확인용·실험 지역의 원값/대체 분리 표와 그림 완료.',
        '7,000회 점검: 아직 학습 전. 구현과 단위 점검이 남음.',
        '8판의 네 값: 확인 불가. 초기 6판과 B173 자체 불확실도 추가 2판의 목표만 고정됨.',
        'GS와 목표 직접 메시 비교: 확인 불가. 둘 다 아직 생성 전.',
        '단계 0 입력·T2·목표 계산 완료. `scientific_verdict: null`.','',
        '## 1. 단계 0','',f"설정 SHA-256: `{lock['config_sha256']}`. 10/31 결정으로 r0를 보존하고 r1을 잠근 뒤 재계산했다. 평가 범위만 10% 중단 기준에 넣고, 띠는 별도로 셌다. [이 발주에서 냄].",'',
        '### 둘째 문턱','',f"전체 u의 T2는 **{t['fits']['main_u']['T2_m']:.6f} m**, 큰 무리 넓이 비율은 **{100*t['fits']['main_u']['area_weights'][1]:.2f}%**이다. a만 사용한 민감도는 {t['fits']['sensitivity_a']['T2_m']:.6f} m이며, 발주 참고값 0.855 m와 다르다. 결과를 맞추기 위한 재선택은 하지 않았다.",'','![둘째 문턱](figures/r1_T2.png)','',
        '### 정밀도 출처와 대체','',c['lod2_sigma_provenance']['statement'],
        '위 문장은 사용자가 제공한 출처 설명이다. 원 추정 세션을 이번 작업에서 독립 재현했다는 뜻은 아니다.',
        '대체값은 같은 단위·같은 사전 정보·같은 면 종류의 유효한 원값 중앙값이다. 실험 단위는 평가 범위와 저장 띠를 함께 사용하고, 개발/확인용은 건물 ID별로 별도 집계했다. u=0 대체는 없다. 법선 누락에는 목표를 주지 않았다.','',
        '| 지역 | 사전 정보 | 평가 넓이 m² | 셀 수 없음 % | 대체 넓이 m² |','|---|---|---:|---:|---:|']
    for r in inputs:
        if r['range']=='eval':text.append(f"| {SITES[r['site']]} | {r['prior']} | {r['area_m2']:.2f} | {100*r['unavailable_fraction']:.4f} | {r['any_replaced_area_m2']:.2f} |")
    text+=['','지역·사전 정보·평가/띠별 대체 수와 넓이는 [전체 CSV](tables/replacement_area_r1.csv). u 대체와 σP 대체, 둘의 합집합을 각각 기록했다.','',
        '### 영역 넓이와 판단 정확도','',
        '[영역 넓이](tables/area_r1.csv), [실험 정확도](tables/experimental_accuracy_r1.csv), [개발·확인용 정확도](tables/judgment_accuracy_r1.csv). 모든 표는 원값, 대체, 전체 줄을 분리한다.',
        '틀린 비율의 분모는 유의 차이가 있는 칸 0·1·2 넓이이며, 분자는 칸 1의 보존 + 칸 2의 보정이다. 실험 지역은 S1의 고정 참값 코드를 의미에 따라 0~6으로 변환했다. 개발·확인용은 JUDGENUM의 고정 칸을 사용했다. 실험 지역의 참값은 목표 파일 저장 후 정확도 계산에만 읽었다.',
        '확인용 상세 패치 값은 외부 payload의 `holdout/`에만 있다. 공개 보고서와 그림에는 집계 수·넓이·비율만 있다.','']
    for split in ['development','holdout','experiment']:text.append(f'![판단 정확도 {split}](figures/r1_accuracy_{split}.png)')
    for site in c['sites']+c['deferred_sites']:
        for prior in c['priors']:text.append(f'![{SITES[site]} {prior} 영역](figures/r1_regions_{site}_{prior}.png)')
    text+=['','### 사진 곡선 연결','',
        '동일하게 정합된 패치 중심(1e-8 m), 면 종류, 바깥 법선(1e-6)이 유일하게 일치하는 경우에만 저장 사진 곡선을 연결했다. 전체 지역 ALS와 실험 ALS의 격자·정합 차이 때문에 B0·B173 주변·B173만은 연결된 곡선이 없다. R1 ALS도 매우 적다. 이런 곳은 사진 판단 모름이며 T2 규칙은 그대로 적용된다. LoD2는 대부분 연결된다. [대응 넓이](tables/photo_join_r1.csv).','',
        '### 띠의 항공 LiDAR 상태 1 원인','',
        '영역 파일의 `in_eval=False` 패치 집합은 저장 점군을 잘라낸 사각형 밖까지 이어진다. 아래 그림과 원통 점 수를 대조하면 상태 1 대부분이 이 범위 차이에서 발생한 빈 원통이다. 소수는 범위 안 점 부족 또는 점은 있으나 0.3 m 층에 20%가 모이지 않은 경우다. 원본 점군이나 영역을 다시 만들지 않았으며, 사용자 결정대로 중앙값 대체 후 진행한다.','']
    for site in c['sites']+c['deferred_sites']:text.append(f'![{SITES[site]} 띠 누락 원인](figures/r1_band_{site}.png)')
    text+=['','### B173만','',
        '자체 학습 영상 140장의 MVS 판 가(5,489,535점)와 자체 범위의 원본 항공 LiDAR로 UNCERT-v1과 같은 1.5 m 고리 계산을 완료했다. 주변 단위 값은 읽어 옮기지 않았다. 두 판의 단계 0도 통과했다. 초기 6판/추가 2판의 실행 순서는 유지한다.','',
        '## 2. 단계 1','', '구현·단위 점검 진행 전. 7,000회 점검 수치는 확인 불가.','',
        '## 3. 단계 2','', '학습·메시·채점 미실행. 수치를 0이나 성공으로 채우지 않았다.','',
        '## 4. 비교 방법','', '이번 실행과 같은 메시·채점 기준의 비교표는 아직 작성 전. 기존 방법 재학습은 하지 않는다.','',
        '## 5. 정성','', '영역 지도와 누락 원인 그림은 위에 있다. 대표 자리의 단면·렌더·메시 결과는 학습 전 보기를 잠근 뒤 작성한다.','',
        '## 6. 미리 정한 물음','', '판단 비교는 위 정확도 표로 제시했다. 학습의 목표 따름, 작은 판단 오류의 변화, GS 대 직접 메시, 비교 방법, B173 뜬 면은 아직 확인 불가다. 결론을 내리지 않는다.','',
        '## 7. 바꾼 것과 확인 불가','',
        'r0의 전체 넓이 기준·무대체·B173 주변 대응 점검은 보존하고, 사용자 결정 1~6으로 r1을 만들었다. LoD2 σP의 원 추정은 독립 재현하지 않았다. C++ 원통을 독립 참조 960건에 대조했으며 최대 차이는 4.44e-15였다. 목표 8판은 각각 512개를 별도 스칼라 식으로 점검하고 넓이 보존을 확인했다.',
        'B173 최초 준비 시 실행 이미지에 lxml이 없어 중단된 환경 오류는, 패치/ALS/고리를 dev 이미지, MVS 읽기를 기존 GeoGS 이미지로 분리해 해결했다. 원래 고리 코드의 0 법선 경고는 기록했으며 해당 패치는 셀 수 없음으로 남았다.','']
    (DOC/'영역별목표학습_보고_v1.md').write_text('\n'.join(text)+'\n')
    (DOC/'progress.md').write_text(f'# PHD-MAIN-TARGET-v1 진행\n\n- {stamp()}: 단계 0 개정 계산 및 독립 점검 완료.\n- 초기 6판 + 자체 불확실도 완료 B173 추가 2판의 목표 고정.\n- 학습 시작 0판, 7,000회 점검 미실행. 다음은 r19 구현·목표 지도·처음 렌더 점검.\n- 예상: 구현과 단위 점검 2~4시간, 점검 통과 뒤 본 학습 및 메시·채점 추가 8~12시간(예측).\n- scientific_verdict: null\n')
    print('STAGE0_REPORT',len('\n'.join(text)),'characters',flush=True)

if __name__=='__main__':main()
