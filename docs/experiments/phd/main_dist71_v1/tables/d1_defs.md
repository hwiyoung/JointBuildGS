# 일 1. 정의 확인 (PHD-MAIN-DIST71-v1)

- 만든 때 2026-10-17 02:08:20 KST, 스크립트 `scripts/phd/main_dist71_v1/d1_defs.py`. 6.5·6.6 사실 확인(FACTS65, `docs/experiments/phd/ch6_facts65_v2/facts_6_5_6_6.md`, 커밋 f556b072)이 답한 물음은 그 줄 번호와 함께 옮기고, 그 표에 없던 수만 새로 셌다[새로 셈].

## 결과 메시

| 경우 | 방법 | 결과 | 학습 시점 메시 | 있음 (GB) | 가상 시점 메시 | 있음 |
|---|---|---|---|---|---|---|
| B0 · LoD2 | 본 방법 | `prop_LoD2_s0` | `S1/stage1/B0_b10/prop_LoD2_s0/post/mesh_tsdf.ply` | 있음 (0.93) | `S1/stage1/B0_b10/prop_LoD2_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | 본 방법 | `prop_LoD2_s1` | `S1/stage1/B0_b10/prop_LoD2_s1/post/mesh_tsdf.ply` | 있음 (0.93) | `S1/stage1/B0_b10/prop_LoD2_s1/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | 2DGS | `imgonly_2dgs_s0` | `SB/runs/B0_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (1.91) | `SB/runs/B0_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | GeoGS | `trust_LoD2_fix1` | `SF/runs/B0_b10/trust_LoD2_fix1/post/mesh_tsdf.ply` | 있음 (1.61) | `SF/runs/B0_b10/trust_LoD2_fix1/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | 결합 | `mvsfuse_LoD2` | `SB/runs/B0_b10/mvsfuse_LoD2/post/mesh_tsdf.ply` | 있음 (0.73) | `SL/work/virtual/B0_b10/mvsfuse_LoD2/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | CDGS | `cdgsnofit_LoD2_s0` | `SL/runs/B0_b10/cdgsnofit_LoD2_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/B0_b10/cdgsnofit_LoD2_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · LoD2 | 사전 정보 | `samepath_LoD2` | `S1/stage1/B0_b10/samepath_LoD2/mesh.ply` | 있음 (0.28) | `SL/work/virtual/B0_b10/samepath_LoD2/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | 본 방법 | `prop_ALS_s0` | `S1/stage1/B0_b10/prop_ALS_s0/post/mesh_tsdf.ply` | 있음 (0.9) | `S1/stage1/B0_b10/prop_ALS_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | 본 방법 | `prop_ALS_s1` | `S1/stage1/B0_b10/prop_ALS_s1/post/mesh_tsdf.ply` | 있음 (0.9) | `S1/stage1/B0_b10/prop_ALS_s1/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | 2DGS | `imgonly_2dgs_s0` | `SB/runs/B0_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (1.91) | `SB/runs/B0_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | GeoGS | `geogs_ALS_fix1` | `SB/runs/B0_b10/geogs_ALS_fix1/post/mesh_tsdf.ply` | 있음 (2.03) | `SB/runs/B0_b10/geogs_ALS_fix1/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | 결합 | `mvsfuse_ALS` | `SB/runs/B0_b10/mvsfuse_ALS/post/mesh_tsdf.ply` | 있음 (1.01) | `SL/work/virtual/B0_b10/mvsfuse_ALS/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | CDGS | `cdgsnofit_ALS_s0` | `SL/runs/B0_b10/cdgsnofit_ALS_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/B0_b10/cdgsnofit_ALS_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B0 · 항공 LiDAR | 사전 정보 | `samepath_ALS` | `S1/stage1/B0_b10/samepath_ALS/mesh.ply` | 있음 (0.86) | `SL/work/virtual/B0_b10/samepath_ALS/mesh_virtual.ply` | 없음 |
| B173 주변 · LoD2 | 본 방법 | `prop_LoD2_s0` | `S0/stage0/b1_LoD2/post/mesh_tsdf.ply` | 있음 (1.02) | `MF/virtual/option2/b1_LoD2/mesh_virtual.ply` | 있음 |
| B173 주변 · LoD2 | 본 방법 | `prop_LoD2_s1` | `S0/stage0/b2_LoD2/post/mesh_tsdf.ply` | 있음 (1.02) | `MF/virtual/option2/b2_LoD2/mesh_virtual.ply` | 있음 |
| B173 주변 · LoD2 | 2DGS | `imgonly_2dgs_s0` | `SB/runs/B173nb_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (1.51) | `SB/runs/B173nb_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 있음 |
| B173 주변 · LoD2 | GeoGS | `trust_LoD2_fix1` | `SF/runs/B173nb_b10/trust_LoD2_fix1/post/mesh_tsdf.ply` | 있음 (1.55) | `SF/runs/B173nb_b10/trust_LoD2_fix1/gpu/virtual/mesh_virtual.ply` | 있음 |
| B173 주변 · LoD2 | 결합 | `mvsfuse_LoD2` | `SB/runs/B173nb_b10/mvsfuse_LoD2/post/mesh_tsdf.ply` | 있음 (0.89) | `SL/work/virtual/B173nb_b10/mvsfuse_LoD2/mesh_virtual.ply` | 있음 |
| B173 주변 · LoD2 | CDGS | `cdgsnofit_LoD2_s0` | `SL/runs/B173nb_b10/cdgsnofit_LoD2_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/B173nb_b10/cdgsnofit_LoD2_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B173 주변 · LoD2 | 사전 정보 | `samepath_LoD2` | `MT/gpu/samepath_LoD2/mesh.ply` | 있음 (0.45) | `SL/work/virtual/B173nb_b10/samepath_LoD2/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | 본 방법 | `prop_ALS_s0` | `S0/stage0/b1_ALS/post/mesh_tsdf.ply` | 있음 (1.0) | `MF/virtual/option2/b1_ALS/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | 본 방법 | `prop_ALS_s1` | `S0/stage0/b2_ALS/post/mesh_tsdf.ply` | 있음 (1.01) | `MF/virtual/option2/b2_ALS/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | 2DGS | `imgonly_2dgs_s0` | `SB/runs/B173nb_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (1.51) | `SB/runs/B173nb_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | GeoGS | `geogs_ALS_fix1` | `SB/runs/B173nb_b10/geogs_ALS_fix1/post/mesh_tsdf.ply` | 있음 (1.56) | `SB/runs/B173nb_b10/geogs_ALS_fix1/gpu/virtual/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | 결합 | `mvsfuse_ALS` | `SB/runs/B173nb_b10/mvsfuse_ALS/post/mesh_tsdf.ply` | 있음 (1.09) | `SL/work/virtual/B173nb_b10/mvsfuse_ALS/mesh_virtual.ply` | 있음 |
| B173 주변 · 항공 LiDAR | CDGS | `cdgsnofit_ALS_s0` | `SL/runs/B173nb_b10/cdgsnofit_ALS_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/B173nb_b10/cdgsnofit_ALS_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| B173 주변 · 항공 LiDAR | 사전 정보 | `samepath_ALS` | `MT/gpu/samepath_ALS/mesh.ply` | 있음 (0.94) | `SL/work/virtual/B173nb_b10/samepath_ALS/mesh_virtual.ply` | 있음 |
| R1 · LoD2 | 본 방법 | `prop_LoD2_s0` | `S1/stage1/R1rep_b10/prop_LoD2_s0/post/mesh_tsdf.ply` | 있음 (1.08) | `S1/stage1/R1rep_b10/prop_LoD2_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | 본 방법 | `prop_LoD2_s1` | `S1/stage1/R1rep_b10/prop_LoD2_s1/post/mesh_tsdf.ply` | 있음 (1.09) | `S1/stage1/R1rep_b10/prop_LoD2_s1/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | 2DGS | `imgonly_2dgs_s0` | `SB/runs/R1rep_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (2.17) | `SB/runs/R1rep_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | GeoGS | `trust_LoD2_fix1` | `SF/runs/R1rep_b10/trust_LoD2_fix1/post/mesh_tsdf.ply` | 있음 (2.07) | `SF/runs/R1rep_b10/trust_LoD2_fix1/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | 결합 | `mvsfuse_LoD2` | `SB/runs/R1rep_b10/mvsfuse_LoD2/post/mesh_tsdf.ply` | 있음 (1.09) | `SL/work/virtual/R1rep_b10/mvsfuse_LoD2/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | CDGS | `cdgsnofit_LoD2_s0` | `SL/runs/R1rep_b10/cdgsnofit_LoD2_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/R1rep_b10/cdgsnofit_LoD2_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · LoD2 | 사전 정보 | `samepath_LoD2` | `S1/stage1/R1rep_b10/samepath_LoD2/mesh.ply` | 있음 (0.25) | `SL/work/virtual/R1rep_b10/samepath_LoD2/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | 본 방법 | `prop_ALS_s0` | `S1/stage1/R1rep_b10/prop_ALS_s0/post/mesh_tsdf.ply` | 있음 (1.01) | `S1/stage1/R1rep_b10/prop_ALS_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | 본 방법 | `prop_ALS_s1` | `S1/stage1/R1rep_b10/prop_ALS_s1/post/mesh_tsdf.ply` | 있음 (1.04) | `S1/stage1/R1rep_b10/prop_ALS_s1/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | 2DGS | `imgonly_2dgs_s0` | `SB/runs/R1rep_b10/imgonly_2dgs_s0/post/mesh_tsdf.ply` | 있음 (2.17) | `SB/runs/R1rep_b10/imgonly_2dgs_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | GeoGS | `geogs_ALS_fix1` | `SB/runs/R1rep_b10/geogs_ALS_fix1/post/mesh_tsdf.ply` | 있음 (1.91) | `SB/runs/R1rep_b10/geogs_ALS_fix1/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | 결합 | `mvsfuse_ALS` | `SB/runs/R1rep_b10/mvsfuse_ALS/post/mesh_tsdf.ply` | 있음 (1.07) | `SL/work/virtual/R1rep_b10/mvsfuse_ALS/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | CDGS | `cdgsnofit_ALS_s0` | `SL/runs/R1rep_b10/cdgsnofit_ALS_s0/post/mesh_tsdf.ply` | 없음 | `SL/runs/R1rep_b10/cdgsnofit_ALS_s0/gpu/virtual/mesh_virtual.ply` | 없음 |
| R1 · 항공 LiDAR | 사전 정보 | `samepath_ALS` | `S1/stage1/R1rep_b10/samepath_ALS/mesh.ply` | 있음 (0.86) | `SL/work/virtual/R1rep_b10/samepath_ALS/mesh_virtual.ply` | 없음 |

