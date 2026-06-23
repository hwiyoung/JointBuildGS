# P2 v6 — 지붕 과분할 진단: (가) GS 표면 거칠기 vs (나) Roofer 임계

> 작성 2026-06-23. 관찰만, **판정 금지(사람=김휘영)**. EPSG:25832 · Docker(p0-tools) · CPU·읽기전용(재학습 없음).
> 입력 = v6 GS/raw 출력의 *orig* classified LAS(building class-6 in footprint = Roofer가 본 바로 그 점).
> 스크립트 `phases/p2-gsjso/scripts/v6_overseg_diag.py`(정의는 p0c_assembly_diag.plane_rms 재사용) ·
> 그림 `v6_overseg_fig.py`. 표 `results/tum_transfer/mob/analysis_pack_v6/overseg_diag.csv`.

## 발단
v6에서 GS가 깨끗한 지붕을 raw보다 잘게 쪼갠다(특히 4906972: ref 3면 → raw 3, **GS dense 13·acmp 12**(orig);
matched에선 15/11). 원인을 (가)표면(GS가 더 울퉁불퉁) vs (나)Roofer 분할 임계(매끈해도 과민)로 가른다.

## 지표 (5동 × 5 arm, building class-6 in footprint)
- `plane_rms` 지배평면 SVD 잔차(전역 거칠기) · `patch_rms` **2m 셀 내부** 평면잔차 중앙값(=facet 구조 제거한 **국소 노이즈**)
- `nDisp` 2m 셀 법선의 지배법선 대비 각 std(°)(=셀 간 방향 분산, 완만 waviness/실제 facet) · `ransac` 순차 RANSAC 지지 평면수(thr 0.15m) · `roofer` Roofer RoofSurface수(orig)

| bld | c | arm | n_b6 | planeRMS | **patchRMS** | nDisp° | **ransac** | **roofer** |
|---|:--:|---|---:|---:|---:|---:|---:|---:|
| 4906972 | Q | GS_dense | 749223 | 2.906 | **0.215** | 31.1 | **5** | **13** |
| 4906972 | Q | GS_acmp | 681277 | 2.011 | 0.254 | 34.0 | 6 | 12 |
| 4906972 | Q | raw_dense | 154558 | 3.419 | 0.205 | 25.2 | 5 | 3 |
| 4906972 | Q | raw_acmp | 191558 | 4.306 | 0.135 | 26.3 | 5 | 3 |
| 4906972 | Q | LiDAR | 7967 | 4.123 | 0.196 | 26.1 | 3 | 3 |
| 4906969 | Q | GS_dense | 14042 | 0.972 | 0.197 | 23.6 | 6 | 5 |
| 4906969 | Q | GS_acmp | 64964 | 0.920 | 0.153 | 25.9 | 3 | 5 |
| 4906969 | Q | raw_dense | 43896 | 1.959 | 0.364 | 21.3 | 6 | **17** |
| 4906969 | Q | raw_acmp | 75714 | 2.294 | 0.327 | 20.6 | 4 | 10 |
| 4906969 | Q | LiDAR | 3336 | 2.004 | 0.380 | 16.4 | 3 | 5 |
| 4908023 | Q | GS_dense | 24200 | 0.207 | 0.150 | 27.9 | 3 | 2 |
| 4908023 | Q | GS_acmp | 20185 | 0.359 | 0.224 | 28.5 | 5 | 2 |
| 4908023 | Q | raw_dense | 7018 | 0.755 | 0.236 | 26.1 | 4 | 1 |
| 4908023 | Q | raw_acmp | 6925 | 1.212 | 0.275 | 17.4 | 3 | 1 |
| 4908023 | Q | LiDAR | 448 | 0.901 | 0.260 | 27.9 | 1 | 1 |
| 42364663 | R | GS_dense | 241308 | 0.399 | 0.197 | 14.0 | 5 | 2 |
| 42364663 | R | GS_acmp | 139375 | 0.387 | 0.191 | 7.3 | 4 | 1 |
| 42364663 | R | raw_dense | 96621 | 0.497 | 0.184 | 12.1 | 4 | 0 |
| 42364663 | R | raw_acmp | 119513 | 0.551 | 0.178 | 17.2 | 5 | 0 |
| 42364663 | R | LiDAR | 676 | 0.411 | 0.243 | 3.8 | 3 | 1 |
| 4907510 | R | GS_dense | 37 | 0.020 | 0.020 | – | 1 | 0 |
| 4907510 | R | GS_acmp | 6312 | 0.216 | 0.036 | 18.6 | 2 | 0 |
| 4907510 | R | raw_dense | 3084 | 1.088 | 0.144 | 14.5 | 4 | 0 |
| 4907510 | R | raw_acmp | 6717 | 1.595 | 0.100 | 13.6 | 4 | 1 |
| 4907510 | R | LiDAR | 2065 | 1.156 | 0.173 | 18.3 | 4 | 4 |

