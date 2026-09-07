# GeoGS 학습뷰·평가뷰 RGB 진단

`PHD-GEOGS-MVS-PGSR-v1` · 2026-09-15 · `scientific_verdict: null`

사용자는 현재 surface 표시의 색 손실 여부와 논문 figure의 출력 종류를 확인하고,
동일 장면의 학습뷰·평가뷰를 원사진과 대조하도록 요청했다. 이 진단은 저장된
30k 결과만 읽으며 새 학습이나 파라미터 변경은 수행하지 않는다.

## 출력 종류와 확인된 코드 경로

현재 3D viewer의 mesh는 UV texture atlas가 아니라 **삼각형 정점 RGB**다.
`src/apps/geogs_rgb_comparison_v1/viewer.js`의 `loadObject`는 색을
`BufferGeometry`의 color attribute로 넣고 `MeshBasicMaterial(vertexColors=true)`로
표시한다. 삼각형 내부 색은 정점 사이에서 보간되므로 세밀한 사진 무늬를 별도
고해상도 texture image처럼 저장하지 않는다.

실제 동결 GeoGS `render.py`는 먼저 학습·평가 camera의 full-SH RGB를 내보낸 뒤,
mesh 추출에서만 `active_sh_degree=0`으로 바꾼다. `utils/mesh_utils.py`의
`extract_mesh_bounded`는 렌더 RGB/depth를 Open3D RGB8 TSDF에 적분한다.
따라서 여러 시점의 색 통합, mesh 정점의 공간 간격, 정점 색 보간 과정에서
세부가 손실될 수 있다. SH0는 시점 의존 성분을 제거하는 설정이며, 그 자체를
공간 저역통과 필터라고 설명해서는 안 된다.

이 사실은 **추출·표시 손실의 가능한 경로**다. 현재 색 손실의 크기나 주된
원인을 입증한 결과가 아니다. 저장된 full-SH RGB에도 흐림이 있으면 그 부분은
mesh 추출 이전부터 존재한다. 좋은 RGB가 정확한 기하를 보증하지도 않는다.

## 논문 figure 재확인

제공된 원문 PDF `1-s2.0-S0924271626003588-main.pdf`
(SHA256 `21342911a9f5db6aba9be155a1e06cb4d36d7a2e27780235acb111f8e91c28c4`)
전체 캡션과 Fig9/10 페이지 이미지를 확인했다.

| Figure | PDF 페이지 / 인쇄 페이지 | 출력 |
|---|---|---|
| 1 | 2 / 185 | 방법 개요와 2-view mesh 비교 |
| 7, 8 | 10 / 193 | 항공·지상 영상의 NVS RGB 렌더 비교 |
| 9 | 11 / 194 | TUM2TWIN Region5의 Gaussian 중심점·색 입힌 추출 mesh·M3C2 |
| 10 | 12 / 195 | egenioussBench Region1의 중심점·색 입힌 추출 mesh·M3C2 |
| 11 | 13 / 196 | 5-view NVS와 point-cloud 비교 |
| 12 | 14 / 197 | 추출 mesh M3C2 편차 |
| 13 | 14 / 197 | PSNR·mesh M3C2 추이 |

Fig9/10 mesh에도 창문·외벽 색이 표현된다. **논문의 좋은 텍스처가 전부
렌더뷰라는 설명은 틀리며**, 논문과 우리 결과의 차이를 출력 종류만으로
설명할 수 없다. 본문 §5.2는 TSDF mesh 추출을 기술하지만, 해당 figure의
색이 UV atlas인지 vertex RGB인지 또는 별도 원사진 재투영인지까지는
본문·캡션으로 확정하지 않았다.

논문: https://doi.org/10.1016/j.isprsjprs.2026.07.011

공식 구현: https://github.com/zqlin0521/GeoGS

PDF 읽기 도구는 고정 project Docker image 안의 임시 `pypdf==6.1.1`,
페이지 시각 확인 도구는 임시 `pymupdf==1.26.5`였다.

## 비교 계약

- P1/P2/P3 각각 학습 2장·평가 2장, 총 12 camera case.
- 결과를 보기 전에 고정 world-prism bbox의 영상 내 투영 면적 내림차순으로
  사진을 고른다. 동률은 파일명 순서다. UAS reference, 결과 RGB 오차,
  prediction alpha로 사진이나 crop을 고르지 않는다.
