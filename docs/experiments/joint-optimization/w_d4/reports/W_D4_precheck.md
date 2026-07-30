# W_D4 — D4 사전점검 (법선 타깃 품질·변동계수 가중 실현성·손실 통계)

> 읽기 전용·관찰만·판정 없음(판정=사람). feature/p2-prior-full. 그림 `docs/figs/W_D_qual/`. 본보고 [[W_D_loss_audit]]·[[W_D_prior_full]].

## 점검 1 — 법선 타깃이 쓸 만한가

### (가) 법선 지도 출처·생성·해상도
- **출처 = MVS PatchMatch(비-구조)**. `data_geoidfix/stereo` → (상대심링크) `phases/p0-audit/data/work/mvs/colmap_dense/stereo`; `normal_maps/*.geometric.bin`는 **COLMAP `patch_match_stereo`** 산출([prior_full_stereo.sh:48-55](scripts/input_and_alignment/p2_gsjso/prior_full_stereo.sh#L48), `--PatchMatchStereo.geom_consistency true --max_image_size 1024`). **구조(G2 평면) 유래 아님** — 구조 법선은 L_structure로만 흐름([[W_D_loss_audit]] §1).
- **해상도 = 1024px**(stereo max_image_size). dataloader가 이미지 dim으로 업샘플([dataloader.py:205](src/stage2/dataloader.py#L205)).
- 로드·프레임: `_find_normal`([dataloader.py:148-157](src/stage2/dataloader.py#L148)) → `_load_normal` 카메라→월드 `n_world = n_cam @ R_c2w.T`, mask=‖n‖>1e-3([dataloader.py:203-212](src/stage2/dataloader.py#L203)). 렌더 법선도 월드프레임([renderer.py:9,77](src/stage2/renderer.py#L9)) → 비교 동일 프레임.

### (나) 그림 (3뷰) — `docs/figs/W_D_qual/d4_normals.png`
[GT MVS 법선 | GS 렌더 법선], RGB=법선방향. **관찰**:
- **GT MVS 법선 = 노이즈·블록·결손**: 큰 단색 양자화 패치 + 검은 무효 구멍 + salt-and-pepper. **유효 커버리지 33–90%**(3번째 뷰 33%만 유효). 매끈한 표면 법선이 아니라 거칠고 구멍 많음.
- **GS 렌더 법선 = 매끈·정합**: 지붕/벽 방향을 부드러운 그라디언트로 해상.
- 둘은 시각적으로 잘 안 맞고, **GT가 더 노이즈한 쪽**. → 매끈한 렌더를 노이즈·구멍 타깃에 맞추라는 감독이라 [[W_D_followup_audit]] §3의 L_normal 평탄(미발화)과 정합(노이즈 타깃엔 수렴 안 함이 정상).

### (다) 판정 재료 (판정=사람)
- GT 법선 지도가 **노이즈·결손**(33–90% 유효) → "**정답 지도가 노이즈면 법선 감독은 빼고 평면화(cp+na)에 기댄다**" 쪽 근거. 단 (라) 참조 — 평면화도 곡면엔 약점.

### (라) 외부 법선 노이즈 대비 — 4906969 G2 그룹 적합
`gs_prior_full_dense/ckpt/final.pt` 내보낸 `stage2_group_ids/rep_normals/rep_d`, 4906969 footprint 클립:
- 클립 프리미티브 26,968 (그룹된 25,851), **G2 그룹 28개 (ref 면 3개)** — 곡면을 다수 그룹으로.
- 그룹 크기: mean 923 · median 70 · max **15,008**. 평면적합 RMS: 크기≥30 그룹 22개 중 median **0.28 m**, max **4.13 m**(>1 m 2개).
- **최대 2그룹이 곡면을 뭉침**: gid1828 **15,008점 RMS 4.13 m**, gid653 **7,161점 RMS 1.70 m** — 곡면 지붕(또는 두 면)을 **한 평면에 4 m 잔차로 병합**. 나머지 소형 그룹은 평탄(median 0.28 m).
- **관찰**: 평면화는 작은 평면면엔 잘 맞지만 **큰 곡면을 4 m 잔차 덩어리로 과병합** → cp(=mean 제곱거리, 씬 18 m²=RMS~4.2 m, [[W_D_loss_audit]])가 이 큰 그룹에 지배됨. 곡면 건물에선 평면화도 **과-평탄화 위험**(법선 노이즈 대체재로 평면화에만 기대면 곡면 손실).

## 점검 2 — 엔진이 변동계수(CV) 가중을 할 수 있나

### (가) 기존 적응 가중 인프라 = 없음
running-stat / EMA / 학습형 log-σ(Kendall) / GradNorm **전무**(train.py·loss/*.py). 비상수 가중은 `_ramp_weight_scale`(고정 일정, 데이터 무관, [train.py:111-127](src/stage2/train.py#L111))뿐; grad-norm은 **진단 전용**(TB 기록, loss_total에 미환류, [train.py:730-744](src/stage2/train.py#L730)). 실가중은 전부 config 상수([train.py:437-461](src/stage2/train.py#L437)).

### (나) 신규 추가 범위 — 가능, ~20–35줄
- 조립 지점([train.py:728](src/stage2/train.py#L728)) ↔ backward([train.py:746-749](src/stage2/train.py#L746)) 사이 삽입. 각 항 raw는 그 자리서 `.item()` 접근 가능: `loss_photo`(585)·`loss_depth`(591)·`loss_n`(600)·`loss_nc`(606)·`loss_sem`(617)·`loss_str_total`(723; na/cp는 detach됨 724/725)·`loss_mut_total`(677).
- 구성: EMA stats dict 갱신(~8줄) + `w_cv = mean/(std+eps)` 또는 `term/mean`(~10줄) + live 텐서로 loss_total 재조립(~10줄).
- **함정 4 + 처리**: (a) warm-up 중 0(depth/normal 램프전·struct 게이트전) → EMA 오염·CV 폭발 → **활성일 때만 EMA 갱신**(post-ramp raw 추적). (b) mean≈0 항(str_na mean 0.003 → 1/mean 287 폭발) → **분모 floor + clamp**. (c) **detach된 스칼라로 stats**(.item() 자동 detach)·ramp와 곱셈 합성(이중 스케줄 금지). (d) MUST-EQ: **기본 off 플래그**(`cv_autoweight=false`)·항<2면 단락 → no-prior arm 무변경.

### (다) 안 갈 때 고정 정규화 (대안)
계량 단위 항만 비차원화: **L_depth ÷ s (미터)·L_coplanar ÷ s² (미터²)**, 나머지는 이미 O(0.1–1) 무차원. 길이 s = `structure_voxel_size` 2.0 m → depth/2≈1.6·cp/4≈4.5로 O(1) 정합. running-stat 불필요([[W_D_loss_audit]] §6).

## 점검 3 — weight 설계용 손실 통계 (D 런 TB)

raw 값(비가중) 구간 평균/표준편차/변동계수. mean·std = step 20k–30k(정상상태), mean[5–15k] = 램프 후 초기.

| 항 | mean[20-30k] | std | **CV=std/mean** | mean[5-15k] | 1/CV(상대) | 1/mean(고정정규) |
|---|---|---|---|---|---|---|
| photo | 0.176 | 0.029 | 0.16 | 0.225 | 6.17 | 5.68 |
| **depth** | 3.174 | 5.519 | **1.74** ←최대 | 5.189 | 0.58 | 0.315 |
| normal | 0.322 | 0.086 | 0.27 | 0.365 | 3.74 | 3.10 |
| nc | 0.244 | 0.089 | 0.36 | 0.274 | 2.74 | 4.10 |
| sem | ~1.1(별도) | — | — | — | — | ~0.9 |
| **struct(cp)** | 18.01 | 2.06 | **0.11** ←최소 | 0.028 | 8.73 | 0.056 |
| str_na | 0.003 | 0.001 | 0.19 | ~0 | 5.19 | 287(폭발) |

**예측(판정=사람)**:
- **CV 가중(1/CV)은 magnitude 불균형을 못 고친다**: depth(CV 1.74)는 낮게(1/CV 0.58), **struct(CV 0.11)는 가장 높게(8.73)** 줘 — 이미 지배적인 구조를 더 키움. CV는 분산만 보고 스케일은 못 봄.
- **magnitude 균형은 mean-정규(1/mean) 또는 길이스케일**: depth ×0.315·struct ×0.056. 단 str_na(mean≈0)는 1/mean 287로 폭발 → floor 필수.
- **깊이를 얼마나 낮추나**: depth raw mean 3.17·**CV 1.74(std>mean, 뷰별 극변동)** = **타깃 신뢰 낮음**(점검1 법선 노이즈와 동일 결). 현 w_depth 0.1→가중 0.32(≈2×photo). photo 수준 정합은 ×0.056(=w_depth~0.006), O(1) 정합은 ×0.315(=w_depth~0.03). 높은 CV가 추가 하향 근거.

## 종합 (한 줄, 판정 없음)
법선 타깃(MVS PatchMatch 1024px)은 **노이즈·33–90% 결손**(렌더는 매끈) → 법선 감독 약함의 근거이나 **평면화 대체도 곡면(4906969 15k점 그룹 4.13 m 잔차) 과병합 약점**; CV 자동가중은 **인프라 없음·~20–35줄 신규 가능**(4함정 처리)이나 **scale 불균형은 mean/길이스케일 정규가 정답**(depth CV 1.74로 최하 신뢰, struct CV 0.11로 안정하나 magnitude는 1/mean·÷s² 필요).
