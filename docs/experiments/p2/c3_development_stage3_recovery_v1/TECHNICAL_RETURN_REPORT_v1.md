# C3 development Stage 3 recovery 기술 결과 보고서 v1

- task: `P2-C3-DEVELOPMENT-STAGE3-v1`
- handoff: `P2-W2C-C3-DEVELOPMENT-STAGE3-RECOVERY-v1`
- source commit: `9f223911a38cb40028e974d706dffa2f28937201`
- accepted commit: `3c856b117d5e72a2dcf7f2fc80655ddcb143443c`
- 기술 상태: `COMPLETE`
- scientific_verdict: `null`

## 한 줄 결과

기존 C3 30k 모델에서 실제 surface와 Roofer 결과를 처음 생성했다. 다만 51동 중
건물 하나와 component 하나가 일대일로 대응한 경우는 6동뿐이며, 이 6동에서 Roofer
LoD2.2 생성은 5동이다. 나머지를 실패 건물로 세지 않고 association 불확실로
분리했다.

## 단계별 결과

| 단계 | 결과 | 의미 |
|---|---:|---|
| checkpoint | 406,337 primitives | R4 seed-0 30k 모델을 재학습 없이 1회 읽음 |
| 저장 group | 812 groups / 319,698 grouped primitives | 재군집 없이 Stage-2 group 그대로 사용 |
| surface | 51,009 points / 202 components | 1 m grid, building max-Z와 terrain min-Z |
| development 연결 | 37/51 | 적어도 한 C3 component와 겹침; 성공 수가 아님 |
| 일대일 연결 | 6/51 | 건물별 gate를 혼동 없이 귀속할 수 있음 |
| Roofer | 18 unique operations | 공유 component 중복 19회를 방지함 |
| component G0 | 16/18 | LoD2.2 roof/wall/ground가 실제 생성됨 |
| component G1 | 18/18 | 내부 CityJSON 구조·semantic screen 통과 |
| building G0 | 5/6 | 일대일 연결 6동에서만 계산 |
| building G1 | 6/6 | 일대일 연결 6동에서만 계산 |
| G2/G3/G4/PASS | `PENDING` | 이번 기술 runner의 범위 밖이며 성공 수가 아님 |

G0가 false인 component는
`C3_GS_image_COMP_4e02547eef70fff90c52`와
`C3_GS_image_COMP_a668b6bac9cea7a36110`이다. 두 작업 모두 Roofer process는 정상
종료했지만 출력에 LoD2.2 roof/wall/ground가 없어서 G0를 통과하지 못했다.

## 왜 51동 중 6동만 건물 단위로 셌는가

C3 surface는 footprint를 학습 입력으로 사용하지 않고 영상 기반 group에서 만들었다.
그래서 큰 component 하나가 여러 건물을 함께 덮거나, 한 건물이 여러 component와
겹치는 일이 발생했다. 실제 결과는 다음과 같이 분리된다.

- 37동: 하나 이상의 component와 연결됨
- 6동: 건물 1개와 선택 component 1개가 서로 일대일이어서 건물별 판정 가능
- 31동: 연결은 됐지만 component 공유·분할 때문에 건물별 G0/G1을 귀속하지 않음
- 14동: 연결 component가 없음

따라서 `6/51`은 C3가 6동만 복원했다는 뜻이 아니다. 현재 footprint-free
component를 51개 평가 건물에 자동 귀속하는 방법이 거칠다는 뜻이다. component
수준에서는 실제 Roofer 대상 18개 중 16개가 LoD2.2를 만들었다.

## 04 결과계약과의 위치

- `G_native`: 기존 R4에서 완료
- `S_extracted`: 이번 실행에서 완료
- `P_Roofer`: 이번 실행에서 완료
- `H_LoD2`: 18 component 출력 생성, 그중 16개 G0 충족
- `A_acceptance`: G0/G1 기술 진단만 완료; G2--G4와 `PASS_usable`은 아직 미완료

즉 04 계약의 artifact chain은 이제 실제 C3 Roofer 모델까지 이어졌지만, 최종
성공 건물 수와 C1/C2/C3 성능 비교를 말할 단계는 아니다. 다음 bounded task는
동일 51동에서 component 공유를 결과 조작 없이 명시적으로 다루고, 독립 UAS
reference로 G2--G4와 정성 비교판을 생성하는 평가 task여야 한다.

## 재현성과 중복 방지

- R4 checkpoint full rehash: 0회; closed attestation + byte count + 안전한 deserialize
- R3 score cells: geometry 봉인 뒤 full read+digest 1회
- R1 15.7GB, Images.zip, OPF.zip 재해시: 0회
- C1/C2 재구성 또는 Roofer 재실행: 0회
- validation/held-out/C4/C5/Fusion W1/R_ext 접근: 0회
- unique component Roofer: 각 1회, terminal receipt 18개

external namespace:
`artifact://JointBuildGS/phase-payloads/p2/c3_development_stage3_v1/P2-C3-DEVELOPMENT-STAGE3-v1/`
