# W_results_consolidation — 레포 전용 수치 통합 (READ-ONLY 추출, 관찰만·판정 없음)

> 생성 = `phases/p2-gsjso/scripts/results_consolidation.py` (on-disk eval_*.json / ref_rms_*.csv / TB / Roofer cityjson 에서 **직접 산출**, 전사 없음).
> EPSG:25832. 관찰만·판정 금지·해석/프레이밍 없음. 셀별 출처 명시. 비교 LiDAR·img(raw)·ref 는 기존값 재사용.
> arm = {v6_protect, D=prior_full, D4} (full eval JSON) + D2(귀속 §5)·D3(무효 §6)는 D run 진단(별도 학습 arm 아님).

## ⚠ §0 출처 무결성 경고 (읽기전용 발견 — 김휘영 확인 필요)
D-수트 eval 은 한 arm 당 **gssem → smrf 순차**로 돌며 per-building `*_classified.las` · Roofer cityjson · val3dity 를 **덮어쓴다**.
→ 현재 디스크의 per-building 산출물은 **마지막=smrf read-out**. (mtime: roofer cityjsonl 23:42 · `*_val3dity.json` 23:42 · `ref_rms_d4.csv` 23:49 모두 > `eval_d4_gssem.json` 23:41, < `eval_d4_smrf.json` 23:44.)
| 메트릭 | read-out 정합? | 비고 |
|---|---|---|
| 생성 assembled/valid-solid (§1,§5,§6) | ✅ gssem 정합 | 결과 JSON `eval_*_gssem.json` 은 안 덮어써짐 |
| PSNR(train) (§4) | ✅ read-out 무관 | Stage-2 렌더 지표(분류 전) |
| **RMS→ref (§3)** | ⚠ **smrf 기준** | `ref_rms_{D,d4}.csv` = smrf 분류 .las 에서 산출 |
| **target-only 면수 (§2)** | ⚠ **smrf 기하** | on-disk roofer cityjson = smrf; gssem 은 CLIP(오염)만 |
| val3dity 오류코드 (§6) | ⚠ **복원불가** | gssem 리포트가 smrf 로 덮임 |
→ **gssem-정합 RMS·target-only 면수·val3dity 코드가 필요하면 gssem 재-eval(`tum_mob_eval --classifier gssem`, CPU/도커, ~20분, GPU·학습 무관) 1회 필요.** (현 작업=읽기전용이라 미실행; 승인 시 실행.)

## §1 생성 (조립안됨 REC 8동, tag=orig) — assembled/8 · valid-solid/8 · meanRMS→ref(REC)
| arm | density | assembled/8 | valid-solid/8 | meanRMS→ref(REC) | 출처(eval / rms) |
|---|---|---:|---:|---:|---|
| v6_protect (smrf) | dense | 2 | 2 | 2.91(n2) | eval_v6_protect.json / ref_rms_protect.csv |
| v6_protect (smrf) | acmp | 2 | 2 | 3.65(n4) | eval_v6_protect.json / ref_rms_protect.csv |
| D (gssem) | dense | 7 | 4 | 3.79(n4) | eval_prior_full_gssem.json / ref_rms_D.csv |
| D (gssem) | acmp | 7 | 3 | 2.53(n5) | eval_prior_full_gssem.json / ref_rms_D.csv |
| D4 (gssem) | dense | 7 | 2 | 2.98(n4) | eval_d4_gssem.json / ref_rms_d4.csv |
| D4 (gssem) | acmp | 7 | 3 | 1.83(n6) | eval_d4_gssem.json / ref_rms_d4.csv |
| img(raw_dense) | - | 0 | 0 | 1.84(n8) | eval_v6_raw.json / ref_rms_raw.csv |
| img(raw_acmp) | - | 3 | 3 | 7.64(n8) | eval_v6_raw.json / ref_rms_raw.csv |
| LiDAR | - | 7 | 7 | 1.36(n8) | eval_v6_raw.json / ref_rms_raw.csv |

## §2 품질 — 지붕 면수 (11동) · ref=baselines.json
> ⚠ **출처 주의(읽기전용 관찰)**: on-disk per-building Roofer cityjson 은 각 arm 의 **smrf eval 이 gssem eval 직후 덮어씀**
> (mtime: roofer cityjsonl 23:42 / eval_d4_gssem.json 23:41 / eval_d4_smrf.json 23:44). 따라서 아래 **target-only 면수 = smrf read-out 기하**다(gssem 아님).
> **gssem CLIP** 열은 `eval_*_gssem.json` 의 roof_surfaces(=gssem, 단 이웃 건물 포함=오염). gssem **target-only** 면수는 현재 디스크에서 복원 불가(재-eval 필요).

