"""Deliver a verified timing-gate partial report; never label it completed Stage A."""
import csv,hashlib,io,json,zipfile
from preflight import C,D,O,R,Path,sha,dump,now
BASE=O/'r1';S=Path(__file__).parent
EX=dict(label='실험 지역과 사진 점을 공유해 뺀 핵심점',count=73,area_m2=5.442552935831812)
EXLINE='실험 지역과 사진 점을 공유해 뺀 핵심점: **73개 / 5.442552935831812 m²**. 모든 셈에서 미리 제외했다.'
LABELS={'ALS_1':'항공 LiDAR 지붕','LoD2_1':'LoD2 지붕','LoD2_2':'LoD2 벽'}

def replace_status(path,prefix,line):
    lines=[s for s in path.read_text().splitlines() if not s.startswith(prefix)]
    path.write_text('\n'.join(lines).rstrip()+'\n\n'+line+'\n')

def table(name,rows,source):
    dump(D/f'tables/{name}.json',dict(source=source,source_tag='[이 발주에서 냄]',rows=rows,excluded_shared_photo_cores=EX,scientific_verdict=None))
    keys=list(dict.fromkeys(k for r in rows for k in r));fields=['row_type']+keys+['excluded_core_count','excluded_area_m2']
    with (D/f'tables/{name}.csv').open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader()
        for r in rows:wr.writerow(dict(row_type='measurement',**{k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()}))
        wr.writerow(dict(row_type='excluded_shared_photo_cores',excluded_core_count=73,excluded_area_m2=EX['area_m2']))
    md=[f'# {name} [이 발주에서 냄]','',EXLINE,'',f'출처: `{source}`','', '| '+' | '.join(keys)+' |','| '+' | '.join('---' for _ in keys)+' |']
    for r in rows:md.append('| '+' | '.join(str(r.get(k,'')) for k in keys)+' |')
    (D/f'tables/{name}.md').write_text('\n'.join(md)+'\n')

