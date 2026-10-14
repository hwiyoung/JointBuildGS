# 2차원 가우시안 스플래팅 공식 구현의 원본, 바꾼 곳, 실행 환경

- 작업: PHD-MAIN-BASELINES-v1, 준비(발주문 v1.1, 5.1절 1~2번, 5.2절, 4절 2번과 9번)
- 날짜: 2026-10-15
- scientific_verdict: null

## 원본

| 항목 | 값 |
|---|---|
| 저장소 | `github.com/hbb1/2d-gaussian-splatting` |
| 커밋 | `f3e3b9fa67bbd1c75e05167ff37391d8dab2a678` (2026-08-25, "Merge pull request #253") |
| 하위 모듈 | `diff-surfel-rasterization` `e0ed0207b3e0669960cfad70852200a4a5847f61` (그 안의 `third_party/glm` `5c46b9c0`), `simple-knn` `f155ec04131cb579f53443a06879d37115f4612f` |
| 라이선스 | Gaussian-Splatting License(Inria, MPII). 비상업 연구와 평가에만 쓸 수 있다. 래스터라이저도 같은 라이선스다 |
| 고치지 않은 원본 | `SB/sources/2d-gaussian-splatting` (git 상태 깨끗함) |
| 어댑터를 붙인 사본 | `SB/sources/2d-gaussian-splatting-adapters-v1` (`.git` 없이 복사) |
| 파일별 sha256 | `source_manifest_v1.json` |

`SB` = `JointBuildGS-artifacts/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1`.

## 바꾼 곳 (발주문 4절 2번의 '입력을 읽는 자리'와 '기록을 남기는 자리'만)

diff는 `adapters_v1.diff`다. 고치지 않은 원본에 `patch -p1`로 붙이면 사본과 바이트까지 같아진다(10월 15일 확인).

| 파일 | 바꾼 것 | GeoGS 어댑터와의 관계 |
|---|---|---|
| `utils/camera_utils.py` | 카메라를 만든 뒤 `jbgs_camera_adapter.maybe_calibrate_camera`를 부른다. 장면 폴더에 `jbgs_calibration.json`이 있으면 그 K의 주점과 초점 거리를 투영 행렬에 넣는다 | 파일 전체가 GeoGS 어댑터 사본(`S1/geogs/source/GeoGS-official-adapters-v1`)과 바이트까지 같다. 두 공식 구현의 원래 파일이 같기 때문이다 |
| `jbgs_camera_adapter.py` (새 파일) | 주점 어댑터 | GeoGS 어댑터와 바이트까지 같다(sha256 `06510fab…`). 본 방법 포크 r14의 것과도 같다 |
| `scene/dataset_readers.py` | 환경 변수 `JBGS_SPLIT_JSON`이 있으면 `split.json`의 이름으로 학습과 평가 영상을 나눈다. 장면, 학습, 평가 영상 수를 한 줄 적는다 | 나누는 코드는 GeoGS 어댑터(r11)와 같고, 영상 수를 적는 한 줄만 더했다(기록) |

코드를 바꾸지 않고 맞춘 것:

- **처음 점.** 장면 폴더의 `sparse/0/points3D.ply`에 영상 점만 넣었다(`SB/scenes/twodgs`, 5.3절). 2차원 가우시안 스플래팅은 이 파일이 있으면 그대로 읽고 새로 쓰지 않는다.
- **`--data_device cpu`.** 공식 인자라 오류 없이 받는다. 다만 이 판의 `Camera`는 원래부터 영상을 CPU에 두고, `train.py`가 반복마다 GPU로 옮긴다. 이 인자는 알파 마스크의 자리만 정하는데, 이 JPEG에는 알파가 없다. 그래서 이 인자가 있든 없든 계산과 메모리 자리가 같다.
- **기록.** 공식 `train.py` 밖의 감싸개 `scripts/phd/main_baselines_v1/twodgs/train_record.py`가 값을 읽기만 하는 고리 넷을 단다(학습 영상 이름과 수, 1,000회마다 가우시안 수와 PyTorch 메모리, 마지막 렌더의 영상 이름, GPU 메모리 부족 때의 기록). 텐서를 바꾸지 않고 난수를 뽑지 않는다. 손실의 NaN은 호스트 실행기 `run_twodgs.py`가 진행 막대를 읽어 잡고 학습을 멈춘다(4절 10번). GeoGS 공식 구현을 돌린 고침 발주의 방식과 같다.

## Docker 이미지

