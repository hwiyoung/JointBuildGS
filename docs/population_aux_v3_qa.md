# population_aux v3 — 모집단 원재료 v3 (관측기하 통일 재계산·QA) (읽기·신규계산·판정 금지)

> **박사연구 GS-JSO · 모집단 원재료 v3.** 브랜치 `feat/p2-structure-learn`. 지오 CRS EPSG:25832(footprint/GML),
> OPF/COLMAP 프레임 EPSG:32632(서브미터 오프셋, 관측기하엔 무시 — P0 T9와 동일). Docker(`--user`).
> **신규 계산 있음·재구성/재학습 없음.** 관찰만, **서브클래스 라벨 안 만듦(규칙=김휘영)**. 커밋 `population-aux-v3`.
> 재현 `phases/p2-gsjso/scripts/population_aux_v3.py`(dev 컨테이너, cv2). QA 스크립트 `population_aux_v3_qa.py`(tools:t0).
> 산출 `docs/population_aux_v3.csv`(199행, `building_id`=DEBY_LOD2_xx 조인) · 본 문서 · `docs/population_aux_v3_versions.txt`.

## 0. 동기 — v2가 아니라 v3인 이유

v2(`population_aux.csv`, [[population_verify]])는 **기존 P0-audit 산출을 재사용**해 병합한 것이라
축·부분집합마다 정의·소스가 섞이고 치명적 결측이 있었다:
- `roof_lowtex_frac` = **생성축(64동)에서 0/64** (T11 survivor 71동만 텍스처 보유).
- `n_views_total` = **79/199만**(T7 view_count), `median_intersection_deg`(뷰-쌍 교차각) = **0/199**(기존 산출 미존재).
- 뷰 카운트 소스가 T7/T11/W4c로 혼재(정의 상이).

**v3 = 199동 전체를 단일 정의·단일 스크립트로 재계산**한다(P0 T9 재투영 수학 + LoD2 GML 3D 지붕면 재사용,
신규 계산). v2는 폐기하지 않고 **겹치는 컬럼의 QA 교차검증**(§4)에 쓴다. **모든 컬럼 199/199 완비**(§3).

## 1. 조작적 정의 (per building, 199)

지붕 = LoD2 GML `RoofSurface` 3D 링(참조). 각 건물의 지붕면을 **팬 삼각분할 후 ~1 pt/m²로 균일 표본**
(건물당 상한 `SAMPLE_CAP=400`). 표본별로 등록영상(937 COLMAP FULL_OPENCV 포즈)에 **재투영**(정면·프레임 내)해
근사 가시뷰를 구한다(폐색은 근사 — [4] 별도 컬럼, self/이웃 폐색은 엄밀 미모델, 인프레임 기준).

**[1] 관측기하**

| 컬럼 | 정의 |
|---|---|
| `n_samples` | 지붕 표본 수(≤400) |
| `n_views_nadir` | 표본당 평균 가시뷰 중 **천정각(뷰↔수직) ≤20°** 뷰 수 (`NADIR_MAX_DEG`, 프로젝트 관례로 기록) |
| `n_views_oblique` | 표본당 평균 가시뷰 중 천정각 >20° 뷰 수 |
| `n_views_total` | 표본당 평균 가시뷰 수 (인프레임 재투영 기준) |
| `median_pair_angle_deg` | 가시뷰 **쌍 시차각**(표본→뷰 광선 사이각)의 중앙값 |
| `frac_pairs_10_60deg` | 뷰-쌍 중 시차각 **10–60°**(Schönberger view-selection band) 비율 |
| `median_incidence_deg` | **입사각**(뷰↔지붕법선)의 중앙값 — **모든 (표본,가시뷰) 쌍에 대한** 중앙값 |
| `frac_views_incidence_le60` | 입사각 **≤60°**(Soudarissanane) 뷰 비율 |
| `roof_obs_covered_frac` | 표본 중 **(가시뷰 ≥2 ∧ 시차각 10–60° 쌍 존재)** 비율 |

