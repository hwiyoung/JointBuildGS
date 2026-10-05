# DA3 입력 불일치와 refinement의 보존·회복: 공간 진단

- 날짜: 2026-09-10
- Task: `PHD-GEOGS-P1P2P3-v1 / DA3_REFINEMENT_SPATIAL_DIAGNOSTIC_v1`
- 상태: `COMPLETE_PAIRED_SPATIAL_DIAGNOSTIC / DA3_ONLY_CAUSAL_EFFECT_UNMEASURED`
- 실행 receipt: `PASS_PAIRED_ASSOCIATION_ONLY`, `PASS_SAME_POINT_CORRESPONDENCE`
- `scientific_verdict: null`

**동일한 DA3 입력 아래에서도, 처음 양호했던 구조의 손상과 처음 멀었던 표면의 회복이 함께 발생했다. DA3 목표가 참조에 가까운 P2 부분에서는 큰 회복이 관찰됐지만, 목표가 높거나 낮게 벗어난 다른 부분에서는 추가 악화가 나타났다.** 아래는 이미 완료된 Anchor8k와 6조건 최종30k의 비교다. 새 학습·입력 보정·정합은 수행하지 않았다. DA3 on/off를 통제한 단독 인과 실험은 아직 실행하지 않았다.

## 비교와 지표의 뜻

공통 Anchor 이후의 `D005_Pnative`를 **원설정**, `D0005_Pnative`를 **prior 깊이 가중치 1/10**으로 표기한다. 후자는 **ALS prior 깊이 가중치를 .005→.0005로 낮춘 조건이며, DA3 가중치를 낮춘 조건이 아니다.** 둘 다 native 구조 보호를 유지한다. 전체 자료에는 prior 깊이 `.005/.0005/0` × 보호 `native/release`의 6조건이 포함된다.

Anchor에서는 DA3 깊이 감독을 사용하지 않고 refinement에서 사용한다. 그러나 단계 전환에는 prior 깊이 감독, 보호, RGB 및 다른 감독과 학습 일정의 영향도 포함된다. Anchor→최종은 **전체 refinement의 변화**, 같은 Anchor의 최종조건 대비는 **prior 제어 변경과 결합된 변화**다.

- **처음 양호 / Anchor-near:** 동일 UAS 참조점에서 Anchor 추출 표면까지 거리 `<0.5m`. 이 점 가운데 최종 표면도 `<0.5m`이면 보존으로 센다.
- **처음 멀음 / Anchor-far:** 초기 거리 `≥0.5m`. 최종 거리가 `<0.5m`가 되면 회복으로 센다.
- **paired 거리변화:** 각 동일 UAS점의 `최종 표면거리 − Anchor 표면거리`. 음수는 참조에 가까워짐, 양수는 멀어짐이다. 표의 median은 점별 차이의 median이며, 두 집단 median의 차이가 아니다.
- 이 보존·회복률은 **참조점 조건부 근접률**이다. F1, 면적 보존율, 건물 보존율 또는 외관 점수가 아니다. `Anchor-near`는 prior의 시간적 유효성이 판정됐다는 뜻도 아니다.
- **DA3 목표높이 편차:** 같은 영상 ray에서 DA3 camera-Z와 참조 camera-Z의 차이를 world-Z 성분으로 변환했다. 양수는 관측 UAS보다 높은 목표, 음수는 낮은 목표다. camera-Z 자체를 세계 높이로 간주하지 않았다.

표면은 전부 공식 추출 경로의 **raw TSDF512**다. 표면 표본/참조 voxel 각각0.1m, seed0, 지역별 ROI·참조점 식별자·좌표·추출 설정이 같다. `.final.raw`의 기존1024 지표와 혼합하지 않는다. Gaussian 중심점을 최종 표면으로 사용하지 않았다.

## 분석이 가능한 관측 범위

