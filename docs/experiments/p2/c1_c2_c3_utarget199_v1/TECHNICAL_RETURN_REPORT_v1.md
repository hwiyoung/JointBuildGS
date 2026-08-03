# C1/C2/C3 기술 실행 결과: C3 학습은 완료됐고 Stage 3의 건물별 read-out은 아직 약하다

- task: `P2-C1-C2-C3-UTARGET199-v1`
- 기술 상태: `COMPLETE`
- scientific_verdict: `null`
- official G3/G4/PASS_usable: `null`

## 기술 요약

C1/C2 3동 비교판과 C3-1/C3-2 30,000-step 학습, C3 `U_target=199`
후처리까지 모두 산출물 단위로 완료했다. C1/C2는 60개 패널과 exact 정량 6행을
재계산 없이 조립했다. C3는 같은 937-view image-derived base와 같은 seed 0을 쓰고,
C3-2에만 image-derived MVS depth loss를 추가해 두 조건의 차이를 고정했다.

중요한 기술 결과는 두 층으로 나뉜다.

1. **GS 자체 산출물은 정상적으로 존재한다.** 두 30k checkpoint, 실제 gsplat
   RGB/semantic/depth 렌더 8장, native Gaussian center PLY, oriented 2D Gaussian
   surfel mesh가 모두 생성됐다.
2. **건물별 Roofer read-out은 현재 결합 규칙에서 충분하지 않다.** 199동 중 frozen
   component와 연결된 건물은 C3-1 16동, C3-2 18동뿐이고, one-to-one 연결은 조건별
   3동이다. 건물 단위 G0는 두 조건 모두 0동이어서 공식 G3/G4/PASS와 연속 정확도
   수치는 모두 `null`로 남겼다.

이는 실행 실패나 Roofer 프로세스 실패가 아니라, 학습된 전역 GS surface group을
1 m class-2/6 증거로 물질화한 뒤 안정 건물 ID에 결합하는 현 read-out 계약의 제한을
보여주는 비확증 기술 결과다.

## GS 결과와 건물별 read-out이 서로 다른 상태를 보인다

| 조건 | 30k primitive | frozen component | Roofer 입력점 | 건물 연결 | one-to-one | building G0 |
|---|---:|---:|---:|---:|---:|---:|
| C3-1: 2DGS + semantic | 333,738 | 36 | 1,199 | 16/199 | 3/199 | 0/199 |
| C3-2: 2DGS + semantic + MVS depth | 396,146 | 51 | 1,568 | 18/199 | 3/199 | 0/199 |

C3-2가 더 많은 primitive, component, 물질화 점과 연결 건물을 만들었지만, 이 차이는
공식 성능 우위나 사용 가능성 판정이 아니다. 건물 G0가 0이고 G3/G4 임계값도 잠겨
있지 않으므로 이 표는 구조적 진단값으로만 읽어야 한다.

대표 3동 원해상도 case sheet를 직접 검토했다.

- `DEBY_LOD2_4907177`: 두 조건 모두 `UNASSOCIATED`. C1/C2에서 이미 분리한
  2024 RGB–2022 LoD2 reference/ID alignment review 대상이며 C3 실패 원인으로
  재명명하지 않는다.
- `DEBY_LOD2_4906975`: 두 조건 모두 `UNASSOCIATED`. native GS geometry는 있지만
  해당 stable-ID bbox에 결합된 Roofer building output은 없다.
- `DEBY_LOD2_108580336`: C3-1은 `UNASSOCIATED`, C3-2는 `ONE_TO_ONE`이며 component
  schema/semantic은 통과했지만 building G0는 false이고 연속 정확도는 산출하지 않았다.

## 범위·입력·지표 정의

- C1/C2 정성·정량 표본: `DEBY_LOD2_4907177`, `DEBY_LOD2_4906975`,
  `DEBY_LOD2_108580336`; 3 case sheets, 60 panels, exact source 정량 6행.
- C3 모집단: 사전 제외 없이 `U_target=199` 전부, 조건당 199행으로 총 398행.
- C3 독립 reference: 현재 UAS LiDAR에서 고정한 평가용 셀이다. 학습 seed, Roofer
  입력, `R_derived`, roofprint 또는 geometry 생성에 쓰지 않고 두 조건 geometry가
  모두 봉인된 뒤 평가/표시에만 열었다.
- `associated`: stable-ID bbox 안 frozen component cell-center가 하나 이상 있어
  결정 규칙으로 component를 연결한 건물 수.
- `one-to-one`: 한 건물과 한 component가 서로 공유되지 않고 대응한 경우.
- `building G0`: 해당 건물에 귀속시킬 생성 LoD2 building output이 존재하는가.
  component-level schema 성공과 별개다.

