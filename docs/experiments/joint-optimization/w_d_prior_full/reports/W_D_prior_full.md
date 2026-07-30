# W_D — 전체 prior 수트 (depth/normal + structure-G2 + GS-semantic) Phase 4 보고

> 관찰만, 판정=사람(김휘영). 브랜치 `feature/p2-prior-full`. EPSG:25832. Docker(jointbuildgs:dev 학습 / p0-tools·3dgi/roofer 평가).
> 질문(점 6의 두 절반 첫 시험): "깊이·법선 감독 + 구조 강화 + GS-의미 분류를 켠 GS가 (가)조립안됨을 살리고 (나)과분할을 줄이고 정확도를 올리나."
> 데이터(`results/`)는 gitignore. 정량 표 = `results/tum_transfer/mob/REPORT_D.md`(재생성: `phases/p2-gsjso/scripts/d_prior_full_table.py`).

## 0) 한 줄 관찰 (판정 없음)

**생성**: 조립안됨 8동 중 prior-on GS가 **7/8 조립(= LiDAR 7/8)** vs v6 2/8·raw 0/8 — **단 이 회복은 GS-의미 read-out(레버 3, SMRF 제거) 효과이고 depth/normal/structure 학습-prior은 무효**(같은 학습에 SMRF read-out인 D-smrf는 2–3/8 ≈ v6 2/8). valid-solid는 4/8로 LiDAR 7/8 미달. **품질**: 과분할 net |Δfacet| 3.5 vs v6 3.0(레버 2 G2는 SMRF read-out의 일부 건물 4906972 9→3 ref수렴만, gssem read-out은 과분할↑)·RMS→ref **2.8 m로 LiDAR 1.4 m 미수렴**(v6 1.9 m 대비 동등~소폭 악화). **무열화**: 제어 2동 RMS ~0.3–0.5 m 악화·PSNR 19.9≈v6 무회귀.

## 1) 설정 (MUST-EQ 유지 + 3 레버 ON)

v6 `gs_seed_{dense,acmp}_protect` 대비 변경분만(나머지 MUST-EQ 동일: data_root·sem_detach=false·w_sem .1·w_nc .05·max_iter 30000·densification v6-dense·seed_protect):
- **L1 깊이·법선 감독**: `w_depth 0.1·w_normal 0.15` (warm-up 5000 후 5000-step 선형 ramp). 맵 = COLMAP PatchMatch(1024px, geom-consistency) 937/937, `data_geoidfix/stereo`. **포즈=학습 카메라 동일**(심링크 증명).
- **L2 구조 강화**: `structure_grouping=g2`(면급 union-find, 1735~3227 그룹 vs G1 패치급 175k) + `w_structure 0.08`(Phase-2 사전점검서 0.3→0.08 재조정: 0.3은 coplanar m² 단위로 total의 85% 지배·과-평탄화 위험; [[W_D_loss_audit]] 참조).
- **L3 GS-의미 분류**: 학습 X. 추출(`tum_mob_tsdf_extract` 의미 voxel-히스토그램) → `_mob_prep_las_gssem`(Roof/Wall→building 6, Terrain→ground 2 + data-derived ground 합성, **SMRF·GT-footprint-overlay 제거**) → 기존 Roofer/val3dity. eval `--classifier {gssem,smrf}`.
- 학습: dense 235.7분·acmp 261.6분(2-GPU 병렬), PSNR 19.87/19.99, final N 3.69M/3.88M.

## 2) 축 B — 생성 (조립안됨 8동, tag=orig)

| arm | assembled/8 | valid-solid/8 |
|---|---|---|
| **D_dense_gssem** | **7** | 4 |
| **D_acmp_gssem** | **7** | 3 |
| D_dense_smrf | 3 | 2 |
| D_acmp_smrf | 2 | 2 |
| v6_dense / v6_acmp | 2 | 2 |
| raw_dense | 0 | 0 |
| **LiDAR** | **7** | **7** |

- **핵심 귀속(read-out vs 학습-prior 분리)**: 동일 D 학습에 read-out만 바꾼 D-smrf(2–3/8) ≈ v6(2/8) ≪ D-gssem(7/8). → **조립 회복 = 레버 3(GS-의미가 SMRF 대체)**. depth/normal/structure 학습-prior 단독으론 조립 미회복. 이는 P0c "SMRF가 ACMP 지붕을 ground로 먹음" 진단을 직접 확증·연장한다.
- assembled 7/8은 LiDAR와 동률이나 **valid-solid 4/8 < LiDAR 7/8** — 조립되나 위상적 유효 solid는 절반.
- 밀도/커버리지: D는 v6보다 많은 회복 건물에 footprint 내 building 점을 산출(레버 3가 지붕점을 building으로 보존). 일부 회복 지붕은 **sub-meter 정확**(4907182 0.20 m·4908050 0.53 m·4908166/42364609 LiDAR급).

