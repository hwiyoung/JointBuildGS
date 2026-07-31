# Work-to-Codex Task Packet — P1 Repository/Data Audit v1

## Handoff metadata

- handoff_id: `P1-W2C-REPO-AUDIT`
- phase: `P1`
- workstream: `READ_ONLY_DESIGN_READINESS_AUDIT`
- repository_effective_phase: `P2 / Fusion W1 ACTIVE`
- direction: `Work→Codex`
- status: `APPROVED_FOR_EXECUTION`
- packet_version: `v1`
- source_commit: `0e2270b238c6d14a61b781998e0cdc3319d9e64f`
- target_branch: `main`
- research_charter_version: `P1_AUDIT_v1`
- master_roadmap_version: `P1_AUDIT_v1`
- result_contract_version: `P1_AUDIT_v1`
- data_scope_version: `P1_AUDIT_v1`
- decision_log_through: `DEC-P1-006`
- supersedes: `none`
- created_at: `2026-07-31 Asia/Seoul`
- user_approval: `APPROVED_FOR_EXECUTION`
- approved_by: `김휘영`
- approved_at: `2026-07-31T14:18:19+09:00`
- approval_scope: `DOCS_ONLY_P1_AUDIT; ACTIVE_P2_FUSION_W1_PROTECTED; NO_SOURCE_CONFIG_DATA_RESULT_GPU_MUTATION; R_DERIVED_ONLY; R_EXT_OUT_OF_SCOPE`

> **Authorization record:** exact source snapshot과 P1 audit scope는 사용자
> 승인을 받았다. 그러나 offered receipt가 commit/push/validate되고 complete
> activation tuple이 전달되기 전에는 Experiment Host가 실행하지 않는다.

## Goal

현재 repository와 실제 manifest-resolved data가 새 P1 연구계약, 결과 출력계약,
향후 P2 baseline을 어느 정도 지원하는지 read-only로 감사하고, 각 기능을
`READY`, `PARTIAL`, `MISSING`, `UNKNOWN`으로 판정한다.

## Scientific context

제안 연구는 다섯 reconstruction conditions를 같은 building-level Roofer/LoD2.2
acceptance chain에서 비교한다. 감사의 목적은 새 방법을 구현하거나 성공을 판정하는
것이 아니라, 현재 자산과 gap을 근거로 보여주는 것이다.

이때 Current UAS/Drone LiDAR는 `C1_L_upper`의 직접 Roofer baseline이고,
Existing ALS는 `C4_GS_lidar_prior`의 재사용 prior 후보이다. 두 자산을 모두 “LiDAR”
라고 축약해 같은 역할로 취급하지 않는다.

이 packet은 `DEC-P1-006`의 authority scope를 적용한다.

- 현행 P2/Fusion W1은 active 상태를 유지하고 P1은 read-only audit workstream이다.
- 현행 no-external-roofprint를 유지하며 `R_derived`만 primary다.
- external `R_ext`는 별도 root-policy 승인 전까지 비실행 범위 밖이다.
- 기존 4-condition geometry–semantics ablation과 새 5-condition prior design
- TUM2TWIN LoD1의 실제 가용성/계보

감사는 앞의 두 authority 결정을 변경하지 않는다. 남은 연구 lineage와 data
가용성에는 evidence만 기록하고 과학적 정본 verdict를 내리지 않는다.

## Authoritative documents

Preflight 당시 승인된 exact versions만 사용한다.

1. [root AGENTS.md](../../AGENTS.md)
2. [Research Charter](../research/00_RESEARCH_CHARTER.md)
3. [Decision Log](../research/06_DECISION_LOG.md)
4. [Master Roadmap](../research/01_MASTER_ROADMAP.md)
5. [Data and Baseline Scope](../research/03_DATA_AND_BASELINE_SCOPE.md)
6. [Result and Acceptance Contract](../research/04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md)
7. [Handoff Protocol](../research/05_HANDOFF_PROTOCOL.md)
8. [RESEARCH_CONTEXT](../research/RESEARCH_CONTEXT.md)와
   [EXPERIMENT_PLAN](../research/EXPERIMENT_PLAN.md) — 현행 정본 충돌 대조
