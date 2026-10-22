# 일 9 3단계 — 새 지표 (PHD-MAIN-AXES71-v2) [이 발주에서 냄]

- 만든 때 2026-10-22 23:10:54 KST. 학습 대장 `AX/work/ledger9/ledger9.json`(표 일9_학습대장.md). 칸은 그 학습이 쓴 영역 파일로 정함. 3단계 조건은 조건마다 obs_masked 파일이 없어 보존 · 거름, 보존 · 문턱 안, 다듬기, 상속 · 결측(과 그 합)은 정의 없음. 결과 기준 값, 부록 값, 축 구간, 읽기는 같은 이름의 json.

## 3단계

**전체** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 42.3 · 268.4 | 42.3 · 268.4 |
| imgonly_s0 | B0a15 · LoD2 | 41.4 · 273.4 | 42.3 · 268.4 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 43.1 · 266.0 | 42.3 · 268.4 |
| prop_LoD2_s0 | B0a9 · LoD2 | 39.7 · 286.8 | 39.7 · 286.8 |
| imgonly_s0 | B0a9 · LoD2 | 36.3 · 307.4 | 39.7 · 286.8 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 43.5 · 268.6 | 39.7 · 286.8 |
| prop_LoD2_s0 | B0a3 · LoD2 | 29.9 · 139.0 | 29.9 · 139.0 |
| imgonly_s0 | B0a3 · LoD2 | 17.8 · 161.6 | 29.9 · 139.0 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 21.1 · 336.1 | 29.9 · 139.0 |
| prop_LoD2_s1 | B0a3 · LoD2 | 29.8 · 143.0 | 29.9 · 139.0 |
| imgonly_s1 | B0a3 · LoD2 | 19.6 · 158.6 | 29.9 · 139.0 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 79.2 · 31.9 | 79.2 · 31.9 |
| imgonly_s0 | B0n13 · LoD2 | 62.4 · 102.5 | 79.2 · 31.9 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 82.6 · 30.2 | 79.2 · 31.9 |
| prop_LoD2_s0 | B0n8 · LoD2 | 84.6 · 25.4 | 84.6 · 25.4 |
| imgonly_s0 | B0n8 · LoD2 | 56.2 · 60.4 | 84.6 · 25.4 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 83.9 · 25.2 | 84.6 · 25.4 |
| prop_LoD2_s0 | B0n2 · LoD2 | 48.6 · 147.8 | 48.6 · 147.8 |
| imgonly_s0 | B0n2 · LoD2 | 19.9 · 393.6 | 48.6 · 147.8 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 34.5 · 106.7 | 48.6 · 147.8 |

**다듬기** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

**보정 · 1~4τ** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 98.3 · 11.8 | 98.3 · 11.8 |
| imgonly_s0 | B0a15 · LoD2 | 98.3 · 11.5 | 98.3 · 11.8 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 83.5 · 23.0 | 98.3 · 11.8 |
| prop_LoD2_s0 | B0a9 · LoD2 | 98.1 · 12.0 | 98.1 · 12.0 |
| imgonly_s0 | B0a9 · LoD2 | 98.2 · 11.8 | 98.1 · 12.0 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 87.7 · 23.3 | 98.1 · 12.0 |
| prop_LoD2_s0 | B0a3 · LoD2 | 92.7 · 19.6* | 92.7 · 19.6* |
| imgonly_s0 | B0a3 · LoD2 | 92.8 · 18.3* | 92.7 · 19.6* |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 70.2 · 25.4* | 92.7 · 19.6* |
| prop_LoD2_s1 | B0a3 · LoD2 | 92.9 · 18.7* | 92.7 · 19.6* |
| imgonly_s1 | B0a3 · LoD2 | 94.6 · 16.1* | 92.7 · 19.6* |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 95.5 · 11.8* | 95.5 · 11.8* |
| imgonly_s0 | B0n13 · LoD2 | 95.8 · 10.5* | 95.5 · 11.8* |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 88.6 · 15.7* | 95.5 · 11.8* |
| prop_LoD2_s0 | B0n8 · LoD2 | 96.2 · 8.0* | 96.2 · 8.0* |
| imgonly_s0 | B0n8 · LoD2 | 93.9 · 7.9* | 96.2 · 8.0* |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 74.9 · 15.5* | 96.2 · 8.0* |
| prop_LoD2_s0 | B0n2 · LoD2 | 88.0 · 15.8* | 88.0 · 15.8* |
| imgonly_s0 | B0n2 · LoD2 | 76.1 · 24.3* | 88.0 · 15.8* |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 69.0 · 21.5* | 88.0 · 15.8* |

