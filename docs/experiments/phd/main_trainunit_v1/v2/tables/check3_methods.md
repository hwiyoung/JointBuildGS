# 확인 3: 비교 방법 넷(2DGS, GeoGS, LGDM, CDGS)의 기본 설정

scientific_verdict: null

## 기본값 (소스 코드)

| 방법 | iterations | densify_from_iter | densify_until_iter | densification_interval | opacity_reset_interval | 출처 |
|---|---:|---:|---:|---:|---:|---|
| 2DGS | 30,000 | 500 | 15,000 | 100 | 3,000 | `$SB/sources/2d-gaussian-splatting-adapters-v1/arguments/__init__.py:75,92,93,90,91` (원본 `2d-gaussian-splatting` 같은 줄·같은 값) |
| GeoGS | 30,000 | 500 | 15,000 | 100 | 3,000 | `$SF/geogs/source/GeoGS-official-adapters-v1-fix1/arguments/__init__.py:110,128,129,126,127` |
| CDGS | 30,000 | **100** | 15,000 | 100 | 3,000 | `cdgs-release{,-adapters-v1,-v2}/arguments/__init__.py:84,98,99,96,97` (`$SB/sources/`), `$SL/sources/cdgs-release-adapters-v3/arguments/__init__.py` 같은 줄. 98행은 `100 #500`으로, 공식 원본부터 500을 100으로 바꿔 둠 |
| LGDM | 없음 | 없음 | 없음 | 없음 | 없음 | GS 학습이 없는 방법(아래) |

밀도 제어 규칙(train.py):
- 2DGS: `train.py:126` `iteration < densify_until_iter`, `:130` `iteration > densify_from_iter and iteration % densification_interval == 0`, `:134` 불투명도 되돌림.
- GeoGS: `train.py:1041` `densify_allowed = (iteration < densify_until_iter) and (not freeze_done)`, `:1048`, `:1074`. `--freeze_onlybldg`이면 `freeze_done=False`(`:1166-1167`)라 밀도 제어는 15,000까지 그대로다. `--stage_switch_iter` 기본 8000(`:1266`).
- CDGS: `train.py:254` `iteration < densify_until_iter and ((not usedepth) or 가우시안 수 <= 1,500,000)`. 깊이를 쓰면 150만 개를 넘을 때 밀도 제어가 멈춘다. `:259`, `:264`(v2·v3 같은 줄).

## 이 실험에서 실제로 쓴 실행 인자

| 방법 | 판 | 넘긴 인자 (receipt.json `train_args`/`command`) | 반복·밀도 제어 인자 | 저장 반복 | 상태 |
|---|---|---|---|---:|---|
| 2DGS | `$SB/runs/<4 장면>/imgonly_2dgs_s0` | `-s /scene -m /o/model --eval -r 1 --data_device cpu` | 넘기지 않음 → 기본값 | 30,000 | PASS 4/4 |
| GeoGS | `$SB/runs/<4 장면>/geogs_ALS_fix1`, `$SF/runs/<4 장면>/trust_LoD2_fix1` | `... --eval --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight -r 1 --port 0 --iterations 30000 --stage_switch_iter 8000 --lambda_lod_init 0.08 --lambda_lod_anchor 0.005` | `--iterations 30000`(기본과 같음)만. 밀도 제어·되돌림 인자는 넘기지 않음 | 30,000 | PASS 8/8 |
| CDGS | `$SL/runs/<4 장면>/cdgsnofit_<ALS·LoD2>_s0`(adapters-v3, 8판), `$SL/runs/B0_b10/cdgs_LoD2_s0`(adapters-v2) | `-s <run>/scene -m <run>/model --depth -r 1 --eval --use_predefined_depth --predefined_depth_path <run>/scene/prior_depth` | 넘기지 않음 → 기본값 | 30,000 | PASS 9/9 |
| LGDM | `mvsfuse_<prior>` | 학습 없음 | 해당 없음 | (receipt iteration 0) | — |

- GeoGS 8판의 `model/training_lod.txt`는 모두 `Fixed stage switch iter: 8000`, `Densify stopped after switch: False`이다.
- `model/cfg_args`는 모든 판에 있지만 ModelParams(sh_degree, source_path, resolution, eval 등)만 담는다. 반복·밀도 제어의 실제 값은 receipt의 인자와 소스 기본값으로 정했다.
- 실행 코드(exp 체크아웃): 2DGS `scripts/phd/main_baselines_v1/twodgs/run_twodgs.py:10, :82-84, :261`; CDGS `scripts/phd/main_fill_v1/cdgs/run_cdgs_train.py:176-179, :419`.

## LGDM

**없음.** 저장소에서 LGDM은 `fusion`(MVS 기반 결합, Zhou et al. 2020 재현, 결과 `mvsfuse_<prior>`)의 별칭으로만 나온다(`scripts/phd/main_gtjudge_v1/add10_export.py:30` `'LGDM':'fusion'`, `docs/experiments/phd/main_gtjudge_v1/verification/addendum5_recolor.json:161`). 판정 → 합성 → depthfuse(TSDF) 순서로 가우시안 학습이 없다(exp 체크아웃 `scripts/phd/main_baselines_v1/fusion_bl.py:1-4` "no training", `mvsfuse/plan.py:123` "iteration 0"). 그래서 반복 수·밀도 제어 값이 없다.

찾아본 곳: 작업 폴더의 `src/`, `scripts/`, `configs/`, `docs/`('LGDM' 검색), `src/phd/forks/`(GeoGS-conf-guided-v1-r11~r28, diff-surfel-rasterization-cull3), exp 체크아웃의 `scripts/phd/main_baselines_v1/`(twodgs, cdgs, geogs_als, mvsfuse, judgefuse, fusion_bl.py, config_bl.py)와 `scripts/phd/main_fill_v1/`, artifacts의 `main_baselines_v1/sources`, `main_fill_v1/sources`.

## 참고 (비교 방법 아님)

본 방법 포크 r28: `src/phd/forks/GeoGS-conf-guided-v1-r28/arguments/__init__.py:110,128,129,126,127` = 30,000 / 500 / 15,000 / 100 / 3,000. GeoGS와 같다(`train.py:1183` densify_allowed).

경로 약어: `$ART` = `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts`, `$SB` = `$ART/phase-payloads/phd/main_baselines_v1/PHD-MAIN-BASELINES-v1`, `$SF` = `$ART/phase-payloads/phd/main_fix_v1/PHD-MAIN-FIX-v1`, `$SL` = `$ART/phase-payloads/phd/main_fill_v1/PHD-MAIN-FILL-v1`.
