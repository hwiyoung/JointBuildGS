# W_D4 — 정규화 재학습(corrected, cp만 정규화) Phase 4 보고

> **관찰만, 판정=사람(김휘영).** 브랜치 `feature/p2-prior-full`. EPSG:25832. Docker(jointbuildgs:dev 학습 / p0-tools·3dgi/roofer 평가).
> 사양·사전등록(잠금) = `P2_D4_사양서_사전등록_20260625.md`(§6 판정기준·§7 cp 사다리 LOCKED). 본 문서는 **결과**(사전등록 아님).
> 질문: "**손실 균형을 바로잡으면(노이즈 depth/normal 제거 + cp 탈-지배) GS 지붕이 펴지고 과분할이 줄되, 생성(7/8)·무열화는 유지되나** — 품질을 GS 방법으로."

## §0 한 줄 관찰 (판정 없음)
**corrected D4**(cp만 정규화: cp 0.08→0.01·depth 0.1→0.03·normal→0, photo/nc/sem/na=D 유지)는 — 같은 고정 Roofer에서 —
**평지붕 4906972 면수 3=ref**(=D=LiDAR; target-only)·**RMS→ref 개선**(dense 2.83→2.25·acmp 2.53→**1.65**, LiDAR 1.40 접근·v6 1.89 상회)·
**곡면 4906969 과병합 19→13↓하되 과-평탄 아님**(RMS 0.76, 곡선 보존)·**생성 7/8 유지**(=D=LiDAR, 깊이 0.03에도)·
**제어 무열화**(4908023 RMS 0.94→0.67↓·면수 2=D·PSNR 20.08≥19.87). **대가 = valid-solid(dense) 회귀**(4→2; acmp 3=3, 위상 잔여).

## §1 설정 (corrected D4 = config-only 손실 균형, 엔진 무변경)
보고된 D(`gs_prior_full_{dense,acmp}`, w_structure 0.08) 대비 **손실 가중만** 변경(MUST-EQ 동일: data_geoidfix·sem_detach=false·max_iter 30000·densification v6-dense·seed_protect·G2 voxel 2.0·structure 게이트 15000·read-out gssem·Roofer 고정).

| 항 | D(보고) 유효 | **D4 유효** | 의도 |
|---|---|---|---|
| photo | 1.0 | **1.0** | D 유지(건강항) |
| nc | 0.05 | **0.05** | D 유지(건강항) |
| sem | 0.1 | **0.1** | D 유지(건강항) |
| structure na | 0.08 | **0.08** | D 유지 |
| **structure cp** | 0.08 (cp share 68%) | **0.01** | **탈-지배**(cp share 31%≈photo); 노이즈 MVS 핀 완화 |
| **depth** | 0.1 | **0.03** | de-noise(CV 1.74 노이즈 타깃) |
| **normal(외부)** | 0.15 | **0** | 외부 MVS 법선 제거(노이즈) |

- **정정 경위**: 초기 D4(전 항 정규화: photo 5.6·nc 2.1·sem 0.92)는 사전점검서 **초반 photo/psnr 열세**(nc 2.1 과제약). **"cp만 정규화" 최소 config로 정정**(config 오류 정정, 골대이동 아님; `P2_D4_사양서` §2·§8).
- **학습**: 2-GPU 병렬, dense/acmp 각 ~4.2/4.4h, 30000 step 완료(final.pt + TB maxstep 29990). **PSNR 20.08/20.15**(D 19.87/19.99 대비 무회귀). 사전점검 ①③④ 통과(`P2_D4_사양서` §3).
- **cp 발화(본런 모니터)**: cp 원시 15k→final = D4 30.3→17.9(dense)·36.1→14.6(acmp) vs D 28.2→16.7 — **D4도 cp 감소(발화)하나 D와 동등**. cp 탈-지배가 cp 원시곡선은 안 바꿈; **지붕 펴짐은 cp 압력이 아니라 depth-denoise+rebalance가 노이즈 핀을 푼 결과**(아래 RMS).

## §2 Axis A — 품질·정확도 (정본 11동, tag=orig)
### (가) 과분할 — **target-only 면수**(클립-이웃 제외; eval 합산 메트릭은 이웃 오염 → §7 주의)
| bid | set | ref | **D4** | D | v6 | img | LiDAR |
|---|---|---|---|---|---|---|---|
| 4906972 | flat | 3 | **3** | 3 | 9 | 3 | 3 |
| 4907182 | flat | 2 | 0 | 0 | 0 | 0 | 2 |
| 4906969 | curved | 3 | **13** | 19 | 7 | 17 | 5 |
| 4908023 | control | 1 | 2 | 2 | 1 | 1 | 1 |
| 4907510 | rec | 1 | 0 | 1 | 0 | 0 | 4 |
| 42364659 | rec | 2 | 5 | 6 | 7 | 0 | 0 |

