# E5 C001 S2 중간 체크포인트

> 관찰 자료. 승인 대기 없이 다음 작업을 계속한다.

- git head: `4988730`
- A-1 decision: `needs_human_mitigation_choice_before_arm3` — roof height direct-score median 6.170 m in 3-8 m band
- CSV: `docs/e5_c001_s2_monodepth_precheck_building.csv`, `docs/e5_c001_s2_grad_share.csv`, `docs/e5_c001_s2_timeline_roofcrop.csv`

## A-1 Roof Direct Score

| building_id | group_new | roof_height_error_abs_median_m | roof_height_error_abs_p90_m | view_idx |
|---|---|---|---|---|
| DEBY_LOD2_4907184 | 양쪽 성공 6동 | 2.7069 | 5.4241 | 195 |
| DEBY_LOD2_4907185 | 양쪽 성공 6동 | 9.2090 | 12.7069 | 146 |
| DEBY_LOD2_4907198 | 양쪽 성공 6동 | 4.7431 | 9.4393 | 161 |
| DEBY_LOD2_4907202 | 양쪽 성공 6동 | 5.5363 | 6.4914 | 146 |
| DEBY_LOD2_4908168 | 양쪽 성공 6동 | 12.1684 | 14.8789 | 146 |
| DEBY_LOD2_4908178 | 양쪽 성공 6동 | 2.3221 | 3.4173 | 146 |
| DEBY_LOD2_4907199 | 입력 한계 5동/무늬없음·관측됨 3 | 6.8042 | 7.0137 | 161 |
| DEBY_LOD2_8568391 | 입력 한계 5동/무늬없음·관측됨 3 | 0.2814 | 0.8103 | 146 |
| DEBY_LOD2_8568392 | 입력 한계 5동/무늬없음·관측됨 3 | 15.0603 | 15.5965 | 136 |
| DEBY_LOD2_60098 | GS만 실패 5동 | 13.8950 | 16.6374 | 161 |
| DEBY_LOD2_4907186 | GS만 실패 5동 | 8.6836 | 12.9499 | 53 |
| DEBY_LOD2_4907188 | GS만 실패 5동 | 7.9579 | 9.8276 | 160 |
| DEBY_LOD2_4907194 | GS만 실패 5동 | 4.1024 | 5.4542 | 135 |
| DEBY_LOD2_4907195 | GS만 실패 5동 | 4.4054 | 6.2103 | 160 |

## B-0 Gates

| gate_kind | weight | return_code | gate_grad_share_le_040 | gate_ok | selected_weight |
|---|---|---|---|---|---|
| normal | 0.05 | 0 | true | true | 0.05 |

## Completed Timelines

| arm | replicate | step | n_gaussians_in_footprint | z_p50 | opacity_p50 |
|---|---|---|---|---|---|
| arm1 | r1 | 5000 | 15 | 575.1594 | 0.0445 |
| arm1 | r1 | 10000 | 12 | 575.1878 | 0.3934 |
| arm1 | r1 | 15000 | 0 |  |  |
| arm1 | r1 | 20000 | 55 | 582.3704 | 0.0762 |
| arm1 | r1 | 25000 | 55 | 582.3776 | 0.0049 |
| arm1 | r1 | 30000 | 54 | 582.3272 | 0.0039 |
| arm1 | r2 | 5000 | 14 | 575.1576 | 0.1569 |
| arm1 | r2 | 10000 | 7 | 575.8485 | 0.2015 |
| arm1 | r2 | 15000 | 1 | 578.0612 | 0.0100 |
| arm1 | r2 | 20000 | 10 | 581.2889 | 0.0316 |
| arm1 | r2 | 25000 | 10 | 581.2913 | 0.0039 |
| arm1 | r2 | 30000 | 10 | 581.2913 | 0.0039 |

## A-3 Implementation Check

| item | status | value |
|---|---|---|
| elongation_filter_config | checked | enabled=True; axis_ratio_threshold=0.01; active in densification strategy before grow/prune |
| mono_normal_loss_path | checked | src.stage2.renderer.render normal_render -> src.stage2.loss.data_fitting.l_normal absdot; S2 overrides normal_dir with Omnidata world npy maps |
| depth_floor_path | checked | w_depth_eff=max(scheduled_weight, depth_weight_floor) when depth_weight_floor is set; Arm2/Arm3 use 0.15 |
| pointcloud_stage_units | checked | pre/minobs/sor are occupied 0.5m footprint-grid cells from stage_coverage.csv; fp pts is final classified roof/wall point count inside footprint from Roofer prep metrics |
