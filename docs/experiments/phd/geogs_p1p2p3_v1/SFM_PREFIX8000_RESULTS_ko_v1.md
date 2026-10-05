# SfM 초기화·Anchor 생략 8k 보조 결과

2026-09-10 · `PHD-GEOGS-SFM-NO-ANCHOR-v1` · `analysis_role: SUPPLEMENTARY_PREFIX_DIAGNOSTIC` · `scientific_verdict: null`

**현재 결과로 “Anchor를 생략해도 충분하다”는 결론은 낼 수 없다.** SfM 초기화에서 Anchor 없이 8,000회 refinement를 수행한 경로는 기존 ALS 초기화·Anchor 8,000회보다 P1/P2/P3 모두 평가 사진의 평균 RGB 지표가 개선됐다. 반면 관측 UAS에 0.5m 이내로 가까운 raw 표면의 F1은 P1 0.6408→0.4839, P2 0.4651→0.3778, P3 0.7018→0.5543으로 낮아졌다. P2의 1·2m 허용 거리에서는 F1이 높아져, 엄격한 표면 일치와 큰 편차의 감소가 같은 방향으로 움직이지 않았다.

P2 고정 단면에서는 넓은 상부 부유 성분이 줄어든 동시에 반복 곡면을 잇는 완만한 표면이 남았다. P3에서는 지붕 근접을 유지하고 일부 외벽을 더 채우면서 지붕 아래의 추출 성분도 늘었다. 즉, 국소 보완과 국소 손실이 함께 존재한다. 이것은 어떤 기존 자산이 유효하거나 오래되었는지의 판정은 아니다. 초기화·감독 단계·학습 일정·보호 멤버십을 함께 바꾼 비교이므로 Anchor 하나의 효과를 분리하지 못한다.

이 문서의 확정 수치는 **세 지역의 완료된 8k 보조 평가**다. P2를 상세히 분석하고 P1/P3의 실제 표·고정 사진·단면을 함께 제시한다. 원 22k/30k 실험과 자원 복구 실행은 별도 계보로 유지된다. P1의 마지막 자원 복구는 CUDA OOM으로 닫혀 22k/30k 미완료이고, P2/P3의 마지막 시도는 진행 중이다. 아래 historical 8k가 전체 완료나 최종 수렴을 대신하지 않는다.

## 1. 같은 8,000회에서 비교한 것은 두 대체 경로다

[사전 계획][plan]과 [8k 조건부 진단 계약][policy]은 세 지역에서 같은 8,000회 checkpoint만 쓰도록 고정했다. 마지막으로 남은 iteration이나 품질이 좋은 checkpoint를 고르지 않는다. 주 비교는 기존 `D005_Pnative.anchor_512`와 새 `SFM_noanchor_D005_Pnative_PREFIX8000`이며, 기존 30,000회 결과는 처리량이 다른 문맥용 비교다.

| 비교 요소 | 기존 ALS 초기화 + Anchor 8k | 역사적 SfM 초기화 + Anchor 생략 8k |
|---|---|---|
| P2 초기 Gaussian | ALS 파생 표면의 93,497개 | 실제 SfM의 5,665개 |
| 1–8,000회 단계 | Anchor | refinement |
| ALS depth 계수 | 0.08 | 0.005 |
| DA3 depth | 이 구간 weight 0 | 첫 step 0.05에서 동적 제어 |
| 보호 대상 등록 | 8k 상태에 한 번 매칭 | 첫 최적화 전 초기 SfM에 한 번 매칭 |
| P2 8k 등록 보호 Gaussian | 114,521개 | 1,437개 |
| P2 8k 전체 Gaussian | 1,625,820개 | 1,704,451개 |
| 일정의 의미 | 원 anchor 구간 | 원 30k 일정의 첫 8k refinement 구간 |

등록 보호 수는 **mask가 등록된 Gaussian 수**다. 기존 조건의 8k 이전 mask가 0이어도 ALS 초기화와 depth 감독의 영향은 존재한다. 두 조건 모두 native clone/split/prune 규칙을 쓰지만, 적용되는 Gaussian 분포와 loss가 다르다. 새 조건은 ALS Gaussian을 추가하지 않았어도 ALS 깊이 감독과 근접 Gaussian 보호를 유지하므로 image-only가 아니다. 최초 SfM 실행의 점 수를 현재 선택된 자원 복구 실행의 점 수로 대신하지 않았다. 위 수는 [고정 historical trace의 8k endpoint CSV][counts]에서 가져왔다.

학습률·SH 증가·normal 활성화·densification은 global iteration을 따른다. 새 경로의 1–8k는 기존 refinement의 8001회 이후 구간과 같은 일정 위치가 아니다. 특히 공통 normal 항은 global 7,000회 이후 켜진다. 같은 8k 처리량 비교는 가능하지만, 같은 상태에서 Anchor만 제거한 비교는 아니다. 구체적 공통 규칙과 차이는 [코드·trace 감사][densification-audit]를 따른다.

