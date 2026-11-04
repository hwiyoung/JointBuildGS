| 항목 | 기록 |
|---|---|
| 작업 | PHD-MAIN-RESCORE-v1 덧붙임 5 · 2026-11-04 |
| 범위 | 기존 코드·설정·중간 파일 확인. 2번의 저장 잔차 초과 비율만 새로 계산 |
| 실행 | Docker CPU, nice 19, 메모리 한도 32 GiB. 잔차 계산·메타데이터 확인 3.19초 |
| 변경 | 학습 0회, GPU 사용 없음, 메시·점수 재생성 없음. 기존 단계 2 유지 |
| 판정 | scientific_verdict: null |

**1. 참값 점의 칸 소속과 패치별 참값 높이**

| 물음 | 답 | 코드·설정 근거 | 확인 방법 |
|---|---|---|---|
| 참값 점도 결과 점과 같은 새 기둥 규칙인가 | **아니오.** 결과 점에만 0.25×0.25 m 패치의 법선 기둥(지붕 ±10 m, 벽 ±5 m)을 적용한다. 겹치면 법선 거리 절댓값이 작은 패치, 동률이면 작은 번호를 고른다. 참값 점은 기존 STAGE1 소속 행을 읽는다. | [geometry.py:21](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/geometry.py:21), [prism.cpp:23](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/prism.cpp:23), [geometry.py:35](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/geometry.py:35), [score_mesh.py:15](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/score_mesh.py:15) | `sample_owner`를 만드는 `columns()`와 `row_owner=lookup[pa]`를 만드는 경로 대조. 칸별 참값 마스크는 후자를 사용 |
| 실제 지붕 참값 소속 규칙 | 각 참값 점의 **XY에서 연직 하향 광선**을 사전 정보 면에 쏜다. 만난 지붕 면의 교점으로 패치를 찾고, 패치에 모인 참값 점 중 최고 높이보다 1 m 아래까지의 점만 남긴다. **참값–사전 정보 높이 차이의 ±10 m 제한은 이 소속 단계에 없다.** | [s04_gt_v7.py:252](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage1_v1/s04_gt_v7.py:252), 특히 258–271행 | `gt_owner_<prior>.npz` 생성 코드 추적 |
| 실제 벽 참값 소속 규칙 | LoD2 벽에 가장 가까운 점을 찾고, 벽면 법선 방향으로 투영되며 면 안에 들어가는 **2 m 이내**의 참값 점을 배정한다. 수직면으로 분류한 참값 점만 쓴다. | [s04_gt_v7.py:272](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage1_v1/s04_gt_v7.py:272), 특히 277–296행 | `dist<=2.0`, `along>=0.999*dist-1e-4`, `locate()` 조건 확인 |
| 채점에 실제 쓰는 참값 점 | 평가 범위·제외 영역 조건을 통과한 지붕점은 지붕 패치, 벽점은 벽 패치의 소속 행만 사용한다. 지붕은 XY 0.1 m 격자, 벽은 면별 벽 좌표 0.1 m 격자로 솎은 `thin` 행을 재사용한다. B0는 패치의 기존 참값 출처에 따라 주 참값과 ULS 보완을 선택한다. | [defs_s1.py:89](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage1_v1/defs_s1.py:89), 95–123행; [s1_common.py:76](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage1_v1/s1_common.py:76) | 저장된 `defs/<지역>/rows_<사전정보>.npz`의 `src, point, patch, kind, thin`을 소비하는 경로 확인. 장면 전체 참값은 `bsurf.npz`의 ULS 건물 표면점 |
| 맞는 판단의 칸을 정할 때 쓴 패치별 참값 높이 `gt_p` | 위의 채점용 소속 행과 **별도**이다. 제외 영역을 뺀 ULS 참값점( B0는 주 참값도 함께)을 모아, 패치 중심·법선 기준 **반경 0.5 m 원기둥, 지붕 ±10 m·벽 ±3 m**에서 면을 찾는다. +H부터 두께 0.3 m 층을 0.05 m씩 옮겨 모은 점의 20% 이상을 처음 포함하는 층 중심 `o`를 고른다. 그 주위 ±1 m 점이 10개 이상이고 LMedS 평면 확인을 통과하면, **그 점들의 법선 좌표 중앙값**을 `gt_p`로 쓴다. | [u1_other_points.py:68](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_uncert_v1/u1_other_points.py:68); [uncert_v1.json:12](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/configs/phd/main_uncert_v1/uncert_v1.json:12), `defs.inner_radius_m/column_half_m/layer_*/slab_half_m/gt_min_points`; [ring_kernel.py:70](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_judgeapply_v1/inherited/ring_kernel.py:70), 126–149행; [u_core.py:37](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_judgeapply_v1/inherited/u_core.py:37) | LoD2는 UNCERT의 `work/gt_<지역>_LoD2.npz`에서 읽고, ALS는 JUDGEAPPLY의 재추정 법선으로 같은 함수를 적용. `gt_p`는 절대 표고가 아닌 패치 중심 기준 법선 좌표 |
| 새 칸과의 연결 | JUDGEAPPLY의 `gt_p`, `gt_status`, 사전 정보 높이와 영상 깊이 평균을 그대로 읽고 τ만 교체했다. `gt_status==0`인 곳에서 두 자료와 `gt_p`의 차이가 τ 안인지로 칸을 정한다. B0 참값 평가도 축·두 높이·관측 수가 같음을 확인하고 기존 값을 재사용했다. | [truth.py:16](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_judgeapply_v1/truth.py:16), [tau_cells.py:26](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/tau_cells.py:26), [refresh_b0_truth.py:3](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_judgeapply_v1/refresh_b0_truth.py:3) | 저장값 재사용·새 칸 생성 코드 대조; 참값 점 재분류·높이 재계산 없음 |

