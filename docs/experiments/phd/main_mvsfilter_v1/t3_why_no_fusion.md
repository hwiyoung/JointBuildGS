# 3절 물음 1: COLMAP 2단계(stereo_fusion)를 왜 돌리지 않았나

scientific_verdict: null. 찾은 시간 약 25분(11/19 23:20~23:45).

## 답

- **까닭을 적은 글: 기록 없음.** 2단계를 돌리지 않기로 한 까닭을 적은 문장은 본 곳 어디에도 없다.
- 있는 것은 두 가지다. (1) 처음 MVS를 돌린 목적을 적은 줄, (2) 화소마다 점을 만들고 합치지 말라는 지시.

| 무엇 | 경로:줄 | 원문 |
|---|---|---|
| 처음 MVS(937장)를 돌린 목적 | `scripts/input_and_alignment/tum_transfer/prior_full_stereo.sh:3-4` | "Run COLMAP PatchMatch stereo on the EXISTING P0 colmap_dense workspace to produce / per-view depth+normal maps (.geometric.bin) for L_depth / L_normal supervision." |
| 같은 스크립트가 돌린 명령 | `prior_full_stereo.sh:42-48` | `colmap patch_match_stereo ... --PatchMatchStereo.geom_consistency true ... --PatchMatchStereo.filter true` (stereo_fusion 줄 없음) |
| 준비 단계 상자 MVS | `scripts/phd/main_prep_measure_v1/run_colmap.sh:4-5, 16-19` | "Same settings as the 937-image MVS (scripts/input_and_alignment/tum_transfer/prior_full_stereo.sh)" — `patch_match_stereo` 만 |
| 점을 만드는 규칙(지시) | `docs/experiments/phd/main_uncert_v1/본실험_불확실도지도_발주문_v2.md:119` | "**MVS 점.** 학습 영상 모두의 MVS 깊이 지도에서 화소마다 카메라로 3차원 점을 만든다. 여러 시점의 점을 합치지 않고 그대로 모은다. 점마다 어느 영상의 점인지를 남긴다." |
| 같은 지시, 판 가 | 같은 파일 `:120` | "판 가(기본): 관측 신뢰도 마스크를 통과한 깊이. 지금 MVS 깊이 항에 들어가는 깊이다." |
| 캠퍼스 MVS(지금 점군의 깊이 지도) 실행 기록 | `PH/main_widen0_v2/PHD-MAIN-WIDEN0-v2/mvs/full/container_launch.json` | `colmap patch_match_stereo --workspace_format COLMAP --PatchMatchStereo.geom_consistency true --PatchMatchStereo.max_image_size 1024 --PatchMatchStereo.num_iterations 3 --PatchMatchStereo.filter true --PatchMatchStereo.cache_size 32` (그 밖 명령 없음) |
| 같은 작업 공간 | `.../mvs/full/colmap_receipt.json`, `stereo/` | 기하 깊이 지도 819장, `stereo/fusion.cfg` 없음, `consistency_graphs/` 비어 있음, `fused.ply` 없음 |
| 앞 작업의 조사 | `docs/experiments/phd/main_judgeprobe_v1/tables/da_survey.md:13` | "stereo_fusion 없음. scripts/phd/main_widen0_v2/mvs_points.py 가 기하 깊이 지도의 유한하고 0보다 큰 모든 화소를 역투영" |

## 깊이 지도를 화소마다 역투영하는 방식이 처음 들어온 커밋

| 커밋 | 날짜(한국) | 파일 | 뜻 |
|---|---|---|---|
| `62429912` | 2026-10-23 09:47:19 | `scripts/phd/main_uncert_v1/u1_mvs_points.py` | 처음. 머리글: "not fused: every valid pixel of every training view's MVS depth map becomes one 3-D point" (UNCERT-v1 발주 1.2-6) |
| `d1281346` | 2026-10-24 01:16:04 | `scripts/phd/main_widen0_v2/mvs_points.py` | 지금 점군(캠퍼스 819장)을 만든 스크립트. "inherited integer-pixel convention ... as UNCERT-v1". `df65fb9d`(01:51)에서 역투영 재현 검사 추가 |

- 그 앞(10/06 `fb2509eb`, 준비 단계 step03)은 깊이 지도를 학습의 관측 신뢰도 마스크(깊이 > 0)로만 썼고 점군을 만들지 않았다.

## 본 곳

`docs/experiments/phd/` 아래 main_uncert_v1·main_widen0_v2(발주문_v2, 보고, issues, progress)·main_prep_measure_v1(보고서 v1·v1.1, 결정요청)·main_judgeprobe_v1; `scripts/phd/main_widen0_v2/`(mvs_points.py, run_mvs.sh, colmap_subset.py), `scripts/phd/main_prep_measure_v1/`, `scripts/phd/main_uncert_v1/`, `scripts/input_and_alignment/tum_transfer/prior_full_stereo.sh`; 저장소 전체에서 `stereo_fusion|StereoFusion|fused.ply` 찾기(걸린 것: JUDGEPROBE da_survey 둘, phases/fair-pilot 의 다른 자료 하나); WIDEN0 `mvs/full` 의 `container_launch.json`, `colmap_receipt.json`, `patch_match.log`; 위 두 스크립트의 커밋 기록.
