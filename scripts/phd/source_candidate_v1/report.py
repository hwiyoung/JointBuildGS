"""Render a Korean development report from immutable method/evaluation outputs."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from scripts.phd.source_candidate_v1.common import sha, write
from scripts.phd.source_candidate_v1.evaluate import verify_method_seal, summarize_cells


def read(path): return json.loads(Path(path).read_text())
def number(value, digits=3): return 'NA' if value is None else f'{value:.{digits}f}'
def percent(value): return 'NA' if value is None else f'{100*value:.2f}%'
def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
                     ['| '+' | '.join(map(str,row))+' |' for row in rows])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--artifact-host-root',required=True)
    args=parser.parse_args();run=Path(args.run);output=Path(args.output);host=Path(args.artifact_host_root)
    if not Path('/.dockerenv').exists(): raise RuntimeError('Docker required')
    config,seal,seal_sha=verify_method_seal(run)
    evaluation=read(run/'evaluation/summary.json');receipt=read(run/'evaluation/evaluation_receipt.json')
    if evaluation['method_seal_sha256']!=seal_sha or receipt['method_seal_sha256']!=seal_sha:
        raise ValueError('Evaluation lineage mismatch')
    for name,digest in receipt['output_sha256'].items():
        if sha(run/'evaluation'/name)!=digest: raise ValueError('Evaluation output changed: '+name)
    cells=read(run/'evaluation/per_cell.json');risk=read(run/'evaluation/risk_coverage.json')
    figures=read(run.parent/'figures/figure_manifest.json')
    output.mkdir(exist_ok=False)
    stages=[];errors=[];strata=[];reason_rows=[];sens=[];oracle_rows=[];native_rows=[];large_rows=[]
    for region in config['regions']:
        candidates=read(run/region/'candidates.json');observations=read(run/region/'observations.json')
        decisions=read(run/region/'decisions.json');ins=read(run/region/'input_summary.json')
        obs={r['cell_id']:r['observation'] for r in observations};ds={r['cell_id']:r for r in decisions}
        erows=[r for r in cells if r['region']==region];ev=evaluation['regions'][region]
        matched=sum(o['shared']['common_scored_pair_count']>=3 and o['shared']['distinct_view_count']>=4
                    and o['shared']['disjoint_pair_count']>=2 for o in obs.values())
        row=dict(region=region,all_cells=len(candidates),mvs_points=ins['native_counts']['mvs'],
            als_points=ins['native_counts']['als'],views=ins['views'],both_valid=ins['both_valid_cells'],
            any_common_score=sum(o['shared']['common_scored_pair_count']>0 for o in obs.values()),
            matched_observation=matched,image=sum(d['action']=='IMAGE' for d in decisions),
            prior=sum(d['action']=='PRIOR' for d in decisions),abstain=sum(d['action']=='ABSTAIN' for d in decisions),
            coverage=ev['accepted_fraction_all_cells'])
        if row['image']+row['prior']+row['abstain']!=row['all_cells']: raise ValueError('Census mismatch')
        stages.append(row)
        accepted=ev['equal_cell_discrepancy']['accepted_same_cells']
        errors.append(dict(region=region,n=ev['common_accepted_cells'],
            mvs=accepted['mvs_error_m']['mean'],als=accepted['als_error_m']['mean'],
            selected=accepted['selected_error_m']['mean'],oracle=accepted['oracle_error_m']['mean'],
            regret=accepted['regret_m']['mean'],clear=ev['accepted_clear_gap_cells'],
            correct=ev['accepted_correct_clear_gap_cells'],ties=ev['accepted_tie_deadband_cells'],
            accuracy=ev['accepted_selection_accuracy_clear_gap']))
        byid={r['cell_id']:r for r in candidates}
        whole=ev['whole_native_point_weighted_diagnostics']
        native_rows.append(dict(region=region,
            mvs_raw=whole['mvs_whole_native']['symmetric_mean_m'],mvs_inliers=whole['mvs_all_inliers']['symmetric_mean_m'],
            als_raw=whole['als_whole_native']['symmetric_mean_m'],als_inliers=whole['als_all_inliers']['symmetric_mean_m'],
            full_target_recall_05m=next(r['recall'] for r in whole['selected_full_target_cell_constrained_completeness']['thresholds'] if r['threshold_m']==.5)))
        large=[r for r in erows if r['action']!='ABSTAIN' and abs(byid[r['cell_id']]['height_difference_m'])>2]
        ls=summarize_cells(large)
        large_rows.append(dict(region=region,selected_gap_gt2m=len(large),image=ls['action_counts'].get('IMAGE',0),
            prior=ls['action_counts'].get('PRIOR',0),correct=ls['accepted_correct_clear_gap_cells'],clear=ls['accepted_clear_gap_cells'],
            same_cells_mvs=ls['equal_cell_discrepancy']['accepted_same_cells']['mvs_error_m']['mean'],
            same_cells_als=ls['equal_cell_discrepancy']['accepted_same_cells']['als_error_m']['mean']))
        for label,predicate in [('valid_gap_ge1m',lambda r:r['both_valid'] and abs(r['height_difference_m'])>=1),
                                ('valid_gap_lt1m',lambda r:r['both_valid'] and abs(r['height_difference_m'])<1)]:
            chosen=[r for r in erows if predicate(byid[r['cell_id']])]
            ss=summarize_cells(chosen)
            strata.append(dict(region=region,stratum=label,n=len(chosen),
                any_score=sum(obs[r['cell_id']]['shared']['common_scored_pair_count']>0 for r in chosen),
                accepted=ss['accepted_cells'],image=ss['action_counts'].get('IMAGE',0),prior=ss['action_counts'].get('PRIOR',0),
                correct_clear=ss['accepted_correct_clear_gap_cells'],clear=ss['accepted_clear_gap_cells'],
                coverage=ss['accepted_fraction_all_cells'],
                regret=ss['equal_cell_discrepancy']['accepted_same_cells']['regret_m']['mean']))
        for source in ('mvs','als'):
            eligible=[r for r in erows if r['both_valid'] and r['mvs_error_m'] is not None and r['als_error_m'] is not None
                      and r['source_gap_m']>.1 and r[source+'_error_m']<r[('als' if source=='mvs' else 'mvs')+'_error_m']]
            expected={'mvs':'IMAGE','als':'PRIOR'}[source]
            oracle_rows.append(dict(region=region,reference_better_source=source,cells=len(eligible),
                correct_selected=sum(r['action']==expected for r in eligible),
                wrong_selected=sum(r['action'] not in (expected,'ABSTAIN') for r in eligible),
                abstain=sum(r['action']=='ABSTAIN' for r in eligible)))
        for reason,count in Counter(d['reason'] for d in decisions).most_common():
            reason_rows.append(dict(region=region,reason=reason,count=count,fraction_all=count/len(candidates)))
        rr=[r for r in risk if r['region']==region]
        sens.append(dict(region=region,settings=len(rr),min_accepted=min(r['accepted_cells'] for r in rr),
            max_accepted=max(r['accepted_cells'] for r in rr),
            min_regret=min((r['regret_mean_m'] for r in rr if r['regret_mean_m'] is not None),default=None),
            max_regret=max((r['regret_mean_m'] for r in rr if r['regret_mean_m'] is not None),default=None)))
    derived=dict(task_id=config['task_id'],scientific_verdict=None,method_seal_sha256=seal_sha,
        stages=stages,accepted_same_cell_discrepancy=errors,source_plane_gap_strata=strata,
        reference_oracle_diagnostic=oracle_rows,decision_reasons=reason_rows,sensitivity_range=sens,
        native_filter_diagnostic=native_rows,accepted_gap_gt2m=large_rows)
    write(output/'analysis.json',derived)
    for name,rows in [('stages',stages),('accepted_same_cells',errors),('plane_gap_strata',strata),
                      ('reference_oracle',oracle_rows),('decision_reasons',reason_rows),('sensitivity_ranges',sens),
                      ('native_filter_diagnostic',native_rows),('accepted_gap_gt2m',large_rows)]:
        with (output/(name+'.csv')).open('x',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    lines=['# P1/P2/P3 다중뷰 소스별 3D 후보 평가기 — 실행 결과',
        '',f'Task `{config["task_id"]}` · 2026-09-08 · 개발 검증 · `scientific_verdict: null`','',
        '**평가기 구현과 세 영역 실행은 완료했다. 현재 고정 규칙의 선택 범위는 좁으며, 큰 이격 영역 전반에서 유효 소스를 선택하는 능력은 아직 입증되지 않았다.**',
        '', 'P2에서는 2 m 초과 이격의 선택 36셀 모두 영상 후보가 참조에 더 가까웠다. 반면 전체 선택률은 42/1,317=3.19%이며, 큰 이격에서 prior를 구제한 증거는 없다. P2의 동일 선택 셀에서 영상 단독 대비 평균 거리 감소는 약 9.5 mm이고, P3 유일 prior 선택은 약 6.2 cm 악화했다. 좋은 국소 선택 사례와 넓은 미해결 영역이 함께 존재한다.',
        '', '## 1. 후보 입력 → 관측 평가 → 소스 판단','',
        table(['영역','전체 셀','MVS / ALS 원점 수','영상 수','두 후보 유효','공통 점수 있음','관측 최소조건 충족','IMAGE / PRIOR / ABSTAIN','전체 선택률'],
              [[r['region'],r['all_cells'],f"{r['mvs_points']:,} / {r['als_points']:,}",r['views'],r['both_valid'],
                r['any_common_score'],r['matched_observation'],f"{r['image']} / {r['prior']} / {r['abstain']}",percent(r['coverage'])] for r in stages]),
        '', '셀은 고정 2 m XY 구획이다. 원점은 모두 보존하고 각 소스에서 국소 dominant plane과 native inlier membership을 독립 구성했다. 한 셀의 단일 평면이 부적합하거나 소스가 없는 경우도 전체 분모에 포함했다.',
        '', '관측 최소조건은 같은 픽셀·마스크의 영상쌍 3개 이상, 영상 4개 이상, 카메라를 공유하지 않는 쌍 2개 이상이다. 원 K/R/t로 후보 평면의 영상 warp를 만들고 ZNCC 비용을 비교했다. 이 쌍 구성은 통계적 독립 관측을 뜻하지 않는다.',
        '', '소스 판단은 비용 ≤0.25, 소스 차이 ≥0.05, 쌍별 우세 비율 ≥0.75와 후보 법선 방향 ±0.5/1/2 m 변위 검사를 통과해야 한다. 통과하지 않으면 ABSTAIN이다. 후보가 동등한 경우와 둘 다 불량인 경우도 강제로 선택하지 않는다.',
        '', f'![단계별 전체 분모와 선택 결과]({host}/figures/00_stage_summary.png)',
        '', '## 2. 같은 선택 셀에서의 참조 기하 비교','',
        table(['영역','같은 선택 셀 n','항상 MVS (m)','항상 ALS (m)','선택 결과 (m)','셀별 oracle (m)','평균 regret (m)','명확한 차이에서 정선택','참조 차이 ≤0.1 m'],
              [[r['region'],r['n'],number(r['mvs']),number(r['als']),number(r['selected']),number(r['oracle']),number(r['regret']),
                f"{r['correct']} / {r['clear']} ({percent(r['accuracy'])})",r['ties']] for r in errors]),
        '', '각 셀의 오차는 해당 셀 native candidate inlier와 UAS의 양방향 최근접거리 평균을 절반씩 합한 값이다. 위 표는 **동일한 선택 셀 집합에서 셀별 동일 가중 평균**이다. 선택 영역 평균을 전체 영역 baseline과 비교하지 않는다. Oracle은 UAS에 더 가까운 소스를 사후 선택한 평가 전용 하한이며 학습·판단에 전달되지 않았다.',
        '', '이 수치는 보존된 좌표에서의 UAS discrepancy다. 점 밀도·결측과 기존 수직기준/정합 불확실성을 포함하므로 보정된 절대 정확도나 실제 변화의 정답률로 해석하지 않는다. 참조 차이 0.1 m 이하 셀은 소스 정선택 비율의 분모에서 뺐다.',
        '', table(['영역','전체 MVS 원점 → 평면 inlier (m)','전체 ALS 원점 → 평면 inlier (m)','선택 결과 전체 참조 완전성 @0.5 m'],
                  [[r['region'],f"{number(r['mvs_raw'])} → {number(r['mvs_inliers'])}",
                    f"{number(r['als_raw'])} → {number(r['als_inliers'])}",percent(r['full_target_recall_05m'])] for r in native_rows]),
        '', '위 원점/inlier 표는 영역 전체의 점 가중 기하 진단이며 앞의 셀 동일 가중 표와 다른 지표다. 특히 P3에서 단일 평면 inlier만 남기면 지지·세부가 사라져 참조 거리가 커진다. 후보 표현 자체의 손실을 선택 모듈의 성과로 숨길 수 없다.',
        '', '## 3. 큰 소스 이격과 미해결 영역','',
        table(['영역','평면 높이 이격','두 유효 후보 셀','공통 점수 셀','선택 셀','IMAGE / PRIOR','선택률','정선택 / 명확 차이','regret (m)'],
              [[r['region'],'≥1 m' if r['stratum'].endswith('ge1m') else '<1 m',r['n'],r['any_score'],r['accepted'],
                f"{r['image']} / {r['prior']}",percent(r['coverage']),f"{r['correct_clear']} / {r['clear']}",number(r['regret'])] for r in strata]),
        '', '큰 이격은 추정 중력 방향의 두 평면 중심 차이로 정의한 진단 구분이다. 실제 변화 라벨이 아니며, 유효한 두 후보가 없는 셀은 첫 표에 남아 있다.',
        '',table(['영역','2 m 초과 이격 선택 셀','IMAGE / PRIOR','정선택 / 명확 차이','같은 셀 MVS (m)','같은 셀 ALS (m)'],
                 [[r['region'],r['selected_gap_gt2m'],f"{r['image']} / {r['prior']}",f"{r['correct']} / {r['clear']}",number(r['same_cells_mvs']),number(r['same_cells_als'])] for r in large_rows]),
        '',table(['영역','참조상 더 가까운 소스','차이 >0.1 m 셀','맞게 선택','잘못 선택','보류'],
                 [[r['region'],r['reference_better_source'].upper(),r['cells'],r['correct_selected'],r['wrong_selected'],r['abstain']] for r in oracle_rows]),
        '', '위 oracle 분해는 좋은 후보가 존재해도 관측 평가·판단에서 얼마나 놓치는지 보여준다. 전체 참조점에 대한 완전성은 `run/evaluation/summary.json`의 `selected_full_target_cell_constrained_completeness`에 별도로 기록했으며, 보류 셀의 모든 참조점을 미복원으로 계산한다.',
        '', '## 4. 판단 이유와 고정 규칙 민감도','',
        table(['영역','판단 이유','셀 수','전체 비율'],[[r['region'],r['reason'],r['count'],percent(r['fraction_all'])] for r in reason_rows]),
        '',table(['영역','사전 고정 조합 수','선택 셀 최솟값–최댓값','regret 최솟값–최댓값 (m)'],
                 [[r['region'],r['settings'],f"{r['min_accepted']}–{r['max_accepted']}",f"{number(r['min_regret'])}–{number(r['max_regret'])}"] for r in sens]),
        '', '민감도는 UAS 접근 전에 고정한 비용 0.15/0.25/0.35 × 차이 0.02/0.05/0.10 × 우세비율 0.67/0.75/1.0의 27조합이다. 사후 참조 성능으로 최적 조합을 선택하지 않았다. 전체 조합별 coverage·risk·regret는 원 CSV에 있다.',
        '', '## 5. 정성 자료와 사례 선정','',
        '각 영역에 전체 단계 지도, 원점군 3D·단면, 실제 원영상 crop, 같은 기준 픽셀로 재생성한 후보별 warp 및 변위 비용곡선을 제공한다. 재생성된 영상쌍 비용은 저장한 값과 1e-6 허용차로 대조한다. 점군 표시용 다운샘플은 판단·수치 평가에 쓰지 않았다.',
        '', '사례는 상태별 첫 cell_id, 점수가 존재하는 첫 ABSTAIN, 최대 평면 이격을 사용한다. 최대 accepted regret 사례만 참조 평가 후 선택한 명시적 실패 진단이다. 없는 선택 상태를 성공 사례로 만들지 않았다.']
    for region in config['regions']:
        lines += ['',f'### {region}', '',f'![{region} 단계별 결과]({host}/figures/{region}_stage_overview.png)']
        observations_by_region={
            'P1':'셀 16의 원영상에는 반복되는 줄무늬와 가로 경계가 보인다. MVS/ALS 높이 차이는 약 2.247 m이고 UAS 거리는 0.224/1.968 m지만, 표시한 한 patch의 비용은 MVS 0.590 / ALS 0.538로 prior 쪽이 오히려 낮다. 전체 영상쌍 조건에서는 서로 다른 영상 수가 부족해 보류했다. 이 사례는 단일 patch 순위만으로 더 유효한 기하를 결정할 수 없음을 보여준다. 반복 무늬가 오류의 유일한 원인이라는 뜻은 아니다.',
            'P2':'셀 5에서는 두 native 표면이 약 4.763 m 떨어져 있고 목표 영상에서 투영 위치도 분리된다. MVS warp가 anchor의 밝기 구조를 더 잘 재현하며 법선 방향 변위 0 부근에서 비용이 낮다. 표시 patch 비용은 0.050/0.334, UAS 거리는 0.263/4.879 m로 영상 선택을 지지한다. 다른 셀의 prior 선택과 최대 regret 오판도 아래에 함께 제시한다.',
            'P3':'전체 540셀 중 350셀은 두 후보의 단일 평면 표현 조건을 통과하지 못했다. 유일한 prior 선택 셀 43의 UAS 거리는 MVS 0.057 m, ALS 0.118 m다. 이는 prior 구제의 성공 사례로 해석할 수 없으며, 관측 적합도 우세와 기하 거리 개선이 일치하지 않을 수 있음을 보여준다.'}
        lines += ['',observations_by_region[region]]
        for fig in figures['figures']:
            if not fig['id'].startswith(region+'_case_'): continue
            case=fig['case']
            ce=case['evaluation']
            lines += ['',f'[{fig["id"]} PNG]({host}/figures/{fig["id"]}.png) · [PDF]({host}/figures/{fig["id"]}.pdf)',
                      '', f"셀 {case['cell_id']}: **{case['action']}** · `{case['reason']}`. MVS {number(ce.get('mvs_error_m'))} m / ALS {number(ce.get('als_error_m'))} m / regret {number(ce.get('regret_m'))} m.",
                      '', '선정 규칙: `'+', '.join(case['selection_rules'])+'`. '+
                      ('저장된 실제 영상쌍과 warp 점수를 재현했다.' if case['warp_evidence'] else '공통 점수가 없어 영상 비교를 만들지 않았다.')]
    lines += ['', '## 6. 해석 범위와 다음 알고리즘','',
        '현재 결과는 조건부 소스 선택의 개발 검증이다. 현재 MVS를 만든 영상과 평가 RGB의 계보가 겹치고, 기존 카메라·정합은 고정했다. 각 소스의 자기 가림은 모델 가설이며 실제 현재 장면의 free-space나 전체 장면 가림을 증명하지 않는다. 따라서 PRIOR 선택은 관측과 양립하는 구조 후보라는 의미이며 과거 구조가 현재에도 존재한다는 확정은 아니다.',
        '', '다음 구현의 우선순위는 (1) 혼합 셀을 여러 유한 표면 후보로 유지하고 같은 reference ray가 교차하는 인접 셀의 실제 표면까지 후보로 조회하는 방식, (2) 후보별 지지/반증/미관측 검사와 후보 간 공통 관측 비교의 분리다. 특히 고정 XY 셀의 두 표면이 영상에서 서로 다른 위치에 투영되면 현재 공통 support 조건은 비교 자체를 막을 수 있다. 원인별 기여율은 아직 분해되지 않았으므로 기하 교집합, 자체 가림, texture 탈락을 별도 계수해야 한다. 단순 임계값 완화보다 후보·관측 대응 단위의 개선을 먼저 검증해야 한다.',
        '', '공통 영역이 없는 후보들의 서로 다른 patch NCC를 그대로 비교해 순위를 매겨서는 안 된다. 각 후보의 SUPPORT/REJECT/UNDETERMINED를 먼저 계산하고, 실제 공통 관측이 있을 때만 paired contrast를 추가하는 구성이 적절하다. 후보 불확실성과 미관측은 계속 ABSTAIN으로 남겨야 한다.',
        '', 'GS 입력 연결은 후보 원행 membership과 IMAGE/PRIOR/ABSTAIN 결과를 전달하는 방식으로 준비되어 있다. 이번 실행에서는 GS 학습, 외관 복원, LoD2 완성도 또는 최종 과학적 성능을 측정하지 않았다.',
        '', '## 7. 재현·검증·산출물','',
        '- 소스: `src/phd/source_candidate_v1/`, driver: `scripts/phd/source_candidate_v1/`, 고정 설정: `configs/phd/source_candidate_v1/`.',
        '- Docker에서 후보/관측/판단 테스트 27개, 참조 평가 테스트 9개 통과. 실자료 3영역 method seal 이후에만 UAS 접근.',
        '- 평가 첫 시도는 UAS 배열 키 불일치로 중단했다. 정확한 `uas_xyz`/`uas_raw_rows` 스키마로 평가 로더만 수정했으며 실패 소스·로그를 보존했다. 재시도 보존 디렉터리 권한 문제도 해당 task 범위의 atomic rename으로 해소했다.',
        '', '```bash', '/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py method --run-id NEW_RUN_ID',
        '/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py evaluation --run-id NEW_RUN_ID',
        '/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py figures --run-id NEW_RUN_ID',
        '/usr/bin/python3 scripts/phd/source_candidate_v1/launch.py report --run-id NEW_RUN_ID', '```','',
        f'- [전체 셀 평가 CSV]({host}/run/evaluation/per_cell.csv)',
        f'- [27조합 민감도 CSV]({host}/run/evaluation/risk_coverage.csv)',
        f'- [파생 분석 JSON]({host}/report/analysis.json)',
        f'- [고정 method seal]({host}/run/method_seal.json)',
        f'- [그림 provenance]({host}/figures/figure_manifest.json)',
        '',f'Method seal SHA256: `{seal_sha}`',
        '', '기존 실험·원자료는 변경하지 않았다. 수치와 그림은 기술적 산출물이며 최종 과학적 판단은 연구자에게 남긴다.']
    (output/'RESULT_ko_v1.md').write_text('\n'.join(lines)+'\n')
    write(output/'report_receipt.json',dict(scientific_verdict=None,method_seal_sha256=seal_sha,
        evaluation_receipt_sha256=sha(run/'evaluation/evaluation_receipt.json'),
        figure_manifest_sha256=sha(run.parent/'figures/figure_manifest.json'),
        files={p.name:sha(p) for p in output.iterdir() if p.is_file()}))
    print(json.dumps(dict(status='REPORT_COMPLETE',output=str(output),stages=stages)),flush=True)


if __name__=='__main__': main()
