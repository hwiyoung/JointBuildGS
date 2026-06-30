# W_phaseB_structure — Phase B: 자기지도 다시점 평면 일관성 학습 (관찰만·판정 금지)

> **실험 2 / Phase B.** 브랜치 `feat/p2-structure-learn`. EPSG:25832. Docker. 관찰만, 판정 = 김휘영.
> 배경(분기 진단 `W_overseg_faithfulness`): GS 과분할 = **결함**(복합 지붕서 면을 실 층에서 **±1~2.5 m 어긋나게** 놓음). 약한 고리 = 평면성 손실(cp)의 **손으로 정한 0.5 m 묶기(merge_d_tol)**. 높이만으론 노이즈가 단차보다 커 못 가름 → **영상·다시점 증거로 구조를 학습**한다. 정답 라벨 없는 자기지도부터(순환 회피).
> ⚠ 용어: **cp** = 평면성 손실(coplanar loss, 학습항). **MVC** = 다시점 일관성(multi-view consistency, 이번에 추가하는 자기지도 항).
> 목표(B1·최소 첫 시험): 다시점 기하 일관성(PGSR/ULSR식)을 학습에 더해 **떠 있는 면이 실 층 높이로 끌려오나** 본다 — **면수가 아니라 높이 정확도**가 표적.

---

## §0 Step 0 — repo 확인 + 삽입 가능성 판정 (완료, 게이트 통과)

> 7-에이전트 병렬 코드 매핑(`ws6ta2bog`, 382k tok) + 핵심 파일 직접 정독으로 교차검증. **결론: 삽입 가능 = 확정. 엔진 수술 불필요, 가산적(additive) 작업.** 막힘 없음 → 진행 가능.

### §0.1 현재 cp 손실·묶기 구조 (왜 ±1~2.5 m를 못 고치나)

- **cp(L_coplanar)** = `mean_{i∈grouped} (n_k·c_i + d_k)²` — 그룹 대표평면 `(n_k, d_k)`에 가우시안 중심 `c_i`를 끌어내림. **대표평면은 detach**(고정 타깃)이고 **그 그룹 멤버들로부터 적합**된다 → `src/stage2/loss/structure.py:42-52`. 즉 한 그룹이 통째로 틀리면 끌어줄 외부 신호가 없다.
- **묶기(g2)**: voxel 2 m + 26-이웃 union-find + `_coplanar` 술어 = `|n_i·n_j|>0.92 AND 국소 점-평면거리 < merge_d_tol(0.5 m)` (단일연결) → `src/stage2/grouping.py:246-254`. **0.5 m 게이트가 단차-인지**(>0.5 m 차이 면은 병합 안 함)이지만, 바로 그래서 **실 층에서 ±1~2.5 m 떠 있는 면은 자기 그룹에 고립**되어 끌어줄 이웃 평면이 없다.
- **gs_d4에서 cp는 이미 약화됨**(`w_structure_cp=0.01`, D4가 cp 지배를 31%로 낮춤) — 0.5 m tol이 ±1~2.5 m wavy를 못 끌어옴을 이미 확인. **cp는 다시점 절대-높이 앵커가 없다** = MVC가 메우는 정확한 공백.

### §0.2 다시점/영상·카메라 포즈 접근 (학습 중) — **모두 가능**