**[2] 재구성가능성 (Smith et al. 2018 아이디어; 채택 가중형태 아래·§2 명시)** — 표본별
`R = Σ_(가시뷰 쌍) w_parallax(α)·w_incidence(θ)·w_distance(d)`; 건물값 = 중앙값·p10.
- `recon_score_median`, `recon_score_p10`. 쌍은 표본당 **입사각 최소 24뷰**(`MAXV_PAIR`)로 상한(Smith 이웃 개념).

**[3] 지붕 텍스처 (199, 천정각 최소 뷰 우선·없으면 입사각 최소 뷰)** — 선정 뷰에서 지붕 **폴리곤 마스크** 픽셀만.

| 컬럼 | 정의 |
|---|---|
| `roof_lowtex_frac` | 정규화 그레이[0,1] Sobel 그래디언트 `< 0.02`(`LOWTEX_GRAD`, T11 sharp 저텍스처 정의) 픽셀 비율 |
| `roof_grad_p10` | 지붕 픽셀 그래디언트의 10퍼센타일(저디테일 지표) |
| `roof_sat_frac` | 밝기 `> 0.97`(`SAT_THRESH`) 포화 픽셀 비율 = **정반사(specular) 프록시** |
| `roof_periodicity` | 마스크 자기상관에서 **중앙 주엽(반경 ~min(h,w)/8) 제외 후 최대 피크** = **반복패턴 프록시** |

**[4] 폐색 근사 (199)** — `occlusion_frac_approx` = 건물 30m 내 이웃 건물 중 **지붕 최고점+2m보다 높은**
이웃 비율(T7 시선차단 논리 확장; 식생은 미포함 — caveat §5). 값 0 = 고립/저층 이웃.

## 2. 채택 파라미터 (versions.txt·QA 병기)

| 항목 | 값 | 근거 |
|---|---|---|
| 표본 밀도 / 상한 | 1 pt/m² / 400 | 균일 지붕 표본 |
| 천정각 near-nadir | ≤20° | 프로젝트 관례 |
| 입사각 허용 | ≤60° | Soudarissanane et al. |
| 시차각 밴드 | 10–60° | Schönberger view-selection |
| 쌍 상한 `MAXV_PAIR` | 24 (입사각 최소순) | Smith 이웃 근사 |
| `w_parallax(α)` | `exp(-(α-20)²/(2·20²))` — 20° 중심 가우시안 | Smith: 중간 시차 선호(소각=베이스라인 부족·대각=매칭 저하) |
| `w_incidence(θ)` | `max(0, cos θ)` (쌍 평균 입사각) | 법선 정면 선호 |
| `w_distance(d)` | 20–120m 평탄, 밖은 선형 감쇠 (쌍 평균 거리) | 명목 GSD 대역 |
| 저텍스처 임계 `LOWTEX_GRAD` | 0.02 (정규화[0,1]) | T11 sharp 정의 |
| 포화 임계 `SAT_THRESH` | 0.97 | 밝기 포화(정반사) |

> ⚠ Smith 2018 원식은 표면점 확률·해상도 항을 포함하나, 여기선 **채택 근사형태**(위 가중곱의 뷰-쌍 합)를 쓴다.
> 값이 아니라 **상대 순위**가 원재료로서 목적이며, 절대 스케일은 파라미터 의존(판정=김휘영).

## 3. 컬럼 커버리지 — **전 16컬럼 199/199** (v2 결측 전부 해소)

| 컬럼군 | v2 비결측 | **v3 비결측** |
|---|---:|---:|
| footprint(area/verts) | 199 | **199** |
| 뷰 카운트(nadir/oblique/total) | 79~125 | **199** |
| 시차각(median_pair/frac_10_60) | **0** | **199** |
| 입사각(median/frac_le60) | 87 | **199** |
| 커버리지(roof_obs_covered) | 79(근사) | **199** |
| 재구성가능성(recon median/p10) | — | **199** |
| 텍스처(lowtex/grad/sat/period) | 70~86(생성축 0) | **199** |
| 폐색(occlusion) | 79 | **199** |