9. [P2 status index](../../phases/p2-gsjso/README.md)와 exact active Fusion W1 locks —
   상태 대조
10. [Artifact manifest guide](../../artifacts/manifests/README.md),
    `artifacts/manifests/local_workspace_20260730.yaml` 및 필요한 exact resolver

## Current frozen audit constraints

사용자가 승인한 P1 audit 범위이며 감사자가 변경할 수 없다.

- 연구 앵커와 다섯 reconstruction conditions
- `L_upper ≠ P_LiDAR`
- `L_upper` 후보는 Current UAS/Drone LiDAR이고 `P_LiDAR` 후보는 Existing ALS
- LiDAR prior와 LoD1 prior는 별도 arm
- `P_LoD1`은 LoD2 roof prior가 아니며 roof topology를 제공하지 않음
- building-level paired result
- `G_native → S_extracted → P_Roofer → H_LoD2`
- Sheet A–D와 building × method schema
- G0–G4와 primary transitions
- threshold와 prior loss는 각각 P2/P3까지 `DEFERRED`
- P1은 split feasibility만 감사하고 held-out-building assignment/result에 접근하지 않음
- 저장소 유효 단계 P2/Fusion W1과 active files/results/locks를 변경하지 않음
- Stage 3는 `R_derived`만 primary이고 external `R_ext`는 비실행
- 감사 결과는 scientific verdict가 아님

`Current`는 역할명이지 취득 시점이 검증된 사실 label이 아니다.

## Split semantics preserved by this audit

P1 audit는 split을 정하거나 P2를 시작하지 않는다. 다음 구조의 실현 가능성과
Gate S0 결정 입력만 조사한다.

```text
E_paired = D_development UNION D_validation UNION D_heldout
the three sets are pairwise disjoint

P2: D_development + D_validation에서 C1–C3
P3: 같은 D_development + D_validation에서 C4/C5 개발·동결,
    동결 후 이 pool 전 건물에 frozen C4/C5 final coverage run,
    exact-compatible P2 C1/C2와 frozen hash-compatible 또는
    protocol-matched C3를 결합해 이 pool의 final C1–C5 matrix 완성
P4: P2/P3에서 사용하지 않은 D_heldout 전 건물에 C1–C5
```

`EXHAUSTIVE_PARTITION`이면 P2/P3 결과와 P4 결과를 합쳐 `E_paired` 전 건물의
C1–C5 matrix를 완성한다. `STRATIFIED_SAMPLE`이면 primary claim은 동결 표본에만
해당하며, 별도 all-eligible census를 완료하지 않고 `E_paired` 전체 확장을
주장하지 않는다.

Exact AOI, `U_target`/`E_paired`, mode, building IDs, split, seed/algorithm과 sample
size는 P1 Return Packet 검토 뒤, **첫 P2 baseline 결과 전에** 사용자 P2 Gate S0에서
동결한다. P1 Codex는 이를 임의 결정하지 않는다.

## Inputs

| Input | Version/hash | Resolver/path | Role | Verification |
|---|---|---|---|---|
| Git checkout | packet source commit | repository root | code/docs/config inventory | exact HEAD |
| Artifact manifest layer | exact checked-in versions | `artifacts/manifests/` | external payload resolution | schema + target existence where accessible |
| TUM2TWIN assets | `TO VERIFY` | manifest and official lineage | images/UAS LiDAR/ALS/MVS/models | checksum/path/metadata |
| Current Fusion W1 | exact active locks/receipts | phase/config/docs/artifact manifests | existing capability/conflict | read-only |
| Pilot PDF | `TO VERIFY` | tracked or artifact resolver | pilot lineage | file/script/config/hash |

## In scope

### Repository and entry points

- top-level ownership and artifact resolver
- current GS backbone and upstream source
- training entry points, configs, Docker drivers, tests
- current phase/status and active protected Fusion W1 controls

### Renderer and native GS

- RGB
- depth, normal, alpha, distortion
- expected/median depth
- position, rotation, scale, opacity, normal
- semantic attribute
- native Gaussian/surfel export
- fixed top/oblique/section feasibility