- **B173 날개:** 참값 점의 XY 연직선이 그 날개 사전 면에 닿고 위의 최고층 조건을 통과하면, 사전 정보보다 3.5~6 m 아래여도 그 패치의 채점용 참값 점으로 들어간다. 높이 차이 자체로 배제하지 않는다. `gt_p`용 지붕 탐색도 ±10 m이지만 반경·면 찾기 조건은 별도로 통과해야 한다.
- 장면 참값의 참고 소속에서 지붕·벽 배정이 겹치면 참값의 수직면 분류와 종류가 맞는 소속을 우선한다. 새 결과 점의 최소 법선 거리 선택과 다르다: [dm_common.py:217](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_dist71_v1/dm_common.py:217).

**2. τ 원본 잔차의 초과 비율**

| 탐색 지역 | 사전 정보·면 | 모은 차이 수 | 이번 비율의 τ (cm) | 절댓값 > τ (%) | 절댓값 > 2 m (%) |
|---|---|---:|---:|---:|---:|
| B0 | LoD2 지붕 | 2,560,818 | 27.2 | 23.2054 | 5.8653 |
| B0 | LoD2 벽 | 2,664,723 | 64.3 | 15.3490 | 7.5595 |
| B0 | 항공 LiDAR | 2,483,355 | 14.7 | 12.1178 | 2.9406 |
| R2 (B173 주변) | LoD2 지붕 | 1,991,449 | 24.7 | 22.8599 | 13.8687 |
| R2 (B173 주변) | LoD2 벽 | 2,092,171 | 39.2 | 29.0839 | 12.2006 |
| R2 (B173 주변) | 항공 LiDAR | 1,954,162 | 21.2 | 21.0619 | 15.1505 |
| R1 | LoD2 지붕 | 7,990,474 | 85.5 | 19.6950 | 8.8449 |
| R1 | LoD2 벽 | 8,661,588 | 100.6 | 23.6109 | 11.6235 |
| R1 | 항공 LiDAR | 7,489,460 | 13.2 | 19.3861 | 3.7082 |

