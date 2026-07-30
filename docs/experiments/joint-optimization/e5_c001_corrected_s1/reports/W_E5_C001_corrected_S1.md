# E5 C001 corrected-S1 표면 복원 공정 재시험

> 관찰 자료. 정본 S0 미변경, 판정 0. corrected-S1은 S1의 깨진 표면 모으기 정규화와 prune 작동을 수리한 재학습 3런이다.

## Step 0 · 표면 모으기 정규화

- 채택: `distort_normalization=scene_scale_sq`, `distort_norm_denominator=1453.980473`, `w_distort=100`.
- S1 실행본의 `scene_extent_sq` 대비 분모가 93252.6 -> 1453.98로 줄어 distortion 항이 실제 손실에 들어왔다.
- tail(20k 이후) distortion share 중앙값: acmp 3.195%, dense 2.970%, sparse 3.444%. 사전 목표 5~15%에는 못 미쳐 `docs/issues.md`에 관찰 이슈로 남겼다.
- 짝 그림: `docs/figs/e5_c001_corrected_s1/corrected_s1_distort_share.png`, `docs/figs/e5_c001_corrected_s1/corrected_s1_depth_share.png`.

## Step 1 · prune/seed-protect 수리

- 채택: `seed_protect_until_iter=5000`, `prune_opa=0.05`, `final_prune_opa=0.05`; prune/grow 카운터와 final prune 값을 ckpt/effective config/CSV에 기록.
- 최종 `opacity<0.005` 및 `opacity<0.05`는 세 arm 모두 0으로 떨어졌다. final prune 절대 개수는 sparse 130224, dense 101484, acmp 113040.
- 짝 그림: `docs/figs/e5_c001_corrected_s1/corrected_s1_low_opacity_after_final_prune.png`, `docs/figs/e5_c001_corrected_s1/corrected_s1_s1_vs_corrected_pointcloud_panel.png`.

| arm | final_n | opacity<0.05 | axis_ratio>10 | cum_pruned | final_pruned |
|---|---|---|---|---|---|
| sparse | 543962 | 0 (0.000) | 155025 (0.285) | 1747780 | 130224 |
| dense | 428848 | 0 (0.000) | 98546 (0.230) | 1837810 | 101484 |
| acmp | 524697 | 0 (0.000) | 177061 (0.337) | 1610790 | 113040 |

## Step 3 · 8-way 관찰

- base corrected-S1 요약: has_lod22 30/54, val3dity_valid 41/54, median ref RMS 4.323 m, mean post-SOR coverage 0.151.
- voxel02 천장 시험: has_lod22 8/54, val3dity_valid 34/54, median ref RMS 3.129 m.
- S1 대비 corrected-S1은 저불투명 가우시안은 제거했지만, readout coverage/has_lod22/RMS는 세 arm 모두 퇴행했다. 이는 판정이 아니라 다음 원인 감사 재료다.
- 짝 그림: `docs/figs/e5_c001_corrected_s1/corrected_s1_delta_summary.png`, `docs/figs/e5_c001_corrected_s1/corrected_s1_validity_by_arm.png`, `docs/figs/e5_c001_corrected_s1/corrected_s1_route_ref_rms.png`, `docs/figs/e5_c001_corrected_s1/readout/coverage_accuracy_scatter.png`.

| arm | coverage S0/S1/corr | median RMS S0/S1/corr | valid S0/S1/corr | has_lod22 S0/S1/corr |
|---|---|---|---|---|
| sparse | 0.112/0.236/0.143 | 6.828/2.898/7.621 | 14/17/16 | 9/12/10 |
| dense | 0.103/0.243/0.146 | 7.123/1.807/4.282 | 15/17/15 | 8/11/9 |
| acmp | 0.128/0.289/0.163 | 4.617/3.852/4.177 | 15/6/10 | 9/14/11 |

## 건물별 표적 관찰

- 정상/무늬 지붕은 일부 저RMS를 유지하지만 valid-solid와 roof-plane 구성에서 퇴행·무효가 남았다.
- DEFECT 5동은 dense 기준에서 사진측량 수준으로 안정적으로 조여졌다고 보기 어렵다. 60098은 corrected dense 3.557 m로 S1 dense 대비 악화했다.
- 무텍스처-관측 3동은 corrected-S1 성공선에 넣지 않는다. 상태만 기록한다.
- 짝 그림 패널: `docs/figs/e5_c001_corrected_s1/panel_normal_4907184.png`, `docs/figs/e5_c001_corrected_s1/panel_defect_60098.png`, `docs/figs/e5_c001_corrected_s1/panel_textureless_observed_8568391.png`.

| route | building | raw_dense | S1 | corrected | LiDAR |
|---|---|---|---|---|---|
| normal | 4907184 | 0.355 | 0.354 | 0.342 | 3.009 |
| normal | 4908168 | 0.179 | 0.735 |  | 0.098 |
| normal | 4907202 | 0.564 | 0.389 |  | 1.014 |
| normal | 4907198 | 2.127 | 1.495 | 1.200 | 0.186 |
| normal | 4907185 | 2.614 | 1.807 | 4.282 | 0.268 |
| normal | 4908178 | 0.625 | 0.649 | 3.332 | 0.997 |
| defect | 4907186 | 3.544 | 12.662 | 5.299 | 0.407 |
| defect | 4907188 | 1.354 | 6.846 | 19.004 | 0.174 |
| defect | 4907194 |  | 10.517 |  |  |
| defect | 4907195 | 0.270 | 5.497 | 6.163 | 0.251 |
| defect | 60098 | 2.992 | 5.721 | 3.557 | 2.817 |
| textureless_observed | 4907199 |  |  | 17.077 | 0.032 |
| textureless_observed | 8568391 |  |  |  | 0.036 |
| textureless_observed | 8568392 |  |  |  | 0.104 |

## CSV 산출

- loss: `docs/e5_c001_corrected_s1_loss.csv`
- densification/prune: `docs/e5_c001_corrected_s1_densification.csv`
- building 8-way: `docs/e5_c001_corrected_s1_building_8way.csv`
- validity breakdown: `docs/e5_c001_corrected_s1_validity_breakdown.csv`
- delta: `docs/e5_c001_corrected_s1_delta.csv`
- target observations: `docs/e5_c001_corrected_s1_target_observations.csv`

## 이슈·지문

| part | severity | message | path |
|---|---|---|---|

| arm | gpu | elapsed_min | seed | ckpt_sha256 |
|---|---|---|---|---|
| sparse | 0 | 78.8 | 2001 | f17643256bd4cc60 |
| dense | 1 | 61.3 | 2001 | 20b5dd92e4ddafb4 |
| acmp | 1 | 64.7 | 2001 | 23e349a7d8222169 |

- train fingerprints: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1/train_fingerprints.csv`.
- readout fingerprints: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1/readout_fingerprints.csv`.
- versions: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1/versions.txt`.
- snapshots: `phases/p2-gsjso/runs/e5_c001/20260709_e5_c001_corrected_s1/snapshots`.
- 재확인: corrected-S1 재학습 3런, 정본 미변경, 판정 0.
