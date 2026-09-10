# P1 prior .0005 — 기존 수정의 유지와 새 손상의 부분 비교

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- main_v2; scientific_verdict: null
- 상태: `PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION`

P1 `.0005 × native/release`의 train/render/metrics는 2026-09-11 08:04:59 KST에 모두 PASS했다. 전체 모델 10/18개 완료 시점의 부분 평가다. **이 평가 attempt는 P1의 .005/.0005 네 조건만 선택했다.** P1 계수0 두 조건은 미완료이며, 다른 지역은 이 attempt의 범위 밖이다. [동결 명세](MAIN_SPEC_ko_v2.md)와 [P1 .005 보고](INTERIM_P1_D005_ko_v2.md)를 함께 읽는다.

## 형상·외관의 대응 비교

Raw TSDF512, 거리 `<.5m`, 같은 참조246,125점이다. 정확도는 예측 표본→관측 UAS, 완전성은 동일 UAS점→삼각형 표면으로 분모가 다르다.

| P1 .0005 | G→LC 정확도 (%) | G→LC 완전성 (%) | G→LC F1 | G 대비 수정 / 손상 참조점 |
|---|---:|---:|---:|---:|
| native | 42.1220→37.4029 | 33.9413→35.1846 | .375917→.362598 | 25,705 / 22,645 |
| release | 40.1858→40.8326 | 36.6562→35.6490 | .383399→.380651 | 27,217 / 29,696 |

Native는 완전성+1.2433%p와 정확도−4.7191%p가 함께 나타났고, release는 정확도+.6467%p와 완전성−1.0072%p가 함께 나타났다. F1은 각각−.013319/−.002748다. 같은 post512의 F1도 G.360673/.371943→LC.346550/.367859로 낮아졌다. Raw/post의 모든 .1/.2/.25/.5/1/2m 결과는 봉인 CSV에 유지한다. 예측 표본 수는 G172,594/206,436→LC192,707/182,641이다.

기존 G.005 native/release의 F1 .499/.519 및 완전성60.62/62.82%가 이 약한 prior 조건보다 높다. Anchor도 정확도61.64%, 완전성66.73%, F1.641이다. 모든 기존 대조와 Anchor를 남기며, 약한 대조 대비 일부 상승을 최선의 기존 방법 대비 개선으로 바꾸어 말하지 않는다.

| 같은15카메라 평균 변화 | native | release |
|---|---:|---:|
| 전체 PSNR (dB) | +.003054 | −.021504 |
| 전체 SSIM | −.001180 | −.000800 |
| 전체 LPIPS (양수가 악화) | +.001039 | −.000673 |
| 고정 ROI PSNR (dB) | −.133806 | −.075485 |

각 카메라 dB의 산술 평균이며 pooled pixel PSNR은 아니다. ROI PSNR 상승은5/15,6/15개이고 전체 PSNR 상승은8/15,9/15개다. ROI SSIM/LPIPS는 미측정이다. 매우 작은 평균 차이에 대해 반복 재현성 또는 의미 있는 우열을 판정하지 않는다.

## 같은 참조점·cell의 수정과 손상

| P1 .0005 | native | release |
|---|---:|---:|
| G의 Anchor 대비 수정 / 손상 | 32,317 / 113,010 | 32,847 / 106,858 |
| LC의 Anchor 대비 수정 / 손상 | 31,233 / 108,866 | 31,965 / 108,455 |
| G 수정 중 LC가 유지 / 소실 | 24,392 / 7,925 | 24,681 / 8,166 |
| G 손상을 LC가 회복 | 18,864 | 19,933 |
| LC 추가 손상 | 14,720 | 21,530 |
| G→LC 수정·손상 공존 cell | 401 / 3,600 | 383 / 3,600 |

0.5m XY 격자3,600개 모두 참조 지지가 있다. Native의 순 완전성 상승에도 기존 수정7,925개가 소실됐다. Release도 기존 손상19,933개를 회복하면서 추가 손상21,530개가 발생했다. 이 상반된 변화를 상쇄하지 않는다. 점/cell 수는 면적·시간 변화의 진실값이나 같은 Gaussian·연속 표면의 직접 대응이 아니다.

## 실제 사진·단면 검토

결과 독립 선택 사진은 `DJI_20241217084551_0099_D.JPG`, image_id90, camera_id1, evaluation_index0이다. 고정 bbox `[567,108,1220,760]`은653×652=425,756pixel이다. 원사진·Anchor·G·LC 네 패널과 crop, 선택 PSNR 및 단면 표본 수를 독립 검사해 모두 PASS했다.

선택 ROI PSNR은 native G21.64233→LC21.34692(−.29541dB), release G21.51990→LC21.27617(−.24373dB)다. 선택 전체 PSNR은−.47565/+.00364dB다. 실제 그림에서 G와 LC 모두 Anchor의 크게 번진 왼쪽 입면과 아래 곡선 지붕을 더 구별되게 만든다. 하지만 .0005의 G도 바닥 타일·작은 물체를 선명하게 복원하지 못한다. Native LC에서는 G의 노란 물체가 더 작은 밝은 덩어리로 바뀌고, release LC에서는 G에 남던 노란 형태가 거의 사라진다. 일부 바닥 선이 더 구별되는 변화와 물체 손실을 함께 기록한다.

