# W_observability_inventory — Phase B 보조: 관측가능성 조사 (인벤토리, 읽기 전용·판정 금지)

> **실험 2 / Phase B 보조.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. **재학습·재구성·data/raw 변경 없음 — 읽기 전용 인벤토리만.** 관찰만, 판정 = 김휘영.
> 배경: D11(complexity-survey)이 "결함은 지붕 복잡도가 아니라 영상 관측가능성(무텍스처·커버리지)에 달렸다"를 시사(결함↔복잡도 약-무상관 r 0.05~0.34). 다음 실험 1순위 = 관측가능성↔결함 상관, 2순위 = B1 메커니즘 점검. 본 런은 그 두 실험 자산이 repo에 이미 있는지 **인벤토리만**(새 계산·학습 금지).
> ⚠ 표기: D9 = overseg-faithfulness(면-받침 진단), D10 = phaseB-b1-mvconsist(L_mvc 학습), D11 = complexity-survey(메트릭 고정).

---

## A. 텍스처·커버리지 지표 [1순위 핵심] — **있음(분할)**

P0 T7/T9/T10/T11 산출이 **건물별 CSV로 잔존**. 전부 `phases/p0-audit/docs/`(+ `G1_package/` 사본).

| 출처(스크립트) | CSV | 동 수 | 핵심 컬럼(관측가능성) |
|---|---|---:|---|
| **T9** `scripts/09_failure_surface_cause.py` | `W3_failure_surface_cause_building_metrics.csv` | **8** (무텍스처 실패) | `near_nadir_view_count·oblique_view_count·near_nadir_texture_gradient_mean·_p10·near_nadir_gray_std·near_nadir_brightness_median·near_nadir_shadow_ratio·oblique_texture_gradient_mean·dim_density_pts_m2·surface_cause_classification` |
| **T7** `scripts/07_failure_diagnosis.py` | `W3_failure_diagnosis_building_metrics.csv` | **79** (실패8+통제) | `view_count·median_incidence_deg·median_in_frame_sample_fraction·occlusion_risk_view_fraction·dim_density_pts_m2·dim_hole_ratio·dim_plane_rmse_m·als_density·als_hole_ratio·als_plane_rmse_m·footprint_area_m2` |
| **T10** `scripts/10_survivor_texture_gap.py` | `W3_survivor_texture_gap_building_metrics.csv` | **71** (survivor) | `image_texture_gradient_median·_p10·image_gray_std_median·image_brightness_median·image_shadow_ratio_median·image_incidence_deg_median·texture_deficit_score` (+ als/dim_plane_f1·delta_plane_f1·nmad) |
| **T11** `scripts/11_survivor_texture_refine.py` | `W3_survivor_texture_refine_building_metrics.csv` | **71** (survivor) | `near_nadir/oblique/all_view_count·sharp_low_texture_pixel_ratio·sharp_gradient_p10·_median·_mean·sharp_gray_std_median·sharp_shadow_ratio_median·sharp_incidence_deg_median` |

**축별 정리:**
- **커버리지 = 11동 전부 닿음**(T7): `view_count·median_incidence_deg·occlusion_risk_view_fraction·median_in_frame_sample_fraction·dim_density·dim_hole_ratio`. → 11동 공통 커버리지 축 **즉시 사용 가능**.
- **텍스처·그림자 = 분할**: T9(실패 8동, `near_nadir_texture_gradient`)와 T11(survivor 71동, `sharp_low_texture_pixel_ratio`/`sharp_gradient`)이 **컬럼 정의가 달라** 11동 단일 텍스처 축이 바로는 없음. → ⓐ T9+T11 근사 조화(불완전) 또는 ⓑ **스크립트 09/11을 11동에 1회 재실행**(아래 재생성).
- **재생성 가용성**(필요 시, 학습 아님·~분): 입력 전부 디스크 존재 — UAV 영상 `data/work/images/Images/`(1899 JPG)·COLMAP 포즈 `data/work/colmap/sparse`·footprint `data/work/footprints/lod2_ground_plan.gpkg`(+ `results/.../footprints_aoi.geojson`). 스크립트 09(`IMAGE_DIR=data/work/images/Images`)·11 재사용 가능.

