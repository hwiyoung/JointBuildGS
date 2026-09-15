# R1 Z06 렌더 기여 추적 및 R2 메모리 복구

- Task: `PHD-R1R5-COMPARISON-v1`, 2026-09-18 사용자 후속 지시.
- 범위: Z06 플로터를 만드는 실제 렌더 기여 추적, 실패한 R2 DA3/prior0 복구.
- `scientific_verdict: null`. 정규 E1–E6와 구분하는 ALS-adapted GeoGS 개발 진단이다.
- 외부 payload: 활성 attempt의 `causal_recovery_20260918/`(이하 B).
- 상태: 기존 R1 렌더의 직접 기여 확인 PASS; R2 복구 및 R1 대조 실행 진행 중.

## 1. 확인된 R1 직접 생성 경로

기존 prior0 최종 Gaussian PLY의 **0-based row 1816099**는 두 scale이
`2.99147m, 168.43472m`다. 이는 scale 매개변수이고 전체 지름을 뜻하지 않는다.
중심 XYZ는 `[-362.79742, 14.77425, -6.33242]`, 객체축 표시 좌표는
약 `[-110.20078, 345.97115, -6.33242]`로 R1 표시 XY 밖에 있다.
최종 protection은 false이며 opacity sigmoid는 float32 기준 1.0이다.

이 Gaussian은 Z06을 보는 픽셀에도 기여한다. 예를 들어 아래 첫 두 카메라에서
교차 깊이는 각각 15.61/17.62m, 최종 정규화 기여 비율은 15.72/21.32%다.
해당 깊이가 약 52–58m의 뒤쪽 지붕 기여와 섞여 expected depth를 카메라 쪽으로
끌어당긴다. 현재 TSDF 입력은 `depth_ratio=0`의 expected depth다.
따라서 Gaussian 중심이 플로터 위치에 없어도 그 공간에 융합 표면이 생길 수 있다.

실제 K의 principal point, native tile bounds, alpha/transmittance threshold,
surfel 교차 및 low-pass 경로를 사용해 선택한 3영상×3조건의 9개 depth를 CPU로
재합산했다. 저장 CUDA depth와의 최대 차이는 **0.000312m**다.
그다음 prior0의 해당 Gaussian만 제외하고 나머지 모든 ray 기여를 처음부터
재합산했다. 상위 기여 몇 개만 다시 정규화한 결과가 아니다.

| 카메라 / pixel (x,y) | 기존 MVS control | prior0 | prior0에서 해당 Gaussian 기여만 제외 |
|---|---:|---:|---:|
| DJI_20241217084721_0144_D / (617,566) | 58.39693m | 50.17112m | 56.61892m |
| DJI_20241217084851_0189_D / (33,717) | 52.16151m | 45.02006m | 52.44172m |
| DJI_20241217084551_0099_D / (1310,163) | 52.64209m | 48.55953m | 52.62088m |

위 세 픽셀 자체는 모두 prior 해제 mask 밖이다. 선택한 플로터 지지 ray에 대한
직접 기여는 확인했지만, 전체 모델에서 삭제 후 TSDF를 재추출한 것은 아니다.
원본 Gaussian, 학습 결과와 뷰어 메쉬를 수정하지 않았다.

증거:

- B/`r1_depth_trace_v2/depth_support.json`
- B/`r1_splat_trace_v2/receipt.json`
- B/`r1_splat_counterfactual/receipt.json`
- B/`r1_large_splat_state_v2/receipt.json`
- B/`r1_attribution_figure/Z06_floater_cause_20260918_v1.png`

이 결과는 이전의 '시선 교차로 연결될 가능성'보다 강한 **고정된 최종 모델의
렌더 기여 증거**다. 다만 그 Gaussian의 scale이 학습 중 언제, 왜 커졌는지는
기존 30k 결과만으로 확정하지 않는다. Z08 prior 해제를 원인으로 분리하는
대조 실행은 아래와 같이 실제 백그라운드 큐에 등록했다.

## 2. R2 복구 방법과 검증

실패와 연관된 `DJI_20241217101311_0008_D`에서 전체 해상도를 유지하면서
영상을 512행 단위로 나눠 rasterize한다. forward OOM이면 256/128행으로
줄인다. 다른 영상은 원래 렌더를 사용하며 forward OOM일 때만 같은 fallback을
적용한다. 입력 영상 제외, downsampling, scale 제한 또는 Gaussian 삭제는 없다.