| 구분 | 정의·근거·확인 방법 |
|---|---|
| 원본 배열 | `PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s52/s03/<B0,R2,R1>/<LoD2,ALS>/residual_samples.npz`의 `roof`, `wall`. PH = `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd`. 항공 LiDAR τ는 `roof` 배열을 쓴다. 파일별 SHA-256과 표본 수가 기존 표 1 출처와 일치함을 확인 |
| 저장 잔차의 정확한 뜻 | **`r=(영상 깊이−사전 정보 렌더 깊이)×f`**. 단순 카메라 깊이 차이가 아니다. 지붕은 `f=abs(n·d)/abs(n_z)`, 벽은 `f=abs(n·d)`이며, 지붕·벽 경계는 `abs(n_z)=0.5`. 부호 반전은 이번 절댓값 비율과 NMAD에 영향 없음. [s03_stage1.py:134](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:134), [conversion.py:47](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/prior_propagation_v5/conversion.py:47) |
| 모으는 조건 | 정합 후 사전 정보 건물 면·탐색 범위 안·유효한 양의 영상 기하 깊이 픽셀. 시점·면 종류마다 최대 20,000개를 모은 기존 배열이며, 새로 표본을 뽑지 않음. [s03_stage1.py:245](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:245), 288–299행 |
| 새 τ와 이번 문턱 | 새 τ는 저장된 유한 잔차 전체에 대해 `2.5×1.4826×median(abs(r−median(r)))`, 벗어난 값 제거 없음: [tolerance.py:18](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/inherited/tolerance.py:18). **이번 비율은 사용자가 준 표 6.5의 반올림한 cm 값**을 문턱으로 사용. 기존 채점기의 반올림 전 τ는 바꾸지 않았고 CSV의 `stored_unrounded_tau_m`에 함께 기록 |
| 비율 계산 | `count(abs(r)>문턱)/유한 잔차 수×100`. 중앙값을 빼지 않음, 엄격한 `>` 사용, 절단·이상값 제거 없음. 9개 배열 모두 비유한 값 0개. [계산 코드](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/ch6_impl_check.py), [설정](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/configs/phd/main_rescore_v1/ch6_impl_check.json) |
| 확인의 한계 | 이 비율은 **불변면·변화면 비율이 아니다.** 저장 잔차에는 각 픽셀의 실제 변화 여부 표지가 없어, “대부분 불변면” 전제 자체는 확인 불가. 같은 면의 여러 시점 표본도 포함하므로 독립 면적 비율로 읽지 않음 |
| CSV·검증 | [ch6_tau_residual_ratios.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_rescore_v1/tables/ch6_tau_residual_ratios.csv). 표본 수·초과 개수·비율·원본 경로·SHA 포함. CSV 9행과 개수/분모 산술 확인 통과. 기존 재현 검사 재실행 없음 |

**3. 영상 크기와 왜곡 보정**

