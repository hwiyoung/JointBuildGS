"""Summarize ONE hash-bound v2 evaluation without loading raw references/models.

Only observed CSV/identity records are consumed. Partial evaluations produce an
explicit intermediate report with no outcome conclusion. All eighteen paired
conditions are required by default; no best-condition selection is performed.
"""
import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import time

from evaluation_utils_v2 import read_json,write_json,write_csv,sha,safe_child


CSV_NAMES=('geometry_metrics','paired_transitions','same_cell_changes','anchor_global_local_transitions',
           'appearance_per_image','coverage','postprocessing_effect','compute','missing_runs')
REPORT_REVISION='v2.2_three_way_accounting'


def numeric(row,key,optional=False):
    value=row.get(key)
    if value in (None,'','null'):
        if optional:return None
        raise ValueError('Missing numeric field: '+key)
    result=float(value)
    if not math.isfinite(result):raise ValueError('Nonfinite numeric field: '+key)
    return result


def integer(row,key):
    value=numeric(row,key)
    if value<0 or value!=int(value):raise ValueError('Expected nonnegative integer: '+key)
    return int(value)


def index_unique(rows,keys):
    result={}
    for row in rows:
        identity=tuple(row[key] for key in keys)
        if identity in result:raise ValueError('Duplicate table identity: '+str(identity))
        result[identity]=row
    return result


def main_rows(rows,kind='raw',threshold=.5,cohort=None):
    return [row for row in rows if row['mesh_kind']==kind and numeric(row,'threshold_m')==threshold
            and (cohort is None or row['cohort']==cohort)]


def validate_geometry_grid(rows,cfg):
    expected={(kind,float(threshold)) for kind in ('raw','post') for threshold in cfg['evaluation']['thresholds_m']}
    groups={}
    for row in rows:
        if integer(row,'mesh_res')!=512:raise ValueError('Only matched TSDF512 geometry may be summarized')
        group=groups.setdefault((row['region'],row['candidate']),set())
        member=(row['mesh_kind'],numeric(row,'threshold_m'))
        if member in group:raise ValueError('Duplicate raw/post threshold metric')
        group.add(member)
    if any(members!=expected for members in groups.values()):
        raise ValueError('All frozen thresholds and both raw/post must be present for every reported geometry')


def validate_paired_grids(rows,cfg,three_way=False):
    """Every exported comparison/cohort must retain the full frozen metric grid."""
    expected={(kind,float(t)) for kind in ('raw','post') for t in cfg['evaluation']['thresholds_m']}
    groups={};before_key='parent_condition' if three_way else 'comparator'
    for row in rows:
        identity=(row['region'],row['candidate'],row[before_key],row['cohort'])
        member=(row['mesh_kind'],numeric(row,'threshold_m'))
        members=groups.setdefault(identity,set())
        if member in members:raise ValueError('Duplicate paired raw/post threshold identity')
        members.add(member)
    if not groups or any(members!=expected for members in groups.values()):
        raise ValueError('All frozen thresholds and both raw/post must be present for every paired comparison/cohort')


def validate_three_way_accounting(row,n,anchor_global,anchor_local,global_local):
    """Producer order is binary A*4 + G*2 + LC; near means distance<threshold.

    Named counts are checked against the eight disjoint states and then derived
    from those states. Missing-surface counts are not derivable from near/far
    states and remain separate producer observations.
    """
    bins=[integer(row,f'anchor_global_local_near_{state:03b}_count') for state in range(8)]
    if sum(bins)!=n:raise ValueError('Three-way classes do not partition the reference points')
    b=bins
    derived=dict(global_corrected_count=b[2]+b[3],global_correction_retained_by_local_count=b[3],
        global_correction_lost_by_local_count=b[2],additional_local_correction_count=b[1],
        global_damaged_count=b[4]+b[5],global_damage_recovered_by_local_count=b[5],
        global_damage_remaining_in_local_count=b[4],additional_local_damage_count=b[6],
        anchor_valid_retained_by_both_count=b[7],anchor_far_remaining_far_in_both_count=b[0])
    for key,value in derived.items():
        if integer(row,key)!=value:raise ValueError('Three-way named count differs from binary states: '+key)
    projections=[('Anchor->G',anchor_global,(b[2]+b[3],b[4]+b[5],b[6]+b[7],b[0]+b[1])),
                 ('Anchor->LC',anchor_local,(b[1]+b[3],b[4]+b[6],b[5]+b[7],b[0]+b[2])),
                 ('G->LC',global_local,(b[1]+b[5],b[2]+b[6],b[3]+b[7],b[0]+b[4]))]
    for label,pair,expected in projections:
        for key,value in zip(('corrected_count','damaged_count','retained_near_count','remaining_far_count'),expected):
            if integer(pair,key)!=value:raise ValueError('Three-way projection differs from '+label+' '+key)
    return derived


