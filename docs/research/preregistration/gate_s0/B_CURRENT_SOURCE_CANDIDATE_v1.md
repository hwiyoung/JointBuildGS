# `B_current` Source Candidate v1

- status: `CANDIDATE_NOT_FROZEN`
- research_canon: `C1C5_CANON_v2`
- decision_log_through: `DEC-P1-011`
- common_image_pose_base_id: `B_CURRENT_CANDIDATE_c205892c390997b5`
- source_candidate_manifest_sha256:
  `c205892c390997b57b13ee211bbc264c45800770bb84f0b2698c45d3c656fd74`
- scientific_verdict: null
- performance_authority: `NONE`

## 결론

기존 Experiment Host가 이미 검증한 compact evidence만 재결속하여 exact source-member
candidate를 만들었다. 962개 image member 중 calibrated pose와 1:1로 결합되는 937개를
포함하고, pose가 없는 25개를 같은 outcome-free rule로 제외한다. 이 작업은 외부
15.7GB payload를 다시 읽거나 해시하지 않았다.

이로써 source member 후보의 중복 정리는 끝났지만 `B_current` 전체가 동결된 것은
아니다. SfM sparse의 source identity는 READY이나 callable conversion은 PARTIAL이고,
exact common-base dense MVS, depth, normal, confidence는 아직 MISSING이다. Human Gate S0가
component enablement와 최종 manifest를 승인하기 전에는 P2 performance를 실행하지 않는다.

## Exact binding

| Item | Result |
|---|---|
| image archive | 5,906,891,973 bytes; prior accepted attestation 재사용 |
| OPF archive | 1,936,493,976 bytes; prior accepted attestation 재사용 |
| image members | 962 exact rows and per-member SHA-256 |
| included image/pose pairs | 937; unique camera IDs |
| exclusions | 25; `NO_CALIBRATED_CAMERA_POSE_IN_OPF` |
| SfM sparse | 4,131,648 points; 937 camera UID set exact match |
| 1,104-image vendor MVS | `SENSOR_PROCESSING_BUNDLE_CONTEXT_ONLY` |

정본 JSON은
`artifacts/manifests/gate_s0/b_current_source_candidate_v1.json`이다. 생성기는 기존
Git evidence의 LF-canonical hashes, exact basename sets, camera-ID pairs와 prior accepted
attestation을 교차검증한다.

## 다음 Experiment Host 작업

다음 작업은 이 source candidate를 재생성하거나 15.7GB를 다시 전수 해시하지 않는다.

1. 기존 derivative manifest를 먼저 찾아 exact source candidate에 결합한다.
2. 결합된 artifact는 `REUSED`, 없는 artifact는 `MISSING`으로 기록한다.
3. missing dense MVS/depth/normal/confidence를 즉석 생성하지 않고, 한 번만 생성할
   idempotent preprocessing DAG와 operation identity를 작성한다.
4. LoD2→LoD1은 `DEC-P1-011`에 따라 deterministic diagnostic candidate로 생성할 수
   있으나, 같은 LoD2 평가에서는 `REFERENCE_DERIVED_SELF_CONDITIONED`로 격리한다.
5. C1–C5 performance, held-out, Fusion W1와 `R_ext`는 실행·열람하지 않는다.

## Reuse guard

동일 operation은 source manifest hash, component, producer/version, code commit,
config hash, coordinate frame과 role이 모두 같으면 다시 실행하지 않는다. Shared
image-derived component는 C2–C5 arm별로 만들지 않고 `B_current` namespace에 한 번만
만든다. R1에서 닫힌 LoD1 동일 범위 검색도 새 provider/scope delta가 없으면 반복하지
않는다.
