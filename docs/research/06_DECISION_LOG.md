# Research Decision Log

- Document status: `USER_APPROVED_RESEARCH_DECISIONS`
- 문서 버전: `C1C5_CANON_v2`
- 작성일: 2026-07-31
- 승인 상태: `USER APPROVED CURRENT C1–C5 CANON — 2026-07-31`

`DEC-P1-010` 이후 이 log와 00–06 contract set이 현재 C1–C5 프로그램을 통제한다.
앞선 decision entry의 당시 용어는 역사 기록으로 보존하며, 충돌 시 더 최신 decision의
`New decision`과 `Superseded decisions`를 적용한다.
`docs/evidence/archive/pre_c1c5_research/`의 context/plan은 기존 4조건 프로그램의 역사 기록이다.
기존 Fusion W1 lock과 artifact는 보호하지만 현재 프로그램의 실행 authority는 아니다.

## Decision schema

- Decision ID
- Date
- Status
- Previous state
- New decision
- Evidence
- Reason
- Affected phases
- Affected documents
- User approval
- Superseded decisions

## DEC-P1-001 — Prior loss 상세설계 연기

- **Decision ID:** `DEC-P1-001`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED AUDIT DECISION`
- **Previous state:** 새 5-condition 프로그램에서 LiDAR-prior와 LoD1-prior의
  상세 loss equation, confidence rule, weights, schedule이 정의되지 않았으며,
  기존 JointBuildGS loss와의 관계도 미결정.
- **New decision:** Detailed prior loss design is deferred until Current UAS/Drone
  LiDAR, MVS and Image-only GS baselines, surface extraction analysis, and LoD2
  acceptance protocol are sufficiently established.
- **Evidence:** prior 효과를 판정하려면 안정적인 Image-only GS baseline과
  extraction/Roofer/acceptance chain이 먼저 필요하다는 P1 연구계약;
  `00_RESEARCH_CHARTER.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`.
- **Reason:** 관찰되지 않은 실패를 가정해 loss를 설계하거나 prior held-out-building 결과에
  맞춰 criterion을 바꾸는 순환을 방지한다.
- **Affected phases:** P1, P2, P3
- **Affected documents:** `00_RESEARCH_CHARTER.md`,
  `01_MASTER_ROADMAP.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`,
  향후 P3 method contract
- **User approval:** `GRANTED`; 상세 loss 자체는 P3까지 의도적으로 미정
- **Superseded decisions:** 없음

### Consequence

- G3/G4 numerical threshold와 final surface adapter: `DEFERRED TO P2`
- LiDAR-prior/LoD1-prior loss equation, weights, training schedule:
  `DEFERRED TO P3`
- P1 read-only audit는 loss 구현·수정·성능 verdict를 수행하지 않는다.

## DEC-P1-002 — Current UAS/Drone LiDAR와 Existing ALS 역할 분리

- **Decision ID:** `DEC-P1-002`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED AUDIT DECISION`
- **Previous state:** 초안은 `L_upper ≠ P_LiDAR`를 선언했으나 여러 표와 packet에서
  둘을 단순히 “LiDAR” 또는 “current/existing LiDAR”로 축약하여 독자가 두 자산의
  필요성과 차이를 오해할 수 있었다.
- **New decision:** Current UAS/Drone LiDAR (`LIDAR_UAS_CURRENT`)는 C1의
  `L_upper` 직접 Roofer baseline이며, Existing ALS (`ALS_EXISTING`)는 C4의
  `P_LiDAR` prior 후보이다. P1 감사는 두 자산을 한 비교표에서 분석한다.
- **Evidence:** 사용자의 2026-07-31 지시와 `03_DATA_AND_BASELINE_SCOPE.md`의
  공식 asset 후보 및 역할 계약.
- **Reason:** sensor modality 이름만 같을 뿐 acquisition regime과 인과적 역할이
  다르다. 이 차이가 입증되지 않으면 C1/C4 contrast가 성립하지 않는다.
- **Affected phases:** P1–P4
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `03_DATA_AND_BASELINE_SCOPE.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`,
  `P1_W2C_REPO_AUDIT_v1.md`
- **User approval:** `GRANTED FOR P1 AUDIT`; program-level method canon 전환은 별도
- **Superseded decisions:** 없음

### Consequence

- canonical label은 `Current UAS/Drone LiDAR`와 `Existing ALS`를 사용한다.
- exact file/version, 취득일, platform/sensor, density, accuracy, classification,
  coverage, CRS/datum, registration, temporal change, overlap, lineage를 비교한다.
- 같은 file/survey derivative이거나 차별성이 입증되지 않으면 C4 ALS prior 채택을
  `BLOCKED`로 판정한다.

## DEC-P1-003 — Held-out building과 held-out view 구분