수직에 가까운 학습 사진만 선택하고, UAS 상부 표면·지역 UAS z-buffer 가시성·투영 주변부 피복과 깊이 안정성을 함께 검사한 점을 `strict support`로 사용했다. DA3 잔차 크기로 support를 선택하지 않았다. 외부 가림 물체가 모두 제공된 것은 아니므로 실제 물리적 가시성을 인증한 mask는 아니다.

|지역|선택 수직 근접 사진 / 학습 사진|strict UAS점 / 전체 UAS점|점 기준 비율|DA3 목표높이 편차 median|
|---|---:|---:|---:|---:|
|P1|1 / 98|97,887 / 246,125|39.77%|+2.654m|
|P2|14 / 57|269,319 / 572,214|47.07%|+0.711m|
|P3|8 / 137|236,736 / 908,677|26.05%|−0.297m|

이는 **참조점 개수의 비율**이며 지역 면적 피복률이 아니다. 이 밖의 영역은 DA3 오류 귀속에 필요한 지지가 부족한 영역으로 남긴다. 참조 부재·가림 불확실성과 복원 실패를 동일하게 세지 않는다. P1은 선택 사진이 한 장이므로 다중뷰 일관성을 검증할 수 없다.

## 대표 결과

### 1. P1: 같은 상향 불일치 안에서도 보존 손상과 회복이 공존한다

DA3 목표가 참조보다1m 이상 높은 91,571점을 초기 Anchor 상태로 나누면 방향이 달라진다.

|초기 상태|점수|원설정|prior 깊이 1/10|
|---|---:|---:|---:|
|Anchor-near|48,861|77.18% 보존|40.85% 보존|
|Anchor-far|42,710|12.71% 회복|47.16% 회복|

처음 양호한 점의 paired 거리변화 median은 **+0.142 / +0.515m**, 처음 멀던 점은 **−1.364 / −2.045m**다. 같은 DA3 편차 부호에서도 prior 완화가 기존 근접 구조를 더 많이 손상시키면서 다른 구조를 더 많이 회복했다.

X=−8 고정 단면에서는 DA3 목표가 현재의 낮은 평탄면보다 위에 있다. prior를 완화한 결과는 Anchor의 과거 상부면이 있던 구간에서 현재의 낮은 면에 접근하지만, Anchor가 이미 낮은 면을 따르던 구간의 변화도 함께 확인된다. 단면의 특정 구간이 이 전체 cohort 통계와 정확히 같은 집합인 것은 아니다.

### 2. P2: DA3 목표가 가까운 부분에서는 큰 회복이 관찰된다

DA3 목표 편차 `±0.5m` 이내이면서 Anchor-far인 **23,250점**에서 원설정은 **84.46%**, prior 깊이1/10은 **84.93%**를 회복했다. paired 거리변화 median은 **−1.131 / −1.059m**, 최종 거리 median은 **0.182 / 0.302m**다. 회복률이 비슷해도 거리의 분포까지 같은 것은 아니다.

X=134 고정 단면의 반복되는 지붕에서는 DA3 목표가 현재 굴곡 근처에 있고, refinement 결과가 Anchor의 과거 상부면보다 현재 지붕에 접근한다. **DA3 감독의 유용성과 부합하는 관찰**이지만, 다른 감독을 고정한 DA3 단독 효과의 측정은 아니다.

### 3. P2: 높게 벗어난 DA3 목표와 기존 근접 구조의 손상이 함께 나타난다

DA3 목표가 `+1m`를 넘고 Anchor-near인 **37,821점**의 보존률은 원설정 **50.30%**, prior 깊이1/10 **12.88%**다. paired 거리변화 median은 **+0.348 / +1.412m**, 최종 거리 median은 **0.497 / 1.497m**다.