| 요건 | 상태 | 증거(file:line) |
|---|---|---|
| 다시점 포즈+영상 메모리 상주·프레임별 로드 | ✅ | `dataloader.py:113-133` `frames:List[Frame]`(K,R,t,image_path); `ds[j]`가 임의 이웃의 영상+w2c+K 로드 |
| 미분가능 렌더 깊이+법선(월드)+alpha | ✅ | `renderer.py:62-94` `render_mode="RGB+ED"` → `depth`(expected)·`normal_render`·`normal_surf`·`alpha`; **깊이/법선 경로 detach 없음** = 기하로 역전파 |
| 깊이→월드 언프로젝트 1차식 존재 | ✅ | `renderer.py:154-186` `_depth_to_normal`(픽셀→카메라 `x=(u-cx)/fx·z`→월드 `inv(w2c)`) |
| 손실 삽입점 + config-키 가중 패턴 | ✅ | `train.py:586-728` `loss_total += w_X·loss_X`; `_ramp_weight_scale`(L111-127) warmup/ramp 재사용 |
| 좌표계 일관성(언프로젝트→재투영 유효) | ✅ | COLMAP 포즈·GS 점군 = 동일 GS-local = EPSG:25832 − [690953,5336071,604] 순수 평행이동(scale 1); 렌더 깊이=GS-local 미터, NDC 정규화 없음 |
| 이웃/공가시성 선택 로직 | ⚠ **없음, 그러나 자명** | poses의 카메라중심 `C=−Rᵀt`·시선 `d=Rᵀ[0,0,1]`로 1회 사전계산(거리+각도). train_idx 한정(test=매 10번째) |

### §0.3 ⭐ 핵심 발견 — 이식 가능한 다시점 일관성 손실이 이미 repo에 있음

- `legacy/planarsplat_ref/loss_util.py:276` **`multi_view_consistency_loss()`** = 완결된 **ULSR-GS(Li et al., ISPRS 2025)식 기하 일관성 손실**. src 가 임포트 안 함(=비활성). 직접 정독 확인:
  - src 깊이 언프로젝트→월드→ref 카메라 재투영(L325-343) → **상대 깊이 일관성** `|z_exp−z_ren|/max(·)`(L365) + **occlusion 인라이어 필터**(상대오차<10%, L368) + **법선 abs-cosine 일관성**(L388, 0.5 가중).
  - 입력은 `c2w`(우리는 `w2c` → `inverse()` 한 번), 픽셀 재투영은 `.long()` 정수 gather(=NN) — **깊이 값**을 통한 gradient(기하 이동의 핵심)는 살아 있음(공간좌표 미분만 없음 = ULSR 원본 방식, B1 최소형에 충분).
- 동반 호출 청사진 `legacy/planarsplat_ref/trainer.py:595-624`: 무작위 ref 뷰 선택 → ref를 `no_grad`로 렌더 → 월드 법선 변환 → MVC 가중합(decay). **배선 패턴까지 그대로 있음.**
- 단일뷰 `l_nc`(`data_fitting.py:84`, render-법선 vs 깊이-법선)는 **이미 활성**인 자기지도 일관성 = MVC의 단일뷰 사촌(이식 시 패턴 일치). 2DGS distortion reg도 존재(`w_distort=0`, 과거 붕괴로 비활성).
- **함의**: 기하 코어 ~80%는 **신규 작성이 아니라 이식**. 신규 = 이웃 선택자 + 2번째 렌더 배선 + w2c/c2w 정합 + config 키 + (선택) 곡면 grid_sample.

### §0.4 평가 하네스 재사용성 — 준비됨(소폭 일반화 필요)

- `overseg_faithfulness.py` **`face_support()`**(L90-110) = GS 지붕면별 raw ALS 점-평면 **수직잔차 중앙값**(resid_abs)·**받침 k/m**(supported iff n_als≥5 AND resid_abs<0.5 m). **±1~2.5 m 어긋남 = 이 resid_abs**(정본 4906969: face13 2.25@520.9, face3 1.78@528 등) → **이게 B1 표적 지표, 라벨-프리**(raw ALS만; 모델·roofType·footprint 미입력 = 규칙 §4-9 준수).
- 정합: 전역 dz 1개를 **받침 최대화**로 favorable 탐색(±3 m). 단차-인지 GS 레벨수 `step_aware_levels`(0.5 m tol = cp/g2 미러).
- ALS 출처: `phases/p0-audit/runs/mob_eval/raw_lidar/DEBY_LOD2_<bid>_orig_classified.las`(class 6, EPSG:25832, ellipsoidal; 4906969=3336점). GS 면: Roofer Solid의 RoofSurface(`parse_solid_roof`, gssem read-out).
- **B1 arm이 거쳐야 할 체인**: `train(config) → ckpt/final.pt → tum_mob_tsdf_extract(P_class_clean npz) → _mob_prep_las_gssem + Roofer(tum_mob_eval --classifier gssem) → mob_eval/<arm>/{classified.las, roofer_*/*.city.jsonl}`. (run_d4.sh 그대로 복제)
- ⚠ **일반화 필요 2건**(공정 A/B 위해): ① arm 이름 `gs_d4_dense`·BLD 목록이 **하드코드** → `--arm/--bid` 플래그화 또는 문자열 교체. ② favorable dz가 arm마다 재탐색됨 → A/B서 **dz 프로토콜 고정/투명화**(아니면 k/m 델타가 dz-탐색 산물일 수 있음). ③ 0.5 m 이진 supported 외에 **resid_abs의 연속 개선(→0)**을 2차 성공기준으로(0.5 m tol은 ±1~2.5 m를 못 당기므로).

