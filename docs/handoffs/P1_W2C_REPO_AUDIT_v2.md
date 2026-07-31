# Work-to-Codex Task Packet — P1 Repository/Data Readiness Audit v2

## Handoff metadata

- handoff_id: `P1-W2C-REPO-AUDIT-R2`
- phase: `P1`
- workstream: `READ_ONLY_DESIGN_READINESS_AUDIT`
- repository_effective_phase: `P2 / Fusion W1 ACTIVE`
- direction: `Work→Codex`
- status: `DRAFT`
- packet_version: `v2`
- source_commit: `TO_BE_FILLED_BY_USER_BEFORE_APPROVAL`
- target_branch: `main`
- research_charter_version: `P1_AUDIT_v1`
- master_roadmap_version: `P1_AUDIT_v2`
- result_contract_version: `P1_AUDIT_v1`
- data_scope_version: `P1_AUDIT_v1`
- handoff_protocol_version: `P1_AUDIT_v2`
- decision_log_through: `DEC-P1-007`
- supersedes: `P1-W2C-REPO-AUDIT / technical BLOCKED at b08ee9167bca30f9b795e549c2b4d5247c94381b`
- created_at: `2026-07-31 Asia/Seoul`
- user_approval: `NOT_GRANTED`
- approved_by: `null`
- approved_at: `null`
- approval_scope: `DOCS_ONLY_P1_AUDIT; ACTIVE_P2_FUSION_W1_PROTECTED; NO_SOURCE_CONFIG_DATA_RESULT_GPU_MUTATION; R_DERIVED_ONLY; R_EXT_OUT_OF_SCOPE`

이 packet은 v1의 과학 목적과 범위를 바꾸지 않는다. v1 technical receipt의
`required_for_task: true`와 빈 records가 만든 순환 gate, 그리고 protocol의 stale
상태 중복만 교정한다. v1 packet과 activation tuple은 재사용하지 않는다.

## Goal

현재 repository와 manifest-resolved data가 새 연구계약, 결과 출력계약과 향후
P2 baseline을 어느 정도 지원하는지 read-only로 감사한다. 각 기능과 asset은
증거 수준에 따라 `READY`, `PARTIAL`, `MISSING`, `UNKNOWN`으로 판정한다.

P1 `READY_FOR_REVIEW`는 감사 산출물의 완결을 뜻한다. 데이터가 P2에 사용할 준비가
됐다는 뜻이 아니며, data/P2 readiness는 P1 Return Packet 검토와 Gate S0에서
별도로 결정한다.

## Authority and protected state

1. root `AGENTS.md`
2. `docs/research/00_RESEARCH_CHARTER.md`
3. `docs/research/06_DECISION_LOG.md` through `DEC-P1-007`
4. `docs/research/01_MASTER_ROADMAP.md`
5. `docs/research/03_DATA_AND_BASELINE_SCOPE.md`
6. `docs/research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`
7. `docs/research/05_HANDOFF_PROTOCOL.md`
8. 현행 `RESEARCH_CONTEXT.md`, `EXPERIMENT_PLAN.md`, active locks와의 충돌 대조

Repository 유효 단계는 계속 P2/Fusion W1이다. P1은 별도의 read-only
설계·준비도 audit workstream이며 active Fusion W1 files/results/locks를
rollback, supersede 또는 수정하지 않는다. Stage 3는 `R_derived`만 감사하고
external `R_ext`는 입력·구현·실행하지 않는다.

## Technical artifact semantics

R2 technical handoff는 다음을 선언해야 한다.

```text
artifacts.required_for_task = false
artifacts.availability.work_host = manifest_only
artifacts.availability.experiment_host = manifest_only
artifacts.records = []
verification.level = git_only
```

이는 artifact store를 무시한다는 뜻이 아니다. P1은 artifact store 자체가 아니라
Git-owned audit contract를 전달받아 시작하며, audit 중 canonical
`JBGS_ARTIFACT_ROOT`와 checked-in resolver를 읽기 전용으로 조사한다.

- live exact bytes와 필요한 metadata 확인: `READY`; exact 사용 파일·타일의
  URI, bytes, SHA-256, CRS/datum, lineage, coverage를 기록
- manifest/receipt만 확인하고 live bytes를 재검증하지 못함: `PARTIAL`
- 합리적으로 고정한 검색 범위에서 기대 asset을 찾지 못함: `MISSING`
- resolver, 권한, 계보 또는 범위가 불명확해 판정할 수 없음: `UNKNOWN`

`MISSING` 또는 `UNKNOWN`은 유효한 P1 finding이며 P1 문서 작성을 자동 차단하지
않는다. 다만 관련 data READY 주장, C1/C4 contrast, Gate S0 또는 P2 진입을
차단할 수 있다. 전체 428GB workspace directory SHA-256은 요구하지 않는다.
기존 checksum/receipt를 우선 사용하고 READY/P2 주장에 필요한 exact 파일·타일만
표적 검증한다. 다수 파일은 deterministic per-file inventory와 그 inventory의
hash를 사용할 수 있지만, live bytes를 재해시하지 않았으면
`artifact_verified`라고 주장하지 않는다.