**보정 · 4τ 넘음** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 100.0 · 3.6* | 100.0 · 3.6* |
| imgonly_s0 | B0a15 · LoD2 | 100.0 · 3.7* | 100.0 · 3.6* |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 100.0 · 4.4* | 100.0 · 3.6* |
| prop_LoD2_s0 | B0a9 · LoD2 | 100.0 · 3.6* | 100.0 · 3.6* |
| imgonly_s0 | B0a9 · LoD2 | 99.9 · 3.7* | 100.0 · 3.6* |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 100.0 · 6.1* | 100.0 · 3.6* |
| prop_LoD2_s0 | B0a3 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0a3 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 표본 부족 | 표본 부족 |
| prop_LoD2_s1 | B0a3 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s1 | B0a3 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 93.1 · 9.6* | 93.1 · 9.6* |
| imgonly_s0 | B0n13 · LoD2 | 90.8 · 10.1* | 93.1 · 9.6* |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 64.9 · 24.0* | 93.1 · 9.6* |
| prop_LoD2_s0 | B0n8 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0n8 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 표본 부족 | 표본 부족 |
| prop_LoD2_s0 | B0n2 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0n2 · LoD2 | 표본 부족 | 표본 부족 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 표본 부족 | 표본 부족 |

**보존 · 거름** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

**보존 · 문턱 안** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

**한계** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 74.2 · 16.9 | 74.2 · 16.9 |
| imgonly_s0 | B0a15 · LoD2 | 69.2 · 22.0 | 74.2 · 16.9 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 88.9 · 13.9 | 74.2 · 16.9 |
| prop_LoD2_s0 | B0a9 · LoD2 | 72.2 · 17.6* | 72.2 · 17.6* |
| imgonly_s0 | B0a9 · LoD2 | 61.2 · 26.4* | 72.2 · 17.6* |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 88.6 · 12.6* | 72.2 · 17.6* |
| prop_LoD2_s0 | B0a3 · LoD2 | 84.6 · 19.3 | 84.6 · 19.3 |
| imgonly_s0 | B0a3 · LoD2 | 62.1 · 49.8 | 84.6 · 19.3 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 75.1 · 24.5 | 84.6 · 19.3 |
| prop_LoD2_s1 | B0a3 · LoD2 | 83.3 · 20.0 | 84.6 · 19.3 |
| imgonly_s1 | B0a3 · LoD2 | 64.4 · 58.2 | 84.6 · 19.3 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 61.9 · 43.4 | 61.9 · 43.4 |
| imgonly_s0 | B0n13 · LoD2 | 50.7 · 97.5 | 61.9 · 43.4 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 79.8 · 25.8 | 61.9 · 43.4 |
| prop_LoD2_s0 | B0n8 · LoD2 | 79.0 · 17.6* | 79.0 · 17.6* |
| imgonly_s0 | B0n8 · LoD2 | 41.6 · 62.9* | 79.0 · 17.6* |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 86.6 · 19.0* | 79.0 · 17.6* |
| prop_LoD2_s0 | B0n2 · LoD2 | 28.5 · 83.9 | 28.5 · 83.9 |
| imgonly_s0 | B0n2 · LoD2 | 10.8 · 232.2 | 28.5 · 83.9 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 77.1 · 24.9 | 28.5 · 83.9 |

