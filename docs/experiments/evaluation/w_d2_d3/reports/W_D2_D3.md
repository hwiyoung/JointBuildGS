# W_D2·D3 — 조립 귀속(분류 vs 학습)·품질 귀속(GS점 vs Roofer)

> 읽기 전용·관찰만·판정 없음. feature/p2-prior-full. 데이터(`results/`·`runs/`) gitignore.
> D2 = 재학습 없는 재추출(v6 ckpt + D 분류). 본보고 [[W_D_prior_full]]·[[W_D_followup_audit]].

## D2 — 조립을 살린 게 '분류'냐 '기하 학습'이냐

v6 ckpt(`gs_seed_{dense,acmp}_protect`, 깊이·법선·평면화 학습 **없음**)에 **D의 새 분류(gssem)만** 입혀 재추출(GPU, 의미 voxel-히스토그램)+Roofer+val3dity. 조립안됨 8동(REC):

| arm | 학습 | 분류 | **assembled/8** | valid-solid/8 |
|---|:---:|:---:|:---:|:---:|
| **D_gssem (dense)** | ✓ | gssem | **7** | 4 |
| D_gssem (acmp) | ✓ | gssem | **7** | 3 |
| **v6+gssem (dense)** | ✗ | gssem | **3** | 2 |
| **v6+gssem (acmp)** | ✗ | gssem | **5** | 0 |
| D_smrf (dense) | ✓ | smrf | 3 | 2 |
| v6 원본 (dense) | ✗ | smrf | 2 | 2 |
| v6 원본 (acmp) | ✗ | smrf | 2 | 2 |
| LiDAR | — | — | 7 | 7 |

REC 순서: 42364609·42364659·42364663·4907182·4907510·4908050·4908166·4908176.

### 관찰 — 초가산적 시너지 (앞선 보고 정정)
- **분류 단독(v6+gssem) = 3–5/8 < D 7/8**: 분류만으론 D에 **한참 못 미침** → 사용자 가설 (나) "학습이 키운 점 밀도도 조립에 필요했다" **확증**.
- **학습 단독(D_smrf) = 2–3/8 ≈ v6**: 학습만(SMRF read-out)으론 거의 안 살림(SMRF가 지붕을 먹음).
- **둘 다(D_gssem) = 7/8**: 가산 예측(2 + 학습기여 ~1 + 분류기여 ~1–3 = 4–5)을 **초과(7)** → **초가산적(super-additive) 시너지**. 분류는 학습이 키운 조밀·정합 점군 위에서만 7/8로 작동하고, 학습은 분류가 SMRF처럼 지붕을 먹지 않을 때만 조립으로 이어짐.
- **정정**: [[W_D_prior_full]] §2의 "회복=read-out 단독, 학습-prior 무효"는 **과단순화**였다. D-smrf≈v6는 "SMRF 하 학습 무효"만 말하고, v6+gssem(3–5/8)이 분류 단독 한계를 드러낸다. 정확히는 **분류+학습 둘 다 필요(시너지)**. 단 valid-solid는 D 3–4/8로 LiDAR 7/8 여전히 미달(위상 과제는 불변).
- 비고: v6+gssem **acmp는 5 조립이나 valid-solid 0** — 분류만 입힌 acmp는 조립되나 전부 무효 solid(위상). 학습이 유효 solid에도 기여.
- 재현: `tsdf_v6sem_gs_seed_{dense,acmp}_protect.npz`(재추출), `eval_v6sem_gssem.json`. 추출 `tum_mob_tsdf_extract.py`(의미 기본 ON), eval `--classifier gssem`.

## D3 — 품질이 'GS 점' 탓이냐 'Roofer' 탓이냐

