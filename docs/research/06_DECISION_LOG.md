# Research Decision Log

- Document status: `USER_APPROVED_RESEARCH_DECISIONS`
- 문서 버전: `C1C5_CANON_v1`
- 작성일: 2026-07-31
- 승인 상태: `USER APPROVED CURRENT C1–C5 CANON — 2026-07-31`

`DEC-P1-008` 이후 이 log와 00–06 contract set이 현재 C1–C5 프로그램을 통제한다.
`RESEARCH_CONTEXT.md`와 `EXPERIMENT_PLAN.md`는 기존 4조건 프로그램의 역사 기록이다.
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
- **Previous state:** 00–06은 P1 audit 기준으로만 승인됐고 `RESEARCH_CONTEXT.md`,
  `EXPERIMENT_PLAN.md`와 Fusion W1이 계속 우선했다. 기존 4조건과 새 5조건의 관계는
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
  `RESEARCH_CONTEXT.md`, `EXPERIMENT_PLAN.md`, research entrypoints, Gate S0 packet
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

## Pending decisions not yet logged as adopted

다음은 선택지가 정리되었으나 사용자 결정 전이므로 adopted decision이 아니다.

- TUM2TWIN LoD1 후보가 독립 prior로 적합한지
- `U_target`/`E_paired` exact IDs, 전수 가능성, pilot/validation/held-out 수량과
  공간 group 경계
