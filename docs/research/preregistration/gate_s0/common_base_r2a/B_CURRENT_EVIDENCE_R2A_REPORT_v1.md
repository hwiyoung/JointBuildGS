# B_current Evidence R2A Report v1

- task_id: `P2-GATE-S0-EVIDENCE-R2A-v1`
- handoff_id: `P2-W2C-GATE-S0-EVIDENCE-R2A-v1`
- research_canon: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-011`
- proposed_status: `BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`
- scientific_verdict: null
- performance_authority: `NONE`

## Answer first

`B_CURRENT_CANDIDATE_c205892c390997b5`는 Git compact evidence에서 정확히
재현됐다. 962 image members, 937 exact image/pose pairs, 25 outcome-free no-pose
exclusions와 937 unique camera IDs가 모두 정본 candidate와 일치했고 contradiction은
없었다. R1의 exact sparse member evidence는 재사용할 수 있다.

그러나 exact common-base derivative chain은 아직 Gate freeze가 가능하지 않다.
`sfm_sparse`는 `REUSED_EXACT`이지만 canonical converted derivative 또는 명시적인
bound-member 소비 계약이 없고, dense MVS는 unbound `scene.mvs` 때문에
`AMBIGUOUS`, depth/normal/confidence는 `MISSING`이다. 1,104-image vendor MVS는
exact 937-base 계보가 없어 `INELIGIBLE ... CONTEXT_ONLY`다. 따라서 다음 상태는
`BLOCKED_FOR_GATE_S0_EVIDENCE_REVIEW`가 적절하며, 이는 human Gate 또는 과학적
판정이 아니다.

두 LoD2 source에서는 12,049개 stable building ID를 전부 보존한 deterministic
LoD1 diagnostic을 생성했다. 이 결과는 항상
`REFERENCE_DERIVED_DIAGNOSTIC_ONLY` / `REFERENCE_DERIVED_SELF_CONDITIONED`이며
`primary_c5_eligible=false`다. Primary C5, `E_paired`, `Delta_N_pass(C5)`로 승격하지
않았다.

## 1. Source candidate replay

| Check | Result |
|---|---|
| Candidate manifest | `c205892c390997b57b13ee211bbc264c45800770bb84f0b2698c45d3c656fd74` exact |
| Images / included / excluded | `962 / 937 / 25` exact |
| Included camera IDs | `937`, all unique and pose-present |
| Exclusion rule | `NO_CALIBRATED_CAMERA_POSE_IN_OPF` exact |
| Included basename set | `dd9b446e11c978ef8223858f08571bfea832e0d33517b24c1e573060244f4e2c` |
| Excluded basename set | `a55a811ffe580790c199b65dc57d518890b04d6110ff7c7a2e4cfeb30e6fcb02` |
| Image-camera pair set | `7d1f90ecb79ee19acfbfedb0b7cf78083349c7669678a1f883c5034a41a89ccc` |
| R1 accepted attestation | commit `7a16085c221ccf87d16f712332ac3c97eda193b1`, LF hash exact |
| Images.zip / OPF.zip full pass | `0 / 0` |
| Contradictions | none |

`source_candidate_replay_v1.json`은 generator `--check`, basename joins, camera-ID
uniqueness, pose-member hashes, R1 receipt identity를 각각 기록한다. 외부 image/OPF
archive를 열거나 재해시하지 않았다.

## 2. Exact common-base derivative binding

| Component | Status | Existing evidence | Remaining requirement |
|---|---|---|---|
| SfM sparse | `REUSED_EXACT` | R1의 16 OPF member records, Pix4D PCL IO 2.1.2, 937 camera UIDs, member-manifest hash | canonical derivative를 1회 bind/generate하거나 exact member consumption contract 동결 |
| Dense MVS | `AMBIGUOUS` | `data/work/mvs/openmvs/scene.mvs` 23,267,921 bytes가 metadata-only discovery에서 발견됐지만 producer/config/member/frame/hash 계보 없음 | content를 채택하기 전에 exact 937-base lineage resolve; 불가하면 shared DAG에서 1회 생성 |
| Vendor dense MVS | `INELIGIBLE_CONTEXT_ONLY` | 4,264,934,724-byte 1,104-image Pix4Dmatic bundle이 manifest 경로에 존재 | primary common base로 사용 금지 |
| Depth | `MISSING` | exact candidate 없음 | dense MVS identity 뒤 shared DAG에서 1회 생성 |
| Normal | `MISSING` | exact candidate 없음 | orientation/frame과 함께 shared DAG에서 1회 생성 |
| Confidence | `MISSING` | exact candidate 없음 | image-derived confidence definition을 human review 후 shared DAG에서 1회 생성 |

Bounded discovery는 directory entry와 stat metadata만 사용했다. 발견 파일의 내용은
읽거나 해시하지 않았다. Missing component는 생성하지 않았다.

## 3. Shared idempotent preprocessing DAG

`preprocessing_dag_v1.json`은 `B_CURRENT_CANDIDATE_c205892c390997b5` namespace 아래
`source_membership → sfm_sparse → dense_mvs → depth/normal → confidence` 순서를
정의한다. 각 node는 source candidate hash, component, producer/version 또는 explicit
`UNSELECTED`, accepted-base commit, config hash, coordinate frame, scientific role로
operation identity를 갖는다.

- Exact completed identity는 `REUSED_EXACT` no-op이다.
- Conflicting namespace는 `BLOCKED_NAMESPACE_CONFLICT`다.
- Missing node는 C2/C3/C4/C5별로 반복하지 않고 공통 namespace에서 1회만 실행한다.
- Producer, MVS algorithm, GS loss, component enablement, adapter, threshold와 비용은
  선택하지 않았고 null/placeholder로 남겼다.

## 4. LoD2-derived LoD1 diagnostic

| Tile | Source bytes / same-stream SHA-256 | Buildings | Footprint polygons | Interior rings |
|---|---|---:|---:|---:|
| `690_5334` | 156,656,509 / `61d29e46...e314` | 5,479 | 5,479 | 49 |
| `690_5336` | 147,865,939 / `494282ee...1674` | 6,570 | 6,570 | 5 |
| Combined | 304,522,448 | 12,049 | 12,049 | 54 |

Rule:

1. `gml:id`를 stable building ID로 그대로 유지한다.
2. 모든 `GroundSurface` exterior/interior XY ring을 순서대로 유지한다.
3. 한 building의 ground는 GroundSurface Z 최솟값, top은 전체 building geometry Z
   최댓값인 단일 scalar envelope로 만든다.
4. roof slope, ridge, face adjacency, roof type, semantic evaluation label,
   RoofSurface topology는 전달하지 않는다.
5. neutral JSONL prism record와 `cjio==0.10.1`로 serialize/parse round-trip한
   CityJSONSeq LoD1 `MultiSolid` 후보를 함께 기록한다.

Add-once namespace:

`artifact://JointBuildGS/phase-payloads/p0-audit/data/work/gate_s0/common_base_r2a/P2-GATE-S0-EVIDENCE-R2A-v1/`

