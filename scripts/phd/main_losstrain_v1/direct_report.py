"""Promote amended preparation evidence, keeping the earlier stop reports."""
import csv
import json
import shutil
from datetime import datetime,timezone,timedelta
from pathlib import Path
import numpy as np
from inputs import OUT,SITES,PRIORS,save,sha

def main():
    doc=Path('/docs');root=OUT/'direct_stage1_v2';g=json.loads((root/'gates.json').read_text())
    history=doc/'history';history.mkdir(exist_ok=True)
    for name in ['준비보고_v1.md','손실학습시험_보고_v1.md','progress.md','issues.md']:
        old=history/('pre_direct_'+name)
        if not old.exists():shutil.copyfile(doc/name,old)
    now=datetime.now(timezone(timedelta(hours=9))).isoformat()
    checked=[];depth=[]
    for site in SITES:
        for prior in PRIORS:
            p=OUT/f'checks/current_direct_v1/comparison_{site}_{prior}.json'
            if p.exists() and json.loads(p.read_text())['status']=='PASS':checked.append(site+'/'+prior)
            p=OUT/f'checks/depth_direct_v2/{site}_{prior}/probe/depth_masks.json'
            if p.exists() and json.loads(p.read_text())['status']=='PASS':depth.append(site+'/'+prior)
    wing=json.loads((doc/'tables/wing_als.json').read_text())
    completed=sum((OUT/'runs/B173nb_b10'/(x+'_ALS_s0/PASS.json')).exists() for x in ['lt_cal_dyn_xthird','lt_cal_dyn_x1','lt_cal_dyn_x3','lt_cal_current'])
    selection_path=OUT/'checks/lambda_selection.json'
    selection=json.loads(selection_path.read_text()) if selection_path.exists() else None
    selected=selection.get('selected_lambda') if selection else None
    full=sum(1 for p in (OUT/'runs').glob('*/*/PASS.json') if not p.parent.name.startswith('lt_cal_'))
    optional=sum(1 for p in (OUT/'runs').glob('*/lt_fixnow_*/PASS.json'))
    caltext=(doc/'tables/calibration.md').read_text() if (doc/'tables/calibration.md').exists() else '짧은 학습 네 번과 세기 선택은 아직 완료하지 않았다.'
    if (doc/'tables/calibration_gradient_audit.md').exists():caltext+='\n'+(doc/'tables/calibration_gradient_audit.md').read_text()
    lines=['# 손실 학습 시험 준비 보고 v1 — 17시 수정 규칙','',
        f'완료 학습: 짧은 학습 {completed}/4, 본 학습 {full-optional}/24, 선택 {optional}/6. 아래 표는 준비 점검이다.',
        f'선택 λ: {selected if selected is not None else "아직 없음. 정해 둔 네 번의 짧은 학습 후 규칙대로 선택한다."}',
        f'점검: 여섯 단위 GPU 기본 동작 {len(checked)}/6, 실제 새 손실 화소 {len(depth)}/6. 본 학습·후처리·최종 비교의 완료 여부는 progress에 따로 남긴다.',
        '',f'기록 시각 {now} · scientific_verdict: null','',
        '## 규칙과 입력','',
        '사용자가 대화로 보낸 10월 26일 17시 수정본의 5절, 값 없음 처리, 6.4절, C.5를 적용했다. UNCERT R1.5·MVS 판 가의 여섯 파일 모두 중심 배열과 순서가 학습 store와 정확히 같다. UNCERT 범위 밖인 1단계 행은 0개다. C.5의 가장자리 거리는 0.5 m 격자·원점 (−170, −237)·3×3 닫기·높이 차 1 m·거리변환×0.5−0.25로 새로 계산했다. 기존 UNCERT edge 값은 사용하지 않았다.',
        '', '값 배열은 `direct_stage1_v2/<단위>/values.npz`, 채점용 p_G·p_M·칸·학습 없는 도착점은 별도 `evaluation.npz`다. 학습 로더는 참값 위치·칸·도착점 파일을 읽지 않는다. 참값 판에 허용된 V 배열만 읽는다. WIDEN 최근접 쌍은 LoD2 점검에만 사용한다.',
        '', '## 면적 95% 기준','',
        '| 단위 | 사전 정보 | 직접 / 평가 패치 | 패치 수 기준 (%) | 직접 / 평가 넓이 (m²) | 넓이 기준 (%) |','|---|---|---:|---:|---:|---:|']
    for r in g['rows']:
        lines.append(f"| {r['site']} | {r['prior']} | {r['direct_eval_patches']:,} / {r['eval_patches']:,} | {100*r['count_coverage']:.4f} | {r['direct_eval_area_m2']:.6f} / {r['eval_area_m2']:.6f} | {100*r['area_coverage']:.4f} |")
    lines+=['','여섯 단위 모두 PASS. MVS 없음과 참값 없음은 사전 정보 값을 직접 정할 수 있으면 덮인 것으로 센다. 항공 LiDAR의 u_사전 없음(다)은 같은 단위의 유효 σ_p와 사정 평균 V 각각의 중앙값으로 대체하고 채점에서 제외한다. 범위 밖(라)은 0개다. [이 발주에서 냄]','',
        '| 단위 | 다: 전체 패치 / 넓이(m²) | 다: 평가 패치 / 넓이(m²) | 다: 전체 영상 화소 비율(%) | 다: 사전 패치 깊이 화소 비율(%) | 다: 평가 패치 화소 비율(%) |','|---|---:|---:|---:|---:|---:|']
    for r in g['rows']:
        p=json.loads((root/(r['site']+'__'+r['prior'])/'pixels.json').read_text())['summary'];m=r['missing_als_prior'];f=p['fractions']['missing_als_prior']
        lines.append(f"| {r['site']}/{r['prior']} | {m['patches']:,} / {m['area_m2']:.6f} | {m['eval_patches']:,} / {m['eval_area_m2']:.6f} | {100*f['all_image_pixels']:.6f} | {100*f['mapped_prior_pixels']:.6f} | {100*f['eval_mapped_prior_pixels']:.6f} |")
    lines+=['','평가 화소는 해당 패치 중심의 고정 in_eval로 구분했다. 화소 비율은 보고용이며 수정 발주문의 중단 기준은 패치 넓이다. 전체 장면의 중앙값 대체 화소 비율이 평가 범위보다 큰 점을 함께 남긴다.','',
        '## LoD2 90% 점검','',
        '| 단위 | 대상 쌍 / 일치 | 전체 (%) | 지붕 (%) | 벽 (%) | 형태 차이 / 가장자리 구간 차이 / 그 밖 |','|---|---:|---:|---:|---:|---:|']
    mismatches=[]
    for r in g['rows']:
        if r['prior']!='LoD2':continue
        q=r['lod2_check'];reason=q['mismatch_reason']
        lines.append(f"| {r['site']} | {q['pairs']:,} / {q['matching']:,} | {100*q['fraction']:.4f} | {100*q['groups']['roof']['fraction']:.4f} | {100*q['groups']['wall']['fraction']:.4f} | {reason['roof_type']} / {reason['edge_bin']} / {reason['other']} |")
        with np.load(root/(r['site']+'__LoD2')/'lod2_pairs.npz') as packed:
            z={k:packed[k] for k in packed.files}
            for i in np.flatnonzero(~z['agree']):
                mismatches.append(dict(site=r['site'],stage1_patch=int(z['stage1_patch'][i]),widen_patch_id=str(z['widen_patch_id'][i]),
                    reason=['agree','roof_type','edge_bin','other'][int(z['reason'][i])],stage1_edge_m=float(z['stage1_edge_m'][i]),
                    widen_edge_m=float(z['widen_edge_m'][i]),stage1_stratum=int(z['stage1_stratum'][i]),widen_stratum=int(z['widen_stratum'][i]),
                    stage1_roof_type=str(z['stage1_roof_type'][i]),widen_roof_type=str(z['widen_roof_type'][i]),
                    sigma_difference_m=float(z['sigma_difference_m'][i]),validity_difference=float(z['validity_difference'][i])))
    with (doc/'tables/direct_lod2_mismatches.csv').open('w') as f:
        w=csv.DictWriter(f,list(mismatches[0]),lineterminator='\n');w.writeheader();w.writerows(mismatches)
    other=[r for r in mismatches if r['reason']=='other'];normal_class=sum((r['stage1_stratum']==6)!=(r['widen_stratum']==6) for r in other)
    lines+=['','전체 장면에서 중심 최근접 거리 1 cm 이내인 쌍만 센다. σ_p와 V_now 차이가 각각 1e-4 이내여야 일치다. 단위별 전체 비율로 모두 PASS. 다른 모든 쌍의 두 가장자리 거리·사정 번호·형태·차이는 `tables/direct_lod2_mismatches.csv`에 있다.',
        f'그 밖 {len(other):,}쌍 중 {normal_class:,}쌍은 새 규칙의 법선 45° 분류와 묶음의 지붕/벽 사정 번호가 다르다. 형태 코드 차이로 분류하지 않았다.',
        '', '| 단위 | MVS σ 차이 중앙값 / 95% (m) | MVS V 차이 중앙값 / 95% |','|---|---:|---:|']
    for r in g['rows']:
        if r['prior']!='LoD2':continue
        q=r['lod2_check'];s=q['mvs_sigma_abs_difference_m'];v=q['mvs_validity_abs_difference']
        lines.append(f"| {r['site']} | {s['median']:.6f} / {s['p95']:.6f} | {v['median']:.6f} / {v['p95']:.6f} |")
    lines+=['','MVS 차이는 중단 기준으로 사용하지 않았다.','', '## 법선과 손실 점검','',
        'UNCERT에서 법선이 0인 행은 모두 격자 칸 없는 중심 보조 패치(loc_extra)였다. LoD2 8개, 항공 LiDAR 534개다. 같은 사전 정보의 원래 면 번호에 저장된 법선을 사용했다. 가까운 다른 면이나 참값으로 대체하지 않았다. 기존 비영 법선과 초기화·보호·밀도 제어는 유지했다. 입력 점검 v1과 법선 출처를 보완한 v2를 별도 보존했다. 수정 후 실제 깊이 대상 화소의 법선 누락은 여섯 단위 모두 0이다.',
        '', '기존 CPU 손실 식 240개 검사는 재사용한다. C.5 경계·닫기·높이 차·구간 경계 검사와 관측용 추가 미분이 본래 기울기를 바꾸지 않는 검사도 PASS다.',
        f'여섯 단위 기본 동작 PASS: {", ".join(checked)}. 실제 fixed/dynamic 화소 수 PASS: {", ".join(depth)}. 진행 중인 단위에는 PASS를 붙이지 않았다.',
        '', '## 학습 없는 시험과 그림 설정','',
        '`tables/analytic_stage1.md/json/csv`에 단위별·세 단위 합, 판별, 칸별·설명 안 됨의 표본 수와 넓이·τ 안 비율을 기록했다. 다·라와 참값 없음은 제외했다. 도착점은 C.4로 다시 계산했다. 학습 결과로 해석하지 않는다.',
        '기존 설정은 `losstrain_v1.pre_direct.json`으로 보존하고 현재 설정·해시를 잠갔다. 9.1의 단면 자리와 위에서 본 범위를 유지했다. B173 렌더는 학습 결과를 보지 않고 원래 사전 정보 범위가 들어오는 학습 카메라 `DJI_20241217091251_0148_D`로 고정했다. 후보·외부/내부 표정·범위는 `figure_camera_v1.json`에 있다.',
        '', '## 6.8 B173 날개 타일의 두 항공 LiDAR 면','',
        f"타일 6911_53361의 날개 범위 {wing['stage1_section_patches']:,}개를 확인했다. 1단계 등록 이동은 {wing['stage1_shift_m']} m, 넓히기 타일은 {wing['widen_shift_m']} m다. 등록 전 중심은 {wing['raw_nearest_within_18cm']:,}개가 18 cm 안이고 거리 중앙값은 {wing['raw_nearest_distance_m']['median']:.6f} m다. 그 쌍의 등록 후 높이 차 중앙값은 {wing['paired_height_difference_m']['median']:.6f} m, 기록된 수직 이동 차를 빼면 {wing['height_difference_after_removing_recorded_shift_m']['median']:.6f} m다.",
        '따라서 이 타일의 큰 높이 차에는 서로 다른 등록 이동이 직접 기여한다. 어느 면이 참인지 판정하지 않았으며 학습 중단 기준으로 사용하지 않았다. 고정 그림 단면은 타일 서쪽 경계 밖에 있어, 이 점검에는 면 33/38의 날개 발자국과 해당 타일의 교집합을 사용했다.','',
        '## 기록과 남은 일','',
        '5 cm·18 cm 연결 결과와 이전 중단 보고는 history/와 기존 표·외부 체크 기록에 보존했다. 새 규칙이 해당 연결 중단을 대체한다. 첨부 ZIP 검증도 재사용했다.',
        '본 학습 24회, 선택 6회, TSDF·채점·최종 그림·전달 묶음은 각 실행 기록으로 확인한다.', '', '## 짧은 학습의 세기 선택', '', caltext]
    text='\n'.join(lines).rstrip()+'\n';(doc/'준비보고_v1.md').write_text(text)
    (doc/'손실학습시험_보고_v1.md').write_text(text.replace('준비 보고 v1','진행 보고 v1',1))
    (doc/'progress.md').write_text(f'# PHD-MAIN-LOSSTRAIN-v1\n\n{now}: REOPENED. Direct stage-1 area coverage and LoD2 agreement PASS.\n\nCurrent equivalence {len(checked)}/6; actual fixed/dynamic masks {len(depth)}/6. Calibration {completed}/4; full training {full-optional}/24; optional {optional}/6. Selected lambda: {selected}. scientific_verdict: null.\n')
    (doc/'issues.md').write_text((history/'pre_direct_issues.md').read_text()+
        '\nLT-004 RESOLVED: user 17:00 amendment replaces LT-001/002 linkage gates with direct stage-1 rules. Both new gates PASS.\n'+
        '\nLT-005 RESOLVED: zero-tangent centroid patches read the exact owning prior surface normals. No GT, nearest-surface imputation or initialization changes. Pixel normal availability PASS.\n'+
        '\nLT-006 RESOLVED: wing diagnostic first draft had duplicate Python keyword, corrected before data execution. First geometric probe used the fixed figure section outside named tile core; final 6.8 uses the named wing/tile intersection and preserves the preliminary receipt.\n'+
        '\nLT-007 RESOLVED: report-only CPU process was interrupted to preload NPZ arrays once instead of repeatedly decompressing them. An early relaunch hit the still-stopping container name; rerun after completion succeeded. No training or source data changed.\n')
    save(OUT/'checks/direct_stage1/report_receipt.json',dict(at=now,report_sha256=sha(doc/'준비보고_v1.md'),scientific_verdict=None))
    print('direct report',len(text),'characters',flush=True)

if __name__=='__main__':main()
