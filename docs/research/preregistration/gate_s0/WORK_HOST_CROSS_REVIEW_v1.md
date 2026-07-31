# Gate S0 Work Host Cross-Review v1

- review_id: `P2-GATE-S0-WORK-REVIEW-v1`
- reviewed_closed_commit: `1cf0db33ecfe4305477735806912992eea3325d8`
- portability_fix_commit: `4027991abd2a049fea28fcbad1cf3f707dda2cb5`
- review_status: `PASS_WITH_MATERIAL_FOLLOW_UPS`
- gate_proposal: `BLOCKED_FOR_GATE_S0_REVIEW`
- scientific_verdict: null

## 결론

Experiment Host의 Gate S0 준비 작업과 handoff 체인은 기술적으로 신뢰할 수 있다.
그러나 이 결론은 Gate 승인이나 data READY가 아니다. C5 independent LoD1이 승인된
검색 범위에서 `MISSING`이고 C1/C2/C4, `U_target`, `E_paired`, 비용 및 writer/toolchain
근거가 불완전하므로 C1–C5 성능 실행은 계속 차단한다.

## 독립 검증 결과

- Git 계보는 `04081d04 → 9197de13 → 380cc891 → deaedff8 → 1cf0db33`의
  offered/accepted/output/verified/closed 직선 체인이다.
- previous-receipt SHA-256과 event별 단일 커밋 경계가 Git LF bytes에서 일치한다.
- output manifest의 9개 파일은 모두 도입 커밋 `380cc891`의 Git blob, bytes,
  SHA-256과 일치한다.
- 200/300 receipt의 11개 artifact record와 총 15,743,666,051 bytes가 서로 같고
  `scientific_verdict`는 null이다.
- Work Host에는 canonical sibling artifact backend와 기록된 Experiment image가 없어
  15.7GB를 새로 재해시하지 않았다. 새 `artifact_verified` 주장을 만들지 않고
  Experiment Host의 immutable record와 Git chain만 교차검토했다.
- Windows CRLF checkout에서 최초 Gate test 8개 중 3개가 실패했다. 증거 손상이 아니라
  worktree EOL 문제였으며, `4027991`에서 LF-canonical text hash, Git introducing blob,
  AOI/image-inventory hash 검증을 추가한 뒤 Docker 통합 테스트 79/79가 통과했다.

## evidence package에 추가할 blocker

원 `issues.md`의 `S0-I01`–`S0-I12`는 당시 immutable output으로 보존한다. 다음
remediation packet에는 아래 두 항목을 별도로 추가한다.

1. `S0-R13 — C3–C5 SfM sparse initialization provenance`
   - OPF/다른 sparse reconstruction 중 실제 사용할 exact artifact/member를 정한다.
   - URI/member, bytes, SHA-256, coordinate frame, producer/version과 initialization-only
     role을 고정한다.
   - `dense_mvs_separation=READY`는 금지 계약 readiness일 뿐 execution readiness가 아니다.
2. `S0-R14 — evaluation reference and C1 self-reference`
   - geometry/structure reference ID, version, uncertainty와 production lineage를 고정한다.
   - reference가 UAS LiDAR, ALS, footprint를 공유하는지 조사한다.
   - C1 input과 geometry reference가 같은 source이면 독립 평가가 아니라
     self-reference/conditional evaluation class로 명시한다.

## remediation 순서

1. independent LoD1 또는 독립 cadastral footprint+height LoD1 후보를 확대 조사하되
   scored LoD2의 Z, RoofSurface, roof type, semantics를 대체 입력으로 쓰지 않는다.
2. horizontal/vertical datum, transformation, registration residual과 reference lineage를
   공통 foundation으로 결속한다.
3. C1 class 2/6 derivative, C2 exact-937 derivation 또는 sensor-bundle lock, C3–C5 sparse
   initialization, C4 independence/overlap/interface evidence를 완성한다.
4. outcome-free stable-ID ledger로 `candidate AOI → U_target → C1–C5 eligibility → E_paired`
   funnel을 만든다. 199 reference intersections를 분모로 승격하지 않는다.
5. non-GT `R_derived`, gravity와 pinned Roofer/CityJSON/CityGML/cjval/val3dity/G0–G4
   writer를 준비한다.
6. 위 입력이 실행 가능해진 뒤에만 소수 non-held-out unit의 비용 calibration을 별도
   승인한다. 이 단계도 performance comparison이나 held-out 열람이 아니다.

## 금지 상태

- C1–C5 performance baseline, GS training, prior loss tuning 금지
- final adapter 또는 G3/G4 threshold 동결 금지
- held-out, legacy Fusion W1, `R_ext` 접근 금지
- LoD2-derived LoD1 또는 평가 정보의 honest-arm 입력 금지
- agent scientific verdict 금지
