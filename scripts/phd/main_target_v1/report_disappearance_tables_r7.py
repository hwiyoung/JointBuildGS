"""Aggregate-only stage-0 tables, area/fallback figures, and exact decision provenance."""
import numpy as np
from common import *
from report_stage0 import plt,save,SITES
def main():
    rows=json.loads((DOC/'tables/disappearance_areas_r7.json').read_text())['rows']
    for split in ['development','holdout']:
        for prior in ['ALS','LoD2']:rows+=json.loads((DOC/'tables'/f'disappearance_{split}_{prior}_r7.json').read_text())['rows']
    rows.sort(key=lambda r:(["experiment","development","holdout"].index(r['split']),list(SITES).index(r['site']) if r['site'] in SITES else 0,r['prior'],r['range'],r['kind'],r['replacement']))
    text=['# r7 단계 0: 사라짐 판단','',
    '사용자의 2026-11-01 후속 결정에 따라, 각 유효 MVS 화소를 3차원으로 되돌린 뒤 같은 단위·사전 정보의 단계 0 패치 중심 중 1 m 안의 최근접 패치를 찾았다. 그 패치의 원값 u를 사용하고, 이웃이 없거나 대체 u이면 같은 단위·사전 정보의 원값 u 중앙값을 썼다. 동률은 원 패치 순서를 따른다. 실험 지역의 단위는 잠긴 site이며, 개발용·확인용은 기존 불확실도 대체에 사용한 건물 단위다.','',
    '3×3 창의 유효 깊이 중앙값과 각 화소 σ_M 중앙값을 사용했다. σ_M=√(u²+0.0275²), m=1.96√(σ_M²+σ_P²)이며 σ_P는 검사 대상 패치의 값이다. 학습 영상에서 뚫고 봄 2장 이상이면서 증거 영상의 절반을 넘을 때만 사라짐이다. 검사 대상 패치 u 방식은 참고로만 계산했다.','',
    '두 설정은 첫 계산 전 19:21:44 KST에 잠갔다. 단계 0 설정 SHA-256 `'+sha(CFG/'target_v1.r7.stage0.json')+'`; 학습 설정 SHA-256 `'+sha(CFG/'target_v1.r7.json')+'`. 참값은 이 판단 계산에서 읽지 않았고, 저장된 판단의 정확도를 세는 데만 사용했다. 사라짐 외 영역의 판단·목표·폭은 그대로다.','',
    '확인용은 집계 수·넓이·비율만 공개했다. 상세 패치와 단위 식별자는 봉인 폴더에 남긴다. 참값 면을 측정할 수 없는 곳은 맞게 지운 넓이로 세지 않는다.','']
    for split,word in [('experiment','실험 지역'),('development','개발용'),('holdout','확인용')]:
        for scope,scopeword in [('eval','평가 범위'),('band','둘레 띠')]:
            rr=[r for r in rows if r['split']==split and r['range']==scope and r['replacement']=='all' and r['old_unobserved_count']]
            if not rr:continue
            text +=[f'## {word} · {scopeword}','', '| 단위 | 사전 정보 | 면 | 이전 관측 없음(m²) | 사라짐(m²) | 남은 관측 없음(m²) | 패치 u 참고(m²) | 중앙값 대체 화소 비율 |','|---|---|---|---:|---:|---:|---:|---:|']
            labels=[]
            for r in rr:
                site=SITES.get(r['site'],'집계');kind='지붕' if r['kind']==1 else '벽';labels.append(site+' '+r['prior']+' '+kind)
                f=r['fallback_fraction'];text.append(f'| {site} | {r["prior"]} | {kind} | {r["old_unobserved_area_m2"]:.3f} | {r["disappeared_area_m2"]:.3f} | {r["remaining_unobserved_area_m2"]:.3f} | {r["reference_disappeared_area_m2"]:.3f} | '+(f'{100*f:.2f}%' if f is not None else '해당 없음')+' |')
            fig,axes=plt.subplots(1,2,figsize=(12,max(4,len(rr)*.28)));y=np.arange(len(rr));gone=[r['disappeared_area_m2'] for r in rr];keep=[r['remaining_unobserved_area_m2'] for r in rr]
            axes[0].barh(y,gone,color='#db5b5b',label='사라짐');axes[0].barh(y,keep,left=gone,color='#a78bc2',label='남은 관측 없음');axes[0].set(yticks=y,yticklabels=labels,xlabel='넓이 (m²)');axes[0].legend(fontsize=7)
            axes[1].barh(y,[100*r['fallback_fraction'] if r['fallback_fraction'] is not None else np.nan for r in rr],color='#888888');axes[1].set(yticks=y,yticklabels=labels,xlim=(0,100),xlabel='중앙값으로 대체한 유효 화소 표본 (%)');fig.subplots_adjust(top=.83,bottom=.17,left=.16,wspace=.65)
            key=f'r7_disappearance_area_{split}_{scope}';save(fig,key,f'{word} · {scopeword}: 사라짐 넓이와 u 대체 비율',rr,'분모: 관측 없음 패치를 검사한 유효 3×3 화소 표본 · 같은 화소가 여러 검사 창에 들면 각각 셈')
            text +=['',f'![넓이와 대체 비율](figures/{key}.png)','']
    accuracy=json.loads((DOC/'tables/disappearance_accuracy_r7.json').read_text())['rows']
    text +=['## 사라짐으로 옮긴 넓이의 참값 점검','', '확인 불가에는 해당 위치의 참값 면 측정값 부재가 포함된다. 특히 없어진 벽은 기존 면 찾기에서 참값이 없을 수 있으므로, 이 표만으로 삭제 정확도가 높다고 결론 내리지 않는다.','', '| 집합 | 사전 정보 | 사라짐(m²) | 맞게 지움(m²) | 잘못 지움(m²) | 참값 확인 불가(m²) |','|---|---|---:|---:|---:|---:|']
    for split,site,label in [('experiment','B173nb_b10','B173 주변'),('development','aggregate','개발용'),('holdout','aggregate','확인용')]:
        for prior in ['ALS','LoD2']:
            rr=[r for r in accuracy if r['split']==split and r['site']==site and r['prior']==prior and r['range']=='eval' and r['replacement']=='all' and r['policy']=='r7']
            values=[sum(r[k] for r in rr) for k in ['correctly_deleted_area_m2','wrongly_deleted_area_m2','deleted_truth_unavailable_area_m2']]
            text.append('| '+label+' | '+prior+' | '+' | '.join(f'{v:.3f}' for v in [sum(values)]+values)+' |')
    text +=['','값은 이 기록을 본 뒤 바꾸지 않았다. 개발용 항공 LiDAR에서는 사라짐 42.503 m² 중 39.559 m²가 잘못 지움으로 측정됐다. 단계 0 정확도는 기록이며, 발주된 7,000회 건강·기하 기준으로 진행 여부를 판단한다.','']
    text +=['## 정확도와 단면','', '원값·대체 별 정확도 및 모두 지킴·모두 지움·패치 u 참고 줄은 `tables/disappearance_accuracy_r7.json`에 기록했다. 아래 그림의 회색은 참값 확인 불가다.','']
    for split in ['development','holdout','experiment']:
        for rep in ['all','original','replaced']:text +=[f'![판단 정확도](figures/r7_disappear_accuracy_{split}_{rep}.png)','']
    text +=['![LoD2 영역 전후](figures/r7_B173nb_LoD2_regions.png)','']
    for prior in ['ALS','LoD2']:text +=[f'![B173 날개](figures/r7_stage0_wing_{prior}.png)','']
    text +=['`scientific_verdict: null`',stamp()];(DOC/'단계0_사라짐_점검_r7.md').write_text('\n'.join(text)+'\n');dump(DOC/'tables/disappearance_all_areas_r7.json',dict(rows=rows,scientific_verdict=None));print('STAGE0_TABLES_R7_COMPLETE',flush=True)
if __name__=='__main__':main()
