# MVS depth 교체 실험 입력 준비와 첫 기술 실행

- task_id: `PHD-GEOGS-MVS-PGSR-v1`
- 기준 시각: `2026-09-14T14:32:09Z` / 한국시각 2026-09-14 23:32
- 상태: `INPUTS_PASS / INITIAL_GPU_PREFLIGHT_PASS / BACKGROUND_QUEUE_PENDING`
- scientific_verdict: null

입력 `inputs_v2` 준비와 첫 P2 100-step GPU 기술 검사가 통과했다. 본문 기준
시점의 백그라운드 본 실행 큐는 아직 시작하지 않았다. 입력 준비, 짧은 기술 검사,
30,000회 본 학습, 최종 기하 평가를 구분한다.

사용자가 선택한 범위는 기존 COLMAP depth, P1/P2/P3, prior 계수 `.005/.0005`,
native 보호다. 각 지역에서 `MVS 교체`와 `MVS + PGSR 방식 기하 loss` 두 방법을
두 계수로 실행하므로 신규 학습은 12회다. 기존 DA3 대조는 지역마다 두 계수의
2조건, 합계 6개를 재사용한다. 사용자는 백그라운드 완료와 최종 보고서 및 완료 후
데스크톱 알림을 요청했다. 이 요청을 큐의 실제 기동·완료로 해석하지 않는다.

## 입력 계보와 무결성

실제 payload는 [외부 resolver](../../../../artifacts/manifests/geogs_mvs_pgsr_v1.yaml)가
해결하는 다음 경로에 있다.

```text
../JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/
```

현행 설정은 [experiment_v2.json](../../../../configs/phd/geogs_mvs_pgsr_v1/experiment_v2.json),
정확한 바이트 복사본은 `inputs_v2/experiment.json`이다.

| 항목 | SHA256 |
|---|---|
| 설정과 정확한 복사본 | `3555f528c7b2c91941c4f9e4812bcf918351605ec6c793c272be7e42a8785c5c` |
| `inputs_v2/receipt.json` | `9c008994d4827a7f1401bd6d6f9fc77484ad88f49880759e63ad86087a98e475` |
| P1 `bindings.json` | `c8afb896b9e6a0cdee1921b49c46e97a3d0cb0c568dd2b37ddce9f592bc1d9d8` |
| P2 `bindings.json` | `64a9d28a22f1679bb63efeac22f91ba569f04c7bee674840638e4924b120cbdf` |
| P3 `bindings.json` | `e3e6adbab866418890fa2d2c57e64a53265232230d0e860a6500c623ce5fe8ac` |

`input_preparation_v2_attempt_20260914T142620Z_GSJ0dE/`는 고정 설정 복사본,
실제 Docker 명령, 로그, 실행 영수증과 source의 전후 SHA 검사를 보존한다.
준비 실행은 고정 Docker 이미지에서 CPU만 사용했고 원 저장소와 원 artifact를
읽기 전용으로 마운트했다. 쓰기는 신규 task namespace에 한정했다.
원 설정·preparer·loader의 실행 전후 해시가 일치했다. 준비 입력 크기는 약 861 MiB다.

| 지역 | train / evaluation 영상 | 복사·SHA 검증한 native depth | native 유효 픽셀 비율 중앙값 |
|---|---:|---:|---:|
| P1 | 98 / 15 | 98 | 76.72% |
| P2 | 57 / 9 | 57 | 74.43% |
| P3 | 137 / 20 | 137 | 78.46% |

총 292개 지역별 train 참조의 depth·RGB가 모두 존재하며 원 결박 해시와 일치했다.
지역 간 중복을 제외한 고유 train 영상은 184개다. 위 비율은 전체 영상 raster의
`finite && depth > 0` 비율이며 건물별 정확도나 변화부 피복률이 아니다.

RGB는 undistorted `PINHOLE` 1400×1013, native COLMAP geometric depth는
1024×741 `camera-Z(m)`다. train K/R/t는 원 COLMAP binary와 최대 절대 차이 0이며,
native K도 두 축의 실제 해상도 비율을 적용한 RGB K와 정확히 일치했다.
원 depth의 음수·0·비유한값을 유효 감독으로 쓰지 않는다. 정수 RGB ray를 native K로
옮겨 nearest 조회하고, 결손 채움·scale fitting·추정 confidence를 넣지 않는다.

## 첫 준비 실패와 v2 처리

`inputs_v1`은 P1의 한 카메라에 neighbor가 없어서 첫 gate에서 실패했다.
실패 위치는 `inputs_v1/P1/failed_neighbor_graph.json`, 실행 기록은
`input_preparation_attempt_20260914T142134Z_bh21n7/`이며 모두 보존했다.