### §0.5 격리(isolation) 설계 — gs_d4 복사 + 키 1개

- `gs_d4_{dense,acmp}.yaml`은 **init seed·out_dir 2줄만 다름**, 나머지 손실/스케줄/densification 바이트 동일. → **B1 = `gs_b1_{dense,acmp}.yaml` 복사 후 out_dir 변경 + 키 1개(`w_mvc` + 스케줄) 추가**. 그 외 D4 값 고정(cp=0.01, na=0.08, depth=0.03, normal=0, photo=1.0, nc=0.05, sem=0.1, sem_detach_geometry=false, g2/voxel2.0/merge_d_tol0.5, structure_warmup=15000, max_iter=30000) → **델타는 MVC 항 단독 귀속**(태스크 "이 항만 격리" 충족).
- `run_d4.sh` → `run_b1.sh`(ARMS·eval 출력명만 교체). 2-GPU 병렬, ~4.4 h/arm-pair(D4 실측) **+ MVC 2번째 렌더로 증가 예상 ~5–7 h**. ⚠ train.py **resume 없음**(kill/정전=0부터) → `setsid nohup` detached + ckpt mtime 진척확인(D5 교훈).

---

## §1 추가 가능 형태 (Step 0 제안 1~2) — 판정=김휘영

> 태스크 자체가 "높이 = 다시점 **기하** 일관성; SF-Recon식 엣지-인지(광학·구조)는 B2"로 규정 → **Form 1(기하)이 B1 본령**. Form 2(광학)는 맥락상 B2.

### Form 1 (권장) — 기하 다시점 깊이+법선 일관성 (legacy ULSR-GS 이식)
- **기제**: 매 iter(warmup 후) 현재 뷰 idx의 covisible 이웃 j(포즈-NN, train_idx 한정) 선택 → j 렌더(2번째 render) → 현재 깊이 언프로젝트→월드→j 재투영 → **상대 깊이 불일치**(occlusion 인라이어<10%) + **법선 불일치** 벌점. 자기지도·라벨 없음.
- **장점**: ① 태스크의 "높이=기하" 정의에 정확히 부합. ② **무텍스처에 강함**(기하만 씀 — 복합지붕 무텍스처 데크가 Form 2의 약점인데 여기선 무관). ③ **~80% legacy 이식**(저위험). ④ 떠 있는 면이 다시점서 불일치 → 실 층으로 끌리는 **직접 동력**.
- **비용/위험**: 활성 iter당 +1 렌더(ref를 `no_grad` 한쪽-gradient로 = legacy 방식, 비용 절감). 이웃 선택이 빈약하면 무신호 → 가드 필요. depth = expected(검증된 미분가능) 기본, median(unbiased)은 후속.

