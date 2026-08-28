# 실험 지도 v2 — 방법론 단계·종류·과거 코드 대응 (2026-08-28)

- 지위: 명명 규약 + 색인. `DEC-P1-025` 방법론 addendum 반영. 실행 권한 없음.
  `scientific_verdict: null`.
- 원칙: **코드명 대신 "무엇을-어떻게" 한국어 이름을 정본으로** 쓴다. 과거
  코드(D1, E9, HV, AX 등)는 이력 라벨로만 남기고 신규 발행하지 않는다.

## 1. 현재 증거 유형

| 종류 | 정답이 있는가 | 답하는 질문 | claim 경계 |
|---|---|---|---|
| **① 기술 측정** | 봉인 산출물 또는 score-only reference | 문제가 얼마나 크고, 대상이 몇 동인가 | development evidence |
| **② 통제 주입** | **있음 — 원인과 크기를 우리가 넣음** | 탐지·정합·source decision 기제가 작동하는가 | mechanism만; 실제 필요성 주장 금지 |
| **③ 실데이터 개발 판독** | 불완전한 라벨/score reference | benign non-degradation과 실제 failure mode가 보이는가 | non-confirmatory |
| **④ 독립 장면 시험** | 독립 current reference와 sealed protocol | selective risk와 일반화가 재현되는가 | confirmatory 후보 |

②·③·④는 절대 섞어 보고하지 않는다. 합성 차이는 기제 검증에 필요하지만 실제
상보성을 만들어내는 근거가 아니며, 기존 93/199는 ④가 아니다.

## 2. 박사 방법론 단계

정본 설계:
`methodology_v1/MINIMUM_RISK_PRIOR_GUIDED_RECONSTRUCTION_ko_v1.md`.

| 단계 | 한국어 이름 | 증거 유형 | 핵심 비교/산출물 |
|---|---|---|---|
| `M0` | **출처 오차·계보 감사** | ① | source×error×observable×latent×loss/action 표 |
| `M1` | **국소 상보성·기준선 시험** | ①+②+③ | image-only, prior-only, registered prior, union, fixed/adaptive loss, local oracle |
| `M2` | **순차 최소위험 중재** | ②+③ | 강한 `align→decide→fuse`, calibration, abstention |
| `M3` | **반복 공동추정 절제** | ②+③ | sequential vs alternating; joint-method kill/simplify |
| `M4` | **하류 전이 시험** | ③ | 직접 geometry와 사전 선택한 복수 probe |
| `M5` | **독립 장면 시험** | ④ | sealed risk–coverage, non-degradation, generalization |

`local oracle`은 평가 reference를 사용하는 상한 측정이며 method 입력이 아니다.
`prior-only`는 필수 comparator이지만 현 E1–E6를 바꾸거나 E7을 승인하지 않는다.

## 3. 과거 코드 → 직관적 이름 대응표

| 과거 코드 | 정본 이름 | 종류 | 한 줄 요약 |
|---|---|---|---|
| A2 (E7/E8) | **단순-결합 대조** | ① | prior를 그냥 합치면(union) 얼마나 좋아지나 — 채움 이득 실측 |
| D1 | **결합 오차-주입 커브** | ② | union에 정합 오차 δ를 일부러 넣으면 어디가 얼마나 오염되나 |
| D2a | **GS 오차-주입 스모크** | ② | 같은 δ를 GS 학습에 넣으면? (봉인 레시피는 불활성 판명) |
| E9 | **선택-결합 규칙 시험** | ②+① | 기하 규칙만으로 "이득 유지+오염 차단"이 되나 → 불가, 모호성은 수직-분리 클래스에 응집 |
| E9-0 | **분류-구멍 측정** | ① | "영상 실패" 중 분류 실패로 고칠 수 있는 몫(7/93동) |
| HV-1 | **3D-검사 전맹 측정** | ① | 값싼 3D 비교(C2C)가 미세 오차를 얼마나 못 보나 (AUC 0.57, 평지붕 전맹) |
| AX-10 | **모집단 층화 측정** | ① | "변화 ∧ 영상 불충분" 건물이 몇 동인가 (N=22/12) |
| — (신규) | **원인 귀속 라벨링** | ① | 붕괴 45동의 실패 원인 5분류 (라벨=리뷰어) |
| HV-3 → | **판정전(判定戰)** | ②+③ | 본 실험 — 아래 3막 |

"HV"는 Hypothesis-Verification(가설-검증) 시리즈의 옛 코드였다 — 폐기.

## 4. 역사적 판정전 (3막 구성)

역사적 정본 문서: `verification_trial_v1/JUDGE_TRIAL_PREREG_ko_v1.md`. 이 3막은
M0–M3의 선행 기술 증거·후보 절제이며 현재 박사 방법론 전체와 동일하지 않다.

| 막 | 이름 | 종류 | 무엇을 하나 |
|---|---|---|---|
| 1막 | **오차-주입 판정전** | ② | 위치를 아는 만큼 틀어놓은 prior를 렌더-대조가 잡아내는가 — 3D 전맹 기준선을 이기는가 |
| 2막 | **변화-주입 판정전** | ② | 증축/철거/지붕형을 합성한 "낡은 prior"를 렌더-대조가 기각하는가 |
| 3막 | **실전 판정전** | ③ | 진짜 변화 12동(+22동 확장)의 구지붕을 잡고, 비변화 건물은 통과시키는가 |

## 5. 명명 규칙 (신규 발행)

- 태스크 ID: `PHD-<무엇을>-<어떻게>-vN` (예: `PHD-JUDGE-TRIAL-v1`)
- 문서·보고·대화의 정본 호칭은 한국어 이름. 코드 축약이 필요하면 이 지도에
  행을 먼저 추가한 뒤 사용한다(지도에 없는 코드 사용 금지).
