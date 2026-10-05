# P2 prior .0005 — 기존 전역 대조와 국소 가중의 부분 비교

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- main_v2; scientific_verdict: null
- 상태: `PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION`

P2 `.0005 × native/release`의 모델 단계는2026-09-11 06:01 KST에 모두 PASS했다. 전체 모델은8/18개 완료 상태에서 이 부분 평가를 수행했다. **이 평가 attempt의 선택 범위는 P2의 `.005/.0005` 네 조건**이며, 전체18개 평가가 아니다. P2 계수0 두 조건은 아직 미완료이고 P1/P3는 이 attempt에 포함하지 않았다. [명세](MAIN_SPEC_ko_v2.md), [첫 .005 P2 보고](INTERIM_P2_D005_ko_v2.md), [첫6개 보고](INTERIM_D005_ALL_REGIONS_ko_v2.md)를 유지한다.

## 대응 G 대비 형상과 외관

Raw TSDF512, 거리 `<.5m`, 고정 참조572,214점이다. 정확도는 예측 표본→관측 UAS, 완전성은 동일 UAS점→삼각형 표면이며 분모가 다르다.

| P2 .0005 | G→LC 정확도 (%) | G→LC 완전성 (%) | G→LC F1 | 수정 / 손상 참조점 |
|---|---:|---:|---:|---:|
| native | 58.0914→55.1372 | 38.0417→35.2019 | .459758→.429699 | 14,822 / 31,072 |
| release | 57.9916→54.7018 | 37.6018→35.5947 | .456222→.431267 | 16,374 / 27,859 |

두 조건 모두 정확도·완전성·F1이 낮아졌다. Δ정확도는−2.9543/−3.2899%p, Δ완전성은−2.8398/−2.0071%p, ΔF1은−.030058/−.024955다. 같은 후처리에서도 F1은 G.458358/.455238→LC.429010/.431250로 낮아졌다. Raw/post의.1/.2/.25/.5/1/2m 전체 문턱 결과는 봉인 요약 CSV에 있다.

기존 P2 G.005 native는 정확도54.90%, 완전성52.09%, F1.535이고 G0 native는59.51%,39.09%,.472다. 기존 방법의 이 성능을 함께 유지하며 약한 비교 하나를 골라 LC의 기여로 바꾸어 말하지 않는다. LC.005의 전체 PSNR 평균 상승과 달리 LC.0005는 대응 G 대비 외관 평균도 악화했다.

| 같은9개 카메라 평균 변화 | native | release |
|---|---:|---:|
| 전체 PSNR (dB) | −.251626 | −.090938 |
| 전체 SSIM | −.003426 | −.007999 |
| 전체 LPIPS (양수가 악화) | +.000550 | +.004658 |
| 고정 ROI PSNR (dB) | −.224012 | −.876532 |

카메라별 dB 산술 평균이며 pooled pixel PSNR은 아니다. ROI PSNR이 높아진 사진도 native4/9, release2/9개 있어 개선 관측을 버리지 않는다. 전체 PSNR은 각각3/9개에서 높아졌다. ROI SSIM/LPIPS는 미측정이다. 이 작은 외관 차이의 반복 재현성은 검증하지 않았다.

## 기존 수정의 보존·소실과 같은 cell의 상반된 변화

| P2 .0005 | native | release |
|---|---:|---:|
| G의 Anchor 대비 수정 / 손상 | 126,582 / 207,564 | 121,213 / 204,712 |
| LC의 Anchor 대비 수정 / 손상 | 120,881 / 218,113 | 123,676 / 218,660 |
| G 수정 중 LC가 유지 / 소실 | 109,159 / 17,423 | 110,575 / 10,638 |
| G 손상을 LC가 회복 | 3,100 | 3,273 |
| LC 추가 손상 | 13,649 | 17,221 |
| G→LC 수정·손상 공존 cell | 369 / 8,799 | 363 / 8,799 |

전체 격자는8,832개, 참조 지지는8,799개다. 참조 부재33개는 미평가로 남긴다. 같은0.5m XY cell의 상반된 변화는 상쇄하지 않으며, 같은 Gaussian·같은 연속 표면의 직접 대응이나 면적·시점 진실값으로 해석하지 않는다.

## 실제 사진·단면 검토

결과 독립 선택 사진은 이전 P2와 같은 `DJI_20241217084503_0075_D.JPG`(image_id66, camera_id1, evaluation_index0)이고 bbox `[719,0,1400,623]`,681×623=424,263pixel이다. 네 패널은 원사진·Anchor·G·LC의 봉인 원본과 정확히 같으며 crop·선택 PSNR·단면 표본 수도 독립 대조를 통과했다.

선택 ROI PSNR은 native G23.92247→LC22.92478(−.99769dB), release G23.83834→LC23.24007(−.59827dB)다. 실제 그림에서 G는 Anchor보다 지붕과 입면을 선명하게 복원한다. LC도 큰 지붕·입면을 유지하지만 차량·작은 흰 물체·바닥 경계의 흐림이 늘어난다. 특히 release의 G에서 더 구별되던 차량 형태가 LC에서 흐려진다. 선택 사진 전체 PSNR도−.27068/−.29337dB다.

