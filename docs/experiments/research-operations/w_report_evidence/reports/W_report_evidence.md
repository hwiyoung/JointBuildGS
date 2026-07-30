# W_report_evidence — GS-JSO 생성품질 기여: 사례 기반 정량·정성 (기존 결과 재사용·재학습 없음, 판정 금지)

> **실험 2 / Phase B.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. Docker(`--user`). **재학습/재구성 없음** — v6 matched·D12·assembly-fidelity·W_ 문서·canonical 산출 재사용(읽기+경량 재계산). 관찰만, 판정 = 김휘영. 지도교수 보고 초안(GS-JSO_생성품질기여) 근거용.
> 재현 `d12_report_figs.py`(그림)·CSV `overseg_lever/{report_evidence,gen_8way,d12_metric_final,d12_defect}.csv`·table_v6.csv. 그림 `docs/figs/W_report_evidence/`.
> ⚠ **정직 경고(§5 공정성)**: 아래 근거는 **서로 다른 GS 설정**서 나옴 — 생성 8-way=**gs_seed_*(v6 make-or-break, matched-density)**, 정확도 4.52→1.13=**gs_seed_acmp(v6-matched)**, 과분할·정식메트릭=**gs_d4_dense(D-수트, cp-정규화)**. 단일 설정 아님(§5).

## §0 재고 (출처)