아래는 동일 8k의 통합 표다. F1은 관측 UAS와의 양방향 표면 근접도를 결합한 값이며 표면 표본/UAS voxel 모두 0.1m인 기본 설정을 사용한다. `0.5 / 1m` 열은 각 거리 임계값의 F1을 차례로 표시한다. RGB는 지역별 고정 투영 bbox 사진의 단순 평균이고 LPIPS는 signed [−1,1] 입력 관례다. 지역별 지표를 독립 표본인 것처럼 합산하지 않는다. 원 값과 source SHA는 [통합 CSV][combined-table] 및 [검증 receipt][combined-proof]가 소유한다.

| 지역·조건, 각 8k | raw F1, 0.5 / 1m | post F1, 0.5 / 1m | ROI PSNR, dB ↑ | ROI SSIM ↑ | ROI LPIPS signed ↓ |
|---|---:|---:|---:|---:|---:|
| P1 ALS Anchor | 0.6408 / 0.7448 | 0.6362 / 0.7389 | 14.5845 | 0.3933 | 0.5937 |
| P1 SfM no-Anchor | 0.4839 / 0.6677 | 0.4567 / 0.6286 | 17.1127 | 0.5378 | 0.4958 |
| P2 ALS Anchor | 0.4651 / 0.6188 | 0.4376 / 0.5701 | 13.7391 | 0.3084 | 0.6363 |
| P2 SfM no-Anchor | 0.3778 / 0.6935 | 0.3729 / 0.6884 | 14.8572 | 0.3373 | 0.6147 |
| P3 ALS Anchor | 0.7018 / 0.8028 | 0.6828 / 0.7833 | 15.3667 | 0.3800 | 0.6143 |
| P3 SfM no-Anchor | 0.5543 / 0.7190 | 0.5726 / 0.7406 | 19.1870 | 0.5629 | 0.5028 |

평균만으로 모든 사진이 좋아졌다고 해석하지 않도록 같은 사진·카메라·crop의 44쌍을 대조했다. 이름, evaluation index, image/camera ID, 사진 SHA와 ROI 좌표가 모두 일치한다. **P2에서는 PSNR과 SSIM이 각각 3/9장 낮아졌다.** P1에도 PSNR이 낮아진 1장이 있다. 아래 집계는 고정 사진 전체의 변화 방향이며 새 사례를 선택한 결과가 아니다. [사진별 원 값·차이][paired-photos] · [방향 집계 CSV][paired-counts]

| 지역 | 일치한 사진 쌍 | PSNR 상승 / 하락 / 동일 | SSIM 상승 / 하락 / 동일 |
|---|---:|---:|---:|
| P1 | 15 | 14 / 1 / 0 | 15 / 0 / 0 |
| P2 | 9 | 6 / 3 / 0 | 6 / 3 / 0 |
| P3 | 20 | 20 / 0 / 0 | 20 / 0 / 0 |

## 2. P2 사진 평균은 개선됐지만 고정 사진에도 세부 손실이 남는다

P2의 동일 평가 사진 9장을 모두 평가했다. 두 도메인 모두 9/9장이 평가됐고 실패는 0이다. 아래 값은 **사진별 지표의 지역 내 단순 평균**이다. ROI 총 픽셀 수는 1,157,082, 전체 사진은 12,763,800이지만 픽셀 수로 가중한 평균은 아니다. PSNR·SSIM은 높을수록, LPIPS는 낮을수록 사진과 가깝다. LPIPS는 표의 입력 범위를 명시해 서로 섞지 않는다.

| 도메인·지표 | ALS Anchor 8k | SfM no-Anchor 8k | 변화 | 기존 native 30k, 문맥용 |
|---|---:|---:|---:|---:|
| 고정 투영 ROI PSNR, dB ↑ | 13.7391 | 14.8572 | +1.1181 | 16.4402 |
| 고정 투영 ROI SSIM ↑ | 0.3084 | 0.3373 | +0.0289 | 0.4466 |
| 고정 투영 ROI LPIPS, native [0,1] ↓ | 0.6047 | 0.5808 | −0.0239 | 0.4933 |
| 고정 투영 ROI LPIPS, signed [−1,1] ↓ | 0.6363 | 0.6147 | −0.0216 | 0.5252 |
| 전체 사진 PSNR, dB ↑ | 15.0222 | 16.5231 | +1.5008 | 19.3743 |
| 전체 사진 SSIM ↑ | 0.4365 | 0.4719 | +0.0354 | 0.6390 |
| 전체 사진 LPIPS, signed [−1,1] ↓ | 0.6305 | 0.6061 | −0.0245 | 0.4534 |

출처는 [P2 RGB 비교 CSV][render-csv]와 [새 조건의 사진별 CSV][render-per-image]다. 개선은 이 9장 평균의 관측이며 모든 사진·영역의 개선을 뜻하지 않는다. 기존 native 30k는 더 많은 업데이트 뒤의 값이므로 동등 예산의 우열 판정에 쓰지 않는다.

![P2 고정 첫 사진의 실제 사진, ALS Anchor 8k, 역사적 SfM no-Anchor 8k, 기존 native 30k 문맥용 비교][fixed-photo]

