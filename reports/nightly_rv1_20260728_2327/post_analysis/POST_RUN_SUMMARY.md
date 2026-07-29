# TUM2TWIN baseline post-run analysis — `20260728_2327`

> R_v1 is a relative, provisional stratification for experiment selection. It is not a final scientific readiness or quality certification.

## Technical summary

- **실행 무결성은 신뢰 가능하다.** `DONE`, 178/178 처리, 실행 실패 0, building ID 중복 0이며 batch 전후 source size/mtime snapshot 8건이 현재도 모두 일치한다.
- **metric 해석은 caveat가 필요하다.** 실제 계산은 explicit mesh-to-surface가 아니라 0.1 m voxelized class-6 point set 사이의 양방향 nearest-neighbour 거리다. 따라서 본 결과명은 `surface_proxy_R_v1`이다.
- **재분류 valid population은 135/178이다.** 43건(24.2%)은 DIM class-6 점이 0개라 completeness/reliability 핵심값이 함께 NaN이며 RX로 유지했다.
- **stable 분포는 R0=33, R1=14, R2=13, R3=25, RX=93이다.** q40/q50/q60 축 임계값은 `q40: C=0.397, Rel=0.387; q50: C=0.485, Rel=0.481; q60: C=0.596, Rel=0.572`이다.
- **공유 판단:** `Share with caveats`. 후보 선택과 T1 설계에는 사용할 수 있으나 mesh 품질 인증이나 인과적 prior 효과 주장에는 사용할 수 없다.

## 가장 중요한 발견 5개

1. **결측은 무작위가 아니다.** surface metric 누락 43건은 모두 reconstruction class-6 count가 0이며 LoD2 process-valid도 아니다. metric만 다시 계산해도 복구되지 않는다.
2. **completeness와 reliability는 같은 축이 아니다.** valid 135건의 Spearman ρ=0.331, Pearson r=0.320로 약한 양의 관계만 보여 R1/R2 분리가 실제 정보를 추가한다.
3. **surface proxy는 LoD2와 관련되지만 결정적이지 않다.** surface score와 roof-plane F1의 Spearman ρ=0.455, RMSZ와는 ρ=-0.683이다(n=114).
4. **upstream이 좋아도 LoD2 shell이 실패한 예외가 있다.** q50 R0이면서 LoD2 process-valid가 아닌 건물은 `DEBY_LOD2_4907520`, `DEBY_LOD2_60042`이다.
5. **upstream이 낮아도 LoD2가 강한 예외가 있다.** q50 R3 중 roof-plane F1≥0.545, RMSZ≤0.640를 동시에 만족한 건물은 `DEBY_LOD2_42364667`, `DEBY_LOD2_4907020`이다. 이는 상관을 인과 또는 필연으로 읽으면 안 된다는 반례다.

## R 분포, 면적과 view 자료

| Group | n | area median [p25, p75] m² | existing view coverage | existing view median |
|---|---:|---:|---:|---:|
| R0 | 33 | 219.4 [145.5, 300.7] | 1/33 | 30.0 |
| R1 | 14 | 122.5 [40.5, 160.9] | 3/14 | 30.0 |
| R2 | 13 | 875.8 [373.0, 1371.8] | 0/13 | unknown |
| R3 | 25 | 199.7 [117.0, 264.3] | 1/25 | 30.0 |
| RX | 93 | 165.1 [55.5, 320.9] | 4/93 | 28.5 |

기존 materialized `views.csv`는 9/178건에만 존재한다. 따라서 population-wide view 분포는 확인되지 않았고 그룹별 view 중앙값은 관측 가능한 subset만 표시했다. 선정 후보 5건은 기존 selector로 10-view minimum을 확인했으며 모두 20–30개의 실제 image inventory를 가진다.

## 선정된 LiDAR oracle 후보

| R | Building | C | Reliability | Area m² | Views | LiDAR class-6 | Cost proxy |
|---|---|---:|---:|---:|---:|---:|---|
| R0 | `DEBY_LOD2_4908023` | 0.795 | 0.619 | 21.9 | 30 | 448 | low (0.51×) |
| R1 | `DEBY_LOD2_4908050` | 0.216 | 0.698 | 131.7 | 30 | 1403 | medium (1.58×) |
| R1 | `DEBY_LOD2_4908176` | 0.362 | 0.802 | 35.6 | 30 | 660 | low (0.74×) |
| R2 | `DEBY_LOD2_4906973` | 0.787 | 0.257 | 55.3 | 30 | 887 | low (1.00×) |
| R2 | `DEBY_LOD2_4906985` | 0.765 | 0.351 | 875.8 | 30 | 9876 | high (11.13×) |

선정 규칙은 stable label, 필수 입력 존재, 그룹 중심거리 최소화, 기존 materialized local scene 우선, 두 번째 표본의 면적 반대편 선택 순이다. GPU-hour 절대치는 비교 가능한 5-arm timing이 없어 `unknown`이며, 표의 비용은 view 수×LiDAR class-6 점수의 상대 proxy다.

## qualitative panel sanity check

qualitative panel은 R 정답으로 사용하지 않았다. 9건 panel은 좌표계 전체 이동이 없음을 확인하며 metric CRS audit와 일치한다. 세부적으로 `DEBY_LOD2_60097`의 좁은 strip support는 R1의 낮은 completeness/높은 reliability와, `DEBY_LOD2_4907207`의 복합·불안정 support는 R3와, `DEBY_LOD2_4959753`의 수목·인접 지붕 방향 확산은 낮은 reliability와 방향상 부합한다. `DEBY_LOD2_4908353`의 REVIEW_NEEDED는 occlusion 미처리 표시 문제라 자동 R0와 직접 비교할 수 없다. 정량 agreement rate는 panel이 quality label을 제공하지 않으므로 계산하지 않았다.

## 확인되지 않은 주장

- explicit mesh surface의 completeness/reliability 또는 watertightness
- `surface_thickness_p90_m`이 물리적 표면 두께라는 주장
- 178건 전체의 per-building usable view 수
- R group이 LiDAR oracle prior의 개선량을 인과적으로 예측한다는 주장
- 후보별 절대 GPU-hour
- qualitative PASS/REVIEW_NEEDED가 자동 R label의 정답이라는 주장

## 재현

`jointbuildgs:dev` 컨테이너의 repository root에서 다음을 실행한다. 이 명령은 기존 metric과 입력을 읽고 `post_analysis/`만 atomic write하며 geometry metric이나 GS 학습을 실행하지 않는다.

```bash
python scripts/analyze_tum2twin_surface_proxy_rv1.py   --run-root reports/nightly_rv1_20260728_2327   --output-dir reports/nightly_rv1_20260728_2327/post_analysis
python tests/test_tum2twin_surface_proxy_rv1_analysis.py
```

## 다음 단계 추천

`oracle_candidates.yaml`의 5건에 대해 먼저 local-scene materialization과 B0 600-iteration cost smoke만 수행해 absolute GPU budget을 측정하고, 이후 동일 image/camera·appearance·iteration·seed·mesh/Roofer 조건으로 B0/P1/P2/P3를 실행한다. P4는 coverage-aware densification의 수식과 threshold가 아직 repository lock으로 확인되지 않았으므로 이를 preregister하기 전에는 실행하지 않는다. 실행 지시는 `next_oracle_prompt.md`에 작성했으며 이번 분석에서는 학습을 시작하지 않았다.