| bid | ref | D gssemCLIP | D4 gssemCLIP | D tgt(smrf) | D4 tgt(smrf) | v6p tgt(smrf) | img tgt | LiDAR tgt |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4906972 | 3 | 12 | 8 | 3 | 3 | 9 | 3 | 3 |
| 4907182 | 2 | 1 | 1 | 0 | 0 | 0 | 0 | 2 |
| 4906969 | 3 | 19 | 14 | 19 | 13 | 7 | 17 | 5 |
| 4908023 | 1 | 2 | 2 | 2 | 2 | 1 | 1 | 1 |
| 4907510 | 1 | 4 | 6 | 1 | 0 | 0 | 0 | 4 |
| 42364659 | 2 | 5 | 6 | 6 | 5 | 7 | 0 | 0 |
| 42364663 | 1 | 3 | 4 | 1 | 2 | 1 | 0 | 1 |
| 42364609 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 4908050 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 4908166 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 1 |
| 4908176 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 1 |

출처: gssemCLIP = `eval_{prior_full,d4}_gssem.json` roof_surfaces(이웃 오염); tgt(smrf) = `runs/mob_eval/<cfg>/roofer_*_orig/*.city.jsonl`(이웃 제외, **smrf 기하**); ref = `baselines.json`.

## §3 RMS→ref (m, orig) — meanRMS(11동 中 산출가능) + 초점 4906972·4906969·4908023
> ⚠ **출처 주의**: `ref_rms_{D,d4}.csv` 는 `tum_mob_ref_rms.py` 가 `runs/mob_eval/<cfg>/<bid>_orig_classified.las` 를 읽어 산출(line 98).
> 그 .las 는 smrf eval 이 덮어쓴 것(ref_rms_d4.csv mtime 23:49 > smrf eval 23:44). 즉 **D·D4 의 RMS→ref = smrf-분류 지붕점 기준**(gssem 아님).
> v6(`ref_rms_protect.csv`)=v6 정본 read-out=smrf 이라 정합; raw/LiDAR=단일 분류라 무관.
| arm | density | meanRMS(all) | 4906972 | 4906969 | 4908023 | 출처(csv) |
|---|---|---:|---:|---:|---:|---|
| v6_protect | dense | 1.89(n5) | 2.49 | 0.74 | 0.40 | ref_rms_protect.csv |
| v6_protect | acmp | 2.62(n7) | 2.27 | 0.49 | 0.95 | ref_rms_protect.csv |
| D | dense | 2.83(n7) | 2.79 | 0.96 | 0.94 | ref_rms_D.csv |
| D | acmp | 2.94(n8) | 2.74 | 7.64 | 0.48 | ref_rms_D.csv |
| D4 | dense | 2.25(n7) | 2.41 | 0.76 | 0.67 | ref_rms_d4.csv |
| D4 | acmp | 1.65(n9) | 2.81 | 0.63 | 0.45 | ref_rms_d4.csv |
| img(raw_dense) | - | 1.80(n11) | 2.97 | 1.29 | 0.77 | ref_rms_raw.csv |
| img(raw_acmp) | - | 6.09(n11) | 3.02 | 1.48 | 1.34 | ref_rms_raw.csv |
| LiDAR | - | 1.40(n11) | 2.41 | 1.17 | 0.91 | ref_rms_raw.csv |

## §4 PSNR(train, final) — TB metric/psnr_train
| arm | dense | acmp | 출처 |
|---|---:|---:|---|
| v6_protect | 20.27 | 20.30 | `gs_seed_dense_protect/tb`, `gs_seed_acmp_protect/tb` |
| D | 19.87 | 19.99 | `gs_prior_full_dense/tb`, `gs_prior_full_acmp/tb` |
| D4 | 20.08 | 20.15 | `gs_d4_dense/tb`, `gs_d4_acmp/tb` |

## §5 (D2) 조립 귀속 — 분류(read-out) × 학습(training-prior), assembled/8 · valid-solid/8 (REC)
| 학습 | 분류 | arm(config) | assembled/8 | valid-solid/8 | 출처 |
|:---:|:---:|---|---:|---:|---|
| ✗ | smrf | v6 (gs_seed_*_protect) [dense] | 2 | 2 | eval_v6_protect.json |
| ✗ | smrf | v6 (gs_seed_*_protect) [acmp] | 2 | 2 | eval_v6_protect.json |
| ✗ | gssem | v6sem (v6sem_*) [dense] | 3 | 2 | eval_v6sem_gssem.json |
| ✗ | gssem | v6sem (v6sem_*) [acmp] | 5 | 0 | eval_v6sem_gssem.json |
| ✓ | smrf | D-smrf (gs_prior_full_*) [dense] | 3 | 2 | eval_prior_full_smrf.json |
| ✓ | smrf | D-smrf (gs_prior_full_*) [acmp] | 2 | 2 | eval_prior_full_smrf.json |
| ✓ | gssem | D-gssem (gs_prior_full_*) [dense] | 7 | 4 | eval_prior_full_gssem.json |
| ✓ | gssem | D-gssem (gs_prior_full_*) [acmp] | 7 | 3 | eval_prior_full_gssem.json |