### Baselines and surface extraction

- Current UAS/Drone LiDAR `C1_L_upper` baseline pipeline
- Existing ALS를 `P_LiDAR`로 주입할 수 있는 C4 input/initialization/regularization 경로
- current-image MVS baseline pipeline
- direct depth fusion
- TSDF extraction/Marching Cubes
- mesh and point export
- extraction parameters, coordinate frame, runtime/memory risk

### Roofer and evaluation

- actual Roofer LAS/LAZ generation
- class 2 ground / class 6 building
- roofprint, terrain, crop, buffer, density normalization
- `R_derived` derivation code/config와 method별 polygon/hash
- Roofer invocation, version, parameters, output serialization
- CityJSON/CityJSONSeq/CityGML handling
- cjval/schema/semantic checks
- val3dity
- roof-plane metrics, RMSXY/RMSZ, acceptance support
- existing qualitative case generation path

### Data and coordinates

- TUM2TWIN manifest and exact files
- image/camera/trajectory/OPF
- Current UAS/Drone LiDAR와 Existing/real ALS의 exact files 및 derivative independence
- 두 LiDAR의 acquisition date, platform/sensor, density, accuracy, classification,
  roof/ground/building coverage, CRS/vertical datum, registration, temporal change,
  common-building overlap 및 role eligibility 비교
- MVS/Pix4D point cloud
- LoD1/LoD2/LoD3 files and lineage
- building IDs and `R_derived` roofprint derivation path
- candidate AOI별 imagery/UAS LiDAR/ALS/LoD1/reference footprint intersection,
  stable-ID coverage, 연속성, 면적과 예상 비용
- `U_target`/`E_paired` candidate counts, inclusion/exclusion reasons and asset coverage
- `EXHAUSTIVE_PARTITION` feasibility versus `STRATIFIED_SAMPLE` fallback inputs:
  spatial groups, non-GT input metadata, expected attrition, C1–C5 compute/storage budget
- acquisition dates, accuracy, density, coverage
- CRS, local/global coordinate, scale, vertical datum
- input/reference leakage

### Reproduction

- relevant tests
- Docker execution path
- runtime/memory/storage estimates
- raw immutability and external payload retention
- `dense_baseline_qualitative_v5.pdf` generation script/config/artifact

## Out of scope

- source code/config/dependency/environment 수정
- data 이동·복사·삭제·재분류
- 기존 experiment result/payload 수정
- 학습, GPU 실행, 장시간 job
- 새로운 loss/adapter 구현
- PASS numerical threshold 또는 criterion 동결
- held-out building assignment/result 접근 또는 성능 실행
- P1에서는 split 구현 가능성만 감사하며 P4 test 결과를 열지 않음
- P2 시작
- AGENTS.md/CLAUDE.md 수정
- active Fusion W1 payload/lock 수정
- external `R_ext` 사용·구현·승인
- scientific success/failure verdict

Scientific audit output은 `docs/audit/**`와 Return Packet만 허용한다. 별도로
technical two-host lifecycle에 필요한 immutable `accepted`/`verified`/`blocked`
receipt는 exact handoff manifest가 허용한
`artifacts/manifests/handoffs/<handoff_id>/` 경로에 event별 단일 commit으로만
추가할 수 있으며 scientific output으로 간주하지 않는다.

## Tasks

1. Preflight와 two-host handoff를 검증한다.
2. `DEC-P1-006` authority scope 준수와 남은 정본 차이를 exact path/line으로 기록한다.
3. repository map과 주요 pipeline entry points를 작성한다.
4. manifest를 통해 data availability/coordinate/lineage를 감사한다.
5. Current UAS/Drone LiDAR와 Existing ALS를 같은 표에서 비교하고 C1/C4 role
   eligibility와 독립성을 판정한다.
