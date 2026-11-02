"""Package the verified input stop. This is not Report A or a result archive."""
import csv
import io
import json
from pathlib import Path
import zipfile
from preflight import C,D,O,R,sha,dump,now


def main():
    a=json.loads((O/'photo_scope_audit.json').read_text())
    check=json.loads((O/'stop_verification.json').read_text())
    join=json.loads((O/'input_join.json').read_text())
    assert a['status']=='STOP_PHOTO_POINT_SCOPE_CONFLICT'
    assert check['status']=='PASS_STOP_EVIDENCE_VERIFICATION'
    assert not (O/'core_points').exists() and not (O/'photo_points').exists()
    totals=[]
    for prior in ['ALS','LoD2']:
        rr=[r for r in join['rows'] if r['prior']==prior]
        totals.append(dict(prior=prior,buildings=join['building_count'][prior],
            core_points=sum(r['core_points'] for r in rr),area_m2=sum(r['area_m2'] for r in rr)))
    dump(D/'tables/input_scope_totals.json',dict(rows=totals,source='input_join.json; selected development rows',scientific_verdict=None))
    rows=[]
    for x in a['rows']:
        rows.append({k:(';'.join(map(str,v)) if isinstance(v,list) else v) for k,v in x.items()})
    with (D/'tables/photo_scope_audit.csv').open('w',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
    md=['# 사진 점 경계 확인 [이 발주에서 냄]','','넓이의 대상은 해당 사진 점에 연결된 개발용 핵심점이다. 실험 지역의 넓이는 계산하지 않았다.','',
        '| 사진 점 | 개발용 핵심점 수 | 넓이 (m²) | 개발용 대표 곡선 열람 |','|---|---:|---:|---|']
    for r in a['rows']:
        md.append(f"| {r['point_id']} | {r['selected_core_count']} | {r['selected_core_area_m2']:.12f} | {'예' if r['curve_decoded_during_initial_join'] else '아니요'} |")
    (D/'tables/photo_scope_audit.md').write_text('\n'.join(md)+'\n')
    st='\n'.join(f"| {r['prior']} | {r['buildings']} | {r['core_points']:,} | {r['area_m2']:.12f} |" for r in totals)
    lock=json.loads((C/'judgecheck_v1.initial.lock.json').read_text())
    report=f'''# 판단검증 입력 점검 — 중단 보고 v1

작업: PHD-MAIN-JUDGECHECK-v1 · 단계 가 입력 점검 · {now()}

**상태: STOP_PHOTO_POINT_SCOPE_CONFLICT. 보고 가는 미완료다.**
개발용 항공 LiDAR 핵심점 73개, 5.442552935831812 m²가 실험 지역 건물과 기존 사진 점 42개를 공유한다.
새 기하 값, 새 사진 점수, 새 판단, 정량 표 6~7절 및 그림 8절은 아직 계산하지 않았다.
학습 및 GPU 사용 없음. 확인용 페이로드를 열지 않았다. scientific_verdict: null.
최초 연결에서 공유 사진 곡선 22개를 읽은 경계 예외를 아래에 명시한다.

## 문제와 원인

발주문 1절 2번은 **“실험 지역 건물은 읽지도 세지도 않는다.”**고 정하고,
1절 5번과 4.1~4.2는 기존 사진 점과 곡선을 그대로 쓰도록 정한다.
기존 지붕 사진 코드는 `surf`와 `kind`, 50 cm 격자로 사진 점을 묶으며 건물 ID로 나누지 않는다.
사진 점의 `building`은 소속 패치 넓이가 가장 큰 건물 하나이고, `building_ids`는 함께 들어간 건물 전체다.
따라서 대표 건물만 개발용으로 확인하면 실험 지역 패치가 함께 든 사진 점을 읽을 수 있다.

처음에는 대표 건물이 개발용이 아닌 사진 점에 연결된 핵심점 25개(1.7995261420965014 m²)가 누락되었다.
전체 소속 ID를 확인하자, 개발용 6동과 실험 지역 4동 사이에 공유 사진 점 42개가 있음을 확인했다.
영향은 항공 LiDAR 지붕에 있으며, 개발용 핵심점 73개와 연결된다. 공유 점을 분리하면 기존 사진 점과 곡선의 정의가 바뀐다.

## 열람 범위와 예외

- 개발용 핵심점 입력은 JUDGENUM의 개발용 ID 목록과 일치하는 행만 읽었다.
- 확인용 패치·핵심점·사진 점·곡선은 열지 않았다. `holdout/internal/points`에서는 공통 원시 타일 파일 이름과 크기만 확인했다. 점 좌표는 열지 않았다.
- 실험 지역 건물의 개별 패치 값과 참값은 읽지 않았다. 경계 확인을 위해 소속 ID와 연결 번호만 확인했다.
- **최초 연결 과정에서 실험 지역 패치를 함께 담은 공유 곡선 22개를 읽었다.** 대표 건물이 개발용인 점이다. 나머지 공유 곡선 20개는 읽지 않았다.
- 따라서 발주문의 “실험 지역 건물을 읽지 않았다” 점검 항목을 PASS로 표시할 수 없다. 공유 곡선을 사용한 새 계산이나 판단은 없다.
- 최초 준비 파일은 재현 기록으로 남겼으며 사용 가능 입력으로 승인하지 않았다. `core_points/`와 `photo_points/` 결과는 생성하지 않았다.

## 확인한 범위

아래는 입력 연결의 수와 넓이이며, 새 규칙의 계산 결과가 아니다. [이 발주에서 냄]

| 사전 정보 | 개발용 건물 수 | 핵심점 수 | 넓이 (m²) |
|---|---:|---:|---:|
{st}

항공 LiDAR는 지붕만, LoD2는 지붕과 벽을 포함한다. 원본 패치의 `area`를 합했다.
새 판단의 틀린 비율, σ_W, r, t, 원통 반지름 선택, 사진 시간 어림은 모두 **미계산**이다.
확인 불가를 0이나 성공으로 바꾸지 않았다.

## 조치와 검증

사진 점의 모든 소속 건물이 개발용인지 ID만으로 확인하는 사전 검사를 추가했다.
범위가 섞인 점이 있으면 `prepare.py`가 사진 값을 읽기 전에 멈춘다. 기존 작업의 코드·설정·결과는 고치지 않았다.

별도 검증은 기존 패치의 `patch_id → building`과 사진의 `patch_id → point_index`에서 소속을 다시 만들었다.
42개 사진 점 모두 저장된 `building_ids`와 일치하고, 개발용 핵심점 73개 및 넓이도 일치했다.
검증 결과는 `PASS_STOP_EVIDENCE_VERIFICATION`이다. 이는 중단 근거의 검증이며, 판단 방법의 성능 검증이 아니다.

설정 저장 시각: {lock['at']}

설정 SHA-256: `{lock['config_sha256']}`

최초 실행 스크립트는 `PH/main_judgecheck_v1/PHD-MAIN-JUDGECHECK-v1/source_snapshots/initial_join/`에 보존했다.
첫 입력 연결의 소요 시간은 {join['seconds']:.6f}초다. GPU 계산·대기는 각각 0초다.
사진 200점 시간 어림은 입력 문제로 시작하지 않았다. 대화·코드 확인을 포함한 전체 시간은 별도 계측하지 않았다.

## 회신이 필요한 항목

**제안:** 공유 사진 점 42개를 이번 검증에서 `확인 불가: 실험 지역과 공유`로 표시하고,
연결된 개발용 핵심점 73개(5.442552935831812 m²)를 사진을 사용하는 판단·정확도 계산에서 제외한다.
원본 점 번호와 넓이는 남기고, 표마다 빠진 분모를 별도로 적는다. 기존 곡선을 다시 계산하거나 점을 분리하지 않는다.

이 제외는 아직 적용하지 않았다. 전체 핵심점에 기존 사진 결과를 연결하라는 요구와 분모가 달라지므로 회신이 필요하다.
발주문 1절의 실험 지역 열람 금지와 입력 연결 불가 시 중단 규칙에 따라 새 계산을 멈췄다.
공유 곡선 사용에 대한 예외를 허용하는 방안은 별도 선택이며 자동으로 적용하지 않는다.

## 전달 내용

- `tables/photo_scope_audit.json`, `.csv`, `.md`: 사진 점 42개, 관련 ID, 핵심점 수와 넓이.
- `tables/alignment_diagnosis.json`: 최초 누락 핵심점 25개의 연결 확인.
- `tables/input_join.json`, `tables/input_scope_totals.json`: 개발용 입력 연결 기록.
- `tables/stop_verification.json`: 독립 연결 검증.
- `PHD-MAIN-JUDGECHECK-v1_입력점검.zip`: 이 중단 보고, 표, 설정, 스크립트, SHA256SUMS.

발주된 `판단검증_보고가_v1.md`, 단계 가 결과 ZIP, 보고 나와 확인용 계산은 미완료다.
'''
    assert len(report)<20000
    (D/'입력점검_중단보고_v1.md').write_text(report)
    (D/'issues.md').write_text('''# Issues

- JC-001 — OPEN — STOP_PHOTO_POINT_SCOPE_CONFLICT: 기존 ALS 사진 점 42개가 개발용과 실험 지역 건물을 함께 담는다. 개발용 핵심점 73개, 5.442552935831812 m². 보고 가 미완료. 범위 처리 회신 전 계산 중단.
- JC-002 — RECORDED — 최초 대표 건물 기준 연결에서 공유 곡선 22개를 읽었다. 새 계산에는 사용하지 않았다. 모든 소속 ID 사전 검사로 재실행을 차단했다. 확인용 자료 열람은 없다.
''')
    (D/'progress.md').write_text(f'''# PHD-MAIN-JUDGECHECK-v1 진행

- {now()}: 단계 가 입력 점검에서 중단. 설정 잠금 완료. 개발용 122/125동 ID 연결 확인.
- STOP_PHOTO_POINT_SCOPE_CONFLICT: 공유 사진 점 42개 / 개발용 핵심점 73개 / 5.442552935831812 m².
- 중단 근거 독립 검증 PASS. 범위 예외를 사용자에게 보고한다. 원본 작업 파일 변경 없음.
- 학습·GPU·새 판단 계산 없음. 보고 가/그림/결과 묶음 미완료. 단계 나 미시작.
- 공유 점 처리 회신 전 재실행 금지. scientific_verdict: null.
''')
    dump(C/'preflight_stop.lock.json',dict(at=now(),status=a['status'],
        config_sha256=sha(C/'judgecheck_v1.json'),source_sha256={p.name:sha(p) for p in Path(__file__).parent.iterdir() if p.is_file()},
        initial_join_preserved=True,user_scope_exception_applied=False,scientific_verdict=None))
    files=[]
    for base in [C,D,Path(__file__).parent]:
        prefix='configs' if base==C else ('docs' if base==D else 'scripts')
        for p in sorted(base.rglob('*')):
            if p.is_file() and p.suffix!='.zip' and p.name!='delivery_receipt.json':
                files.append((p,prefix+'/'+str(p.relative_to(base))))
    archive=D/'PHD-MAIN-JUDGECHECK-v1_입력점검.zip'
    hashes={name:sha(p) for p,name in files}
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,name in files:z.write(p,name)
        z.writestr('SHA256SUMS',''.join(f'{h}  {name}\n' for name,h in hashes.items()))
    import hashlib
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,h in hashes.items():assert hashlib.sha256(z.read(name)).hexdigest()==h
    assert archive.stat().st_size<400_000_000
    receipt=dict(at=now(),status='PASS_INPUT_STOP_PACKAGE_INTEGRITY',archive=archive.name,
        bytes=archive.stat().st_size,sha256=sha(archive),files=len(files),crc_verified=True,
        member_sha256_verified=True,not_report_a=True,not_scientific_validation=True,scientific_verdict=None)
    dump(D/'delivery_receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