## §6 (D3) 무효 solid — canonical D4 gssem (eval_d4_gssem.json 기준), tag=orig, 11동
> ⚠ **오류유형 집계 불가(읽기전용)**: eval 의 `val3dity_valid` 는 gssem 시점 combined cityjson 으로 판정됐으나,
> 그 per-building val3dity 리포트는 smrf eval 이 덮어씀(현 디스크 val3dity.json = 전부 validity:True = smrf 기하). → **gssem 무효동의 오류코드는 현 디스크서 복원 불가**.
> 무효 '개수'는 gssem 결과 JSON 에 남아있어 아래 표로 보고. 코드(302/303/306/405)는 §8 인용(W_D2_D3 §D3가, D run) 참조 또는 gssem 재-eval 필요.

| arm | assembled(REC)/8 | valid-solid/8 | 무효-but-assembled 동(REC) | 출처 |
|---|---:|---:|---|---|
| D4 dense | 7 | 2 | 42364609, 42364663, 4907182, 4907510, 4908166 | eval_d4_gssem.json |
| D4 acmp | 7 | 3 | 42364659, 4907182, 4907510, 4908166 | eval_d4_gssem.json |

- D4 dense 전체 11동 中 assembled-but-invalid: 4906972, 4907182, 4906969, 4907510, 42364663, 42364609, 4908166
- D4 acmp 전체 11동 中 assembled-but-invalid: 4907182, 4908023, 4907510, 42364659, 4908166

출처: `eval_d4_gssem.json`(무효 개수, gssem). per-building 오류코드 디스크 파일은 smrf-덮어쓰기로 무효(§ 위 주의).

## §7 geoid 확인 — 각 arm config의 data_root
- v6_protect `gs_seed_dense_protect`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`
- v6_protect `gs_seed_acmp_protect`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`
- D `gs_prior_full_dense`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`
- D `gs_prior_full_acmp`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`
- D4 `gs_d4_dense`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`
- D4 `gs_d4_acmp`: data_root = `/workspace/JointBuildGS/results/tum_transfer/data_geoidfix`

→ 통합 arm(v6_protect·D·D2·D3·D4) **전부 `data_geoidfix`(post-fix)**. pre-fix 잔존 수치는 통합 arm 에 **없음**.
  (알려진 pre-fix geoid 이슈 = 초기 make-or-break 5-way ablation `eval_results.json`(vanilla/baseline/mutual/structure/both)의 LABEL ~48 m geoid 혼입 — **본 통합 범위 밖**, 메모리/`SESSION_HANDOFF` [[p2-makeorbreak-run]] 기록. 출처: 메모리, 디스크 미검증.)

## §8 인용문 (원문 그대로 — read-out·학습 귀속 정정)

### (a) 원 주장 — `docs/experiments/joint-optimization/w_d_prior_full/reports/W_D_prior_full.md` §2 (조립 회복 = read-out 단독)
> **핵심 귀속(read-out vs 학습-prior 분리)**: 동일 D 학습에 read-out만 바꾼 D-smrf(2–3/8) ≈ v6(2/8) ≪ D-gssem(7/8). → **조립 회복 = 레버 3(GS-의미가 SMRF 대체)**. depth/normal/structure 학습-prior 단독으론 조립 미회복. 이는 P0c "SMRF가 ACMP 지붕을 ground로 먹음" 진단을 직접 확증·연장한다.
>
> (동 문서 §0) 단 이 회복은 GS-의미 read-out(레버 3, SMRF 제거) 효과이고 depth/normal/structure 학습-prior은 **무효**(같은 학습에 SMRF read-out인 D-smrf는 2–3/8 ≈ v6 2/8).

### (b) 정정/철회 — `docs/experiments/evaluation/w_d2_d3/reports/W_D2_D3.md` (분류+학습 초가산적 시너지)
> **정정**: [[W_D_prior_full]] §2의 "회복=read-out 단독, 학습-prior 무효"는 **과단순화**였다. D-smrf≈v6는 "SMRF 하 학습 무효"만 말하고, v6+gssem(3–5/8)이 분류 단독 한계를 드러낸다. 정확히는 **분류+학습 둘 다 필요(시너지)**. 단 valid-solid는 D 3–4/8로 LiDAR 7/8 여전히 미달(위상 과제는 불변).
>
> **둘 다(D_gssem) = 7/8**: 가산 예측(2 + 학습기여 ~1 + 분류기여 ~1–3 = 4–5)을 **초과(7)** → **초가산적(super-additive) 시너지**. 분류는 학습이 키운 조밀·정합 점군 위에서만 7/8로 작동하고, 학습은 분류가 SMRF처럼 지붕을 먹지 않을 때만 조립으로 이어진다.

출처: (a) `docs/experiments/joint-optimization/w_d_prior_full/reports/W_D_prior_full.md` §0·§2 · (b) `docs/experiments/evaluation/w_d2_d3/reports/W_D2_D3.md` D2 "관찰 — 초가산적 시너지". 원문 그대로 인용.