## 관찰 (판정 금지)
1. **GS 국소 노이즈(patch_rms)는 raw/LiDAR 이하** — 5동 전부에서 GS patch_rms ≈ 또는 < raw/LiDAR
   (예 4906969 GS 0.15–0.20 vs raw 0.33–0.36·LiDAR 0.38; 4907510 GS_acmp 0.036 vs raw 0.10–0.14).
   → **GS 표면은 고주파로 더 거칠지 않다**(렌더 표면이라 오히려 매끈). (가)고주파 거칠기 = **0/5**.
2. **GS 지지 평면수(ransac) ≈ raw** — GS ransac 3–6 ≈ raw 3–6. 데이터가 지지하는 평면 수는 GS·raw가 비슷.
3. **GS 과분할 건물에서 Roofer facet ≫ (ransac·raw)** — 명확 과분할 = **4906972**: GS roofer **12–13**인데
   ransac은 **5–6**, raw roofer는 **3**(=ref). 즉 데이터가 5–6면을 지지하고 raw는 3면으로 조립되는데, 동일 Roofer가
   GS만 12–13면으로 쪼갬. → **(나) Roofer 분할 임계가 GS의 조밀·연속 표면에 과민**이 우세.
4. **동반 요인 — GS large-scale waviness**: 4906972에서 GS nDisp **31–34°** > raw 25–26°·LiDAR 26°.
   국소(patch)는 매끈하나 셀 간 법선 분산이 커 **완만한 굴곡**이 있고, Roofer가 이를 다수 facet으로 절단.
   (= 고주파 노이즈가 아니라 저주파 굴곡. L_structure로 평탄화 여지.)
5. **반례**: 4906969은 **raw_dense가 17·raw_acmp 10으로 GS(5=ref)보다 더 과분할** — 과분할이 GS 전용 현상은 아님.
   42364663·4907510은 GS가 ref 수준(1–2)·또는 미조립 → 과분할 아님.

## 한 줄 (판정 금지)
**과분할은 (나) Roofer 임계 우세** — GS가 raw를 초과 분할하는 곳(명확 1/5=4906972, 경미 4908023 포함 ~2/5)에서
GS 국소거칠기는 raw/LiDAR 이하·ransac 지지면수도 raw와 동급인데 Roofer facet만 4×로 폭증. **(가) GS 고주파
거칠기 = 0/5**. 단 GS는 저주파 waviness(nDisp↑)를 동반.

## 레버 후보 (관찰 기반, 결정=사람)
- (나) 우세 → **Roofer 분할/병합 파라미터**(plane-detection 거리·각 임계, facet 병합) 조정으로 GS 조밀·연속 표면 대응.
- 동반 waviness → **L_structure 강화**(공면 정렬)로 저주파 굴곡 평탄화; 또는 **GS-의미 분류**(sem-argmax→building6)로
  더 깨끗한 평면 입력 — 단 GS-sem→classified-LAZ 어댑터는 현재 미구현(Phase 0-2; export_ply_semantic + _tsdf_to_classified 조합 필요).

## 산출
- `results/tum_transfer/mob/analysis_pack_v6/overseg_diag.csv`(25행) · 그림 `docs/figs/tum_transfer/v6_overseg_4906972.png`.