- **Decision ID:** `DEC-P1-003`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED AUDIT DECISION`
- **Previous state:** “P4 held-out 전체 실험”과 “held-out RGB rendering”이 서로 다른
  분할 단위를 같은 용어로 표현했고, P3까지 전체 건물을 실험하는지 불명확했다.
- **New decision:** held-out building은 P2/P3에서 접근하지 않는 최종 test building
  group이고, held-out view는 같은 development/validation building에서 학습에
  제외한 camera view이다. P4 primary의 “전체”는 held-out test에 배정된 모든
  building × C1–C5를 뜻하며 전체 eligible corpus를 뜻하지 않는다.
- **Evidence:** 사용자의 2026-07-31 확인 요청과 split leakage 방지 목적.
- **Reason:** method/criterion tuning과 최종 일반화 평가를 분리하면서 rendering
  diagnostics의 view split을 계속 사용할 수 있게 한다.
- **Affected phases:** P1–P4
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `03_DATA_AND_BASELINE_SCOPE.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`,
  `05_HANDOFF_PROTOCOL.md`, `P1_W2C_REPO_AUDIT_v1.md`
- **User approval:** `GRANTED FOR DISTINCTION`; split 수량·경계는 P2 Gate S0에서 결정
- **Superseded decisions:** 없음

### Consequence

- P1은 split feasibility만 감사하고 실험 결과에 접근하지 않는다.
- P2는 pilot/development+validation에서 C1–C3와 criterion을 동결한다.
- P3는 같은 허용 split에서 C3를 frozen control로 재실행/재사용하고 C4/C5를
  개발·동결한다. C3는 P3에서 재튜닝하지 않는다.
- P4에서 held-out building test를 처음 열어 전 건물 × C1–C5를 실행한다.
- primary 잠금 뒤 all-eligible rerun은 supplementary descriptive analysis로만 허용한다.

## DEC-P1-004 — P4 확장과 전수 우선 split

- **Decision ID:** `DEC-P1-004`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED AUDIT DECISION`
- **Previous state:** P4가 held-out test 전 건물을 실행한다는 점은 명확했지만, 전체
  eligible building을 언제 포함하는지, held-out 규모와 확장 기준을 언제 정하는지
  정의되지 않았다.
- **New decision:** P1 audit에서 `U_target`/`E_paired`와 C1–C5 비용을 산출하고,
  P2 첫 baseline 결과 전 Gate S0에서 `EXHAUSTIVE_PARTITION`을 기본안으로 검토한다.
  전수가 불가능한 경우에만 `STRATIFIED_SAMPLE`을 사용자 승인으로 사용한다.
- **Evidence:** 사용자의 2026-07-31 확인 요청, paired building-level endpoint,
  held-out peeking 방지 계약.
- **Reason:** P4의 building 추가가 결과 기반 선택이 되지 않게 하고, 최종 coverage와
  외적 타당성 범위를 사전에 명확히 한다.
- **Affected phases:** P1–P4
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `03_DATA_AND_BASELINE_SCOPE.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`,
  `P1_W2C_REPO_AUDIT_v1.md`
- **User approval:** `GRANTED FOR DESIGN`; exact counts와 mode는 P1 audit 후 P2 Gate S0
- **Superseded decisions:** 없음

### Consequence

- P2/P3는 동일한 development+validation building pool을 사용한다.
- `EXHAUSTIVE_PARTITION`이면 P2/P3가 앞의 두 split, P4가 held-out remainder를
  담당하고, 최종 합집합은 `E_paired` 전체 × C1–C5다.
- P2 Gate S0는 data-footprint/stable-ID/연속성/면적/비용만으로 exact AOI
  polygon/hash를 동결한다.
- P3 method freeze 뒤 frozen C4/C5를 development+validation 전 건물에 적용하여
  P2의 exact-compatible C1–C3와 함께 해당 pool의 final matrix를 완성한다.
- `STRATIFIED_SAMPLE`이면 outcome-free spatial/input-metadata group sampling,
  paired endpoint 정밀도/검정력, attrition, compute budget을 동결한다.
- sampled fallback에서 `E_paired` 전체 확장을 주장하려면 P4 primary 잠금 뒤
  all-eligible census coverage run을 완료해야 한다.
- split ID·seed·algorithm·strata·source hash·제외 사유를 immutable manifest로
  기록하고 P3/P4에서 변경하지 않는다.

## DEC-P1-005 — Work Host push 후 Experiment Host exact pull