### Form 2 (B2 영역, 참고) — 광학 평면유도 워프 (PGSR 정통)
- **기제**: 렌더 깊이+법선으로 픽셀 평면 정의 → 이웃 뷰로 호모그래피 워프 → 이웃 RGB를 현재로 워프 → NCC/SSIM 광학 일관성.
- **장단**: 실제 영상 텍스처를 교차증거로 = "영상이 구조를 학습"의 최강형. **단 무텍스처에 취약**(복합지붕 데크가 바로 그 실패모드) + grid_sample 신규 + 노출편차 교란. → 태스크 framing상 **B2**(엣지-인지 구조)로 미룸.

### §1.1 권장 B1 사양(초안, 승인 시 확정)
- 항 = **Form 1**. 2-arm(dense+acmp) = gs_d4 + MVC. **cp는 0.01 유지**(태스크 "다른 손실 고정" → MVC만 격리; cp 끄기/facet-merge=비지시).
- 이웃 = 포즈-NN(중심거리+시선각, k=1~2, train_idx). depth = expected. ref = no_grad(한쪽). warmup = structure와 정합(또는 약간 이르게 — depth 정착 후). 가중 `w_mvc` = 소(스윕 대상, 초기 보수적).
- 평가 = `overseg_faithfulness` arm 플래그화 + dz 고정 프로토콜 + resid_abs 연속지표 추가; 정본 4906969 + 복합 + 가드(4906972·42364663) 대비 현재(MVC 없는 gs_d4_dense).

---

## §2 B1 구현 (Form 1 기하, 승인=김휘영 2026-06-29) — 완료

> 가산적(additive) 변경만. 엔진 손실 균형·데이터는 D4 고정, **L_mvc 항 하나만 추가**. 커밋 `phaseB-b1-mvconsist`.

### §2.1 손실 — `src/stage2/loss/multiview.py` `l_multiview_consistency()`
- **이식원** `legacy/planarsplat_ref/loss_util.py:276`(ULSR-GS) → repo 규약으로 적응: ① **w2c-네이티브**(legacy는 c2w; 내부 `inverse()` 1회), ② **shape-robust**(src/ref 해상도 깊이텐서서 추론), ③ **dict 반환**(`total/depth/normal/n_inlier`, l_structure 규약).
- **기제**: src 렌더 깊이 언프로젝트→월드→ref 카메라 재투영 → **상대 깊이 일관성** `|z_exp−z_ren|/max(·)` + **occlusion 인라이어 필터**(상대오차<rel_thresh=0.1) → `loss_depth`; 동일 대응점서 **법선 abs-cosine 일관성** `1−|n_src·n_ref|`(w_normal=0.5) → `loss_normal`. `total = loss_depth + 0.5·loss_normal`.
- **gradient**(ref를 no_grad로 렌더, ref_detach=True): depth_ref/normal_ref=상수, gradient는 **depth_src(=렌더 깊이→means/scales/quats)·normal_src 통해 src-뷰 기하로 한쪽 흐름**. 무작위 (src,ref) 다수 누적 → 모든 뷰가 상호일관으로 끌림. 정수-픽셀 gather(NN, legacy식)지만 높이 교정 gradient는 **깊이 값**으로 흐름(픽셀좌표 미분 불요).

### §2.2 이웃 색인 — `train.py:_build_mvc_neighbors()`
- 포즈만으로 1회 사전계산: 카메라중심 `C=−Rᵀt`·시선 `d=Rᵀ[0,0,1]`. 이웃 = 시선각<`max_angle`(같은 면 관측) AND 베이스라인>`min_baseline`(시차 확보)인 train_idx 프레임 중 베이스라인 최근접 k개. 후보 없으면 최근접 k로 폴백. **test(매 10번째) 누출 차단**. silent-zero 가드(빈 색인이면 RuntimeError).

### §2.3 train.py 배선
- config 파싱(L536+): `w_mvc, mvc_warmup, mvc_schedule, mvc_ramp_steps, mvc_every, mvc_neighbor_k, mvc_max_angle_deg, mvc_min_baseline, mvc_w_normal, mvc_rel_thresh, mvc_ref_detach` 전부 `cfg.get(default)`, **기본 w_mvc=0 → 기존 config 바이트동일**.
- 루프(distort 직후): `it≥mvc_warmup AND it%mvc_every==0`이면 이웃 1개 random pick → `ds[j]` 로드 → ref 렌더(no_grad) → `l_multiview_consistency` → `loss_total += w_mvc·_ramp_weight_scale(...)·loss_mvc`. TB `loss/mvc{,_depth,_normal}`·`stats/mvc_n_inlier`.

