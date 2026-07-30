# E5 C001 ③a readout 재실행 ablation

> 재확인: GS 학습 0 · GS 레시피 변경 0 · 정본 readout 미변경 · 판정 0. 기존 C001 6런 체크포인트에 readout 파라미터만 바꿔 재점군화, Roofer 재조립, 8-way 재측정했다. CRS는 EPSG:25832.

## 한계

- readout만 본다. 플로터 근원 수리는 ③b(재학습) 대상이다.
- C001 18동·2씨드다. 완화 조합이 순이득으로 보여도 정본 채택은 §11 변경 절차 대상이다.
- 완화는 플로터 유입 대가가 있을 수 있어 coverage와 correctness/ref RMS를 함께 본다.
- `base`도 ③a 산출 경로에서 다시 추출·조립했다. 정본 canonical 산출은 비교 기준으로만 남기고 수정하지 않았다.

## 시작 전 확인

- 브랜치·HEAD: `feat/p2-structure-learn` · `3786ac5db4912d0949742933928fab8f5ec33985`.
- 체크포인트: `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_*_*/ckpt/final.pt` 6개.
- 기존 학습 지문: `phases/p2-gsjso/runs/e5p_train_20260707_C001/train_fingerprints.csv`.
- 정본 조립 입력/기준선: `phases/p0-audit/runs/e5p_gate_20260707_C001`와 `docs/e5_c001_8way_metrics.csv`.
- ② readout 귀속 근거: `docs/W_E5_C001_렌더플로터점검.md`, `docs/e5_c001_render_readout_coverage.csv`.
- 변경한 것은 extractor의 `min_obs`, `voxel`, `SOR`뿐이다. Roofer 설정과 GS-semantic LAS prep은 기존 경로를 그대로 썼다.

## ablation 매트릭스

| setting | minobs | SOR | voxel | alpha | purpose |
|---|---|---|---|---|---|
| base | 3 | on std2 | 0.05 | 0.5 | 정본 기준선 재현 |
| minobs2 | 2 | on std2 | 0.05 | 0.5 | minobs 3->2 관측 게이트 완화 |
| minobs1 | 1 | on std2 | 0.05 | 0.5 | minobs 3->1 게이트 최대 완화 |
| sor_weak | 3 | on std4 | 0.05 | 0.5 | SOR std 비율 완화 |
| sor_off | 3 | off | 0.05 | 0.5 | SOR 생략 |
| voxel03 | 3 | on std2 | 0.03 | 0.5 | voxel 0.05->0.03 해상도 기여 |
| voxel02 | 3 | on std2 | 0.02 | 0.5 | voxel 0.05->0.02 해상도 기여(강) |
| relaxed | 1 | off | 0.03 | 0.5 | minobs1 + SOR off + voxel0.03 완화 조합 |

## 커버리지 회복

| setting | pre | post_minobs | post_sor | drop_minobs | drop_sor |
|---|---|---|---|---|---|
| base | 0.9953 | 0.3081 | 0.1827 | 0.6872 | 0.1254 |
| minobs2 | 0.9953 | 0.6397 | 0.4411 | 0.3556 | 0.1986 |
| minobs1 | 0.9953 | 0.9953 | 0.9524 | 0.0000 | 0.0430 |
| sor_weak | 0.9953 | 0.3081 | 0.2379 | 0.6872 | 0.0702 |
| sor_off | 0.9953 | 0.3081 | 0.3081 | 0.6872 | 0.0000 |
| voxel03 | 0.9952 | 0.1582 | 0.0825 | 0.8370 | 0.0757 |
| voxel02 | 0.9954 | 0.0894 | 0.0588 | 0.9060 | 0.0306 |
| relaxed | 0.9952 | 0.9952 | 0.9952 | 0.0000 | 0.0000 |

## 트레이드오프