**분포(199) 요약**: n_views_total 115–415(중 234; 고중첩 항공), median_pair_angle 5–37°(중 20°=Schönberger 이상대),
frac_pairs_10_60 0.16–0.88(중 0.73), roof_obs_covered 0.80–1.0(전동 잘 덮임), median_incidence 46–81°(중 63°,
전-뷰 중앙값이라 오블리크 편중), frac_views_incidence_le60 0.002–0.99(중 0.40=식별력 큼), lowtex 0.001–0.74(중 0.05),
grad_p10 0–0.25, sat 0–0.79, periodicity 0.06–0.90(중 0.43). **nan/inf 0셀.**

**진짜 0(결측 아님) 주의**: `n_views_nadir=0` **69동**(오블리크 편중 항공서 천정각≤20° 뷰 없음 — 단 텍스처는
입사각-최소 뷰서 산출되어 199/199), `roof_sat_frac=0` 100동(정반사 없음), `occlusion=0` 100동(고립), `recon_p10=0` 11동·
`recon_median=0` 2동(초소형/슬리버 지붕, 가시뷰<2 표본).

## 4. [6] QA 교차검증 — v3(통일) vs v2(재사용 부분집합)

겹치는 컬럼을 **둘 다 비결측인 건물**에서 비교(Pearson r·Spearman ρ·중앙편차 v3−v2·최대 불일치 5).

| 비교(v3↔v2 소스) | n | Pearson r | Spearman ρ | 중앙편차(v3−v2) | 평균 v3 / v2 | 해석 |
|---|---:|---:|---:|---:|---:|---|
| views_total ↔ T7 view_count | 79 | **0.964** | 0.967 | −18.7 | 267 / 290 | **강일치**(투영 검증); v3가 약간↓(=지붕표본 한정 vs 풋프린트) |
| views_nadir ↔ T11/W4c near_nadir | 125 | **0.838** | 0.853 | +0.0 | 9.0 / 10.7 | 순위 일치; 꼬리 불일치=**정의차**(v3 천정각≤20° vs v2 near-nadir 정의) |
| views_oblique ↔ T11/W4c oblique | 125 | **0.972** | 0.971 | −16.9 | 231 / 250 | **강일치**; v3 약간↓ |
| incidence ↔ T7/T11/W4c median | 87 | 0.060 | **0.509** | +0.5 | 61.3 / 56.6 | **정의차 큼**: v3=전-가시뷰 입사각 중앙값(~60°) vs v2=선정(near-nadir)뷰 단일값(~15°). 선형 무상관·순위 중간 |
| lowtex ↔ T11 sharp_low_texture | 70 | 0.580 | **0.653** | −0.534 | 0.055 / 0.568 | **순위 일치**(어느 지붕이 저텍스처인지 동의); 절대값은 임계/방법차로 v3 ~10×↓ |
| grad_p10 ↔ T9/T11/W4c gradient | 86 | 0.048 | 0.323 | +0.025 | 0.036 / 0.008 | 약한 순위 일치; v3=지붕마스크 Sobel([0,1]), v2=상이 방법 → 스케일차 |
| occlusion ↔ T7 occlusion_risk | 79 | 0.656 | **0.768** | +0.0 | 0.283 / 0.217 | **좋은 일치**; v3가 약간↑(이웃 LOS 근사가 더 적극적, 30m·+2m) |

**계통 편향(요약)**: (i) v3 뷰 카운트가 v2보다 **약간 낮음** — v3는 **지붕면 표본**에 한정(v2 T7은 풋프린트 전체 인프레임).
(ii) v3 `median_incidence`는 **전-가시뷰 중앙값(~60°)**, v2는 **선정 뷰 단일값(~15°)** — 다른 양(선형 무상관, 순위 ρ=0.51).
`frac_views_incidence_le60`이 식별용으론 더 유용. (iii) v3 `lowtex`는 더 엄격한 임계라 절대값 v2의 ~1/10이나 **순위는 동의**(ρ=0.65).
(iv) v3 `occlusion`은 이웃-높이 LOS 근사로 v2 T7보다 약간 큼.