def validate_all_three_way_accounting(rows,pairs):
    """Check the copied raw/post tables as well as the primary reported slice."""
    lookup={}
    for row in pairs:
        key=(row['region'],row['candidate'],row['comparator'],row['mesh_kind'],
             numeric(row,'threshold_m'),row['cohort'])
        if key in lookup:raise ValueError('Duplicate paired accounting identity')
        lookup[key]=row
    for row in rows:
        region,candidate,baseline=row['region'],row['candidate'],row['parent_condition']
        suffix=(row['mesh_kind'],numeric(row,'threshold_m'),row['cohort'])
        keys=[(region,baseline,'ANCHOR',*suffix),(region,candidate,'ANCHOR',*suffix),
              (region,candidate,baseline,*suffix)]
        if any(key not in lookup for key in keys):raise ValueError('Missing three-way paired projection')
        projected=[lookup[key] for key in keys];n=integer(row,'reference_count')
        if any(integer(pair,'reference_count')!=n for pair in projected):
            raise ValueError('Three-way paired reference denominators differ')
        validate_three_way_accounting(row,n,*projected)


def pair_summary(geometry,pairs,cells,three_way,cfg,complete):
    """Validate reference-point accounting before summarizing G versus LC."""
    geo=index_unique(main_rows(geometry),('region','candidate'))
    paired=index_unique(main_rows(pairs,cohort='ALL_REFERENCE'),('region','candidate','comparator'))
    joint=index_unique(main_rows(three_way,cohort='ALL_REFERENCE'),('region','candidate','parent_condition'))
    expected={(region,c['id']) for region in cfg['regions'] for c in cfg['conditions']}
    observed={key for key in geo if key[1].startswith('LC_')}
    if not observed<=expected:raise ValueError('Unexpected local condition in evaluated table')
    if complete and observed!=expected:raise ValueError('Complete evaluation lacks exact full18 local membership')
    result=[];methods=[]
    for region in cfg['regions']:
        region_observed=[c for c in cfg['conditions'] if (region,c['id']) in observed]
        if not region_observed:continue
        for c in cfg['conditions']:
            if (region,c['parent_condition']) not in geo:raise ValueError('An original G comparator is missing')
        for candidate in ['ANCHOR',*[c['parent_condition'] for c in cfg['conditions']],*[c['id'] for c in region_observed]]:
            metrics=geo[(region,candidate)]
            row=dict(region=region,candidate=candidate,method='ANCHOR' if candidate=='ANCHOR' else 'LC' if candidate.startswith('LC_') else 'G',
                precision=numeric(metrics,'precision',True),recall=numeric(metrics,'recall',True),f1=numeric(metrics,'f1',True),
                reference_count=integer(metrics,'reference_count'),surface_samples=integer(metrics,'surface_samples'),
                status=metrics['status'],raw512_threshold_m=.5,scientific_verdict=None)
            if candidate!='ANCHOR':
                transition=paired[(region,candidate,'ANCHOR')]
                row.update(corrected_vs_anchor=integer(transition,'corrected_count'),damaged_vs_anchor=integer(transition,'damaged_count'))
            methods.append(row)
        for c in region_observed:
            candidate,baseline=c['id'],c['parent_condition']
            anchor,old,new=geo[(region,'ANCHOR')],geo[(region,baseline)],geo[(region,candidate)]
            p=paired[(region,candidate,baseline)];ga=paired[(region,baseline,'ANCHOR')];la=paired[(region,candidate,'ANCHOR')]
            joint_row=joint[(region,candidate,baseline)]
            n=integer(p,'reference_count')
            if any(integer(row,'reference_count')!=n for row in (anchor,old,new,ga,la,joint_row)):
                raise ValueError('Paired and geometric reference denominators differ')
            gain,damage=integer(p,'corrected_count'),integer(p,'damaged_count')
            retained,remaining=integer(p,'retained_near_count'),integer(p,'remaining_far_count')
            if gain+damage+retained+remaining!=n:raise ValueError('Pair transition categories do not partition reference points')
            old_recall,new_recall=numeric(old,'recall',True),numeric(new,'recall',True)
            if n:
                if (old_recall is None or new_recall is None or
                    not math.isclose(old_recall,(retained+damage)/n,abs_tol=1e-12) or
                    not math.isclose(new_recall,(retained+gain)/n,abs_tol=1e-12)):
                    raise ValueError('Reference recall does not reconcile with correction/damage counts')
            selected=[row for row in cells if row['region']==region and row['candidate']==candidate
                and row['comparator']==baseline and row['mesh_kind']=='raw' and numeric(row,'threshold_m')==.5]
            index_unique(selected,('cell_id',))
            if any(integer(r,'corrected_count')+integer(r,'damaged_count')>integer(r,'reference_count') for r in selected):
                raise ValueError('Same-cell corrected/damaged points exceed its reference count')
            if sum(integer(row,'reference_count') for row in selected)!=n:
                raise ValueError('Same-cell reference counts differ from pointwise pair')
            if (sum(integer(row,'corrected_count') for row in selected)!=gain or
                    sum(integer(row,'damaged_count') for row in selected)!=damage):
                raise ValueError('Same-cell gains/damage do not reconcile with pointwise pair')
            derived=validate_three_way_accounting(joint_row,n,ga,la,p)
            if n and (numeric(anchor,'recall',True) is None or not math.isclose(
                    numeric(anchor,'recall'),(integer(ga,'retained_near_count')+integer(ga,'damaged_count'))/n,abs_tol=1e-12)):
                raise ValueError('Anchor reference recall differs from three-way projection')
            row=dict(region=region,condition=candidate,parent_condition=baseline,lambda_prior=c['lambda_p'],protection=c['protection'],
                mesh_kind='raw',mesh_res=512,threshold_m=.5,reference_count=n,
                global_surface_samples=integer(old,'surface_samples'),local_surface_samples=integer(new,'surface_samples'),
                global_corrected_vs_anchor=integer(ga,'corrected_count'),global_damaged_vs_anchor=integer(ga,'damaged_count'),
                local_corrected_vs_anchor=integer(la,'corrected_count'),local_damaged_vs_anchor=integer(la,'damaged_count'),
                local_corrected_vs_global=gain,local_damaged_vs_global=damage,
                same_cell_both_count=sum(integer(r,'corrected_count')>0 and integer(r,'damaged_count')>0 for r in selected),
                same_cell_reference_supported_count=len(selected),
                global_correction_retained_by_local_count=derived['global_correction_retained_by_local_count'],
                global_correction_lost_by_local_count=derived['global_correction_lost_by_local_count'],
                global_damage_recovered_by_local_count=derived['global_damage_recovered_by_local_count'],
                additional_local_damage_count=derived['additional_local_damage_count'],
                proximity_transitions_are_temporal_or_area_truth=False,scientific_verdict=None)
            for key in ('precision','recall','f1'):
                previous,value=numeric(old,key,True),numeric(new,key,True)
                row['global_'+key]=previous;row['local_'+key]=value
                row['delta_'+key]=value-previous if previous is not None and value is not None else None
            result.append(row)
    return result,methods