- **Decision ID:** `DEC-P1-005`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED HANDOFF DECISION`
- **Previous state:** DRAFT roadmap과 launcher가 two-host 시작을 “Remote pull /
  immutable handoff 확인”으로 축약하여 fetch, exact SHA, fast-forward-only update,
  accepted receipt의 순서가 불명확했다.
- **New decision:** Work Host가 approval 및 immutable offered-receipt commits를
  `origin/main`에 push한 뒤 write를 멈춘다. Experiment Host의 첫 task action은
  activation 확인, clean check, fetch, offered SHA 및 remote approval tree 확인,
  `git pull --ff-only`, offered validation, accepted-receipt commit/push와
  write-ownership 인수이다.
- **Evidence:** 사용자의 2026-07-31 지시와 현행
  `docs/research/reproducibility/CHATGPT_WORK_CODEX_HANDOFF.md`의
  `serialized_main` contract.
- **Reason:** stale/local-divergent checkout에서 audit 또는 experiment가 시작되는
  것을 막고 exact commit과 single-writer ownership을 보장한다.
- **Affected phases:** 모든 two-host handoff
- **Affected documents:** `01_MASTER_ROADMAP.md`, `05_HANDOFF_PROTOCOL.md`,
  `W2C_TASK_PACKET_TEMPLATE.md`, `P1_W2C_REPO_AUDIT_v1.md`
- **User approval:** `GRANTED`; 사용자가 2026-07-31 상호검수와 다음 단계의
  중단 없는 진행을 승인
- **Superseded decisions:** 없음

### Consequence

- blind `git pull`이나 merge commit은 허용하지 않는다.
- pull 전 local dirty/divergent state 또는 remote SHA mismatch면 `blocked`다.
- technical accepted receipt와 scientific `APPROVED_FOR_EXECUTION`을 모두 통과한
  뒤에만 Experiment Host가 작업을 시작한다.

## DEC-P1-006 — P1 audit authority와 no-external-roofprint 범위

- **Decision ID:** `DEC-P1-006`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED`
- **Previous state:** 제안 P1이 repository의 현재 P2/Fusion W1 phase와 충돌하고,
  `R_ext`/`R_derived` 선택이 root no-external-roofprint invariant와 충돌하는
  blocking open question이었다.
- **New decision:** P1은 repository phase를 rollback/supersede하지 않는 read-only
  설계·준비도 audit workstream이다. 저장소 유효 단계는 계속 P2/Fusion W1이고
  active files/results/locks는 protected scope다. Stage 3 primary는 point evidence에서
  생성하는 `R_derived`이며 external `R_ext`는 별도 root-policy 승인 전까지
  P1과 후속 P2–P4의 비실행 범위 밖이다.
- **Evidence:** root `AGENTS.md` phase status와 Stage 3 invariant, 사용자의
  2026-07-31 문서 승인 및 “다음 단계 멈추지 말고 서브에이전트 상호검수를 통해
  진행” 지시, 독립 scientific/handoff 검수.
- **Reason:** 승인 packet이 상위 정본과 자기모순으로 중단되는 것을 막고 기존
  Fusion W1 자산을 보호한다.
- **Affected phases:** P1 audit; 향후 P2–P4의 roofprint authority
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `03_DATA_AND_BASELINE_SCOPE.md`, `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`,
  `05_HANDOFF_PROTOCOL.md`, `P1_W2C_REPO_AUDIT_v1.md`
- **User approval:** `GRANTED`
- **Superseded decisions:** P1 phase/roofprint에 관한 미채택 pending options

### Consequence

- P1 audit의 `phase: P1`은 task/workstream label이며 repository phase 변경이 아니다.
- P1은 source/config/data/result/Fusion W1을 수정하거나 GPU experiment를 실행하지 않는다.
- `R_ext`를 감사 결과의 실행 대안으로 승인하거나 입력에 사용하는 것은 금지한다.
- P1 Return Packet은 `R_derived` 구현 가능성·계보만 판정한다.

## DEC-P1-007 — P1 감사 시작 gate와 data READY gate 분리

- **Decision ID:** `DEC-P1-007`
- **Date:** 2026-07-31
- **Status:** `R2 OPERATIONAL CORRECTION WITH USER STANDING AUTHORIZATION`
- **Previous state:** v1 scientific packet은 TUM2TWIN과 Pilot을 `TO VERIFY`로
  두고 `READY/PARTIAL/MISSING/UNKNOWN` 감사를 요구했지만, technical offered
  receipt는 `required_for_task: true`, `availability: manifest_only`,
  `records: []`를 선언했다. Experiment Host는 이 모순과 protocol의 stale
  `DRAFT` 표기를 근거로 `b08ee9167bca30f9b795e549c2b4d5247c94381b`에서
  handoff를 blocked 처리했다.
- **New decision:** P1은 외부 payload를 생성·전달하거나 data readiness를
  선결조건으로 요구하는 작업이 아니라, 부재와 검증 불능도 결과로 기록하는
  docs-only readiness audit이다. 새 R2 technical handoff는
  `required_for_task: false`, `availability: manifest_only`, `records: []`로
  시작할 수 있다. Audit 중 mount와 resolver를 읽기 전용으로 조사하고,
  확인 수준에 따라 `READY/PARTIAL/MISSING/UNKNOWN`을 기록한다.
- **Evidence:** v1 `200-blocked.json`, packet Inputs/Done when, two-host validator의
  artifact-required 규칙, independent scientific/handoff/reader reviews.
- **Reason:** P1이 확인해야 할 미지의 asset을 P1 시작 전 완전 검증하도록 요구하는
  순환 gate를 제거하되, 검증되지 않은 data를 READY로 승격하는 것은 막는다.
- **Affected phases:** P1 activation; P2 Gate S0와 이후 data readiness
- **Affected documents:** `01_MASTER_ROADMAP.md`, `05_HANDOFF_PROTOCOL.md`,
  `06_DECISION_LOG.md`, `HANDOFF_INDEX.md`, P1 v1/v2 packet