6. GS-native attributes와 renderer output/export 가능성을 감사한다.
7. direct fusion/TSDF/mesh/point path를 감사한다.
8. exact Roofer input adapter와 validation/metric path를 감사한다.
9. Sheet A–D와 quantitative schema의 구현 가능성 matrix를 작성한다.
10. outcome-free data footprint 기준으로 candidate AOI와 `U_target`/`E_paired`
    후보 수 및 전수실험 비용을 산출하고,
    `EXHAUSTIVE_PARTITION` 가능성 또는 `STRATIFIED_SAMPLE` fallback에 필요한
    outcome-free metadata·표본수 입력을 감사한다. Actual split assignment와
    held-out result에는 접근하지 않는다.
11. Docker-based 최소 검증 계획, open questions와 Return Packet을 작성한다.

## Required outputs

| Output | Path | Required content |
|---|---|---|
| Repository map | `docs/audit/REPOSITORY_MAP.md` | entry points, owners, versions, tests |
| Data/coordinate audit | `docs/audit/DATA_AND_COORDINATE_AUDIT.md` | exact files/manifests, CRS, datum, lineage, leakage, mandatory UAS/Drone LiDAR–ALS comparison table, candidate-AOI coverage matrix, `U_target`/`E_paired` funnel, full-matrix cost and census/sample feasibility |
| Baseline status | `docs/audit/BASELINE_PIPELINE_STATUS.md` | C1–C3 capability and gaps |
| GS native audit | `docs/audit/GS_NATIVE_ARTIFACT_AUDIT.md` | renderer/native fields and fixed-view feasibility |
| Extraction audit | `docs/audit/SURFACE_EXTRACTION_AUDIT.md` | direct fusion/TSDF/mesh/point paths |
| Roofer/evaluation audit | `docs/audit/ROOFER_AND_EVALUATION_AUDIT.md` | exact input/output, class 2/6, validation/metrics |
| Feasibility matrix | `docs/audit/RESULT_OUTPUT_FEASIBILITY_MATRIX.md` | every Sheet/table/gate item: READY/PARTIAL/MISSING/UNKNOWN |
| Reproduction plan | `docs/audit/TEST_AND_REPRODUCTION_PLAN.md` | Docker commands, data needs, cost/risk |
| Open questions | `docs/audit/OPEN_QUESTIONS.md` | blocking/major/minor, owner, evidence needed |
| Return Packet | `docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md` | template-compliant evidence index |

## Finding format

각 기능 판정:

- `READY`
- `PARTIAL`
- `MISSING`
- `UNKNOWN`

가능할 때 다음을 포함한다.

- exact file path
- function/class/config name
- line range
- coordinate frame
- input/output type
- reuse feasibility
- risk
- recommended Docker test

파일 존재만으로 READY로 판정하지 않는다. call path, config, output, test 또는
reproduction evidence의 수준을 밝힌다.

## Verification

- `git status --short` 전/후: 허용된 문서 외 변경 없음
- root instruction validator와 repository tests는 **Docker에서** 실행 계획을 세움
- audit가 source/config/data/result를 수정하지 않았는지 diff 확인
- markdown relative links와 required section 검사
- every capability row에 status/evidence
- external payload claim은 `git_only`와 `artifact_verified`를 구분
- exact commands와 exit code를 Return Packet에 기록

## Preflight

- [ ] User supplied `handoff_id`, exact `offered_receipt_commit_sha`,
      `packet_path`, non-placeholder `source_commit`, and
      `explicit_user_authorization: APPROVED_FOR_EXECUTION`
- [ ] Experiment Host local checkout had no unpushed/dirty WIP before synchronization
- [ ] `git fetch origin main` resolved the exact Work Host offered-receipt SHA
- [ ] Before pull, the packet and offered receipt at that remote commit were inspected
      read-only; packet status and user approval were `APPROVED_FOR_EXECUTION`,
      source commit matched the activation tuple, the receipt `base_main`
      pinned the approval commit, and scope/receiver matched