조각의 RGB/depth/normal을 전체 영상으로 합쳐 원래 loss를 계산한다. backward는
PyTorch checkpoint로 조각별 forward를 재계산해 모든 조각의 binning buffer를
동시에 보관하지 않는다. pixel 좌표와 principal point를 유지하도록 투영을
보정하고 densification의 screen gradient 배율도 보정한다.

RTX 3090에서 12,000 Gaussian, 비중앙 principal point, 192×144 영상과
64행 조각의 native/분할 렌더를 비교했다.

- RGB 최대 절대 차이 `4.41e-6`, relative L2 `1.82e-7`.
- allmap 최대 절대 차이 `1.56e-4`, relative L2 `6.07e-7`.
- radii 동일; 여섯 gradient 군의 최대 relative L2 `3.43e-4`.
- 기준 `0.003` 이내로 `PASS_NATIVE_STRIP_OUTPUT_GRADIENT_PARITY`.
- 실제 prior 유지/해제 loss와 gradient 및 native branch 검사 3개 PASS.

이는 수치적 근사 동등성 검사이며 bitwise 동일성 또는 전체 학습 궤적의 동일성
보증이 아니다. 학습 camera membership/순서, 원본 depth, loss 계수, 전체 영상
loss, densification/pruning 설정, Anchor 완전 복원 및 30k 종료는 유지한다.
선정 카메라의 Gaussian별 큰 투영 반경, scale, tile-pair 수와 메모리를 기록하고
14,745/14,862/15,000/30,000 checkpoint를 남긴다.

검증: B/`raster_validation_v2/receipt.json`, B/`driver_validation_v2/receipt.json`.
실행 script/config/hash/Docker command는 각 출력과 B/`source/`에 보존한다.

## 3. 실제 백그라운드 큐

독립 서비스: `jbgs-r1r2-causal-recovery-20260918.service`.
기존 R4/R5 작업 종료 후 동일 scheduler lock을 인계받아 실행한다.
이 서비스는 대화 종료와 독립적으로 진행한다.

| GPU | 순서 | 조건 |
|---|---|---|
| 0 | 1 | R2 local prior0, 분할 메모리 복구 |
| 0 | 2 | R1 matched keep, 같은 mask 경로에서 내부 배율 1 |
| 0 | 3 | R1 matched release, 같은 mask 경로에서 내부 배율 0 |
| 1 | 1 | R2 DA3, 분할 메모리 복구 |

R1 짝은 같은 GPU 0, allocator, source snapshot, 완전 Anchor, camera 순서에서
실행하며 12k/15k/20k/25k/30k checkpoint와 해당 관측 pixel depth를 남긴다.
해제 마스크 밖의 배율은 두 조건 모두 1이다. 이 첫 짝지은 비교를 여러 seed의
반복 실험 또는 통계적 인과 효과 증명으로 간주하지 않는다.

R2는 각각 preflight/30k 학습/TSDF 추출이 통과해야만
`execution/artifact_overrides.json`을 갱신하여 기존 뷰어에 게시한다.
R1 추가 대조는 원래 뷰어 조건을 덮어쓰지 않고 진단 산출물로 유지한다.
과거 실패 디렉터리와 로그는 보존하고 새 실패도 별도 receipt에 기록한다.

진행: B/`status.json`, `execution/status.json`.
완료: B/`R2_<branch>_memory_recovery_20260918_receipt.json`,
B/`R1_local_prior0_matched_<keep|release>_20260918_receipt.json`,
B/`r1_pair_summary/receipt.json`.

## 4. 진단 중 실패와 한계

- 최초 ray replay는 FoV 중심을 가정해 실제 K principal point를 누락했고 CUDA
  depth와 최대 약 22m 차이가 났다. 해당 v1은 원인 증거에서 제외한다.
  calibration adapter와 일치시킨 v2를 사용한다. 최초 로그/출력은 보존했다.
- 최초 large-splat checkpoint 검사는 torch 2.1의 mmap이 Path 객체를 거부해
  실패했다. 문자열 경로로 바꾼 v2가 통과했다. 최초 실패 로그는 보존했다.
- R2 복구의 성공 여부는 실제 30k 및 TSDF receipt로 판정한다. 사전 렌더 검사
  PASS를 R2 전체 복구 완료로 표시하지 않는다.