따라서 P2 전체 평균이나 매끈한 외관만으로 prior 완화의 성공 여부를 판단하기 어렵다. 위2번의 회복과 이3번의 손상을 함께 기록해야 한다. 이 결과는 DA3 입력 불일치가 큰 곳과 손상이 겹친다는 증거이며, 손상의 전부를 DA3에 귀속한 결과는 아니다.

### 4. P3: 낮게 벗어난 부분은 회복보다 추가 악화가 두드러진다

DA3 목표가 `−1m`보다 낮고 Anchor-far인 **14,488점**에서는 원설정 **1.60%**, prior 깊이1/10 **0.61%**만 회복했다. paired 거리변화 median은 **+0.818 / +1.709m**, 최종 거리 median은 **1.885 / 2.822m**다.

반면 DA3 목표 편차 `±0.5m` 이내인 **118,550점 전체**는 초기 근접률 **99.06%**에서 최종 **98.66% / 96.08%**로 대부분 유지됐다. 다만 paired 거리변화 median은 **+0.0556 / +0.1019m**로 커졌다. 중앙 곡면의 유지와 가장자리·아래쪽 표면의 문제를 구분해서 볼 필요가 있다.

### 5. 큰 DA3 불일치가 있어도 유지되는 반례가 있다

P3의 `DA3>+1m / Anchor-near` 전체 21,507점의 보존률은 **56.75% / 52.63%**다. 그러나 같은 cohort에서 점이 가장 많은2m 격자, **X[−28,−26), Y[0,2)**의690점은 DA3 목표 편차 median이 **+1.675m**인데도 원설정 **100%**, prior 깊이1/10 **99.57%**가 유지됐다. 최종 거리 median은 **0.077 / 0.247m**다.

이 반례는 입력 깊이의 편차 하나만으로 최종 손상을 설명할 수 없음을 보여준다. 다른 감독·구조 보호·기하 상태·가시성과 추출의 영향을 함께 조사해야 한다. 타일은 **해당 지정 cohort의 점 개수가 최대인2m 격자**로 선택했고, 결과가 좋거나 나쁜 값을 기준으로 고르지 않았다. 다만 이 위치 탐색은 사후 진단이며 독립 검증 사례 선택은 아니다.

## 뷰 사이에 서로 다른 감독 목표가 존재한다

같은 참조점에 strict 관측이3개 이상 있는 점 중, DA3 목표높이의 뷰간 범위가1m를 넘는 경우는 P2 **208,358/256,395점(81.26%)**, P3 **128,600/196,629점(65.40%)**다. P1에서는 이 조건을 검사할 수 없다.

이는 사용한 카메라·참조 조건에서 감독 목표가 서로 맞지 않는다는 관찰이다. DA3 모델 자체의 오류, pose 오차, 남아 있는 가림·참조 오차를 분리한 비율이 아니다. 뷰median 깊이가 가까워 보여도 일부 뷰가 다른 표면으로 당길 수 있으므로, 단일뷰 정확성과 다중뷰 일관성을 구분해야 한다.

## 그림과 원자료

출력 저장소:

`/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/da3_refinement_spatial_v1/`

아래 주소는 기존 GeoGS 서비스의 같은 파일을 연다. 먼저 지역 단면을 열고, 같은 지역의 동일점 지도와 cohort 표를 함께 확인한다. 단면의 분홍 DA3 표시는 **ray에서 계산한 목표높이를 참조 XY에 붙인 진단 표시**이며 DA3를3D로 재구성한 표면이 아니다.

|자료|P1|P2|P3|
|---|---|---|---|
|고정 단면|[P1 단면](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/P1.fixed_sections.png)|[P2 단면](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/P2.fixed_sections.png)|[P3 단면](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/P3.fixed_sections.png)|
|같은 strict점의 공간 지도¹|[P1 지도](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/P1.matched_maps.png)|[P2 지도](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/P2.matched_maps.png)|[P3 지도](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/P3.matched_maps.png)|

