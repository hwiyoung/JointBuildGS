"""Fact-only report, bounded to 4,000 Unicode characters."""
from common import *

def main():
    cfg()
    def read(name):return json.loads((D/'tables'/f'{name}.json').read_text())['rows']
    judge=read('judgment_summary');summ=read('method_summary');wall=read('wall_check');unassigned=read('unassigned');repro=read('reproduction')
    def fmt(v):return '확인 불가' if v is None else f'{v:.2f}'
    def loc(r):return f"{LABELS[r['max_gap_site']]}·{r['max_gap_prior']}·{CASES[r['max_gap_cell']]}"
    lines=['# PHD-MAIN-RECOUNT-v1','', '| 장면·사전 정보 | 규칙 | 둘 다 맞음 | 영상만 맞음 | 사전 정보만 맞음 | 영상 없음 | 전체 |','|---|---|---:|---:|---:|---:|---:|']
    for site in SITES:
        for prior in PRIORS:
            for rule in ['본 방법','늘 보존','늘 보정']:
                mine=[r for r in judge if (r['site'],r['prior'],r['rule'])==(site,prior,rule)]
                vals=[]
                for k in [0,1,2,4,'all']:
                    r=next(r for r in mine if r['case_id']==k);vals.append(fmt(r['accuracy_pct'])+(' 적음' if r['small'] else ''))
                lines.append('| '+f'{LABELS[site]}·{prior} | {rule} | '+' | '.join(vals)+' |')
    lines+=['','위는 판단 맞음 %. 경우는 참값 채점 기준 칸, 판단은 FINALTRAIN 꼬리표다. 전체는 둘 다 틀림·사전 정보 면 없음·미소속을 제외한 점 수 가중 비율이다. 적음: 참값 1,000개 미만.','',
        '| 방법 | B173 주변·B0 최대 차이 %p (자리) | 여섯 장면 최대 차이 %p (자리) |','|---|---|---|']
    for method in METHODS:
        cells=[]
        for scope in ['B173_B0','all_six']:
            r=next(r for r in summ if (r['scope'],r['metric'],r['method'])==(scope,'completeness',method));cells.append(f"{r['max_gap_pp']:.2f} ({loc(r)})")
        lines.append('| '+NAMES[method]+(' [참고]' if method in ['prior','mvs','judgment_mesh'] else '')+' | '+' | '.join(cells)+' |')
    lines+=['','최고는 사전 정보·MVS·판단 조합 메시를 제외한 6개 방법 중 완전성 최댓값이다. 표는 다섯 경우의 참값 1,000개 이상 칸만 썼다. 최솟값·3/5/10 %p 이내 칸 수·정확성 요약은 [방법 요약](tables/method_summary.csv)에 있다.']
    triggers=[r for r in wall if r['exceeds_2pct']];strong=[r for r in triggers if r['n_wall']>=1000]
    peak=max(triggers,key=lambda r:r['farther_1m_pct']) if triggers else None
    lines+=['',f'벽 점검: 2% 조건 {"초과" if triggers else "미초과"}. 참값 1,000개 이상 칸×방법 중 {len(triggers)}개가 넘었다(벽 참값 자체도 1,000개 이상인 것은 {len(strong)}개).']
    if peak:lines.append(f"최대 {peak['farther_1m_pct']:.2f}%: {LABELS[peak['site']]}·{peak['prior']}·{peak['case_name']}·{NAMES[peak['method']]} ({peak['n_wall_within_tau_farther_1m']}/{peak['n_wall_within_tau']}벽 점). [기존/3차원 보조 완전성](tables/wall_sensitivity.csv)을 함께 냈다. 채점 규칙 변경은 없다.")
    low=min([r for r in judge if r['rule']=='본 방법' and r['case_id']==2 and r['n_gt']>=1000],key=lambda r:r['accuracy_pct'])
    lines+=['',f"기대와 다른 수치: 사전 정보만 맞음의 판단 맞음은 {LABELS[low['site']]}·{low['prior']}에서 {low['accuracy_pct']:.2f}%다. 일치·보정도 이 경우에서는 틀림으로 셌다.",
        f"ALS 세 장면의 상속 참값 행에는 벽(kind=2)이 없어 벽 비율은 확인 불가(분모 0)다. 미소속 참값 행 {sum(r['row_owner_missing'] for r in unassigned):,}개와 사전 정보 면 없음 {sum(r['prior_surface_absent_rows'] for r in unassigned):,}개는 [별도 수](tables/unassigned.csv)로 남겼다(서로 겹침).",
        '', '[경우별 결과](tables/result_accuracy.csv) · [판단별 결과](tables/result_by_judgment.csv) · [틀린 크기별 결과](tables/offset_bins_wide.csv) · [발표 CSV](tables/central_figure.csv)',
        '', '[B173 ALS 지도](figures/B173nb_b10__ALS_maps.png)·[단면](figures/B173nb_b10__ALS_section.png) / [B173 LoD2 지도](figures/B173nb_b10__LoD2_maps.png)·[단면](figures/B173nb_b10__LoD2_section.png) / [R1 ALS 지도](figures/R1rep_b10__ALS_maps.png)·[단면](figures/R1rep_b10__ALS_section.png)',
        '', f"RELEASE τ 1배 324개 칸×방법 대조: 최대 차이 {max(r['delta_pp'] for r in repro if r['delta_pp'] is not None):.8f} %p. 판단 표 비율 합 100%(빈 행 제외). 설정 선잠금·CPU만 실행·학습/렌더/메시 생성 없음·지정 경로만 기록. [점검](validation.json).",
        '', 'τ 0.5~2배는 [기존 RELEASE 표](../main_release_v1/tables/stage0/table4_all.csv)만 참조했다. scientific_verdict: null.']
    report='\n'.join(lines)+'\n'
    assert len(report)<=4000,len(report)
    (D/'보고.md').write_text(report)
    print('REPORT_CHARACTERS',len(report))

if __name__=='__main__':main()