def main():
    gate=json.loads((BASE/'photo_time_gate.json').read_text());audit=json.loads((BASE/'independent_reply1_audit.json').read_text());cal=json.loads((BASE/'geometry_calibration.json').read_text())
    assert gate['status']=='STOP_PHOTO_TIME_ESTIMATE' and audit['status']=='PASS_REPLY1_INDEPENDENT_AUDIT'
    assert gate['parity']['status']=='PASS_CPU_GPU_PHOTO_PARITY'
    assert not (O/'core_points').exists() and not (O/'photo_points').exists()
    scope=[dict(group=k,**v) for k,v in audit['rows'].items()];table('reply1_scope',scope,'r1/independent_reply1_audit.json; retained development cores only')
    table('reply1_als_radius',cal['als_radius_candidates'],'r1/als_radius.json; all retained ALS cores with a defined fitted normal')
    params=[dict(parameter='sigma_W_m',group='shared',value=cal['sigma_W_m'],sample_count=cal['building_count'],sample_unit='building')]
    for key,val in cal['r_m'].items():
        # The calibration agreement count is reconstructed from retained outputs.
        prior,kind=key.split('_');count=0
        import numpy as np
        for p in (BASE/'geometry').glob(f'*__{prior}.npz'):
            with np.load(p) as z:count+=int((z['agreement_for_calibration']&(z['kind']==int(kind))).sum())
        params.append(dict(parameter='r_m',group=key,value=val,sample_count=count,sample_unit='core'))
    table('reply1_geometry_parameters',params,'r1/geometry_calibration.json; no truth in calibration')
    table('reply1_photo_timing',gate['rows'],'r1/photo_benchmark/preparation.json and timing_cpu.json / timing_cuda.json; 200 identical points')
    table('reply1_missing_uncertainty',[audit['missing_u_recalculation']],'r1/ring_recompute; inherited finite values unchanged')
    table('reply1_photo_parity',[dict(field=k,**v) for k,v in gate['parity']['fields'].items()],'identical 200-point planes.npz; CPU and one RTX 3090')
    # No early/initial preparation metadata is swept into the new package.
    for name in ['scope_audit_reply1.json','input_receipt_reply1.json','geometry_calibration_interim.json','reply1_verification.json','photo_time_gate_reply1.json','photo_precision_r0_issue.json']:
        p=D/'tables'/name;obj=json.loads(p.read_text());obj['excluded_shared_photo_cores']=EX;dump(p,obj)
    lock=json.loads((C/'judgecheck_v1.reply1.lock.json').read_text());cpu,gpu=gate['rows'];prep=cpu['preparation_seconds'];N=cpu['target_count_types_1_2']
    scope_md='\n'.join(f"| {LABELS[r['group']]} | {r['building_count']} | {r['core_count']:,} | {r['area_m2']:.9f} |" for r in scope)
    timing_md='\n'.join(f"| {'CPU 4개' if r['device']=='cpu' else 'GPU 1장 (RTX 3090)'} | {r['preparation_seconds']:.6f} | {r['scoring_seconds']:.6f} | {r['seconds_per_point']:.9f} | {r['linear_estimate_hours']:.6f} | {r['limit_hours']} |" for r in gate['rows'])
    radius_md='\n'.join(f"| {r['radius_m']} | {r['count']:,} | {r['q25']} | {r['median']} | {r['q75']} |" for r in cal['als_radius_candidates'])
    um=audit['missing_u_recalculation']
    text=f'''# 판단검증 보고 가 v1 — 회신 1 적용 후 시간 점검 중단 (부분 보고)

작업: PHD-MAIN-JUDGECHECK-v1 · 작성: {now()} · scientific_verdict: null

1. 범위: 개발용 항공 LiDAR 지붕 122동, LoD2 125동. 아래 표는 공유 핵심점 73개를 모든 셈에서 뺀 값이다.
2. 본 규칙·늘 사전 정보·늘 영상의 틀린 비율: **미계산**. 결과 0 또는 성공으로 표시하지 않았다.
3. 7절 본 방법·모두 정답의 τ 안 비율: **미계산**.
4. 상태: **STOP_PHOTO_TIME_ESTIMATE**. 정식 단계 가 완료 전 중단이며, 6~7절 정량 표와 8절 그림은 미완료다.
5. 200점 준비 {prep:.6f}초, CPU 채점 {cpu['scoring_seconds']:.6f}초, GPU 채점 {gpu['scoring_seconds']:.6f}초. 다른 GPU 작업을 기다린 시간 0초. 학습 없음.

## 회신 1 적용과 입력 범위

{EXLINE}

사진 점의 모든 소속 건물 ID를 패치 ID와 사진 연결표로 다시 만들었다. 항공 LiDAR 지붕뿐 아니라 LoD2 지붕·벽, 개발용과 확인용의 공유도 검사했다. 추가 제외 대상은 없었다. 확인용에서는 소속 번호만 확인했으며 곡선·값은 열지 않았다. 단계 나는 시작하지 않았다.

**처음 연결에서 읽은 공유 곡선 22개에서 나온 값은 이번 재개 계산의 어떤 표·그림·설정에도 들어가지 않았다.** 최초 준비는 재현 기록으로만 보존하며 이번 전달 ZIP에 포함하지 않았다. 새 입력은 원본에서 허용된 행만 다시 읽어 `/out/r1/`에 만들었다. 기존 곡선 재계산이나 사진 점 분할은 하지 않았다.

| 묶음 | 건물 수 | 핵심점 수 | 넓이 (m²) |
|---|---:|---:|---:|
{scope_md}

{EXLINE}

원시 MVS·LiDAR 둘레 자료는 회신 1의 4번에 따라 사용할 수 있다. 이웃의 원시 점·화소가 섞인 것을 이유로 중단하지 않았다. 실험 지역 소유 패치·핵심점·사진 점·곡선·판단·참값을 새 셈에 쓰지 않았다.

최종 설정 저장 시각: {lock['at']}. SHA-256: `{lock['config_sha256']}`. 회신 1 적용 직후의 계산 전 설정 SHA-256은 `37d88a061463bf9b1477f4b3a8b5c245da2e95a9f6f2a158f8eaf132577b6618`이다. 이후 아래 수치 정밀도 수정만 덧붙였으며 앞 설정은 `revisions/r0/`, `revisions/r1/`에 보존했다.

## 기하 계산 — 완료한 부분 [이 발주에서 냄]

항공 LiDAR 법선, 위아래 10 m 원통, 누락 MVS 고리 불확실도 재계산을 완료했다. LoD2는 중심·법선·반지름이 같은 JUDGENUM의 10 m 원통 캐시를 SHA-256과 행 일치 검사 후 사용했다. 원통 구현은 독립 기준 계산 720개 검사를 통과했다.

LiDAR 원통 반지름은 **0.75 m**를 골랐다. 법선이 정의된 핵심점 501,646개가 반지름 선택의 분모다. 예상 0.55 m와 다르지만 고르는 규칙은 바꾸지 않았다.

| 반지름 (m) | 핵심점 수 | 점 수 25% | 점 수 중앙값 | 점 수 75% |
|---|---:|---:|---:|---:|
{radius_md}

{EXLINE}

넓은 범위 오차 σ_W는 **{cal['sigma_W_m']*100:.9f} cm**, 기준을 채운 건물 **{cal['building_count']}동**이다. 건물별 d 중앙값의 10·90%는 {cal['building_median_q10_q90_m'][0]*100:.9f}, {cal['building_median_q10_q90_m'][1]*100:.9f} cm다.

정합 오차 r는 항공 LiDAR 지붕 **{cal['r_m']['ALS_1']*100:+.9f} cm**, LoD2 지붕 **{cal['r_m']['LoD2_1']*100:+.9f} cm**, LoD2 벽 **{cal['r_m']['LoD2_2']*100:+.9f} cm**다. 참값을 쓰지 않고 계산했으며 별도 계산으로 재검산했다. 단계 나에 쓸 값의 최종 잠금은 사용자 회신 전이다.

누락 u_M {um['attempted']:,}개를 같은 고리 정의로 다시 확인해 {um['recovered']:,}개를 구했고, {um['unavailable']:,}개는 여전히 확인 불가로 남겼다. 유효한 기존 u_M은 전부 그대로다. 법선 규칙 미충족, 사전 정보 높이 없음, 5 m·10 m 결측 넓이는 `tables/reply1_scope.*`에 표본 수와 함께 남겼다.

참값의 새 법선 위치, 새 칸, 정밀도 확인과 5% 확인은 아직 계산하지 않았다. 따라서 6.5 전체가 완료됐다는 뜻은 아니다.

## 사진 시간 어림과 중단 근거 [이 발주에서 냄]

참값 없이 정한 대상 1(한계 밖)과 대상 2(묶음마다 일치 표본 최대 5,000)의 합은 **{N:,}점**이다. 씨앗 20261102로 여기서 무작위 200점을 고정했다. 7절 전용 대상 3은 미산정이므로 {N:,}는 **대상 수의 하한**이다. 이 시간 측정을 전체 대상이 모두 정해진 측정으로 표시하지 않는다.

200점에서 사전 정보 면은 200개, MVS 면은 153개였다. 두 평면, 높이 범위, 매 높이의 면 안쪽 마스크를 같은 입력으로 CPU와 GPU에서 채점했다. 529장의 관련 학습 사진을 한 장씩 읽어 그 사진의 점들을 함께 처리했다. CPU/GPU에서 유효값이 있는 곳, 사용 영상 수, 영상 축소 단계가 일치했고 점수·무늬 값도 검증 허용 오차 안에서 일치했다. 사진 점수는 아직 기준 t나 판단·성능 표로 사용하지 않았다.

처음 float32 보간·누적에서는 낮은 무늬 표본의 전체 곡선 CPU/GPU 차이가 최대 0.0078153163으로 검사에 실패했다(최고 점수 차이는 2.98e-7). 보간과 NCC 누적을 float64로 고친 뒤 **같은 200점**을 재측정했고 같은 허용 오차를 통과했다. 곡선·점수의 정의, 사진·마스크·높이 표본, 검증 허용 오차는 바꾸지 않았다. 앞 코드·설정·결과는 재현 기록으로 남겼다. 아래 시간은 수정 뒤 값이다.

발주문 4.5의 `200점에 걸린 시간 ÷ 200 × 대상 수`를 준비와 채점을 포함해 적용했다.

| 장치 | 준비 (초) | 채점 (초) | 점당 (초) | 단순 외삽 (시간) | 중단 상한 (시간) |
|---|---:|---:|---:|---:|---:|
{timing_md}

{EXLINE}

**시간 어림의 한계:** 공통 타일 읽기와 KD-tree 생성, 사진 디코딩도 이 단순 곱에서는 반복해서 곱해진다. 전체를 타일·사진별로 묶으면 줄어들 수 있다. 위 숫자는 발주 방식의 보수적인 외삽이며 실제 전체 소요시간이나 그 하한이 아니다. 아직 전체 규모에서 비용을 분리한 시간은 측정하지 않았다.

참고로 **채점만** 단순 외삽하면 CPU {cpu['score_only_linear_hours']:.6f}시간, GPU {gpu['score_only_linear_hours']:.6f}시간이다. 이는 필요한 평면·마스크·사진 선택 준비를 뺀 값이므로 전체 작업 시간으로 대신 쓰지 않는다. 디코딩과 산술 시간도 `tables/reply1_photo_timing.*`에 분리했다. GPU 1장의 산술은 빨랐지만 사진 읽기 등이 전체 시간의 대부분이었다.

발주문 1절 12번: **“4.5의 시간 어림이 GPU 한 장으로 48시간, CPU로만 72시간을 넘으면 멈추고 여쭙는다.”** 이 조건에 따라 전체 사진 계산을 시작하지 않았다. 현재 결과를 바탕으로 공통 준비비용과 점당 반복비용을 분리한 시간 어림을 추가로 한 뒤 계속할지 회신이 필요하다. 이미 얻은 설정·기하 값을 바꾸는 제안은 아니다.

## 미완료 및 넘기지 않은 경계

- 사진 기준 t, 전체 옛 곡선 재해석, 고친 사진의 전체 채점·판단: 미완료.
- 6.1~6.5, 7.2 정량 성능 표: 미완료. 현재 표는 범위·기하 기준·시간 점검 표다.
- 8.1 결과 지도와 8.2 조각 모음: 미작성. 사진을 보고 원인을 붙이지 않았다.
- 새 법선의 참값·칸, 시선 검사·영역, 조합 높이: 미계산.
- 발주 2절과 나란히 비교할 수 있는 값은 σ_W, r, 반지름뿐이다. 기대 대비 성능 결론은 내리지 않는다.
- 확인용 측정값·곡선 미열람, 단계 나 미시작. scientific_verdict: null.

## 전달 및 재현 범위

이번 ZIP은 **회신 1과 시간 중단 근거의 점검 묶음**이며, 완료된 `_가.zip` 결과 묶음이 아니다. 보고서, 새 표·설정·스크립트, 200점 평면/마스크·CPU/GPU 점수, 검증 기록과 SHA256SUMS를 담는다. 처음 준비 파일·공유 곡선은 제외한다.

전체 원시 자료 및 263만 핵심점의 중간 배열은 로컬 외부 저장소에 남긴다. `resumed_lineage_final_hashes.json`은 그 파일들의 해시와 경로를 담는다. 원시 이웃 파일의 바이트 해시는 계산 후 결속한 기록이며 계산 전 해시 잠금으로 주장하지 않는다. 설정과 방법 잠금은 계산 전에 했다. CRC·SHA-256 검증은 묶음 무결성 검증이며 과학적 성능 판단이 아니다.
'''
    assert len(text)<20000
    (D/'판단검증_보고가_v1.md').write_text(text)
    replace_status(D/'issues.md','- JC-006 — RESOLVED_NUMERICALLY',f'- JC-006 — RESOLVED_NUMERICALLY — {now()}: 동일 200점의 float64 CPU/GPU 재측정이 원래 허용 오차를 통과했다. 처음 실패를 삭제하거나 허용 오차를 완화하지 않았다. 과학적 성능 검증은 아직 하지 않았다.')
    replace_status(D/'issues.md','- JC-005',f'- JC-005 — OPEN — STOP_PHOTO_TIME_ESTIMATE: 200점 준비+채점 단순 외삽 CPU {cpu["linear_estimate_hours"]:.6f} h / GPU {gpu["linear_estimate_hours"]:.6f} h. 공통 비용이 곱해지는 한계 명시. 전체 사진 계산 및 6~8절 미진행. 발주 1.12에 따라 회신 대기.')
    lines=[s for s in (D/'progress.md').read_text().splitlines() if ': 현재 상태 **STOP_PHOTO_TIME_ESTIMATE**' not in s];(D/'progress.md').write_text('\n'.join(lines)+'\n')
    with (D/'progress.md').open('a') as f:f.write(f'\n- {now()}: 현재 상태 **STOP_PHOTO_TIME_ESTIMATE**. CPU/GPU 200점 및 독립 제외·기하 재검산 PASS. 준비 포함 단순 외삽 CPU {cpu["linear_estimate_hours"]:.6f} h / GPU {gpu["linear_estimate_hours"]:.6f} h. 보고 가는 부분 보고이며 완료된 단계 가가 아니다. 전체 사진 셈·정량 성능·그림·단계 나를 시작하지 않고 회신 대기.\n')
    dump(C/'stage_a_derived_parameters.reply1.json',dict(at=now(),status='development_computed_not_authorized_for_stage_b',
        sigma_W_m=cal['sigma_W_m'],r_m=cal['r_m'],als_radius_m=cal['als_selected_radius_m'],photo_threshold_t=None,
        source_sha256=sha(BASE/'geometry_calibration.json'),excluded_shared_photo_cores=EX,scientific_verdict=None))
    files=[]
    for p in sorted(C.glob('*')):
        if p.is_file() and (p.name in ['judgecheck_v1.json','reply_1.txt','order_v1.txt'] or 'reply1' in p.name or p.name.startswith('photo_')):files.append((p,'configs/'+p.name))
    script_names=['preflight.py','selected_npz.py','prepare.py','authorize_reply1.py','stage_a_inputs.py','u_core.py','cylinders.cpp','cylinder.py','geometry.py','ring_kernel.py','ring_context.py','ring_recompute.py','calibrate_geometry.py','photo_cameras.py','photo_targets.py','photo_planes.py','photo_score.py','verify_photo_math.py','audit_reply1.py','benchmark_gate.py','record_lineage.py','diagnose_photo_parity.py','amend_photo_precision.py','deliver_reply1.py','verify_reply1_delivery.py','run_cpu.sh','run_gpu.sh']
    files.extend((S/name,'scripts/'+name) for name in script_names)
    files.extend((D/name,'docs/'+name) for name in ['판단검증_보고가_v1.md','progress.md','issues.md'])
    files.append((D/'tables/photo_precision_r0_issue.json','docs/tables/photo_precision_r0_issue.json'))
    files.extend((p,'docs/tables/'+p.name) for p in sorted((D/'tables').glob('reply1_*')))
    for name in ['scope_audit.json','input_receipt.json','geometry_calibration.json','als_radius.json','cylinder_verification.json','independent_reply1_audit.json','photo_benchmark_selection.json','photo_time_gate.json','resumed_lineage_final_hashes.json']:
        files.append((BASE/name,'evidence/'+name))
    for p in sorted((BASE/'photo_benchmark').iterdir()):
        if p.is_file():files.append((p,'evidence/photo_benchmark/'+p.name))
    files.append((BASE/'photo_benchmark/revisions/r0/parity_diagnosis.json','evidence/photo_benchmark/precision_r0_diagnosis.json'))
    archive=D/'PHD-MAIN-JUDGECHECK-v1_회신1_시간점검.zip';hashes={name:sha(p) for p,name in files}
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in files:z.write(p,name)
        z.writestr('SHA256SUMS',''.join(f'{h}  {name}\n' for name,h in hashes.items()))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert not any(n.startswith(('inputs/','photo_inputs/','source_snapshots/','holdout/')) for n in z.namelist())
        for name,h in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==h
    assert archive.stat().st_size<400_000_000
    receipt=dict(at=now(),status='PASS_REPLY1_TIME_GATE_PACKAGE_INTEGRITY',archive=archive.name,bytes=archive.stat().st_size,sha256=sha(archive),
        files=len(files),crc_verified=True,member_sha256_verified=True,initial_preparation_included=False,
        report_a_complete=False,stage_b_started=False,scientific_verdict=None)
    dump(D/'delivery_reply1_receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False))

if __name__=='__main__':main()