- 학습 시점 메시가 없는 것: B0 · LoD2 · CDGS 학습 시점 메시 (cdgsnofit_LoD2_s0); B0 · 항공 LiDAR · CDGS 학습 시점 메시 (cdgsnofit_ALS_s0); B173 주변 · LoD2 · CDGS 학습 시점 메시 (cdgsnofit_LoD2_s0); B173 주변 · 항공 LiDAR · CDGS 학습 시점 메시 (cdgsnofit_ALS_s0); R1 · LoD2 · CDGS 학습 시점 메시 (cdgsnofit_LoD2_s0); R1 · 항공 LiDAR · CDGS 학습 시점 메시 (cdgsnofit_ALS_s0). CDGS는 빈칸 채우기 일 1·9의 변형 결과(`cdgsnofit_<사전 정보>_s0`)이며, B0 · LoD2만 학습이 끝났고 후처리가 호스트 메모리 부족으로 멈춰 메시가 없다(SL/progress.md 10-16 04:06). 표에는 '채우기 대기'로 둔다.
- 가상 시점 메시는 B173 주변에만 있다(1단계 본 방법은 MF/virtual/option2, 2DGS와 항공 LiDAR GeoGS는 SB, 고친 GeoGS LoD2는 SF, 결합과 사전 정보는 채우기 일 6). B0와 R1에는 어느 방법에도 없다(FACTS65 2.3-4).
- 메시의 자리: 본 방법과 사전 정보는 `scripts/phd/main_stage1_v1/metrics_s1.py:32-50`(result_paths; B173 주변 본 방법은 0단계 학습, 사전 정보는 지표 시험 묶음), 2DGS·항공 LiDAR GeoGS·결합은 SB/runs, 고친 GeoGS LoD2는 SF/runs(R1은 3단계 5.0이 혼자 다시 한 후처리, `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md:451`).