**이중 오류** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 70.8 · 29.2* | 70.8 · 29.2* |
| imgonly_s0 | B0a15 · LoD2 | 68.1 · 30.1* | 70.8 · 29.2* |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 54.7 · 39.5* | 70.8 · 29.2* |
| prop_LoD2_s0 | B0a9 · LoD2 | 78.3 · 25.0* | 78.3 · 25.0* |
| imgonly_s0 | B0a9 · LoD2 | 77.2 · 25.1* | 78.3 · 25.0* |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 58.6 · 39.2* | 78.3 · 25.0* |
| prop_LoD2_s0 | B0a3 · LoD2 | 64.0 · 33.9* | 64.0 · 33.9* |
| imgonly_s0 | B0a3 · LoD2 | 64.2 · 37.4* | 64.0 · 33.9* |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 76.4 · 23.5* | 64.0 · 33.9* |
| prop_LoD2_s1 | B0a3 · LoD2 | 62.8 · 33.8* | 64.0 · 33.9* |
| imgonly_s1 | B0a3 · LoD2 | 64.1 · 36.8* | 64.0 · 33.9* |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 37.0 · 68.5* | 37.0 · 68.5* |
| imgonly_s0 | B0n13 · LoD2 | 43.9 · 93.7* | 37.0 · 68.5* |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 45.8 · 54.4* | 37.0 · 68.5* |
| prop_LoD2_s0 | B0n8 · LoD2 | 34.4 · 40.4* | 34.4 · 40.4* |
| imgonly_s0 | B0n8 · LoD2 | 43.4 · 46.4* | 34.4 · 40.4* |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 71.1 · 34.9* | 34.4 · 40.4* |
| prop_LoD2_s0 | B0n2 · LoD2 | 23.9 · 72.2* | 23.9 · 72.2* |
| imgonly_s0 | B0n2 · LoD2 | 15.8 · 299.6* | 23.9 · 72.2* |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 52.6 · 39.3* | 23.9 · 72.2* |

**상속 · 결측** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

**결측 · 사전 정보 틀림** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 66.6 · 25.5* | 66.6 · 25.5* |
| imgonly_s0 | B0a15 · LoD2 | 72.0 · 26.5* | 66.6 · 25.5* |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 71.2 · 22.8* | 66.6 · 25.5* |
| prop_LoD2_s0 | B0a9 · LoD2 | 67.1 · 23.0* | 67.1 · 23.0* |
| imgonly_s0 | B0a9 · LoD2 | 60.4 · 100.9* | 67.1 · 23.0* |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 70.0 · 26.7* | 67.1 · 23.0* |
| prop_LoD2_s0 | B0a3 · LoD2 | 55.6 · 32.1 | 55.6 · 32.1 |
| imgonly_s0 | B0a3 · LoD2 | 45.7 · 48.2 | 55.6 · 32.1 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 65.2 · 31.2 | 55.6 · 32.1 |
| prop_LoD2_s1 | B0a3 · LoD2 | 57.4 · 30.5 | 55.6 · 32.1 |
| imgonly_s1 | B0a3 · LoD2 | 47.0 · 57.4 | 55.6 · 32.1 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 35.7 · 34.5 | 35.7 · 34.5 |
| imgonly_s0 | B0n13 · LoD2 | 41.3 · 92.4 | 35.7 · 34.5 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 53.3 · 36.3 | 35.7 · 34.5 |
| prop_LoD2_s0 | B0n8 · LoD2 | 29.4 · 40.8 | 29.4 · 40.8 |
| imgonly_s0 | B0n8 · LoD2 | 37.2 · 72.8 | 29.4 · 40.8 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 59.7 · 27.3 | 29.4 · 40.8 |
| prop_LoD2_s0 | B0n2 · LoD2 | 27.5 · 52.9 | 27.5 · 52.9 |
| imgonly_s0 | B0n2 · LoD2 | 9.5 · 429.1 | 27.5 · 52.9 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 44.9 · 48.6 | 27.5 · 52.9 |

