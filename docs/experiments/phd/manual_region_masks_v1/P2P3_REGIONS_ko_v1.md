# P2/P3 수동 depth 가중치 영역 — 2026-09-15

`task_id: PHD-P2P3-MANUAL-REGIONS-v1`  
`scientific_verdict: null`  
상태: 입력 영역도 생성 및 배열 검증 완료. P2/P3 학습 실행 없음.

## 결과와 범위

각 대상의 기준 RGB 2장을 직접 확인해 폴리곤을 지정했다. 현재 native MVS와
prior depth를 함께 확인했으며, **prior–MVS 차이에 임계값을 적용해 자동 분류한 결과는 아니다.**
R1은 가중치 변화에 대한 반응을 확인할 대상 표면이다. 실제 변화, MVS 정답,
prior 오류 또는 Gaussian 제거 명령을 뜻하지 않는다.

| 구분 | P2 | P3 | 시험용 배율 |
|---|---|---|---|
| R1 | 반복 아치 구조와 바깥 지붕을 포함한 대상 지붕 | 긴 곡면 지붕과 관측된 전면 외벽 | 0 / 1 / 4 |
| R2 | R1 밖에서 지정한 건물 표면 | R1 밖에서 지정한 건물 표면 | 1 |
| R3 | 수동 확인한 정적 포장 지면 | 수동 확인한 정적 포장 지면 | 1 |
| R4 | 차량·수목·이동 장비 등 제외 대상 | 차량·수목·이동 장비 등 제외 대상 | 0 |
| R5 | 미분류·경계·판단 유보·결측 | 미분류·경계·판단 유보·결측 | 0 |
| R6 | 현재 유효 XYZ가 설정 범위 밖 | 현재 유효 XYZ가 설정 범위 밖 | 0 |

R1–R4가 의미적으로 판단한 영역이며, 전체 raster 분할을 완성하기 위해 R5/R6를
별도 기록했다. 미분류 공간을 임의로 건물 또는 지면에 포함하지 않는다.
각 영상에 네 종류가 모두 존재해야 하는 것은 아니다. 예를 들어 P3 경사 기준뷰에는
확실히 지정한 R3가 없어 0표본이다. 연결통로·영구 지붕 구조물은 제외 대상이 아니며,
R1 후보 영역 안의 건물 표면이면 R1, 그 밖에서 지정된 건물 표면이면 R2가 된다.

## 기준 영상과 관측 차이

| 대상 | train index | 기준 영상 | 최종 R1 native 표본 |
|---|---:|---|---:|
| P2 | 10 | DJI_20241217091247_0146_D.JPG | 176,727 |
| P2 | 4 | DJI_20241217091131_0108_D.JPG | 163,790 |
| P3 | 119 | DJI_20241217103041_0046_D.JPG | 255,178 |
| P3 | 4 | DJI_20241217084717_0142_D.JPG | 35,361 |

P2는 대상 지붕의 native MVS 표본이 많은 수직뷰를 선택했다. P3는 외벽이 연속적으로
관측되는 경사뷰와 위에서 지붕·주변을 확인할 수 있는 수직뷰를 함께 선택했다.
P3 수직뷰의 반사성 지붕은 MVS가 크게 결손돼 있다. 유효값이라는 이유만으로
정확한 깊이라고 판정하지 않으며, 결측 보간·scale fitting을 하지 않았다.
표본 수 차이는 보이는 표면·가림·투영 면적 차이도 포함하므로 정확도 비교가 아니다.

## 전체 영상과 멀티뷰 전파

- P2: train 57장 전부 생성, R1 표본 존재 14장.
- P3: train 137장 전부 생성, R1 표본 존재 74장(100 RGB 표본 이상은 67장).
- 각 영상에서 native 1024×741, 실제 RGB 1400×1013 마스크를 모두 저장했다.
- 전파는 현재 native MVS, 실제 K/R/t, camera-Z 깊이 차이 ≤0.5m,
  왕복 재투영 거리 ≤2 native px를 사용했다. 이 수치는 진단용 설정이며 보정된 confidence가 아니다.
- 수동 기준뷰는 자신의 분류를 우선한다. 다른 뷰에서 건물/지면 충돌 또는 제외 관측이
  대응되면 R5로 유보한다. 기준뷰의 R4는 분홍색으로 보존하고, 다른 뷰의 제외 veto는
  R5 및 별도 `exclusion_veto` 배열에 기록한다. 양쪽 모두 배율 0이다.
