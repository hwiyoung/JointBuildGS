# W_D — 후속 감사 (valid-solid 오류·정밀분리 실현성·법선 발화·품질 세부)

> 읽기 전용·관찰만·판정 없음. feature/p2-prior-full. 본보고 [[W_D_prior_full]]·손실 [[W_D_loss_audit]].
> 데이터(`results/`·`runs/`)는 gitignore. #1 val3dity 상세는 smrf eval이 덮어써서(마지막 실행) 4동만 gssem 재생성(코드·실험 무변경, 진단 재생성).

## 1) valid-solid 무효 동 — val3dity 오류 유형 (D_dense_gssem, tag=orig)

조립(roof>0)됐으나 invalid인 4동. val3dity 코드(3xx=shell, 4xx=solid). 점수·밀도·RMS 병기:

| bid | facets | val3dity 코드 | 유형 | n_pts | dens(/m²) | roof RMS(m) |
|---|---|---|---|---|---|---|
| 4907182 | 1 | **302** | shell 비폐합(not closed, 워터타이트 아님) | 282k | 39 | **0.11** |
| 4907510 | 4 | **306** | shell 면방향 오류(wrongly oriented) | 369k | 116 | 1.44 |
| 4908176 | 1 | **405** | solid shell 방향 오류(wrong orientation) | 83k | 10 | 0.62 |
| 4906969 | 19 | **303** | shell 비-다양체(non-manifold edge/vertex) | 1.94M | 640 | 1.84 |