¹ 동일점 지도와 비교 그림은 별도 Docker 실행에서 생성 완료했다. 세 지역 모두 DA3 지도와 거리변화 지도가 정확히 같은 참조점 집합으로 집계됨을 검사했다. 실제 PNG를 열어 축·색상·피복·A–F 위치 표시를 확인했다. 거리변화 지도에서 빨강은 참조로부터 멀어짐, 파랑은 가까워짐이며 회색은 이 진단의 관측 지지 부재다. 왼쪽 위 DA3 지도에서는 빨강이 높은 목표, 파랑이 낮은 목표를 뜻한다.

지도 A–F는 다음 2m×2m 진단 위치다. 숫자는 해당 타일 안의 **지정 cohort 참조점만** 사용하며, 위 본문 표는 지역의 전체 지정 cohort를 사용한다. 각 행은 결과값을 보지 않고 해당 cohort의 점 개수가 가장 많은 격자로 선택했다. 이 선정 기준도 사후 진단 선택임을 기록한다. 좌표는 공통 local metric이고 world shift는 `[690953, 5336071, 604]`다.

|표시|지역·초기 상태·DA3 목표|Local X / Y 범위(m)|점수|DA3 높이편차 중앙값|최종 표면거리 중앙값: 원설정 / prior 1/10|
|---|---|---|---:|---:|---:|
|A|P1 양호·+1m 초과|[−12,−10) / [4,6)|749|+2.440m|0.273 / 2.191m|
|B|P1 멂·+1m 초과|[−6,−4) / [−18,−16)|712|+2.685m|0.225 / 0.044m|
|C|P2 멂·±0.5m 이내|[120,122) / [92,94)|663|+0.396m|0.051 / 0.234m|
|D|P2 양호·+1m 초과|[110,112) / [112,114)|744|+1.715m|0.415 / 1.589m|
|E|P3 멂·−1m 미만|[−34,−32) / [−36,−34)|345|−3.435m|1.223 / 1.535m|
|F|P3 양호·+1m 초과|[−28,−26) / [0,2)|690|+1.675m|0.077 / 0.247m|