### §2.4 config(격리) + 러너
- `gs_b1_{dense,acmp}.yaml` = `gs_d4_{dense,acmp}` + **MVC 블록 + out_dir만 변경**, 그 외 D4 바이트동일(**cp=0.01 유지**, na=0.08, depth=0.03, photo=1.0, nc=0.05, sem=0.1, g2/voxel2.0/merge_d_tol0.5, warmup15000, max_iter30000). MVC 하이퍼: `w_mvc=0.5`(loss_mvc~0.05·O(photo/cp)와 동급, 초기 보수적), `warmup=7000`(photo 5k·depth ramp 5k→10k 정착 후, densification stop 20k·structure 15k 창 포괄), `ramp 5000`(→12k 완전발화), `every=1, k=2, angle<40°, base>2m, w_normal=0.5, rel<0.1, ref_detach`.
- `run_b1.sh` = run_d4.sh 복제(ARMS=gs_b1_*; 2-GPU 병렬 dense@GPU1·acmp@GPU0 → TSDF extract → eval gssem+smrf). detached 실행(setsid nohup).

### §2.5 사전 검증(엔진 손대기 전, 6h 런 전) — PASS
- **구문**: py_compile clean(multiview.py·train.py·overseg_b1_faithfulness.py).
- **40-iter Docker 스모크**(전 손실경로+densification N-변경+sem 렌더+MVC 발화): 크래시 없음. **깊이 일관성 작동** — `loss/mvc_depth=0.047`, **n_inlier≈32만~40만**(warmup=8 전 0). ⚠ 초기-모델서 `loss/mvc_normal=0`(씨앗 quats=항등→법선 전부 ~[0,0,1] 미분화).
- **수렴 모델 직접 검증**(gs_d4_dense final.pt, src=468·ref=475 covisible쌍): **법선 항도 정상** — both=**739,631 대응점**, `loss_normal=0.0037`, `|cos|=0.996`. → 초기 0은 버그 아닌 모델 미성숙(실 런은 7000+서 발화=성숙). **함의: 높이 교정 동력=깊이 재투영 항(workhorse, ~74만 인라이어), 법선은 소규모 정규화**(수렴서 0.0018 기여)=설계의도 일치.
- 성능: MVC 활성 iter 추가 렌더(ref no_grad) **≈+0.2 s/it**(스모크 iter8-9 3.0→1.8 it/s) → 실 런 ~5–6 h/2arm(D4 4.4h 대비).

## §0″ ⚠ 검증으로 정정된 헤드라인 (적대 3렌즈, must-fix 반영)

> 1차 헤드라인("복합동 면을 실 층으로 강하게 끌어옴, resid̄ 42364659 4.58→0.95·val3dity F→T, PSNR −0.3")은 **적대 3렌즈 재검(step-collapse / provenance / regression)으로 대거 정정**. 본 §3~5는 정정본. 핵심 정정 4건(전부 직접 재확인):

