# R1 MVS–GeoGS와 DA3–GeoGS 하늘 차이

2026-09-18, 기존 입력·저장 렌더만 읽는 진단. `scientific_verdict: null`.
학습 또는 TSDF 결과를 바꾸지 않았다.

## 후속 확인: prior 0의 하늘 소실은 뷰어 잘림

2026-09-18 후속 원본 감사에서 prior0의 같은 하늘 표본은 깊이 중앙값
**66.131m**, TSDF 거리 이내 **279,886/402,500픽셀**이었다. 원영상 GT 배열의
동일성도 세 조건에서 확인했다. MVS 대조군의 68.854m와 비슷하며, prior0가
하늘을 제거하거나 DA3처럼 원거리로 보냈다는 근거가 아니다.

기존 MVS 표시는 local Z `[-90,80]`, 새 prior0/DA3 표시는
`[-81.285965,-1.835385]`여서 비교가 불일치했다. prior0 원본 메쉬의 R1 XY 안에
기존 상한보다 높은 정점 815,473개가 존재하며 최대 Z는 72.100m다.
publisher v5는 같은 `[-90,80]`으로 신규 cache를 생성한다. Z06의 낮은 플로터는
이 잘림과 별개다. 자세한 검증은 `sky_crop_audit_20260918/receipt.json`과
`viewer/crop_validation_v5/receipt.json`에 있다.

아래의 DA3 하늘 깊이 분석은 저장된 원본 depth에 근거하며 그대로 유효하다.
prior0가 DA3와 같은 이유로 하늘을 없앴다는 해석으로 확장하지 않는다.

## 확인한 표본

기존 R1 하늘 진단의 동일 영상 `DJI_20241217101349_0027_D.JPG`, train index 370,
동일한 `[100,50,1250,400]` 직사각형 402,500픽셀이다. 원영상과 두 추출 GT PNG의
RGB 배열이 정확히 일치한다. 두 조건은 같은 Anchor8k에서 시작했다.

| 대상 | 양수·유한 픽셀 | 깊이 중앙값 | TSDF 최대 거리 이내 |
|---|---:|---:|---:|
| MVS 입력 depth | 2 | 28.219m (2픽셀만) | 2 |
| DA3 입력 depth | 402,500 | 363.229m | 0 |
| 공통 Anchor8k 렌더 depth | 402,500 | 60.906m | 402,500 |
| MVS–GeoGS 30k 렌더 depth | 402,500 | 68.854m | 266,976 (66.33%) |
| DA3–GeoGS 30k 렌더 depth | 402,500 | 366.177m | 0 (0%) |

공통 TSDF depth truncation은 116.636m다. 이 픽셀 수는 추출 가능한 거리 조건을
통과한 ray 수이며, 실제 메쉬 삼각형 수 또는 개별 삼각형의 기여 ray 추적 결과가 아니다.

## 왜 이런 차이가 생기는가

1. MVS 입력에서는 이 하늘 영역에 depth 감독이 거의 없다. RGB loss는 그대로
   작동한다. 하늘 쪽 유한 Gaussian 렌더 깊이는 공통 Anchor에서부터 있었다.
2. 사용한 DA3NESTED 모델 자체에 하늘 판별과 원거리 깊이 대입이 있다. pinned
   `model/da3.py`의 `_handle_sky_regions`는 metric branch의 sky prediction을 쓰고,
   비하늘 depth의 99% 분위수와 200m 중 작은 값을 sky에 대입한다. 이후 입력 카메라
   scale alignment로 최종 깊이 단위가 다시 조정되므로 저장 depth가 항상 200m인 것은 아니다.
3. 실제 저장된 R1 DA3 입력은 표본 전체에서 약 363.229m로 거의 일정하다. GS의
   최종 하늘 depth도 244.019–517.806m로, 표본 전체가 TSDF 범위 밖이다.
4. 따라서 이 표본에서 하늘이 메쉬에 나타나지 않는 경로는 **하늘에 대한 원거리
   depth 감독 → 최종 렌더 depth의 원거리 이동 → 공통 TSDF 최대 거리 밖**으로
   설명된다. 하늘 Gaussian 또는 RGB 하늘 표현 자체가 삭제됐다는 뜻은 아니다.

우리 코드에 별도 sky mask를 추가하지 않았다는 기존 기록은 유지된다. 다만 DA3
모델 **내부의 sky 처리**는 원래 존재했으므로 두 입력이 배경을 다루는 방식은 다르다.
DA3 confidence를 별도 loss weight로 사용한 결과는 아니다.

이 수치는 한 장의 사전 검토 하늘 표본에 대한 직접 관측이다. 전체 R1 하늘 면적,
건물 면의 정확도, 건물 주변 모든 노이즈의 원인 또는 DA3 우월성으로 일반화하지 않는다.
하늘 처리만의 인과 효과를 분리하는 ablation은 실행하지 않았다.

## 자료와 구현

- [같은 픽셀 비교 그림](http://127.0.0.1:8913/data/review/R1/R1_sky_comparison.png)
- [수치·입력 hash](http://127.0.0.1:8913/data/review/R1/sky_comparison_receipt.json)
- DA3 pinned source: <https://github.com/ByteDance-Seed/Depth-Anything-3/blob/3d835ec1a5802d64a8b8b15f817a1ab54809bfe4/src/depth_anything_3/model/da3.py#L418>
- 실행: attempt의 `sky_comparison_20260918_v2/command.json` 및 `config.json`.
- 소스: `scripts/phd/r1r5_comparison_v1/audit_r1_sky_comparison.py`.