| 단계 | 확인한 크기·처리 | 근거 | 확인 방법 |
|---|---|---|---|
| 원본 카메라 | FULL_OPENCV, **5280×3956** | [원본 cameras.txt:5](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p0-audit/data/work/colmap/sparse/0/cameras.txt:5) | 저장된 원본 보정 모델의 폭·높이 읽기 |
| COLMAP 왜곡 보정 | `image_undistorter --max_image_size 1400`; 출력 PINHOLE **1400×1013**. 가로세로비 변경은 이 단계에서 이미 나타남 | [03_mvs.sh:367](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/phases/p0-audit/scripts/03_mvs.sh:367); [실제 실행 로그:1](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/p0-audit/runs/t3_mvs_20260611_230138/logs/colmap_image_undistorter.log:1) | 저장된 `colmap_dense/sparse/cameras.bin` 및 보정 JPEG 한 장의 헤더가 모두 1400×1013 |
| 가장자리 자르기 여부 | **왜곡 보정·출력 화면 변경 단계는 확인. 원본의 고정 사각형을 얼마나 잘랐는지는 확인 불가.** 실제 명령에는 별도 ROI·crop 지정이 없다. 같은 고정 COLMAP 이미지의 도움말은 `blank_pixels=0`, ROI `(0,0)–(1,1)` 기본값. 정확한 원본 픽셀 제거 범위나 최대 크기 축소 전의 중간 크기는 저장 자료에서 찾지 못함 | [고정 실행 파일 도움말:18](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/main_rescore_v1/PHD-MAIN-RESCORE-v1/ch6_impl_check/colmap_image_undistorter_help.txt:18); 위 실행 로그 | 실행 인수·카메라·이미지 헤더 대조. 크기 차이만으로 원본 crop 좌표를 역산하지 않음 |
| 학습 입력 생성 | 보정된 **1400×1013 → 1024×741**, `cv2.resize(..., INTER_AREA)`와 JPEG 품질 95. 이 코드에는 추가 crop 없음. `fx,cx`는 `1024/1400`, `fy,cy`는 `741/1013`으로 함께 축소 | [fork_inputs_v6.py:103](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage0_v1/fork_inputs_v6.py:103); [common.py:155](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_prep_discard_rule_v1/common.py:155) | 세 지역 학습 `cameras.bin`이 모두 1024×741. 같은 이름의 보정 JPEG와 학습 JPEG 헤더 대조 |

- 논문에 확정해 적을 크기: **원본 5280×3956 → COLMAP 왜곡 보정 출력 1400×1013 → 학습 영상 1024×741**.
- “잘라 낸 뒤 크기”가 보정 후 저장 영상을 뜻하면 **1400×1013**. 최대 크기 축소 전 원본 좌표계의 crop 크기를 뜻하면 **확인 불가**.

**4. 사전 정보 정합 이동 — 부록 표 B.1용**

| 탐색 지역 | 적용 실험 지역 | 사전 정보 | x 이동 (m) | y 이동 (m) | z 이동 (m) |
|---|---|---|---:|---:|---:|
| B0 | B0 | 항공 LiDAR | -0.048193371 | +0.043051139 | 0 |
| R2 | B173 주변 | 항공 LiDAR | -0.056194347 | +0.062888844 | 0 |
| R1 | R1 | 항공 LiDAR | 0 | 0 | 0 |
| B0 | B0 | LoD2 | 0 | 0 | 0 |
| R2 | B173 주변 | LoD2 | 0 | 0 | 0 |
| R1 | R1 | LoD2 | 0 | 0 | 0 |

| 구분 | 답·근거·확인 방법 |
|---|---|
| 좌표·적용 방향 | 지역 좌표의 x=E, y=N, z=높이이며 EPSG:25832의 축 방향을 유지한다. 표 값은 **사전 정보 좌표에 더하는 이동량**. 공통 원점 이동·기존 높이 기준 변환과 구분한 정합 추가 이동 |
| 구한 방법 | 경사진 지붕의 영상 깊이−사전 정보 높이 차이로 Nuth–Kääb 수평 보정량을 제안하고, 다시 렌더한 확인 시점의 NMAD가 감소하는 단계만 채택. 마지막에는 전체 시점 건물 면 NMAD 감소도 확인. 수직은 수평 보정 후 중앙값 절댓값이 NMAD보다 클 때만 채택했으며 위 여섯 조건은 모두 0. [registration.py:74](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/prior_propagation_v5/registration.py:74), 101–118행; [s03_stage1.py:265](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:265) |
| 원본 수치 | `PH/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1/s52/s03/<탐색지역>/<사전정보>/summary.json`의 `registration.shift_applied`. 각 실험 지역 `PH/main_stage0_v1/PHD-MAIN-STAGE0-v1/s61/box/<지역>/<사전정보>/summary.json`과 **여섯 조건 모두 정확히 일치**함을 확인. 상세 경로·SHA는 아래 확인 기록 |
| LoD2·R1의 0 의미 | 정합을 추정하지 않았다는 뜻은 아니다. 제안된 수평 이동이 채택되지 않았고, 수직 채택 조건도 충족하지 않아 최종 적용값이 0 |
| 정합에서의 제거와 τ의 제거 | Nuth–Kääb 보정량 추정 내부에는 중앙값 기준 3 NMAD 선택이 남아 있다([registration.py:86](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/src/phd/prior_propagation_v5/registration.py:86)). 덧붙임의 “벗어난 값 지우기 없음”은 **고정 정합 후 τ 계산**에 적용한 변경이며 정합 알고리즘을 바꾸지 않음 |

