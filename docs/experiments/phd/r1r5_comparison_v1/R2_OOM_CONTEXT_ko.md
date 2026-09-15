# R2: 작은 영역에서 CUDA OOM이 발생한 실행 맥락

- 확인일: 2026-09-18. `scientific_verdict: null`.
- 기존 로그·설정·카메라만 읽는 CPU Docker 감사. 신규 학습 0회.
- artifact: 활성 attempt의 `r2_memory_context_20260918/receipt.json`.
- 재현: `scripts/phd/r1r5_comparison_v1/audit_r2_memory_context.py`, artifact의
  script snapshot/config/Docker command/provenance.

## 1. ROI 면적과 실제 학습량

R2는 객체축 기준 140×75m이고 입력 기하 준비에는 25m context buffer를 쓴다.
그러나 선택된 train 221장은 각 1400×1013 전체 영상으로 학습한다.
`regional_loss_mask=false`이며, 실행된 `train.py`의 RGB L1/SSIM 계산에도
지역 마스크가 없다. 한 iteration에 한 영상을 처리하므로 221장이 동시에
GPU에 올라간다는 뜻은 아니다. 지도의 ROI를 줄였다고 각 iteration의 렌더
해상도나 배경 RGB loss가 같이 줄어들지는 않는다.

성공한 R2 MVS 대조군도 기록된 최대 allocated GPU 메모리는 18.228GiB였다.
실패한 국소 prior0의 마지막 진행 기록은 2,340,642 Gaussian이다. 지도 면적만으로
가벼운 렌더라고 볼 수 없는 실행 규모다.

## 2. 세 실패가 같은 카메라 차례로 좁혀짐

완료된 MVS 대조군과 각 실패 실행의 **모든 기록된 iteration의 camera**가 일치한다.
기록도 8,001회부터 마지막까지 연속이다. 그 다음 카메라를 대조군에서 읽으면
세 실패 모두 `DJI_20241217101311_0008_D`다.

| 실행 | 마지막 완료 camera 기록 | 대조군에서 추적한 다음 회차 | 다음 카메라 |
|---|---:|---:|---|
| DA3 최초 실행 | 14,745 | 14,746 | `101311_0008_D` |
| DA3 allocator 변경 재시도 | 14,862 | 14,863 | `101311_0008_D` |
| 국소 prior0 | 14,745 | 14,746 | `101311_0008_D` |

이는 **실패 전 camera 순서와 성공 대조군으로 추론한 실패 카메라**다.
관측 wrapper는 loss 계산과 optimizer step 이후 camera를 기록하므로, 실패한
render 시작의 camera를 직접 기록한 증거와 구분한다. 원영상 bytes는 split
manifest SHA256과 일치한다. 원영상은 가까운 건물 전경과 먼 도시·하늘을 함께
보는 사선 영상이다. 이 외관만으로 큰 projected footprint를 입증하지 않는다.

같은 영상은 실패 이전에도 반복 처리됐다. DA3 재시도는 14,746회에서 이 영상을
통과하고 다음 방문에서 실패했으며, MVS 대조군은 전체 학습을 통과했다.
따라서 영상 파일 자체의 항상 발생하는 오류로 해석하지 않는다.

국소 prior0의 해당 영상 mask는 **해제 픽셀 0개**다. 여기에만 적용하는 mask
계산이 거대 임시 버퍼를 직접 만든 것으로 설명할 수 없다. 다른 관측에서의
개입이 누적된 모델 상태에 영향을 주었을 가능성과 실행 수치 차이는 별개다.

## 3. 코드에서 확인한 메모리 경로

`forward.cu`는 각 Gaussian의 projected bounding radius와 덮는 image tile 수
`tiles_touched`를 계산한다. `rasterizer_impl.cu`는 그 합 `num_rendered`에
비례하는 Gaussian–tile 목록과 정렬 buffer를 만든다. 따라서 메모리는 Gaussian
총수 외에도 특정 카메라에서의 화면상 크기·중첩에 의존한다. 같은 Gaussian이
여러 tile에 걸치면 목록에 반복해서 들어간다.

국소 prior0는 이 rasterizer forward 안에서 20.29GiB 추가 할당에 실패했다.
당시 allocated 4.32GiB와 합치면 24.61GiB로 device limit 23.56GiB를 초과한다.
DA3 재시도는 allocated 22.81GiB인 상태에서 SSIM의 추가 16.23MiB 할당에
실패했다. 구체적인 할당 sub-buffer나 primitive별 기여량은 당시 계측하지 않았다.

Gaussian clone/split의 실제 크기 경계도 확인했다. R2는 카메라 분포에서 정한
extent 290.155m × `percent_dense=.01` = 2.902m다. R3/R4/R5는 각각
2.847/2.984/2.926m로 비슷하다. 이 값은 Gaussian 최대 크기 제한이나 최소
재구성 해상도가 아니며, 이번 R2만의 실패 원인으로 단정할 수 없다.

## 4. 결론과 남은 확인

- **확인:** 전체 영상 학습, 수백만 Gaussian, GPU 메모리 초과.
- **범위를 좁힌 증거:** 세 실패가 동일 카메라 차례로 추적됨.
- **아직 미확인:** 실패 직전 어떤 Gaussian의 projected footprint가 얼마나
  커졌는지, learned geometry와 renderer 수치 계산 중 무엇이 이를 유발했는지.
- 세 실패 폴더에는 입력 PLY만 있고 실패 직전 refinement PLY/checkpoint는 없다.
  완료 결과나 공통 8k Anchor를 실패 직전 상태로 대체해 진단할 수 없다.
- 후속 재현에는 해당 camera의 render **직전** iteration/name, projected radius,
  tile count와 메모리 요청을 남기는 계측이 필요하다. 이번 감사에서는 재학습,
  해상도·densification 변경, 카메라 제외를 실행하지 않았다.