그림은 고정 평가 순서의 첫 사진 `DJI_20241217084503_0075_D.JPG`(index 00000)이다. 원본 1400×1013에서 반개구간 ROI `[719, 0, 1400, 623)`를 사용했고, 각 681×623 패널을 리샘플링 없이 복사했다. 세 montage의 사진 패널과 최종 PNG의 네 패널은 각각 원본 RGB byte와 일치했다. 파일과 픽셀 SHA, 원 montage crop 위치는 [그림 검증 receipt][figure-receipt]에 있다. 첫 index를 고정해 사용했으며 좋은 사례를 검색해 고른 그림은 아니다. 기존 montage를 먼저 열어본 사실도 설정에 보존했다.

**시각 관찰:** SfM 8k는 Anchor 8k보다 오른쪽 반복 곡면 지붕의 구분과 일부 장비 외곽이 선명해 보인다. 기존 native 30k는 작은 질감이 더 보인다. 그러나 이 사진의 미분 가능 렌더링 외관만으로 해당 곡면의 3D 높이·곡률 일치, ROI 전체 구조 보존 또는 시간적 정합성을 확인할 수 없다. 다음 단면은 외관 개선과 표면 일치가 분리되는 사례다.

## 3. P2의 엄격한 표면 일치는 낮아지고 큰 편차는 줄었다

기하는 Gaussian 중심이 아닌 **공식 TSDF의 삼각형 표면**을 평가한다. 두 조건 모두 `mesh_res=512`이며 raw가 주 평가, 공식 후처리 post가 보조 평가다. 고정 scene-local 범위는 X `[110,158)`, Y `[86,132)`, Z `[−49.386,−17.679)`m이고 EPSG:25832의 공통 world shift를 적용한 좌표다. 기본 표면 표본 간격과 UAS reference voxel은 각각 0.1m, seed는 0이다.

Precision은 예측 표면 표본 중 관측 UAS 점까지의 거리가 임계값 **미만**인 비율이다. Recall은 관측 UAS 점 중 예측 삼각형 표면까지의 거리가 임계값 미만인 비율이다. F1은 두 비율의 조화평균이다. 같은 ROI의 UAS 2,325,976개 중 voxel 선택된 572,214개를 기준으로 하며, raw 표면 표본은 Anchor 654,344개, SfM 534,044개다. 따라서 precision의 표본 분모와 예측 면적은 조건별로 다르다. 이 값들은 관측 UAS에 대한 근접도를 측정하며, UAS 공백이 있는 곳의 시간적 진실을 확정하지 않는다. [원 측정 JSON][raw-metrics] · [평가 코드][geometry-code]

`512`라는 표기뿐 아니라 **실제 TSDF의 물리 크기도 지역 내 두 조건에서 같다.** 학습 카메라에서 유도된 반경으로 `depth_trunc`가 정해지고 `voxel_size=depth_trunc/512`, `sdf_trunc=5×voxel_size`가 된다. P2의 실제 두 로그는 voxel 0.5044786537268449m, depth truncation 258.29307070814457m, SDF truncation 2.5223932686342243m로 일치한다. P1/P3 voxel은 각각 약 0.338623/0.306729m다. 0.25m 평가 임계값은 셀 크기보다 작고 특히 P2에서는 약 절반이므로 이 지표는 추출된 표면의 표현 제약과 함께 해석해야 한다. 셀 크기를 절대 정확도 하한으로 보거나 F1을 Gaussian 자체의 품질과 동일시하지 않는다. 앞의 RGB는 이 TSDF mesh가 아닌 저장된 Gaussian의 공식 렌더다. [기존 P2 추출 로그][p2-anchor-export-log] · [새 P2 추출 로그][p2-prefix-export-log]

| 거리 임계값 | Anchor raw F1 | SfM raw F1 | Anchor post F1 | SfM post F1 |
|---|---:|---:|---:|---:|
| 0.10m | 0.1692 | 0.0539 | 0.1702 | 0.0529 |
| 0.20m | 0.2903 | 0.1223 | 0.2831 | 0.1198 |
| 0.25m | 0.3303 | 0.1604 | 0.3188 | 0.1574 |
| 0.50m | 0.4651 | 0.3778 | 0.4376 | 0.3729 |
| 1.00m | 0.6188 | 0.6935 | 0.5701 | 0.6884 |
| 2.00m | 0.8170 | 0.9192 | 0.7448 | 0.9145 |

**0.25m에서는 precision과 recall이 모두 낮아졌다.** raw precision은 0.2953→0.1734, recall은 0.3747→0.1492다. 0.5m에서도 precision 0.4194→0.4039, recall 0.5219→0.3548이다. 관측 UAS에 가깝게 놓인 표면을 더 많이 확보했다고 볼 수 없고, 엄격한 기준의 recall 감소가 특히 크다.

**1·2m의 높은 F1은 recall 개선을 뜻하지 않는다.** raw 1m precision은 0.5523→0.7202로 높아지지만 recall은 0.7036→0.6687로 낮아진다. 2m도 precision 0.7287→0.9362, recall 0.9295→0.9029다. 이 범위의 F1 증가는 관측 reference에 크게 떨어진 예측 표본의 비중이 줄어든 쪽과 일치한다. 어떤 점이 실제로 삭제·유지·이동했는지의 전이를 이 집계표만으로 판정하지 않는다.

