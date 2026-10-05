# R1 하늘 표면 진단 — 2026-09-17

- 범위: 기존 checkpoint·렌더·입력·추출 구현의 읽기 전용 진단. 새 학습·메쉬 수정 없음.
- `scientific_verdict: null`
- 문제: R1 MVS–GeoGS RGB 메쉬에 하늘색의 넓은 면이 보임.
- 상태: **관측·구현 경로 확인 / 수정 미실행**. 표본에서 TSDF 이전의 유한 sky depth가 확인됨. 개별 mesh triangle의 모든 기여 ray를 추적한 것은 아님.

## 1. 실제 표면 생성 경로

봉인된 native `render.py`는 학습 카메라의 Gaussian `surf_depth`와 렌더 RGB를 Open3D `ScalableTSDFVolume`에 넣고 `fuse.ply`를 만든다. 뷰어 publisher는 이 raw mesh를 R1으로 잘라 표시한다. 하늘 사진을 배경으로 붙이는 skybox는 없으며 viewer background는 단색 `#14202d`다.

현재 TSDF 설정은 voxel 0.22780491385323318m, SDF truncation 1.1390245692661658m, depth truncation 116.63611589285539m다. 후처리 `fuse_post.ply`는 큰 연결 성분 50개를 유지하는 처리이며 의미적 하늘 분리가 아니다.

`utils/mesh_utils.py:168-169`는 카메라 `gt_alpha_mask`가 있을 때만 배경 depth를 0으로 바꾼다. `utils/camera_utils.py`는 입력 영상의 네 번째 채널을 이 마스크로 읽는다. 확인 영상은 RGB JPEG이며 alpha가 없다. 렌더링된 `rend_alpha`는 계산되지만 저장·추출 필터로 사용되지 않는다. 추출에는 native MVS 유효성 마스크도 적용되지 않는다.

학습 `train.py:851-852`의 RGB L1/SSIM은 전체 영상에 적용된다. depth loss의 유효 픽셀 조건은 각각의 입력 depth 존재 조건이다. 따라서 MVS depth가 비어 있는 하늘에도 RGB 학습은 작용하며, MVS 유효 depth가 없다는 사실만으로 하늘의 Gaussian 렌더 depth가 제거되지는 않는다.

## 2. 동일 픽셀 표본으로 확인

영상 `DJI_20241217101349_0027_D.JPG`, 정렬된 train index 370, 1400×1013. 저장된 GT RGB와 원본 JPEG의 픽셀 배열을 직접 비교해 일치함을 확인했다.

원영상에서 사람이 확인한 하늘 전용 직사각형 `[x0,y0,x1,y1]=[100,50,1250,400]`, 402,500픽셀이다. 이 직사각형은 진단 표본이며 training mask·자동 분류 결과로 사용하지 않는다.

| 표본 내 depth | 양수·유한 픽셀 | 깊이 정보 |
|---|---:|---|
| 입력 prior | 0 | 관측 없음 |
| 입력 MVS | 2 | 28.219m, 하늘의 두 양수 값도 정확한 기하라는 뜻이 아님 |
| Anchor8k Gaussian 렌더 | 402,500 | 45.58–77.19m, 중앙값 60.91m |
| 최종30k Gaussian 렌더 | 402,500 | 중앙값 68.85m; 266,976픽셀(66.33%)이 최종 TSDF 최대 거리 이내 |

초기 1–8k에는 MVS 계수가 0이다. 따라서 하늘의 유한 렌더 depth는 MVS refinement 이전부터 존재하며, 이 현상을 MVS 계수 또는 prior 0.005의 단독 결과로 귀속할 수 없다. TSDF가 무에서 하늘 depth를 만든 설명도 배제된다. RGB 표현을 위한 유한 깊이의 배경 기하가 마스크 없이 표면 추출로 들어가는 경로와 일치한다. RGB·정규화·초기화 각각의 인과 기여 비율은 이번 검사로 측정하지 않았다.

## 3. 대응 제안

1. 원본 대조군 mesh와 checkpoint는 보존한다.
2. 하늘 제외 mask를 현재 RGB에서 만들고 실제 의미·경계를 검토한다. 하늘색만으로 판별하면 파란 지붕·유리·그림자를 오분류할 수 있다.
3. 별도 TSDF 파생본에서 하늘 ray를 제외해 출력 영향을 분리한다. 모든 후보에는 동일한 배경 제외 규칙을 적용한다. alpha threshold만으로 의미적 하늘을 분리했다고 주장하지 않는다.
4. 향후 학습 비교에서는 RGB loss에서 하늘을 제외하거나 별도 배경 모델로 표현하는 조건을 공통으로 통제한다. 이미 학습된 Gaussian에 대한 TSDF mask만으로 모든 sky artifact가 제거된다고 보장할 수 없다.

위 대응은 제안이며 아직 실행하지 않았다. 하늘의 대상 제외는 건물 표면에서 prior/MVS 중 어떤 관측을 믿을지 판단하는 문제와 구분한다.

## 4. 재현·증거

- script: `scripts/phd/r1_mvs_control_run_v1/audit_sky.py`
- config: `configs/phd/r1_mvs_control_run_v1/sky_view370_v2.json`
- Docker image: `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`; CPU 2, memory 4GiB, network none, GPU 미사용.
- 원래 실행의 commit·입력·모델·소스 계보는 본 workstream resolver를 따른다.
- payload: 활성 attempt 아래 `sky_audit_20260917/view370_v2/`; config, 실행 source, 입력 hashes, 수치 receipt, `sky_rgb_depth.png` 보존.
- 최종 30k와 Anchor8k extraction receipt 모두 PASS, recovery status `COMPLETE`. 이 표면 생성 성공은 정확한 건물 기하 또는 sky 제거 성공을 뜻하지 않는다.