X=134m와 Y=109m midpoint의 폭.5m 점 띠를 함께 보았다. 두 방법 모두 Anchor의 높은 지붕 주변 중복 곡선을 줄이고 참조에 가까운 큰 외곽을 만든다. X 띠의 참조5,239개에 대해 G 예측2,830/2,965개, LC2,976/2,886개이며 반복 지붕 형태와 참조 사이 편차가 함께 남는다. Y 띠의 참조6,268개에 대해 G4,383/4,569개, LC4,381/4,555개다. native의 왼쪽 바닥 구간은 LC에서 더 휘고 참조와의 편차가 커진 부분이 보이는 반면, 다른 구간은 비슷하거나 더 가까워진 부분도 있다. 단면은 mesh-plane 교선이 아니고 미관측 참조 공백의 정오를 인증하지 않는다.

새 .0005 두 조건의 full/ROI/단면6개·지도2개와 P2 네 조건 행렬 그림2개를 실제 열어 검토했다. 행렬은이 attempt에서 그린4/18개와 그리지 않은14개를 명시한다. 후자는 현재 전체 큐의 미완료 수를 뜻하지 않는다.

## Source 층과 loss/controller

Prior near는 참조점→prior 삼각형 거리 `<.5m`, image-target near는 strict DA3 median world-Z 오차 절댓값 `≤.5m`다. source 정오나 사진 관측 가능성·시간 변화의 진실값이 아니다.

| 평가 층 | 참조점 수 | native 수정 / 손상 | release 수정 / 손상 |
|---|---:|---:|---:|
| prior near / image-target near | 28,250 | 815 / 3,781 | 614 / 4,905 |
| prior near / image-target far | 124,054 | 896 / 3,823 | 1,493 / 6,558 |
| prior far / image-target near | 27,213 | 563 / 3,397 | 1,175 / 2,199 |
| 둘 다 far | 89,802 | 8,162 / 9,031 | 8,938 / 4,922 |
| strict 대응 없음 | 302,895 | 4,386 / 11,040 | 4,154 / 9,275 |

전체 악화 속에서도 release의 both-far 층처럼 수정이 손상보다 많은 부분을 보존한다. Strict 지지269,319개 밖302,895개는 source 층으로 억지 분류하지 않는다. ±1m 등 추가 진단은 전체 cohort CSV에 있다.

완결된8100–30000 로그 표본은조건마다220개이고 대응 G와 카메라가220/220개 일치했다. 기록된 lambdaV 차이는 native0개, release177개다. native 평균lambdaV는양쪽.05, release는G.05→LC.0479886이다. 표본 평균 prior/visual 배율은.112940/.950413으로, 이 값을 맞춘 전역 대조를 실제 실행한 것은 아니다.

평균 raw prior loss는G81.1323/81.0955→LC82.9234/82.9288, raw visual loss도G4.44589/4.40134→LC4.77026/4.48053으로 증가했다. .005에서 관측한 raw visual loss 감소가 이 조건에서는 이어지지 않았다. 이는 원 목적의 표본 잔차이며 공간 배분만의 원인·전체 반복 안정성을 식별하지 않는다.

## 실행·검증 계보와 기여의 범위

외부 task root는 [resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml)의 `payload_host_root`다.

| 산출물 | task root 아래 경로 |
|---|---|
| P2 네 조건 평가 | `main_v2/evaluation/attempt_20260910T210212_221592Z/` |
| 전체 G/Anchor·LC 표와 모든 raw/post 문턱 | `main_v2/summary/attempt_20260910T210518_700422Z/` |
| 사진·단면 | `main_v2/figures/attempt_20260910T210517_436288Z/` |
| 같은 cell 지도 | `main_v2/maps/attempt_20260910T210212_221592Z/` |
| source 층 | `main_v2/strata_diagnostic/attempt_20260910T210516_668798885Z/` |
| 행렬 그림 | `main_v2/matrix_figures/attempt_20260910T210704_295617Z/` |
| 완결8개/진행2개 trace snapshot | `main_v2/trace_monitor/attempt_20260910T210632Z_F9RMGQ_trace_v2/analysis/` |
| 네 원본 패널·PSNR·단면 QA | `main_v2/figures_review/attempt_20260910T210703_894395Z/receipt.json` |
| 원 거리→모든 표시 cell 독립 QA | `main_v2/maps_review/attempt_20260910T210703_881599Z/receipt.json` |

평가 receipt SHA256은 `2cd606390cb3bc70a6077e292bb194a9bef9be6d2720fe98c4eaeb7fd626aa25`다. 독립 사진·지도 QA는4개 모두 PASS했다. 새 `.0005` 학습 driver wall은4599.872/4293.920초, child peak RSS는12,295,966,720/12,097,687,552bytes다. CPU 평가는P1 학습과 겹쳤고 직전 MemAvailable66,875,836kB를기록했다. 기존 G의 Anchor prefix·checkpoint·렌더 범위·타이머 차이를 유지하므로 순수 방법 비용 이득으로 해석하지 않는다.

**문제 차별성**은 유효한 기존 구조와 수정 필요 부분이 공존하는 조건이다. **원인 설명**은 loss·controller·대응 부위 변화의 관측으로 제한한다. **방법 신규성**이나 국소 규칙의 우위는 이 악화 관측으로 입증되지 않는다. **검증 기여**는 기존 G가 이미 회복한 형태와 LC가 보존·손실·추가 수정한 부위를 같은 원본 참조점·카메라·단면으로 추적하는 데 있다. 평균 배율 전역 대조·controller replay·반복이 없어 공간 배분 고유 효과, DA3 단독 인과, 작은 차이 재현성·일반화는 확정하지 않는다. GT는 평가 전용, scientific_verdict는 null이며 남은10개 모델 조건도 동결 명세대로 계속 실행한다.