| 기본 0.1/0.1m 거리 통계, m | Anchor raw | SfM raw | Anchor post | SfM post |
|---|---:|---:|---:|---:|
| 예측 표면 → 관측 UAS 평균 | 1.496 | 0.826 | 1.462 | 0.758 |
| 예측 표면 → 관측 UAS p95 | 5.092 | 2.173 | 5.014 | 1.945 |
| 관측 UAS → 예측 삼각형 평균 | 0.719 | 0.970 | 1.269 | 1.093 |
| 관측 UAS → 예측 삼각형 p95 | 2.135 | 3.013 | 4.460 | 3.885 |
| 고정 ROI의 예측 면적, m² | 6,543.432 | 5,340.438 | 5,761.326 | 5,079.390 |

raw에서는 예측→UAS 평균·꼬리 거리가 줄고 UAS→예측 평균·꼬리 거리가 늘었다. 면적도 감소했지만 줄어든 면적 전체를 오류나 오래된 자산의 제거량으로 읽을 수 없다. post끼리의 UAS→예측 평균은 개선됐으므로 “모든 형태에서 모든 방향의 거리가 악화했다”는 설명도 맞지 않는다. 새 SfM 자체를 raw→post로 바꾸면 UAS→예측 평균은 0.970→1.093m로 커진다. 후처리도 별도 표면 변화이며 raw와 post를 섞어 주장하지 않는다.

원 [기하 비교 CSV][geometry-csv]는 180행이고 새 조건 60행을 포함한다. 표면 표본 0.05/0.1/0.2m 또는 UAS voxel 0.05/0.1/0.2m를 한 요소씩 바꾼 **고정된 다섯 설정 모두**에서 raw/post의 F1 변화 부호가 유지됐다: 0.25·0.5m는 감소, 1·2m는 증가. 이는 표본화 민감도 확인이며 독립 반복·신뢰구간·일반화 검정은 아니다.

## 4. P2 고정 단면에는 부유 성분 감소와 곡면 추종 손실이 함께 보인다

아래 그림은 같은 X=134m 및 Y=109m, 폭 0.5m의 고정 단면이다. 검은 점은 관측 UAS, 색은 예측 표면 표본에서 관측 UAS까지의 거리이며 2m에서 표시가 잘린다. 색만으로 해당 위치가 오류 또는 오래된 자산이라고 판정하지 않는다.

![기존 ALS Anchor 8k raw의 고정 단면][anchor-sections]

기존 Anchor의 X=134m 단면에서 Y≈90–112m에는 관측 UAS의 반복 곡선과 가까운 예측 표본이 보인다. 동시에 Y≈108–130m, Z≈−22…−24m에는 관측된 아래 표면과 분리된 넓은 상부 성분이 보인다. [원 단면 PNG][anchor-sections]

![역사적 SfM no-Anchor 8k raw의 동일 고정 단면][sfm-sections]

새 SfM 단면은 Y≈90–112m에서 곡선의 아래쪽 변화까지 따라가기보다 위쪽을 잇는 완만한 형태로 보인다. 기존의 넓은 상부 성분은 대부분 줄었지만 Y≈116–130m, Z≈−25m 부근의 작은 분리 성분과 다른 잔여 조각이 남아 있다. “깨끗해 보인다”와 “가까운 표면을 정확히 따른다”가 동시에 성립하지 않을 수 있는 관찰이다. [원 단면 PNG][sfm-sections]

이 해석은 직접 확인한 두 고정 단면의 시각적 관찰이다. 색의 전역 평균이나 대응점별 유지/삭제 증명으로 제시하지 않는다. 곡면 구간의 이동·누락과 부유 성분 감소가 F1 변화에서 각각 얼마를 차지하는지, 또는 삭제된 표면이 어느 시기의 자산인지도 아직 분해되지 않았다. 동일 좌표의 사진·관측 범위와 원 source membership을 함께 확인해야 국소 보존·수정의 근거가 된다.

## 5. P1도 RGB 개선과 표면 F1 감소가 함께 나타났다

P1도 고정 평가 사진 15/15장을 두 도메인에서 평가했고 실패는 0이다. 아래 RGB는 P2와 같은 사진별 단순 평균, 기하는 같은 기본 0.1/0.1m 표본화 정의를 사용한 **P1 고유의 고정 ROI**다. P2 점·면적 분모를 P1에 적용하지 않는다. [P1 RGB CSV][p1-render-csv] · [P1 기하 CSV][p1-geometry-csv]

| 지표 | ALS Anchor 8k | SfM no-Anchor 8k |
|---|---:|---:|
| 고정 투영 ROI PSNR, dB ↑ | 14.5845 | 17.1127 |
| 고정 투영 ROI SSIM ↑ | 0.3933 | 0.5378 |
| 고정 투영 ROI LPIPS, native [0,1] ↓ | 0.5614 | 0.4567 |
| 전체 사진 PSNR, dB ↑ | 16.6712 | 18.4081 |
| 전체 사진 SSIM ↑ | 0.4907 | 0.5572 |
| 전체 사진 LPIPS, native [0,1] ↓ | 0.5804 | 0.5131 |
| raw F1 @0.25m | 0.5060 | 0.2978 |
| raw F1 @0.5m | 0.6408 | 0.4839 |
| raw F1 @1m | 0.7448 | 0.6677 |
| raw F1 @2m | 0.8369 | 0.8468 |
| post F1 @0.5m | 0.6362 | 0.4567 |
| 예측 raw → 관측 UAS 평균, m | 0.9504 | 1.2710 |
| 관측 UAS → 예측 raw 평균, m | 0.7596 | 0.5904 |

