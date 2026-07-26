# issues — 20260726_fusion_w1_aprime

판정 필드는 두지 않는다. 상태, 수치, 예외, 처리만 누적한다.

## FUS-W1-APRIME-ATTR-001 — prior 가중치 귀속 정정

- Recorded: 2026-07-26 21:00 KST
- Status: RECORDED BEFORE A′ RESULTS
- `lambda_db=0.5`, `lambda_nb=0.05`는 GS4Buildings 논문 수치가 아니다.
  논문은 prior weight를 공개하지 않고 2단계 scheduling과 “2DGS hyperparameters
  unchanged”만 적는다. 본 run의 실출처는 depth `0.5`의 CityGaussianV2와
  normal `0.05`의 DN-Splatter 계열 범위(`0.05~0.1`)다. 15k split,
  10배 endpoint 감쇠, α estimator도 이식판 사전등록 선택값이다.

## FUS-W1-APRIME-SMOKE-A-001 — 기존 arm A 지붕 opacity 붕괴와 readout 소멸

- Recorded: 2026-07-26 21:00 KST
- Status: PRESERVED OBSERVATION; A′ 판정 미사용
- 대상: `DEBY_LOD2_42364609`, arm A r1, 30k.
- 기존 full-state의 지붕 geometry proxy에서 opacity 중앙값은 init `0.25`,
  5k `0.00293739`, 10k `0.00269597`, 15k `0.00265593`, 30k
  `0.00265546`이고 모든 checkpoint에서 `opacity>0.5`는 0개다.
- collapse는 distortion 활성 15k보다 앞선 5k부터 관찰된다.
- T4의 정본 궤적 CSV·그림·receipt는
  `runs/20260726_fusion_w1_aprime/preflight/T4/`에 보존한다. 같은 arm A에서
  누적 prune 후보가 모두 보호되어 실제 prune이 0이었던 현상은 아래
  `FUS-W1-APRIME-PROTECT-001`의 보호 역설 기록과 연결한다.
- 기존 alpha-point readout은 25,433점을 만들었으나 분류 class count가
  `{1:2188, 2:23245}`, footprint 내부 class 6이 0, roof density가 0이었다.
  관련 원 산출물과 실패 receipt는 `runs/20260724_fusion_w1/`에 그대로 보존한다.

## FUS-W1-APRIME-PROTECT-001 — seed protection 제거

- Recorded: 2026-07-26 21:00 KST
- Status: PREREGISTERED CONFIG CHANGE
- 기존 arm A의 누적 prune 후보 `10,589,306`개가 모두 seed-lineage 보호되어
  실제 prune 0개였다. A′는 GS4B의 무보호/default dynamics에 맞춰
  `seed_protect=false`, `surface_seed_protect=false`로 고정한다.
- arm A에서는 낮은 opacity가 pruning을 대행하지 못한 채 보호된 lineage에
  잔류한 병목이 관찰됐으므로, A′에서는 opacity·pruning의 기본 결합을 복원한다.
  이는 보호 제거 사유의 기록이며 결과 판정 문장이 아니다.
- 보호 코드는 삭제하지 않고 config에서 off한다. seed 잔존/opacity/prune은
  관찰 로그일 뿐 intervention에 쓰지 않는다.

## FUS-W1-APRIME-T2-IMPLEMENTATION-001 — 기존 `tsdf` 명칭 경로는 실제 TSDF가 아님

- Recorded: 2026-07-26 21:00 KST
- Status: COMPLETED BEFORE A′ TRAINING ENTRY
- 기존 `tum_mob_tsdf_extract.py`는 surface depth 역투영, voxel consensus, SOR로
  점군을 만드는 경로이며 TSDF volume이나 Marching Cubes mesh를 만들지 않는다.
