# C2 — opacity 진단: alpha 게이트 우회로 in-scope 0점이 회복되나. 관찰만, 판정=김휘영.

> 작성 2026-06-24. branch feature/p2-seed-protect. EPSG:25832 · Docker(p0-tools/dev) · **CPU·읽기전용·재학습 없음**.
> C 기존 ckpt(it=25k)의 Gaussian 위치를 opacity 무시하고 추출(=alpha>0.5 TSDF 게이트 우회) → v6/C와 동일 SMRF→Roofer→val3dity.
> 스크립트 `c2_dump_means.py`(ckpt→P_utm) + 기존 `tum_mob_eval.py`·`tum_mob_ref_rms.py`. 산출 `results/.../eval_bypass.json`·`ref_rms_bypass.csv`.

## Phase 0 — 확인
1. ckpt: gs_seed_{dense,acmp}_protect/ckpt/final.pt (763M/773M, it=25k) ✓.
2. **seed-flag in ckpt = NO** (state_dict=means/quats/log_scales/opacities_raw/sh0/shN/sem_logits) → bypass는 전체 means 위치 사용.
3. 엔진 `SeedProtectStrategy._prune_gs`: `is_prune &= ~is_seed` = **remove에서만 면제**, opacity gradient **미차단** → 옵티마이저가 씨드 op를 0으로. (리뷰 일치)
4. **densification config (사용자 질문 해소)** — C는 **v6 dense 그대로 유지, 변경 없음(sparse식 아님)**:

| key | dense_protect | acmp_protect | v6_dense | v6_acmp | v6_sparse |
|---|--|--|--|--|--|
| grow_grad2d | 1.0e-3 | 1.0e-3 | 1.0e-3 | 1.0e-3 | **5.0e-4** |
| refine_every | 200 | 200 | 200 | 200 | **100** |
| refine_stop_iter | 20000 | 20000 | 20000 | 20000 | **25000** |
| reset_every·prune_opa·grow/prune_scale3d·max_iter | 동일 | 동일 | 동일 | 동일 | 동일 |

→ protect = v6 dense **byte-동일**. C가 densification을 throttle한 게 아니라 v6 dense를 승계(throttle은 v6 단계에서 dense-init용으로 이미 적용된 것).

5. **Opacity 분포 (ckpt 정량)**: median **0.0038**, p90 0.0039 (≈96% Gaussian이 op~0.004), **op>0.5는 3.7%(~115k)뿐**. in-scope 5 footprint 씨드 op0.00·위치 유효(42364663=19132·4907510=4017·4907182=994·4908050=1314·4908176=401). → "살아있되 투명"의 정확한 opacity = **~3.8e-3**.

## Phase 1 — 게이트 우회 추출 (in-scope 5, matched: 지붕점수 / 조립)
| 건물 | GS-정상 d/a | **우회(bypass)** d/a 점수 | 우회 solid d/a | 우회 RMS→ref d/a | raw_dense d/a (solid) | raw_lidar (solid) |
|---|--|--|--|--|--|--|
| 42364663 | 982/993 | 1081/1144 | **Y/Y** | 7.07/8.36 | 1124/1113 (**N**) | 672 (Y) |
| 4907510 | 3/1024 | 886/868 | N/N | 3.21/2.86 | 1392/1287 (Y) | 2056 (Y) |
| 4907182 | **0**/21 | **83/108** | N/N | **0.51**/10.4 | 242/242 (N) | 1837 (Y) |
| 4908050 | **0/0** | **19/77** | N/N | **0.39**/24.2 | 38/81 (N) | 1403 (Y) |
| 4908176 | **0/0** | **63/93** | N/**Y** | **0.22**/7.42 | 168/251 (N) | 642 (Y) |

- **지붕점 회복**: GS-정상 0이던 곳이 bypass로 **dense 4/5·acmp 2/5 회복**(0→19~108). **조립 회복**: dense 0/5·acmp 1/5(4908176 acmp만).
- **dense bypass RMS→ref 0.2~0.5m** (4907182·4908050·4908176) = 씨드 위치가 **참조 지붕면에 정확**. acmp는 7~24m(smear).

## 관찰 (판정 금지)
1. **점-blocker = opacity/alpha 게이트 (확정·고칠 수 있는 artifact)**: 씨드는 op≈3.8e-3로 투명 → TSDF alpha>0.5에서 탈락 → in-scope 0점. **위치는 유효**(우회 시 지붕점 회복, dense RMS 0.2~0.5m로 참조면에 정확). 레버: 씨드 opacity 하한(floor) 또는 opacity gradient detach.
2. **조립은 우회만으론 미회복 (cloud-limited)**: 4907182·4908050·4908176은 점이 돌아와도 미조립이고, **raw_dense(점 더 많음 242/81/168)도 미조립** — Roofer가 그 밀도로 구조화 불가. **raw_lidar(642~1837·조밀)만 조립**. → 조립엔 opacity 외 **더 조밀·구조화된 증거** 필요(W4c: near-nadir 커버리지 결손과 정합).
3. **42364663은 GS 씨드가 raw_dense를 능가**: bypass solid Y인데 raw_dense는 N → 그 자리 GS 씨드 위치가 raw보다 조립에 유리.
4. densification은 C에서 **v6 dense 유지**(변경 없음) → 조립실패가 densification 변경 탓은 아님.

## 한 줄 (판정 금지)
**alpha 게이트 우회로 in-scope 지붕점 dense 4/5·acmp 2/5 회복(dense RMS→ref 0.2~0.5m=위치 정확), 조립 dense 0/5·acmp 1/5 — 점-blocker는 opacity/alpha(고칠 수 있음), 조립은 cloud-limited(4907182·4908050·4908176은 raw_dense도 미조립, LiDAR 밀도만 조립). densification은 C에서 v6 dense 유지.**
→ full fix 재료: 씨드 opacity floor/detach로 점은 회복되나, 조립까지는 더 조밀·구조화된 증거(joint-opt L_structure / 나디르 재촬영)가 추가로 필요(판정=사람).

## 산출
- eval_bypass.json/csv · ref_rms_bypass.csv · bypass/bypass_{dense,acmp}.npz · c2_dump_means.py.