| 항목 | 값 |
|---|---|
| Dockerfile | 저장소 바탕의 `Dockerfile.2dgs-official-v1` |
| 바탕 이미지 | `jointbuildgs:geogs-official-db40c95-v1` (`sha256:6886d5920db3dc7dc9176b235a8a9240ebaccd607440f09fd7da32c106f2aee6`) |
| 이미지 | `jointbuildgs:2dgs-official-f3e3b9f-v1` |
| 이미지 id | `sha256:b2be486e519c31364ff73fe0c64d439488f49f84d97e07a14e042acb9b505c82` (로컬 이미지라 레지스트리 digest는 없다) |
| 빌드 | 10월 15일 06:09:32~06:11:36(2분 4초, 하위 모듈 둘을 다시 빌드), 06:15:50에 `LD_PRELOAD` 한 줄을 더해 다시 빌드(앞 층은 모두 캐시, 1초) |
| 빌드 컨텍스트 | 고치지 않은 원본 `SB/sources/2d-gaussian-splatting`의 `submodules/` 둘 |
| pip freeze | `SB/prep/twodgs/detail/pip_freeze_2dgs_image.txt`, 바탕은 `pip_freeze_base_image.txt`. 다른 줄은 래스터라이저와 `simple-knn`이 깔린 자리 둘뿐이다 |

이미지 안에서 한 일:

1. 바탕 이미지의 `diff-surfel-rasterization`과 `simple-knn`을 지우고, 2차원 가우시안 스플래팅 원본의 두 하위 모듈을 다시 빌드했다(sm_86, `--no-build-isolation`).
   - 래스터라이저 e0ed020은 GeoGS가 쓴 것과 커밋도 원본 파일도 같다(`diff -r` 차 없음).
   - `simple-knn`은 GeoGS가 86710c2를, 2차원 가우시안 스플래팅이 f155ec0을 고정한다. 둘의 차는 `simple_knn.cu`의 `#include <cfloat>` 한 줄뿐이다(86710c2 "Compatibility"). f155ec0은 이 줄 없이도 CUDA 12.1과 gcc 11.4에서 빌드되었다. 그래서 고정된 판 그대로 썼다.
2. `ENV LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6`. 바탕 환경의 ICU 78이 시스템보다 새 C++ 런타임을 요구한다. 이 줄이 없으면 공식 `render.py`가 부르는 `utils/mesh_utils.py`의 import가 `CXXABI_1.3.15 not found`로 멈춘다(`train.py`는 이 줄 없이도 된다). 고친 GeoGS를 돌린 이미지(`geogs-official-db40c95-compat-v1`)와 고침 발주의 GeoGS 명령에 있던 것과 같은 설정이다. 파이썬 패키지는 바꾸지 않았다.

## README의 환경과 다른 점

README는 `environment.yml`로 환경을 만들라고 한다. 이 이미지와 다른 점은 아래가 전부다. 모두 바탕 이미지(GeoGS와 본 방법 포크가 쓰는 판)에서 온 것이고, 2차원 가우시안 스플래팅 코드는 바꾸지 않았다.

| 항목 | README(`environment.yml`) | 이 이미지 |
|---|---|---|
| Python | 3.8.18 | 3.10.20 (`/opt/geogs`) |
| PyTorch | 2.0.0 | 2.1.2+cu121 |
| torchvision, torchaudio | 0.15.0, 2.0.0 | 0.16.2+cu121, 2.1.2+cu121 |
| CUDA | 적혀 있지 않음(PyTorch 2.0.0의 conda 꾸러미) | 컴파일러 12.1.105, cuDNN 8.9.2, sm_86 |
| open3d | 0.18.0 | 0.19.0 |
| mediapy | 1.1.2 | 1.2.6 |
| scikit-image | 0.21.0 | 0.25.2 |
| tqdm | 4.66.2 | 4.67.3 |
| trimesh | 4.3.2 | 4.12.2 |
| pillow | 10.2.0 | 12.2.0 |
| typing_extensions | 4.9.0 | 4.15.0 |
| pip | 23.3.1 | 26.1.1 |
| lpips | 0.1.4 | 0.1.4 (같음) |
| plyfile, opencv-python | 판 없음 | 1.1.3, 4.8.1.78 |
| ffmpeg | 4.2.2 | 없음. 공식 `render.py`의 영상 만들기에만 쓰이고, 이 발주는 그 길을 쓰지 않는다 |
| matplotlib | 판 없음 | 3.10.9. `utils/general_utils.colormap`이 3.10에서 없어진 `tostring_rgb`를 쓰지만, TensorBoard가 있을 때의 이미지 기록에서만 불린다. TensorBoard는 README 환경에도 이 이미지에도 없어서 불리지 않는다 |
| TensorBoard | 없음 | 없음(같음). `train.py`는 "Tensorboard not available"을 찍고 표준 출력에만 기록한다 |

## 저장소 규칙과의 관계

저장소 규칙 6은 이 저장소의 구현에 gsplat을 쓰라는 것이다. 2차원 가우시안 스플래팅 공식 구현은 비교 방법으로 그대로 돌리는 남의 구현이고, 래스터라이저 `diff-surfel-rasterization` e0ed020은 GeoGS와 본 방법의 포크가 이미 쓰는 것과 같다(발주문 4절 9번).
