"""Facts and explicit pending outputs; never claim a stage completed."""
from common import *

def main():
    cfg()
    data=json.loads((D/'tables/reference_preflight.json').read_text())['rows']
    inputs=json.loads((D/'tables/saved_method_inputs.json').read_text())['rows']
    default=json.loads((D/'tables/unit_default.json').read_text())
    primitive=json.loads((D/'tables/unit_primitives.json').read_text())
    runs=[]
    for site in SITES:
        for prior in PRIORS:
            for arm,name in [('A1','gt'),('A2','gtfs')]:
                row=dict(site=site,prior=prior,arm=arm,run_name=f'{name}_{prior}_s0',
                    status='NOT_STARTED_PREREQUISITE_UNAVAILABLE',iterations=0,
                    reason='단계 0 참값 삼각형 면 미확인; 단계 1 정답 판단 목표 파일 없음',
                    results=None,scientific_verdict=None)
                runs.append(row)
    table('run_status',runs)
    state=dict(at=now(),status='PARTIAL_PREFLIGHT_ONLY',
        stage0='UNAVAILABLE_REFERENCE_TRIANGLE_SURFACE',
        stage1='NOT_STARTED_NO_STAGE0_DECISION',stage2='NOT_STARTED_NO_STAGE1_CELLS',
        stage3='NOT_STARTED_NO_REAL_TARGETS',stage4='NOT_ELIGIBLE_STAGE3_INCOMPLETE',
        training_runs_started=0,completed_experiment_runs=0,
        synthetic_optimizer_steps_per_fork=100,
        A2_implementation_status='PREPARATORY: pre-1000 coefficient undefined; pruning attribution not implemented',
        scientific_verdict=None)
    dump(O/'STATUS.json',state);dump(D/'status.json',state)
    lines=['# PHD-MAIN-GTJUDGE-v1 — 사전점검 부분 결과','',
        '**PARTIAL_PREFLIGHT_ONLY. 단계 0·1·2·3은 완료되지 않았다. 실험 학습 0판.**',
        '`scientific_verdict: null`.', '',
        '1. 단계 0 이상 신호: **확인 불가**. 참값 삼각형 면이 상속 입력에서 확인되지 않아 90% 검증을 계산하지 못했다. 두 거리 완전성 차이 상위 세 칸도 확인 불가다.',
        '2. 법선 거리 판단 맞음과 패치 다수결 상한: **미산출**. 단계 1의 칸·정답 판단 목표를 생성하지 않았다.',
        '3. 보존 칸의 무늬 없음·가장자리·사진 지지 보존 비율: **미산출**. 단계 1 칸이 없다.',
        '4. FINALTRAIN → A-1 → A-2 및 정답 판단 조합 메시: **미산출**. 기존 FINALTRAIN 6판의 완료 receipt와 목표 파일 존재만 확인했다.',
        '5. 기대와 다른 입력: RESCORE의 참값은 점군이고, 법선은 반경 0.5 m PCA / 10점 KNN 보완이며 부호를 정하지 않았다. 발주문 2.1의 최근접 참값 삼각형 면 법선과 다르다.',
        '', '| 장면 | 사전 정보 | 상속 참값 행 | 옛 둘 다 맞음 행 | 참값 삼각형 인덱스 필드 |',
        '|---|---|---:|---:|---:|']
    for r in data:lines.append(f"| {r['site']} | {r['prior']} | {r['n_reference_rows']:,} | {r['n_old_both_correct']:,} | {r['gt_triangle_fields']} |")
    lines+=['',f"상속 참값 행 합계 {sum(r['n_reference_rows'] for r in data):,}개(기존 중복도 유지). 기존 방법별 메시와 점 파일 {len(inputs)}세트 모두 존재한다. 파일 존재와 과거 receipt는 새 채점 완료 또는 이번 전체 payload SHA 검증을 뜻하지 않는다.",
        'B0 추가 참값 PLY의 헤더에는 vertex 4,709,500개와 XYZ/RGB 속성만 있고 face 요소가 없다. 세 지역의 gt_classes, gt_points, gt_primary, 기존 normals 파일의 ZIP 배열 헤더를 점검했다. [배열 구조](provenance/reference_schemas.json) · [B0 PLY 헤더](provenance/B0_primary_ply_header.json) · [코드 근거](provenance/reference_source_lines.json).',
        '', '단계 0의 최근접 칸 fallback은 실제 신호를 확인하고 구현을 한 번 고친 뒤에도 신호가 남을 때만 허용된다. 입력 부재를 그 신호로 바꾸지 않았다. `measured_anomaly_signal: null`, 재계산 0회, fallback 미적용이다. 참값 면 없음이라는 점별 측정 결과와 입력 참값 메시 부재도 구분했다.',
        '', '| 독립 점검 | 결과 | 한계 |','|---|---|---|',
        '| 법선 거리 | 합성 예제 통과 | 옆벽 오인, ±부호, 10/5 m, 5원점, 경사면, 거리 요약 확인. 실제 장면 검증 아님 |',
        '| 칸·다수결 | 합성 예제 통과 | 동률·둘 다 틀림·범위 밖·참값 없음·값 결측 처리. 실제 목표 미생성 |',
        '| r23 ↔ r25 기본값 | 씨앗 0, 100회 일치 | 실제 GaussianModel·Adam·기둥 연결·카메라 순서 비교. 렌더 사진 손실로 학습한 비교는 아님 |',
        '| 목표 경로 스위치 | 합성 목표 일치·잘못된 맵 해시 거부 | 3절의 실제 정답 판단 파일 검증은 미실행 |',
        '| 빈 공간 항 | 7개 중 선택된 3개만 불투명도 감소 | 위치·크기·색 기울기 없음. 합성 사진 기울기로 λ≈2.1 확인. 실험용 λ 아님 |',
        '', 'r25는 준비본이다. 발주문은 빈 공간 항을 500회부터 적용하고 λ를 1,000회에 처음 정한다. 500~999회의 λ가 없으므로 0 또는 1로 임의 채우지 않았다. 현재 `on` 실행은 이 미정 값에서 명시적으로 실패하며, 생산 대기열은 시작하지 않았다. 이 항에 의한 불투명도 정리 삭제 수의 추적도 아직 구현하지 않았다. A-2 준비 완료로 보고하지 않는다.',
        '', '이어서 필요한 근거는 세 지역의 정렬된 참값 삼각형 면 경로·출처와 벽 바깥방향 정의다. 현재 상속 코드는 이를 제공하지 않는다. 참값 점군을 새로 삼각화하는 정책은 이번 발주문에 정의되어 있지 않으며, PCA·사전 정보·MVS 면으로 대신하지 않았다.',
        '', '출력은 지정 폴더에만 두었다. 원본 입력은 Docker 읽기 전용 마운트로 접근했다. 설정 저장 시각과 SHA-256은 계산 전 잠금에 있고, 기존 코드 해시와 r25의 바뀐 줄은 provenance에 있다. 새 정량 그림이나 단계 완료 ZIP은 만들지 않았다. 최종 이름 ZIP은 이 사전점검 부분 결과를 담으며 전체 작업 완료를 뜻하지 않는다.',
        '', '[단계 0 판정](단계0_판정.json) · [12판 미실행 상태](tables/run_status.csv) · [재실행 경로](재실행_경로.md)']
    report='\n'.join(lines)+'\n'
    assert len(report)<10000
    (D/'보고.md').write_text(report)
    (D/'issues.md').write_text('# 실행 기록과 미완료 사항\n\n'
        '- PH는 manifest의 외부 phase-payloads/phd로 해석했다. 재실행 문서의 실제 경로는 docs/experiments/phd/main_rescore_v1/addendum3_stage1/재실행_경로.md다.\n'
        '- 여섯 장면의 상속 참값 입력은 점군이고 PCA 법선의 부호도 미설정이다. 발주문 2.1의 참값 삼각형 면/바깥방향을 확인하지 못했다.\n'
        '- 90% 신호를 측정하지 못했으므로 없음/있음 어느 쪽으로도 채우지 않았다. 단계 1용 최근접 칸 fallback은 미적용이다.\n'
        '- A-2는 500회부터 항을 적용하지만 λ는 1000회에 처음 정한다. 상속 FINALTRAIN에는 이 항이 없어 500~999회의 값을 가져올 수 없다. r25 준비본에 명시적 미정 오류를 두었으며 실행하지 않았다.\n'
        '- GPU 사용은 상속된 작은 단위 예제 r23/r25 각각 100회와 합성 손실 점검에 한정했다. 실제 장면 학습·렌더·메시 생성은 0회다.\n'
        '- r25의 실제 목표/맵 초기화 검증, A-2 전 구간 손실·삭제 수 추적, 전체 대기열, 실험 채점·정성 산출물은 미완료다.\n')
    (D/'재실행_경로.md').write_text('# 재실행 경로와 현재 한계\n\n'
        '`scientific_verdict: null`. 상태는 PARTIAL_PREFLIGHT_ONLY이며 실제 장면 계산 명령은 아직 없다.\n\n'
        '| 명령 | 범위 |\n|---|---|\n'
        '| `bash scripts/phd/main_gtjudge_v1/run_cpu.sh reference inspect_reference.py` | 상속 입력 구조와 단계 0 계산 가능 여부 점검 |\n'
        '| `bash scripts/phd/main_gtjudge_v1/run_cpu.sh unit-cpu unit_cpu.py` | 합성 거리·다수결 점검 |\n'
        '| `python3 -B scripts/phd/main_gtjudge_v1/gpu_checks.py` | Docker GPU 단위점검만; 기존 fixture가 있으면 덮어쓰기 거부 |\n'
        '| `bash scripts/phd/main_gtjudge_v1/run_cpu.sh report report_preflight.py` | 실제 실행하지 않은 단계들을 명시한 부분 보고 |\n\n'
        '최초 freeze.py는 설정이 이미 있으면 거부한다. GPU 명령을 그대로 재실행하면 기본값 fixture 경로가 이미 있어 실패하므로 재실행을 자동 요청하지 않는다. 소스 변경 시 별도 검증 폴더/receipt를 추가해야 한다.\n\n'
        'r25에는 목표 파일 스위치, 동일 해시의 목표·맵·씨앗 검사, 빈 공간 선택/기울기 원형이 있다. --jbgs_preserve_freespace on은 미정인 500~999회 λ 때문에 현재 실행 가능한 A-2가 아니다. 실제 목표가 없으므로 6.3 전체 통과로 간주하지 않는다.\n\n'
        '부족한 참값 면을 찾은 뒤에는 기존 잠금을 덮어쓰지 말고 근거·정책을 별도 추가 잠금으로 남겨야 한다. 삼각화나 법선 교체를 이 문서에서 승인하지 않는다.\n')
    print('PARTIAL_REPORT',len(report),'characters; 0 experiment runs')

if __name__=='__main__':main()