def appearance_summary(rows,identities):
    result=[]
    index_unique(rows,('region','candidate','domain','name'))
    for (region,candidate),names in identities.items():
        if len(names)!=len(set(names)):raise ValueError('Duplicate frozen camera name in render identity')
        for domain in ('full_frame','fixed_prism_projected_bbox'):
            selected=[r for r in rows if r['region']==region and r['candidate']==candidate and r['domain']==domain]
            if {r['name'] for r in selected}!=set(names):raise ValueError('Appearance rows do not match frozen camera identity membership')
            for metric in ('psnr','ssim','lpips'):
                new_key={'psnr':'psnr_native_db' if domain=='full_frame' else 'psnr_cpu_float64_db',
                         'ssim':'ssim_native','lpips':'lpips_vgg_native_01'}[metric]
                old_key={'psnr':'parent_psnr_native_db','ssim':'parent_ssim_native','lpips':'parent_lpips_vgg_native_01'}[metric]
                assessed=[r for r in selected if r['status']=='ASSESSED']
                values=[(numeric(r,old_key,True),numeric(r,new_key,True)) for r in assessed]
                finite=[(a,b) for a,b in values if a is not None and b is not None]
                finite_pixels=sum(integer(r,'pixel_count') for r,(a,b) in zip(assessed,values) if a is not None and b is not None)
                result.append(dict(region=region,condition=candidate,domain=domain,metric=metric,
                    unit='dB' if metric=='psnr' else 'dimensionless',expected_camera_count=len(names),
                    assessed_domain_camera_count=len(assessed),finite_pair_count=len(finite),
                    unpaired_or_unmeasured_camera_count=len(names)-len(finite),
                    total_domain_pixels=sum(integer(r,'pixel_count') for r in assessed),
                    finite_paired_domain_pixels=finite_pixels,
                    mean_global=sum(a for a,b in finite)/len(finite) if finite else None,
                    mean_local=sum(b for a,b in finite)/len(finite) if finite else None,
                    mean_paired_delta=sum(b-a for a,b in finite)/len(finite) if finite else None,
                    averaging='arithmetic camera mean over identical finite pairs; not pooled-pixel PSNR',
                    status='ASSESSED_MATCHED_CAMERA_PAIRS' if finite else 'UNMEASURED_OR_NO_FINITE_PAIRS',
                    new_definition='CPU float64 ROI PSNR' if domain!='full_frame' and metric=='psnr' else 'native full-frame metric' if domain=='full_frame' else 'ROI metric unmeasured',
                    parent_definition='native float32 PSNR' if metric=='psnr' else 'native metric',scientific_verdict=None))
    return result