- [ ] `git pull --ff-only origin main` produced `HEAD == origin/main == offered receipt commit`
- [ ] offered receipt passed validation and immutable accepted receipt transferred write ownership
- [ ] packet status is `APPROVED_FOR_EXECUTION`
- [ ] source commit is exact, non-placeholder, and an ancestor/base snapshot
- [ ] approved research documents have not drifted from that source snapshot
- [ ] charter/roadmap/result/data versions match
- [ ] Decision Log is current through `DEC-P1-006`
- [ ] no newer P1 audit packet exists
- [ ] repository effective phase remains P2/Fusion W1 and P1 is only the approved audit workstream
- [ ] active Fusion W1 is protected, `R_derived` is primary, and external `R_ext` is out of scope
- [ ] target branch and current write owner match this packet
- [ ] required external artifacts resolve at the claimed verification level
- [ ] dirty WIP is absent or covered by an immutable validated snapshot
- [ ] `scripts/repository/validate_two_host_handoff.py` passes those ownership/artifact/WIP checks
- [ ] protected scope does not overlap allowed output scope

Activation tuple이 불완전하거나 packet이 DRAFT/unapproved이면 command를 실행하지
않고 `DRAFT_OR_UNAUTHORIZED_HANDOFF`로 중단한다. 승인 후 나머지 preflight가
실패하면 `STALE_TASK_PACKET`으로 중단한다.

## Stop conditions

- current repository or contract version mismatch
- unresolved authority conflict가 감사 범위를 바꿈
- required data path가 ambiguous하거나 destructive access 필요
- source/config/data/result 수정이 필요
- active Fusion W1 protected scope와 overlap
- download/install/GPU/long run 필요
- scientific choice 또는 threshold 결정 필요
- raw/canonical payload integrity가 의심됨

## Done when

- required 9 audit documents와 Return Packet이 모두 존재
- 기능별 status와 evidence가 있고 unknown을 추정으로 채우지 않음
- Current UAS/Drone LiDAR `L_upper`와 Existing ALS `P_LiDAR`가 exact file,
  acquisition regime, 품질, 역할, lineage 기준으로 비교·분리됨
- candidate AOI별 data-footprint/stable-ID/연속성/면적/비용 matrix와
  `U_target → E_paired` coverage funnel이 작성됨
- `EXHAUSTIVE_PARTITION` 가능성 또는 `STRATIFIED_SAMPLE` fallback 입력이
  outcome 없이 판정되며 actual split/sample size는 결정하지 않음
- LoD1/LoD2, input/reference가 분리됨
- coordinate/vertical datum/leakage 위험이 명시됨
- exact Roofer input과 output serialization이 확인되거나 UNKNOWN
- Sheet A–D, metric table, G0–G4 구현 가능성이 전부 판정됨
- 변경이 허용된 docs 범위에만 있음
- Codex는 `READY_FOR_REVIEW`만 제안

## Return packet path

`docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md`

## Launcher prompt

