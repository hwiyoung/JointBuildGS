# t4_A_fusion

4.1절. 방법 A(COLMAP stereo_fusion 기본값). 영상마다 살아남은 화소 비율 = 살아남은 화소 / 유효 깊이 화소. 실제 값은 fusion.log 에서 읽음.

scientific_verdict: null

| 작업 공간 | 융합 점 | 영상(깊이 있음) | 살아남은 화소 / 유효 | 영상마다 비율 최소·10·25·50·75·90 %·최대 / 평균 |
|---|---|---|---|---|
| campus | 11,746,886 | 819 (815) | 93,645,352 / 502,237,168 (18.6 %) | 1.5 · 15.6 · 17.3 · 18.7 · 19.9 · 21.0 · 25.2 / 18.3 |
| box_B0_b10 | 3,366,019 | 243 (243) | 24,581,925 / 135,571,341 (18.1 %) | 6.0 · 15.3 · 16.8 · 18.4 · 19.3 · 20.5 · 24.3 / 17.9 |
| box_B173nb_b10 | 2,638,300 | 203 (203) | 20,576,834 / 113,931,925 (18.1 %) | 3.4 · 14.2 · 16.4 · 18.0 · 19.5 · 20.9 · 22.3 / 17.6 |
| box_R1rep_b10 | 4,759,329 | 338 (333) | 36,850,950 / 198,024,768 (18.6 %) | 3.9 · 15.2 · 17.1 · 18.7 · 19.9 · 20.9 · 25.0 / 18.3 |

실제로 쓰인 값(fusion.log):

- campus: mask_path "", max_image_size -1, min_num_pixels 5, max_num_pixels 10000, max_traversal_depth 100, max_reproj_error 2, max_depth_error 0.01, max_normal_error 10, check_num_images 50, use_cache 0, cache_size 32, bbox_min -3.40282e+38 -3.40282e+38 -3.40282e+38, bbox_max 3.40282e+38 3.40282e+38 3.40282e+38
- box_B0_b10: mask_path "", max_image_size -1, min_num_pixels 5, max_num_pixels 10000, max_traversal_depth 100, max_reproj_error 2, max_depth_error 0.01, max_normal_error 10, check_num_images 50, use_cache 0, cache_size 32, bbox_min -3.40282e+38 -3.40282e+38 -3.40282e+38, bbox_max 3.40282e+38 3.40282e+38 3.40282e+38
- box_B173nb_b10: mask_path "", max_image_size -1, min_num_pixels 5, max_num_pixels 10000, max_traversal_depth 100, max_reproj_error 2, max_depth_error 0.01, max_normal_error 10, check_num_images 50, use_cache 0, cache_size 32, bbox_min -3.40282e+38 -3.40282e+38 -3.40282e+38, bbox_max 3.40282e+38 3.40282e+38 3.40282e+38
- box_R1rep_b10: mask_path "", max_image_size -1, min_num_pixels 5, max_num_pixels 10000, max_traversal_depth 100, max_reproj_error 2, max_depth_error 0.01, max_normal_error 10, check_num_images 50, use_cache 0, cache_size 32, bbox_min -3.40282e+38 -3.40282e+38 -3.40282e+38, bbox_max 3.40282e+38 3.40282e+38 3.40282e+38