## 3) 축 A — 품질·정확도 (정본 11동, tag=orig)

`results/tum_transfer/mob/REPORT_D.md` §A 표 참조. 요지:
- **과분할**(mean |facets−ref|, assembled): D_gssem 3.4–3.5 · D_smrf 2.4–3.5 · **v6 1.2–3.0** · LiDAR 0.5. → D는 net 과분할 **미감소**(v6와 동등~소폭 악화). 단 **SMRF read-out·일부 건물에선 G2가 감소**(4906972: D-smrf 3 = ref 3 vs v6 9; gssem은 12). gssem read-out 자체가 facet을 늘림.
- **RMS→ref**(m): D ~2.8 · v6 ~1.9 · LiDAR 1.4. **D는 LiDAR쪽으로 미수렴**; 비교 가능 건물에선 v6와 동등~0.3–1 m 악화. depth-prior가 1024px MVS(자체 노이즈 ~4 m, [[W_D_loss_audit]])에 핀되어 참 지붕으로 더 못 당김.

## 4) 축 C — 무열화 (제어 4906972·4908023)

| bid | D RMS | v6 RMS | D facets(smrf/gssem) | v6 facets | ref |
|---|---|---|---|---|---|
| 4906972 | 2.79 | 2.49 | 3 / 12 | 9 | 3 |
| 4908023 | 0.94 | 0.40 | 2 / 2 | 1 | 1 |

- RMS 소폭 악화(~0.3–0.5 m). 과분할은 **혼합**: SMRF read-out에선 4906972가 9→3(ref 수렴, G2 효과)·gssem에선 12(악화). PSNR 19.9 ≈ v6 ~20(광도 무회귀).

## 5) G1 판정 패키지 (사람용 의사결정 자료)

판정 게이트(P0 스타일, 임계=사람). 본 실험이 제공하는 결정 자료:

| 가설 | 관찰 | read-out 귀속 |
|---|---|---|
| (가) 조립안됨 회복 | **7/8 (=LiDAR)**, v6 2/8 | **레버 3(read-out)** 단독 효과; 레버 1·2 무효(D-smrf≈v6) |
| (나) 과분할 감소 | net 미감소(3.5 vs v6 3.0) | G2(레버 2) 일부 건물만(smrf); gssem read-out은 과분할↑ |
| (다) 정확도 향상(RMS→LiDAR) | **미수렴**(2.8 vs LiDAR 1.4, v6 1.9) | depth-prior(레버 1) 효과 없음(노이즈 MVS 핀) |
| 무열화 | PSNR 무회귀, RMS ~0.3–0.5 m 악화, 과분할 혼합 | — |

- **결정적 함의(사람 검토)**: "make-or-break"의 생성 축은 **미분 가능 렌더링 기하 prior가 아니라 GS-의미 read-out**이 푼다. 이는 P2 가설(공동 최적화가 surface evidence를 개선)에 대해 — 적어도 본 가중·해상도·일정에선 — **기하 prior 무효 + read-out 결정적**을 가리킨다. valid-solid 4/8(<LiDAR 7/8)은 구조화(위상) 잔여 과제.
- **혼선 주의**: D는 학습-prior와 read-out을 동시에 켜므로 gssem-vs-smrf 분리(본 보고)가 귀속의 핵심. 정밀 분리 후속(예: v6 ckpt에 gssem read-out만; depth-prior 고해상도/스케줄 재튜닝)은 미착수.

## 6) 재현성

- 학습: `phases/p2-gsjso/scripts/run_prior_full.sh` (config `gs_prior_full_{dense,acmp}.yaml`). 맵 생성: `prior_full_stereo.sh`(GPU=1 MAXSZ=1024 ITERS=3).
- 평가: `tum_mob_eval.py --classifier {gssem,smrf}` + `tum_mob_ref_rms.py --arms gs_prior_full_{dense,acmp}`.
- 표: `d_prior_full_table.py` → `REPORT_D.md`. 사전점검 손실 감사: `docs/experiments/joint-optimization/w_d_loss_audit/reports/W_D_loss_audit.md`.
- `runs`/버전: 각 arm `results/tum_transfer/mob/<arm>/versions.txt`. 한 커밋 "전체 prior 수트".