- 원본 depth 결측, source 경계 2px, target 경계 1px 및 depth 불연속 주변은 유보한다.
- 원래 평가 ROI만 잘라 쓰는 마스크가 아니다. 수동으로 지정하고 대응이 확인된 표면 중
  기존 학습 context 안인 부분을 사용한다. context는 P2 x[85,183], y[61,157], z[-90,80],
  P3 x[-85,5], y[-67,37], z[-90,80]의 기존 local frame이다. 새 gravity 추정은 하지 않았다.
- evaluation 카메라와 UAS/LoD2 평가 형상, GS 학습 결과로 폴리곤이나 가중치를 고르지 않았다.

## 도면과 실제 사용 정책

뷰어: `http://127.0.0.1:8910/app/manual_regions.html`

기준 영상 도면에는 RGB, **전체 native MVS**, 전체 영역 분류도, α=0/1/4의 실제
배율 배열을 별도 패널로 표시했다. native MVS의 파란색은 깊이 색이다.
가중치 패널은 진회색 0, 초록 1, 주황 4로 읽는다.
뷰어에서 모든 학습뷰를 선택할 수 있으며, 기준 영상 2쪽 PDF와 전체뷰 PDF도 제공한다.

이 작업은 입력 마스크 초안이다. P1의 진행 중 학습/후처리를 바꾸지 않았고,
P2/P3 optimizer에 연결하지 않았다. 멀티뷰 전파 영상 전체의 픽셀별 수동 검수나
의미 분류 정확도를 주장하지 않는다. 현재 저장된 시험 배율은 R1만 바꾸며,
후속 학습에서는 대상 카메라 집합과 loss 분모 등 실행 조건을 별도로 고정해야 한다.

## 재현과 검증

입력은 기존 `geogs_p1p2p3_v1`의 P2/P3 RGB·prior와 `geogs_mvs_pgsr_v1/inputs_v2`의
동일 train membership/native MVS를 사용한다. 원본은 좁은 read-only mount로 접근했다.
정본 config: `configs/phd/manual_region_masks_v1/p2_v1.json`, `p3_v1.json`.
P2 현재 config는 `annotation_revision: 2`이며 이전 시도를 보존한다.

Docker CPU 실행:

```bash
bash scripts/phd/manual_region_masks_v1/run_inspection.sh P2
bash scripts/phd/manual_region_masks_v1/run_inspection.sh P3
bash scripts/phd/manual_region_masks_v1/run_region.sh P2
bash scripts/phd/manual_region_masks_v1/run_region.sh P3
# 각 result/receipt.json 생성 후
bash scripts/phd/manual_region_masks_v1/run_review.sh P2
bash scripts/phd/manual_region_masks_v1/run_review.sh P3
```

각 attempt에 source/config snapshot, commit, Docker image ID, 명령, 로그, 입출력 SHA256,
버전을 기록했다. publication 경로는 새로 만드는 방식으로 원래 결과를 덮어쓰지 않는다.

- 기하·가림·결측·분류 우선순위·건물 후보 opt-in 회귀 검사: Docker 16개 PASS.
- 내보낸 배열 388개(native/RGB × 194뷰), 출력 해시 1,781개 검증 PASS.
- 전체 픽셀 R1–R6 분할, boolean dtype, invalid/outside/unknown 배율 0,
  R1 후보 지지, native→RGB 샘플링과 기존 depth loader 일치 확인.
- 이는 소프트웨어와 출력 일관성 검증이며, 복원 성능·의미적 정확도의 판정이 아니다.
- 실제 Docker Chromium 17개 검사 PASS: P2/P3 네 기준 영상, 전체뷰 선택과 전파 영상,
  PDF 접근, 390px 화면, 브라우저·네트워크 오류 0개. 증거는
  `browser_qa.FK8ki4Kw/receipt.json`과 desktop/mobile PNG다.
- P1 기존 학습·후처리·마스크 파일 목록 `training_unchanged.sha256` 재검증 PASS.

## Payload resolver

외부 루트 `../JointBuildGS-artifacts/phase-payloads/phd/manual_region_masks_v1/PHD-P2P3-MANUAL-REGIONS-v1/`:

| 역할 | P2 | P3 |
|---|---|---|
| 입력 점검 | inspect.P2.Qn3aLga2 | inspect.P3.w4bEb3UQ |
| 채택한 전체뷰 마스크 | annotation.P2.fur6lKVS | annotation.P3.5CQlJP1P |
| native 도면 및 독립 검증 | review.P2.EuYjocmS | review.P3.keaol6t3 |

P2 이전 `annotation.P2.VB6hd6dQ`는 차량 경계 보완 전 시도로 보존한다.
뷰어용 사본은 기존 `geogs_mvs_pgsr_v1/.../viewer_rgb_v1/p2p3_manual_regions_v1/`에 있으며,
`publication.json`이 도면/배열/문서의 SHA256과 원본 검증 receipt를 연결한다.