P1 raw의 0.5m precision은 0.6164→0.4014, recall은 0.6673→0.6092로 모두 감소했다. 다만 UAS→예측 평균 거리는 개선됐다. P2와 달리 예측→UAS 평균은 커졌으므로, 두 지역을 묶어 “큰 편차가 모두 줄었다”라고 설명하지 않는다. P1의 2m raw F1은 소폭 증가하지만 post 2m F1은 0.8201→0.8116으로 감소한다. 표면 종류와 거리 범위를 명시해야 하는 결과다.

P1 첫 사진에서는 기존 Anchor 렌더의 광장을 가로지르는 긴 파란 대각선 띠가 새 SfM 렌더에서 줄고 일부 경계의 가는 선 성분도 덜 보인다. 새 결과의 나무·장비는 여전히 크게 흐리며, 두 결과 모두 원 사진의 포장 줄무늬와 작은 물체를 충분히 표현하지 못한다. 이 관찰은 고정 index 00000의 한 ROI에 한정하며 P1 전체의 개선·보존·시간적 정확성으로 확장하지 않는다. [P1 Anchor montage][p1-anchor-photo] · [P1 SfM montage][p1-sfm-photo]

P1 raw의 고정 단면도 두 조건을 직접 확인했다. X=−8m, Y≈−23…−5m, Z≈−37m의 관측 지면보다 높은 예측 표면은 기존 Anchor에도 이미 존재한다. 이를 새 SfM이 처음 만든 오류라고 부를 수 없다. 반면 기존 Anchor의 Y≈−5…6m에는 UAS Z≈−42m에 가까운 지면 표본이 이어지지만 새 SfM에서는 일부가 굴곡·상향 편차와 띄엄한 분포를 보인다. Y=−6m, X≈−10…3m에서도 새 결과의 중간 높이 곡면이 넓다. 이 관찰은 “기존에도 보였던 높은 표면이 새 결과에도 존재하고, 다른 일부에서 지면 근접을 잃는다”는 범위다. 두 실행의 동일 Gaussian 계보나 오류 원인, 과거 구조의 유래를 확인한 것은 아니다. [P1 Anchor 단면][p1-anchor-sections] · [P1 SfM 단면][p1-sfm-sections]

## 6. P3는 외벽 보완과 아래쪽 성분 증가가 함께 나타났다

| 지역 | 이 문서에 포함한 실제 근거 | 8k 정량 요약 상태 | 해석 범위 |
|---|---|---|---|
| P1 | prefix 검증·공식 export·RGB·기하·summary, 고정 첫 사진·단면 | **PREFIX8000_COMPARISON_READY** | 위 8k 개발 진단 |
| P2 | prefix 검증·공식 export·RGB·기하·summary, 고정 사진·단면 | **PREFIX8000_COMPARISON_READY** | 위 8k 개발 진단 |
| P3 | prefix 검증·공식 export·RGB·기하·summary, 고정 첫 사진·raw/post 단면 | **PREFIX8000_COMPARISON_READY** | 위 8k 개발 진단 |

P3는 사진 20/20장을 두 도메인에서 평가했고 실패는 0이다. bbox 평균 PSNR·SSIM·LPIPS는 위 통합 표처럼 개선됐다. 그러나 raw F1은 0.25m 0.5587→0.3596, 0.5m 0.7018→0.5543, 1m 0.8028→0.7190, 2m 0.8685→0.8300으로 낮아졌다. 0.5m raw precision 0.7029→0.5595와 recall 0.7006→0.5491이 함께 감소했다. [P3 기하 CSV][p3-geometry-csv] · [P3 RGB CSV][p3-render-csv]

평균 거리는 raw 예측→UAS 0.8970→0.9490m, UAS→예측 0.7597→1.2454m로 모두 커졌다. post의 예측→UAS는 0.8934→0.6611m로 줄지만 UAS→예측은 0.9099→1.3369m로 커졌다. post 1m에서도 precision은 0.7812→0.8005로 높아지나 recall은 0.7855→0.6891로 낮아진다. 새 post가 reference에서 먼 예측 성분을 덜 포함해도 관측 표면 전체의 근접도가 함께 회복된 것은 아니다. 고정 다섯 표본화 설정에서 raw F1은 여섯 임계값 모두 감소했다. post의 2m F1 변화는 설정에 따라 음·양이 달라져 그 작은 차이를 일관된 개선으로 주장하지 않는다.