4개 output의 합계는 28,472,973 bytes다. 생성 시 serialized bytes에서 digest를
계산했으며 기존 path를 overwrite/delete하지 않았다. 최초 `200` artifact receipt에서
각 output을 push 전·후 한 번씩만 full rehash하고 `300-closed`에서는 재해시하지 않는다.

## 5. Repetition budget and guards

| Operation | Actual |
|---|---:|
| Closed R1 15.7GB bundle repeated reads/hashes | `0 / 0` |
| Images.zip full rehash | `0` |
| OPF.zip full rehash | `0` |
| LoD2 `690_5334` processing+digest stream | `1` |
| LoD2 `690_5336` processing+digest stream | `1` |
| New output full reread before first receipt | `0` |
| Dense/depth/normal/confidence generation | `0` |

No C1-C5 performance, GS training, Roofer comparison, `U_target`/`E_paired` freeze,
held-out, Fusion W1 or `R_ext` access was performed.

## 6. Remaining gaps and next safe task

The next safe task is one separately approved, idempotent **common-base preprocessing
lineage task**, not a performance task:

1. resolve the existing unbound `scene.mvs` producer/config/exact-member/frame lineage
   without treating its filename as proof;
2. bind a canonical sparse consumption path without repeating R1 member hashes;
3. only if still absent, freeze producer/config/resource ceilings and execute each shared
   dense/depth/normal/confidence DAG node once;
4. return exact URI/bytes/hash/frame/role records for human Gate S0 review.

Independent LoD1 remains unavailable for primary C5. The new diagnostic can be used only
in a separately authorized self-conditioned diagnostic; independent evaluation reference
and a separate human Gate decision would be required for any primary-candidate review.
