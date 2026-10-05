# Wu–Vallet 원문·영상 입력·공간 이상점 제거 감사 v3

작성일: 2026-09-07. 범위: 기존 v2 실행의 읽기 전용 감사와 별도 SOR 진단. `scientific_verdict: null`.

**v2에서 큰 참조 편차를 가진 영상점이 추가된 결과를 곧바로 논문의 맹점으로 해석하면 안 된다. 작은 변화영역 정제와 최종 추가를 연결하는 구현 결함이 확인됐고, 영상점 생성도 원문과 다른 대체 입력이다.** 이 문서는 해당 차이와 일반적인 고립점 제거가 실제로 얼마나 작동했는지를 기록한다. 기존 실행·코드·산출물은 보존했다.

## 1. 논문에서 실제로 수행한 정제

출처: [Wu–Vallet 2026 공식 원문 PDF](https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf). 로컬 원문은 [보존 텍스트](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v1/literature_20260907/jbgs_wu_vallet_2026_20260907.txt:163)에 있다.

| 원문 위치 | 수행 내용 | 현재 감사에서의 의미 |
|---|---|---|
| §3.2, p387; 로컬 163–183행 | PSMNet disparity를 생성하고 master pixel마다 다중시점 전방교차, 인접 pixel로 센서 메시 구성 | 현재 COLMAP depth 역투영과 같은 영상점 생산이라고 입증되지 않았다. |
| §4.2, p388; 로컬 221–261행 | SGM과 LiDAR disparity의 차이가 1px를 넘는 오염 학습 표본을 제거하고 PSMNet 재학습 | 최종 갱신 점군의 통계적 이상점 제거가 아니라 학습 라벨 정제다. |
| §4.3.1/§4.3.2, p389; Figs11/15; 로컬 299–338행 | 작은 변화영역을 제거한 다음 남은 변화영역의 영상점을 LiDAR에 합침 | 문턱·연결성은 미공개지만, 탈락 영상영역을 다시 추가하는 동작은 기술된 정제 효과와 맞지 않는다. |
| §3.3/Fig6, pp387–388; 로컬 185–240행 | LiDAR가 없는 새 단독영역은 유지; 저자 실험에서는 LiDAR coverage가 image coverage를 포함해 해당 사례가 없었음 | 진짜 새 단독 관측과 가림·검사 부재·정제 탈락을 같은 상태로 취급할 수 없다. |
| §4.3.2/§5, pp389–390; 로컬 316–382행 | 벽면 불일치에 따른 잔존 오탐, dense matching·가림·식생 문제를 인정; 갱신 품질 평가를 미래 과제로 남김 | 정제 후에도 남는 문제는 검토할 가치가 있으나 저자가 숨긴 맹점이나 정량적으로 입증한 실패라는 표현은 부정확하다. |

최종 점군에 SOR/ROR 등 별도의 통계적 이상점 제거를 수행했다는 내용은 본문에 명시돼 있지 않다. 명시된 정제들을 재현하지 않은 채 일반 필터의 추가만으로 원문 재현이 완성되는 것도 아니다.

## 2. v2의 작은영역 정제 연결 결함

[ray_runtime.py:230](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/src/phd/wu_vallet_p3_v2/ray_runtime.py:230)의 `region_diagnostics`는 작은 `CHANGED` 영역을 `SINGLE`로 바꾼다. 그러나 [최종 조립:271](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/src/phd/wu_vallet_p3_v2/ray_runtime.py:271)과 [출력 드라이버:216](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/wu_vallet_p3_v2/update_points.py:216)는 새 점 중 `CONSISTENT`가 아닌 점을 모두 추가한다.

실제 `estimated_bidir_d0.3_a0 → estimated_bidir_d0.3_a1`에서 새 changed는 **26,669→15,082**, single은 **8,480→20,067**, 최종 추가는 **35,149→35,149**다. 정제로 changed에서 빠진 **11,587점도 계속 추가**됐다. 근거: [무정제 영수증](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v2/PHD-WU-VALLET-P3-UPDATE-v2/run/estimated_bidir_d0.3_a0/result.json), [1m² 정제 영수증](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v2/PHD-WU-VALLET-P3-UPDATE-v2/run/estimated_bidir_d0.3_a1/result.json).

