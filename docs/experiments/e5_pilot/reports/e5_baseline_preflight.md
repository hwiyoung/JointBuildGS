# E5 A4 Baseline Preflight

> 분류·관찰 재료만 기록한다. CRS는 EPSG:25832.

## 높이 이력

| 입력 | 원천 | 신규 실행 높이 처리 | 이중 적용 확인 |
|---|---|---|---|
| raw-ACMP | `results/tum_transfer/mob_analysis/p0c_step2/acmp_aoi_utm.laz` | orthometric source +45.7 m in `tum_mob_raw_to_npz.py` | 신규 NPZ 생성 경로에서만 적용 |
| raw-sparse | `phases/p0-audit/data/work/mvs/openmvs/colmap_txt/sparse/points3D.txt` | COLMAP local +604 m, geoid 미개입 | +45.7 미적용 |
| ALS reference patch | `results/tum_transfer/mob_analysis/p0c_step2/als_aoi.laz` | orthometric source +45.7 m for patch comparison | 조립 입력 아님 |

## 지면 패치 확인

- 격자: 5 m cell. ACMP는 cell z 10 분위, ALS는 ground(class 2) median을 비교했다.
- 전체 겹침 cell 수: 1878. diff median=-2.296 m, IQR=-2.340..-2.260 m.

| cell_ix | cell_iy | ACMP q10 z | ALS ground median z | diff m | n_acmp_sample | n_als_ground |
|---:|---:|---:|---:|---:|---:|---:|
| 138200 | 1067258 | 559.150 | 559.240 | -0.090 | 600 | 38 |
| 138185 | 1067205 | 562.470 | 562.330 | 0.140 | 157 | 27 |
| 138194 | 1067190 | 561.007 | 561.260 | -0.253 | 600 | 22 |
| 138228 | 1067235 | 560.100 | 560.700 | -0.600 | 52 | 29 |
| 138177 | 1067183 | 561.415 | 560.770 | 0.645 | 452 | 24 |
| 138161 | 1067177 | 560.458 | 561.280 | -0.822 | 60 | 25 |
| 138168 | 1067225 | 561.320 | 560.410 | 0.910 | 46 | 27 |
| 138168 | 1067203 | 561.788 | 560.600 | 1.188 | 600 | 23 |

## 관찰

- 위 표의 best patch들은 +45.7 m 적용 후 ACMP 낮은 표면과 ALS 지면이 서브미터 범위에서 맞는 위치다.
- 전체 cell diff는 지붕·수목·매칭 잡음이 섞인 관찰 재료이며, 여기서 판정하지 않는다.
