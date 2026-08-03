# P2 development C1–C3 입력·처리·결과 설명서 v1

## 결론부터

현재 C1은 **좋은 센서 입력을 사용한 상한 후보**이지만, 만들어진 Roofer 결과는
51동을 독립적으로 표현하지 못한다. 51동 전체가 CityJSONSeq 한 개를 공유한다.
그 한 파일은 G2 위상검사를 통과했지만, 후보 높이 정확도는 2/51만 통과했다.
따라서 현재 C1 결과를 검증 없이 “신뢰할 수 있는 정답” 또는 “성능 상한”으로 쓰면 안 된다.

## 왜 이 건물들을 사용했나

전체 AOI 199동 중 독립 UAS 지붕 관측과 pilot 입력 지지가 있는 72동을 결과를 보기 전에
골랐다. 이 중 development 51동만 C1–C3 설계 확인에 사용했다. validation 11동과
held-out 10동은 열지 않았다.

정성 비교 5동은 성공·실패 결과로 고른 사례가 아니다. development에 존재하는 5개
공간 group에서 각각 한 동을 `MIN_SHA256(task_id|group_id|building_id)` 규칙으로
결과를 보기 전에 선택했다. 따라서 다섯 그림은 좋은 사례 모음이 아니라 공간 group별
고정 점검 사례다.

## 각 조건에 무엇을 넣고 어떻게 처리했나

| 조건 | 실제 입력 | 처리 | 나온 모델 |
|---|---|---|---|
| C1 | current UAS LiDAR grid의 min/max/count | class 2/6 점군 → 동일 Roofer Stage 3 | AOI 전체가 연결된 component 1개와 CityJSONSeq 1개 |
| C2 | 937-view common-base dense MVS | GS 없이 바로 component/Roofer | component 6개; 50/51동 연결 |
| C3 | 같은 937 images/poses, dense MVS, semantic | seed 0 GS 30k → surface 202개 → Roofer | Roofer 작업 18개; 건물과 정확히 1:1인 것은 6/51 |

C1의 UAS input과 C1 geometry 평가용 UAS cell은 같은 원자료 계보다. 그러므로 C1의
G3/G4는 Roofer 변환 과정에서 원자료 형상을 얼마나 보존했는지 보는 자기참조 진단이지,
독립 정확도 평가는 아니다.

## 단계별 정량 결과

| 조건 | 건물 | 실제 독립 Roofer output | G0 생성 | G1 형식 | G2 위상 | G3 후보 | G4 후보 | 공식 PASS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| C1 UAS LiDAR | 51 | 1 | 51* | 51* | 51* | 0 | 2 | `null` |
| C2 MVS | 51 | 6 | 50 | 50 | 50 | 0 | 6 | `null` |
| C3 GS | 51 | 건물 1:1은 6 | 35** | 37** | 19 | 0 | 1 | `null` |

`*` C1의 51은 51개 독립 모델이 아니라 같은 단일 CityJSONSeq 결과를 51동에 상속한
수다. 실제 G2 validator 실행은 1회이며 그 단일 output이 valid였다.

`**` C3는 평가 component 관점의 수다. strict 건물 단위로는 1:1 연결 6동 중 G0 5,
G1 6이다.

G3의 0은 최종 지붕구조 실패 수가 아니다. 현 matcher가 큰/concave Roofer surface와
작은 UAS roof patch를 대응시키지 못해 C1–C3 모두 0이 됐다. matcher를 고치기 전에는
공식 G3로 사용할 수 없다.

G4 후보는 coverage≥0.8, MAE/RMSZ/RMSE≤1 m, p95≤2 m의 임시 규칙이다. C1은 2/51,
C2는 6/51, C3는 1/51이었다. 아직 수치 기준이 동결되지 않았으므로 공식 G4가 아니다.

## C1을 눈으로·수치로 보면

- C1 height MAE 중앙값: `5.22 m` (Q1–Q3 `2.25–8.61 m`)
- C1 RMSZ 중앙값: `5.81 m` (Q1–Q3 `2.86–10.61 m`)
- C1 surface-distance p95 중앙값: `8.76 m`
- pinned val3dity: 단일 C1 output `PASS`

UAS 입력 자체가 나쁘다는 뜻은 아니다. C1 input의 ground/building points가 AOI 전체에서
연결된 채 하나의 Roofer 작업으로 들어갔고, 그 결과 큰 RoofSurface가 여러 건물을 함께
덮었다. 즉 현재 C1의 실패 지점은 주로 **건물별 분리와 Stage 3 read-out**이다.

## 고정 5동에서 확인되는 것

| 건물 | 선정 이유 | C1 MAE / RMSZ | C3 상태 | 그림에서 볼 것 |
|---|---|---:|---|---|
| 4906981 | 해당 공간 group의 사전 hash 선택 | 2.96 / 3.19 m | shared+multi component | C1/C2/C3 면이 건물보다 넓게 이어짐 |
| 4906982 | 해당 공간 group의 사전 hash 선택 | 3.81 / 3.82 m | 정확한 1:1 후보 | C3도 다중 roof fan이 생김 |
| 4959314 | 해당 공간 group의 사전 hash 선택 | 8.61 / 8.62 m | unassociated | C3 Roofer 결과가 건물에 연결되지 않음 |
| 4959327 | 해당 공간 group의 사전 hash 선택 | 1.42 / 1.60 m | 정확한 1:1 후보 | C3 면은 있으나 높이 후보 실패 |
| 4959461 | 해당 공간 group의 사전 hash 선택 | 2.86 / 2.86 m | multi component | C3 면이 여러 component로 갈라짐 |

점은 독립 평가용 UAS cell, 빨간 면은 각 조건의 Roofer RoofSurface다. 현재 그림은
입력 점군 사진이 아니라 실제 LoD2 roof output을 같은 위치에서 겹쳐 보여준다.

## 무엇을 결론낼 수 있나

1. C1 산출물은 파일과 위상 자체는 유효하다.
2. 그러나 한 output이 51동을 공유하고 높이 오차도 커서, 현재 상태로는 건물별 상한
   baseline이나 threshold 기준으로 채택할 수 없다.
3. C2는 C1보다 더 많은 G4 후보를 만들었지만 건물별 component 분리가 여전히 거칠다.
4. C3는 학습 후 surface가 생겼지만 건물 association이 가장 큰 실패 지점이다.
5. 다음 우선순위는 loss 변경이 아니라 C1–C3에 공통인 건물별 Stage 3 분리 규칙과 G3
   matcher 검증이다.

공식 G3, G4, `PASS_usable`, `scientific_verdict`는 모두 `null`이다.