**상속 · 비가시** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 91.2 · 17.7 | 91.2 · 17.7 |
| imgonly_s0 | B0a15 · LoD2 | 30.3 · 81.5 | 91.2 · 17.7 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 28.0 · 69.2 | 91.2 · 17.7 |
| prop_LoD2_s0 | B0a9 · LoD2 | 88.0 · 21.4 | 88.0 · 21.4 |
| imgonly_s0 | B0a9 · LoD2 | 28.1 · 96.3 | 88.0 · 21.4 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 25.4 · 73.9 | 88.0 · 21.4 |
| prop_LoD2_s0 | B0a3 · LoD2 | 66.9 · 36.8 | 66.9 · 36.8 |
| imgonly_s0 | B0a3 · LoD2 | 35.5 · 54.4 | 66.9 · 36.8 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 29.2 · 63.7 | 66.9 · 36.8 |
| prop_LoD2_s1 | B0a3 · LoD2 | 76.6 · 23.6 | 66.9 · 36.8 |
| imgonly_s1 | B0a3 · LoD2 | 33.3 · 57.8 | 66.9 · 36.8 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 94.8 · 22.7 | 94.8 · 22.7 |
| imgonly_s0 | B0n13 · LoD2 | 15.2 · 192.7 | 94.8 · 22.7 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 41.1 · 81.0 | 94.8 · 22.7 |
| prop_LoD2_s0 | B0n8 · LoD2 | 88.1 · 27.4 | 88.1 · 27.4 |
| imgonly_s0 | B0n8 · LoD2 | 18.7 · 176.6 | 88.1 · 27.4 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 44.0 · 71.8 | 88.1 · 27.4 |
| prop_LoD2_s0 | B0n2 · LoD2 | 93.9 · 15.9 | 93.9 · 15.9 |
| imgonly_s0 | B0n2 · LoD2 | 24.9 · 103.2 | 93.9 · 15.9 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 35.7 · 67.4 | 93.9 · 15.9 |

**비가시 · 사전 정보 틀림** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 63.8 · 32.4 | 63.8 · 32.4 |
| imgonly_s0 | B0a15 · LoD2 | 50.7 · 53.7 | 63.8 · 32.4 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 47.9 · 42.2 | 63.8 · 32.4 |
| prop_LoD2_s0 | B0a9 · LoD2 | 62.5 · 33.6 | 62.5 · 33.6 |
| imgonly_s0 | B0a9 · LoD2 | 53.3 · 74.1 | 62.5 · 33.6 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 48.0 · 47.6 | 62.5 · 33.6 |
| prop_LoD2_s0 | B0a3 · LoD2 | 39.9 · 45.6 | 39.9 · 45.6 |
| imgonly_s0 | B0a3 · LoD2 | 35.3 · 47.4 | 39.9 · 45.6 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 32.7 · 44.9 | 39.9 · 45.6 |
| prop_LoD2_s1 | B0a3 · LoD2 | 50.4 · 35.9 | 39.9 · 45.6 |
| imgonly_s1 | B0a3 · LoD2 | 34.0 · 49.6 | 39.9 · 45.6 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 56.0 · 49.8 | 56.0 · 49.8 |
| imgonly_s0 | B0n13 · LoD2 | 11.8 · 169.5 | 56.0 · 49.8 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 50.3 · 56.8 | 56.0 · 49.8 |
| prop_LoD2_s0 | B0n8 · LoD2 | 61.4 · 44.9 | 61.4 · 44.9 |
| imgonly_s0 | B0n8 · LoD2 | 12.8 · 236.2 | 61.4 · 44.9 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 53.0 · 53.3 | 61.4 · 44.9 |
| prop_LoD2_s0 | B0n2 · LoD2 | 43.6 · 44.9 | 43.6 · 44.9 |
| imgonly_s0 | B0n2 · LoD2 | 20.8 · 88.5 | 43.6 · 44.9 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 32.2 · 72.1 | 43.6 · 44.9 |