고정 X=−8m/Y=−6m, 폭.5m 점 띠를 열어 확인했다. X 띠에서 G와 LC 모두 Anchor의 높은 평탄층 일부를 관측 UAS 높이 쪽으로 낮춘다. Native LC의 왼쪽 일부는 G보다 참조에 가깝지만, 두 LC 조건의 오른쪽에는 G보다 높은 표면이 더 생긴다. Y 띠에서 release G가 유지하던 왼쪽 높은 참조 군집 부근의 예측이 LC에서 줄고 더 낮아진다. Native도 일부 중간층 위치가 바뀌고, 오른쪽 낮은 표면은 G와 대체로 비슷하다. 참조 부재 구간의 정오를 인증하지 않는다.

X 띠의 참조2,088점에 대해 G 예측2,629/2,184→LC3,217/2,771점이다. Y 띠의 참조6,064점에 대해 G3,150/4,295→LC3,254/3,310점이다. 이는 mesh-plane 교선이 아니다. 새 .0005 full/ROI/단면6개, 지도2개, 부분 행렬2개를 실제 열어 검토했다. 행렬의4/18개 표시는 이 attempt의 선택 범위이며 전체 큐의 완료 수10/18과 다르다.

## Source 층과 loss/controller

Prior near는 참조→prior 삼각형 거리 `<.5m`, image-target near는 strict DA3 median world-Z 오차 절댓값 `≤.5m`인 평가 proxy다. Source 정오·사진 가시성·시간 변화의 진실값이 아니다.

| 평가 층 | 참조점 수 | native 수정 / 손상 | release 수정 / 손상 |
|---|---:|---:|---:|
| prior near / image-target near | 1,532 | 67 / 64 | 0 / 146 |
| prior near / image-target far | 51,372 | 4,099 / 4,772 | 10,339 / 5,411 |
| prior far / image-target near | 478 | 0 / 26 | 0 / 20 |
| 둘 다 far | 44,505 | 4,343 / 3,710 | 4,170 / 3,097 |
| strict 대응 없음 | 148,238 | 17,196 / 14,073 | 12,708 / 21,022 |

Strict 지지97,887개 밖은 source 층으로 억지 분류하지 않는다. Native의 전체 수정 초과는 strict 밖에서도 나타나며, release는 strict 안에서 수정14,509/손상8,674개지만 밖에서는 손상이 더 많다. 이를 source 신뢰 판단의 성공으로 일반화하지 않는다.

8100–30000의 완결 로그는조건마다220표본이고 G와카메라가220/220개 일치했다. 기록된 lambdaV 불일치는 native0개/release203개다. Native의 평균은G/LC모두.05, release는G.0476932→LC.05다. 평균 prior/visual 배율은.148111/.976209이며 이를 맞춘 전역 대조를 실행하지 않았다.

Raw prior loss 평균은G35.6446/35.6523→LC35.8628/35.9243으로 증가했다. Raw visual loss는native8.86972→8.71393으로 감소하고 release8.52567→8.81462로 증가했다. 이 원 목적의 표본 잔차를 형상 정오나 공간 배분만의 인과로 해석하지 않는다. 표본 lambdaV 일치도 controller replay를 뜻하지 않는다.

## 계보·자원·기여 범위

외부 task root는 [resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml)의 `payload_host_root`다.

| 산출물 | task root 아래 경로 |
|---|---|
| P1 네 조건 평가 | `main_v2/evaluation/attempt_20260910T230615_457896Z/` |
| 전체 G/Anchor·LC와 모든 raw/post 문턱 | `main_v2/summary/attempt_20260910T231138_925434Z/` |
| 사진·단면 | `main_v2/figures/attempt_20260910T231138_562974Z/` |
| 같은 cell 지도 | `main_v2/maps/attempt_20260910T230615_457896Z/` |
| Source 층 | `main_v2/strata_diagnostic/attempt_20260910T231137_874559507Z/` |
| 행렬 그림 | `main_v2/matrix_figures/attempt_20260910T231217_728827Z/` |
| 완결10개/진행2개 trace snapshot | `main_v2/trace_monitor/attempt_20260910T231137Z_y9S6Ms_trace_v2/analysis/` |
| 네 원본 패널·PSNR·단면 QA | `main_v2/figures_review/attempt_20260910T231217_309807Z/receipt.json` |
| 원 거리→모든 cell 독립 QA | `main_v2/maps_review/attempt_20260910T231217_302698Z/receipt.json` |

평가 receipt SHA256은 `c9fbc91a8d9f8bdb6eef3713af97dd9834b3a7f05a1183397c8e066990e79cd0`다. 독립 사진·지도 QA는4개 모두 PASS했다. 학습 driver wall은6994.688/5807.409초, child peak RSS는24,218,574,848/22,405,742,592bytes다. 최종 Gaussian은6,342,350/5,788,096개다. CPU 평가 전 MemAvailable=63,973,096kB를기록했으며 P3 학습과겹친 비독점 비용이다. 기존 G와 checkpoint·렌더·타이머 범위가 달라 순수 방법 비용 이득으로 읽지 않는다.

**문제 차별성**은 기존 형상의 재사용 가능한 부분과 수정 필요 부분의 공존이다. **원인 설명**은 관측된 입력 불일치·loss/controller 반응·대응 부위 변화로 제한한다. **방법 신규성**과 국소 배분의 고유 우위는 이 결과로 입증되지 않는다. **검증 기여**는 G의 기존 성공, LC의 추가 수정과 기존 수정 소실을 같은 원본 참조점·카메라·단면에서 추적한 것이다. 평균 배율 전역 대조·controller replay·반복이 없어 공간 배분 고유 효과, DA3 단독 인과, 작은 차이 재현성·일반화를 확정하지 않는다. GT는 평가 전용이며 scientific_verdict는 null이다. 남은8개 모델과 전체 평가를 동결 명세대로 이어간다.