- 각 사진에서 DA3 / MVS / MVS+PGSR × prior .005 / .0005의 6조건을 비교한다.
  모두 보호 유지, final 30k이며 같은 원사진·camera·정수 pixel bbox를 사용한다.
- 저장된 full-SH RGB와 원사진 crop을 재표본화 없이 보존한다. 화면 맞춤 표시와
  원본 크기 100% 확대를 구분한다. 새 sharpness 보정이나 texture 합성은 없다.
- 원사진 SHA, exported GT와 원사진 pixel 대응, frozen camera membership,
  렌더 출처와 crop SHA를 실행 receipt에 기록한다.
- ROI PSNR와 공식 GeoGS SSIM을 계산한다. PSNR/SSIM은 RGB 복원 지표이며
  독립적인 표면 정밀도나 선명도 단일 지표가 아니다.

학습뷰는 RGB 학습에 사용했고 평가뷰는 RGB 학습에서 제외했다. 하지만 기존
COLMAP MVS의 최종 생성 membership이 미복구이므로 평가뷰를 MVS와 독립인
검증 자료로 주장할 수 없다. 각 split의 관측 방향·가림·해상도가 다르며 각
2장만 보므로 train/evaluation 점수 차이를 일반화 성능 추정으로 해석하지 않는다.

동일 장면에서 ALS↔LoD2만 바꾼 비교가 없으므로 ALS 출처를 흐림의 원인으로
확정하지 않는다. 틀린 geometry에 여러 영상의 RGB를 맞추는 충돌은 가능한
가설이지만 이번 RGB 비교만으로 카메라·가림·깊이 감독·보호·표현력 중 하나의
기여를 분리할 수 없다.

## 실행 결과: PASS, 원인 규명은 부분 완료

출력: `viewer_rgb_v1/rgb_diagnostic_v1/attempt.Ym5F9Uzs` (상위 MVS/PGSR
task artifact root 기준). 12개 camera case × 6조건 = 72쌍을 CPU Docker에서
322.21초 동안 분석했다. 원본 camera 336개의 COLMAP calibration과 split을
대조했고, 선택한 72쌍 모두 exported GT와 원사진의 전체 RGB 픽셀이 정확히
일치했다 (`max_abs_u8_delta=0`). 새 학습·렌더·기하 추출은 0회다.

Manifest SHA256:
`f2b338a0da04831a9eabd3abb0a69fab27b844a8ceb9874658b2c18a1246c70b`.

