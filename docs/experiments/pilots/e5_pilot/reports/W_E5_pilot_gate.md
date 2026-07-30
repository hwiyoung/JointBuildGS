# E5 파일럿 게이트 재료

> 판정 금지. 이 문서는 표·그림·관찰만 기록한다. CRS는 EPSG:25832.

## 고정 조건

- 파일럿 블록: C001, 18동.
- 학습 범위: C001 AOI + 20 m 버퍼로 자른 씨앗 점군·영상. 전체 장면 학습 없음.
- 관측기하 기록: 선정 규칙에는 관측기하 조건이 없었고, 미학습 지역 전체가 관측 열세(최고 0.7)라는 판정 부속 사실을 기록한다.
- 점군화·라벨 방식(read-out): `readout(gssem; semantic-TSDF[minobs3, voxel0.05]; Roofer eps0.3/minpts15/complexity0.888)`.
- 생성 채점 범위: 씨앗별 짝 채점. GS-sparse vs raw-sparse, GS-dense vs raw-dense(w2_1 DIM), GS-acmp vs raw-ACMP. LiDAR는 완전측량 기준선 참고.
- C001 기준선 성적(has_lod22): LiDAR 15/18, raw-ACMP 12/18, raw-dense(w2_1 DIM) 10/18, raw-sparse 2/18.
- 성공 회계: `has_lod22`가 주, 유효성 통과는 참고. `no_points`는 조립기 문턱 기준과 클립 내 점 0 기준을 구분한다.

## 완주 체크리스트

| run | 학습 | 점군화 | 조립 run_1 | has_lod22 run_1 |
|---|---|---|---|---|
| gs_e5_C001_sparse_r1 | 완료 | 완료 | 완료 | 9/18 |
| gs_e5_C001_sparse_r2 | 완료 | 완료 | 완료 | 11/18 |
| gs_e5_C001_dense_r1 | 완료 | 완료 | 완료 | 8/18 |
| gs_e5_C001_dense_r2 | 완료 | 완료 | 완료 | 13/18 |
| gs_e5_C001_acmp_r1 | 완료 | 완료 | 완료 | 9/18 |
| gs_e5_C001_acmp_r2 | 완료 | 완료 | 완료 | 11/18 |

## 씨앗별 짝 채점 요약

| 씨앗 | 짝 기준 | 기준 has_lod22 | GS r1 has_lod22 | GS r2 has_lod22 | r1-r2 flip | r1 유효성 통과 | r2 유효성 통과 |
|---|---|---|---|---|---|---|---|
| sparse | raw-sparse | 2/18 | 9/18 | 11/18 | 4 | 14/18 | 16/18 |
| dense | raw-dense(w2_1 DIM) | 10/18 | 8/18 | 13/18 | 7 | 15/18 | 16/18 |
| acmp | raw-ACMP | 12/18 | 9/18 | 11/18 | 4 | 15/18 | 14/18 |

## 재현 재료

- r1 vs r2 조립 성공 동 집합 flip: 15건.
- 조립 3회 내부 flip: 0건.
- 전체 flip 목록: `docs/experiments/pilots/e5_pilot/tables/e5_pilot_seed_pair_status.csv`, `phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/repeat_flip_table.csv`.

## 그림 쌍

- 생성 축: `docs/figs/e5_pilot/e5_generation_DEBY_LOD2_8568391.png`.
- 품질 축: `docs/figs/e5_pilot/e5_quality_gs_e5_C001_dense_r1_DEBY_LOD2_4908178.png`. 대표 선정: 조립 3회 flip 우선, 없으면 `rf_rmse_lod22` 짝 델타 최대.

## 런 지문

- 학습 지문: `phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/train_fingerprints.csv`.
- 점군화 지문: `phases/p2-gsjso/runs/e5_c001/e5p_train_20260707_C001/readout_fingerprints.csv`.
- 조립 지문: `phases/p0-audit/runs/e5p_gate_20260707_C001/versions.txt`.
- 속성 검산: `docs/e5_pilot_pointcloud_attributes_v1_3_check.json`.

## 관찰

- C001은 미학습 지역이며 관측 열세(최고 0.7)가 함께 기록된 블록이다.
- sparse 씨앗의 일부 동은 초기 씨앗점이 0개로 기록됐다. 이 항목은 생성 축 그림과 실패 목록에서 따로 확인한다.
- 위 표와 그림은 게이트 판정 재료이며, 판정 문구는 쓰지 않는다.