P3 첫 사진에서 새 SfM은 기존 Anchor의 넓고 밝은 가로 띠가 줄고 노란색·파란색 물체와 청백색 기둥이 더 분명해 보인다. 두 8k 결과 모두 지붕과 포장의 촘촘한 줄무늬 및 나무 질감은 크게 흐리며, 새 결과에는 건물 쪽 경계가 물결처럼 휘어진 부분도 보인다. 이 bounding-box 영상은 P1과 주변 맥락이 겹치며, 모든 픽셀이 P3 목표 건물인 것은 아니다. 전경 물체의 외관 개선을 목표 건물의 구조 회복이나 시간적 정확성으로 바꾸어 읽지 않는다. [P3 Anchor montage][p3-anchor-photo] · [P3 SfM montage][p3-sfm-photo]

P3의 X=−40m, Y=−15m raw 단면에서는 Z≈−19…−27m 지붕 윤곽이 두 조건 모두 관측 UAS에 가깝다. 새 SfM은 Y≈5…6m, X≈−48m 및 −32m 부근에서 관측 UAS 외벽의 수직 분포에 가까운 표면이 더 많이 나타난다. 동시에 지붕 아래 Z≈−30…−43m에는 관측 UAS와 멀리 떨어진 추출 성분이 크게 늘었다. 외벽 보완 가능성과 관측되지 않은 내부·하부 성분의 증가를 함께 볼 수 있는 사례다. 내부 reference가 비어 있어 모든 빨간 점을 거짓 표면으로 확정하지 않으며, 위에서 내려다본 거리 지도에서 중첩된 아래 표면을 지붕 전체의 오류로 해석하지 않는다. [P3 Anchor 단면][p3-anchor-sections] · [P3 SfM 단면][p3-sfm-sections]

새 P3 post 단면에서는 지붕과 주된 외벽 윤곽을 유지하면서 raw의 많은 분산 성분이 줄었다. 그러나 X=−40m, Y≈−30…−20m, Z≈−30…−36m 및 Y=−15m, X≈−39…−34m, Z≈−35…−38m 부근에는 군집된 하부 층이 남는다. 후처리 뒤 깨끗해 보이는 정도를 새로운 지붕 최적화의 성과로 보지 않으며, 모두 제거됐다고 표현하지 않는다. [P3 SfM post 단면][p3-sfm-post-sections]

## 7. 같은 관측점에서도 새 근접과 근접 손실이 동시에 확인된다

기존 거리 배열의 reference ID·순서·XYZ byte가 같음을 검증한 뒤, **동일 관측 UAS 점**에서 Anchor 표면과 SfM 표면까지의 거리가 0.5m 미만인지 대조했다. 아래는 raw 표면의 네 상태다. “신규만 근접”과 “기존만 근접”은 관측점의 거리 상태 변화이며 유효 자산의 생성·철거 또는 실제 Gaussian 삭제를 뜻하지 않는다. 표본화·정합·거리 계산을 다시 하지 않았다. [여섯 고정 임계값·raw/post 전이 CSV][support-csv] · [동일 reference 검증 receipt][support-proof]

| 지역·reference 수 | 두 표면 모두 근접 | 신규만 근접 | 기존만 근접 | 두 표면 모두 범위 밖 | 순 근접점 변화 |
|---|---:|---:|---:|---:|---:|
| P1 · 246,125 | 122,814 | 27,119 | 41,417 | 54,775 | −14,298 |
| P2 · 572,214 | 108,089 | 94,934 | 190,573 | 178,618 | −95,639 |
| P3 · 908,677 | 369,039 | 129,959 | 267,619 | 142,060 | −137,660 |

세 지역 모두 새로 0.5m 안에 들어온 관측점이 있지만, 기존에 가까웠다가 새 결과에서는 범위 밖이 된 점이 더 많다. post의 순 근접점 변화도 P1 −32,886, P2 −70,065, P3 −112,654다. 따라서 보완이 전혀 없다는 설명도, 보완하면서 기존 근접도를 모두 유지했다는 설명도 맞지 않는다. 어떤 공간에서 이 상태가 생기는지의 지도와 원 사진은 평가 진단이며, reference가 관측하지 못한 자산의 유효성은 이 표에 들어 있지 않다.

![P2의 동일 관측점에서 0.5m 근접 여부가 바뀐 위치, raw/post][support-p2-figure]

이 지도의 빨간색은 **기존만 근접**, 초록색은 신규만 근접, 파란색은 두 표면 모두 근접, 회색은 두 표면 모두 범위 밖이다. 앞 단면의 연속 거리 색과 다른 범례다. P2에서 새 근접과 근접 손실이 서로 다른 위치에 분포하는 것을 볼 수 있으며, 수직으로 겹친 관측점은 XY 표시에서 중첩될 수 있다. 색을 시간적 유효성이나 건물 전체의 판정으로 해석하지 않는다. 동일 정의의 수정 완료 그림은 [P1][support-p1-figure] · [P2][support-p2-figure] · [P3][support-p3-figure]에 있고, 원 CSV/NPZ는 그대로 보존돼 있다.

## 8. 8k 보조 성공과 원 22k/30k 실패·진행 상태를 분리한다