- **공통 관찰**: 네 동 모두 **점군은 충분·정확**(RMS 0.11–1.84 m, 밀도 10–640/m²)인데 오류는 전부 **shell 위상**(비폐합 302 / 면·solid 방향 306·405 / 비-다양체 303)이다. **자기교차(305)·점 부족(101)·비평면(203)은 없음**.
- **가름(점군 vs Roofer 위상)**: 점 부족·노이즈성 오류(1xx/2xx/305) 부재 + 위상성 오류(폐합·방향·다양체)만 → **Roofer 위상(구조화) 단계** 문제로 가리킴, 점군 밀도 문제 아님. 특히 4906969는 19면 과분할이 비-다양체를 유발(과분할↔위상 연동), 4907182는 정확한 점(0.11 m)에도 shell 비폐합(단일면+ground 합성 폐합 실패 가능).
- 출처: 재생성 리포트 `phases/p0-audit/runs/mob_eval_gssem_diag/gs_prior_full_dense/DEBY_LOD2_*_orig_val3dity.json`(키 `all_errors`/`validity`); 오케스트레이터 val3dity 호출 [tum_mob_eval.py:148](phases/p2-gsjso/scripts/tum_mob_eval.py#L148).

## 2) 정밀 분리("v6 ckpt에 gssem read-out만") 실현성

- **재학습 불필요, 단 재추출 필요**: v6 TSDF npz(`tsdf_gs_seed_{dense,acmp}_protect.npz`)는 키가 `P_utm/P_utm_clean`뿐 — **P_class 없음**(구 추출기 산출). gssem 어댑터([_mob_prep_las_gssem.py:69-71](phases/p2-gsjso/scripts/_mob_prep_las_gssem.py#L69))는 `P_class_clean`를 요구하므로 **어댑터만 재실행 불가**.
- **빠진 것 = 의미-운반 추출**: v6 ckpt(`gs_seed_*_protect/ckpt/final.pt`)에는 `sem_logits` 보존됨([model.py:112-120](src/stage2/model.py#L112); export_ply_semantic로 확인). 따라서 **새 의미 추출기**([tum_mob_tsdf_extract.py:62-71,118-141](phases/p2-gsjso/scripts/tum_mob_tsdf_extract.py#L62))를 v6 ckpt에 재실행 → P_class npz → gssem 어댑터 → Roofer.
- **예상 소요**: 추출 = **GPU 필요**(rasterization 2-pass), D 추출 실측 2.7–3.1분/arm → v6 2arm ~6분 GPU. 이후 eval(gssem 분류+Roofer+val3dity) = GPU 불필요, ~3분/arm. **총 ~12분**. 이는 동일 v6 기하에 read-out만 바꾸는 **가장 깨끗한 read-out 분리**(D는 학습-prior+read-out 동시 변경이라 본보고는 D-smrf로 간접 분리; 이건 직접 분리).

## 3) 법선·깊이·구조 발화 (gs_prior_full_dense, TB 전구간)

원시(비가중) 손실 추이. 로그 `results/tum_transfer/mob/gs_prior_full_dense/tb` (loss/normal·depth·structure{,_na,_cp}).

| step | L_normal | L_depth(m) | L_struct (na/cp) |
|---|---|---|---|
| 0 | 0.258 | 42.6 | 0 |
| 5000(depth ramp 시작) | 0.339 | 5.36 | 0 |
| 10000(ramp 끝) | 0.442 | 3.81 | 0 |
| 15000(struct 게이트) | 0.442 | 3.90 | 28.18 (0.006/28.175) |
| 20000 | 0.316 | 5.05 | 20.74 (0.005/20.73) |
| 29990 | 0.453 | 2.05 | 16.67 (0.003/16.66) |
| **구간평균** | **[0-5k] 0.351 → [25-30k] 0.321** | **[0-5k] 23.6 → [25-30k] 3.27** | **[15-16k] 24.4 → [25-30k] 16.1** |

- **L_normal = 평탄/미발화**: 0.35→0.32 (≈42°→47°, 노이즈 수준). w_normal 0.05→0.15 상향에도 **렌더 법선이 MVS 법선으로 수렴 안 함**. 법선 감독 실질 무효.
- **L_depth = 발화**: warmup 5000 후 가중 들어오자 **23.6→3.3 m로 급감**(MVS 깊이로 수렴). 단 **~3.3 m는 1024px geom-MVS 자체 노이즈 바닥**(L_depth 590 smoke와 동일) → 참 지붕 아닌 노이즈 MVS에 핀 = RMS→ref가 LiDAR로 안 가는 이유.
- **L_structure = cp만 발화**: cp 28.2→16.7 m²(RMS 점-평면 5.3→4.1 m, 완만 평면화). **na ≈ 0.005로 무시 가능**(normal-align 거의 0; 구조 손실 = 사실상 coplanar 단독).

## 4) 품질 세부 — 과분할 발생원 분리 (tag=orig, REPORT_D §A)

facet 수(ref 대비) read-out·학습 분해:

| bid | ref | gssem | smrf | v6 | 발생원 |
|---|---|---|---|---|---|
| 4906972(CTL) | 3 | 12 | **3** | 9 | **read-out**: smrf=3(=ref, G2가 v6 9→3 수렴) but gssem read-out이 12로 재분할 |
| 4906969 | 3 | 19 | 19 | 7 | **학습**: 두 read-out 모두 19(≫v6 7) → depth/structure 학습이 이 지붕을 분할 |
| 4908023(CTL) | 1 | 2 | 2 | 1 | read-out 무관, 경미(+1) |
| 42364663(REC) | 1 | 3 | 1 | 1 | **read-out**: gssem 3 vs smrf 1 |

- **과분할 두 경로 분리**: (가) **read-out 경로** — gssem이 smrf보다 facet↑(4906972 3→12, 42364663 1→3): GS-의미가 wall/roof 점을 building으로 더 넣어 Roofer가 더 잘게 나눔. (나) **학습 경로** — 4906969는 read-out 무관하게 v6 7→19: depth/structure 학습-prior 자체가 분할 증가.
- **G2 평면화가 ref로 수렴시킨 유일 사례**: 4906972 **smrf** 3=ref 3(v6 9 대비 감소) — 구조 lever 효과는 smrf read-out에서만 가시화, gssem read-out에 가림.

---
### 한 줄 종합 (판정 없음)
invalid 4동은 전부 **위상(shell 폐합·방향·다양체) 오류**(점군 충분·정확) → Roofer 구조화 단계 과제; gssem-only 분리는 v6 ckpt **재추출(~6분 GPU)+eval로 가능**; 본런에서 **depth 발화·structure cp 완만 발화·normal 미발화**; 과분할은 read-out(gssem↑)·학습(4906969↑) 두 경로, G2의 ref수렴은 4906972 smrf만.