### (가) Roofer 파라미터 — 전부 default, 위상수리 옵션 없음
Roofer = **3dgi/roofer 1.0.0**(digest `dd2c415a…`, [docker-compose.p0.yml:29](phases/p0-audit/env/docker-compose.p0.yml#L29)). exp-D 호출은 **plumbing 플래그만**(`--id-attribute building_id --box`), 재구성 알고리즘 파라미터는 **전부 기본값** ([tum_mob_eval.py:138-140](scripts/input_and_alignment/p2_gsjso/tum_mob_eval.py#L138)).

| 파라미터 | 제어 | exp-D 값 | 관련 오류 |
|---|---|---|---|
| `--plane-detect-epsilon` | inlier→평면 거리(m); **높이면 과분할↓** | **기본 0.3** | 303·과분할·306/405 |
| `--plane-detect-min-points` | 평면 채택 최소 점수 | **기본 15** | 303·과분할 |
| `--plane-detect-k` | region-growing kNN | 기본 15 | 303·과분할 |
| `--complexity-factor` | 충실도↔단순성(0–1, 높을수록 상세) | **기본 0.888** | 303·306/405·과분할 |
| `--lod13-step-height` | 높이차<값 지붕부 병합 (**LoD1.3 전용**) | 기본 3 | 과분할 병합(단 LoD2.2엔 무효) |
| `--clip-terrain` | ground점서 footprint 클립("불규칙 외곽 유발") | 기본 true | 302·306 |
| `--simplify` | footprint 근접정점 dedupe | 기본 true | 303/306 |
| `--cj-scale` | 출력 정점 양자화(0.001) | 기본 | 302(근접정점 용접) |

**watertight/snap/heal/repair 플래그는 help-all 전체에 없음** — Roofer 자체 위상수리 옵션 부재. P0 선례([13_roofer_tune_w2a.py:32-87,204](phases/p0-audit/scripts/13_roofer_tune_w2a.py#L32))서 epsilon·min-points·complexity 스윕이 **val3dity 유효수를 움직임(ALS 8→5, DIM 11→9)** = 이 파라미터가 shell 위상을 실제로 바꿈([phases/p0-audit/docs/W2_3a_roofer_tuning.md:13-14](../../../../phases/p0-audit/docs/W2_3a_roofer_tuning.md)).

**오류별 판정**(무효 4동):
- **302 비폐합(4907182)**: 워터타이트 옵션 無 → **별도 위상수리 필요**(약한 레버 `--no-clip-terrain`만).
- **306·405 방향(4907510·4908176)**: 면/shell winding은 출력 메쉬 속성, 방향 플래그 無 → **방향수리 필요**(파라미터로 표적 불가; 평면검출 튜닝은 발생빈도만 바꿈).
- **303 비-다양체(4906969, 19면)**: **부분적 파라미터 가능** — epsilon↑·min-points↑·complexity↓ → 평면수↓ → junction↓. 잔여는 수리 필요.

### (나) 4906969 점별 라벨 — 라벨 응집, 곡면이 과분할 원인
`docs/figs/W_D_qual/4906969_labels.png` (P_class_clean, 537,741점: **Roof 289,698 + Wall 248,043**, Terrain/BG 0):
- **라벨은 큰 덩어리로 응집**(중앙 red 지붕 + 주변 green 벽), **salt-and-pepper 아님** → 19면은 **라벨 경계 잡음 탓이 아님**.
- 높이맵(우)이 **곡면 지붕** 확인(앞 [[W_D_prior_full]] figs와 정합). → 19면 = Roofer 평면검출(epsilon 0.3)이 **곡면을 다수 평면으로 분할**한 결과. gssem이 Roof·Wall 모두 building=6로 넣어(벽 46%) 곡면+벽 union 표면을 평면검출이 더 쪼갬.
- 즉 과분할 원인 = **(GS 곡면 기하 + Roofer 평면검출 임계 default)** 결합이지 라벨 얼룩 아님 → D3(가)의 "epsilon↑/complexity↓로 병합" 방향과 일치.

## 종합 (한 줄, 판정 없음)
조립 회복은 **분류·학습의 초가산적 시너지**(분류만 3–5/8·학습만 2–3/8·둘다 7/8; 앞 보고의 "read-out 단독"은 정정); 무효 4동은 **Roofer 위상**(302/306/405 수리 필요·303 평면검출 튜닝 부분가능, 위상수리 옵션 부재); 4906969 19면은 **곡면을 default epsilon이 분할**한 것(라벨 잡음 아님).
