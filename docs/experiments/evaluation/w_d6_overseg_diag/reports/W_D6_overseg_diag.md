# W_D6 step0 — 곡면 과분할 무결성 점검 + 청정 재진단 (관찰만·판정 금지)

> **관찰만, 판정 = 김휘영.** 브랜치 `feat/p2-d6-curved`. EPSG:25832. Docker(p0-tools / 3dgi/roofer:v1.0.0). 학습 없음(평가·진단만).
> **gssem 정본 · smrf 병기.** 대상 = 곡면 **4906969** (+대조: 복합 **42364659**, 평지붕 **4906972**).
> GS = `gs_d4_{dense,acmp}`(cp-공정 D4, gssem 캐노니컬 디스크). LiDAR = `raw_lidar`. 지붕점 = class=6 ∩ GT 풋프린트 폴리곤.
> 출처: `d6_overseg_diag.py`(a,b) · `d6_roofer_sweep.py`(c) · `d6_density_match.py`+`d6_densmatch_roofer.py`(b×c 보조) · `d6_figs.py` · 실행 `run_d6_step0.sh`.
> 산출(gitignore): `results/tum_transfer/mob/analysis_pack_d6/{overseg_diag_d6,roofer_sweep_d6,density_match_d6,densmatch_roofer_d6}.csv` + `versions_d6.txt`. 그림 `docs/figs/W_D6/`.

## §0 무결성 점검 — v6 과분할 진단은 gssem인가 smrf인가 (코드 증거, 추정 금지)

**결론: v6 과분할 진단(`W3_overseg_diagnosis.md`)은 SMRF 분류 지붕점을 읽었다.** 따라서 그 옛 결론(“(가) GS 고주파 거칠기 = 0/5; (나) Roofer 임계 우세”)은 gssem 정본 기준에서 **‘보류’** 표시한다. 코드 증거:

| # | 증거 | 파일:라인 |
|---|---|---|
| 1 | `v6_overseg_diag.py`는 `mob_eval/<arm>/<bid>_orig_classified.las`(class 6)를 읽음 | `phases/p2-gsjso/scripts/v6_overseg_diag.py:97-104` |
| 2 | `--classifier {smrf,gssem}` 플래그는 **D 수트(커밋 0e43d37)에서 신설**, default=smrf("the v6 default") | `tum_mob_eval.py:84-91` |
| 3 | v6-시점(커밋 3af7bab) `tum_mob_eval.py`엔 `--classifier` 없음 → 단일 `_mob_prep_las.py`만 호출 | `git show 3af7bab:.../tum_mob_eval.py` |
| 4 | `_mob_prep_las.py` = PDAL `filters.smrf`(ground=2) + `filters.overlay`(footprint→building=6) | `_mob_prep_las.py:96-102` |
| 5 | `_mob_prep_las_gssem.py`(GS-의미 argmax)는 “SMRF 대체”로 0e43d37에서 신설 | `_mob_prep_las_gssem.py:2-5` |
| 6 | `run_mob_v6.sh`는 `--classifier` 인자 없이 호출(=smrf) | `run_mob_v6.sh:70-74` |
| 7 | gssem 재평가(`run_gssem_requal.sh`·`run_d5_gssem_requal.sh`)는 **`gs_prior_full_*`·`gs_d4_*`·`gs_d5*`만** 정정; **v6(`gs_seed_*`)는 미정정** | `run_gssem_requal.sh:15-16` |
| 8 | 디스크 확인: v6 `gs_seed_*` LAS mtime = **2026-06-23** < gssem 코드(0e43d37, **2026-06-25**) → smrf 산출일 수밖에 없음; `gs_d4_*` = 06-26(requal) | `stat`·`git show -s 0e43d37` |

→ matched_rms(`W_matched_rms.md`)와 **동형**의 오염: v6 진단 입력이 smrf였다. **단, 본 §1~§4의 gssem 청정 재진단은 v6의 정성 관찰(“GS는 LiDAR보다 거칠지 않다”)을 곡면 4906969·gssem에서 재현**한다(§2). 즉 v6 결론은 분류 정본 기준 ‘보류’이나, 핵심 정성 방향은 뒤집히지 않았다(관찰만).

> ⚠ 맥락 차이: v6 과분할 표적은 **평지붕 4906972**(v6에서 GS 13면≫raw 3). 곡면 4906969는 v6 당시 GS=5=LiDAR(과분할 아님). 곡면 과분할은 **D4 학습 이후 현상**(D5 §5: D4 dense 14·acmp 10 vs LiDAR 5). 그러므로 §1~§4는 곡면을 **신규로** 분해한다.