def fmt(value,percent=False,digits=3):
    if value is None:return '미평가'
    return f'{value*100:.2f}%' if percent else f'{value:.{digits}f}'


def korean_report(cfg,paired,methods,appearance,complete,missing,receipt_hash):
    lines=['# 국소 상보 depth refinement v2 — 실제 평가 요약','',
        '- scientific_verdict: null',f'- 상태: `{ "COMPLETE_18_DEVELOPMENT_SUMMARY" if complete else "PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION" }`',
        f'- 평가 완료 조건: {len(paired)}/18; 각 조건 1회; 평가 receipt SHA256: `{receipt_hash}`','']
    if complete:
        higher=sum(r['delta_f1'] is not None and r['delta_f1']>1e-12 for r in paired)
        lower=sum(r['delta_f1'] is not None and r['delta_f1']< -1e-12 for r in paired)
        lines += [f'Raw TSDF512·0.5m에서 대응 G 대비 LC의 F1 수치는 상승 {higher}조건, 하락 {lower}조건이다. '
                  '이 방향 집계는 정확도·완전성의 상충, 같은 부위의 수정·손상, 작은 차이의 재현성을 대신하지 않는다.','']
    else:
        lines += ['**18조건이 완결되지 않았다. 아래는 완료된 조건의 중간 관측이며 방법의 효과·우열 결론을 내리지 않는다.**','']
    lines += ['## 기존 G와 신규 LC 전체 조건','',
        'G는 기존 전역 제어이며 LC는 같은 지역·prior 계수·보호 상태의 국소 상보 가중이다. 정확도는 예측 표면 표본→관측 UAS, 완전성은 동일 UAS 원본점→삼각형 표면의 0.5m 미만 비율이다. '
        '수정/손상은 Anchor 대비 동일 참조점의 근접 분류 변화이며 구조의 정오·면적·시간적 유효성 판정이 아니다.','']
    for region in cfg['regions']:
        selected=[r for r in methods if r['region']==region]
        if not selected:continue
        lines += [f'### {region}','', '| 조건 | 정확도 | 완전성 | F1 | Anchor 대비 수정 / 손상 참조점 수 | 참조점 / 예측 표본 |',
                  '|---|---:|---:|---:|---:|---:|']
        for r in selected:
            changes='—' if r['method']=='ANCHOR' else f'{r["corrected_vs_anchor"]:,} / {r["damaged_vs_anchor"]:,}'
            lines.append(f'| {r["candidate"]} | {fmt(r["precision"],True)} | {fmt(r["recall"],True)} | {fmt(r["f1"])} | {changes} | {r["reference_count"]:,} / {r["surface_samples"]:,} |')
        lines.append('')
    lines += ['## 같은 부위의 수정과 손상','',
        '| 지역 / LC 조건 | Δ정확도 / Δ완전성 / ΔF1 | G 대비 수정 / 손상 참조점 수 | 같은 cell에서 둘 다 발생 / 참조 지지 cell | G의 수정 중 LC가 잃은 참조점 수 |',
        '|---|---:|---:|---:|---:|']
    for r in paired:
        lines.append(f'| {r["region"]} / {r["condition"]} | {fmt(r["delta_precision"])} / {fmt(r["delta_recall"])} / {fmt(r["delta_f1"])} | '
            f'{r["local_corrected_vs_global"]:,} / {r["local_damaged_vs_global"]:,} | {r["same_cell_both_count"]:,} / {r["same_cell_reference_supported_count"]:,} | {r["global_correction_lost_by_local_count"]:,} |')
    lines += ['', 'Δ비율은 0–1 단위이다. 두 변화가 같은 0.5m XY cell에 공존해도 같은 Gaussian이나 같은 연속 표면의 대응을 뜻하지 않는다. '
        '기존 G의 Anchor 대비 성공과 LC의 손상을 모두 보존하며, 약한 대조군 하나 또는 지역별 최적 조건만 고르지 않는다.','',
        '## 외관','', '각 셀은 G 평균 → LC 평균 (유한 대응 카메라/예정 카메라)이다. 정확한 대응 평균 차이·분모·pixel 수는 `appearance_paired_means.csv`에 남긴다.','',
        '| 지역 / 조건 | 전체 PSNR (dB) | 전체 SSIM | 전체 LPIPS | 고정 ROI PSNR (dB) |',
        '|---|---:|---:|---:|---:|']
    appearance_index={(r['region'],r['condition'],r['domain'],r['metric']):r for r in appearance}
    for item in paired:
        parts=[]
        for domain,metric in [('full_frame','psnr'),('full_frame','ssim'),('full_frame','lpips'),('fixed_prism_projected_bbox','psnr')]:
            r=appearance_index[item['region'],item['condition'],domain,metric]
            parts.append(f'{fmt(r["mean_global"])} → {fmt(r["mean_local"])} ({r["finite_pair_count"]}/{r["expected_camera_count"]})')
        lines.append(f'| {item["region"]} / {item["condition"]} | '+' | '.join(parts)+' |')
    lines += ['', '외관은 같은 유한 대응 카메라의 산술 평균이다. PSNR의 dB 평균을 전체 pixel 오차로 다시 계산한 PSNR로 해석하지 않는다. '
        '전체 영상은 native PSNR/SSIM/LPIPS, ROI는 신규 CPU float64 PSNR과 기존 native PSNR을 대조한다. ROI SSIM/LPIPS는 미측정이다. '
        '원사진의 관측 가능성·O/X와 현재성을 DA3 depth 잔차나 외관 지표에서 자동 추론하지 않는다.','',
        '## 평가 범위와 계산량','',
        'Raw512가 주 비교이고 post512는 보조 비교다. 모든 문턱(.1/.2/.25/.5/1/2m)과 raw/post 값은 `geometry_all_thresholds_raw_post.csv`, '
        '`paired_all_thresholds_raw_post.csv`에 함께 남긴다. 참조 피복과 prediction 결손은 `coverage.csv`, 원표면의 후처리 제거는 `postprocessing_effect.csv`, '
        '실행 누락·실패는 `missing_runs.csv`에서 별도로 확인한다. UAS 피복·절대 높이 datum과 물리적 가시성은 이 요약이 인증하지 않는다.','',
        '계산량 원값과 범위는 `compute.csv`를 유지한다. 기존 primary1024와 신규512, 기존 auxiliary512의 이미지 미저장, '
        'Anchor prefix 및 checkpoint 저장 횟수, driver 시간 측정 범위 차이가 있어 순수 방법 비용의 차감으로 읽지 않는다. '
        '기존 auxiliary512 비용은 정확한 산출물 identity가 확인된 경우에도 맥락용이며 같은 phase 비용은 아니다.','',
        '## 박사 기여의 구분','',
        '- **문제 차별성:** 유효한 기존 구조와 수정 필요 부분이 공존하는 조건을 다룬다. 이 3지역 개발 비교만으로 문제의 보편성이나 모집단 일반화를 확정하지 않는다.',
        '- **원인 설명:** 관측 차이는 국소 가중과 native controller 반응을 합친 결과다. 평균 배율 전역 대조·controller replay가 없어 공간 배분 고유 효과를 분리하지 못한다.',
        '- **방법 신규성:** 이 결과표는 상보 함수·정적 불일치 가중의 최초성이나 새 복원 원리를 증명하지 않는다. 기존 방법의 성공과 새 방법의 악화에 맞춰 기여 범위를 제한한다.',
        '- **검증 기여:** 같은 Anchor·입력·조건·참조점·문턱에서 기존 G의 수정/보존과 LC의 수정/손상을 함께 기록한다. 조건별 1회이므로 작은 차이의 재현성·반복 안정성을 주장하지 않는다.','',
        'Prior 근접도와 strict DA3 world-Z 잔차 strata는 평가용 proxy다. 큰 prior–영상 depth 차이가 어느 source의 정확성을 식별한다는 결론, '
        '기구축 형상의 재현만으로 현재 기하라는 결론은 내리지 않는다. 과학적 판정은 사람 검토에 남긴다.','']
    if missing:lines += [f'미완료/실패 목록 {len(missing)}행은 `missing_runs.csv`에 보존했다. 참조 부재로 재분류하지 않는다.','']
    return '\n'.join(lines)