1. **42364659 "4.8× 개선"의 대부분 = 메트릭 인공산물**(per-arm dz 재중심화). `fixed_dz = max(0, median(ALS)−median(GS))`가 **arm마다** 재계산 → D4 GS가 ALS보다 ~7m 위라 dz가 0으로 clamp되어 7m 벌점(resid 4.58), B1은 dz=2.62 적용(resid 0.95). **공유 dz(=0)서는 0.95→3.04로 소실**, strict 받침 k는 **양 arm 0/6→0/4**(둘 다 0개). → 면-당김 아님, 전역 재등록.
2. **PSNR −0.3 = 오류**(train-노이즈 readout). **Held-out `eval/psnr`: B1 +0.11(회귀 없음)** — dense 18.21→18.32·acmp 18.28→18.39. **단 누락했던 실 비용 = `eval/depth_mae` 회귀** dense 2.03→2.12(+4.6%)·acmp 2.02→2.08(+3.4%).
3. **val3dity F→T = arm 혼동**. **dense arm**: 42364659 **T→F(악화)**·4907510 F→F(미수정). F→T는 **acmp arm**(5→7)만. dense/acmp 절대 혼용 금지.
4. **"복합/단차" 라벨 오류** — 42364659는 ALS 모드 0.75m 간격=**사실상 단일레벨**, 4907510도 단일(518.2). 끌 "단차"가 거의 없음 → "단차 보존" 프레이밍 부적절. (단 4906969은 진짜 3레벨: 523.5/526.5/530.3, 단 530.3은 D4·B1 공통 ~528 readout 절단으로 미도달.)

## §3 정량 (정정본; dense arm, gssem read-out, raw ALS, EPSG:25832)

> ⚠ **메트릭 갱신(2026-06-30, [[W_complexity_survey]] Part 1)**: 아래 표의 per-arm dz(+공유=D4 dz)는 **dz-강건 clamp-free best-fit / joint-shared-dz로 대체**됨(`complexity_metric.py`). 갱신본: 42364659 "4.8×"는 **clamp 거품**(공정 best-fit 2.65→0.95 ≈ 2.8×, B1 실개선 잔존)·4907510 개선 유지·**정본 4906969는 1차 "판정불가"였으나 dz-강건서 B1 소폭 우위**(1.60→1.52). **B1 핵심 = 평균회귀**(고-결함 동 개선·저-결함 동 소폭 악화, corr(d4_resid, B1−D4)=−0.82). 즉 1차 "거의 인공산물" 결론은 **부분 정정**(고-결함서 실재). 비용(depth_mae·plane_rms)은 불변.

**면별 수직거리 resid̄(median|ALS−면평면|) — own-dz vs 공유-dz(=D4 dz, 재중심화 제거):**

| 동 | 역할 | D4 resid̄ | B1 resid̄(own) | **B1 resid̄(공유)** | B1 <1.0(공유) | 견고성 |
|---|---|---:|---:|---:|---:|---|
| 4906969 | 정본(3레벨) | 1.88 | 1.93 | **1.53** | 0.50 | ⚠ **dz-민감**(dz=0서는 D4 1.68<B1 1.93 역전; 판정불가) |
| 42364659 | (단일레벨) | 4.58 | 0.95 | **3.04** | 0.0 | ✗ own-dz 이득 **공유서 소실**(인공산물); 받침 0/4 |
| **4907510** | (단일레벨) | 2.88 | 1.79 | **1.77** | 0.50 | ✓ **유일 견고 개선**(own·공유 모두 B1<D4) |
| 4906972 | 대조 박공 | 0.30 | 0.58 | **0.59** | 0.8 | ✗ **악화**(새 떠있는 면 3개, resid 0.84/1.14/1.91) |
| 42364663 | 대조 ridge | 0.94 | 0.16 | **0.16** | 1.0 | ✓ 개선 |

→ **공유-dz 기준 견고한 결과는 4907510(개선)·42364663(개선)·4906972(악화) 3건뿐**; 정본 4906969는 dz 선택에 따라 순위가 뒤집혀 **판정 불가**; 42364659의 화려한 이득은 인공산물.

**위상·표면 (per-arm 명시):** dense val3dity 42364659 T→**F**·4907510 F→F·전체 11동 3→4; **acmp** 5→**7**(여기가 개선). **plane_rms(전체 11동 평균): dense 0.83→1.06(+27% 악화, 최악 회귀=정본 4906969 1.71→2.02)**, acmp 0.90→0.82(−9% 개선). 생성(roofer_ok&면>0): dense 10→9, acmp 10→10. roof_density −6~7%(양 arm).