[기존 테스트:98](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/tests/phd/test_wu_vallet_ray_runtime_v2.py:98)도 작은 양쪽 변화영역 정제 후 출력이 8→16으로 늘어나는 동작을 정답으로 고정했다. 수정 시에는 원 판정·크기 탈락·진짜 단독영역과 최종 추가 허용을 분리하고, 작은 old 오탐은 보존하며 작은 new 오탐은 추가하지 않는 출력까지 검증해야 한다. 이 감사는 v2의 해당 파일을 수정하지 않았다.

## 3. 현재 MVS와 영상 센서점은 서로 다른 입력 계보

P3 native MVS **865,108점**은 [현재 source config:11](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/mvs_als_source_relation_v1/run_v1.json:11)이 바인딩한 **복구 OpenMVS `dim_dense.ply` 43,926,567점**의 부분집합이다. 원행·XYZ 재생은 [preflight:140](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/wu_vallet_p3_v1/preflight.py:140)에 구현돼 있다. PLY에는 native image/pixel 필드가 없다.

이 복구의 [실제 실행 로그:6](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/densify_point_cloud.log:6)는 OpenMVS `--resolution-level 4 --max-resolution 1400 --min-resolution 640 --number-views 3 --number-views-fuse 2`를 기록한다. [실행 영수증](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/run_receipt.env:17)은 고정 이미지와 성공 종료를 바인딩한다. 과거 원본 PLY 43,942,554점과 이 복구 PLY는 동일하지 않으며 [기존 이슈:18](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/docs/experiments/p2/mvs_native_textured_mesh_preflight_v1/ISSUES_v1.md:18)가 그 차이를 보존한다.

반면 Wu v2의 현재 영상 센서점 **145,577점**은 [build_new:85](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/wu_vallet_p3_v2/update_points.py:85)가 image133의 **COLMAP `DJI_20241217084717_0142_D.JPG.geometric.bin`**을 읽어 역투영한 결과다. depth 크기는 1024×741, SHA256은 `1202e4efd919663a6aabee9184e139dd39a67c0bbd222fbff221779d04dd02a1`이다. 최종 OpenMVS 융합점의 일부를 그대로 사용한 입력이 아니다.

2026-09-07 읽기 전용 현장 점검:

- [patch-match.cfg:265](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p0-audit/data/work/mvs/colmap_dense/stereo/patch-match.cfg:265)는 exact937개 항목, image133에 `__auto__, 20`; SHA256 `1bcb36c2054112a3d91b45c47e0082b0fa8e2ace312e305891bedfa70b999067`.
- [fusion.cfg:133](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p0-audit/data/work/mvs/colmap_dense/stereo/fusion.cfg:133)는 exact937개 영상을 포함; SHA256 `a01732c4eb6d4958eb21813170e187bb086175cf348c7afbe1c8904d63ef05cf`.
- `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p0-audit/data/work/mvs/colmap_dense/stereo/consistency_graphs`는 존재하지만 파일 **0개**다. 저장된 pixel별 시점 일치 목록을 이 위치에서 복원할 수 없다.
- [공통계보:167](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/artifacts/manifests/gate_s0/common_base_r2b/existing_common_base_derivative_lineage_v1.json:167)의 COLMAP 4.0.4는 공통 SfM/OpenMVS 생산 기록이다. **geometric depth의 2026-06-24 실제 호출·로그는 durable binding이 없다고 같은 문서:91에 명시**돼 있다. 그 버전이나 생성 예제 스크립트를 실제 depth filter 설정의 증거로 확대하면 안 된다.