- **User approval:** 기존 P1 과학 범위를 변경하지 않는 운영 교정. 사용자의
  2026-07-31 “판단을 반복해서 묻지 말고 에이전트 간 검증으로 진행” 지시를
  R2 준비 authority로 적용한다. Scientific verdict와 후속 Gate S0 승인은
  여전히 사용자에게 남는다.
- **Superseded decisions:** 없음; v1 technical handoff만 새 R2가 대체

### Consequence

- 전체 `JointBuildGS-artifacts` 428GB directory hash는 P1 activation 조건이 아니다.
- 기존 checksum/receipt를 우선 사용하고, 특정 asset을 `READY` 또는 P2 입력으로
  주장할 때만 실제 사용 파일·타일을 URI, bytes, SHA-256, CRS/datum, lineage,
  coverage 기준으로 표적 검증한다.
- manifest/receipt만 확인되면 `PARTIAL`, 기대 범위에서 찾지 못하면 `MISSING`,
  resolver/권한/계보 때문에 판정할 수 없으면 `UNKNOWN`이다.
- UAS/Drone LiDAR와 ALS의 derivative independence가 입증되지 않으면 P1은 그
  사실을 보고할 수 있지만 C1/C4 contrast와 P2 진입은 `BLOCKED`다.
- P1 `READY_FOR_REVIEW`는 감사 문서가 완결됐다는 뜻이며 data/P2 READY와 동일하지
  않다.

## DEC-P1-008 — C1–C5 연구 정본 채택과 legacy 계획 격리