- [6조건 전체 지역 지표 CSV](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/global_stage_metrics.csv): 전체 P/R/F1와 참조점 거리 변화.
- [6조건 전체 cohort 전이 CSV](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/error_cohort_transitions.csv): 모든 깊이편차 구간·Anchor-near/far·거리 임계값0.25/0.5/1m.
- [지역별 지원 범위](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/region_support.csv), [사진별 지원 범위](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/per_view_support.csv).
- [cohort 비교 그림¹](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/cohort_summary.png), [대표 타일 원자료¹](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/representative_tiles.csv).
- [main 실행 receipt](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/receipt.json): 입력 SHA256, 설정, 도구 버전과 출력 SHA256.
- [동일점 지도 실행 receipt](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/receipt.json), [동일점 셀 원자료](http://127.0.0.1:8902/task/evaluation/da3_refinement_spatial_v1/strict_correspondence_v1/same_point_cells.csv). 같은 폴더의 `P1.six_conditions.png`, `P2.six_conditions.png`, `P3.six_conditions.png`는 6조건을 동일 지지·축척·색상으로 보여 준다.
- [P1 실제 수직 근접 사진과 입력 비교](http://127.0.0.1:8902/task/input_diagnostics_v1/da3_visual_review_v1/P1_nadir.png), [P2](http://127.0.0.1:8902/task/input_diagnostics_v1/da3_visual_review_v1/P2_nadir.png), [P3](http://127.0.0.1:8902/task/input_diagnostics_v1/da3_visual_review_v1/P3_nadir.png). 이전 입력 진단의 사진 사례로, 위 전체 다중뷰 집합과 같은 단일 집계로 간주하지 않는다.

`{P1,P2,P3}.paired.npz`에는 같은 참조점 ID·XYZ, Anchor/6최종 표면거리, 사진별 DA3 camera-Z·world-Z 편차, support 및 cell 식별자를 보존했다. 재현 소스는 [분석 스크립트](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/analysis/da3_refinement_spatial.py)와 [설정](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_p1p2p3_v1/da3_refinement_spatial_v1.json)이다. 프로젝트 계산은 Docker에서 실행했다.

**원 main `*.spatial_maps.png`와 `spatial_cells.csv`의 DA3 편차는 strict점, 거리변화는 셀의 전체 UAS점 집계다.** 이 둘의 겹침은 공간 맥락으로만 사용한다. DA3오류와 결과변화의 직접 대응에는 위 동일 strict점 지도와 cohort/paired NPZ를 사용한다. 원 셀상관계수를 DA3 효과의 근거로 사용하지 않는다.

## 검증 범위와 후속 질문

공식 실행 소스에서 refinement는 DA3를 metric L1 목표로 사용했고, 이번 18조건은 confidence·scale-invariant 옵션이 꺼져 있었다. 해당 손실 호출에는 ROI·alpha·외부 가림 mask가 전달되지 않았다. 다만 학습 깊이는 alpha로 정규화한 **expected depth**이고 이번 UAS 진단은 관측 앞표면이며, 최종 결과는 TSDF 추출 표면이다. 따라서 목표의 불일치가 최종 삼각형의 동일한 높이 편차로 그대로 전달된다고 가정하지 않는다. L1에서는 큰 잔차가 픽셀별 더 큰 gradient 크기를 뜻하지도 않는다.

이번에 확인한 오류 후보는 **높이 목표의 상향·하향 불일치와 뷰간 목표 불일치**다. 이를 DA3 모델 자체의 배치 척도 파손으로 확정하지 않는다. 앞선 대규모 사경 잔차는 가림·참조 표면 선택의 영향을 분리하지 못했다는 [입력 감사 정정](DA3_AUDIT_INTERPRETATION_CORRECTION_ko_v1.md)을 그대로 유지한다. P3 단면에서는 원설정의 지붕 아래 다중 표면이 prior 깊이1/10에서 줄어드는 이득도 보인다. 이 추출 표면의 감소와 참조 근접 구조의 손상을 함께 보고, 하부 띠를 DA3가 만들었다는 인과 귀속은 유보한다.

- 표면/참조 식별과 계산은 기술적으로 검증됐다. 동일지역의 공통 Anchor 복원 직후 상태도 검증됐지만, 이후 CUDA 학습 궤적의 exact parity와 장기 반복 품질 변동은 입증되지 않았다.
- EPSG:25832 local metric과 공통 world shift를 유지했다. UAS header는 EPSG:32632이며 기존 높이 계보와 절대 datum·참조 피복 불확실성은 그대로다. UAS로 학습 입력·정합·조건을 보정하지 않았다.
- 선택 사진은 학습용 수직 근접 영상의 일부다. 독립 평가 사진의 렌더 품질을 이 참조점 기하 지표에서 추론하지 않는다. 기존 SfM 전처리 계보의 평가 영상 관여 한계도 해소된 것이 아니다.
- DA3 편차, Anchor-near/far 분류, 최종 표면거리가 **동일 UAS를 공유**한다. 참조 잡음·초기오차 선택·공간 유형 차이가 연관을 만들거나 키울 수 있다. 픽셀/참조점을 독립 실험 반복으로 간주하지 않는다.
- TSDF512는 동일하지만 추출의 smoothing·피복 손실은 남는다. 최종 mesh의 변화가 학습된 렌더 깊이 단계에도 존재하는지 별도 추적해야 한다.

현재 확인된 현상은 **입력 불일치의 방향, 뷰간 일관성, 초기 구조의 근접 상태에 따라 회복과 보존 손상이 달라진다**는 것이다. 추가 검증은 같은 Anchor·카메라·학습량·다른 감독을 고정한 DA3 on/off 또는 입력품질 통제 비교에서, 위 회복과 손상 집단의 변화가 재현되는지를 묻는다. UAS로 만든 유리한 보정값을 학습하는 조건과 정직한 입력 조건은 구분해야 한다. 이 문서는 새 제어 알고리즘의 필요성·우위나 DA3의 단독 인과 기여량을 판정하지 않는다.

구체적인 다음 비교는 같은 complete Anchor8k에서 DA3 감독을 켠22k refinement와 끈22k refinement다. prior 깊이·구조 보호·RGB·카메라 순서·학습 일정·추출512를 동일하게 고정하고, 실제 DA3 총 손실항과 first-step 기록으로 on/off를 검증해야 한다. 현재 dynamic controller는 `--lambda_da_depth 0`만 지정해도 .05를 사용할 수 있으므로 단순 CLI 변경은 유효한 off 조건이 아니다. 이 비교도 **현재 DA3 감독 전체의 순효과**를 분리하며, 특정 오류만을 고친 효과는 아니다. 오류별 효과에는 학습 자료만으로 정의한 수정 또는 독립적인 오염 통제가 추가로 필요하다.

현재 결과에서 검증할 개선 방향은 세 가지다. (1) 틀어진 깊이 목표가 이미 양호한 구조를 손상시키는 노출을 줄일 수 있는가, (2) 현재 표면 회복을 돕는 깊이는 유지할 수 있는가, (3) 여러 뷰가 서로 다른 목표를 주는 영역을 구분할 수 있는가. 이 진단에서 사용한 UAS 기반 near/far·오류 구간은 평가용 분류이며 그대로 학습 판단 알고리즘에 넣을 수 없다. 어떤 신뢰도·제어가 이 목표를 충족하는지는 후속 동일 조건 비교의 질문으로 남긴다.

## 실행과 검증 기록

두 계산 모두 고정 Docker 이미지 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, CPU2개·메모리6GiB 상한으로 실행했고 종료0이다. main과 `strict_correspondence_v1/` 각각 `code/`, `config.json`, `command.sh`, `run.log`, `exit_code.txt`, `receipt.json`이 있다. 이 자원값은 실행 제한이며 실측 peak 메모리가 아니다. 새 모델 학습·렌더·TSDF 추출은 수행하지 않고 보존된 결과를 분석했다.

21개 입력의 raw512/iteration/CRS/참조 식별자를 대조했고, 원 참조 ID를 통한 XYZ 복원이 세 지역 모두 정확히 일치했다. 독립 읽기 검증에서 paired NPZ로 cohort72행의 표본 수·획득·상실·거리변화 중앙값을 재계산해 CSV와 일치함을 확인했다. 지도 집계 검토에서 발견한 strict/전체높이 참조점 불일치는 원 산출물을 유지한 채 동일점 보완물로 해결했다. 기록은 [ISSUES](ISSUES_ko_v1.md)의 `DA3-SPATIAL-001`이다. 기존 문서·학습 결과·서비스를 덮어쓰거나 재시작하지 않았다.

보완물도 독립 Docker 읽기 검사에서 지역당1셀의5통계, 대표 타일6개의 max-count 선정·좌표·점수, 전체 cohort 막대12개가 원 NPZ 재계산과 일치했다. 첫 독립 검사에서는 모든 계산 assertion이 통과한 뒤 점검 JSON 출력의 `numpy.int64` 직렬화만 실패했으며, 출력 정수 변환 후 같은 읽기 검사가 종료0으로 완료됐다. 과학 출력에는 변경이 없다. 실제 제공하는 단면3개·동일점 지도3개·비교 그림1개·CSV3개의 HTTP200과 내용형식을 확인했고 기록은 `strict_correspondence_v1/http_check.txt`다. 다음 세션은 [공간 진단 인계](DA3_REFINEMENT_SPATIAL_HANDOFF_ko_v1.md)에서 시작한다.
