# Gate S0 Freeze Packet v1

## Metadata

- packet_type: `HUMAN_REVIEW_FREEZE_PACKET`
- status: `DRAFT_NOT_APPROVED`
- packet_version: `v1`
- research_canon: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-010`
- created_at: `2026-07-31`
- prior_evidence_state: `GATE_S0_REMEDIATION_R1 TECHNICAL CLOSED / PROPOSED BLOCKED`
- gate_decision: null
- scientific_verdict: null
- execution_authority: `NONE`

이 문서는 다음 human Gate S0 결정을 위한 초안이다. Experiment Host task packet,
handoff 승인 또는 performance 실행 권한이 아니다. 과거 preparation/remediation
Task Packet, Return Packet, receipt와 evidence bytes는 수정하지 않고 당시 사실의
입력 증거로만 참조한다.

Read-only evidence basis:

- `remediation_r1/REMEDIATION_EVIDENCE_REPORT_v1.md`
- `remediation_r1/remediation_issue_log_v1.md`
- `remediation_r1/sfm_sparse_initialization_v1.json`
- `../../../handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md`

## 1. Answer first

Gate S0는 아직 승인할 수 없다. `DEC-P1-010`으로 C3–C5의 과학적 조건은 교정됐지만,
exact common image/pose base와 그 파생 component manifest가 아직 동결되지 않았다.
독립 LoD1, coordinate/datum/registration, reference, `U_target`/`E_paired`, Stage 3
toolchain과 cost도 기존 blocker 상태를 유지한다.

이 packet의 첫 목적은 1,104-image vendor MVS를 자동 채택하지 않고 exact common
image/pose base를 명시적으로 검토·동결하는 것이다. 결과를 보기 전 입력계약만 다룬다.

## 2. Gate S0가 검토할 reconstruction conditions

`C3_GS_image` ID는 기존 schema/계보 호환성을 위해 유지한다. canonical condition
name은 `no-external-prior GS`이며 `image-only`, RGB-only 또는 sparse-only를 뜻하지 않는다.

| ID | Frozen scientific definition | External existing-asset prior |
|---|---|---|
| `C1_L_upper` | Current high-quality UAS LiDAR → Roofer | 없음; sensor upper baseline |
| `C2_MVS` | `B_current`에서 파생한 MVS geometry → direct Roofer | 없음 |
| `C3_GS_image` | `B_current` → no-external-prior GS reoptimization → extraction → Roofer | 없음 |
| `C4_GS_lidar_prior` | exact C3 base + Existing ALS prior → GS → extraction → Roofer | Existing ALS 하나 |
| `C5_GS_lod1_prior` | exact C3 base + independent LoD1 prior → GS → extraction → Roofer | Independent LoD1 하나 |

C4와 C5를 합치지 않는다. C3–C5의 image-derived base, GS backbone, renderer,
surface adapter와 common parameters는 동일하게 유지하고 external prior만 달라야 한다.

## 3. `B_current` common image/pose base freeze

`B_current`는 다음 두 층을 하나의 immutable manifest로 묶는다.

### 3.1 Exact source members

| Required field | Freeze rule | Current evidence |
|---|---|---|
| image archive/version | exact URI, bytes, SHA-256 | 962-image archive candidate verified |
| included image members | member ID/path/hash 전부 기록 | 937 included candidate |
| excluded image members | 25 IDs와 outcome-free exclusion reason | deterministic ledger candidate |
| camera/pose members | image ID와 1:1 join, frame·units·intrinsics/extrinsics | 937 calibrated candidate |
| common-base manifest | ordered members, join rule, count, schema, content hash | `MISSING` |

962/937/25는 현재 근거가 설명하는 candidate counts이며 이 DRAFT가 자동 동결하지
않는다. Human Gate S0는 exact members, join, exclusions와 manifest hash를 검토한다.

### 3.2 Permitted image-derived components

같은 frozen images/poses에서만 파생한 아래 component는 C3–C5 공통 입력으로 허용한다.
각 component는 `enabled/disabled`와 실제 사용 역할까지 사전 동결한다. Enabled component는
C3–C5에서 동일 bytes/config/hash여야 한다.

| Component | Permitted role examples | Required provenance |
|---|---|---|
| SfM sparse | GS initialization, camera support | producer/version, code/config, source IDs, frame, bytes/hash |
| dense MVS | geometry initialization 또는 supervision | producer/version, code/config, source IDs, frame, bytes/hash |
| depth | depth initialization/loss support | generation rule, view IDs, scale/frame, confidence binding, bytes/hash |
| normal | normal initialization/loss support | derivation rule, orientation convention, frame, bytes/hash |
| confidence | image-derived weighting/mask | definition, valid range, calibration, source component, bytes/hash |

이 component들은 current images에서 파생하므로 external prior가 아니다. Current UAS
LiDAR, Existing ALS, LoD1, evaluation reference, scored LoD2, roof type/semantics와
external roofprint는 `B_current`에서 금지한다. Image-derived confidence와
external-prior confidence는 별도 field와 artifact로 기록한다.

## 4. C2–C3 contrast freeze

| Dimension | `C2_MVS` | `C3_GS_image` |
|---|---|---|
| Source image/pose base | exact same `B_current` | exact same `B_current` |
| Image-derived geometry | MVS output | same frozen common component set |
| GS optimization | 없음 | 있음; geometry/support를 GS representation에서 재최적화 |
| Roofer path | MVS → common adapter → Roofer | GS → surface extraction → common adapter → Roofer |
| Primary interpretation | direct photogrammetric geometry | GS-reoptimized image-derived geometry |

Primary C2–C3 해석을 허용하려면 image members, poses, photometric/geometric
preprocessing과 MVS producer/config 차이를 manifest에서 통제해야 한다. 통제되지 않은
차이는 method effect가 아니라 sensor-processing-bundle difference로 분류한다.

## 5. Existing 1,104-image MVS rule

기존 Pix4D/vendor MVS는 1,104 acquired images를 사용한 것으로 기록되어 있고, 현재
public image/pose evidence는 962 images와 937 calibrated poses를 가리킨다. 따라서
기존 MVS를 다음 중 하나로만 판정한다.

1. `EXACT_COMMON_BASE_ELIGIBLE`: 1,104 source records를 포함한 exact image/pose member,
   hash, producer/config와 exclusion relation이 `B_current`에 완전히 결합되고 human
   Gate가 이를 공통 base로 승인한 경우.
2. `SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY`: exact 결합이 없거나 다른 image/pose/
   preprocessing을 사용한 경우. 이때 primary C2나 C3–C5 common base로 사용하지 않고
   별도 context baseline으로만 보존한다.

기존 파일의 존재, 높은 point density 또는 vendor metadata만으로 1번을 선택하지 않는다.

## 6. Gate S0 freeze checklist

| Freeze item | Required decision evidence | Current proposal |
|---|---|---|
| C1 input | exact UAS selection/merge, class 2/6, CRS/datum, registration, coverage | `BLOCKED` |
| `B_current` | exact image/pose members와 common manifest hash | `BLOCKED` |
| shared derivatives | component별 enablement, producer/config/frame/role/bytes/hash | `BLOCKED` |
| C2 direct MVS | common-base derivation 또는 context-only 분류, Roofer adapter | `BLOCKED` |
| C4 ALS prior | independent asset lineage, registration, overlap, interface/confidence | `BLOCKED` |
| C5 LoD1 prior | independent LoD1 bytes, provider lineage, CRS/datum, coverage, leakage guard | `BLOCKED` |
| references | geometry/structure ID/version/uncertainty와 self-reference class | `BLOCKED` |
| `U_target`/`E_paired` | stable IDs, condition attemptability, exclusions, coverage | `BLOCKED` |
| split/AOI | outcome-free exact polygon, IDs, group, seed/algorithm, mode | `BLOCKED` |
| Stage 3 readiness | callable/pinned `R_derived`, class/terrain interface, Roofer/writer/validator와 surface-adapter candidate set | `BLOCKED`; final surface adapter 선택은 P2 |
| cost ceiling | non-held-out preprocessing/baseline runtime·memory·storage bound | `UNKNOWN` |

`DEC-P1-010`의 조건 정의 승인은 위 payload readiness를 자동 `READY`로 바꾸지 않는다.

## 7. Required freeze record

Gate 승인안에는 최소 다음 값을 placeholder 없이 기록한다.

- `common_image_pose_base_id`와 manifest SHA-256
- included/excluded image IDs, camera/pose join과 exact counts
- SfM sparse/dense MVS/depth/normal/confidence별 `enabled`, role, producer/config/hash
- C3–C5 공통 GS backbone, renderer, common parameter/config IDs와 hashes
- C2 `condition_flow=mvs_direct_roofer`
- C3–C5 `condition_flow=gs_reoptimized_then_roofer`
- C3 `external_prior=none`
- C4 ALS prior ID/hash/interface 및 `external_prior=existing_als`
- C5 LoD1 prior ID/hash/interface 및 `external_prior=independent_lod1`
- 1,104-image vendor MVS disposition과 근거
- C1/class/coordinate/reference/roofprint/toolchain readiness와 adapter-candidate IDs
- final surface adapter/parameters는 Gate S0에서 임의 선택하지 않고 P2 criterion freeze로 이관
- exact `U_target`, `E_paired`, AOI/split manifest와 cost ceiling
- protected held-out IDs와 접근 금지 receipt

## 8. Human decision block

현재 제안은 다음과 같다.

```text
gate_decision: null
scientific_verdict: null
recommended_state: BLOCKED_PENDING_EXACT_FREEZE_EVIDENCE
performance_execution: PROHIBITED
```

Human reviewer는 evidence가 채워진 후에만 다음 중 하나를 명시적으로 선택한다.

- `APPROVED_FOR_P2_BASELINE_PREPARATION`
- `DEFERRED_WITH_REQUIRED_EVIDENCE`
- `BLOCKED`

이 DRAFT의 evidence gap을 채우는 bounded preprocessing/manifest 작업도 별도
Experiment Host task packet, non-placeholder source commit과 immutable
offered/accepted receipt가 필요하다. Performance task는 human Gate 승인 뒤에만
만든다. 이 DRAFT 자체를 Experiment Host에 보내 실행하지 않는다.

## 9. Protected history

다음은 읽기 전용 입력 증거이며 이 packet에서 수정하지 않는다.

- `docs/handoffs/P2_W2C_GATE_S0_PREPARATION_v1.md`
- `docs/handoffs/P2_W2C_GATE_S0_REMEDIATION_R1_v1.md`
- `docs/handoffs/returns/P2_C2W_GATE_S0_PREPARATION_RETURN_v1.md`
- `docs/handoffs/returns/P2_C2W_GATE_S0_REMEDIATION_R1_RETURN_v1.md`
- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-PREP-v1/`
- `artifacts/manifests/handoffs/P2-W2C-GATE-S0-REMEDIATION-R1-v1/`
- `docs/research/preregistration/gate_s0/`의 기존 v1/remediation R1 evidence
- `docs/evidence/archive/pre_c1c5_research/`
- protected Fusion W1와 held-out 결과