## Frozen scientific constraints

- 다섯 reconstruction conditions와 building-level paired comparison
- `L_upper ≠ P_LiDAR`
- Current UAS/Drone LiDAR (`LIDAR_UAS_CURRENT`)는 C1의 `L_upper` 직접 baseline
- Existing ALS (`ALS_EXISTING`)는 C4의 `P_LiDAR` prior 후보
- 두 LiDAR의 파일, survey, 시점, platform/sensor, density, accuracy, coverage,
  classification, CRS/datum, registration, temporal change, overlap와 derivative
  independence를 별도로 비교
- LiDAR prior와 LoD1 prior는 별도 arm이며 `P_LoD1`은 roof topology를 주지 않음
- `G_native → S_extracted → P_Roofer → H_LoD2`
- Sheet A–D, building × method schema, G0–G4와 primary transitions
- threshold와 prior loss는 각각 P2/P3까지 `DEFERRED`
- P1은 held-out-building assignment/result에 접근하지 않음
- scientific verdict와 phase approval은 사용자에게 남음

## Split semantics

```text
E_paired = D_development UNION D_validation UNION D_heldout
the three sets are pairwise disjoint

P2: D_development + D_validation에서 C1–C3
P3: 동일한 D_development + D_validation에서 C4/C5 개발·동결,
    동결 후 pool 전 건물의 frozen C4/C5 final coverage run,
    exact-compatible C1/C2와 frozen hash-compatible 또는
    protocol-matched C3를 결합하여 pool의 final C1–C5 matrix 완성
P4: 앞 단계에서 격리한 D_heldout 전 건물에 C1–C5를 처음 실행
```

P1은 candidate AOI, `U_target`, `E_paired`, asset/reference coverage, 공간 group,
결측, C1–C5 compute/storage를 outcome-free로 감사한다. Exact AOI, building IDs,
split, seed/algorithm, mode와 sample size는 P1 Return Packet 검토 뒤 첫 P2
baseline 결과 전에 Gate S0에서 사용자가 동결한다.

`EXHAUSTIVE_PARTITION`이면 P2/P3와 P4 결과 합집합이 `E_paired` 전 건물의
C1–C5 matrix가 된다. `STRATIFIED_SAMPLE`이면 primary claim은 동결 표본에
한정하며 별도 all-eligible census 없이는 `E_paired` 전체 확장을 주장하지 않는다.

## Inputs to audit

| Input | Resolver/path | P1 handling |
|---|---|---|
| Git checkout | repository root | exact source/approval/offered lineage |
| Artifact manifest layer | `artifacts/manifests/` | schema, resolver, claim level |
| TUM2TWIN imagery/camera/OPF | manifest + canonical mount | READY/PARTIAL/MISSING/UNKNOWN |
| Current UAS/Drone LiDAR | manifest + canonical mount | exact identity and C1 eligibility |
| Existing ALS | manifest + canonical mount | exact identity, independence and C4 eligibility |
| MVS/Pix4D | manifest + canonical mount | lineage and extraction readiness |
| LoD1/LoD2/LoD3 | manifest + official lineage | input/reference separation |
| Current Fusion W1 | active locks/receipts | read-only capability/conflict |
| Pilot PDF/script/config | tracked path or resolver | READY/PARTIAL/MISSING/UNKNOWN |

`TO VERIFY`이거나 찾지 못한 input을 추정으로 채우지 않는다.

## In scope

1. Repository ownership, resolver, entry points, Docker drivers와 tests
2. Current GS backbone, renderer outputs와 native Gaussian/surfel fields
3. C1 UAS/Drone LiDAR direct Roofer baseline과 C4 ALS-prior integration 후보
4. Image/MVS baseline, direct fusion, TSDF, mesh/point extraction
5. Roofer LAS/LAZ class 2/6 adapter, `R_derived`, terrain/crop/buffer,
   invocation/version/parameters와 CityJSON/CityGML serialization
6. cjval, val3dity, roof-plane metrics, RMSXY/RMSZ와 G0–G4 support
7. imagery/UAS LiDAR/ALS/MVS/LoD1/reference의 exact identity, dates, CRS/datum,
   registration, lineage, leakage와 stable-ID coverage
8. candidate AOI별 coverage intersection, `U_target → E_paired` funnel,
   full-matrix cost와 census/sample feasibility
9. 기존 qualitative pilot PDF의 artifact/script/config lineage

## Out of scope