문제는 모든 카메라에 다중 시점 loss를 강제하는 gate였다. v2는 기존 선정 조건
`광축 각도 <= 30°`, `baseline / reference median MVS depth <= 1`, 최대 8개를
그대로 유지한다. 입력만 사용한 45°/1.5 민감도 검토는 현행 선정에 채택하지 않았다.
현재 graph의 in-frame overlap은 실제 가시성이나 기하 정답 confidence가 아니다.
학습 중 별도의 유효성·가림 검사를 적용한다.

| 지역 | neighbor가 없는 카메라 | 처리 |
|---|---|---|
| P1 | `DJI_20241217084553_0100_D.JPG` | RGB·MVS·single-view geometry 유지, multiview skip 기록 |
| P2 | `DJI_20241217100056_0034_D.JPG`, `DJI_20241217102537_0021_D.JPG` | 동일 |
| P3 | `DJI_20241217102531_0018_D.JPG` | 동일 |

각 지역에는 선택된 다중 시점 후보가 존재하고 최대 degree는 8이다. 카메라별
부재를 감추거나 neighbor를 강제로 추가하지 않는다. 실제 preflight에서는 각 지역의
유효 multiview 표본과 활성 loss를 확인해야 한다.

## 소스와 같은 Anchor의 결박

부모 task는 `PHD-GEOGS-P1P2P3-v1`이며 원 source는 그 task의
`sources/GeoGS-state-camera-v1`이다. 신규 source는 현재 task의
`sources/GeoGS-mvs-pgsr-v1`에 별도로 준비했다. 원 GeoGS commit은
`db40c95c657ec03ff21c83cb99cf39f4e90247a6`, PGSR 참조 commit은
`de24f1a38b350387e8d8fe381b2cd70c1ae946e7`이다.

신규 `mvs_pgsr_source_provenance.json` SHA256은
`62b7b9d97ec48c82c5ef3783ccbde82dbdabd4ed62642efca9abe5224063afe3`이다.
부모·신규 implementation/payload 해시, helper 해시와 변경 허용 범위를 담는다.
공식 PGSR unbiased-depth renderer 전체 재현이 아니라 기존 GeoGS expected depth에
국소 평면·기하 loss를 이식한 개발 조건이다.

| 지역 | 부모 task 안의 complete Anchor8k 경로 | checkpoint SHA256 |
|---|---|---|
| P1 | `runs/P1/D005_Pnative/model/jbgs_complete/iteration_8000` | `c08a39aa2deb81b26dd4dd75d0be9e6bb5e150db503f9d422a05423388679274` |
| P2 | `runs_allocator_v2/P2/D005_Pnative/model/jbgs_complete/iteration_8000` | `91bc9ad74b115c37d4ae35ec4eb197832e730be165d36f52ebe4bb291f1ebcfd` |
| P3 | `runs_allocator_v2/P3/D005_Pnative/model/jbgs_complete/iteration_8000` | `3b0de04d99435e36d05ffca49951976352bd663192cce14e59f2bddb58bdf567` |

## 검증 상태와 남은 실행

통합 Docker CPU 검사 30개가 통과했다. native depth 형식·hash·camera-Z 재투영·결손,
기하 loss의 합성 평면·warp·gradient, source integration 계약을 검사했다.
고정 runtime image ID는
`sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`다.

첫 실제 GPU preflight는
`preflight/P2/mvs_pgsr_0.005/attempt.zWaYG9SA/receipt.json`이며
SHA256은 `3b77982dcb12a19d888789c0e981fe8384dde22c0d224956548f299eff5672f1`이다.
8000 complete Anchor의 model/optimizer/controller/camera order/stack/RNG/native 보호
복원이 모두 exact PASS였다. 8001–8100의 100 step을 실행해 exit 0, final iteration
8100, wall time 60.40초를 기록했다. 첫 step의 sv/mv/NCC 유효 표본은 각각
1,392,247 / 2,857 / 1,311개이며 세 기하 loss가 모두 유한하게 활성화됐다.
이 결과는 첫 기술 실행 증거이고 기하 정확도·현재성 개선이나 전체 matrix 완료가 아니다.

본문 기준 시점에는 남은 지역·방법 preflight, 신규 12회 본 학습, mesh 추출,
같은 참조점 ID의 보정·손상 비교와 최종 보고서가 남아 있다.
[run_queue.sh](../../../../scripts/phd/geogs_mvs_pgsr_v1/run_queue.sh)는 이 순서의
백그라운드 실행과 성공·실패 데스크톱 알림을 담당하도록 준비 중이다.
실제 background queue 기동은 별도 시작 영수증으로 확인한다.

역사 COLMAP MVS의 실제 생성 이웃과 producer binary는 완전히 복구되지 않았다.
지역 간 train/evaluation 역할이 겹치는 영상 25개도 있으므로 독립 held-out 결과를
주장하지 않는다. UAS/LoD 참조는 평가용이며 loss·neighbor 선정에 들어가지 않는다.
과학적 판정은 계속 `null`로 둔다.
