# P2 C1/C2 oracle 재실행 및 C3 결과판 복구 recovery v4 — LOCAL EXECUTION AUTHORITY

- task_id: `P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v4`
- handoff_id: `null`
- execution_record_id: `P2-LOCAL-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v4`
- recovery_base_commit: `acc532ca2e4647003478615035f6c41eb27cc9ed`
- status: `APPROVED_FOR_LOCAL_EXPERIMENT_HOST_EXECUTION`
- execution_authority: `DIRECT_HUMAN_INSTRUCTION_SINGLE_EXPERIMENT_HOST`
- write_ownership_transfer_performed: `false`
- two_host_receipt_required: `false`
- scientific_verdict: `null`

## 사람이 승인한 작업 방향

사용자는 현재 task에서 C1/C2를 올바른 건물별 입력으로 다시 실행하고 C3는 학습 없이
결과만 다시 추출하도록 지시했다. 이어서 이번 작업은 Work→Experiment write ownership
transfer가 아니며, 현재 Experiment Host에서 직접 실행하고 Work Host는 필요할 때 주요
문서를 제작하는 용도로만 사용한다고 명시했다.

따라서 이 task는 가짜 `000-offered`/`100-accepted`를 만들지 않는다. 저장소의 two-host
불변식은 실제 host 간 write ownership transfer가 있을 때 그대로 적용되며, 이번에는 그런
transfer가 발생하지 않는다. 기존 `P2_W2C_...` 파일명은 이미 커밋된 계획의 추적 호환
경로로만 보존하고 `handoff_id`는 `null`로 고정한다.

## 정확한 실행계획

정본 실행계획은
`docs/experiments/p2/c1_c2_oracle_c3_extract_v1/EXECUTION_PLAN_ko_v1.md`, 실행 config는
`configs/p2/c1_c2_oracle_c3_extract_v1/run_v1.json`이다. 과거 공용 component output,
`COMPLETED_REUSED_EXACT` Roofer output, 1 m C1/C2 grid와 Gaussian quad mesh는 재사용하지
않는다.

## C1/C2 preflight 결과와 실행 수

실제 raw current-UAS LAZ와 exact common-MVS PLY를 쓰기 없이 한 번씩 읽은 결과:

| building | C1 class-6 voxels | C2 class-6 voxels | action |
|---|---:|---:|---|
| `DEBY_LOD2_4907177` | 25 | 0 | 두 방법 모두 `PRE_ROOFER_REFERENCE_ID_ALIGNMENT_FAILURE`; Roofer 0회 |
| `DEBY_LOD2_4906975` | 134,260 | 148,719 | C1/C2 Roofer 각 1회 |
| `DEBY_LOD2_108580336` | 253,622 | 440,453 | C1/C2 Roofer 각 1회 |

따라서 planned Roofer invocation은 6회 강제가 아니라 정확히 4회다. `4907177`의 두
record는 같은 case sheet에 입력/footprint와 함께 남기되 다른 건물 output을 대입하지
않는다. 이 상태는 C1/C2 또는 Roofer 실패가 아니라 2022 reference와 2024 evidence의
alignment/identity precondition failure다.

C1/C2는 LoD2 `GroundSurface` XY를 footprint로 쓰는 oracle diagnostic이다. RoofSurface
XYZ, LoD2 Z, roof type, final roof model은 Roofer 입력에 사용하지 않는다. 따라서 결과를
official no-external-roofprint honest arm으로 부르거나 승격하지 않는다.

## C3 실제 학습 이력과 이번 실행

성공한 독립 학습은 4회가 아니라 두 번이다.

- `C3_1_SEM seed0`: 30,000 iter, 129.9분
- `C3_2_SEM_DEPTH seed0`: 30,000 iter, 86.6분
- 순차 합계: 216.5분 = 03:36:30

recovery directory와 실패한 iteration-0 시작은 독립 학습 반복이 아니다. 이번 task의
GS training invocation은 0이다. 두 exact checkpoint에서 모든 Gaussian native field를
보존한 full PLY, 명시적 display proxy, rendered median-depth 다중시점 fused point cloud,
Poisson surface mesh만 추출한다. 이전 4-corner/2-triangle-per-Gaussian 파일을 mesh로
재사용하지 않으며 새 mesh를 TSDF라고 잘못 표기하지 않는다.

## 실행 한계와 출력

- Roofer/G2/GS training/metric/C4-C5 lineage total: `4/0/0/0/0`
- Recovery-v4 Roofer invocation: `0` (Recovery-v3 exact completed outputs hash-verified inheritance)
- Recovery-v4 C3 extraction invocation: `0` (Recovery-v3의 두 completed extraction hash-verified inheritance)
- pre-Roofer reference alignment failures: `2`
- output: fresh add-once namespace
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_oracle_c3_extract_recovery_v4/P2-C1-C2-ORACLE-C3-EXTRACT-RECOVERY-v4`
- C1/C2: 3개 6행×4열 case sheet, 72 panels
- C3: 2 condition × 3 building case sheet, 96 panels
- report/operation CSV/HTML/manifest
- official G3/G4/PASS and scientific_verdict: `null`

## 실행 권한과 기록

1. recovery-v4의 base commit은 `acc532ca2e4647003478615035f6c41eb27cc9ed`이며 실제 실행 commit은 final manifest에 고정한다.
2. 현재 task의 직접 사용자 지시를 local Experiment Host 실행 권한으로 기록한다.
3. 실행 launcher는 clean `HEAD == origin/main`, exact project image, 입력/checkpoint,
   add-once namespace 부재와 config의 local authority tuple을 확인한다.
4. 실제 실행 commit은 final manifest의 `source_commit`으로 기록한다.
5. Return과 기술 보고서는 결과 생성 후 작성하되 `scientific_verdict`는 계속 `null`이다.

## 보존된 launcher partial

최초 local launcher invocation은 `.partial` bind mount를 먼저 만든 뒤 producer가 경로
존재 자체를 거부해 scientific input read와 계산 전에 중단됐다. 해당 빈 partial은 삭제하거나
재사용하지 않는다. Recovery v1은 새로운 namespace를 사용하며, producer는 Docker가 미리
만든 빈 bind-mount root만 허용하고 단 하나의 항목이라도 있으면 계속 fail-closed한다.
Recovery v1은 이 gate를 통과한 뒤, 예상된 `4907177/C2 class-6=0` 통계에서 빈 배열의
최소·최대를 계산해 preparation 중단됐다. Roofer와 C3 extraction은 시작되지 않았다.
Recovery v2는 빈 class-6의 높이 범위를 `null`로 기록하고 고정된 pre-Roofer failure로
계속 진행했다. 네 Roofer operation은 모두 성공했지만 C3-1 surface render가 gsplat lazy
CUDA extension용 `/.cache` 권한 오류로 중단됐다. Recovery v3는 네 C1/C2 output/input/
footprint/terminal hash를 검증해 계승했고, writable CUDA/Torch cache에서 C3 두 condition의
full Gaussian, fused point cloud, Poisson mesh 추출을 모두 완료했다. 이후 C3 mesh의
TOP/PRINCIPAL_SECTION panel에서 2D axes가 생성되지 않은 renderer 결함으로 최종화 전에
중단됐다. Recovery v4는 C1/C2 16개 및 C3 16개 핵심 산출물을 크기와 SHA-256으로 검증해
새 namespace에 계승하고, Roofer·C3 extraction·GPU·GS training을 추가 실행하지 않은 채
결과판 렌더링과 최종화만 수행한다.