**품질 (held-out, TB 30k):** eval/psnr **+0.11(무회귀)**; **eval/depth_mae +3.4~4.6%(회귀)**; train psnr는 20.08→16.03 급락(단일배치 노이즈, held-out과 불일치). **lever 약함**: loss/mvc last-500 평균 ~0.0085(≪ total ~0.36)·n_inlier ~1.03M/3.2M(32%) — w_mvc=0.5는 **과강 아닌 약한 레버**.

## §4 정성 (`docs/figs/W_phaseB/<bid>.png` = [D4 | B1 | raw ALS] 높이색)
- **42364659**: D4 6면 높이 난잡(녹색 고스파이크) → B1 4면 거의 단색(균일). **단 ALS가 단일레벨**이라 "균일화=정답 근접"은 dz-재중심화 착시(§3). z-span 13.3→13.7m(축소 안 됨=붕괴 아님).
- **4906969**(반원 단차평): D4 14면 파편 → B1 10면 더 큰 응집 면(과분할↓·허위 510.8[−12.6m]면 제거). 단 resid̄·plane_rms는 보합~악화.
- **4906972**(박공 대조): B1 3→10면 **과분할**(레벨 3 보존이나 새 떠있는 면 도입).
- **4907510**: B1 면 높이가 ALS에 상대적으로 근접(유일 견고 개선의 정성 근거).

## §5 종합 (판정 금지 — 관찰·진단·권고만; 판정=김휘영)

**관찰**: B1(자기지도 다시점 기하 일관성, w_mvc=0.5)은 **설정대로는 "떠있는 면을 실 층 높이로 끌어온다"는 B1 목표를 명확히 달성하지 못함**.
- ① **높이↑**: 견고한 개선은 **4907510·42364663 2건**뿐; **정본 4906969는 메트릭이 dz에 민감해 판정 불가**(plane_rms로는 오히려 악화); 42364659의 큰 이득은 인공산물. ② **단차 보존**: 붕괴는 없으나 대상이 사실상 단일레벨이라 검증 부적합. ③ **대조 무파괴**: 42364663 OK이나 **4906972 박공 악화**(과분할+새 떠있는 면). ④ **순비용**: dense plane_rms +27%·depth_mae +3~5%·생성 −1(held-out PSNR은 보존). **arm-의존**(dense 악화 / acmp val3dity +2·plane_rms 소폭 개선).

**진단(왜 안 됐나)**: (a) **레버 약함** — w_mvc=0.5서 loss_mvc가 total의 ~2%, 떠있는 면은 소수 픽셀이라 평균 깊이-일관성에 희석. (b) **메트릭 결함** — per-arm dz+clamp가 전역 재등록을 면-당김으로 오인(must-fix); 공유-dz 통제 필수. (c) **표적 부적합** — "복합/단차" 4동이 실은 단일레벨, 진짜 다층 단차 동이 표본에 없음. (d) **읽기-절단** — 530.3 등 상위 레벨이 TSDF/Roofer ~528서 공통 절단(B1 무관).

**권고(판정=김휘영)**: 곧장 B2 이행은 비권고. 다음 후보 — ① **메트릭 고정**(공유-dz·clamp 제거·면-내 ALS 단일레벨 게이트) 후 재해석; ② **w_mvc 상향 스윕**(0.5→1~3) 또는 늦게-강하게, depth_mae 가드와 함께; ③ **진짜 다층 단차 동**으로 표적 교체; ④ depth_mae·dense plane_rms 회귀가 자기지도 다시점 항의 실 비용인지 더 진단. B1은 **부분 신호(4907510)**는 보였으나 **순효과는 미명확~약음(dense 회귀)**.

**검증**: 적대 3렌즈(step-collapse / provenance / regression) workflow, 핵심 4정정 직접 재확인(held-out psnr·depth_mae·dense val3dity·shared-dz). provenance 렌즈=비교 자체는 공정·재현(gssem requal·deterministic) 확인; step-collapse·regression=부분지지(인공산물·arm혼동·숨은 비용 적발).
