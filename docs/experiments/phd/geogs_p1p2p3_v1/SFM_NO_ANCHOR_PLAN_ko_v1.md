# SfM 초기화에서 Anchor를 생략한 GeoGS 비교

2026-09-09 · `PHD-GEOGS-SFM-NO-ANCHOR-v1` · `scientific_verdict: null`

사용자는 SfM 초기 Gaussian에서 Anchor 없이 바로 refinement를 수행하고 기존 결과와 비교하도록 요청했다. 이 문서는 새 학습 결과를 보기 전에 고정한 실행 계획이다. 기존 실험·서비스·소스·뷰어를 보존하며 새 payload는 기존 task의 `no_anchor_sfm_v1/`에만 쓴다.

## 비교 질문과 해석 범위

기존 ALS 표면 초기화+Anchor8000+refinement22000을 SfM 초기화+refinement-only로 대체해도 현재 표면·관측 세부·외관을 회복하고 필요한 구조를 보존하는가? 이 비교는 **초기화와 Anchor 단계를 함께 바꾸는 대체 경로 검사**다. Anchor만의 단일 요인 효과로 해석하지 않는다.

| 조건 | 초기화 | Anchor | refinement 감독·보호 | 저장·평가 |
|---|---|---:|---|---|
| 기존 D005_Pnative | 동일 ALS 파생 표면 | 8000 | ALS 깊이 .005, DA3 동적 감독, native 보호 | 기존 final30000 재사용 |
| 기존 D0005_Pnative | 동일 ALS 파생 표면 | 8000 | ALS 깊이 .0005, 나머지 동일 | 기존 final30000 재사용 |
| 신규 SFM_noanchor_D005_Pnative | 실제 SfM 점군 | 0 | ALS 깊이 .005, DA3 동적 감독, 초기 SfM의 ALS 근접 Gaussian에 native 보호 | 연속 30000 중 22000·30000 |

22k는 기존 refinement의 명목 반복 수를, 30k는 기존 전체 명목 반복 수를 맞춘다. 신규 경로는 학습률·SH 증가·normal 활성화·densification이 1부터 시작하므로 기존 8001부터의 일정과 다르다. `position_lr_max_steps=30000`을 고정하고 한 궤적의 22k prefix를 평가한다. 22k에서 압축한 별도 일정을 사용하지 않는다. 원 코드의 마지막 iteration optimizer 처리도 그대로 유지하고 실제 업데이트 수는 기록한다.

## 입력과 구현

- 공식 commit `db40c95c657ec03ff21c83cb99cf39f4e90247a6`에 기존 상태·카메라 계측이 추가된 확보 source를 복사한다. 원 loss/model/renderer/extractor를 보존한다.
- 기존 regional `scene/sparse/0`은 점이 없는 렌더용 placeholder다. 실제 입력은 고정 camera_root의 `sparse/points3D.bin` (SHA256 `bf93766e9773bdc59ce393cf1a36de4b3801cadc1bf834ea705396f5e9a706c3`)에서 만든다. 이미 scene-local metric이므로 좌표 shift를 재적용하지 않는다.
- 기존 context crop 안에서 지역 학습 영상의 track 관측이 2개 이상인 점을 사용한다. 점 수 cap이나 결과에 따른 추가 필터를 적용하지 않는다. 원 point ID, track 수, 제외 사유, 좌표·RGB 출처와 SHA를 기록한다. SfM 위치·색·카메라는 역사적 전체 영상 전처리 계보이며 독립 확증 분할로 주장하지 않는다.
- 현재 영상·카메라·1400×1013 해상도·split·DA3 입력·ALS 깊이·보호점은 원 byte를 유지한다. UAS와 평가용 기하는 입력 준비·학습·정합·설정 선택에 마운트하지 않는다.
- `stage_switch_iter=0`만 지정하면 upstream의 단계 전환 이벤트가 발생하지 않아 보호 등록도 빠진다. 새 adapter가 첫 optimization 전에 원 matching/gradient attenuation/frozen-mask helper를 한 번 호출한다. 그 수와 첫 step의 ALS/DA3 가중치를 기록한다. ALS Gaussian은 추가하지 않는다.
- 초기 Gaussian·optimizer는 새로 생성하며 기존 Anchor checkpoint를 복원하지 않는다. ALS 감독과 보호가 남으므로 image-only라 부르지 않는다. seed0과 기존 allocator revision을 사용한다.

## 실행·평가·완료

P2부터 실행하고 자원 여유에서 P1을 병렬 실행하며 다음으로 P3를 수행한다. Docker image ID는 원 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, 각 GPU 프로세스 CPU8·RAM32GiB, 최대2개다. 학습 전 input·source·설정 봉인과 첫 step 제어 검사를 수행한다. 각 지역 22k/30k를 공식 경로로 렌더·512 TSDF 추출하며 raw와 post를 모두 보존한다.

기존 고정 영역·0.1m 표면 표본/참조 voxel·거리 임계값·평가사진/ROI를 유지한다. 예측→UAS 및 UAS→삼각형 거리, precision/recall/F1 민감도, 실제 렌더 PSNR/SSIM/LPIPS, 시간·메모리를 기록한다. Gaussian 중심점을 최종 표면으로 평가하지 않는다. 원 baseline512 표와 동일 estimand에서 비교하고 1024 수치를 섞지 않는다.

새 조건을 별도 viewer manifest에 연결하고 같은 시점의 prior/MVS/Anchor/기존/신규/UAS, 고정 단면·거리 지도·실제 사진/렌더를 제공한다. 전역 평균과 수정·보존·관측 부족 위치를 함께 분석한다. 실패와 편차, 원자료 CSV/arrays, 최종 분석·인계를 남긴다. 단일 seed 개발 결과로 Anchor 불필요·소스 교체 필요·반복 판단 필요를 확정하지 않는다.