## 동일 seed에서 depth loss만 달리한 실험 설계

두 조건은 seed 0, 371,808 SfM sparse points, 103,546 neutral dense representatives,
초기 primitive 475,354개, exact 937 views를 공유한다. dense seed는 MVS geometry를
그대로 정답으로 고정한 것이 아니라 초기화 표본이며, 5,000 iteration까지 prune에서만
보호한 뒤 GS 최적화와 grow/prune을 허용했다.

공통 loss는 photo `1.0`, semantic `0.1`, normal-consistency `0.05`, scene-scale 정규화
distortion `100.0`이다. 요청대로 structural, mutual, MVC, external-prior loss는 모두
0이다. C3-2만 image-derived MVS depth `0.03`을 iteration 5,000부터 10,000까지 ramp로
추가했다. C3-1은 129.9분 후 333,738 primitive, C3-2는 86.6분 후 396,146 primitive로
각각 30,000 iteration을 종료했다. OOM, NaN, checkpoint restart는 없었다.

## Stage 3는 GT roofprint 없이 component 자체의 R_derived를 사용했다

각 checkpoint의 저장된 Stage-2 group을 그대로 사용해 native PLY/mesh와 1 m
class-2/6 evidence를 먼저 봉인했다. 이 시점의 stable-ID bbox, UAS reference cell,
external/GT roofprint 접근은 모두 0이었다. 봉인 후 bbox를 열어 component를 연결했고,
선택된 unique component 25개에 대해 Roofer를 한 번씩 실행했다. `R_derived`는 각 C3
component 자체에서 만들었으며 GT footprint/roofprint는 사용하지 않았다.

C3-1은 1,713 stored groups 중 12,844 grouped primitive를 1,199점으로 축약했고,
C3-2는 3,009 groups 중 23,104 grouped primitive를 1,568점으로 축약했다. 전체
checkpoint primitive를 표시하는 native PLY/mesh와 Roofer용 축약 증거를 같은 것으로
오해하지 않도록 case sheet에서 층을 분리했다.

## 제한과 강건성 확인

- 398행 중 reference cell이 있는 행은 조건별 79개지만, 예측 roof surface와 건물
  귀속이 없으면 RMS/MAE를 계산하지 않았다. `null`을 0이나 실패 점수로 대체하지 않았다.
- C3-1 183동, C3-2 181동이 `UNASSOCIATED`다. 이 결과는 현재 전역 grouping–1 m
  물질화–stable-ID association 계약에 민감하며, GS 표현 자체가 전부 비어 있다는 뜻은
  아니다.
- 첫 postprocess의 정량/Roofer는 완료됐으나 qualitative gsplat 배경 채널 결함으로
  렌더가 중단됐다. 그 namespace를 보존하고 294개 파일을 byte-identical recovery한 뒤
  누락된 렌더/case sheet만 생성했다. recovery Roofer 및 metric 재계산은 0이다.
- GPU1의 별도 사용자 프로세스 때문에 C3-2를 GPU0에서 순차 실행했다. 외부 프로세스를
  종료하지 않았고, 이 자원 경합을 모델 실패로 분류하지 않았다.
- C1 self-reference metric과 독립 UAS green overlay는 서로 다른 역할이다. 전자는
  기존 C1 output과 그 exact source binding의 자기 일치 수치이고, 후자는 현재 UAS
  평가/표시 reference다.

## 다음 단계

1. C4/C5로 넘어가기 전에 C3의 stored group → 1 m class-2/6 materialization에서 왜
   333k/396k primitive가 1,199/1,568점과 36/51 component로 축약되는지 진단한다.
2. GT roofprint를 Stage 3 입력으로 넣지 않은 채, image-derived building support 또는
   component association 규칙을 개선할 수 있는지 별도 preregistration으로 고정한다.
3. 인간 검토자가 199 case sheets와 actual GS render를 보고 C3 representation 품질과
   building read-out 실패를 구분해 판단한다.

## 남은 질문

- component-level CityJSON schema 성공을 건물별 G0로 연결하지 못하는 주원인이
  materialization 희소성인지, grouping 범위인지, stable-ID association인지 추가 분해가
  필요하다.
- 변경 건물과 비변경 건물의 2022 LoD2 사용 방식은 별도 평가 설계가 필요하다. 현재
  결과는 그 LoD2를 C3 입력이나 scientific verdict로 사용하지 않았다.

모든 기술 산출물은 검토 근거다. 사람의 별도 승인 전까지 `scientific_verdict: null`이며,
공식 G3/G4/PASS, 유효성 우위, 일반화·모집단 결론을 뜻하지 않는다.