## 참값

- 평가 범위를 자르는 법과 뺀 칸: FACTS65 2.1-4(참값 점은 XY가 평가 범위 사각형 안이고 제외 칸 밖인 것; 제외 칸은 0.5 m 칸의 나무와 일시 물체, 항공 LiDAR는 사전 정보 쪽 나무도). 코드 `scripts/phd/main_stage1_v1/defs_s1.py:52-61`(use = 평가 범위 안 & 제외 칸 밖).
- 파일: 참값 점군 `S1/v3/box_gt/<지역>/gt_points.npz`(드론 LiDAR), B0는 `gt_primary.npz`(주 참값, GeoGS 예제 장면 정리본)도; 제외 칸 `S1/v3/box_gt/<지역>/exclusion_cells.npz`(any); 점마다의 쓰임 `S1/defs/<지역>/gt_classes.npz`(use, roof, wall, excl); 건물 표면 칸 `S1/defs/<지역>/bsurf.npz`.
- B0의 두 참값: 영역 지표는 패치의 라벨 출처의 점만 쓴다. 주 참값에 라벨이 없는 패치만 드론 LiDAR 라벨로 채운다(FACTS65 2.1-7, `scripts/phd/main_stage1_v1/s1_common.py:76-100`). 장면 F1(이 발주의 '전체')은 모든 지역에서 드론 LiDAR 점만 쓴다(FACTS65 2.2-39).
- 이 발주의 셈에 쓴 참값: 전체는 장면 F1과 같은 드론 LiDAR 점(건물 표면 칸)을 d_g와 d_r 모두에 쓴다. 곳의 d_g는 영역 행(솎은 행)이고, 곳의 d_r은 그 행과 같은 출처의 점까지 구한다: B0는 건물 표면 칸의 드론 LiDAR 점과 주 참값 점(`d2b_b0gt.py`), 다른 지역은 드론 LiDAR 점.