- source/config/dependency/environment 수정
- data 이동·복사·삭제·재분류 또는 canonical result/payload 수정
- 학습, GPU, download/install 또는 장시간 job
- 새 loss/adapter 구현, threshold/criterion 동결
- held-out building assignment/result 접근 또는 성능 실행
- P2 시작
- AGENTS.md/CLAUDE.md 또는 active Fusion W1 수정
- external `R_ext` 사용·구현·승인
- scientific success/failure verdict

## Required outputs

| Output | Path |
|---|---|
| Repository map | `docs/audit/REPOSITORY_MAP.md` |
| Data/coordinate audit | `docs/audit/DATA_AND_COORDINATE_AUDIT.md` |
| Baseline status | `docs/audit/BASELINE_PIPELINE_STATUS.md` |
| GS native audit | `docs/audit/GS_NATIVE_ARTIFACT_AUDIT.md` |
| Extraction audit | `docs/audit/SURFACE_EXTRACTION_AUDIT.md` |
| Roofer/evaluation audit | `docs/audit/ROOFER_AND_EVALUATION_AUDIT.md` |
| Feasibility matrix | `docs/audit/RESULT_OUTPUT_FEASIBILITY_MATRIX.md` |
| Reproduction plan | `docs/audit/TEST_AND_REPRODUCTION_PLAN.md` |
| Open questions | `docs/audit/OPEN_QUESTIONS.md` |
| Return Packet | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v2.md` |

각 finding에는 가능한 범위에서 exact path/resolver, searched scope, host,
timestamp, line/function/config, coordinate frame, evidence level, risk, downstream
gate와 next action을 기록한다. 파일 존재만으로 READY로 판정하지 않는다.

## Preflight

- [ ] complete R2 activation tuple이 사용자에게서 전달됨
- [ ] Experiment Host가 sync 전 clean하고 unpushed/divergent WIP가 없음
- [ ] fetch한 `origin/main`이 exact R2 offered receipt SHA와 일치
- [ ] pull 전 remote v2 packet/receipt의 status, source, approval tree,
      scope/receiver와 `required_for_task: false`를 확인
- [ ] fast-forward-only pull 후 `HEAD == origin/main == R2 offered SHA`
- [ ] offered receipt가 Docker validator를 통과
- [ ] immutable accepted receipt가 write ownership을 이전하고 push 후 검증됨
- [ ] `source_commit`이 ancestor이고 승인 대상 문서가 source snapshot에서 drift 없음
- [ ] version과 Decision Log가 이 packet metadata와 일치
- [ ] P2/Fusion W1, `R_derived`, protected scope와 output scope가 일치

불완전 tuple/DRAFT는 `DRAFT_OR_UNAUTHORIZED_HANDOFF`, 그 밖 mismatch는
`STALE_TASK_PACKET`으로 중단한다. Artifact mount의 개별 asset 부재나
미검증은 activation mismatch가 아니라 P1 finding이다.

## Stop conditions

- current repository/contract/activation tuple mismatch
- source/config/data/result 또는 active Fusion W1 수정이 필요
- destructive access, download/install, GPU 또는 장시간 job이 필요
- held-out result 접근, scientific choice 또는 threshold 결정이 필요
- raw/canonical payload integrity 훼손 정황이 있어 read-only 조사도 안전하지 않음

개별 data path가 ambiguous하거나 missing이면 안전한 범위에서 evidence와 searched
scope를 기록하고 `UNKNOWN/MISSING`으로 계속한다. 이것만으로 handoff를 blocked로
되돌리지 않는다.

## Done when

- required 9 audit documents와 v2 Return Packet이 존재
- 모든 capability/asset에 status와 evidence가 있고 unknown을 추정으로 채우지 않음
- UAS/Drone LiDAR와 ALS가 별도 asset·역할로 비교됨
- candidate-AOI coverage matrix와 `U_target → E_paired` funnel이 작성됨
- census/sample feasibility를 outcome-free로 판정하되 actual split은 결정하지 않음
- LoD1/LoD2, input/reference, `R_derived`/`R_ext`가 분리됨
- coordinate/datum/leakage와 downstream blocked gate가 명시됨
- 변경은 `docs/audit/**`, v2 Return Packet과 immutable handoff receipts에 한정
- Codex는 audit `READY_FOR_REVIEW`만 제안하고 scientific verdict는 내리지 않음

## Launcher prompt

Experiment Host launcher는 packet 본문을 복제하지 않고 다음 activation tuple을
고정한 뒤 이 packet 전체를 읽는다.

```text
handoff_id: P1-W2C-REPO-AUDIT-R2
offered_receipt_commit_sha: TO_BE_FILLED_AFTER_R2_OFFER
packet_path: docs/handoffs/P1_W2C_REPO_AUDIT_v2.md
expected_source_commit: TO_BE_FILLED_BY_USER_BEFORE_APPROVAL
explicit_user_authorization: APPROVED_FOR_EXECUTION
```

Old v1 tuple, packet 또는 receipt를 사용하면 실행하지 않는다.
