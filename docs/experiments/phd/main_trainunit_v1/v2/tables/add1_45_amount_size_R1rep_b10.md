addendum 1 items 4-5: iterations per training image = 30,000 / training images; radius used = extent_override.json used_radius written by the run (fork getNerfppNorm over the training cameras, addendum 12 record); radius_from_cameras_json_all = same rule over cameras.json (train + test) for reference; clone/split threshold 0.01 r, big-Gaussian prune 0.1 r

| site | plan | unit | train_images | cameras_json_all | iterations | iterations_per_image | radius_from_cameras_json_all_m | fork_radius_train_m | radius_fixed | radius_used_m | clone_split_threshold_m | big_gaussian_prune_m | run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1rep_b10 | 건물단위_s0 | R1repef_ALS_s0 | 333 | 382 | 30000 | 90.09 | 229.6 | 229.7 | False | 229.7 | 2.297 | 22.97 | /tu1/runs/ef/R1repef_ALS_s0/attempt1 |
| R1rep_b10 | 건물단위_s1 | R1repef_ALS_s1 | 333 | 382 | 30000 | 90.09 | 229.6 | 229.7 | False | 229.7 | 2.297 | 22.97 | /tu1/runs/ef/R1repef_ALS_s1/attempt1 |
| R1rep_b10 | 전체 | campus | 819 | 937 | 30000 | 36.63 | 317.2 | 317.1 | False | 317.1 | 3.171 | 31.71 | /tu1/runs/ef/campusef30k_ALS_s0/attempt2 |
| R1rep_b10 | 넷 | 넷 칸 1 | 471 | 525 | 30000 | 63.69 | 281.6 | 282.1 | False | 282.1 | 2.821 | 28.21 | /tu1/runs/ef/cellsef_ALS_s0_cell1/attempt3 |
| R1rep_b10 | 넷 | 넷 칸 2 | 544 | 597 | 30000 | 55.15 | 225.7 | 228 | False | 228 | 2.28 | 22.8 | /tu1/runs/ef/cellsef_ALS_s0_cell2/attempt3 |
| R1rep_b10 | 넷 | 넷 칸 3 | 324 | 362 | 30000 | 92.59 | 199.6 | 199.2 | False | 199.2 | 1.992 | 19.92 | /tu1/runs/ef/cellsef_ALS_s0_cell3/attempt2 |
| R1rep_b10 | 아홉 | 아홉 칸 4 | 466 | 495 | 30000 | 64.38 | 204.6 | 204.6 | False | 204.6 | 2.046 | 20.46 | /tu/runs/cells9ef_ALS_s0_cell4/attempt1 |
| R1rep_b10 | 아홉 | 아홉 칸 5 | 207 | 226 | 30000 | 144.9 | 183.6 | 184 | False | 184 | 1.84 | 18.4 | /tu/runs/cells9ef_ALS_s0_cell5/attempt2 |
| R1rep_b10 | 아홉 | 아홉 칸 6 | 217 | 236 | 30000 | 138.2 | 204.6 | 202.7 | False | 202.7 | 2.027 | 20.27 | /tu/runs/cells9ef_ALS_s0_cell6/attempt1 |
| R1rep_b10 | 아홉 | 아홉 칸 7 | 233 | 255 | 30000 | 128.8 | 182.3 | 182 | False | 182 | 1.82 | 18.2 | /tu/runs/cells9ef_ALS_s0_cell7/attempt1 |