- Open3D ScalableTSDFVolume + Marching Cubes triangle mesh 추출 경로를 구현했고,
  기존 arm A checkpoint 리허설 receipt를 발행했다. 정본 receipt는
  `preflight/T2/t2_tsdf_rehearsal_receipt.json`, SHA-256은
  `6ef49bba0e9cc93251717cf104ab9ec4543402542998857194da08da7bbeda0b`다.
  raw mesh는 12,860 vertices/18,607 triangles, filtered mesh는
  11,103 vertices/17,148 triangles, surface samples는 1,553점이다.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-001 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T12:30:25.699343+00:00`
- error_type: `TsdfReadoutError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2`
- message: `empty exact M_j: /workspace/JointBuildGS/phases/p2-gsjso/runs/20260724_fusion_w1/preprocess_v1/pose_28b38383a0b6d826/by_building/DEBY_LOD2_42364609/supervision/class6/DJI_20241217095139_0076_D.JPG.npz`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-T1-RUNTIME-FAILURE-001 — materialize 산출물 소유권 불일치

- Recorded: 2026-07-26 22:16 KST
- Status: FIXED BEFORE TRAINING COMPUTE; SAME-ERROR COUNT 1/3
- 대상: `DEBY_LOD2_42364609`, arm A′ r1, mini smoke.
- `materialize`가 Compose 기본 root로 run 디렉터리를 생성하여 호스트 launcher가
  `started.json`을 만들 때 `PermissionError`가 발생했다. iteration은 0회다.
- 래퍼의 materialize/check/queue 명령을 host UID:GID로 고정하고, 이미 생성된 T1
  preflight 디렉터리만 `1000:1000`으로 복구했다. 계산 산출물 삭제·덮어쓰기는 없다.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-002 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T12:31:25.161049+00:00`
- error_type: `TsdfReadoutError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2`
- message: `no integrable surf_depth inside M_j: DJI_20241217095123_0068_D.JPG`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-T1-RUNTIME-FAILURE-002 — 완료 계약 필드·초기 opacity 관찰 시점

- Recorded: 2026-07-26 22:52 KST
- Status: FIX IN PROGRESS; ERROR SIGNATURE COUNT 1/3
- 대상: `DEBY_LOD2_42364609`, arm A′ r1, mini smoke 600 updates.
- CUDA 학습은 return code 0으로 600 updates를 완료했고, 네 항의 후반부 양수
  loss/weight/weighted share/gradient 증거와 실제 prune 누적 429개를 저장했다.
- 완료 검증은 `effective_config.normal_schedule` 누락으로 `ContractError`를 냈다.
  trainer가 실행에 사용한 normal schedule을 로그에는 출력했지만 effective JSON에
  schedule/warmup/ramp/final weight 필드를 쓰지 않은 구현 누락이다.
- seed CSV의 iteration 0은 gsplat 기본 `step_post_backward(0)` opacity reset 뒤의
  관찰이라 configured 0.1이 아니라 `2*prune_opa=0.01`이었다. 역학은 변경하지 않고,
  전략 callback·optimizer update 전 실제 0.1을 별도 initialization receipt로 고정한 뒤
  CSV의 0.01을 post-dynamics 관찰로 유지한다.
- 실패 run 전체와 `failed.json`은 `r1` 경로에 보존하며 재시도 때 append-only archive로
  이동한다. 이 run은 T1 PASS나 학습 본선 진입에 사용하지 않는다.

## FUS-W1-APRIME-T1-RUNTIME-RESOLUTION-002 — T1 재실행 완료

- Recorded: 2026-07-26 22:56 KST
- Status: PASSED; PRIOR ERROR SIGNATURE REMAINS 1/3
- 대상: `DEBY_LOD2_42364609`, arm A′ r1, mini smoke 600 updates.
- T1 gate SHA-256: `075fe2b421222e7abd15ac276b0cdb59a80cf994219d714622ccbd60a9436b2b`.
- pre-dynamics opacity median `0.10000000149011612`; 첫 default reset 후
  post-dynamics median `0.009999998845160007`; 최종 관찰 iteration 575 median
  `0.0706343725323677`, seed-lineage 4,908개.
- cumulative prune candidate/actual `428/428`, protected `0`, protection active `false`.
- iteration 575의 depth·normal-prior·normal-consistency·distortion 모두
  raw loss, weight, weighted loss/share, gradient norm/share가 0보다 컸다.