```text
EXECUTION AUTHORIZATION GATE

이 launcher는 승인된 packet용이다. 다음 activation tuple이 사용자의 명시적
실행 지시와 함께 제공되기 전에는 git fetch/pull/commit/push, receipt 작성,
파일 수정 또는 audit를 수행하지 마라.

- handoff_id
- exact offered_receipt_commit_sha
- packet_path
- expected non-placeholder source_commit
- explicit_user_authorization: APPROVED_FOR_EXECUTION

하나라도 없으면 아무 command도 실행하지 말고
DRAFT_OR_UNAUTHORIZED_HANDOFF로 중단하여 필요한 Work Host 조치를 보고하라.

Activation tuple이 완전할 때만 Experiment Host에서 시작하라.
어떤 task action보다 먼저 local checkout에 unpushed/dirty WIP가 없는지 확인하라.
dirty/divergent state이면 pull하지 말고 blocked handoff로 보고하라.

git fetch origin main을 수행하고 origin/main이 activation tuple의
offered_receipt_commit_sha와 정확히 같은지 확인하라.
pull 전에 origin/main의 packet과 offered receipt를 read-only로 검사하여 다음을
모두 확인하라.

- packet status == APPROVED_FOR_EXECUTION
- packet source_commit is non-placeholder and equals the activation tuple
- packet user_approval is granted
- offered receipt `base_main` pins the approval commit and exact scope/receiver;
  that approval tree contains this exact packet path

하나라도 실패하면 pull/accepted receipt/task를 수행하지 말고
STALE_TASK_PACKET 또는 blocked handoff로 중단하라.

모두 일치할 때만 git pull --ff-only origin main으로 local main을 exact offered
commit까지 갱신하고 HEAD == origin/main == offered_receipt_commit_sha를 확인하라.
fast-forward 실패 또는 SHA mismatch이면 실행하지 마라.

offered handoff manifest를 scripts/repository/validate_two_host_handoff.py로
검증하라. technical manifest가 허용할 때만 immutable accepted receipt를
작성·commit·push하고 다시 검증하여 write ownership을 인수하라.

그 뒤 승인된 docs/handoffs/P1_W2C_REPO_AUDIT_v1.md를 읽고 root AGENTS.md와
packet의 authority를 적용하여 status/source_commit,
charter·roadmap·data·result contract version, decision_log_through,
더 새 packet, repository effective P2/Fusion W1 phase와 P1 audit workstream을
formal preflight하라.
불일치하면 코드·config·data·실험을 실행하지 말고
STALE_TASK_PACKET으로 중단해 mismatch와 필요한 Work 조치를 보고하라.

일치하면 repository/code/config/data는 read-only로 감사하고 packet이 허용한
docs output만 작성하라. Current UAS/Drone LiDAR
(`LIDAR_UAS_CURRENT`, C1의 `L_upper`)와 Existing ALS
(`ALS_EXISTING`, C4의 `P_LiDAR`)를 같은 LiDAR로 취급하지 말고, exact file/version,
취득일, platform/sensor, density, accuracy, classification, roof/ground/building
coverage, CRS/vertical datum, registration, temporal change, common-building overlap,
derivative independence와 role eligibility를 비교표로 작성하라.
Stage 3는 `R_derived`만 감사하고 external `R_ext`를 입력·구현·실행하지 마라.
Active Fusion W1 files/results/locks를 수정하지 마라.
pilot/development, validation, held-out-building test의 split 구현 가능성만 감사하고
held-out building assignment/result에는 접근하지 마라. held-out view와 held-out
building을 구분하라.

다음 phase 관계를 그대로 보존하라.
`E_paired = D_development UNION D_validation UNION D_heldout`이며 세 집합은
서로 겹치지 않는다.
P2와 P3는 동일한 `D_development + D_validation` building IDs를 사용한다.
P2는 C1-C3, P3는 C4/C5 개발·동결과 이 pool 전 건물의 frozen C4/C5 final
coverage run을 담당한다. P3는 exact-compatible P2 C1/C2와 frozen
hash-compatible 또는 protocol-matched C3를 결합해 이 pool의 final C1-C5
matrix를 완성한다. P4는 별도로 보관한 `D_heldout` 전 건물에 C1-C5를 처음
실행한다.

candidate AOI별 imagery/UAS LiDAR/ALS/LoD1/reference footprint intersection,
stable-ID coverage, 연속성·면적·비용을 outcome-free 기준으로 비교하라.
`U_target`과 `E_paired` 후보 수, inclusion/exclusion funnel, asset/reference
coverage, 공간 group, 결측, building x C1-C5 예상 compute/storage를 감사하라.
전수 `EXHAUSTIVE_PARTITION` 가능성을 우선 판정하고, 불가능할 때 필요한
`STRATIFIED_SAMPLE`의 outcome-free metadata와 표본수·비용 결정 입력을 보고하라.
`EXHAUSTIVE_PARTITION`이면 세 split의 결과 합집합이 `E_paired` 전 건물 x C1-C5가
되어야 한다. `STRATIFIED_SAMPLE`이면 별도 census 없이는 `E_paired` 전체 확장을
주장할 수 없음을 명시하라.

Actual AOI, building IDs, split, threshold 또는 sample size를 임의로 결정하지 마라.
이 결정은 P1 Return Packet을 사용자가 검토한 뒤, 첫 P2 baseline 결과 전에
P2 Gate S0에서 사용자가 승인한다. Work는 evidence와 결정안을 작성하고 Codex는
감사 evidence만 제공한다.

지정된 docs/audit 문서 9개와
docs/handoffs/returns/P1_C2W_REPO_AUDIT_RETURN_v1.md를 작성하라.
과학적 verdict, threshold, phase approval을 임의로 결정하지 마라.
```
