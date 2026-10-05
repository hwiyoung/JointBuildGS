# 첫 prior .005 여섯 조건 — 부분 관측과 P3 검토

- task_id: `PHD-LOCAL-COMPLEMENTARY-REFINEMENT-v1`
- 명세: `main_v2`; scientific_verdict: null
- 상태: `PARTIAL_INTERMEDIATE_NO_OUTCOME_CONCLUSION`, 6/18 조건만 평가 완료
- 원 실행·문턱·loss 계약: [MAIN_SPEC_ko_v2.md](MAIN_SPEC_ko_v2.md)

P1/P2/P3의 `.005 × native/release`는 학습·추출·외관 계산을 모두 완료했다. 아래는 첫6개의 관측이며, 남은 `.0005/0` 조건을 바꾸거나 전체 방법의 우열을 판정하는 근거로 사용하지 않는다. 기존 complete Anchor8k와 G18개는 재사용했고 신규 LC만 실행했다. P1/P2의 상세 사진·단면·source 층은 [P1 보고](INTERIM_P1_D005_ko_v2.md), [P2 보고](INTERIM_P2_D005_ko_v2.md)에 있다.

## 대응 G 대비 개선과 악화

Raw TSDF512, 거리 `<0.5m`, 정확도는 예측 표면 표본→관측 UAS, 완전성은 동일 UAS 원본점→삼각형 표면이다. 아래 수정·손상은 후자의 동일 참조점에서 문턱을 넘는 변화다. 참조 근접도이며 표면의 정오·면적·시점 유효성은 아니다.

| 지역 / 보호 | Δ정확도 (%p) | Δ완전성 (%p) | ΔF1 (0–1) | G→LC 수정 / 손상 참조점 |
|---|---:|---:|---:|---:|
| P1 native | +0.34 | −20.46 | −0.08504 | 35,486 / 85,853 |
| P1 release | +3.54 | −19.83 | −0.06646 | 32,936 / 81,739 |
| P2 native | −0.55 | −13.70 | −0.08460 | 32,360 / 110,751 |
| P2 release | +5.31 | −9.33 | −0.03685 | 51,225 / 104,624 |
| P3 native | +16.12 | −4.23 | +0.04541 | 51,569 / 90,015 |
| P3 release | +18.24 | −3.46 | +0.05877 | 51,365 / 82,828 |

P3의 정확도·F1 상승과 세 지역 모두의 완전성 하락을 함께 기록한다. 모든6개에서 동일 참조점 손상 수가 수정 수보다 많다. 정확도와 완전성은 분모가 달라 정확도 상승만으로 구조 보존을 주장하지 않는다.

## P3의 기존 방법 성공을 포함한 전체 대조

모든 행의 참조점 수는908,677개다. 원 ROI와 참조 ID/XYZ/순서는 동일하다.

| 조건 | 정확도 (%) | 완전성 (%) | F1 | Anchor 대비 수정 / 손상 |
|---|---:|---:|---:|---:|
| Anchor8k | 70.29 | 70.06 | .702 | — |
| G .005 native | 58.19 | 59.43 | .588 | 141,278 / 237,879 |
| G .005 release | 55.89 | 57.79 | .568 | 133,659 / 245,202 |
| G .0005 native | 73.83 | 54.29 | .626 | 137,646 / 280,996 |
| G .0005 release | 74.84 | 55.01 | .634 | 142,732 / 279,521 |
| G 0 native | 74.83 | 55.36 | .636 | 145,113 / 278,764 |
| G 0 release | 74.71 | 54.87 | .633 | 149,819 / 287,842 |
| LC .005 native | 74.31 | 55.20 | .633 | 138,123 / 273,170 |
| LC .005 release | 74.13 | 54.33 | .627 | 138,377 / 281,383 |

P3에서 G0 native는 LC.005 native보다 정확도·완전성이 모두 높고, G.0005 release도 LC.005 release보다 두 지표가 높다. 따라서 `.005` 대응 G에 대한 개선을 전역 대조군 전체에 대한 우위로 바꾸어 말할 수 없다. 이 다른 prior 계수 비교는 기존 방법의 성능 범위를 보이는 맥락이며, 정확한 평균 배율을 맞춘 전역 대조를 대신하지 않는다. 계수0도 prior 의존 Anchor·가중·보호를 유지하므로 image-only가 아니다.

P3 native/release에서 G가 Anchor 대비 수정한 점 중 LC가 유지한 수는115,862/115,127, 잃은 수는25,416/18,532다. G의 손상을 회복한 수는29,308/28,115지만 LC가 추가한 손상도64,599/64,296개다. 같은0.5m XY cell에서 수정과 손상이 공존한 cell은1,024/934개(관측 참조가 있는8,633개 중)다. 전체8,640개 중 참조 부재7개는 미평가로 남긴다. cell 공존은 동일 Gaussian 또는 연속 표면의 직접 대응을 뜻하지 않는다.

## P3 사진·단면과 평균 외관