- completed optimizer updates `600`, Docker return code `0`; scientific verdict 필드 없음.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-003 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T14:22:28.169467+00:00`
- error_type: `PermissionError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2`
- message: `[Errno 13] Permission denied: '/.cache'`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-004 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T14:27:10.077939+00:00`
- error_type: `RuntimeError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/preflight/T2`
- message: `Error building extension 'gsplat_cuda': [1/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output compute_sh_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/compute_sh_fwd.cu -o compute_sh_fwd.cuda.o
FAILED: [code=137] compute_sh_fwd.cuda.o
/usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output compute_sh_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/compute_sh_fwd.cu -o compute_sh_fwd.cuda.o
Killed
[2/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output proj_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/proj_fwd.cu -o proj_fwd.cuda.o
FAILED: [code=137] proj_fwd.cuda.o
/usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output proj_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/proj_fwd.cu -o proj_fwd.cuda.o
Killed
[3/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output quat_scale_to_covar_preci_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/quat_scale_to_covar_preci_fwd.cu -o quat_scale_to_covar_preci_fwd.cuda.o
[4/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output fully_fused_projection_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/fully_fused_projection_fwd.cu -o fully_fused_projection_fwd.cuda.o
[5/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output rasterize_to_indices_in_range.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_indices_in_range.cu -o rasterize_to_indices_in_range.cuda.o
[6/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output fully_fused_projection_2dgs_bwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/fully_fused_projection_2dgs_bwd.cu -o fully_fused_projection_2dgs_bwd.cuda.o
[7/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output fully_fused_projection_2dgs_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/fully_fused_projection_2dgs_fwd.cu -o fully_fused_projection_2dgs_fwd.cuda.o
[8/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output world_to_cam_bwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/world_to_cam_bwd.cu -o world_to_cam_bwd.cuda.o
[9/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output rasterize_to_pixels_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_fwd.cu -o rasterize_to_pixels_fwd.cuda.o
[10/26] /usr/local/cuda/bin/nvcc --generate-dependencies-with-compile --dependency-output rasterize_to_pixels_2dgs_fwd.cuda.o.d -DTORCH_EXTENSION_NAME=gsplat_cuda -DTORCH_API_INCLUDE_EXTENSION_H -DPYBIND11_COMPILER_TYPE=\"_gcc\" -DPYBIND11_STDLIB=\"_libstdcpp\" -DPYBIND11_BUILD_ABI=\"_cxxabi1011\" -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc -I/opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/third_party/glm -isystem /opt/conda/lib/python3.11/site-packages/torch/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/torch/csrc/api/include -isystem /opt/conda/lib/python3.11/site-packages/torch/include/TH -isystem /opt/conda/lib/python3.11/site-packages/torch/include/THC -isystem /usr/local/cuda/include -isystem /opt/conda/include/python3.11 -D_GLIBCXX_USE_CXX11_ABI=0 -D__CUDA_NO_HALF_OPERATORS__ -D__CUDA_NO_HALF_CONVERSIONS__ -D__CUDA_NO_BFLOAT16_CONVERSIONS__ -D__CUDA_NO_HALF2_OPERATORS__ --expt-relaxed-constexpr -gencode=arch=compute_86,code=sm_86 --compiler-options '-fPIC' -O3 --use_fast_math -std=c++17 -c /opt/conda/lib/python3.11/site-packages/gsplat/cuda/csrc/rasterize_to_pixels_2dgs_fwd.cu -o rasterize_to_pixels_2dgs_fwd.cuda.o
ninja: build stopped: subcommand failed.
`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-QUEUE-BINDING-001 — 정상 training completion의 receipt-shape 오분류

- Recorded: 2026-07-27 00:41 KST
- Status: RECOVERED WITHOUT PRODUCER RECEIPT REWRITE
- 대상: `DEBY_LOD2_42364609`, arm A′ r1, 30k smoke.
- training은 optimizer update `30,000`, return code `0`으로 끝났고 final checkpoint
  SHA-256은 `20e1e625b90487201e3574b102dbcc10d559b17ee1de59073b893fc71a0019b9`다.
- committed queue validator가 producer의 materialization record
  `{path, sha256}`를 자체 `file_record`의 `{path, sha256, bytes}`와 객체 전체 비교해
  `OrphanedTrainingAttempt`로 오분류했다. 실제 execution HEAD·method hash·checkpoint
  binding은 모두 일치했다.
- 정상 완료분 27개 artifact는 append-only `attempt_001` archive에 보존했다.
  잘못 시작된 두 번째 학습은 SIGINT 후 `KeyboardInterrupt` receipt와 함께
  `attempt_002`로 별도 보존했다.
- recovery controller는 비교 범위만 producer 계약의 `path+sha256`으로 좁혔다.
  원 producer receipt를 수정하지 않고 26개 유효 artifact를 canonical 경로로
  재수화했으며 orchestration 산출 `orchestrator_orphan_failure.json` 1개만 제외했다.