| 지역 | 출처 | 점 | 평가 범위 안 | 그 가운데 제외 칸 | 쓰는 점(use) | 지붕류 | 벽류 | 전체(건물 표면 칸) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| B0 | 드론 LiDAR | 26,994,350 | 2,236,666 | 49,263 | 2,187,403 | 1,580,004 | 267,226 | 2,063,378 |
| B0 | 주 참값 | 4,709,500 | 4,709,500 | 101,824 | 4,607,676 | 1,629,960 | 2,680,095 | — |
| B173 주변 | 드론 LiDAR | 37,798,404 | 5,424,718 | 706,973 | 4,717,745 | 3,311,093 | 412,552 | 3,881,308 |
| R1 | 드론 LiDAR | 36,405,930 | 3,740,905 | 775,324 | 2,965,581 | 2,070,793 | 481,565 | 2,667,737 |

B0 패치의 라벨 출처 [새로 셈] (코드가 있는 패치): LoD2: 주 참값 51,115, 드론 LiDAR 13,990; ALS: 주 참값 15,421, 드론 LiDAR 7,692.

## 참값 점의 대응

- 규칙(FACTS65 2.1-15, `scripts/phd/main_stage1_v1/s04_gt_v7.py:255-292`): 가장 가까운 패치를 찾는 규칙이 아니다. 지붕꼴은 참값 점에서 위로부터 내린 연직선이 맨 먼저 만나는 정합한 사전 정보 면(\|n_z\| ≥ 0.5)의 패치이고, 연직 거리의 한도는 없되 그 패치의 가장 높은 점에서 1 m 아래까지(윗겹)만 남긴다(270행). 벽꼴(LoD2만)은 수직면 점에서 가장 가까운 벽 삼각형의 수선의 발이 면 안이고 거리가 2 m 안일 때 그 패치다(287행). 지표 행은 평가 범위 안·제외 칸 밖의 지붕류 점은 지붕꼴 패치로, 벽류 점은 벽꼴 패치로 대응된 것뿐이다(`defs_s1.py:97`).
- 이 발주의 결과 점은 가장 가까운 패치(중심, 거리 한도 없음)를 따르므로 참값 점의 규칙과 다르다: 참값 점은 면을 거쳐(지붕은 연직선, 벽은 2 m 안) 정해지고, 대응되지 않은 참값 점은 곳이 없다.
- 몫: FACTS65 2.1-16의 셈(행 수 ÷ 평가 범위 안 지붕류와 벽류 점)은 B173 주변과 R1만 있었고 B0는 확인 불가(2.1-17)였다. 아래는 여섯 경우 모두 다시 센 값이다[새로 셈]. '전체'의 몫은 장면 F1의 참값 점(건물 표면 칸의 드론 LiDAR 점) 가운데 1단계 대응 파일로 패치가 있는 점의 몫이다.