[COLMAP 공식 출력 형식](https://colmap.github.io/format.html#dense-reconstruction)은 `run-colmap-geometric.sh`를 생성된 사용 예제로 설명하고, [공식 튜토리얼](https://colmap.github.io/tutorial.html#dense-reconstruction)은 depth 계산과 fusion을 별도 단계로 구분한다. [공식 fusion 소스](https://github.com/colmap/colmap/blob/3.9.1/src/colmap/mvs/fusion.h#L50-L77)에도 pixel 지지 수·재투영·깊이·법선 조건이 따로 있다. 이 소스의 기본값을 과거 현장 실행값이라고 주장하지 않는다. `geometric.bin`이라는 이름만으로 최종 융합점과 같은 검증을 통과했다고 간주할 수 없다.

## 4. 일반 공간 이상점 제거를 실제 적용한 진단

[Open3D 공식 예제](https://www.open3d.org/docs/release/tutorial/geometry/pointcloud_outlier_removal.html#statistical-outlier-removal)의 `nb_neighbors=20`, `std_ratio=2.0`을 고정했다. 이는 이웃까지의 평균 거리로 고립 정도를 검사하는 SOR이며 **Wu 논문에 명시된 필터가 아니다**. 원 pixel 행을 보존하기 위해 예제의 voxel downsampling은 생략했다. 두 조건 모두 같은 파라미터를 사용했다.

| SOR 입력 범위 | 전체 입력점 | P3 제거점 | 참조 거리 >2m 7,971점 중 제거 | 큰 편차 잔존 | 참조 거리 ≤2m 제거 |
|---|---:|---:|---:|---:|---:|
| 전체 image133 센서점에서 계산 후 P3 선택 | 657,682 | 2,156 | 304 (3.81%) | 7,667 | 1,852 |
| P3 crop에서만 계산 | 145,577 | 2,559 | 329 (4.13%) | 7,642 | 2,230 |

전체 센서점 제거는 7,812점, 두 P3 마스크 차이는 403점이다. **이 고정 SOR 설정으로 큰 참조 편차점 대부분은 제거되지 않았다.** 연속적인 잘못된 표면도 내부에서는 조밀할 수 있어 고립점 검사의 목적과 실제 표면 적합성 검사는 다르다. 다만 이 결과가 모든 이상점 필터의 실패를 뜻하지 않으며, 큰 참조 편차가 모두 확정 오류라는 의미도 아니다. UAS header EPSG:32632와 working EPSG:25832의 차이, 미보정 datum/epoch·정합과 실제 관측 차이를 남겨둔다.

[실행 영수증](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v3/PHD-WU-VALLET-P3-SOR-DIAGNOSTIC-v3/run/receipt.json): Docker CPU4/8GiB, 네트워크 없음, Open3D 0.18.0, 3.68초. 마스크 저장·해시 고정 뒤 처음 UAS를 읽었고 평가 후 마스크 해시 불변을 검증했다. 참조 거리 2m는 기존 진단층을 재사용한 것으로 추가 허용 문턱이나 파라미터 선택에 사용하지 않았다.

[masks.npz](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/wu_vallet_p3_v3/PHD-WU-VALLET-P3-SOR-DIAGNOSTIC-v3/run/masks.npz)의 `p3_keep_with_context`/`p3_keep_without_context`는 기존 `common.npz/new_xyz`와 같은 순서다. `full_keep`, `full_native_pixel_id`, `p3_full_indices`, `p3_native_pixel_id`로 전체 센서점과 원 pixel을 정확히 연결한다. 마스크 SHA256: `91e2bd7a1ff1dfeaf050d626e4016cea4645ebbcb70b2bb8195b53aca4b039f1`.

재현 진입점: [실행 드라이버](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/wu_vallet_p3_v3/run_sor_diagnostic.sh), [구현](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/scripts/phd/wu_vallet_p3_v3/spatial_outlier_diagnostic.py), [고정 설정](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-operator/configs/phd/wu_vallet_p3_v3/sor_diagnostic_v3.json). 재실행은 별도 run ID를 지정해 기존 출력을 보존한다.