## §1 청정 재진단 설정

- 대상 3동 × 소스 {GS_dense, GS_acmp}×{gssem 정본, smrf 병기} + LiDAR. 지붕점 = class 6 ∩ 풋프린트 폴리곤(point-in-polygon).
- 격차 정의: 곡면 4906969 = GS **10~14면**(dense 14·acmp 10) vs LiDAR 5면·ref 3(동일 Roofer). 이를 (a)입력거칠기 / (b)밀도·분포 / (c)Roofer 임계로 분해.
- 정합성 sanity: Roofer eps=0.30(=default)에서 GS_dense 4906969 target-only **14**, LiDAR **5** → **D5 §5 수치 재현**.

## §2 (a) 입력 거칠기 — 지역 평면 적합 잔차 (GS vs LiDAR, 동일 1.5 m 셀)

지붕점을 1.5 m 셀로 나눠 셀별 PCA 평면 적합 → 점별 |잔차|. **localRMS**=잔차 RMS, **localP90**=p90, **nDisp**=셀간 법선 분산(°, 저주파 waviness), **planeRMS**=전역 지배평면 잔차.

| 동(set) | 소스 | 분류 | level | n_roof | **localRMS** | **localP90** | nDisp° | planeRMS |
|---|---|---|---|---:|---:|---:|---:|---:|
| 4906969 (곡면) | GS_dense | gssem | orig | 110585 | **0.297** | 0.502 | 21.9 | 2.07 |
| 4906969 | GS_dense | gssem | **lidarD** | 3447 | **0.257** | 0.433 | 23.6 | 2.35 |
| 4906969 | GS_acmp | gssem | orig | 111369 | 0.280 | 0.467 | 21.4 | 1.71 |
| 4906969 | GS_dense | smrf | orig | 109659 | 0.288 | 0.487 | 22.1 | 1.77 |
| 4906969 | GS_acmp | smrf | orig | 93705 | 0.255 | 0.423 | 21.1 | 1.48 |
| 4906969 | **LiDAR** | lidar | orig | 3336 | **0.277** | 0.482 | 17.7 | 2.00 |
| 42364659 (복합) | GS_dense | gssem | orig | 40138 | 0.278 | 0.463 | 10.1 | 1.08 |
| 42364659 | LiDAR | lidar | orig | 265 | 0.058† | 0.070† | 18.6 | 0.56 |
| 4906972 (평지붕) | GS_dense | gssem | orig | 819420 | 0.207 | 0.328 | 27.1 | 2.89 |
| 4906972 | GS_dense | gssem | lidarD | 8178 | 0.145 | 0.227 | 24.8 | 3.48 |
| 4906972 | LiDAR | lidar | orig | 7967 | 0.203 | 0.352 | 26.3 | 4.12 |

(† 복합 42364659 LiDAR는 n=265·구멍 56%로 셀별 적합이 trivial; §3 caveat.)

**관찰 (판정 금지):**
1. **곡면 4906969: GS 국소 거칠기 = LiDAR 수준.** localRMS GS_dense gssem **0.297** ≈ LiDAR **0.277**; **밀도 정합(lidarD) 0.257**도 LiDAR 이하. p90도 동급(0.50 vs 0.48). gssem≈smrf(0.297 vs 0.288). → **GS 고주파 거칠기는 LiDAR 초과 아님**(v6 정성 관찰을 곡면·gssem에서 재현).
2. **저주파 waviness(nDisp)만 소폭 상회:** GS 21.4~22.1° vs LiDAR **17.7°**(+4°). 밀도 정합해도 23.6°(유지). 평지붕은 GS≈LiDAR(27 vs 26).
3. **평지붕 4906972: GS≈LiDAR 거칠기**(0.207 vs 0.203). (D4가 평지붕은 이미 정리 — D5 §5 면수 3=ref.)

## §3 (b) 입력 밀도/분포 — 점밀도·구멍비율 + 밀도→면수 인과 (보조)

| 동 | 소스 | dens(pts/m²) | hole비율(1 m 셀) | 비고 |
|---|---|---:|---:|---|
| 4906969 (곡면) | GS_dense gssem | **637.8** | 0.00 | |
| 4906969 | LiDAR | **19.2** | 0.00 | GS ≈ **33×** 조밀 |
| 42364659 (복합) | GS_dense gssem | 607.2 | 0.02 | |
| 42364659 | LiDAR | 4.0 | **0.56** | LiDAR 희박(265점)→D5 면수 0 |
| 4906972 (평지붕) | GS_dense gssem | 2208.6 | 0.00 | GS ≈ **100×** 조밀 |
| 4906972 | LiDAR | 21.5 | 0.00 | |