- controller receipt SHA-256:
  `dec660b29098a2e4d4665a8547bfd17d00a89856dbad0332a98c9a826ec3c363`.
  rehydration receipt SHA-256:
  `9baf96f3cc584824ef5c64df889432fd46a8e7235faef6bd63f46793e6545f52`.

## FUS-W1-APRIME-READOUT-RUNTIME-001 — 본선 TSDF non-root cache 권한 오류 3회

- Recorded: 2026-07-27 00:43 KST
- Status: TERMINAL STAGE STOP PER PREREGISTERED CATASTROPHE RULE
- 대상: `DEBY_LOD2_42364609`, arm A′ r1, primary TSDF readout.
- append-only readout attempt `001`~`003`이 모두
  `PermissionError: [Errno 13] Permission denied: '/.cache'`로 종료됐다.
  세 attempt의 readout error signature는
  `00fa59bf782c96a81dabb741788c22b6b7a650099188c3192adbf4a15e533012`로 같다.
- T2 rehearsal wrapper에는 run-scoped `HOME`/`XDG_CACHE_HOME`/
  `TORCH_EXTENSIONS_DIR` bind가 있었으나 본선 readout wrapper의 primary TSDF
  컨테이너에는 같은 non-root cache bind가 없었다. TSDF mesh·Roofer·CityJSON·score는
  생성 전 단계에서 중단됐다.
- 동일 오류 3회 규칙에 따라 smoke stage record는 `SKIPPED`, queue state는
  `STOPPED_SMOKE_BARRIER_NOT_MEASURED`로 발행됐다. 후속 stage는 orchestrator가
  시작하지 않았다.
- stage-stop SHA-256:
  `759569f0d5c3b33602e8f67fe3869a9007d936da6a438343cacd58412f7a0774`.
  queue complete SHA-256:
  `7a37c2ea41edd194169415335f1412408748c24b9f0741d09372b04383f0b1e3`.
- 본 항목은 실행 상태·오류·처리 기록이며 과학적 판정은 포함하지 않는다.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-005 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T15:42:23.312127+00:00`
- error_type: `PermissionError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout/by_building/DEBY_LOD2_42364609/arm_Aprime/r1/attempts/attempt_001/tsdf`
- message: `[Errno 13] Permission denied: '/.cache'`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-READOUT-ATTEMPT-001 — preserved attempt

- timestamp_utc: `2026-07-26T15:42:24.583959+00:00`
- job: `DEBY_LOD2_42364609/arm_Aprime/r1/attempt_001`
- stage: `primary_tsdf`
- error_type: `ExternalStageError`
- message: `wrapper stage exited nonzero: status=1`
- action: attempt artifacts and failure receipt retained; no verdict emitted.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-006 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T15:42:35.899020+00:00`
- error_type: `PermissionError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout/by_building/DEBY_LOD2_42364609/arm_Aprime/r1/attempts/attempt_002/tsdf`
- message: `[Errno 13] Permission denied: '/.cache'`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-READOUT-ATTEMPT-002 — preserved attempt

- timestamp_utc: `2026-07-26T15:42:37.165392+00:00`
- job: `DEBY_LOD2_42364609/arm_Aprime/r1/attempt_002`
- stage: `primary_tsdf`
- error_type: `ExternalStageError`
- message: `wrapper stage exited nonzero: status=1`
- action: attempt artifacts and failure receipt retained; no verdict emitted.

## FUS-W1-APRIME-T2-RUNTIME-FAILURE-007 — TSDF rehearsal/extraction exception

- timestamp_utc: `2026-07-26T15:42:48.793630+00:00`
- error_type: `PermissionError`
- output_dir: `phases/p2-gsjso/runs/20260726_fusion_w1_aprime/readout/by_building/DEBY_LOD2_42364609/arm_Aprime/r1/attempts/attempt_003/tsdf`
- message: `[Errno 13] Permission denied: '/.cache'`
- action: exception receipt and traceback retained; no verdict emitted.

## FUS-W1-APRIME-READOUT-ATTEMPT-003 — preserved attempt

- timestamp_utc: `2026-07-26T15:42:50.147113+00:00`
- job: `DEBY_LOD2_42364609/arm_Aprime/r1/attempt_003`
- stage: `primary_tsdf`
- error_type: `ExternalStageError`
- message: `wrapper stage exited nonzero: status=1`
- action: attempt artifacts and failure receipt retained; no verdict emitted.
