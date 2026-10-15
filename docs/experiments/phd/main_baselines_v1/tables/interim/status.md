# 학습이 끝났는지의 표 (10.4)

- 만든 때: 2026-10-15 13:19:16 KST. 대기열 상태 SB/jobs/state.json(읽기만), 영수증 SB/runs/<지역>/<결과>/receipt.json, train_record.json.
- GPU 최대 = nvidia-smi 최대 − 시작(GiB). 단계: 후처리(post0 평가 영상·TSDF, post1 평가 점·부유·가상 시점), 지표(cpu0·cpu1 metrics_s2, cpu2 measure_s2), 결합의 pre0 판정·합치기. 호스트 최소 = 그 단계 동안 쓸 수 있던 호스트 메모리의 최소(GB).

| 방법 | 결과 | 지역 | 단위 | 상태 | 코드·이미지 | 시도 | 학습 (분) | GPU 최대 (GiB) | PyTorch 할당 최대 (GiB) | 마지막 가우시안 | 단계: 초 · 호스트 최소 GB |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2차원 가우시안 스플래팅 | `imgonly_2dgs_s0` | B173 주변 | LoD2, 항공 LiDAR | 끝남 | github.com/hbb1/2d-gaussian-splatting f3e3b9f + 어댑터 v1; 이미지 jointbuildgs:2dgs-official-f3e3b9f-v1 | 1 | 32.8 | 5.0 | 4.0 | 1,440,563 | post0 PASS 395 s · 19.0; post1 PASS 208 s · 37.2; cpu0 PASS 307 s · 48.3; cpu1 PASS 293 s · 51.6; cpu2 PASS 44 s · 57.1 |
| 2차원 가우시안 스플래팅 | `imgonly_2dgs_s0` | B0 | LoD2, 항공 LiDAR | 끝남 | github.com/hbb1/2d-gaussian-splatting f3e3b9f + 어댑터 v1; 이미지 jointbuildgs:2dgs-official-f3e3b9f-v1 | 1 | 26.4 | 3.4 | 2.6 | 1,024,176 | post0 PASS 451 s · 3.0; post1 PASS 41 s · 52.0; cpu0 PASS 326 s · 47.2; cpu1 PASS 310 s · 39.4; cpu2 PASS 53 s · 49.5 |
| 2차원 가우시안 스플래팅 | `imgonly_2dgs_s0` | R1 | LoD2, 항공 LiDAR | 아직 (대기열) | github.com/hbb1/2d-gaussian-splatting f3e3b9f + 어댑터 v1; 이미지 jointbuildgs:2dgs-official-f3e3b9f-v1 | 1 | 25.9 | 3.8 | 3.1 | 1,053,603 | post0 PASS 533 s · 34.5; post1 PASS 32 s · 91.7 |
| 2차원 가우시안 스플래팅 | `imgonly_2dgs_s0` | B173만 | LoD2, 항공 LiDAR | 진행 중: train | — | 1 | — | — | — | — | — |
| GeoGS (LoD2, 고침 발주의 결과를 옮김) | `trust_LoD2_fix1` | B173 주변 | LoD2 | 끝남 (앞 작업) | GeoGS-official-adapters-v1-fix1; 이미지 jointbuildgs:geogs-official-db40c95-compat-v1 | — | 71.1 | 17.8 | — | — | — |
| GeoGS (LoD2, 고침 발주의 결과를 옮김) | `trust_LoD2_fix1` | B0 | LoD2 | 끝남 (앞 작업) | GeoGS-official-adapters-v1-fix1; 이미지 jointbuildgs:geogs-official-db40c95-compat-v1 | — | 54.1 | 9.2 | — | — | — |
| GeoGS (LoD2, 고침 발주의 결과를 옮김) | `trust_LoD2_fix1` | R1 | LoD2 | 끝남 (앞 작업) | GeoGS-official-adapters-v1-fix1; 이미지 jointbuildgs:geogs-official-db40c95-compat-v1 | — | 52.6 | 10.8 | — | — | — |
| GeoGS (LoD2, 고침 발주의 결과를 옮김) | `trust_LoD2_fix1` | B173만 | LoD2 | 끝남 (앞 작업) | GeoGS-official-adapters-v1-fix1; 이미지 jointbuildgs:geogs-official-db40c95-compat-v1 | — | 195.6 | 21.2 | — | — | — |
| GeoGS | `geogs_ALS_fix1` | B173 주변 | 항공 LiDAR | 끝남 | GeoGS-official-adapters-v1-fix1; 이미지 jointbuildgs:geogs-official-db40c95-compat-v1 | 1 | 66.9 | 13.4 | — | 3,605,015 | post0 PASS 382 s · 11.4; post1 PASS 186 s · 36.5; cpu0 PASS 217 s · 58.8; cpu1 PASS 41 s · 57.7 |
| GeoGS | `geogs_ALS_fix1` | B0 | 항공 LiDAR | 아직 (대기열) | — | — | — | — | — | — | — |
| GeoGS | `geogs_ALS_fix1` | R1 | 항공 LiDAR | 아직 (대기열) | — | — | — | — | — | — | — |
| GeoGS | `geogs_ALS_fix1` | B173만 | 항공 LiDAR | 아직 (대기열) | — | — | — | — | — | — | — |
| CDGS | `cdgs_LoD2_s0` | B173 주변 | LoD2 | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 35.5 %, 항공 LiDAR 학습 영상 27.6 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_ALS_s0` | B173 주변 | 항공 LiDAR | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 35.5 %, 항공 LiDAR 학습 영상 27.6 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_LoD2_s0` | B0 | LoD2 | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 항공 LiDAR 학습 영상 32.1 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_ALS_s0` | B0 | 항공 LiDAR | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 항공 LiDAR 학습 영상 32.1 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_LoD2_s0` | R1 | LoD2 | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 38.1 %, 항공 LiDAR 학습 영상 47.1 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤; 가중 규칙: 깊이 가중 중앙값 0.000312 < 0.006이라 이 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_ALS_s0` | R1 | 항공 LiDAR | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 38.1 %, 항공 LiDAR 학습 영상 47.1 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_LoD2_s0` | B173만 | LoD2 | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 31.4 %, 항공 LiDAR 학습 영상 36.4 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤; 가중 규칙: 깊이 가중 중앙값 0.000000 < 0.006이라 이 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| CDGS | `cdgs_ALS_s0` | B173만 | 항공 LiDAR | 결과 없음 (학습하지 않음: 5.5 점검) — 축척 규칙: 이 지역의 LoD2 학습 영상 31.4 %, 항공 LiDAR 학습 영상 36.4 %가 축척 0.9~1.1 밖(4분의 1 초과)이라 이 지역의 두 사전 정보가 멈춤; 가중 규칙: 깊이 가중 중앙값 0.000000 < 0.006이라 이 사전 정보가 멈춤 | github.com/zqlin0521/cdgs-release db853c1 + 어댑터 v2; 이미지 jointbuildgs:cdgs-official-db853c1-v1 | — | — | — | — | — | — |
| MVS 기반 결합 | `mvsfuse_LoD2` | B173 주변 | LoD2 | 끝남 | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 10.2) | — | — | — | pre0 PASS 87 s · 42.2; post0 PASS 537 s · 21.9; cpu0 PASS 113 s · 47.1; cpu1 PASS 31 s · 51.8 |
| MVS 기반 결합 | `mvsfuse_ALS` | B173 주변 | 항공 LiDAR | 끝남 | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 7.5) | — | — | — | pre0 PASS 65 s · 46.1; post0 PASS 392 s · 22.5; cpu0 PASS 116 s · 46.2; cpu1 PASS 37 s · 49.0 |
| MVS 기반 결합 | `mvsfuse_LoD2` | B0 | LoD2 | 끝남 | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 4.5) | — | — | — | pre0 PASS 46 s · 52.2; post0 PASS 230 s · 35.1; cpu0 PASS 69 s · 50.0; cpu1 PASS 23 s · 61.4 |
| MVS 기반 결합 | `mvsfuse_ALS` | B0 | 항공 LiDAR | 아직 (대기열) | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 5.4) | — | — | — | pre0 PASS 62 s · 47.8; post0 PASS 271 s · 34.5 |
| MVS 기반 결합 | `mvsfuse_LoD2` | R1 | LoD2 | 아직 (대기열) | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 5.7) | — | — | — | pre0 PASS 31 s · 47.3; post0 PASS 322 s · 38.0 |
| MVS 기반 결합 | `mvsfuse_ALS` | R1 | 항공 LiDAR | 진행 중: post0 | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 1.3) | — | — | — | pre0 PASS 78 s · 47.6; post0 RUNNING |
| MVS 기반 결합 | `mvsfuse_LoD2` | B173만 | LoD2 | 아직 (대기열) | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 0.8) | — | — | — | pre0 PASS 48 s · 52.2 |
| MVS 기반 결합 | `mvsfuse_ALS` | B173만 | 항공 LiDAR | 아직 (대기열) | scripts/phd/main_baselines_v1/mvsfuse (재현; 학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 0.6) | — | — | — | pre0 PASS 38 s · 51.7 |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_LoD2` | B173 주변 | LoD2 | 끝남 | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 5.0) | — | — | — | pre0 PASS 87 s · 55.5; post0 PASS 222 s · 33.7; cpu0 PASS 72 s · 51.2; cpu1 PASS 27 s · 55.7 |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_ALS` | B173 주변 | 항공 LiDAR | 끝남 | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | 학습 없음 (판정·합치기 + TSDF 5.1) | — | — | — | pre0 PASS 58 s · 54.7; post0 PASS 256 s · 28.8; cpu0 PASS 121 s · 41.9; cpu1 PASS 35 s · 46.9 |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_LoD2` | B0 | LoD2 | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_ALS` | B0 | 항공 LiDAR | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_LoD2` | R1 | LoD2 | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_ALS` | R1 | 항공 LiDAR | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_LoD2` | B173만 | LoD2 | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
| 본 방법의 판정으로 갈아 끼운 변형 | `judgefuse_ALS` | B173만 | 항공 LiDAR | 아직 (대기열) | scripts/phd/main_baselines_v1/judgefuse (학습 없음) | — | — | — | — | — | — |
