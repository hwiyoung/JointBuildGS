addendum 1 items 4-5: iterations per training image = 30,000 / training images; radius used = extent_override.json used_radius written by the run (fork getNerfppNorm over the training cameras, addendum 12 record); radius_from_cameras_json_all = same rule over cameras.json (train + test) for reference; clone/split threshold 0.01 r, big-Gaussian prune 0.1 r

| site | plan | unit | train_images | cameras_json_all | iterations | iterations_per_image | radius_from_cameras_json_all_m | fork_radius_train_m | radius_fixed | radius_used_m | clone_split_threshold_m | big_gaussian_prune_m | run |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B173nb_b10 | 건물단위_s0 | B173nbef_ALS_s0 | 203 | 232 | 30000 | 147.8 | 272.9 | 272.4 | False | 272.4 | 2.724 | 27.24 | /tu1/runs/ef/B173nbef_ALS_s0/attempt1 |
| B173nb_b10 | 건물단위_s1 | B173nbef_ALS_s1 | 203 | 232 | 30000 | 147.8 | 272.9 | 272.4 | False | 272.4 | 2.724 | 27.24 | /tu1/runs/ef/B173nbef_ALS_s1/attempt1 |
| B173nb_b10 | 전체 | campus | 819 | 937 | 30000 | 36.63 | 317.2 | 317.1 | False | 317.1 | 3.171 | 31.71 | /tu1/runs/ef/campusef30k_ALS_s0/attempt2 |
| B173nb_b10 | 넷 | 넷 칸 2 | 544 | 597 | 30000 | 55.15 | 225.7 | 228 | False | 228 | 2.28 | 22.8 | /tu1/runs/ef/cellsef_ALS_s0_cell2/attempt3 |
| B173nb_b10 | 넷 | 넷 칸 3 | 324 | 362 | 30000 | 92.59 | 199.6 | 199.2 | False | 199.2 | 1.992 | 19.92 | /tu1/runs/ef/cellsef_ALS_s0_cell3/attempt2 |
| B173nb_b10 | 아홉 | 아홉 칸 7 | 233 | 255 | 30000 | 128.8 | 182.3 | 182 | False | 182 | 1.82 | 18.2 | /tu/runs/cells9ef_ALS_s0_cell7/attempt1 |
| B173nb_b10 | 아홉 | 아홉 칸 8 | 217 | 241 | 30000 | 138.2 | 157.4 | 158.8 | False | 158.8 | 1.588 | 15.88 | /tu/runs/cells9ef_ALS_s0_cell8/attempt2 |