| 방법 | 같은 정합 사전 정보인가 | 근거·확인 방법 |
|---|---|---|
| 기준선 | **예.** 세 지역·두 사전 정보 실행 영수증의 입력이 같은 STAGE0 `fork_inputs/s61/<지역>/scene_<사전정보>` | `PH/main_stage3_v1/PHD-MAIN-STAGE3-v1/runs/<지역>/nojudge_<사전정보>_s0/receipt.json`의 `command`; [fork_inputs_v6.py:134](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage0_v1/fork_inputs_v6.py:134), 158–177행 |
| GeoGS | **예, 같은 정합 이동·원래 면 출처.** 면의 사용 범위는 같다고 하지 않음: ALS는 건물 정점이 하나 이상 있는 삼각형, LoD2는 바닥면 제외 | [als_inputs.py:102](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_baselines_v1/geogs_als/als_inputs.py:102); [geogs_prep.py:123](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_stage1_v1/geogs_prep.py:123). 세 ALS 준비 영수증의 `registration_check.shift_equal=true`, 등록 정점 최대 차이 0 m; 세 LoD2 준비 영수증 `registration_shift=[0,0,0]` |
| CDGS | **예.** 이번 채점 대상 `cdgsnofit_*`는 같은 STAGE0 사전 정보 깊이를 읽고 시점별 추가 적합을 하지 않는 판(scale 1, shift 0) | [cdgs_fl_scenes.py:3](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_fill_v1/cdgs/cdgs_fl_scenes.py:3), 46–49·78–84행. 여섯 준비 영수증의 `prior_depth`가 STAGE0 export를 가리키며 `all_checks_pass=true`. 옛 CDGS 시점별 적합 판과 구분 |
| 2DGS | **해당 없음. 영상 단독**이며 사전 정보 점을 받지 않음. 두 사전 정보 칸에서 같은 모델을 평가 | [prep_scenes_2dgs.py:8](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_baselines_v1/twodgs/prep_scenes_2dgs.py:8), 164–171행; 채점 job의 동일 모델 경로 |
| 결합·판단 조합·상한 | **같은 정합 사전 정보에서 출발.** 공통 JUDGEAPPLY 패치의 사전 정보 높이와 영상 높이로 목표를 고른다. 목표를 조합하므로 최종 면 자체가 사전 정보와 동일하다는 뜻은 아님 | [targets.py:4](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/targets.py:4), [render_patches.py:8](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_rescore_v1/render_patches.py:8) |
| 본 방법 FINALTRAIN | **같은 정합 입력에서 출발.** 초기점은 같은 STAGE0 장면, 목표는 판단으로 정한 패치별 높이 | [prepare_inputs.py:24](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/scripts/phd/main_finaltrain_v1/prepare_inputs.py:24), 49–52·55–75행. R1 학습의 완료 여부와 별개인 입력 구현 확인 |

- 확인 기록: [provenance/ch6_impl_check.json](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-exp/docs/experiments/phd/main_rescore_v1/provenance/ch6_impl_check.json). 원본 잔차 SHA, 저장 표본 수 대조, CSV 산술, 실제 카메라·JPEG 크기, 정합·비교 방법 준비 영수증을 기록했다.
- 확인 불가: 원본 좌표에서의 정확한 왜곡 보정 crop 경계·축소 전 크기, 잔차 표본의 실제 불변면/변화면 표지. 이 값을 짐작으로 채우지 않았다.