20개 대응 카메라의 전체 PSNR 평균 변화는 native/release 각각+0.08500/+0.10685dB, ROI PSNR 평균 변화는+1.52384/+1.03533dB다. 전체 LPIPS는 약.397→.400/.394→.397로 악화했다. ROI PSNR이 높아진 카메라는11/20,9/20개이며 평균 상승이 모든 사진의 개선을 뜻하지 않는다. dB의 카메라별 산술 평균이고 pooled pixel MSE로 산출한 PSNR이 아니다. ROI SSIM/LPIPS는 미측정이다.

결과와 무관하게 고정 prism의 투영 bbox 면적으로 선택한 사진은 `DJI_20241217103039_0045_D.JPG`, image_id859, camera_id1, evaluation_index17이다. bbox `[156,0,1400,965]`, crop1244×965=1,200,460pixel이며, 원사진·Anchor·G·LC를 동일 원본 pixel과 crop으로 비교했다.

| P3 선택 사진 | G PSNR | LC PSNR | 변화 (dB) |
|---|---:|---:|---:|
| native 전체 | 20.61995 | 20.59989 | −.02006 |
| native ROI | 20.86791 | 20.83265 | −.03526 |
| release 전체 | 20.79270 | 20.48971 | −.30299 |
| release ROI | 21.02505 | 20.73818 | −.28687 |

실제 원사진에서는 큰 곡면 지붕, 수평 줄무늬 입면, 전경 금속 지붕, 연결 통로와 입면 아래 차량이 보인다. G는 Anchor의 흐림에 비해 지붕·입면 줄무늬와 작은 물체를 복원한다. LC도 큰 지붕·입면을 유지하지만 native의 차량·바닥 경계는 대응 G보다 흐려진다. release도 작은 물체의 일관된 개선으로 보이지 않는다. 원본 pixel 일치와 PSNR 독립 재계산은 통과했지만 이 정성 관찰은 semantic O/X나 현재 기하 인증이 아니다.

원 ROI midpoint의 X=−40m와 Y=−15m, 폭.5m 점 띠를 확인했다. 이는 mesh와 평면의 정확한 교선이 아니다. X 띠의 참조점은10,469개, 예측 표본은 Anchor7,864→G18,046/17,190→LC8,893/8,949다. 내부에 넓게 퍼진 G 예측이 LC에서 줄고 상부 지붕·큰 외곽 형태가 남는다. Y 띠는 참조6,789개, Anchor5,400→G8,105/7,904→LC5,935/5,103으로, 바닥 주변의 어긋난 예측과 G의 근접 지지가 사라진 부위도 함께 보인다. 관측 UAS의 가시성·피복이 인증되지 않았으므로 참조점 없는 내부 예측 전부를 잘못된 구조로 분류하지 않는다.

P3의 full/ROI/단면6개와 지도2개, 첫6개 행렬 그림2개를 실제 열어 검토했다. 지도는 수정/손상을 상쇄하지 않고 같은 축과 원본 참조점을 사용한다. 행렬 그림은6/18 부분 상태와 빠진12조건을 명시하며, 조건별1회여서 신뢰구간을 그리지 않는다.

## Source proxy와 controller 관측

Prior near는 참조점→prior 삼각형 거리 `<.5m`, image-target near는 strict 대응 DA3 target의 유한 median world-Z 오차 절댓값 `≤.5m`다. 둘은 다른 양의 평가 proxy이며 source의 정오·사진 관측 가능성·시점 변화의 진실값이 아니다.

| P3 평가 층 | 참조점 수 | native 수정 / 손상 | release 수정 / 손상 |
|---|---:|---:|---:|
| prior near / image-target near | 117,826 | 974 / 4,233 | 596 / 5,236 |
| prior near / image-target far | 103,991 | 4,107 / 5,074 | 4,667 / 6,100 |
| prior far / image-target near | 724 | 34 / 11 | 30 / 15 |
| 둘 다 far | 14,195 | 253 / 205 | 367 / 298 |
| strict 대응 없음 | 671,941 | 46,201 / 80,492 | 45,705 / 71,179 |

Strict 지지는236,736개뿐이며, 이를 벗어난671,941개는 별도로 남긴다. prior far / image-target near의724개 관측을 지역 전체의 상보 가능성으로 일반화하지 않는다. ±1m 등 민감도·중첩 층은 전체 cohort CSV에 보존한다.

완료 trace의8100–30000, 각220개 표본은 G/LC 카메라가 모두 일치했다. 실제 lambdaV가 다른 표본은 native0개, release204개다. native 평균lambdaV는양쪽.0435126, release는G.0476818→LC.05다. 로그 표본의 평균 prior/visual 배율은.249694/.911348로, 입력 전체의 camera-uniform 통계와 분모·표본 추출이 다르다. 평균 raw prior loss는G19.2168/20.9639→LC30.9180/30.9365로 증가하고 raw visual loss는10.1093/9.8556→9.2055/9.0371로 감소했다. 이는 최적화 목적의 상충 관측이고 직접 형상 정오나 DA3 단독 원인이 아니다. Native의 기록된 lambdaV 일치도 전체 controller replay를 실시했다는 뜻이 아니다.