## B. 결함 지표 [상관의 다른 축] — **있음(정본)**

| 항목 | CSV | 동 수 | 컬럼 |
|---|---|---:|---|
| **D11 dz-강건 best-fit resid** | `results/tum_transfer/mob/overseg_lever/complexity_metric.csv` | 10(d4)/**9(d4+b1)** | `bid·arm·roofType·n_faces·als_levels·als_span_m·gs_stepaware_levels·`**`bestfit_resid`**`·bestfit_dz·joint_dz·shared_resid·shared_frac1·dominance` |

- **`bestfit_resid`(arm=gs_d4_dense / gs_b1_dense) = 관측가능성과 맞붙일 결함 정본**(±1~2.5m off-level의 dz-강건 측정, clamp 제거). d4 10동·b1 9동(4908176 양 arm solid 없음·4908050 b1 solid 없음).
- 값: 42364659 d4 2.65/b1 0.95·4907510 2.56/1.74·4906969 1.60/1.52·4908023 0.82/1.01·42364663 0.50/0.16·4907182 0.55/0.56·4906972 0.26/0.58·42364609 0.13/0.14·4908166 0.04/0.04·4908050 d4 0.06.
- (보조 결함: D11 `als_levels·als_span_m`, [[W_complexity_survey]] §3. DIM측 결함은 T7 `dim_plane_rmse`·T10 `delta_plane_f1`로 71~79동 확장 가능 — 단 GS 결함 아님.)

## C. P0 무텍스처 실패 8동 [관측가능성 극단 표본] — **있음, 단 ⚠ 11동의 부분집합**

- **8동 ID** = `42364609·42364659·42364663·4907182·4907510·4908050·4908166·4908176` (T9 `building_metrics`). 텍스처·커버리지·footprint 전부 닿음(A·T7·T9).
- ⚠ **이 8동은 GS 11동(mob)의 부분집합** — P0 단계서 DIM/MVS 0면 실패했으나 **P2 GS-JSO가 회복**(D-suite assembly)해 현재 gs_d4/gs_b1 보유. **따라서 "8동 추가로 n 11→확대"는 성립 안 함**(이미 11 안에 있음). 가치 = **11동 내부의 저텍스처 극단 표본**(T9가 그 텍스처 수치 제공).
- **n 확대 경로**(상관 표본 키우려면): ⓐ GS 결함을 더 많은 동에 = 추가 GS-JSO 실행(E), 또는 ⓑ **DIM 결함을 결함축으로** = T10 `delta_plane_f1`·T7 `dim_plane_rmse` vs 텍스처(71~79동) — 단 이는 GS 결함 아닌 DIM 품질(T10/T11이 이미 산출: survivor 텍스처↔DIM품질 r≈0, 실패8 r≈0.3).

## D. B1 메커니즘 점검 자산 [2순위] — **있음(즉시 재분석 가능)**

| 항목 | 경로 | 상태 |
|---|---|---|
| D10 B1 ckpt | `results/tum_transfer/mob/gs_b1_{dense,acmp}/ckpt/final.pt` | ✓ |
| D10 B1 의미 TSDF | `results/tum_transfer/mob/tsdf_gs_b1_{dense,acmp}.npz` | ✓ |
| **D10 건물별 GS 지붕면(Roofer Solid)** | `phases/p0-audit/runs/mob_eval/gs_b1_dense/roofer_DEBY_LOD2_*_orig/*.city.jsonl` | ✓ **11동** |
| **D10 건물별 GS 점군** | `phases/p0-audit/runs/mob_eval/gs_b1_dense/DEBY_LOD2_*_orig_classified.las` | ✓ **11동** |
| **D9 면-받침 판정 도구** | `phases/p2-gsjso/scripts/overseg_faithfulness.py` `face_support()`(k=실층/m=가짜, dz정합) | ✓ 실행됨(D11 `complexity_metric.py`서 재사용) |

→ **재학습 없이** 건물별 GS 면 높이 vs ALS 점 높이(k/m·면별 resid)로 "B1이 진짜 구조 잡나 vs 평균 뭉개기" 점검 가능. ⚠ 단 디스크 cityjsonl은 **gssem read-out**이어야(run_b1 gssem→smrf 순차로 smrf가 덮을 수 있음 — D11서 gssem requal로 복원 완료, 현 디스크=gssem). raw ALS = `mob_eval/raw_lidar/`(11동).

## E. 재학습 비용 [스윕 사이징] — **장면 전체 ~5h/arm (건물별 학습 없음)**

- **파이프라인은 건물 단위가 아니라 AOI 장면 전체를 1회 학습**(937프레임·~3.2M 가우시안) → 11동은 그 1회 결과서 평가. 건물별 학습 불가.
- **실측(D10 B1, 30k iter·풀해상도·RTX 3090)**: 학습 **~5.2h/arm**(B1 5h13m, MVC 2번째 렌더로 D4 4.4h보다 ~0.8h↑) + TSDF extract ~2–3분 + eval(건물별 Roofer) ~5분.
- **2-GPU 병렬**: dense+acmp 동시 → 벽시계 ~5.2h. faithfulness 평가는 **dense만** 필요 → GPU 2장에 dense 2설정 동시.
- **w_mvc 스윕 현실 사이징**: 값 1개 = dense 1 arm = ~5h. **2값 동시(2-GPU)** → ~5h, **3값** → ~10h, **4값** → ~10h. 단축 노브: iter 30k→20k(~3.5h, 단 D4 기준 30k와 비교 주의)·`mvc_every=2`(~4.5h). → **현실 스윕 ≈ 3~4칸(값) × 고-결함 표적**(표적은 동 추가 아닌 기존 11동 재사용이므로 칸=값 수).

---

## 종합 — 1순위·2순위 즉시 가능성 (판정 금지)

**1순위 (관측가능성↔결함 상관):**
- **커버리지 축 = 즉시 가능** — T7(11동 공통: view_count·incidence·occlusion_risk·in_frame_fraction·dim_density·hole_ratio) × B(complexity_metric `bestfit_resid`, n=9~10). 새 계산 0.
- **텍스처 축 = 소-선행 필요** — T9(실패8)·T11(survivor3) 컬럼 정의 상이 → 11동 단일 텍스처 지표가 바로 없음. **선행 = ⓐ T9+T11 근사 조화(즉시·불완전) 또는 ⓑ 스크립트 09/11을 11동에 1회 재실행(입력 디스크 존재·학습 아님·~분)**. → **권장: ⓑ로 11동 단일 텍스처 산출 후 상관**(저텍스처 극단 8동 = T9가 이미 있음).
- ⚠ **표본 n = 9~11로 묶임**(8 실패동이 이미 11 안). 더 키우려면 GS-JSO 추가(E) 또는 DIM-결함 프록시(T10, n=71).

**2순위 (B1 메커니즘 점검):**
- **즉시 가능 — 선행 없음.** D10 B1 건물별 Roofer Solid+점군(11동) + D9 `face_support`가 디스크에 있어 **재학습 없이** k(실층)/m(가짜)·면별 resid 재분석 가능. 현 디스크=gssem 확인됨.

**한 줄**: 2순위는 지금 바로 가능; 1순위는 커버리지 축 즉시·**텍스처 축만 11동 단일 지표 1회 재산출(09/11 재실행, 학습 아님) 선행 권장**. 두 실험 다 **추가 GS-JSO 학습 없이 착수 가능**(상관 n 확대만 학습 필요).

> 재현/출처: 본 인벤토리는 읽기 전용 확인. CSV 경로·컬럼은 `phases/p0-audit/docs/`·`results/tum_transfer/mob/overseg_lever/`. 재생성 입력(영상·포즈·footprint)·스크립트(09/11·face_support) 가용. EPSG:25832 · Docker · 관찰만.