- **Decision ID:** `DEC-P1-008`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED RESEARCH CANON DECISION`
- **Previous state:** 00–06은 P1 audit 기준으로만 승인됐고 현재 archive로 이동한
  legacy context/plan과 Fusion W1이 계속 우선했다. 기존 4조건과 새 5조건의 관계는
  pending decision이었다.
- **New decision:** 연구 앵커를 “불완전하지만 재사용 가능한 기구축 3D 자산의 구조적
  안정성과 최신 항공영상의 현재성·세부 관측을 상보적으로 결합하여 자동 LoD2 생성이
  가능한 건물 범위를 확대”로 채택한다. 현재 비교는 `C1_L_upper`, `C2_MVS`,
  `C3_GS_image`, `C4_GS_lidar_prior`, `C5_GS_lod1_prior`의 다섯 reconstruction
  conditions이다. 00–06이 현재 정본이고 기존 context/plan은 역사 기록이다.
- **Evidence:** 사용자의 2026-07-31 명시적 연구목적·다섯 조건 재확인과 “이에 맞게
  수정하고 Experiment Host로 진행”, 이어 “사람의 개입 없이 멈추지 말고 서브
  에이전트 간 검증으로 진행” 지시.
- **Reason:** audit-only 문구와 legacy 권위가 새 실행 packet을 차단하고 독자에게 서로
  다른 연구목적·조건·phase를 제시했기 때문이다.
- **Affected phases:** P2 Gate S0, P2–P4
- **Affected documents:** root `AGENTS.md`/`CLAUDE.md`, `docs/research/00_*.md`–`06_*.md`,
  archived legacy context/plan, research entrypoints, Gate S0 packet
- **User approval:** `GRANTED FOR CURRENT RESEARCH CANON AND AUTONOMOUS PREPARATION`
- **Superseded decisions:** audit-only/legacy-authority 제한과 아래 pending relation을
  supersede한다. `DEC-P1-006`의 Fusion 보호, `R_derived` primary, `R_ext` 비실행은 유지한다.

### Consequence

- C1/C2는 context baselines이고 C4-vs-C3, C5-vs-C3가 primary prior contrasts다.
- “상보성”은 C4/C5 rescue-set과 failure-mode 차이를 뜻하며 joint prior synergy를
  뜻하지 않는다.
- 기존 4조건/Fusion 결과는 삭제·재라벨하지 않고 capability evidence로만 사용한다.
- 다음 실행은 P1 재실행이나 C1–C5 performance run이 아니라 Gate S0 evidence
  preparation이다.
- Gate S0는 exact AOI, inputs, `U_target`, `E_paired`, eligibility, split과 cost를
  outcome 없이 동결할 자료를 만든다. 과학적 verdict는 계속 사용자에게 남는다.

## DEC-P1-009 — Gate S0 evidence 종료와 remediation 우선순위

- **Decision ID:** `DEC-P1-009`
- **Date:** 2026-07-31
- **Status:** `TECHNICAL EVIDENCE INTEGRATION / scientific_verdict null`
- **Evidence:** output commit `380cc8916e739702206a65cdd9318b2014c81030`,
  verified `deaedff800bd62b6a6b893ff885898c99571f199`, closed
  `1cf0db33ecfe4305477735806912992eea3325d8`, Work Host cross-review
  `P2-GATE-S0-WORK-REVIEW-v1`.
- **Decision:** Gate S0 preparation v1은 기술적으로 종료됐지만 제안 상태는
  `BLOCKED_FOR_GATE_S0_REVIEW`다. 기존 packet은 재실행하지 않고 새 remediation
  packet에서 누락 증거를 다룬다. C1–C5 performance execution은 계속 금지한다.
- **Added blockers:** 원 evidence의 `S0-I01`–`S0-I11`에 더해 C3–C5 SfM sparse
  initialization의 exact identity/hash/frame/role과 evaluation reference
  ID/version/production lineage/C1 self-reference class를 remediation 필수 항목으로 둔다.
- **Priority:** independent LoD1 viability → coordinate/datum/reference foundation →
  condition별 input provenance → `U_target/E_paired` → Stage 3/writer → bounded
  non-held-out cost calibration 순서다.
- **User approval:** 사용자의 “사람의 개입 없이 멈추지 말고 서브 에이전트 간 검증으로
  진행” 지시는 이 technical integration과 다음 DRAFT/approval packet 준비 authority로
  적용한다. Gate S0와 scientific verdict는 여전히 사용자/human reviewer에게 남는다.
- **Superseded decisions:** 없음. `DEC-P1-008`의 연구 정본과 금지 범위를 유지한다.

### Consequence

- 962/937 차이는 937 included + 25 explicit exclusions ledger로 해소됐다. 다만 C2
  MVS exact derivation binding은 `PARTIAL`이다.
- C5 `MISSING`은 승인된 bounded search scope에 한정한다. 더 넓은 독립 provider/
  cadastral 조사 없이 전역 부재로 과장하지 않는다.
- Work Host CRLF portability fix는 evidence bytes를 변경하지 않고 Git LF blob을
  검증하도록 구현한다.
- 새 remediation handoff가 closed되기 전에는 Gate freeze packet이나 performance
  packet을 만들지 않는다.

## DEC-P1-010 — C3–C5 no-external-prior common base와 C2 contrast

- **Decision ID:** `DEC-P1-010`
- **Date:** 2026-07-31
- **Status:** `USER-APPROVED RESEARCH CANON AMENDMENT`
- **Previous state:** `C3_GS_image`를 “Image-only GS”로 부르고 current RGB/pose와
  SfM sparse initialization만 허용했으며, dense MVS point cloud/depth/normal은
  C3–C5 입력과 supervision에서 금지했다. 이 정의는 외부 기구축 prior의 효과를
  분리하려는 비교와 image-derived geometry를 공통 활용하려는 설계를 혼동했다.
- **New decision:** `C3_GS_image` ID는 계보 호환성을 위해 유지하되 canonical
  condition name을 **no-external-prior GS**로 정의한다. Gate S0에서 exact current
  image members와 camera/pose IDs를 `B_current`로 동결하고, 그 동일 base에서만 파생한
  SfM sparse, dense MVS, depth, normal, confidence를 C3–C5 공통 initialization,
  supervision 또는 weighting support로 허용한다. C4는 exact C3 base에 Existing ALS
  prior만, C5는 exact C3 base에 independent LoD1 prior만 추가한다. C2는 같은 base의
  MVS geometry를 GS 없이 Roofer로 직접 전달하고, C3는 image-derived geometry를
  GS에서 재최적화한 뒤 extraction/Roofer로 전달한다.
- **Evidence:** 사용자의 2026-07-31 명시적 조건 교정, Gate S0 remediation evidence의
  962 images/937 poses ledger와 1,104-image vendor MVS mismatch, 독립 정본 교차검토.
- **Reason:** `image-only`를 RGB-only 또는 sparse-only로 오해하지 않게 하고, C4/C5가
  C3와 동일한 image-derived evidence를 공유한 상태에서 external prior 하나의 순효과만
  비교하게 한다. C2-vs-C3는 입력 캠페인 차이가 아니라 direct MVS와 GS
  reoptimization의 차이로 해석할 수 있어야 한다.
- **Affected phases:** P2 Gate S0, P2–P4
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `02_NOVELTY_MAP.md`, `03_DATA_AND_BASELINE_SCOPE.md`,
  `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`, `05_HANDOFF_PROTOCOL.md`,
  `06_DECISION_LOG.md`, 다음 `preregistration/gate_s0/GATE_S0_FREEZE_PACKET_v1.md`
- **User approval:** `GRANTED — exact common image/pose base는 Gate S0에서 동결`
- **Superseded decisions:** `DEC-P1-008`의 다섯 조건·primary contrasts는 유지한다.
  `C3`의 “Image-only/sparse-only” 해석과 C3–C5 dense MVS/depth/normal blanket ban만
  이 결정이 supersede한다. 과거 packet, return, receipt와 evidence의 당시 기록은
  수정하지 않는다.

### Consequence

- `B_current`는 exact image/pose member IDs, inclusion/exclusion rule, producer/version,
  component별 code/config, coordinate frame, role, bytes와 hash가 모두 동결되기 전에는
  `READY`가 아니다.
- image-derived confidence와 external-prior confidence를 구분해 기록한다.
- Existing ALS, independent LoD1, Current UAS LiDAR, evaluation reference, scored LoD2,
  external roofprint는 `B_current`에 포함되지 않는다.
- 기존 1,104-image vendor MVS는 exact common image/pose mapping이 입증되기 전에는
  primary common base나 primary C2로 자동 채택하지 않는다. 필요하면 별도
  sensor-processing-bundle context baseline으로만 유지한다.
- 962/937 ledger도 근거 후보일 뿐 이 결정 자체로 자동 freeze되지 않는다. Gate S0
  human packet이 exact members와 hashes를 승인해야 한다.
- 이 정본 변경은 Gate S0 승인, data READY, C5 readiness 또는 performance 실행
  권한을 뜻하지 않는다.

## DEC-P1-011 — LoD2-derived LoD1 diagnostic 허용과 primary 분리

- **Decision ID:** `DEC-P1-011`
- **Date:** 2026-08-01
- **Status:** `USER-APPROVED BOUNDED DIAGNOSTIC PREPARATION`
- **Previous state:** 독립 LoD1이 없으면 C5 준비 전체가 멈추는 것처럼 해석됐고,
  evaluation LoD2를 단순화한 LoD1은 primary honest arm 금지만 기록돼 있었다.
- **New decision:** LoD2 `GroundSurface`와 단일 height envelope를 사용한 deterministic
  LoD1 단순화 산출물은 생성·hash-bind할 수 있다. 같은 LoD2 또는 같은 생산 계보로
  평가할 때는 `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`와
  `REFERENCE_DERIVED_SELF_CONDITIONED`로 표시하고 primary C5, `E_paired`,
  `Delta_N_pass(C5)`에 사용하지 않는다. 독립 평가 reference가 확보되면 primary C5
  후보 승격을 별도 Gate decision으로 검토한다.
- **Evidence:** 사용자의 2026-08-01 “LoD1은 LoD2 기반으로 만들면 된다”는 명시적
  지시와 현재 local LoD2 reference 두 파일의 verified provenance.
- **Reason:** 실행 가능한 LoD1 diagnostic을 만들면서도 동일 정답의 footprint/height가
  입력과 평가에 동시에 들어가 독립 prior 효과로 과장되는 것을 막는다.
- **Affected phases:** Gate S0 evidence completion, P2/P3 diagnostic
- **Affected documents:** `00_RESEARCH_CHARTER.md`, `01_MASTER_ROADMAP.md`,
  `03_DATA_AND_BASELINE_SCOPE.md`, `GATE_S0_FREEZE_PACKET_v1.md`, 다음 Task Packet
- **User approval:** `GRANTED FOR AUTONOMOUS BOUNDED PREPARATION`; scientific Gate와
  primary 승격은 별도 human decision
- **Superseded decisions:** independent LoD1 primary 원칙은 유지한다. LoD2-derived
  LoD1의 생성 자체를 전면 중단시키는 해석만 supersede한다.

### Consequence

- 다음 evidence task는 LoD2→LoD1 rule/config/output hash를 만들 수 있다.
- scored RoofSurface topology와 semantic label은 LoD1 diagnostic에 전달하지 않는다.
- source LoD2와 평가 reference가 같으면 결과는 self-conditioned diagnostic이다.
- 이 diagnostic은 independent LoD1 탐색의 반복을 요구하지 않으며, primary C5 부재를
  숨기지 않는다.

## DEC-P1-012 — exact 962/937/25 source set과 C5 독립 평가 원칙

- **Decision ID:** `DEC-P1-012`
- **Date:** 2026-08-01
- **Status:** `USER-APPROVED GATE S0 INPUT DECISION`
- **Previous state:** `B_CURRENT_CANDIDATE_c205892c390997b5`는 962 image members,
  937 calibrated image/pose pairs와 25 no-pose exclusions를 정확히 재현했지만
  candidate로 남아 있었다. R2A LoD2-derived LoD1은 같은 reference 계보 평가에서
  diagnostic-only였고, primary C5 입력 후보 승격에는 별도 human decision이 필요했다.
- **New decision:** exact 962 image members, 937 calibrated image/pose pairs와 25
  `NO_CALIBRATED_CAMERA_POSE_IN_OPF` exclusions를 Gate S0 common source membership으로
  확정한다. C5는 R2A의 LoD2-derived LoD1 bytes를 입력 후보로 사용하되, primary
  evaluation은 입력 LoD2와 독립된 exact reference 계보를 사용해야 한다. 독립
  reference가 bind되기 전에는 기존 R2A artifact의
  `REFERENCE_DERIVED_DIAGNOSTIC_ONLY`,
  `REFERENCE_DERIVED_SELF_CONDITIONED`, `primary_c5_eligible=false` 표시를 유지하고
  과거 manifest/receipt를 수정하지 않는다.
- **Evidence:** R2A source replay 962/937/25 contradiction 없음, output commit
  `4d02792861d4b57cb29f22b0fbce923997a54cef`, closed commit
  `00181afc4dc1a5e5c520f4b7783fdb4dbf2ae9c8`, 사용자의 2026-08-01 명시적 승인.
- **Reason:** 이미 검증된 exact source membership을 반복 조사하지 않고 derivative
  lineage에 집중하며, LoD2-derived LoD1 사용 의도를 보존하면서 동일 정답 계보의
  자기참조를 primary C5 효과로 해석하는 것을 막는다.
- **Affected phases:** Gate S0, P2–P4
- **Affected documents:** `01_MASTER_ROADMAP.md`, `06_DECISION_LOG.md`,
  `P2_W2C_GATE_S0_COMMON_BASE_LINEAGE_R2B_v1.md`, 다음 Gate S0 freeze revision
- **User approval:** `GRANTED — R2B commit/push/Experiment Host handoff; exact
  962/937/25 freeze; C5 LoD2-derived LoD1 with independent evaluation reference`
- **Superseded decisions:** `DEC-P1-011`의 same-reference diagnostic 격리는 유지한다.
  독립 reference가 bind된 뒤 primary candidate를 다시 검토할 수 있다는 조건부
  조항의 human input 선택만 이 결정이 충족한다. Gate S0 전체 승인과 performance
  실행 권한은 부여하지 않는다.

### Consequence

- exact source membership을 다시 계산·검색·재해시하지 않는다.
- R2B는 기존 exact-937 P0 derivative 계보를 먼저 resolve하고 새 dense 계산을
  자동 승인하지 않는다.
- C5 primary 실행 전 geometry/structure evaluation reference의 exact ID, version,
  production lineage와 독립성 class를 별도 Gate evidence로 bind한다.
- 독립 reference가 확보되지 않으면 LoD2-derived LoD1 결과는 self-conditioned
  diagnostic으로만 보고한다.
- `scientific_verdict`는 null이며 P2 performance는 Gate S0 전체 freeze 전까지
  계속 금지한다.

## DEC-P1-013 — C1/C2 development feasibility pilot와 C3 순서

- **Decision ID:** `DEC-P1-013`
- **Date:** 2026-08-02
- **Status:** `USER-APPROVED BOUNDED GATE DECISION`
- **Previous state:** promoted Gate S0 evidence fixed `U_target=199`, a technical
  `E_paired` candidate set of 72 buildings and a 51/11/10 split, but only nine
  independent groups overall and two held-out groups. The evidence therefore allowed
  only `PILOT_ONLY_REFERENCE_SCOPE` and prohibited every performance run until a
  separate human Gate decision.
- **New decision:** authorize `C1_L_upper` and `C2_MVS` on the exact 51-building,
  five-group development split only, after reviewed implementation and a validated
  two-host handoff. Validation 11 and held-out 10 remain inaccessible. C3--C5
  execution remains prohibited. The development result is used to draft the first C3
  training strategy, which requires a separate DRAFT, review and activation.
- **Evidence:** R1 promoted result `U_target=199`, `E_paired=72`, groups `9`, split
  buildings `51/11/10`, split groups `5/2/2`; human instructions on 2026-08-02 to run
  the quick LiDAR/MVS baselines first and then design C3.
- **Reason:** C1 and C2 are direct Stage-3 baselines without GS training. They expose
  common read-out failures and the MVS-to-upper-baseline gap before the no-external-
  prior GS representation/loss/schedule is chosen. Preserving validation and held-out
  keeps later selection and final evaluation separable.
- **Exact human approval:**
  `docs/research/preregistration/gate_s0/GATE_S0_C1_C2_DEVELOPMENT_PILOT_APPROVAL_v1.md`
- **Affected phases:** P2 development baseline; C3 strategy preparation
- **User approval:** `APPROVE_DEVELOPMENT_FEASIBILITY_PILOT_ONLY`
- **Scientific verdict:** `null`
- **Superseded decisions:** the blanket prohibition on every P2 pilot after the R1
  blocker evidence is narrowed only for this exact C1/C2 development task. The
  confirmatory blocker, validation/held-out protection, `DEC-P1-011` diagnostic C5
  isolation and all protected-history rules remain.

### Consequence

- C1 is reported only as `SELF_REFERENCE_UPPER_BASELINE`; it is not pooled or ranked
  as if it shared C2's independent accuracy reference.
- C2 uses the exact common-base MVS derivative and independent UAS reference only for
  scoring; UAS/LoD2/reference geometry cannot enter reconstruction, registration,
  cropping or `R_derived` generation.
- Development group sizes are 47, 1, 1, 1 and 1. Reports include group-balanced
  summaries and do not treat 51 buildings as 51 independent repetitions.
- G0--G2 are provisional technical outcomes under a precommitted schema. G3, G4,
  `PASS_usable`, confirmatory inference and population/generalization claims remain
  unavailable. LoD1.1 fallback is not counted as LoD2.2 success.
- Exact method/config/schema/tests must be committed and independently reviewed
  before activation. Experiment Host may execute and promote outputs only after an
  immutable `100-accepted` ownership transfer.
- Synthetic smoke failure closes as a technical blocker without scientific payload
  access. Success or failure returns writer ownership through verified/blocked 200
  followed by direct-child 300.

## DEC-P1-014 — sealed C3 checkpoint의 development Stage 3 기술 진단

- **Decision ID:** `DEC-P1-014`
- **Date:** 2026-08-03
- **Status:** `USER-APPROVED BOUNDED TECHNICAL CONTINUATION`
- **Previous state:** `DEC-P1-013`은 C1/C2 development feasibility만 허용하고 C3에는
  별도 DRAFT·검토·activation을 요구했다. 이후 승인된 first-wave handoff에서 exact
  937-view C3 seed-0 30k 학습이 기술적으로 완료됐지만, 실제 surface extraction과
  footprint-free Roofer read-out은 보호된 source 부재로 실행되지 않았다.
- **New decision:** 닫힌 R4 C3 30k checkpoint를 재학습하지 않고 development 51동에
  대해서만 저장 Stage-2 group 기반의 bounded Stage 3 기술 진단을 실행할 수 있다.
  모든 geometry와 `R_derived`를 score/reference보다 먼저 봉인하고, validation 11동과
  held-out 10동은 열지 않는다. 큰 component가 여러 건물에 연결되거나 한 건물이 여러
  component에 걸치면 G0/G1은 component-level 진단으로만 보고하며 건물별 gate는
  `null`로 둔다. G2, G3, G4, `PASS_usable`과 scientific verdict도 `null/PENDING`이다.
- **Evidence:** 승인된
  `P2_W2C_C1_C2_G2_C3_FIRST_WAVE_v1.md`의 explicit next task, R4 closed checkpoint
  `bec692b0...`, 그리고 2026-08-03 Work Host 세션에서 사용자가 같은 development
  건물로 C3까지 순서대로 진행하고 단계별·최종 결과를 만들라고 반복 승인한 지시.
- **Reason:** 완료된 학습을 실제 Stage 3 기술 결과로 연결하되, C1/C2에서 발견된
  coarse-component 중복을 건물 성공 수로 과장하지 않고 다음 building-instance
  adapter 결정을 실측 근거로 내리기 위함이다.
- **Affected phases:** P2 development C3 technical diagnostic only
- **User approval:** `GRANTED_FOR_BOUNDED_C3_DEVELOPMENT_STAGE3_EXECUTION`
- **Scientific verdict:** `null`
- **Superseded decisions:** `DEC-P1-013`의 C3 전면 실행 금지를 이 exact bounded
  development Stage 3 task에 한해서만 좁힌다. C4/C5, validation, held-out,
  confirmatory performance와 final acceptance 금지는 유지한다.

### Consequence

- source implementation, DRAFT review, activated packet, 000/100 writer transfer가
  모두 일치한 뒤에만 Experiment Host가 실행한다.
- checkpoint와 R3 score-cell reuse ledger를 우선하며 C1/C2, semantic, training,
  15.7 GB R1 input, `Images.zip`, `OPF.zip`을 재실행·재해시하지 않는다.
- 결과는 component multiplicity, unique Roofer operation 결과, development 51행의
  nullable technical table과 한글 설명을 포함한다.

## DEC-P1-015 — U_target 199동 C1/C2/C3 전수 기술 실행과 계약 결과 생성

- **Decision ID:** `DEC-P1-015`
- **Date:** 2026-08-03
- **Status:** `USER-APPROVED U_TARGET CENSUS EXECUTION`
- **Previous state:** `DEC-P1-013`과 `DEC-P1-014`가 기존 72동 후보 중 development
  51동만 열고 validation 11동과 held-out 10동을 보호했다. 127동은 방법 실패가 아니라
  reference/input eligibility 부족으로 실행 분모 밖에 있었다.
- **New decision:** C1/C2/C3의 현재 동결 구현을 `U_target=199` 전 건물에 적용한다.
  입력 또는 UAS reference 부족은 사전 제외하지 않고 건물×방법 결과 행의 명시적
  missing/failure로 유지한다. 결과는
  `04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`의 단계별 metric/gate 표와 Sheet A/B/C를
  199동 전수에 생성한다.
- **Evidence:** 사용자의 2026-08-03 명시적 지시: “199동에 대해서 전체로 일단
  수행”하고 계약 산출물을 직접 생성할 것.
- **Consequence:** 기존 validation/held-out membership은 이 전수 기술 실행으로
  열리므로 더 이상 미열람 confirmatory test라고 주장하지 않는다. 후속 최종 일반화
  주장은 새 독립 test set 또는 별도 승인된 검증 설계가 필요하다.
- **Execution boundary:** C1/C2/C3만 실행한다. C4/C5 성능, Fusion W1, R_ext는 실행하지
  않는다. 이미 봉인된 component/Roofer 결과와 checkpoint를 우선 재사용하고 중복
  Roofer 실행 및 R1/Images.zip/OPF.zip 재해시를 금지한다.
- **Verdict:** numerical G3/G4 criterion freeze 전 공식 `PASS_usable`은 null이다.
  동일 수치의 diagnostic candidate gate와 연속 metric은 함께 보고한다.
- **Scientific verdict:** `null`

## Pending decisions not yet logged as adopted

다음은 선택지가 정리되었으나 사용자 결정 전이므로 adopted decision이 아니다.

- final P2 building-instance Stage-3 adapter, generic C3 val3dity path, G3/G4
  numerical thresholds and `PASS_usable` criterion
- materially broader independent reference coverage for a confirmatory claim and an
  independently sourced LoD1 prior for primary C5 interpretation
