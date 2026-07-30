# W E5 Pilot Prep (A-stage)

> 분류·관찰 재료만 기록한다. 성공 기준 판정과 게이트 통과 여부는 쓰지 않는다. CRS는 EPSG:25832.

## A0 Start Check

| item | record |
|---|---|
| branch | `feat/p2-structure-learn` |
| HEAD at A-stage start | `bcd8ac94f8e6a6681500e71da99941ee32de7dca` |
| 기준문서 | `기준문서_방법론·모집단·비교설계_v1.md` line 1 = v1.25 (2026-07-06) |
| 사전등록서 잠금본 | `사전등록서_본비교실험E5·기준레시피_v1_20260706.md`, committed in `03d3b8e` |
| required pilot inputs | present: `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729`, `docs/pointcloud_attributes_v1_2.csv`, `docs/recipe_registry.md` |
| ACMP 64 대장 | user-confirmed path: `results/tum_transfer/mob/overseg_lever/gen_8way.csv` |
| manual failure labels | `docs/manual_review_judgments.csv` |
| run-root rule | new run material placed under `phases/p0-audit/runs/` or `phases/p2-gsjso/runs/`; no new root `runs/` |

## Roofer Alignment

| source | value |
|---|---|
| baseline run | `phases/p0-audit/runs/w2_1_roofer_default_20260612_152729` |
| config sha256 | `65a8435b8e95b5cbeb86d3a2b82a8fed0b07e62737dc7714062a4151eb24bdd3` |
| versions sha256 | `4a786bdc66cc29732b208b665c5133aa57af848ff38da8e347d77dc001b9c113` |
| Roofer | `roofer 1.0.0 (v1.0.0)` |
| val3dity | `2.6.0` |
| read-out relation | W2 used Roofer default family with only `--id-attribute` and AOI `--box`; E5 raw baselines use the same plumbing-only Roofer call. The preregistered `eps0.3/minpts15/complexity0.888` is recorded as the same default 계열 for the GS read-out fingerprint. |

## A1 Pilot Block Candidates

| item | value |
|---|---:|
| existing GS stage exclusion | 79 buildings |
| outside-stage buildings | 120 |
| rule-satisfying candidate blocks | 412 |
| recommended candidate | `C001` |
| candidate buildings | 18 |
| dense success / failure | 10 / 5 |
| dense no-points / no-planes / assembly | 5 / 0 / 0 |
| ref-mismatch included | none |
| seed clip possible | sparse yes, dense yes, ACMP yes |

Files:

- Candidate table: `docs/e5_pilot_block_candidates.csv`
- Map: `docs/figs/e5_pilot_block_candidates.png`
- Run fingerprint: `phases/p2-gsjso/runs/e5p_prep_20260706_235306/versions.txt`

Cost material for the human A-stage decision: 6 learning runs = three seed sources x two random seeds; estimated GPU time 6 x 4-8 h; read-out + assembly <1 h per learned run.

## A2 Constant Set Switch

| linked constant | before | after | files |
|---|---:|---:|---|
| ACMP seed transform | `-556` | `-558.3` | `seed_prep_acmp.json`, `tum_mob_seed_prep.sh` |
| semantic seed/label shift | `604-48=556` | `604-45.7=558.3` | `seed_semantic.yaml`, `semantic_seed.py` |
| seed band geoid | `48.0` | `45.7` | `seed_depth_bands.py`, `seed_material_audit.py` |
| raw unification geoid | `+48.0` | `+45.7` | `tum_mob_raw_to_npz.py` |

Gate material:

- Scoped old-constant grep hit count: 0.
- ACMP local z p50 moved from `-36.240` to `-38.540`, delta `-2.300 m`.
- Full table: `docs/experiments/pilots/e5_pilot/reports/e5_seed_constant_gate.md`
- Run fingerprint: `phases/p2-gsjso/runs/e5p_const_20260706_235710/versions.txt`
- Commit: `2ebd8af`

## A3 GS-Sparse Config

| item | value |
|---|---|
| config | `configs/tum_mob/gs_d4_sparse.yaml` |
| derived from | `configs/tum_mob/gs_d4_dense.yaml` |
| seed change | `init_pointcloud` -> `results/tum_transfer/mob_analysis/seed/seed_sparse.ply` |
| sparse seed points | 369225 |
| recipe diffs excluding seed path and output directory | 0 |
| recipe string | `GS(D4; seed-protect; pho1·sem0.1·nc0.05·dep0.03·nrm-off·str1[g2;na0.08;cp0.01;warm15k]; gssem)` |

Files:

- Diff proof: `docs/experiments/pilots/e5_pilot/reports/e5_gs_sparse_config_diff.md`
- Run fingerprint: `phases/p2-gsjso/runs/e5p_sparse_config_20260706_000204/versions.txt`
- Commit: `7b25e71`

## A4 Preflight

