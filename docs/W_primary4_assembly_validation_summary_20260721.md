# 주 명단 4동 수평면 합성 점군 조립 측정

- 범위: 4907199 재현 1동 + 4908049·104586480·4908048 신규 3동.
- 입력: 0.5 m 격자, 상수 높이, class 6 지붕 + B-1 동일 지면 공식 class 2.
- 조립: 잠금 Roofer 표준 설정. 참조 LoD2는 입력 고정 후 채점에만 사용.
- 학습 0, 신규 추론 0, 이미지 입력 0, GPU 0.

## 측정표

| 건물 | 행 | rf_extrusion_mode | has_lod22 | 부호 중앙오차 m | 지붕 RMS m | 면수비 | 완전율 | val3dity | 눈금 b |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 4907199 | reproduction | `lod11_fallback` | false | -0.014 | 0.014 | 1.000 | 1.0000 | true | false |
| 4908049 | new_target | `lod11_fallback` | false | 0.022 | 0.129 | 1.000 | 1.0000 | true | false |
| 104586480 | new_target | `lod11_fallback` | false | -2.942 | 2.942 | 1.000 | 1.0000 | true | false |
| 4908048 | new_target | `lod11_fallback` | false | 0.096 | 0.270 | 0.500 | 1.0000 | true | false |

눈금 b: `has_lod22 == true AND abs(signed_delta_z_median_m) <= 1.0 m`.

## 4907199 재현 행

- B-1 조립 중앙오차 기대값: -0.014000000000 m.
- 이번 중앙오차: -0.014000000000 m.
- 전 재현 검사 통과: `true`.

## 입력·범위 기록

- 네 z 값은 `boundary_map_v4_1_ladder.csv`의 잠금 문자열과 일치한다.
- 4908048은 참조 분류 `multiple horizontal`; 입력은 잠금 지시에 따라 MAD 0.039240 m의 단일 상수 높이로 작성했다.
- 지면 공식은 B-1 C001 clip의 원천인 전역 sparse/dense seed PLY에 같은 외곽·격자·q10·하위 모드 파라미터를 적용했다.
- 이 문서는 4/4 문장 또는 K2 확정·후퇴를 기록하지 않는다.
