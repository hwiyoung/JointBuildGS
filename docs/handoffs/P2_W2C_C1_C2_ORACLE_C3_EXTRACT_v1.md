# P2 C1/C2 oracle 재실행 및 C3 결과 재추출 v1 — OFFER CONTENT READY

- task_id: `P2-C1-C2-ORACLE-C3-EXTRACT-v1`
- handoff_id: `P2-W2C-C1-C2-ORACLE-C3-EXTRACT-v1`
- source_commit: `5f0b944c1c841c45fa263e5a557fbed081603653`
- status: `OFFER_CONTENT_READY_NOT_ISSUED_BY_WORK_HOST`
- scientific_verdict: `null`

## 사람이 승인한 작업 방향

사용자는 현재 task에서 C1/C2를 올바른 건물별 입력으로 다시 실행하고 C3는 학습 없이
결과만 다시 추출하도록 지시했다. Work Host의 역할은 이 exact plan/commit/source binding을
검토하고 write ownership을 넘기는 문서 처리뿐이다. 이 문서는 실제 Work Host가 발행한
`000-offered` receipt가 아니며 역할을 대리하거나 허위로 만들지 않는다. Experiment Host는 유효한
`100-accepted` 전에는 artifact namespace를 만들거나 Roofer/C3 extraction을 실행하지 않는다.

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

- Roofer/G2/GS training/metric/C4-C5: `4/0/0/0/0`
- pre-Roofer reference alignment failures: `2`
- output: fresh add-once namespace
  `artifact://JointBuildGS/phase-payloads/p2/c1_c2_oracle_c3_extract_v1/P2-C1-C2-ORACLE-C3-EXTRACT-v1`
- C1/C2: 3개 6행×4열 case sheet, 72 panels
- C3: 2 condition × 3 building case sheet, 96 panels
- report/operation CSV/HTML/manifest
- official G3/G4/PASS and scientific_verdict: `null`

## 100-accepted에 필요한 exact action

Work Host는 다음만 수행한다.

1. source commit `5f0b944c1c841c45fa263e5a557fbed081603653`과 이 packet/config를 검토한다.
2. config `status`를 `APPROVED_FOR_EXECUTION`으로 바꾼다.
3. 이 문서의 exact content에 동의하면 실제 Work Host 역할로 validator-compatible
   `000-offered.json`을 작성·commit·push한다.
4. Experiment Host가 그 commit을 fast-forward한 뒤 read-only artifact records를 실제로
   확인한다.
5. Experiment Host가 validator를 통과하는 immutable
   `artifacts/manifests/handoffs/P2-W2C-C1-C2-ORACLE-C3-EXTRACT-v1/100-accepted.json`을
   실제 receiver role로 작성·commit·push한다.
6. 그 accepted commit부터 Experiment Host가 exclusive write ownership을 갖는다.

가짜 role, 자체 acceptance, Git-only artifact verification은 금지한다.