def summarize(evaluation,config,output,allow_partial=False):
    started=time.time();evaluation=Path(evaluation).resolve();config=Path(config).resolve();output=Path(output).resolve()
    receipt_path=evaluation/'receipt.json';receipt=read_json(receipt_path);cfg=read_json(config)
    if receipt.get('schema')!='jbgs.local_complementary_evaluation.v2' or receipt.get('scientific_verdict','absent') is not None:
        raise ValueError('A v2 technical evaluation receipt with null verdict is required')
    if receipt.get('reference_used_for_training_or_parameter_selection','absent') is not False:
        raise ValueError('Explicit evaluation-only reference use is required')
    if cfg.get('scientific_verdict','absent') is not None:raise ValueError('Null configuration scientific verdict required')
    count=len(cfg['regions'])*len(cfg['conditions'])
    if count!=18 or receipt['expected_full_run_count']!=18:raise ValueError('Exact first18 configuration required')
    complete=(receipt['status']=='COMPLETE_DEVELOPMENT_EVALUATION' and receipt['run_count']==18 and not receipt['missing'])
    if receipt['status'] not in ('COMPLETE_DEVELOPMENT_EVALUATION','PARTIAL_DEVELOPMENT_EVALUATION'):
        raise ValueError('Only completed technical evaluation attempts may be summarized')
    if not complete and not allow_partial:raise ValueError('Full18 evaluation required; use --allow-partial only for explicit intermediate output')
    expected_config={r['sha256'] for r in receipt['inputs'] if r['path'].endswith('/experiment_v2.json')}
    if expected_config!={sha(config)}:raise ValueError('Evaluation and supplied frozen config digests differ')
    manifest=index_unique(receipt['outputs'],('path',));used=[dict(path=str(receipt_path),sha256=sha(receipt_path)),dict(path=str(config),sha256=sha(config))]
    def checked(relative):
        if (str(relative),) not in manifest:raise ValueError('Missing sealed evaluation output: '+str(relative))
        path=safe_child(evaluation,relative);record=manifest[(str(relative),)]
        if path.stat().st_size!=record['bytes'] or sha(path)!=record['sha256']:raise ValueError('Changed evaluation output: '+str(relative))
        used.append(dict(path=str(path),sha256=record['sha256'],bytes=record['bytes']));return path
    tables={};paths={}
    for name in CSV_NAMES:
        paths[name]=checked(name+'.csv')
        with paths[name].open(newline='') as stream:tables[name]=list(csv.DictReader(stream))
    validate_geometry_grid(tables['geometry_metrics'],cfg)
    validate_paired_grids(tables['paired_transitions'],cfg)
    validate_paired_grids(tables['anchor_global_local_transitions'],cfg,three_way=True)
    validate_all_three_way_accounting(tables['anchor_global_local_transitions'],tables['paired_transitions'])
    paired,methods=pair_summary(tables['geometry_metrics'],tables['paired_transitions'],tables['same_cell_changes'],
                               tables['anchor_global_local_transitions'],cfg,complete)
    if len(paired)!=receipt['run_count']:raise ValueError('Receipt and summarized local run counts differ')
    identities={}
    for row in paired:
        identity=read_json(checked(Path(row['region'])/row['condition']/'render_identity.json'))
        identities[row['region'],row['condition']]=[r['name'] for r in identity['records']]
    appearance=appearance_summary(tables['appearance_per_image'],identities)
    if output==evaluation or output.is_relative_to(evaluation) or evaluation.is_relative_to(output):
        raise ValueError('Summary output root must be separate from immutable evaluation attempt')
    attempt=safe_child(output,'attempt_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));attempt.mkdir(parents=True,exist_ok=False)
    write_json(attempt/'config_snapshot.json',cfg)
    write_csv(attempt/'paired_summary.csv',paired);write_csv(attempt/'all_methods_raw512_0.5m.csv',methods)
    write_csv(attempt/'appearance_paired_means.csv',appearance)
    aliases={'geometry_metrics':'geometry_all_thresholds_raw_post','paired_transitions':'paired_all_thresholds_raw_post'}
    for name,path in paths.items():shutil.copyfile(path,attempt/(aliases.get(name,name)+'.csv'))
    (attempt/'RESULT_ko_v2.md').write_text(korean_report(cfg,paired,methods,appearance,complete,tables['missing_runs'],sha(receipt_path)))
    code=Path(__file__);used.append(dict(path=str(code),sha256=sha(code),bytes=code.stat().st_size))
    helper=code.with_name('evaluation_utils_v2.py');used.append(dict(path=str(helper),sha256=sha(helper),bytes=helper.stat().st_size))
    final=dict(schema='jbgs.local_complementary_summary.v2',report_revision=REPORT_REVISION,
        status='COMPLETE_18_DEVELOPMENT_SUMMARY' if complete else 'PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION',
        scientific_verdict=None,task_id=cfg['task_id'],observed_condition_count=len(paired),expected_condition_count=18,
        raw_gt_or_model_loaded=False,parameter_selection_or_temporal_truth_inferred=False,
        full18_required_for_outcome_summary=True,inputs=used,wall_seconds=time.time()-started,
        outputs=[dict(path=str(p.relative_to(attempt)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(attempt.iterdir()) if p.is_file()])
    write_json(attempt/'receipt.json',final)
    return attempt,final


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evaluation',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-partial',action='store_true')
    args=parser.parse_args()
    if not Path('/.dockerenv').exists():raise RuntimeError('Docker required')
    attempt,receipt=summarize(args.evaluation,args.config,args.output,args.allow_partial)
    print(json.dumps(dict(status=receipt['status'],output=str(attempt),scientific_verdict=None)),flush=True)


if __name__=='__main__':main()