**밀도→면수 인과 (밀도 정합 후 동일 Roofer, eps 0.30/0.80):**

| 동 | GS native 면수 | **GS@LiDAR밀도 면수** | LiDAR 면수 |
|---|---:|---:|---:|
| 4906969 (곡면) | 14 (dense)/10 (acmp) | **1 / 1** | 5 |
| 42364659 (복합) | 6 | 0 (no planes) | 0 |
| 4906972 (평지붕) | 3 | 1 | 3 |

**관찰 (판정 금지):**
1. **GS 면수는 밀도에 강하게 의존.** 곡면 GS를 LiDAR 밀도로 솎으면 14→**1**(평지붕 3→1). 즉 14면은 **조밀 샘플링에 결합**돼 있고, 밀도 불변의 고유 waviness가 아니다(v6 평지붕은 밀도 정합 후에도 17 유지였던 것과 대비 — D4 학습이 표면을 더 펴 솎으면 붕괴).
2. **단, 균일 voxel 다운샘플은 곡면을 과평탄화**(GS@LiDAR밀도 1면 < LiDAR 5면)하여 LiDAR 거동을 **재현하지 못함** → 이 보조시험은 격차를 **‘밀도 결합’으로 한정(bound)**할 뿐 LiDAR 등가를 입증하진 않음. 또한 GS@LiDAR밀도 `rf_roof_type`=slanted(1면)인데 LiDAR eps0.3는 `multiple horizontal`(5면) → **형상 해석 자체가 다를 수 있음**(아래 §3 caveat).
3. 구멍비율: 곡면·평지붕 GS·LiDAR 모두 ≈0(분포 결손 아님). 복합 LiDAR만 56% 구멍(희박).

> ⚠ **caveat (관찰 범위):** 본 진단은 **카운트 기반**(면수·평면수·집계 잔차)이며 GS 14면 vs LiDAR 5면의 **면-기하 공간 중첩은 미수행**. 따라서 GS가 실제 건축 특징(능선/단)을 한 평면으로 뭉개거나 그 반대인지(표면-형상 해석 차이)는 본 step0로 배제되지 않음 — 이는 step0 범위 밖(후속 면-기하 대조 필요).

## §4 (c) Roofer 민감도 — 동일 임계를 GS·LiDAR 양쪽에 적용 (target-only 면수)

`--plane-detect-epsilon` 스윕(GS·LiDAR 동일값). + `--plane-detect-min-points`(region-grow) 프로브.

**epsilon 스윕 (target-only 면수):**

| 동 | 소스 | e0.2 | e0.3 | e0.5 | e0.8 | e1.2 |
|---|---|---:|---:|---:|---:|---:|
| 4906969 (곡면, ref 3·LiDAR 5) | GS_dense | 16 | **14** | 12 | 11 | **9** |
| 4906969 | GS_acmp | 12 | 10 | 10 | 8 | 9 |
| 4906969 | **LiDAR** | 6 | **5** | 4 | 4 | 3 |
| 42364659 (복합, ref 2) | GS_dense | 6 | 6 | 5 | 5 | 4 |
| 42364659 | LiDAR | 0 | 0 | 0 | 0 | 0 |
| 4906972 (평지붕, ref 3) | GS_dense | 6 | 3 | 3 | 3 | 2 |
| 4906972 | LiDAR | 3 | 3 | 2 | 2 | 2 |

**min-points 프로브 (곡면, eps=0.30):**

| 소스 | mp 15 | mp 30 | mp 60 |
|---|---:|---:|---:|
| GS_dense | 14 | 16 | 12 |
| GS_acmp | 10 | 10 | 9 |
| LiDAR | 5 | 5 | 5 |