| setting | mean_coverage_post_sor | mean_correctness | median_ref_rms_m | has_lod22 | val3dity_valid | coverage_delta_vs_base | correctness_delta_vs_base | median_ref_rms_delta_vs_base | tradeoff_note |
|---|---|---|---|---|---|---|---|---|---|
| base | 0.1827 | 0.5053 | 5.1679 | 74 | 88 | 0.0000 | 0.0000 | 0.0000 | little_coverage_gain |
| minobs2 | 0.4411 | 0.4180 | 4.2668 | 95 | 83 | 0.2584 | -0.0873 | -0.9011 | coverage_gain_with_accuracy_cost |
| minobs1 | 0.9523 | 0.1054 | 17.0527 | 108 | 48 | 0.7696 | -0.3999 | 11.8848 | coverage_gain_with_accuracy_cost |
| sor_weak | 0.2380 | 0.5172 | 4.2632 | 82 | 92 | 0.0553 | 0.0119 | -0.9047 | coverage_gain_small_accuracy_cost |
| sor_off | 0.3081 | 0.5352 | 3.7424 | 82 | 85 | 0.1254 | 0.0299 | -1.4255 | coverage_gain_small_accuracy_cost |
| voxel03 | 0.0825 | 0.7737 | 3.5507 | 32 | 97 | -0.1002 | 0.2684 | -1.6172 | little_coverage_gain |
| voxel02 | 0.0588 | 0.7749 | 2.5186 | 15 | 95 | -0.1239 | 0.2696 | -2.6493 | little_coverage_gain |
| relaxed | 0.9952 | 0.1061 | 18.5744 | 108 | 44 | 0.8125 | -0.3992 | 13.4065 | coverage_gain_with_accuracy_cost |

## 대표 건물

- 60098과 8568391은 ②에서 readout 폐기가 큰 사례로 지정된 두 동이다. 전체 행은 `docs/e5_c001_readout_ablation_representative_buildings.csv`에 둔다.

| building_id | setting | run_name | coverage_pre_minobs | coverage_post_minobs | coverage_post_sor | has_lod22 | correctness | ref_rms_m | shell_bucket |
|---|---|---|---|---|---|---|---|---|---|
| DEBY_LOD2_60098 | base | gs_e5_C001_sparse_r1 | 1.0 | 0.20408163265306123 | 0.0663265306122449 | true | 0.0000 | 11.6023 | 조립 |
| DEBY_LOD2_60098 | base | gs_e5_C001_sparse_r2 | 0.9974489795918368 | 0.3163265306122449 | 0.11096938775510204 | true | 0.0000 | 1.3167 | 조립 |
| DEBY_LOD2_60098 | base | gs_e5_C001_dense_r1 | 1.0 | 0.36989795918367346 | 0.14668367346938777 | true | 0.0000 | 16.2820 | 조립 |
| DEBY_LOD2_60098 | base | gs_e5_C001_dense_r2 | 1.0 | 0.37244897959183676 | 0.09948979591836735 | true | 1.0000 | 8.5475 | 조립 |
| DEBY_LOD2_60098 | base | gs_e5_C001_acmp_r1 | 0.9974489795918368 | 0.475765306122449 | 0.18877551020408162 | true | 0.5000 | 5.4602 | 무효·붕괴 |
| DEBY_LOD2_60098 | base | gs_e5_C001_acmp_r2 | 0.9987244897959183 | 0.4336734693877551 | 0.14668367346938777 | true | 1.0000 | 6.8135 | 조립 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_sparse_r1 | 1.0 | 1.0 | 1.0 | true | 0.0571 | 22.6082 | 무효·붕괴 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_sparse_r2 | 0.9987244897959183 | 0.9987244897959183 | 0.9987244897959183 | true | 0.0645 | 19.0156 | 무효·붕괴 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_dense_r1 | 1.0 | 1.0 | 1.0 | true | 0.0455 | 15.8661 | 무효·붕괴 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_dense_r2 | 1.0 | 1.0 | 1.0 | true | 0.0833 | 15.5170 | 무효·붕괴 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_acmp_r1 | 0.9974489795918368 | 0.9974489795918368 | 0.9974489795918368 | true | 0.1333 | 14.6832 | 조립 |
| DEBY_LOD2_60098 | relaxed | gs_e5_C001_acmp_r2 | 0.9987244897959183 | 0.9987244897959183 | 0.9987244897959183 | true | 0.0408 | 14.0725 | 무효·붕괴 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_sparse_r1 | 1.0 | 0.2850678733031674 | 0.13574660633484162 | true | 0.0000 | 9.9430 | 조립 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_sparse_r2 | 0.995475113122172 | 0.07692307692307693 | 0.0 | false |  |  | 미조립 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_dense_r1 | 1.0 | 0.06334841628959276 | 0.02262443438914027 | true | 0.0000 | 10.8430 | 조립 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_dense_r2 | 1.0 | 0.20361990950226244 | 0.08597285067873303 | true | 1.0000 | 1.3269 | 조립 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_acmp_r1 | 0.995475113122172 | 0.049773755656108594 | 0.01809954751131222 | false |  |  | 미조립 |
| DEBY_LOD2_8568391 | base | gs_e5_C001_acmp_r2 | 1.0 | 0.1085972850678733 | 0.027149321266968326 | true | 0.0000 | 37.8450 | 무효·붕괴 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_sparse_r1 | 1.0 | 1.0 | 1.0 | true | 0.0000 | 13.9668 | 조립 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_sparse_r2 | 0.995475113122172 | 0.995475113122172 | 0.995475113122172 | true | 0.0000 | 16.9087 | 조립 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_dense_r1 | 1.0 | 1.0 | 1.0 | true | 0.0000 | 10.8752 | 조립 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_dense_r2 | 1.0 | 1.0 | 1.0 | true | 0.1000 | 11.9141 | 무효·붕괴 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_acmp_r1 | 0.9909502262443439 | 0.9909502262443439 | 0.9909502262443439 | true | 0.0000 | 33.3513 | 조립 |
| DEBY_LOD2_8568391 | relaxed | gs_e5_C001_acmp_r2 | 1.0 | 1.0 | 1.0 | true | 0.1429 | 14.6450 | 조립 |

