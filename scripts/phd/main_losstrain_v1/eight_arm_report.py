"""Two-region ALS handover assembled from unchanged stage-1 scoring outputs."""
import csv
import json
import math
from pathlib import Path

from inputs import OUT, save, sha
from interim_report import SUBSETS, VARS
from post_memory_policy import policy_for

DOC = Path('/docs')
SITES = ['B173nb_b10', 'B0_b10']
REPORT = '중간보고_항공LiDAR_8판_v1.md'
LABELS = {'B173nb_b10':'B173 주변', 'B0_b10':'B0'}


def read(path):
    return json.loads(Path(path).read_text())


def fmt(value):
    return '자료 없음' if value is None else f'{value:.6f}'


def main():
    scores = read(DOC/'tables/patch_scores_all.json')['rows']
    score = {(r['site'],r['variant'],r['subset']):r for r in scores if r['prior']=='ALS'}
    noise = read(DOC/'tables/noise_thresholds.json')['rows']
    thresholds, paired, overview, fates, sources = [], [], [], [], []
    lines = ['# 손실 학습 시험 — 항공 LiDAR 두 지역 8판 중간 보고', '',
             'B173 주변과 B0의 네 판씩, 총 8판의 학습 후 실제 시점 메시·패치 채점 자료다. '
             'R1 및 LoD2의 결과까지 완성한 보고서는 아니다. scientific_verdict: null.', '',
             '1단계 패치, 고정된 평가 범위, 동일한 바깥면 첫 교차 채점을 사용한다. '
             '면 없음은 τ 밖으로 센다. N < 100은 표본 부족이다. 두 지역은 따로 비교한다.', '',
             '## 먼저 볼 값', '',
             '보존 칸의 τ 안 넓이는 보존 칸 전체에서 참값과 τ 이내인 면적이다. '
             '면 없음 넓이는 전체 칸 0~3에서 결과 면을 만나지 못한 면적이다. '
             '각 비율의 분모는 옆에 적었으며, 중단·미채점 결과를 0으로 넣지 않았다.', '',
             '| 지역 | 결과 | 전체 τ 안 % | 보존 τ 안 m² | 보존 전체 m² | 보존 τ 안 % | 전체 면 없음 m² | 전체 면 없음 % |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    baselines = [('nojudge_ALS_s0','판정 끔'),('prop_ALS_s0','1단계 본 방법 씨앗 0'),
                 ('prop_ALS_s1','1단계 본 방법 씨앗 1'),('mvs_a','MVS'),('prior','학습 전 사전 정보')]
    for site in SITES:
        for result,label in baselines + [(v+'_ALS_s0',name) for v,(name,_) in VARS.items()]:
            all_row=score[(site,result,'all_0_3')];pres=score[(site,result,'cell_2')]
            overview.append(dict(site=site,result=result,label=label,all_0_3=all_row,preservation=pres))
            lines.append(f"| {LABELS[site]} | {label} | {fmt(all_row['within_tau_percent'])} | {fmt(pres['successful_area_m2'])} | {fmt(pres['area_m2'])} | {fmt(pres['within_tau_percent'])} | {fmt(all_row['no_surface_area_m2'])} | {fmt(all_row['no_surface_percent'])} |")
        for variant in VARS:
            result=variant+'_ALS_s0';unit=OUT/'runs'/site/result
            for name in ['PASS.json','post_stage_PASS.json']:
                path=unit/name;assert path.exists();sources.append(dict(path=str(path),sha256=sha(path)))
            receipt=OUT/'patch_z'/f'{site}__ALS__{result}.json'
            assert read(receipt)['status']=='PASS'
            sources.append(dict(path=str(receipt),sha256=sha(receipt)))
        for result in ['nojudge_ALS_s0']+[v+'_ALS_s0' for v in VARS]:
            for folder in ['fates','fate_cell_split']:
                path=DOC/'tables'/folder/site/f'ALS__{result}.json'
                data=read(path);assert data['status']=='PASS'
                if folder=='fate_cell_split':assert data['partition_counts_equal_combined']
                fates.append(data);sources.append(dict(path=str(path),sha256=sha(path)))
    for site in SITES:
        lines += ['',f'## {LABELS[site]}: 8.1 학습 없는 시험과 학습 후 결과','',
                  '| 판 | 범위 | N | 전체 m² | 학습 없음 τ 안 % | 학습 τ 안 % | τ 안 m² | 학습 없음 면 없음 % | 학습 면 없음 % | 학습 면 없음 m² |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for variant,(label,analytic) in VARS.items():
            for subset,name in SUBSETS.items():
                trained=score[(site,variant+'_ALS_s0',subset)];expected=score[(site,'analytic_'+analytic,subset)]
                assert trained['patches']==expected['patches'] and trained['area_m2']==expected['area_m2']
                paired.append(dict(site=site,variant=variant,subset=subset,analytic=expected,trained=trained))
                insufficient=' · 표본 부족' if trained['patches']<100 else ''
                lines.append(f"| {label} | {name+insufficient} | {trained['patches']} | {fmt(trained['area_m2'])} | {fmt(expected['within_tau_percent'])} | {fmt(trained['within_tau_percent'])} | {fmt(trained['successful_area_m2'])} | {fmt(expected['no_surface_percent'])} | {fmt(trained['no_surface_percent'])} | {fmt(trained['no_surface_area_m2'])} |")
        lines += ['', '다듬기 칸(칸 0)의 참값까지 거리 중앙값은 면을 만난 패치에서 계산한다. '
                  '면 없음은 위 표에 별도로 남기며 τ 안 비율에서는 실패로 센다.', '',
                  '| 판 | 학습 없음 관측 N | 학습 없음 거리 중앙값 m | 학습 관측 N | 학습 거리 중앙값 m |',
                  '|---|---:|---:|---:|---:|']
        for variant,(label,analytic) in VARS.items():
            trained=score[(site,variant+'_ALS_s0','cell_0')];expected=score[(site,'analytic_'+analytic,'cell_0')]
            lines.append(f"| {label} | {expected['error_observed_patches']} | {fmt(expected['error_patch_median_m'])} | {trained['error_observed_patches']} | {fmt(trained['error_patch_median_m'])} |")
    lines += ['', '## 8.4 같은 규칙으로 계산한 지표별 문턱', '',
              '단위 폭은 2.8 × |prop_ALS_s0 − prop_ALS_s1| / √2다. 비율의 문턱 단위는 %p, '
              '거리 중앙값의 문턱은 m다. 모은 폭이 없는 지표는 자료 없음이며, 거리에 300/N을 적용하지 않는다. '
              '차이가 최댓값의 두 배를 넘으면 수치 차이 확인, 최댓값 초과부터 두 배 이하는 가능·근거 불완전이다. '
              '이 표는 판정 문턱을 제공하며 방법론의 과학적 판정을 하지 않는다.', '',
              '| 지역 | 범위 | 지표 | N | 모은 폭 | 단위 폭 | 300/N | 최댓값 |',
              '|---|---|---|---:|---:|---:|---:|---:|']
    metrics={'within_tau_percent':'τ 안 %','no_surface_percent':'면 없음 %','error_patch_median_m':'거리 중앙값 m'}
    for site in SITES:
        for subset,name in SUBSETS.items():
            for metric,label in metrics.items():
                if metric=='error_patch_median_m' and subset!='cell_0':continue
                found=[r for r in noise if (r['kind'],r['site'],r['prior'],r['subset'],r['metric'])==('stage1_patch',site,'ALS',subset,metric)]
                assert len(found)==1
                row=dict(found[0]);seed_sources=[]
                for seed in [0,1]:
                    r=score[(site,f'prop_ALS_s{seed}',subset)]
                    assert r[metric]==row[f'seed_{seed}']
                    seed_sources.append(dict(source=r['source'],sha256=r['source_sha256'],
                         N=r['error_observed_patches'] if metric=='error_patch_median_m' else r['patches']))
                assert row['N']==min(x['N'] for x in seed_sources)
                expected=2.8*abs(row['seed_0']-row['seed_1'])/math.sqrt(2) if row['seed_0'] is not None and row['seed_1'] is not None else None
                assert row['case_spread']==expected
                parts=[row[k] for k in ['pooled','case_spread','three_points'] if row[k] is not None]
                assert row['threshold']==(max(parts) if parts else None)
                row['seed_sources']=seed_sources;thresholds.append(row)
                three='적용 없음' if metric=='error_patch_median_m' else fmt(row['three_points'])
                lines.append(f"| {LABELS[site]} | {name} | {label} | {row['N']} | {fmt(row['pooled'])} | {fmt(row['case_spread'])} | {three} | {fmt(row['threshold'])} |")
    side_rows=[];seen=set()
    for r in read(DOC/'tables/sides_all.json')['rows']:
        if r['site'] not in SITES or r['prior']!='ALS' or r['variant'] not in VARS:continue
        key=(r['site'],r['variant'],r['subset'])
        if key not in seen:side_rows.append(r);seen.add(key)
    assert len(side_rows)==24
    lines += ['', '## 8.2 도착점과 같은 쪽', '',
              '| 지역 | 판 | 범위 | N | 넓이 m² | 같은 쪽 % |','|---|---|---|---:|---:|---:|']
    for r in side_rows:
        lines.append(f"| {LABELS[r['site']]} | {VARS[r['variant']][0]} | {SUBSETS[r['subset']]} | {r['denominator_patches']} | {fmt(r['denominator_area_m2'])} | {fmt(r['same_side_percent'])} |")
    lines += ['', '## 8.5 칸 0과 칸 2의 심긴 점 운명', '',
              '| 지역 | 결과 | 칸 | 심긴 N | 지워짐 % | 옛 자리 % | 지금 면 % | 둘 다 아님 % |',
              '|---|---|---|---:|---:|---:|---:|---:|']
    for data in fates:
        for key,r in data['regions'].items():
            if key not in ['cell_0','cell_2']:continue
            shares=[fmt(None if r['shares'][k] is None else 100*r['shares'][k]) for k in ['removed','old_place','current_surface','neither']]
            lines.append(f"| {LABELS[data['site']]} | {data['result']} | {key} | {r['seeds_planted']} | "+' | '.join(shares)+' |')
    lines += ['', '칸 1·3과 0·2 묶음까지 포함한 전체 수와 비율은 [운명 표](tables/fates_all.md)에 있다.', '',
              '## 그림', '', 'B173 단면의 자리·폭·축은 앞 전달 자료와 같다. B0는 발주에 미리 정한 단면이 없어 임의 단면을 추가하지 않았다.', '',
              '![B173 날개 단면](figures/section_B173nb_b10_ALS_0.png)', '']
    for site in SITES:
        for prefix in ['map','side_map','fates']:
            path=f'figures/{prefix}_{site}_ALS.png';assert (DOC/path).exists()
            lines += [f'![{LABELS[site]} {prefix}]({path})','']
    full=sum((OUT/'runs'/s/(v+'_ALS_s0')/'measure_PASS.json').exists() for s in SITES for v in VARS)
    policy=policy_for(OUT)
    resource_note=(
        '64 GiB/60초/48 GiB 조건은 바꾸지 않았다.' if policy['id']=='resource_resume_v1' else
        f"사용자 승인으로 후처리 시작 조건은 {policy['host_available_GiB']} GiB 이상 60초, "
        f"컨테이너 한도는 {policy['container_limit_GiB']} GiB로 조정했다. "
        '이전 64/48 GiB 기록은 보존했고 기하 계산 설정은 유지했다.')
    lines += ['## 남은 것과 바꾼 것', '',
              f'핵심 8.1·8.2·8.5는 8/8판이다. 가상 시점·부유점·두 축 등 추가 지표까지 마친 판은 {full}/8이다. '
              'R1 항공 LiDAR 4판을 더한 12판 비교와 LoD2를 포함한 24조건 전체 보고는 아직 미완료다.', '',
              '이번에는 완료된 B0 항공 LiDAR 모델의 실제 시점 메시와 핵심 채점을 먼저 처리하도록 순서만 조정했다. '
              '진행 중 학습은 그대로 마쳤다. 손실·학습·채점·단면 설정은 바꾸지 않았다. '+resource_note+' '
              'B0와 B173 및 R1의 LoD2 고정 판은 중단 기록을 유지한다. 재학습하거나 정상 완료로 바꾸지 않았다.', '',
              '[사진 표](tables/photo.md), [불투명도·PSNR 관측](tables/monitor_v2_observations.md), '
              '[전체 패치 표](tables/patch_scores_all.md), [세부 값](tables/eight_arm_values.json), '
              '[지역별 문턱](tables/eight_arm_thresholds.json), [변화량과 문턱 비교](tables/numerical_changes.md). 과학적 판정은 별도다.']
    save(DOC/'tables/eight_arm_values.json',dict(overview=overview,paired_patch_rows=paired,side_rows=side_rows,
         fates=fates,source_receipts=sources,core_scored_arms=8,full_measurement_complete=full,post_memory_policy=policy,scientific_verdict=None))
    save(DOC/'tables/eight_arm_thresholds.json',dict(rows=thresholds,scientific_verdict=None))
    flat=[dict(site=r['site'],variant=r['variant'],subset=r['subset'],**{k:v for k,v in r['trained'].items() if k not in ['site','variant','subset','analytic_within_tau_percent']},analytic_within_tau_percent=r['analytic']['within_tau_percent']) for r in paired]
    keys=list(dict.fromkeys(k for r in flat for k in r))
    with (DOC/'tables/eight_arm_patch_scores.csv').open('w') as f:
        w=csv.DictWriter(f,keys,lineterminator='\n');w.writeheader();w.writerows(flat)
    (DOC/REPORT).write_text('\n'.join(lines)+'\n')
    print('eight-arm report ready; visual inspection and verification remain',flush=True)


if __name__=='__main__':main()