| 경우 | 출처 | 행 ÷ 지붕류·벽류 점 | 지붕류 | 벽류 | 전체의 참값 점 가운데 패치가 있는 몫 (두 패치) |
|---|---|---|---|---|---|
| B0 · LoD2 | 드론 LiDAR | 44.0 % (811,943 ÷ 1,847,230) | 45.6 % | 34.3 % | 84.3 % (1,739,696 ÷ 2,063,378; 1,899) |
| B0 · LoD2 | 주 참값 | 87.6 % (3,774,088 ÷ 4,310,055) | 76.5 % | 94.3 % | — |
| B0 · 항공 LiDAR | 드론 LiDAR | 35.4 % (654,436 ÷ 1,847,230) | 41.4 % | — | 66.8 % (1,378,138 ÷ 2,063,378; 0) |
| B0 · 항공 LiDAR | 주 참값 | 25.7 % (1,108,969 ÷ 4,310,055) | 68.0 % | — | — |
| B173 주변 · LoD2 | 드론 LiDAR | 94.8 % (3,529,247 ÷ 3,723,645) | 95.7 % | 87.8 % | 91.1 % (3,537,798 ÷ 3,881,308; 61,322) |
| B173 주변 · 항공 LiDAR | 드론 LiDAR | 78.0 % (2,902,426 ÷ 3,723,645) | 87.7 % | — | 75.9 % (2,947,910 ÷ 3,881,308; 0) |
| R1 · LoD2 | 드론 LiDAR | 84.4 % (2,153,823 ÷ 2,552,358) | 92.0 % | 51.8 % | 88.0 % (2,348,309 ÷ 2,667,737; 106,051) |
| R1 · 항공 LiDAR | 드론 LiDAR | 66.2 % (1,689,584 ÷ 2,552,358) | 81.6 % | — | 64.4 % (1,717,898 ÷ 2,667,737; 0) |

- 항공 LiDAR는 벽 패치가 없어 벽류 점이 하나도 대응되지 않는다(FACTS65 2.1-18). B0의 드론 LiDAR 행은 드론 LiDAR가 라벨을 낸 패치의 점뿐이다.
- '전체'에서 패치가 없는 참값 점(건물 둘레 2 m 안의 땅, 항공 LiDAR의 벽 등)은 τ와 법선의 방향을 정할 패치가 없다. 이 발주는 그 점의 τ와 부호를 정하지 않으므로 전체의 R(τ), F1(τ)(LoD2; 항공 LiDAR는 τ가 하나라 정해짐)과 전체의 치우침·퍼짐은 '정의 없음'으로 두고 여쭙는다. 후보 값(가장 가까운 패치를 따름)은 표 폴더에 함께 둔다.

## 패치의 어긋남

- 영역 파일에 있다: `gt_med`(패치에 대응한 참값 점의 '참값 − 사전 정보' 부호 있는 거리의 중앙값). 사전 정보의 정오는 \|gt_med\|를 그 패치 종류의 τ와 비교해 정했다(FACTS65 2.1-6, `scripts/phd/main_stage1_v1/s04_gt_v7.py:300-313`; 대응 점이 5개 미만이면 라벨 없음). 이 발주는 패치의 어긋남 = \|gt_med\| ÷ τ를 쓴다.
- 점검 [새로 셈]: 라벨이 있는 패치에서 라벨과 '\|gt_med\| > τ'가 같은 몫, 코드 11 가운데 어긋남이 τ를 넘는 몫, 코드 2 가운데 τ 안인 몫.