## 판별 한 줄

- 판정 아님: readout 완화 조합(relaxed)은 최종 coverage를 0.1827에서 0.9952로 바꿨고, correctness delta=-0.3992, median ref RMS delta=13.4065로 관찰된다.

## ③b 필요 폭

- coverage가 회복되면서 correctness/RMS 대가가 함께 나타난 설정은 readout 단독 완화보다 플로터 근원 수리(distortion 복원, depth 감독 강화, floater/elongation 제어)를 ③b 후보로 남긴다.
- coverage 회복이 작고 품질도 비슷한 설정은 minobs/SOR가 단독 지배 원인이 아니라 렌더 깊이·플로터·SH 흡수와 복합이라는 관찰 재료로 남긴다.
- 어떤 완화 설정이 순이득으로 보이더라도 §11 정본 변경 절차로만 채택 여부를 검토한다.

## 산출

- coverage: `docs/e5_c001_readout_ablation_coverage.csv`.
- filter contribution: `docs/e5_c001_readout_ablation_filter_contrib.csv`.
- metrics: `docs/e5_c001_readout_ablation_metrics.csv`.
- summary/tradeoff: `docs/e5_c001_readout_ablation_summary.csv`, `docs/e5_c001_readout_ablation_tradeoff.csv`.
- inventory/issues: `docs/e5_c001_readout_ablation_inventory.csv`, `docs/e5_c001_readout_ablation_issues.csv`.
- versions: `phases/p2-gsjso/runs/20260708_e5_c001_readout_ablation/versions.txt`, `phases/p0-audit/runs/e5p_readout_ablation_20260708_C001/versions.txt`.
- figures: `docs/figs/e5_c001_readout_ablation/`.

- `docs/figs/e5_c001_readout_ablation/coverage_recovery_summary.png`
- `docs/figs/e5_c001_readout_ablation/coverage_accuracy_scatter.png`
- `docs/figs/e5_c001_readout_ablation/filter_stage_contribution.png`
- `docs/figs/e5_c001_readout_ablation/case_60098_base_vs_relaxed.png`
- `docs/figs/e5_c001_readout_ablation/case_8568391_base_vs_relaxed.png`

## 인용

- ② 회신: `docs/W_E5_C001_렌더플로터점검.md`.
- 분석 연결: `docs/W_E5_C001_렌더플로터_분석·③라우팅_20260707.md`(파일이 있으면 잠금본 우선).
- config 감사: `docs/W_D4_손실config_감사.md` §6.
- 2DGS: [arXiv 2403.17888](https://arxiv.org/abs/2403.17888).
- CityGaussianV2: [arXiv 2411.00771](https://arxiv.org/abs/2411.00771).