| input | height history |
|---|---|
| raw-ACMP | source `acmp_aoi_utm.laz` orthometric, E5 NPZ path adds `+45.7 m` once |
| raw-sparse | COLMAP sparse `points3D.txt` + `[690953,5336071,604]`, geoid 미개입 |
| ALS patch reference | source `als_aoi.laz` orthometric, patch check uses `+45.7 m` |

Ground-patch material from `docs/experiments/pilots/e5_pilot/reports/e5_baseline_preflight.md`:

- Overlap cells: 1878.
- Global cell diff median: `-2.296 m`, IQR `-2.340..-2.260 m`.
- Best listed patch: ACMP q10 `559.150`, ALS ground median `559.240`, diff `-0.090 m`.
- Observation only: best patches show submeter local alignment after +45.7; global cell diff mixes roofs, trees, and matching noise.

## A4 Baseline Reinforcement Runs

| input | run_id | points after prep | class 6 after overlay | Roofer crop/features | status success/failure | main reason counts |
|---|---|---:|---:|---:|---:|---|
| raw-ACMP | `e5p_baseline_acmp_20260706_001813` | 35,453,062 | 16,336,157 | 198 / 198 | 124 / 75 | no_points 22; no_planes 13; val3dity_invalid 17; missing_lod22 22; missing_roofer_output 1 |
| raw-sparse | `e5p_baseline_sparse_20260706_002300` | 369,543 | 214,272 | 198 / 198 | 91 / 108 | no_points 87; no_planes 17; val3dity_invalid 2; missing_lod22 1; missing_roofer_output 1 |

Fingerprint table:

| input | config | versions | ckpt sha256 | pointcloudification | label 방식(read-out) | geoid flag |
|---|---|---|---|---|---|---|
| raw-ACMP | `phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/config.yaml` | `phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/versions.txt` | not applicable baseline no training | raw point cloud -> LAS -> SMRF ground -> footprint overlay | original point cloud + SMRF/boundary | ACMP source +45.7 m |
| raw-sparse | `phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/config.yaml` | `phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/versions.txt` | not applicable baseline no training | raw point cloud -> LAS -> SMRF ground -> footprint overlay | original point cloud + SMRF/boundary | sparse local+604, geoid 미개입 |

Status and validation files:

- raw-ACMP status: `phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/building_reconstruction_status.csv`
- raw-ACMP val3dity: `phases/p0-audit/runs/e5p_baseline_acmp_20260706_001813/val3dity/raw_acmp_val3dity_report.json`
- raw-sparse status: `phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/building_reconstruction_status.csv`
- raw-sparse val3dity: `phases/p0-audit/runs/e5p_baseline_sparse_20260706_002300/val3dity/raw_sparse_val3dity_report.json`
- Commits: raw-ACMP `6150ab3`, raw-sparse `0484921`

## Attributes v1.3

| item | value |
|---|---:|
| v1.2 rows copied | 597 |
| original v1.2 columns checked | 67 |
| old-row diffs | 0 |
| new rows appended | 398 |
| raw_acmp_e5p rows | 199 |
| raw_sparse_e5p rows | 199 |
| raw_acmp_e5p no-points rows | 1 |
| raw_sparse_e5p no-points rows | 40 |
| v1.2 sha256 | `4d0ca1bf377e7094291e865910c74206aec2b46eaa9ea8f1e9e1b9885bd19a11` |
| v1.3 sha256 | `364b2f08938518707864e838e72e3075bef8158a0d6af0fb22200b89d6885849` |

Files:

- Attribute table: `docs/pointcloud_attributes_v1_3.csv`
- Invariance check: `docs/e5_pointcloud_attributes_v1_3_check.json`
- Run fingerprint: `phases/p2-gsjso/runs/20260706_attr_v1_3/versions.txt`

## Commit Ledger

| step | commit |
|---|---|
| prereg + 기준문서 lock | `03d3b8e` |
| figure path docs | `2bbe237` |
| figure asset add | `bcd8ac9` |
| A1 pilot candidates | `8237380` |
| A2 constant switch | `2ebd8af` |
| A3 sparse config | `7b25e71` |
| A4 raw-ACMP baseline | `6150ab3` |
| A4 raw-sparse baseline | `0484921` |

## One-Line Observation

관찰: A단계 재료는 후보 블록·상수 전환 게이트 표·sparse config diff·raw-ACMP/raw-sparse 전수 status·attributes v1.3까지 생성됐고, raw-sparse는 raw-ACMP보다 no-points 회계가 많다; 판정은 여기서 하지 않는다.

## Stop Point

B단계 파일럿 학습·게이트 재료 생성은 아직 실행하지 않는다.

판정 기입란:

- 파일럿 블록 = ⟦대기⟧
- 세 씨앗 x 2회(6학습) 유지 = ⟦대기(기본: 유지)⟧
- 해석 노트 ①~⑥ = ⟦대기(승인/수정)⟧