**관찰 (판정 금지):**
1. **곡면 GS-LiDAR 격차(비율)는 Roofer 임계에 둔감.** eps 0.2→1.2(6배)로 풀면 **GS·LiDAR가 함께** 내려가나(GS_dense **16→9에서 바닥**·GS_acmp 8~9; LiDAR 6→3) **격차는 선택적으로 좁혀지지 않음** — 매 eps에서 GS_dense ≈ **2.7~3×**·GS_acmp ≈ **2×** LiDAR. GS는 **9에서 바닥(>LiDAR 5)**. → **느슨하게 풀면 GS가 5 위에서 바닥난다**(14→5 수렴 아님). 즉 전역 임계는 절대 면수만 둔화시킬 뿐 GS의 초과분을 제거 못함.
2. min-points(region-grow)도 무관: GS_dense 14/16/12, LiDAR 5/5/5.
3. 대조: 평지붕은 eps 0.3에서 GS 3≈LiDAR 3(이미 정합); 복합은 LiDAR 자체가 미조립(희박)이라 GS 6 vs LiDAR 0(밀도 비대칭).

## §5 그림 (docs/figs/W_D6/)
- [4906969_gssem_vs_lidar.png](../../../figs/W_D6/4906969_gssem_vs_lidar.png) — (좌) 곡면 지붕 y-슬라이스 단면 GS vs LiDAR(같은 표면·GS 조밀); (우) 국소 평면잔차 분포 GS native·GS@LiDAR밀도·LiDAR **중첩**(GS 안 거침).
- [facets_vs_epsilon.png](../../../figs/W_D6/facets_vs_epsilon.png) — (c) 3동 면수 vs epsilon: 곡면에서 GS·LiDAR 함께 내려가나 GS가 9에서 바닥(>LiDAR 5), 격차 비율 보존(임계로 미해소).

## §6 한 줄 관찰 — 레버 지시 (판정 금지)

**격차 주성분 = 입력측(GS).** 곡면 4906969의 GS **10~14면**(dense 14·acmp 10) vs **LiDAR 5면**(CityGML ref=3) 격차는 — (a) **고주파 거칠기 아님**(GS localRMS 0.30 ≈ LiDAR 0.28, 밀도 정합 0.26), (b) **Roofer 분할 임계(epsilon/min-points) 단독 아님**(eps 0.2~1.2·min-points 15~60 전 구간에서 GS는 9에서 바닥·GS≥~2×LiDAR; 임계는 절대 면수만 둔화) — 이며, GS의 **조밀 샘플링(33×) × 완만한 곡면/waviness**(nDisp +4°)가 Roofer **원시 평면검출**(rf_roof_planes: 곡면 GS 22 vs LiDAR 4 — 병합 전, 14-vs-5 면수와 구분)을 다수화하는 데 결합돼 있다(밀도 솎으면 14→1 붕괴 = 밀도 결합; 단 §3.2대로 LiDAR 5 재현은 아님 = 한정적 증거).

**따라서 D6 레버는 입력측(GS)이 관찰상 지시됨** — 곡률/밀도 인지 제어(예: 곡률 기반 G2 구조 정렬·공면화, 또는 밀도/곡률 인지 read-out). **Roofer 분할 임계 노브(epsilon/min-points) 단독은 비지시**(전역 둔화·정확도 손실, 초과분 미제거). 단 격차는 **GS 밀도 × Roofer 평면검출 민감성의 상호작용**일 수 있고(Roofer 밀도민감성 자체는 본 step0로 배제 안 됨), 이 경우에도 임계 노브로는 못 닫고 단순 솎기는 과교정(→1)이므로 **작동 레버는 입력측(GS 곡률/밀도)으로 수렴**한다. (D5 §5의 두 후보 ‘곡률 기반 G2 / Roofer 분할 임계’ 중 **입력측·곡률 쪽**을 지시. 판정 줄 = 김휘영.)

## §7 재현 / 출처
- 실행: `bash phases/p2-gsjso/scripts/run_d6_step0.sh`(idempotent: smrf 재분류→a,b→c). provenance `analysis_pack_d6/versions_d6.txt`.
- (a,b): `d6_overseg_diag.py`(p0-tools, numpy/laspy/matplotlib·scipy 미사용). smrf 병기 = `_mob_prep_las.py`로 GS를 SMRF 재분류(temp `_d6_smrf_tmp`; gssem 캐노니컬 디스크 무변경, deterministic).
- (c): `d6_roofer_sweep.py`(host→P0 compose roofer). target-only 면수 = `d5_target_facets` 로직(cid==full or startswith(full+'-')). 보조 b×c: `d6_density_match.py`(voxel→LiDAR밀도, v6 bisection 재사용)+`d6_densmatch_roofer.py`.
- baseline 재사용: D5 §5 면수·LiDAR(`d5_target_facets.csv`·`baselines.json`). EPSG:25832 · Docker · 학습/D5 무중단 · gssem 캐노니컬 디스크 무변경 · 관찰만.