**참값 없음** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 25.1 · 611.9 | 25.1 · 611.9 |
| imgonly_s0 | B0a15 · LoD2 | 24.1 · 614.9 | 25.1 · 611.9 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 24.9 · 603.2 | 25.1 · 611.9 |
| prop_LoD2_s0 | B0a9 · LoD2 | 23.8 · 658.5 | 23.8 · 658.5 |
| imgonly_s0 | B0a9 · LoD2 | 17.6 · 706.7 | 23.8 · 658.5 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 23.6 · 611.1 | 23.8 · 658.5 |
| prop_LoD2_s0 | B0a3 · LoD2 | 23.7 · 249.6 | 23.7 · 249.6 |
| imgonly_s0 | B0a3 · LoD2 | 13.1 · 316.1 | 23.7 · 249.6 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 21.3 · 684.8 | 23.7 · 249.6 |
| prop_LoD2_s1 | B0a3 · LoD2 | 23.0 · 272.4 | 23.7 · 249.6 |
| imgonly_s1 | B0a3 · LoD2 | 14.0 · 320.3 | 23.7 · 249.6 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 65.8 · 100.0 | 65.8 · 100.0 |
| imgonly_s0 | B0n13 · LoD2 | 38.2 · 393.6 | 65.8 · 100.0 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 64.0 · 145.9 | 65.8 · 100.0 |
| prop_LoD2_s0 | B0n8 · LoD2 | 67.5 · 100.4 | 67.5 · 100.4 |
| imgonly_s0 | B0n8 · LoD2 | 43.9 · 144.0 | 67.5 · 100.4 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 64.1 · 140.7 | 67.5 · 100.4 |
| prop_LoD2_s0 | B0n2 · LoD2 | 42.1 · 342.3 | 42.1 · 342.3 |
| imgonly_s0 | B0n2 · LoD2 | 12.7 · 467.6 | 42.1 · 342.3 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 55.7 · 301.2 | 42.1 · 342.3 |

**보정 합** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 98.5 · 10.7 | 98.5 · 10.7 |
| imgonly_s0 | B0a15 · LoD2 | 98.6 · 10.6 | 98.5 · 10.7 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 85.6 · 20.7 | 98.5 · 10.7 |
| prop_LoD2_s0 | B0a9 · LoD2 | 98.4 · 11.0 | 98.4 · 11.0 |
| imgonly_s0 | B0a9 · LoD2 | 98.4 · 10.8 | 98.4 · 11.0 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 89.2 · 21.3 | 98.4 · 11.0 |
| prop_LoD2_s0 | B0a3 · LoD2 | 92.6 · 19.6* | 92.6 · 19.6* |
| imgonly_s0 | B0a3 · LoD2 | 92.7 · 18.3* | 92.6 · 19.6* |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 70.3 · 25.4* | 92.6 · 19.6* |
| prop_LoD2_s1 | B0a3 · LoD2 | 92.9 · 18.7* | 92.6 · 19.6* |
| imgonly_s1 | B0a3 · LoD2 | 94.6 · 16.1* | 92.6 · 19.6* |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 95.4 · 11.7* | 95.4 · 11.7* |
| imgonly_s0 | B0n13 · LoD2 | 95.6 · 10.5* | 95.4 · 11.7* |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 87.5 · 16.1* | 95.4 · 11.7* |
| prop_LoD2_s0 | B0n8 · LoD2 | 96.2 · 8.0* | 96.2 · 8.0* |
| imgonly_s0 | B0n8 · LoD2 | 94.0 · 7.9* | 96.2 · 8.0* |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 73.9 · 15.9* | 96.2 · 8.0* |
| prop_LoD2_s0 | B0n2 · LoD2 | 89.8 · 15.5* | 89.8 · 15.5* |
| imgonly_s0 | B0n2 · LoD2 | 79.5 · 21.6* | 89.8 · 15.5* |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 68.4 · 20.8* | 89.8 · 15.5* |

**보존 합** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

**상속 합** — 참값 기준 재현율 R(τ) (%) · 참값 기준 평균 거리 (cm)

| 학습 | 경우 | 이 학습 | 같은 경우 본 방법 (두 씨앗 평균) |
|---|---|---|---|
| prop_LoD2_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a15 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a15 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a9 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a9 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s1 | B0a3 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n13 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n13 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n8 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n8 · LoD2 | 정의 없음 | 정의 없음 |
| prop_LoD2_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |
| imgonly_s0 | B0n2 · 항공 LiDAR | 정의 없음 | 정의 없음 |
| trust_LoD2_fix1 | B0n2 · LoD2 | 정의 없음 | 정의 없음 |

