# P2 C1/C2/C3 development 단계별 평가 결과 v1

## 한 줄 결론

`04_RESULT_AND_ACCEPTANCE_CONTRACT_v0.md`가 요구한 development 51동의 C1/C2/C3
단계별 표와 실제 모델 비교판을 생성했다. 현재 결과는 **C2는 모델 생성·형식·위상까지
대부분 통과하지만 높이 정확도가 낮고, C3는 건물별 분리와 Roofer 입력 연결에서 크게
무너진다**는 것을 보여준다. 공식 최종 성공 수는 G3 matcher와 G4 threshold가 아직
동결되지 않아 `null`이다.

## 모집단과 이번 분모

- 199동: 선택 AOI의 전체 `U_target`.
- 72동: 독립 UAS 지붕 관측과 pilot 입력 지지가 있는 진단 후보.
- 51동: 72동 중 이번에 허가된 development split. C1/C2/C3 모두 같은 51동을 비교했다.
- validation 11동과 held-out 10동은 열지 않았다.

따라서 아래 수치는 199동 전체 성공률이나 confirmatory 결론이 아니라, 동일 51동에서
파이프라인이 어디서 실패하는지를 보는 development 결과다.

## 단계별 정량 결과

| 조건 | 분모 | G0 모델 생성 | G1 schema/semantic | G2 위상 유효 | G3 지붕구조 후보 | G4 높이·거리 후보 | 최종 후보 |
|---|---:|---:|---:|---:|---:|---:|---:|
| C1 current UAS LiDAR | 51 | 51 | 51 | 범위 밖 | 범위 밖 | 범위 밖 | 공식 `null` |
| C2 current-image MVS | 51 | 50 | 50 | 50 | 0 | 6 | 0 |
| C3 image-only GS | 51 | 35* | 37* | 19 | 0 | 1 | 0 |

`*` C3의 35/37은 평가용 component 관점의 가용 수다. 엄격한 건물↔component
1:1 연결이 된 건물은 6동뿐이며, 그 안에서는 G0 5/6, G1 6/6이다. 나머지 45동은
shared/multiple/unassociated component라 공식 건물 단위 G0/G1을 `null`로 격리했다.

C3 연결 상태는 `UNASSOCIATED 14`, `SHARED_COMPONENT 13`,
`SHARED_AND_MULTI_COMPONENT 12`, `MULTI_COMPONENT 6`, 정확한 1:1 연결 `6`이다.
즉 현재 C3의 가장 큰 병목은 GS 학습 자체의 유무보다 **전체 AOI surface를 건물별
Roofer 입력으로 안정적으로 나누는 단계**다.

## 결과의 의미

- C2는 51동 중 50동에서 CityJSON 생성과 위상 검사를 통과했다. 그러나 후보 높이·거리
  기준은 6동만 통과했다. 형식은 잘 만들어지지만 지붕 높이 정확도는 부족하다는 뜻이다.
- C3는 평가 가능한 component가 있는 경우에도 한 component가 여러 건물을 덮거나 한
  건물이 여러 component와 겹치는 일이 많다. 후보 높이·거리 기준 통과는 1동이다.
- G3 후보는 C2/C3 모두 0이다. 현 matcher가 Roofer의 큰/concave roof surface와 UAS의
  작은 plane patch를 제대로 대응시키지 못해 accepted plane pair가 0이 된 결과다.
  그러므로 이것을 곧바로 “지붕구조가 전부 실패”라는 과학 결론으로 쓰지 않는다.
- 후보 최종 통과 0은 현 후보식의 교집합 결과다. 공식 `PASS_usable`은 matcher 검증과
  G4 임계값 동결 전까지 전 행 `null`이다.

## 정성 비교판에서 볼 것

점은 독립 UAS reference, 빨간 면은 각 조건의 Roofer RoofSurface다. 위쪽은 평면,
아래쪽은 3D 보기다. 5개 사전선정 사례에서 C1/C2의 빨간 면이 한 건물보다 훨씬 크게
이어지거나, C3가 부채꼴 다중 면·미연결·다중 component가 되는 현상을 직접 확인할 수
있다. 이는 단순 수치 문제가 아니라 현재 Roofer read-out과 건물 association이 연구
의도에 맞는 건물별 모델을 만들지 못하고 있다는 실물 증거다.

## 재실행 방지와 격리

- 기존 C3 G2 18건을 재사용했고 G2 실행은 0회였다.
- reconstruction 0회, Roofer 0회, 대용량 R1/Images.zip/OPF.zip hash 0회다.
- validation/held-out/C4/C5/Fusion W1/R_ext 접근은 0회다.
- `scientific_verdict: null`.

## 산출물

- 외부 namespace: `artifact://JointBuildGS/phase-payloads/p2/c3_development_evaluation_candidate_v1/P2-C3-DEVELOPMENT-EVALUATION-CANDIDATE-v1/`
- C3 51행: `results/c3_development_diagnostics_v1.jsonl`
- C1/C2/C3 153행: `results/three_condition_development_diagnostics_v1.jsonl`
- 조건별 요약: `results/three_condition_summary_v1.jsonl`
- 비교판 목록 및 hash: `results/qualitative_manifest_v1.jsonl`
- 실제 비교판 5개: `qualitative/*_C1_C2_C3_roof_comparison_v1.png`