- **평지붕 4906972 = 3 = ref**(=D=LiDAR): D4 평지붕은 **참조 수준 면수**(과분할 없음). v6은 9였음 → D/D4가 해결, D4 유지.
- **곡면 4906969 = 13**(D 19↓, v6 7, ref 3): D4가 D 대비 **과분할 6면 감소**하나 곡면 분할로 ref엔 미달(Roofer default epsilon 0.3이 곡면을 다면 분할). **과-평탄 아님**(§6 그림: 곡선 따라 면 근사).

### (나) RMS→ref (m, 낮을수록 참 지붕에 근접; LiDAR 1.40·v6 1.89가 비교축)
| arm | meanRMS→ref | vs D | vs LiDAR |
|---|---|---|---|
| **D4_dense** | **2.25**(n7) | D 2.83 ↓0.58 | 1.40 미달 |
| **D4_acmp** | **1.65**(n9) | D_acmp 2.53 ↓ | LiDAR 1.40 **접근**·v6 1.89 **상회** |
| D_dense | 2.83 | — | — |
| v6_dense | 1.89 | — | — |
| LiDAR | 1.40 | — | (상한) |

- **D-수트 최초로 RMS가 LiDAR 쪽으로 이동**: depth-prior를 0.03으로 낮추고 외부 normal 제거 → 노이즈 1024px MVS(자체 ~4 m)에 덜 핀 → 참 지붕에 더 근접. D4_acmp 1.65는 v6 1.89도 상회.
- **평지붕 4906972**: D4 RMS **2.41 = LiDAR 2.41**(D 2.79·v6 2.49) — **RMS→LiDAR 수렴**. 곡면 4906969: D4 0.76(D 0.96·v6 0.74·LiDAR 1.17) — 저잔차(과-평탄 아님).

### (다) valid-solid (위상 유효 solid; 회복 8동 orig)
- D4_dense **2/8**(D_dense 4/8 ↓)·D4_acmp **3/8**(=D_acmp 3/8). LiDAR 7/8. → **dense 위상 회귀**(2동 무효화), acmp 동일. 조립은 되나(아래 §3) solid 유효성은 dense서 하락 = **위상 잔여 과제**.

## §3 Axis B — 생성 (조립안됨 8동, tag=orig): assembled/8 · valid-solid/8 · meanRMS
| arm | assembled/8 | valid-solid/8 | meanRMS(REC) |
|---|---|---|---|
| **D4_dense(gssem)** | **7** | 2 | 2.98(n4) |
| **D4_acmp(gssem)** | **7** | 3 | 1.83(n6) |
| D_dense / D_acmp | 7 / 7 | 4 / 3 | 3.79 / 2.53 |
| v6_dense / v6_acmp | 2 / 2 | 2 / 2 | 2.91 / 3.65 |
| img(raw)_dense / acmp | 0 / 3 | 0 / 3 | 1.84 / 7.64 |
| **LiDAR** | **7** | **7** | 1.36 |

- **생성 유지**: D4 **7/8 조립 = D = LiDAR**, 깊이를 0.03으로 낮췄음에도 회복 유지(depth↓가 생성 안 깨뜨림). v6 2/8·img 0~3/8 대비 우위.
- **회복동 밀도**: seed-protect로 footprint 점 유지(예 4907182 fp=992 = D, A-gate). 단 4907182은 D·D4 모두 **분류 지붕점 0**(불투명도 붕괴, D4 범위 밖) → RMS 산출 불가(= D, 회귀 아님).
- valid-solid는 §2(다) — dense 2(D 4↓).

## §4 Axis C — 무열화 (제어 4906972·4908023)
| bid | D4 RMS | D RMS | v6 RMS | D4 면(tgt) | D 면 | ref | PSNR |
|---|---|---|---|---|---|---|---|
| 4906972 | **2.41** | 2.79 | 2.49 | 3 | 3 | 3 | — |
| 4908023 | **0.67** | 0.94 | 0.40 | 2 | 2 | 1 | — |
| (train) | — | — | — | — | — | — | D4 **20.08** / D 19.87 |

- **제어 D보다 안 나빠짐**: 4906972·4908023 모두 D4 RMS < D(개선), 면수 = D. PSNR 무회귀(20.08≥19.87). v6 대비 4908023 RMS는 소폭 높음(0.67 vs 0.40)나 D보단 개선.

## §5 Axis D — 전역정렬 watch
- 통째로 기운 채 조립되는 신규 동 **없음**(관찰): D4 per-building RMS→ref가 전반적으로 D 이하(기움이면 RMS 급증), dz 정렬(40–56 m geoid) 내 정상 수렴. §6 그림서도 기운 조립 없음.