P2의 원 선택 학습 `no_anchor_sfm_memory_recovery_P2_v2`는 `FAIL`, native exit −9로 닫혔다. 별도 커널 근거는 32GiB cgroup의 OOM kill을 확인했다. 이 실패는 보존하며 8k 결과가 있어도 전체 학습 PASS로 바꾸지 않는다. 다만 실패 전의 완전한 8k checkpoint·PLY가 엄격한 검증을 통과했고, 이후 별도 공식 export와 평가가 성공해 보조 결과를 제공할 수 있었다. [학습 실패 receipt][p2-train-receipt] · [자원 실패 근거][p2-resource-failure] · [8k 검증][p2-prefix-validation] · [비교 summary][p2-summary]

현재 계획의 22k/30k 및 추가 자원 복구 시도는 이 historical 8k와 분리한다. P1의 마지막 `no_anchor_sfm_gradient_memory_v3_P1`은 native exit 1, CUDA rasterizer backward OOM으로 닫혔다. 작업 관측상 마지막 완료는 10,608회이며 원 22k/30k 결과를 만들지 못했다. 실행 제한에 따라 더 이상의 P1 학습을 추가하지 않는다. [P1 마지막 실패 receipt][p1-final-failure] · [원 실패 로그][p1-final-log]

P2/P3의 마지막 자원 복구 시도는 이 문서 작성 시 진행 중이며 완료로 표시하지 않는다. 후속 결과가 생겨도 이 문서의 선택된 historical checkpoint를 새 시도의 8k로 바꿔 쓰지 않는다. CPU depth/Adam 상태 offload 등 자원 경로가 달라졌으므로 경과 시간 차이는 Anchor 단계 유무만의 순수 방법 속도가 아니다.

실제 [8k 비교 뷰어][viewer]에서는 지역을 고른 뒤 **③ 기존 ALS Anchor 8k와 ⑤ 역사적 SfM no-Anchor 8k**를 같은 위치에서 비교한다. ④ 기존 native 30k는 문맥용이다. raw/post 전환과 고정 단면을 확인하고, RGB 갤러리에서는 같은 사진 이름의 실제 사진·기존·신규 렌더를 대조한다. 3D의 높이색이나 소스색을 실제 RGB 텍스처로 해석하지 않는다.

발행된 profile의 실제 브라우저 검증은 `PASS_PREFIX8000_BROWSER_QA`이며 208개 검사, 9개 screenshot, 새 mesh 6개와 지역 RGB 갤러리 3개를 확인했다. 이는 실제 표시·원 binary 로딩·사진 연결의 기술 검증이며 재구성 품질 또는 과학적 판정의 PASS가 아니다. 기존 공유 앱·서비스와 원 manifest는 바꾸지 않았다. [브라우저 QA receipt][browser-qa] · [발행 manifest][viewer-manifest]

## 9. 현재 답할 수 있는 것과 남은 확인

**답할 수 있는 것:** 세 지역에서 초기 SfM으로 바로 refinement를 시작한 경로는 같은 8k의 Anchor 상태보다 평균 사진 일치도를 높였지만, 0.25·0.5m의 표면 F1은 낮아졌다. 같은 관측점에서 신규 근접도 확인됐으나 근접을 잃은 점이 더 많았다. P2에서는 큰 거리의 예측 성분이 줄고 일부 곡면 구간을 덜 따르는 모습이 함께 보였고, P3에서는 지붕 근접과 일부 외벽 보완을 유지하면서 아래쪽 성분도 늘었다. 따라서 충분성 판단에는 외관뿐 아니라 유효한 국소 구조를 얼마나 유지했는지가 함께 필요하다.

**아직 답할 수 없는 것:** 이 결과는 Anchor가 반드시 필요하거나 불필요하다는 단일 요인 결론, ROI 전체의 구조 보존, 오래된 자산의 올바른 제거, 현재 형상의 완전한 회복, 최종 수렴을 증명하지 않는다. 단일 seed 개발 결과이며 역사적 SfM의 전체 영상 전처리 영향도 남아 있다. 평가 reference는 학습·checkpoint 선택·설정 선택에 사용하지 않았다.

후속 작업은 이미 정한 비교를 완성하는 범위다. 실제로 제공되는 원 22k/30k 결과는 동일 512 raw/post 및 고정 사진으로 별도 비교하고, P1 미완료를 다른 상태로 대체하지 않는다. 이후 국소 분석을 할 경우, 지금 검증한 reference ID 전이를 곡면 구간·외벽·상부 분리 성분의 실제 표면 위치에 연결해야 보존 손실과 큰 편차 감소를 더 구체적으로 나눌 수 있다. 이 문서의 수치로 학습 설정을 선택하거나 새 실험의 파라미터를 정하지 않는다.

## 근거와 재현 범위

P1 summary SHA256은 `dd38faf810a1d2873297a606bd6fe1a52a0483c5f57b50d15585cd7777ccfa34`, P2는 `fc2afa1353be9003595642f9a4ff7bd87756e960696c9b5ae508222d5accde92`, P3는 `56768e7918305694c1fa61afec1d93e6bf483d98d00629feb1b2435767411788`이다. 고정 진단 계약은 `a312c4999ff590d757116dc0f4a90695020e3ac70130df24fdf6e02a0eb769f0`이다. 통합 표·사진별 대조 검증 receipt SHA는 `65360aac29a10a6d7eb1a868da3f841f46f81b11751457277f8a010a9f5fd999`, reference 전이 검증 receipt SHA는 `d8f703d07b7f938c33e3d15c6226f443c8fe2edb9a759d68cfb73126203ba5a1`이다.