**대표 불일치(정의차, 오류 아님)**: incidence — 4908054 v3 80.6 vs v2 15.0(v2=near-nadir뷰만); lowtex — 4906977 v3 0.089 vs
v2 0.829(임계/방법차); occlusion — 4906969 v3 1.0 vs v2 0.047(단차평 건물이 더 높은 이웃에 둘러싸임 → LOS 근사 100%).

**결론**: **정의가 일치하는 축(뷰 총수/오블리크 r≈0.97, near-nadir r=0.84, 폐색 ρ=0.77)에서 강일치** → v3 재투영·기하가
P0-audit와 정합. 나머지 차이는 **의도된 정의 통일**(입사각=전-뷰 중앙값, 텍스처=지붕마스크·엄격임계)이며 순위는 보존.

## 5. [5] 일관성 점검 — reason=`no_points`인데 `rf_pt_density>0` 7동 (설명만, 재분류 없음)

대상 7동(모두 **DIM 입력**): DEBY_LOD2_ **4908049·8568392·8568391·4907199·108247350·108247351·4907027**.

**관측(canonical w2_1)**: 7동 모두 DIM에서 `rf_success=True`·**`rf_pt_density`=4.35~23.69 pt/m²(>0)**이나
`reason=pointcloud_unusable_no_points`·**`rf_roof_planes=0`**·`has_lod22=False`. 같은 7동 **ALS는 성공**(density 10~19,
roof_planes 1~5, has_lod22=True).

**밀도 근거의 이원성(코드 확인, `08_roofer_w2.py:555,578-584`)**:
1. **`rf_pt_density`** = Roofer가 보고하는 **입력(풋프린트 클립) 원점 밀도** — 점이 실제로 존재함(>0).
2. **`reason=pointcloud_unusable_no_points`** = Roofer가 `rf_pointcloud_unusable=True` **그리고** `rf_roof_type=="no points"`일
   때만 부여 = **Roofer 내부 판정**: 자체 지붕점 선별(지면·벽·이상치 제거) 후 **사용 가능한 지붕점이 0** → `rf_roof_planes=0` → LoD2.2 없음.

→ 즉 `"no points"`는 **"클립이 비었다"가 아니라 Roofer의 `rf_roof_type` 판정("선별 후 쓸 지붕점 없음")**이다.
`rf_pt_density`(원 클립 밀도)와 `no_points`(내부 사용가능 지붕점)는 **서로 다른 단계의 양**이라 모순이 아니다.
7동은 **생성축(ALS✓∧DIM✗) 실패가 맞고**(density>0가 이를 뒤집지 않음), **재분류하지 않는다.**
동일 7동 ALS는 유사 밀도서 성공 → 차이는 **원점 개수가 아니라 DIM 지붕점의 품질/응집**(P0 점군-중간표현 약점 논지와 정합).

## 6. 종합 (판정 금지)

- **v3 = 199동 단일 정의·단일 스크립트 재계산, 16컬럼 전동 199/199 완비**(v2의 생성축 텍스처 0·교차각 0·뷰 79 결측 전부 해소).
- **QA**: 정의 일치 축서 v2/P0-audit와 강일치(투영 검증); 차이 축은 의도된 정의 통일(문서화, 순위 보존).
- **[5]**: `no_points`+`density>0` 7동은 **Roofer 내부 "지붕점 없음" 판정 vs 풋프린트 클립 밀도**의 단계차 — 모순 아님, 재분류 없음.
- **원재료 확정**: 서브클래스 규칙은 김휘영이 이 CSV로 고정. **라벨 미생성.**

> 재현: `docker run … jointbuildgs:dev python3 phases/p2-gsjso/scripts/population_aux_v3.py`(신규계산·재구성 없음).
> QA: `… jointbuildgs-p0-tools:t0 python3 …/population_aux_v3_qa.py`. CSV=`docs/population_aux_v3.csv`(=`overseg_lever/` 원본 사본).