[비교 화면](http://127.0.0.1:8910/app/rgb_diagnostic.html) ·
[카메라·원본·렌더·계보 manifest](http://127.0.0.1:8910/data/rgb_diagnostic_v1/attempt.Ym5F9Uzs/manifest.json) ·
[72쌍 전체 수치](http://127.0.0.1:8910/data/rgb_diagnostic_v1/attempt.Ym5F9Uzs/per_case_metrics.csv) ·
[완료 receipt](http://127.0.0.1:8910/data/rgb_diagnostic_v1/attempt.Ym5F9Uzs/receipt.json).

**학습 카메라의 full-SH 렌더에도 이미 세부 손실이 있다.** P1 학습1의 바닥
줄눈·노란 차량·파란 물체는 원사진에서 선명하지만, .005 렌더에서도 일부 번짐과
뒤틀림이 보이며 .0005에서는 줄눈 대부분과 차량 세부가 사라진다. MVS의 해당
ROI SSIM은 .675→.502다. P1 학습2의 비스듬한 지붕에서는 많은 줄무늬가 남는다.
따라서 모든 위치·시점이 똑같이 흐린 것도, 평가 카메라에서만 실패하는 것도 아니다.

**P2에서는 큰 번짐 감소와 작은 무늬 복원이 분리된다.** 학습1에서 지붕의 큰
반복 구조와 일부 차량 모양은 남지만, 지붕의 작은 식생·입자 무늬는 렌더에서
줄어든다. 평가2 (`DJI_20241217091137_0111_D.JPG`)의 MVS .005에는 오른쪽
지붕을 덮는 큰 회색 번짐이 있다. .0005에서는 번짐이 줄고 지붕 윤곽이 나타나며
ROI PSNR 17.94→25.27 dB, SSIM .674→.751로 개선된다. 여전히 작은 무늬는
원사진보다 흐리다. 큰 오류 감소가 수치 개선과 함께 관찰되지만, 픽셀별 기여를
분해해 수치 증가 전체의 원인을 하나로 확정한 것은 아니다.

**P3에는 특정 평가 카메라의 큰 실패도 있다.** 평가2
(`DJI_20241217084723_0145_D.JPG`)에서 MVS .005의 저장 렌더는 ROI 대부분이
청회색 면으로 덮여 있다 (PSNR 10.20 dB, SSIM .307). 같은 사진의 다른 5조건은
PSNR 23.98–24.65 dB다. PNG 누락이나 viewer/crop 오류가 아니며, 원사진과
exported GT 대응이 정확하다. 무엇이 이 면의 실제 렌더 기여를 만들었는지는
아직 분리하지 않았다. P3 학습1의 건물 창·지붕 반복선은 상당 부분 남지만
작은 표면 무늬와 가려진 낮은 곳의 세부는 손실되어 있다.

아래는 각 split에서 **선택한 2장만의 ROI SSIM 평균**이다. 전체 평가 집단의
평균이나 일반화 성능 추정이 아니다. DA3/.005가 현재 viewer의 vanilla
(ALS 적용판)에 대응한다. PSNR과 사진별 값은 위 CSV에 모두 보존했다.

| 영역·사진 | DA3 .005 | MVS .005 | +PGSR .005 | DA3 .0005 | MVS .0005 | +PGSR .0005 |
|---|---:|---:|---:|---:|---:|---:|
| P1 학습 | .720 | .718 | .657 | .632 | .611 | .579 |
| P1 평가 | .653 | .652 | .596 | .597 | .584 | .547 |
| P2 학습 | .800 | .806 | .793 | .730 | .776 | .766 |
| P2 평가 | .730 | .700 | .689 | .724 | .747 | .734 |
| P3 학습 | .753 | .736 | .709 | .722 | .722 | .686 |
| P3 평가 | .684 | .527 | .659 | .662 | .664 | .637 |

현재 확인된 범위는 **표면 추출 이전의 RGB 복원 손실과, 일부 평가 시점에서
추가되는 큰 렌더 오류가 함께 존재한다**는 것이다. MVS나 PGSR 추가, prior
완화가 모든 위치의 RGB 세부를 일관되게 회복하지는 않는다. 이것만으로
ALS 출처, 잘못된 prior 유지, camera pose 또는 특정 loss를 단독 원인으로
선택할 수 없다. 학습뷰에서도 원사진을 충분히 복원하지 못한다는 사실은 확인했으며,
깊이·보호·가림·표현 자유도 사이의 인과 기여는 별도 검증 대상으로 남는다.

## 확인 가능한 구현과 화면

실행 driver/config: `scripts/phd/geogs_mvs_pgsr_v1/rgb_train_eval_diagnostic.{py,sh}`,
`configs/phd/geogs_mvs_pgsr_v1/rgb_train_eval_v1.json`.
Browser app: `src/apps/geogs_rgb_comparison_v1/rgb_diagnostic.{html,js,css}`.

기존 viewer의 상단에 학습뷰·평가뷰 RGB 비교 링크를 추가했다. 12장과 여섯 조건,
원사진을 선택할 수 있고, 1:1/200% 확대에서 사진·렌더의 스크롤을 동기화한다.
전체 영상 링크와 camera·file SHA·수치 manifest도 제공한다.

실제 CPU Chromium 검증도 PASS했다. 12개 case, 여섯 조건과 원사진 84개
PNG의 SHA/디코딩/크기, prior 필터, 100%/200% 확대와 scroll 동기화,
390px 모바일 표시를 포함한 373개 항목을 확인했다. 스크린샷은 5개다.
최종 receipt는 `rgb_diagnostic_v1/browser_qa/attempt.20260915T074105Z.eVPADQVf/receipt.json`,
SHA256은 `8553a4d6c958778a0208caf8f241b40be2742c9e370feeec18242df8bd4d0df4`다.
첫 PASS attempt의 스크린샷은 아래쪽 행이 화면 높이를 넘었으므로, 최종 검증에서는
두 가중치 행이 모두 보이는 전체 페이지 스크린샷을 추가했다. 프런트엔드 변경이나
데이터 재계산은 없었다. 100% 확대 스크린샷에서도 P2 vanilla의 큰 지붕 구조는
남지만 원사진의 작은 지붕 무늬가 사라진 것을 직접 확인했다.

Resolver: `artifacts/manifests/geogs_rgb_train_eval_diagnostic_v1.yaml`.
