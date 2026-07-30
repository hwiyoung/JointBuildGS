# E5 Pilot Train Prep

> B단계 준비 재료. 판정 문구 없이 지문과 관찰만 기록한다.

- Candidate: `C001`
- Buffer: 20.0 m
- Data root: `results/tum_transfer/e5_pilot/C001/data_geoidfix_C001_buf20`
- Selected crop views: 428
- C001 buildings: 18
- 관측기하 기록: 선정 규칙에는 관측기하 조건이 없었고, 미학습 지역 전체가 관측 열세라는 판정 부속 사실을 기록한다. C001 `frac_views_incidence_le60` 범위는 0.057..0.539; 판정 회신의 미학습 지역 최고값 기록은 0.7이다.

## Seed Clips

| seed | source points | clipped points | path |
|---|---:|---:|---|
| sparse | 369225 | 43899 | `results/tum_transfer/e5_pilot/C001/seeds/seed_sparse_C001_buf20.ply` |
| dense | 2885763 | 201625 | `results/tum_transfer/e5_pilot/C001/seeds/seed_dense_C001_buf20.ply` |
| acmp | 2919104 | 243660 | `results/tum_transfer/e5_pilot/C001/seeds/seed_acmp_C001_buf20.ply` |

## Configs

| run | arm | replicate | random seed | config | out_dir |
|---|---|---|---:|---|---|
| gs_e5_C001_sparse_r1 | sparse | r1 | 1001 | `configs/e5_c001/e5_pilot/gs_e5_C001_sparse_r1.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_sparse_r1` |
| gs_e5_C001_sparse_r2 | sparse | r2 | 1002 | `configs/e5_c001/e5_pilot/gs_e5_C001_sparse_r2.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_sparse_r2` |
| gs_e5_C001_dense_r1 | dense | r1 | 1001 | `configs/e5_c001/e5_pilot/gs_e5_C001_dense_r1.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_dense_r1` |
| gs_e5_C001_dense_r2 | dense | r2 | 1002 | `configs/e5_c001/e5_pilot/gs_e5_C001_dense_r2.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_dense_r2` |
| gs_e5_C001_acmp_r1 | acmp | r1 | 1001 | `configs/e5_c001/e5_pilot/gs_e5_C001_acmp_r1.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_acmp_r1` |
| gs_e5_C001_acmp_r2 | acmp | r2 | 1002 | `configs/e5_c001/e5_pilot/gs_e5_C001_acmp_r2.yaml` | `results/tum_transfer/e5_pilot/C001/runs/gs_e5_C001_acmp_r2` |

## Training Runtime

첫 런 실측 시간은 `gs_e5_C001_sparse_r1` 66.8분이다. 이 값으로 남은 5런을 단순 재추정하면 약 334분이었고, 실제 남은 5런 합계는 345.4분이었다.

| run | elapsed min | final N | start UTC | end UTC |
|---|---:|---:|---|---|
| gs_e5_C001_sparse_r1 | 66.8 | 409546 | 2026-07-07T01:42:41Z | 2026-07-07T02:49:34Z |
| gs_e5_C001_sparse_r2 | 62.5 | 402332 | 2026-07-07T02:49:59Z | 2026-07-07T03:52:32Z |
| gs_e5_C001_dense_r1 | 67.3 | 575318 | 2026-07-07T03:52:33Z | 2026-07-07T04:59:56Z |
| gs_e5_C001_dense_r2 | 66.3 | 508235 | 2026-07-07T04:59:57Z | 2026-07-07T06:06:23Z |
| gs_e5_C001_acmp_r1 | 72.0 | 627259 | 2026-07-07T06:06:24Z | 2026-07-07T07:18:27Z |
| gs_e5_C001_acmp_r2 | 77.3 | 642766 | 2026-07-07T07:18:28Z | 2026-07-07T08:35:49Z |

학습 시간 합계는 412.2분이고, 첫 시작부터 마지막 종료까지의 벽시계 시간은 약 413.1분이다.
