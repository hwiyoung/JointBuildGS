# P2 make-or-break C — 씨드보존 재실행 (de-confound v6 prune). 관찰만, 판정=김휘영.
생성 2026-06-24. branch feature/p2-seed-protect (commit c39c15c). matched tag. EPSG:25832.
v6 raw/LiDAR/ref 재사용. 씨드보존 = MVS 씨드 Gaussian을 opacity-prune에서 제외(엔진: SeedProtectStrategy, gsplat fork 없음).

## 씨드 생존 (train log, 5k마다)
| arm | init seeds | final seeds(it=25k) | final N | v6 final N | PSNR |
|---|--:|--:|--:|--:|--:|
| dense_protect | 2,885,763 | **2,950,262** (성장) | 3.08M | 226k(붕괴) | 20.27 |
| acmp_protect | 2,919,104 | **2,989,057** (성장) | 3.12M | 281k(붕괴) | 20.30 |
저밀도 R footprint 씨드(it=25k): 4907182=994, 4908176=401 (v6=0). **단 중앙 opacity ≈ 0.00**(prune은 막았으나 옵티마이저가 0으로).

## 8-way (matched) — facet / solid / RMS→ref(m)
| 건물 | r | ref | dense_v6 | dense_PROT | acmp_v6 | acmp_PROT | raw_lidar |
|---|--|--:|--|--|--|--|--|
| 42364609 | R* | 1 | 0/N/- | 0/N/- | 0/N/- | 0/N/- | 1/Y/0.43 |
| 42364659 | R | 2 | 3/Y/2.28 | 3/Y/2.26 | 2/Y/1.79 | 1/Y/1.71 | 0/N/4.84 |
| 42364663 | R | 1 | 1/Y/2.90 | 1/Y/5.56 | 1/Y/1.91 | 1/Y/3.21 | 1/Y/2.26 |
| 4907182 | R* | 2 | 0/N/- | 0/N/- | 0/N/- | 0/N/0.11 | 2/Y/1.74 |
| 4907510 | R | 1 | 0/N/1.34 | 0/N/- | 0/N/0.35 | 2/Y/9.45 | 4/Y/1.34 |
| 4908050 | R* | 1 | 0/N/- | 0/N/- | 0/N/- | 0/N/- | 1/Y/0.07 |
| 4908166 | R* | 1 | 0/N/- | 0/N/- | 0/N/- | 0/N/- | 1/Y/0.11 |
| 4908176 | R* | 1 | 0/N/- | 0/N/- | 1/Y/4.62→0/N/- | 0/N/- | 1/Y/0.13 |
| 4906969 | Q | 3 | 7/Y/4.07 | 12/Y/0.83 | 7/Y/0.77 | 6/Y/0.65 | 5/Y/1.17 |
| 4906972 | Q | 3 | 15/Y/2.06 | 17/Y/3.03 | 11/Y/1.48 | 16/Y/3.61 | 3/Y/2.41 |
| 4908023 | Q | 1 | 1/Y/0.29 | 1/Y/0.67 | 2/Y/0.46 | 1/Y/1.16 | 1/Y/0.92 |

solid/11 (R-solid/8): dense_v6 5(2) | dense_PROT 5(2) | acmp_v6 5(2) | **acmp_PROT 6(3)** | lidar 10(7). (* = in-scope: v6 씨드 prune→0)

## 관찰 (판정 금지)
- **씨드보존 메커니즘 성공**(씨드 2.9M+ 생존, v6 붕괴와 대비), **그러나 in-scope 5동 새 조립 = 0/5**(dense·acmp 모두).
- 원인 재료: 보존 씨드 op≈0 → TSDF alpha>0.5 표면화에 미포착 → 점 부족 그대로(대부분 RMS "–"). 4907182 acmp만 점 일부(RMS 0.11)·미조립.
- **de-confound 결론 재료**: v6의 prune이 생성 밴드를 막은 게 아니라 **"얇은 증거 한계"** — 씨드를 살려도 photometric이 op를 0으로 밀어 표면을 못 만든다.
- 부수: acmp_PROT +1(4907510, in-scope 아님, RMS 9.45 불량) · Q 과분할↑(저-op 씨드가 가짜 facet) · PSNR 무회귀 · LiDAR floor 미도달.
- (다음 후보 재료, 판정=사람: 씨드 opacity 하한/floor, 또는 depth/normal supervision으로 씨드를 표면에 고정 — 별건.)

## 산출
- eval_v6_protect.json/csv · ref_rms_protect.csv · train_gs_seed_{dense,acmp}_protect.log(seed-survival) · versions.txt.