## 계보·검증·비용과 해석 한계

외부 task root는 [resolver](../../../../artifacts/manifests/local_complementary_refinement_v2.yaml)의 `payload_host_root`다. 다음 경로는 모두 그 아래이며 기존 attempt를 덮어쓰지 않았다.

| 산출물 | 경로 |
|---|---|
| 첫6개 평가 | `main_v2/evaluation/attempt_20260910T194117_768119Z/` |
| 전체 G/Anchor·LC 표와 raw/post 모든 문턱 | `main_v2/summary/attempt_20260910T194640_975912Z/` |
| 사진·단면 | `main_v2/figures/attempt_20260910T194638_655580Z/` |
| 같은 cell 지도 | `main_v2/maps/attempt_20260910T194117_768119Z/` |
| source 층 | `main_v2/strata_diagnostic/attempt_20260910T194637_863822280Z/` |
| 부분 행렬 그림 | `main_v2/matrix_figures/attempt_20260910T194707_258527Z/` |
| 완료6개/진행2개 trace snapshot | `main_v2/trace_monitor/attempt_20260910T194335Z_KFH275_trace_v2/analysis/` |
| 독립4개 원본 패널·PSNR·단면 표본 수 QA | `main_v2/figures_review/attempt_20260910T203212_627796Z/receipt.json` |
| 독립 원 거리→모든 표시 cell QA | `main_v2/maps_review/attempt_20260910T201112_205568Z/receipt.json` |
| 앞선 P1/P2와 첫6개 평가의 정확한 동등성 | `main_v2/evaluation_preflight/first6_parity_v2/receipt.json` |

평가 receipt SHA256은 `3e19a441629f5a49f6a5413c4a8f4c5b3a7c60d6708fefd79ce91fdc48bfc08b`다. 첫6개 원본 pixel/PSNR/단면 QA는 PASS다. 별도 map_review는 Anchor/G/LC의 원 거리 배열과 정확한 참조점 ID/XYZ에서18개 지도 panel의 모든 표시 cell을 재계산하여 수정·손상·유한 거리 쌍·strict 지원·범주·전체 격자 수의 일치를 확인했다. P1/P2의 앞선 별도 평가와 이번 통합 평가 사이14개 CSV의 해당 지역 행,8개 거리 NPZ,12개 사진·단면 PNG,8개 map CSV/PNG가 모두 정확히 같았다. 이것은 분석 재계산의 일치이며 독립 학습 반복의 재현성 증거가 아니다.

Figure QA의 최초 attempt는4개 ROI crop 일치와 원사진/G/LC 원본 대조를 수행했다. 위 최종 QA는 Anchor 전체 패널까지 봉인 원 렌더와 독립 대조한 `v2.1_all_four_native_panel_sources`이며,6개 모두 통과했다. 최초 QA는 `attempt_20260910T195401_933515Z`에 보존하고 검사 범위 보완은 [issue](ISSUES_ko_v2.md)에 기록했다.

P3 학습 driver wall은6100.877/7501.454초, child peak RSS는18,526,359,552/22,940,512,256bytes다. 각 학습은GPU1/CPU8/RAM32GiB/network none이다. CPU 부분 평가는 다음 P2 .0005 학습과 겹쳤고, 기존 G의 Anchor prefix·checkpoint 저장·primary1024/auxiliary512 렌더 범위·타이머가 다르다. 비용 원값은 보존하지만 순수 방법 비용 우위를 주장하지 않는다. Peak RSS에서 과거 prefix를 차감할 수 없으며 trace의 CUDA 표본을 전체 pipeline 최대값으로 바꾸지 않는다.

GT는 평가 컨테이너에서만 사용했다. CRS25832/참조32632 header 및 기존 height bridge45.7m·datum 미인증, GT 재정합 없음, UAS 피복 미인증의 범위는 원 계약을 유지한다. Raw512가 주평가이고 post512와.1/.2/.25/.5/1/2m 문턱 결과는 별도 CSV에 모두 남긴다.

박사학위의 **문제 차별성**은 유효한 기존 구조와 수정 필요 부분이 공존하는 상황을 다루는 데 있다. **원인 설명**은 충돌·loss·controller 반응·대응 형상 변화를 연결하되 source 정오와 공간 배분 원인을 아직 식별하지 못한다. **방법 신규성**은 이 정적 상보 규칙의 최초성이나 별도 복원 원리를 이번 결과가 입증하지 않는다는 범위로 제한한다. **검증 기여**는 같은 Anchor·입력·참조점에서 기존 G의 성공과 새 LC의 악화·수정·추가 손상을 함께 추적하는 통제와 감사 자료다. 평균 배율 전역 대조, controller replay와 독립 반복이 없으므로 공간 배분 고유 효과·DA3 단독 인과·작은 차이 재현성·일반화 판정은 남는다. 과학적 판정은 null을 유지한다.