| 경우 | 라벨 = 규칙 | 코드 11: \|gt_med\| > τ | 코드 2: \|gt_med\| ≤ τ |
|---|---|---|---|
| B0 · LoD2 | 95,456 / 95,456 | 6,421 / 6,421 | 52,164 / 52,164 |
| B0 · 항공 LiDAR | 44,794 / 44,794 | 80 / 80 | 21,870 / 21,870 |
| B173 주변 · LoD2 | 136,463 / 136,463 | 21,741 / 21,741 | 32,128 / 32,128 |
| B173 주변 · 항공 LiDAR | 76,125 / 76,125 | 15,279 / 15,279 | 10,142 / 10,142 |
| R1 · LoD2 | 86,537 / 86,537 | 11,518 / 11,518 | 19,586 / 19,586 |
| R1 · 항공 LiDAR | 45,825 / 45,825 | 177 / 177 | 17,807 / 17,807 |

## 법선

- 참값 점의 법선 [새로 셈]: 출처마다 평가에 쓰는 점(use) 전부를 이웃으로, 반경 0.5 m 안의 점으로 분산이 가장 작은 방향(Open3D estimate_normals, 반경 탐색, 이웃 수 한도 없음). 이웃이 10점 미만이면 법선 없음(`src/phd/metrics_v3/cloud.py:89-110` pca_normals의 min_n = 10과 같게). 방향은 그 점이 대응한 패치의 바깥 법선과 같은 쪽으로 맞춘다(`d2_dist.py` oriented_sign).

| 지역 | 출처 | 점 | 법선 없음 | 이웃 수 중앙값 |
|---|---|---:|---:|---:|
| B0 | 드론 LiDAR | 2,187,403 | 411 | 644 |
| B0 | 주 참값 | 4,607,676 | 952 | 1,142 |
| B173 주변 | 드론 LiDAR | 4,717,745 | 1,198 | 885 |
| R1 | 드론 LiDAR | 2,965,581 | 791 | 763 |

- 사전 정보 패치의 법선(`scripts/phd/main_stage1_v1/defs_s1.py:65-75` patch_geometry): 지붕꼴은 패치 면의 법선을 n_z ≥ 0으로 뒤집어 둔다(69행: 위가 바깥). LoD2 벽꼴은 LoD2 면 표(DR/s02_box/<지역>/lod2_surfaces.json)의 다각형 법선이다(74행). 항공 LiDAR에는 벽꼴 패치가 없다.
- 바깥을 향하는지 [새로 셈]: 지붕꼴은 n_z < 0인 패치를 셌다. LoD2 벽꼴은 패치 중심에서 법선의 수평 방향으로 0.3 m 나간 점이 그 건물의 바닥 윤곽(DR/s02_box/<지역>/footprints.json) 밖이고 0.3 m 들어간 점이 안이면 바깥, 거꾸로면 안쪽, 둘 다 안이거나 밖이면 정할 수 없음으로 셌다(평가 범위 안, 코드가 있는 패치).

| 경우 | 지붕꼴 패치 | n_z < 0 | 벽꼴 패치 | 바깥 | 안쪽 | 정할 수 없음 | 윤곽 없음 |
|---|---:|---:|---:|---:|---:|---:|---:|
| B0 · LoD2 | 27,182 | 0 | 37,923 | 37,923 (100.0 %) | 0 | 0 | 0 |
| B0 · 항공 LiDAR | 23,113 | 0 | 0 | — | — | — | — |
| B173 주변 · LoD2 | 40,232 | 0 | 25,626 | 20,015 (78.1 %) | 3 | 5,608 | 0 |
| B173 주변 · 항공 LiDAR | 30,956 | 0 | 0 | — | — | — | — |
| R1 · LoD2 | 29,920 | 0 | 12,130 | 8,643 (71.2 %) | 0 | 3,487 | 0 |
| R1 · 항공 LiDAR | 22,948 | 0 | 0 | — | — | — | — |