비교 CSV와 JSON을 읽고 고정 행을 Docker CPU 2개/RAM 2GiB/네트워크 없음/GPU 없음으로 대조했다. 통합 표는 기존 측정값을 선택해 옮겼고 사진별 증감과 원 reference 전이는 저장된 값만 사용했다. 새 표면·거리 계산이나 학습은 하지 않았다. 표의 수치는 표시 자릿수로 반올림했으며 원자료가 정확한 값을 소유한다. 문서의 사진과 단면은 실제 저장 PNG를 직접 확인했다. [통합표 생성 스크립트·설정·명령·실행 로그][report-bundle]

[plan]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_PLAN_ko_v1.md
[policy]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/geogs_p1p2p3_v1/sfm_prefix8000_diagnostic_v1.json
[densification-audit]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/phd/geogs_p1p2p3_v1/SFM_NO_ANCHOR_DENSIFICATION_AUDIT_ko_v1.md
[counts]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_v1/resource_prefix8000_figure_v1/endpoints.csv
[render-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P2/R8000/render_comparison.csv
[render-per-image]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P2/R8000/new_render_per_image.csv
[fixed-photo]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/figures_fixed_photo_v1/P2/P2_fixed_photo00000_four_columns.png
[figure-receipt]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/figures_fixed_photo_v1/P2/receipt.json
[geometry-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P2/R8000/geometry_comparison.csv
[raw-metrics]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/geometry/P2/SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.raw/sample0.1_reference0.1.json
[geometry-code]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/geogs_p1p2p3_v1/evaluation/geometry.py:184
[anchor-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Pnative.anchor_512.raw.sections.png
[sfm-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/viewer/P2/SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.raw.sections.png
[p1-anchor-photo]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/anchor_512/montages/00000_fixed_prism_projected_bbox.png
[p1-sfm-photo]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/renders/P1/SFM_noanchor_D005_Pnative_PREFIX8000/refinement_only/montages/00000_fixed_prism_projected_bbox.png
[p2-train-receipt]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/no_anchor_sfm_memory_recovery_P2_v2/runs/P2/SFM_noanchor_D005_Pnative/receipt.json
[p2-resource-failure]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/resource_observations_sfm_final_v1/P2/20260909T170815170028144/resource_failure_receipt.json
[p2-prefix-validation]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/completed_prefix8000_v1/P2/validation/receipt.json
[p2-summary]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P2/R8000/receipt.json
[p1-render-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P1/R8000/render_comparison.csv
[p1-geometry-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P1/R8000/geometry_comparison.csv
[p1-final-failure]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/no_anchor_sfm_gradient_memory_v3_P1/runs/P1/SFM_noanchor_D005_Pnative/receipt.json
[p1-final-log]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/no_anchor_sfm_gradient_memory_v3_P1/runs/P1/SFM_noanchor_D005_Pnative/native.log
[p3-anchor-photo]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/anchor_512/montages/00000_fixed_prism_projected_bbox.png
[p3-sfm-photo]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/renders/P3/SFM_noanchor_D005_Pnative_PREFIX8000/refinement_only/montages/00000_fixed_prism_projected_bbox.png
[p2-anchor-export-log]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/extraction_resource_v3/primary/P2/D005_Pnative/auxiliary/anchor_512/render.log
[p2-prefix-export-log]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/completed_prefix8000_v1/P2/export/native.log
[p1-anchor-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.anchor_512.raw.sections.png
[p1-sfm-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/viewer/P1/SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.raw.sections.png
[p3-anchor-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.anchor_512.raw.sections.png
[p3-sfm-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/viewer/P3/SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.raw.sections.png
[p3-sfm-post-sections]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/viewer/P3/SFM_noanchor_D005_Pnative_PREFIX8000.mesh_512.post.sections.png
[combined-table]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/report_table_v1/comparison.csv
[combined-proof]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/report_table_v1/receipt.json
[paired-photos]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/report_table_v1/per_photo_comparison.csv
[paired-counts]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/report_table_v1/per_photo_direction_counts.csv
[p3-geometry-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P3/R8000/geometry_comparison.csv
[p3-render-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/summary/P3/R8000/render_comparison.csv
[support-csv]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/support_transitions_v1/support_transitions.csv
[support-proof]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/support_transitions_v1/receipt.json
[report-bundle]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/report_table_v1
[support-p1-figure]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/support_transitions_figures_v2/P1.transitions_0.5m.png
[support-p2-figure]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/support_transitions_figures_v2/P2.transitions_0.5m.png
[support-p3-figure]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/support_transitions_figures_v2/P3.transitions_0.5m.png
[viewer]: http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json&color=height
[browser-qa]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/qa/actual_v1/receipt.json
[viewer-manifest]: /media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/no_anchor_sfm_prefix8000_v1/profiles/viewer_v1/manifest.json