## §6 Axis E — 정성 그림 (`docs/figs/W_D4_qual/`, [D4 | image | LiDAR | ref] × [점군 | 조립모델 면별색])
- **평지붕 [4906972.png](../../../../figs/W_D4_qual/4906972.png)**: D4 조립모델이 평탄한 박공/평지붕으로 ref·LiDAR와 정합(과분할 없음, 면수 3=ref).
- **평지붕 [4907182.png](../../../../figs/W_D4_qual/4907182.png)**: D4·image 점군 희박(불투명도 한계) → 조립 미흡; LiDAR만 ref 재현.
- **곡면 [4906969.png](../../../../figs/W_D4_qual/4906969.png)**: D4 조립모델이 **곡선을 다수 평면으로 근사**(13면, 곡면 형상 보존) — **한 평면으로 뭉개지 않음**(과-평탄 반증). D(19면)보다 깔끔, LiDAR(5면)보단 분할 많음.
- **제어 [4908023.png](../../../../figs/W_D4_qual/4908023.png)**: D4가 ref와 정합(평지붕), 무열화 시각 확인.

## §7 사전등록 §6 판정 패키지 (판정=김휘영, 본 문서는 자료만)
> `P2_D4_사양서_사전등록_20260625.md` §6(LOCKED) 기준에 결과를 **그대로 대입**(골대이동 금지).

| §6 성공 조건 | 관찰 결과 | 충족? (판정=사람) |
|---|---|---|
| 1. 평지붕 과분할↓ref접근 **AND** RMS→LiDAR 개선 | 4906972 면 3=ref·RMS 2.41=LiDAR(D 2.79↓) | 충족 방향 |
| 2. 생성 ≥7/8 · 회복동 밀도 미감소 | **7/8**(=D=LiDAR)·fp 점 = D | 충족 |
| 3. 제어 D보다 악화 없음 | 4906972·4908023 RMS↓·면=D·PSNR≥D | 충족 |
| 4. 전역 기움 신규 없음 | 없음(§5) | 충족 |
| 5. 곡면 과-평탄 아님 | 4906969 RMS 0.76·곡선 보존(§6 그림) | 충족 |
| **대가(부분지지 신호)** | **valid-solid dense 4→2 회귀**(위상); 곡면·평지붕 4907182 미해결 | — |

- **관찰 종합(판정 없음)**: §6 성공조건 1–5는 **충족 방향**(평지붕 ref-수준·RMS→LiDAR 수렴·생성 유지·무열화·곡면 비-과평탄). 단 **valid-solid(dense) 회귀**가 사전등록 "부분지지(메커니즘 작동하나 대가 동반)"에 해당할 수 있는 **위상 비용**. → 성공 vs 부분지지 경계는 **김휘영 판정**.
- **§7 cp 사다리**: cp는 발화(감소)했고 지붕도 펴졌으므로 "cp 미발화 → 사다리" 분기는 **불발동**. (지붕 펴짐의 동력은 cp 압력이 아니라 depth-denoise였음 — §1.)
- **메트릭 주의**: eval 합산 over-seg 메트릭은 **클립-이웃 건물 오염**(예 4906972 eval=8/12 vs target-only=3). 본 보고 면수는 **target-only**(이웃 제외)로 재계산 — D 보고(W_D_prior_full)의 합산 수치와 직접 비교 시 이 차이 유의.

## §8 재현성
- 학습: `scripts/evidence_and_attributes/p2_gsjso/run_d4.sh`(config `gs_d4_{dense,acmp}.yaml`; 사전점검 `gs_d4_dense_precheck.yaml`). 엔진 무변경(가중은 config만).
- 평가: `tum_mob_eval.py --classifier {gssem,smrf}`(→`eval_d4_{gssem,smrf}.json`) + `tum_mob_ref_rms.py --arms gs_d4_{dense,acmp}`(→`ref_rms_d4.csv`).
- 표·면수: `scripts/evidence_and_attributes/p2_gsjso/d4_table.py`(→`REPORT_D4.md`); target-only 면수·정성 그림: `d4_qual_figs.py`(→`docs/figs/W_D4_qual/`).
- 비교 baseline 재사용: `eval_prior_full_gssem.json`(D)·`eval_v6_protect.json`(v6)·`eval_v6_raw.json`(raw/LiDAR)·`baselines.json`(ref)·`ref_rms_{D,v6,raw}.csv`.
- `runs`/버전: `results/tum_transfer/mob/gs_d4_{dense,acmp}/versions.txt`(commit 5dd26cc). 한 커밋 "D4".