| 근거 | 소스 | 위치 | 비고 |
|---|---|---|---|
| 생성 8-way(실패 64동) | gen_8way.csv | `overseg_lever/` | gs_seed_{sp,de,ac}+raw_{sp,de,ac,lidar}, 모델 y/val3dity y |
| v6-matched 정확도(11동) | table_v6.csv·REPORT_v6.md | `results/tum_transfer/mob/` | RMS→ref matched, raw_acmp vs GS |
| 조립 충실도(3동) | W_assembly_fidelity.md §5 | `docs/` | 닫힘·ridge·roof-RMS |
| 정식 3축 메트릭 | d12_metric_final.csv·d12_defect.csv | `overseg_lever/` | gs_d4: h_common/abs·slope·psd·facets |
| 정성(점군·모델·영상) | mob_eval/<arm>/*.las·roofer_* | `phases/p0-audit/runs/` | 79+64동 clip·Roofer Solid; ref=LoD2 GML |

## §1 린치핀 — 생성 기여 (raw 조립 실패 ∧ GS 조립 성공)

**(A) 엄격 린치핀(raw sparse·dense·ACMP 모두 실패 ∧ GS 성공, 실패-64 8-way):**

| 동 | 버킷 | GS(sp/de/ac) | raw(sp/de/ac) | LiDAR | 상태 |
|---|---|---|---|---|---|
| **104586480** | 조립 | 1/1/1 | 0/0/0 | **0** | **GS-단독 성공**(LiDAR도 실패, 참조 없음→val3dity+정성으로 충실 판단) |
| 42364609 | 조립 | 1/0/0 | 0/0/0 | 1 | GS-sparse 회복, LiDAR 성공 |
| 4908046 | 조립 | 0/1/0 | 0/0/0 | 1 | GS-dense 회복, LiDAR 성공 |

→ **모든 raw(ACMP 포함) 실패한 곳에서 GS가 회복 = 3동**(그중 **104586480은 LiDAR조차 실패한 GS-단독**). 광의로 **② 조립버킷(16) 집계: GS-dense 6·sparse 5·acmp 4 vs raw-dense 1·sparse 1 → GS가 raw-DIM 0면 실패를 5~6동 모델 회복**(단 raw-ACMP 7·LiDAR 14; val3dity 유효는 GS 1~3뿐=위상 약함).

**(B) 조립 표적 3동(11-mob, v6+assembly-fidelity; 42364659·42364663 필수):**

| 동 | raw 조립 | GS 조립 | LiDAR | v6 RMS→ref(raw_acmp→GS-ac) | 면수(ref/GS-d4/GS-v6de) | assembly-fidelity 판정 |
|---|---|---|---|---|---|---|
| **42364659** | DIM 0면 실패 | 성공(6면) | **실패** | 4.75→**1.79** | 2/6/3 | **부분**(닫힘·ridge −1.7m 근사·표면 판정불가·과분할) |
| **42364663** | (성공 대조) | 성공(1면) | 성공 | 8.32→**1.91** | 1/1/1 | **충실 후보**(높이·표면 1.36≈ALS·면수 ALS급, 유일) |
| 4907510 | DIM 0면 실패 | 성공(6면) | 성공 | 2.92→**0.35** | 1/6/0 | **부분**(ridge +1.0m 근사·표면 2.6× 노이지·과분할) |

→ **"raw-DIM 0면 실패 → GS 조립" 실재**(닫힘 3/3, ridge 높이 ALS ~±2m 3/3); 단 **표면·면수 충실은 1/3(42364663)**, 나머지 과분할·표면 노이지 = **"조립됨 ≠ 완전 충실"**. **42364659는 LiDAR조차 실패 = GS/ACMP-단독 회복**. 정성 그림 (a).

## §2 정확도 교정 (ACMP raw 대 GS, v6-matched, RMS→ref[LiDAR])

**중앙값 RMS→ref: raw-ACMP 4.519 → GS-ACMP 1.125**(11동, gs_seed_acmp). 원인 = GS가 raw-ACMP의 **노이지 최악동(8.3·9.3·29.2m)을 평활**.

| 동 | raw-ACMP | GS-ACMP | Δ | GS 우위? |
|---|---:|---:|---:|---|
| 42364663 | 8.32 | **1.91** | −6.41 | ✓ |
| 42364659 | 4.75 | **1.79** | −2.96 | ✓ |
| 4907510 | 2.92 | **0.35** | −2.57 | ✓ |
| 4908023 | 2.61 | **0.46** | −2.15 | ✓ |
| 4906969 | 2.45 | **0.77** | −1.68 | ✓ |
| 4906972 | 2.92 | 1.48 | −1.44 | ✓ |
| **중앙값** | **4.52** | **1.13** | **−3.4** | GS ↓RMS |

→ **GS-ACMP가 RMS→ref를 전 동에서 낮춤**(4.52→1.13 = ~4× 개선). ⚠ **정직 병기**: (i) 이는 **matched-density full-class6 RMS**(facade 포함); D-수트 `ref_rms`(roof-env)는 raw 1.25→GS-d4 **1.01**(개선폭 작음) — 지표에 따라 개선폭 다름. (ii) **dense 씨앗은 혼재**: v6-dense raw 1.06→GS 2.17(오히려 악화) — ACMP 씨앗만 큰 개선, dense는 아님. **"GS가 LiDAR보다 정확"은 미해당**(LiDAR=참조 자체; GS는 참조 대비 RMS, LiDAR 대비 우위 주장 불가).

## §3 과분할 사례 (통제 건물, 정식 메트릭 병기)

| 동 | ref면 | raw(v6 acmp) | **GS-v6-dense** | **GS-d4** | h_common/abs | slope | psd |
|---|---:|---:|---:|---:|---|---:|---:|
| **4906972**(박공) | 3 | 3 | **15**(v6 과분할) | **4**(D4) | 0.24/1.94 | 39.8° | 3.71 |
| 4906969(단차평) | 3 | 11 | 7 | 16 | 1.48/1.54 | 60° | 2.00 |
| 4908023 | 1 | 1 | 1 | 3 | 0.73/2.45 | 50.6° | 1.33 |

→ **4906972: ref 3 → v6-GS 15(심한 과분할) → GS-d4 4**(cp-정규화로 과분할 통제, ref 근접). **과분할은 GS 설정 의존**(v6 무통제 vs D4 cp-정규화). 정성 그림 (b). 정식 메트릭(h_common 상대잔차·slope·psd)은 [[W_D12_metric_final]]·[[W_observability_test]] 참조.

## §4 정성 그림 (`docs/figs/W_report_evidence/`)

- **(a) a_recovery.png** — 린치핀 42364659: raw-DIM 점군(2870점, 구멍·조립 실패) → GS-JSO 모델(6면 조립) → GS-d4(6면) → 참조 LoD2(2면). **raw 점 있으나 0면 조립실패 → GS 조립**(LiDAR도 실패=GS-단독).
- **(b) b_overseg.png** — 과분할 4906972: 참조(3면) vs GS-v6-seed(15면 과분할) vs GS-d4(4면). **cp-정규화가 과분할 통제**.
- **(c) c_textureless.png** — 무텍스처 4907182: DIM/MVS 점군(502점, 희박) vs ALS(1851점, 꽉 참). **점군 중간표현이 무텍스처서 붕괴**(GS 동기).

## §5 공정성 메모 (필독)

**본 근거는 단일 GS 설정이 아님** — 정직 비교용:
- **생성 8-way·정확도 4.52→1.13** = **gs_seed_{sparse,dense,acmp}** (v6 make-or-break, MVS-씨앗, **matched-density** eval, cp-정규화 前). 밤샘 gen-8way(gs_seed) 설정과 **동일**.
- **과분할·정식 3축 메트릭(h_common/slope/psd)** = **gs_d4_dense** (D-수트, cp-정규화·depth 0.03·30k). **v6와 다른 설정**(D4가 과분할↓·품질 정규화).
- 따라서 **"GS 생성 회복(v6)"과 "GS 과분할 통제(D4)"는 서로 다른 런** — 보고 시 **한 GS 파이프라인의 단일 결과가 아님**을 명시해야 공정. 최신·최선 품질 설정 = D4(cp-정규화)이나 생성 8-way는 v6서 측정됨. **동일 설정 전수 재평가는 미실시**(재학습 필요 영역 = 판정=김휘영).

## §6 종합 (판정 금지)

**GS-JSO 생성품질 기여(관찰)**: ① **생성**: raw-DIM 0면 실패를 GS가 회복(엄격 린치핀 3동·조립버킷 6/16, 104586480·42364659는 LiDAR조차 실패한 GS-단독) — 단 raw-ACMP(20/64)가 경쟁적·GS 위상 유효율 낮음. ② **정확도**: GS-ACMP가 raw-ACMP RMS→ref를 **4.52→1.13(~4×)** 낮춤(노이지 동 평활) — 단 지표·씨앗(dense 혼재) 의존. ③ **과분할**: D4 cp-정규화가 v6 과분할(4906972 15→4)을 ref 근처로 통제. **한 줄: "GS-JSO는 raw-DIM 조립실패를 일부 회복(LiDAR-단독 포함)하고 ACMP 정확도를 크게 개선하며 D4서 과분할을 통제 — 단 완전 충실(표면·위상·면수)은 부분(1/3)이고 설정이 혼재(v6 생성 vs D4 품질)."** 커밋 `report-evidence`.
