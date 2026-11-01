"""Current r3 gate report and inspectable fixed-view diagnostics."""
import csv
import numpy as np
from common import *
from report_stage0 import plt,save,SITES

def main():
    cfg,lock=locked_r3();rows=[];reps=json.loads((CFG/'representatives_v1.json').read_text())['rows']
    entries=[('B173nb_b10','ALS'),('B173nb_b10','LoD2'),('R1rep_b10','LoD2'),('B0_b10','LoD2')]
    for site,prior in entries:
        p=OUT/'r3/preflight'/f'{site}_{prior}/initial_render.json';d=json.loads(p.read_text())
        total=sum(r['target_pixels'] for r in d['views']);valid=sum(r['rendered_target_pixels'] for r in d['views'])
        rows.append(dict(site=site,prior=prior,views=len(d['views']),target_pixels=total,valid_render_pixels=valid,
            missing_fraction=(total-valid)/total,median_m=d['pooled_median_m'],status=d['status']))
    dump(DOC/'tables/initial_render_gate_r3.json',dict(at=stamp(),rows=rows,criterion_m=.05,config_sha256=lock['config_sha256'],scientific_verdict=None))
    with (DOC/'tables/initial_render_gate_r3.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    fig,ax=plt.subplots(figsize=(9,4));values=[r['median_m']*100 for r in rows]
    ax.bar(range(4),values,color=['#54ad80' if r['status']=='PASS' else '#c25d4d' for r in rows]);ax.axhline(5,color='black',ls='--',label='5 cm 기준')
    ax.set(xticks=range(4),xticklabels=[SITES[r['site']]+' '+r['prior'] for r in rows],ylabel='깊이 절대 오차 중앙값 (cm)');ax.legend()
    for i,v in enumerate(values):ax.text(i,v+4,f'{v:.2f}',ha='center')
    ax.set_ylim(0,max(values)*1.2);fig.subplots_adjust(top=.8,bottom=.2)
    save(fig,'r3_initial_depth_gate','배경 제외 뒤에도 LoD2 세 조합은 5 cm를 넘었다',rows,'모든 학습 영상 · 사전 목표 화소 · 유효 깊이만 · 깊이 없음은 별도 기록 · 최적화 0회')
    illustrations=[];diagrows=[]
    for rep in reps:
        site=rep['site'];camera=rep['camera']['name']
        for prior in rep['priors']:
            p=OUT/'r3/preflight'/f'{site}_{prior}'/f'{camera}.npz'
            with np.load(p) as z:a={k:z[k] for k in z.files}
            good=(a['owner']>=0)&(a['target_depth']>0)&(a['render_depth']>0)
            error=np.where(good,abs(a['render_depth']-a['target_depth']),np.nan)
            fig,ax=plt.subplots(1,3,figsize=(12,4.5));ax[0].imshow(a['photo_rgb'].transpose(1,2,0));ax[0].set_title('고정한 학습 사진')
            ax[1].imshow(a['render_rgb'].transpose(1,2,0).clip(0,1));ax[1].set_title('사전 목표 가우시안만')
            im=ax[2].imshow(error,cmap='magma',vmin=0,vmax=1);ax[2].set_title('목표 깊이와 차이 (m)');fig.colorbar(im,ax=ax[2],fraction=.045,extend='max')
            for x in ax:x.axis('off')
            fig.subplots_adjust(top=.8,bottom=.2,wspace=.1)
            key=f'r3_rep{rep["id"]}_{prior}_initial';median=float(np.nanmedian(error))
            save(fig,key,f'{rep["name"]} · {prior}: 배경을 제외한 초기 깊이',dict(representative=rep['id'],site=site,prior=prior,camera=camera,median_m=median),
                f'이 영상 중앙값 {median*100:.2f} cm · 전체 영상 통과 기준과 별도 · 색 범위 0~1 m')
            illustrations.append((rep['name'],prior,key))
            diagnostic=OUT/'r3/diagnose'/f'{site}_{prior}/diagnosis.json'
            if diagnostic.exists():
                d=json.loads(diagnostic.read_text());v=next(r for r in d['rows'] if r['representative']==rep['id']);samples=v['individual_owner_samples']
                single=[abs(s['owner_only_m']-s['target_m']) for s in samples if s['owner_only_m'] is not None]
                combined=[abs(s['combined_m']-s['target_m']) for s in samples if s['owner_only_m'] is not None]
                row=dict(site=site,prior=prior,representative=rep['id'],samples=len(single),owner_only_median_m=float(np.median(single)),
                    owner_only_max_m=float(np.max(single)),combined_same_samples_median_m=float(np.median(combined)),
                    seed_target_max_error_m=d['seed_target_max_error_m'],normal_max_error=d['quaternion_normal_max_error'])
                diagrows.append(row)
    dump(DOC/'tables/prior_overlap_diagnosis_r3.json',dict(rows=diagrows,diagnostic_only=True,scientific_verdict=None))
    failed=[r for r in rows if r['status']!='PASS']
    status=dict(at=stamp(),status='STOP_STAGE1_PRIOR_ONLY_DEPTH_5CM' if failed else 'PASS_STAGE1_PREFLIGHT',rows=rows,
        criterion_m=.05,training_steps=0,pilot_7000='NOT_RUN',initial_background_policy='baseline uncapped nearest-neighbour, no isolated removal',
        user_decision='2026-11-01 re-stop items 1-5',config_sha256=lock['config_sha256'],scientific_verdict=None)
    dump(OUT/'r3/stage1_status.json',status);dump(DOC/'tables/stage1_status_r3.json',status)
    text=['# 11/1 r3: 배경을 제외한 3.5 재검사','',
        '**LoD2 세 조합이 5 cm를 넘어 학습 전 중단했다. 최적화 0회이며, 7,000회 결과는 없다.**','',
        '사용자 결정대로 배경 크기 상한·외톨이 제거를 쓰지 않았다. 통과 판단은 사전 패치 목표에 심은 가우시안만 렌더한 깊이로 바꿨다. r2 판단·목표·지도·초기 사전 크기는 그대로다. r3 설정은 첫 계산 전 15:39:20, 검사 코드는 15:43:30에 잠갔다.','',
        '| 조합 | 영상 수 | 깊이 오차 중앙값 (cm) | 깊이 없음 (%) | 5 cm |','|---|---:|---:|---:|---|']
    for r in rows:text.append(f"| {SITES[r['site']]} {r['prior']} | {r['views']} | {r['median_m']*100:.4f} | {r['missing_fraction']*100:.5f} | {'통과' if r['status']=='PASS' else '미충족'} |")
    text+=['','모든 학습 영상의 사전 패치 목표 화소 중 양의 유한 렌더 깊이가 있는 화소를 합쳐 중앙값을 구했다. 깊이 없음은 성공에 포함하지 않았다. 항공 LiDAR의 43.44% 깊이 없음도 별도로 드러내며 추가 멈춤 기준으로 만들지 않는다.','',
        '![배경 제외 점검](figures/r3_initial_depth_gate.png)','',
        '## 원인 확인','',
        'B173 날개 고정 영상은 LoD2 중앙값 4.26 cm로 통과하지만, 같은 단위의 전체 203장 중앙값은 13.61 cm다. 좋은 한 장만으로 전체 검사를 바꾸지 않았다.','',
        '목표 지도는 가장 가까운 패치 원반의 깊이이고, 기준선 렌더 깊이는 여러 반투명 가우시안의 기여를 합친 기대 깊이(`depth_ratio=0`)다. 배경을 제외해도 앞뒤의 지붕·벽이 함께 기여한다. 아래 개별 패치 검사로 씨앗 위치 오차와 겹침의 영향을 구분했다.','',
        '| 고정 자리 | 표본 수 | 그 화소의 패치만 렌더한 오차 중앙값 / 최댓값 (mm) | 같은 표본의 전체 사전 렌더 오차 중앙값 (cm) |','|---|---:|---:|---:|']
    for r in diagrows:text.append(f"| {SITES[r['site']]} {r['prior']} 자리 {r['representative']} | {r['samples']} | {r['owner_only_median_m']*1000:.5f} / {r['owner_only_max_m']*1000:.5f} | {r['combined_same_samples_median_m']*100:.3f} |")
    text+=['','표본은 고정 영상의 유효 화소를 순서대로 24개 등간격 선택했다. 이 분해는 원인 확인용이며 새 통과 기준이 아니다. 씨앗 위치·법선은 목표와 float32 반올림 수준으로 맞았다. 깊이 종류 변경, 지붕·벽 분리, 개별 패치 검사로의 기준 변경을 학습에 적용하지 않았다.','']
    for name,prior,key in illustrations:text +=[f'![{name} {prior}](figures/{key}.png)','']
    text+=['## 남은 상태','',
        '배경 포함 r2 렌더는 참고값으로 마무리하며, 초기 크기 1 m 초과 배경의 수와 상위 열 개를 별도 표로 낸다. 7,000회 자손 잔존·크기·불투명도와 뜬 면 지도는 학습 전 중단으로 확인 불가다. 이 항목들을 0 또는 성공으로 적지 않는다.','',
        '재개에는 3.5 깊이 비교 방식에 대한 후속 결정이 필요하다. 사용자 결정 4의 “통과하면” 조건을 충족하지 못했기 때문이다. 배경의 크기 규칙, 밀도 제어 일정, 정밀도와 5 cm 기준은 바꾸지 않았다.','',
        '`scientific_verdict: null`']
    (DOC/'단계1_r3_재점검.md').write_text('\n'.join(text)+'\n')
    print('R3_GATE_REPORT',status['status'],flush=True)

if __name__=='__main__':main()
