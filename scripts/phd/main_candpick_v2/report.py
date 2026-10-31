"""Requested report order; measurements only, no causal or scientific conclusion."""
from cp2_common import *
from plot_figures import LABELS,SITES,REP_NAMES

def pct(v):return '확인 불가' if v is None else f'{100*v:.1f}'
def num(v):return '확인 불가' if v is None else f'{v:.2f}'
def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])+'\n'

def main(write=True):
    cfg=config();opacity=json.loads((DOC/'tables/opacity_outcomes.json').read_text())['rows']
    depth=json.loads((DOC/'tables/depth_outcomes.json').read_text())['rows']
    op={(r['unit'],r['variant'],r['start'],r['group'],r['side']):r for r in opacity}
    dp={(r['unit'],r['variant'],r['start'],r['group'],r['side']):r for r in depth}
    get=lambda mapping,key,field:mapping.get(key,{}).get(field)
    photo={p:json.loads((OUT/'photo_dl'/f'{p}_selection.json').read_text())['groups'] for p in ['ALS','LoD2']}
    timing=json.loads((DOC/'tables/training_status.json').read_text())['rows']
    training_seconds=sum(r.get('seconds',0) for r in timing if r['arm'].startswith('cp2_'))
    depth_seconds=sum(json.loads(p.read_text())['seconds'] for p in (OUT/'depth').glob('*/complete.json'))
    photo_seconds=json.loads((OUT/'photo_dl/complete.json').read_text())['seconds']
    first=[]
    for v in 'abcd':
        values=[]
        for u in UNITS:
            pair=[]
            for s in ['equal','right']:
                k=(u,v,s,'a','front');pair.append(pct(get(op,k,'right_darker_fraction'))+'/'+pct(get(dp,k,'right_fraction')))
            values.append(SITES[u]+': '+' · '.join(pair))
        first.append(LABELS[v]+' — '+'; '.join(values)+' %.')
    first.append('사진 다시 셈 틀린 넓이: 항공 LiDAR 지붕 '+num(photo['ALS']['roof']['summary']['wrong_area_m2'])+
        ', LoD2 지붕 '+num(photo['LoD2']['roof']['summary']['wrong_area_m2'])+', LoD2 벽 '+num(photo['LoD2']['wall']['summary']['wrong_area_m2'])+
        f' m². 확인 불가: 모양 학습 2판. 학습 합계 {training_seconds/60:.1f}분, 깊이 합계 {depth_seconds/60:.1f}분, 사진 다시 셈 {photo_seconds/60:.1f}분.')
    text='\n'.join(first)+'\n\n# 후보 고르기 원인 확인 보고 v1\n\n'
    text+='앞 다섯 줄은 묶음 가·맞는 후보가 앞인 자리다. 각 경우의 순서는 **출발 같음 · 출발 맞음**, 각 값은 **맞는 쪽이 0.2 넘게 진한 넓이 / 렌더 깊이가 맞는 높이에 잡힌 넓이**다. 새 값은 모두 **[이 발주에서 냄]**이다.\n\n'
    text+=f'작업: PHD-MAIN-CANDPICK-v2. 갱신 {now()}. 설계 24판 중 **22판 학습 완료 / 2판 단위 점검 중단**, 깊이 채점 **28판 완료(새 22 + v1 기준 6)**. `scientific_verdict: null`.\n\n'
    text+='## 일 1 · 후보 상태\n\n'
    text+='아래는 묶음 가다. 전체 묶음 가·나·다, 앞뒤 전체·앞·뒤의 원래 넓이와 비율은 [전체 불투명도 표](tables/opacity_outcomes.csv)에 있다. v1은 다시 학습하지 않았다.\n\n'
    rows=[]
    for u in UNITS:
        for s in ['equal','right']:
            for side in ['front','back']:
                for v in ['v1','a','b','c','d']:
                    k=(u,v,s,'a',side);r=op.get(k,{})
                    rows.append([SITES[u],'같음' if s=='equal' else '맞음','앞' if side=='front' else '뒤',LABELS[v],
                        *[pct(r.get(x)) for x in ['right_only_fraction','wrong_only_fraction','both_fraction','neither_fraction','right_darker_fraction','wrong_darker_fraction']],
                        num(r.get('combined_coverage_median'))])
    text+=mdtable(['경우','출발','맞는 후보','판','맞음만 %','틀림만 %','둘 다 %','둘 다 아님 %','맞는 쪽 진함 %','틀린 쪽 진함 %','함께 덮음 중앙값'],rows)+'\n'
    text+='판 가의 지운 후보는 존재하지 않으므로, 두 후보 비교 표에서만 불투명도 0으로 표시했다. 학습·렌더에는 넣지 않았다. 함께 덮음은 `1−(1−맞는 쪽)(1−틀린 쪽)`이며 실제 화소 불투명도와 별개의 후보 요약값이다.\n\n'
    for u in UNITS:
        for s in ['equal','right']:text+=f'![{SITES[u]} {s}](figures/curves_{u}_{s}.png)\n\n'
    text+='## 일 2 · 렌더 깊이\n\n'
    text+='v1의 사진별 후보 마스크 합집합과 기여 화소가 모든 보기에서 일치했다. 13,214점 모두 점별로 화소 수가 가장 많은 학습 사진 3장을 학습 전에 고정했다. 동률은 사진 이름 순서다. 각 점이 실제로 기여한 화소의 세 보기 값을 모아 화소마다 같은 무게로 중앙값을 구했다.\n\n'
    text+='GeoGS의 메시용 `depth_ratio=0`은 광선과 원반이 만나는 깊이를 가시성 가중 평균하고 불투명도 합으로 나눈다. 깊이에는 GeoGS 원본의 불투명도 상한 0.99, 0.2m보다 가까운 기여 제외, 투과도 0.0001 미만 직전 종료를 적용했다. 기여를 제외한 뒤 가중치를 다시 누적하며 뒤의 원반도 계속 확인한다. 투영 원반·화소 중심·타일 순서는 고정한 gsplat 1.4 값이다. 색 렌더와 학습은 v1의 gsplat 설정 그대로다. 유효 기여가 없거나 유한하지 않은 계산은 확인 불가다.\n\n'
    text+='첫 깊이 구현은 가까운 기여가 하나라도 있으면 화소 전체를 비우고 gsplat의 상한 0.999를 사용한 오류가 있었다. 학습 완료 뒤 원본 코드와 대조해 고쳤다. [수정 시각·규칙·해시](tables/depth_correction_r1.json)를 다시 잠그고 28판 모두 재채점했다. 학습 상태·사진 선택·문턱은 바꾸지 않았다. 첫 채점 28판과 렌더는 전달 묶음의 `payload/revisions/depth_r0/`에 오류 이력으로 보존하며 주 표에는 수정 결과만 쓴다. 작은 예제 4개와 실제 384화소의 별도 CPU 비교를 통과했고 최대 차이는 0.032mm였다.\n\n'
    text+='맞음·틀림은 원래 후보 높이에서 항공 LiDAR ±12.66cm, LoD2 ±20cm다. 판 다도 원래 후보 높이와 비교한다. 세 보기 중 유효 깊이 화소가 없는 보기가 있으면 그 점은 확인 불가다. 표는 묶음 가이며 [전체 깊이 표](tables/depth_outcomes.csv)에 모든 묶음이 있다.\n\n'
    rows=[]
    for u in UNITS:
        for s in ['equal','right']:
            for v in ['v1','a','b','c','d']:
                row=[SITES[u],'같음' if s=='equal' else '맞음',LABELS[v]]
                for side in ['front','back']:
                    r=dp.get((u,v,s,'a',side),{})
                    row.append(' / '.join(pct(r.get(k+'_fraction')) for k in ['right','wrong','between_outside','unavailable']))
                rows.append(row)
    text+=mdtable(['경우','출발','판','앞: 맞음/틀림/사이·바깥/확인 불가 %','뒤: 맞음/틀림/사이·바깥/확인 불가 %'],rows)+'\n'
    text+='## 정성 · 같은 자리의 단면과 렌더\n\n'
    text+='모두 출발 맞음이다. 단면은 0·500·1,000·끝 회, 렌더는 학습 전에 고른 같은 보기와 같은 확대 범위다. 판 다는 실제 이동한 원반 중심 네 개를 각각 표시한다. 낙엽 지붕은 v1의 대체 자리 표시를 유지한다. 색 보정과 생성 영상은 쓰지 않았다.\n\n'
    for r in cfg['representatives']:
        if r['selection']:
            text+=f'### {REP_NAMES[r["id"]]}\n\n![단면](figures/section_{r["id"]}.png)\n\n![렌더](figures/render_{r["id"]}.png)\n\n'
    text+='## 일 3 · 사진 검사 다시 셈\n\n'
    text+='저장 곡선과 원래 봉우리 표시를 그대로 사용했다. 점에 속한 JUDGENUM 핵심점 패치들의 유한한 검출 한계 중앙값으로 범위만 바꿨다. 해당 값이 하나도 없는 점은 확인 불가다. 지붕과 LoD2 벽은 같은 형식의 저장 곡선이 있었다. 항공 LiDAR 벽의 사진 곡선은 없어 별도 사진 결과를 만들지 않았다.\n\n'
    coverage=json.loads((DOC/'tables/photo_census_coverage.json').read_text())['rows']
    text+='전체 저장 사진 점·패치의 새 판단은 외부 `photo_dl/points`, `photo_dl/patches`에 있다. 아래 고르기 셈은 JUDGENUM의 원래 건물·패치 범위를 유지한다. 전체 사진 범위의 넓이 표는 [전체 판단 넓이](tables/photo_census_judgment_areas.csv)에 따로 둔다.\n\n'
    text+=mdtable(['사전 정보','대상','사진 점 수','사진 패치 수','전체 넓이 m²','검출 한계 없는 넓이 m²'],
        [[r['prior'],'지붕' if r['group']=='roof' else '벽',r['points'],r['patches'],num(r['area_m2']),num(r['unavailable_DL_area_m2'])] for r in coverage])+'\n'
    rows=[]
    for prior,group,label in [('ALS','roof','항공 LiDAR 지붕'),('LoD2','roof','LoD2 지붕'),('LoD2','wall','LoD2 벽')]:
        r=photo[prior][group]
        for setting,index,summary in [('새 고른 값',r['choice_index'],r['summary']),('JN 고른 값',r['old_choice_index'],r['old_selected']),
            ('사진 없음',None,r['no_photo']),('사진 보기 값',44,r['old_display_photo'])]:
            pidx=None if index is None else index//9
            pars=cfg['photo']['inherited_judgments']['candidates'][pidx] if pidx is not None else None
            rows.append([label,setting,'—' if pars is None else pars['delta'],'—' if pars is None else pars['s_min'],
                '∞' if summary['threshold2_m'] is None else summary['threshold2_m'],num(summary['wrong_area_m2']),num(summary['evaluated_area_m2'])])
    text+=mdtable(['대상','설정','δ','최소 점수','거리 문턱 m','틀린 넓이 m²','계산 대상 m²'],rows)+'\n'
    text+='135개 조합, 원래 처리 뒤 판단, 건물별 대상, 동률 규칙을 유지했다. 지붕·벽을 따로 고른 표, 건물을 같게 본 값, 건물 하나 빼기 결과와 전 조합은 `tables/photo_*` 및 외부 `photo_dl/*_selection.json`에 저장했다.\n\n'
    trans=json.loads((DOC/'tables/photo_834_transition.json').read_text())['rows']
    text+='### 기존 사진 지지 834.4375 m²의 변화\n\n'
    text+=mdtable(['사진 선택값','지지 m²','반박 m²','모름 m²'],[
        [label]+[num(next(x['area_m2'] for x in trans if x['rule']==rule and x['new_judgment']==j)) for j in ['support','contradict','unknown']]
        for rule,label in [('old_selected_photo_parameters','JN 고른 값 고정'),('new_selected_photo_parameters','새 고른 값')]])+'\n'
    text+='![저장 곡선](figures/photo_834_ten_curves.png)\n\n'
    text+='### 저장 정밀도와 확인 불가\n\n'
    rows=[]
    for prior in ['ALS','LoD2']:
        r=json.loads((OUT/'photo_dl'/f'{prior}_replay.json').read_text())
        rows.append([prior,r['unavailable_DL_patches'],num(r['unavailable_DL_area_m2']),r['old_range_precision_changed_patches'],num(r['old_range_precision_changed_area_m2'])])
    text+=mdtable(['사전 정보','검출 한계 없는 패치 수','해당 넓이 m²','옛 범위 재생 차이 패치 수','재생 차이 넓이 m²'],rows)+'\n'
    text+='저장 곡선은 float16이고 당시 점수 요약은 float32다. 따라서 옛 범위를 다시 적용해도 일부 문턱 가까운 판단이 일치하지 않는다. 이 차이를 숨기거나 원본 곡선을 새 사진 처리로 대체하지 않았다. [고른 값에서의 정밀도 영향](tables/photo_precision_sensitivity.csv)을 함께 낸다. 새 판단과 원래 판단의 차이를 모두 범위 변경 하나의 효과로 단정하지 않는다.\n\n'
    held=json.loads((DOC/'tables/holdout_counts_and_hashes.json').read_text())
    text+='확인용 건물에는 개발 대상에서 고른 값을 그대로 적용했다. 공개한 것은 수·넓이·SHA-256뿐이다. 상세 판단과 선택은 외부 `holdout/`에만 있다.\n\n'
    text+=mdtable(['사전 정보','확인용 패치 수','확인용 넓이 m²'],[[r['prior'],r['patches'],num(r['area_m2'])] for r in held['counts']])+'\n'
    text+='## 기대값과 수치 비교\n\n'
    comparison=[]
    for u in UNITS:
        for s in ['equal','right']:
            for v in 'abcd':
                k=(u,v,s,'a','front');back=(u,v,s,'a','back');r=op.get(k,{})
                a=r.get('right_darker_fraction');b=dp.get(k,{}).get('right_fraction');drop=op.get(back,{}).get('right_darker_fraction_minus_v1')
                comparison.append([SITES[u],'같음' if s=='equal' else '맞음',LABELS[v],pct(a),pct(b),
                    '확인 불가' if a is None or b is None else ('충족' if a>=.7 and b>=.7 else '미충족'),
                    '확인 불가' if drop is None else f'{drop*100:+.1f}'])
    text+=mdtable(['경우','출발','판','앞 진함 %','앞 깊이 맞음 %','둘 다 70%','뒤 진함 v1 대비 %p'],comparison)+'\n'
    text+='표는 발주문에 적힌 70%와 −10%p를 확인할 수 있는 수치다. 원인 해석과 방법 채택 결론은 이 보고서에서 내리지 않는다. 판 가의 앞 후보가 혼자 남았을 때 0.5 이상인 비율은 일 1의 맞음만 열, 판 다·라의 수치는 위 표와 단면·렌더에서 확인한다.\n\n'
    text+='## 바꾼 것·확인 불가·시간\n\n'
    text+='- 판 가: 앞 후보 네 개만 렌더. 판 나: 1~1,000회 불투명도 고정, 1,001~4,000회 함께 학습. 판 다: 후보 위치·회전·크기만 추가 학습하고 매 갱신 뒤 자기 범위로 이동 제한. 판 라: 자리에서 수평 3m 안 바탕의 불투명도·색만 추가 학습.\n'
    text+='- 판 다의 위치 학습률은 GeoGS 기본 시작 0.00016, 끝 0.0000016, 30,000회 지수 변화에 원본 장면 크기를 곱했다. B173 272.353813, R1 229.696469이다. 회전 0.001, 크기 0.005. 불투명도·색 학습률은 v1과 같다.\n'
    text+='- 판 다의 범위 점검은 float32 좌표 반올림에 대해 0.03mm의 수치 허용치를 사용한다. 실제 초과량은 100회 기록에 보존하고, 끝 좌표는 별도 float64 계산으로 다시 확인한다.\n'
    bg=[]
    for unit in UNITS:
        check=json.loads((OUT/'preflight'/f'cp2_d_right_{unit}.json').read_text())
        bg.append(SITES[unit]+' '+format(check['trainable_background_gaussians'],','))
    text+='- 판 라에서 학습한 바탕 가우시안 수: '+', '.join(bg)+'개. 그 밖의 바탕 값과 바탕 기하는 유지했다. 판 다의 끝 법선 이동 분포는 [분포 표](tables/normal_displacement_distribution.csv)에 있다.\n'
    text+='- B173·항공 LiDAR 43점의 `u_prior`가 없어 판 다 2판을 학습하지 않았다. 해당 결과는 확인 불가다. 다른 판의 점을 임의로 제외하지 않았다.\n'
    text+='- 판 라의 처음 역변환 오류는 원본 logit 직접 읽기로 학습 전에 해결했다. 처음 실패 기록은 보존했다. 모든 단위 점검·실행 실패·표시 수정은 [실패 기록](issues.md)에 남겼다.\n'
    text+=f'- 학습 합계 {training_seconds/60:.1f}분, 깊이 채점 합계 {depth_seconds/60:.1f}분은 두 GPU의 각 판 실행 시간 합이다. 사진 CPU 계산 {photo_seconds/60:.1f}분. 준비·검증·그림·압축·대기는 이 합계에서 제외했다. 시작·끝 시각은 각 실행 기록에 있다.\n'
    text+='- 앞 작업의 값·설정·코드·결과를 수정하지 않았다. 참값은 자리·초기 불투명도·채점에만 쓰고 손실에는 넣지 않았다. 새 깊이 손실·밀도 제어·불투명도 재설정·정리는 없다.\n\n'
    text+='실제 실행 코드는 첫 커밋 전에 해시로 잠갔다. 실행 기록의 커밋은 당시 저장소 HEAD이며 새 코드의 동일성은 별도 코드 해시로 확인한다. 사진 계산의 당시 HEAD는 Git 기록으로 확인했고, 원래 완료 기록에 빠진 환경변수 직접 기록은 [출처 표](tables/photo_execution_provenance.json)에 확인 불가로 표시했다.\n\n'
    text+='전달 묶음에는 설정, 코드, 이 보고서, 표·그림, 새 판의 상태·기록 및 사진 다시 셈의 공개 값이 들어간다. 원본 사진·바탕 장면·v1 전체 자료는 외부 입력 경로와 해시로 연결한다. ZIP 무결성은 과학적 결론을 뜻하지 않는다.\n'
    assert len(text)<=20000,len(text)
    if write:
        (DOC/'원인확인_보고_v1.md').write_text(text)
        save(DOC/'tables/report_receipt.json',dict(at=now(),characters=len(text),source=SOURCE,scientific_verdict=None),replace=True)
    print('REPORT',len(text),'characters',flush=True)

if __name__=='__main__':main()
