# P2 효과 검증 (make-or-break) — 깨끗한 라벨 + ablation

> 📑 **P2 (제안 방법 효과 검증)** 작업. 인덱스: [docs/P2_index.md](../../../P2_index.md). 사람 검토자: 김휘영.
> **일자:** 2026-06-19 · **branch:** `feature/p2-gsjso` · **판정은 사람 — 본 문서는 측정·관찰까지(판정 금지).**

## 0. 목적 (한 줄)

제안 방법(`L_sem`·`L_mutual`·`L_structure`)이 **상한 기준의 깨끗한 라벨**(reference LoD2 의미면 투영)에서
① 무텍스처 MVS 실패 8동을 **복구**하고 ② survivor·control의 지붕면 품질이 **LiDAR(reference) 수준에 근접**하는지를,
컴포넌트별 ablation(vanilla→+sem→+mutual→+structure→both)으로 분리해 본다. 정답 = reference LoD2 지붕면 구조.
엔진 로직 무변경(라벨·config·분석만). EPSG:25832 · 도커.

---

## 1. 예전 결과 (기대치 보정)

L_sem/L_mutual/L_structure 과거 실험 전수조사: **[docs/experiments/p2_mob_past_results.md](../../p2_mob_past_results.md)** (157행 추출).
요지:

- 모든 기존 증거는 **합성 데이터**(MatrixCity Aerial / 3D BAG synthetic-B / FlatCity)뿐. **실항공·깨끗한라벨·밀도보정 facet 비교는 전무** → 본 실험이 그 공백을 메움.
- **L_mutual**: 벽 법선 수직화엔 가장 강하나(P1 19→91%, P2 28→79%) **Stage-3 val3dity를 회귀**시키고(P2 −3.8pp) terrain drift. FC-S5/S6 전체가 mutual 재설계에 소진, "terrain-off" 변형(A8)이 겨우 +0.008.
- **L_structure**: 평면 정렬(σ_normal −45% P1)·val3dity 최상(P2 +2.3pp)이나 강한 supervision 하에선 primitive 효과 소실(P2 +1%).
- **L_sem**: 비파괴적이나 단독으로 downstream 지표를 움직인 적 없음. semcal(FC-S6E)은 오히려 악화.
- **Both 시너지 없음**(P2 Both ≤ Structure). 절대 수치 신뢰 불가, 상대 랭킹만.

→ **기대치:** structure가 면 정규화에 유리, mutual은 위험, sem은 보조. 실데이터·깨끗라벨에서의 검증은 미지.

---

## 2. 깨끗한 라벨 + QA (관문: 통과)

reference LoD2/3 의미면(`690_5334.gml`·`690_5336.gml`, 945동, 48,622 삼각형)을 **Open3D RaycastingScene**으로
937 영상 포즈(COLMAP w2c)에 raycast → `semantic/<stem>.png`(uint8 0..3, Roof=1/Wall=2/Ground=3). **의미 클래스만**(기하 미반입).
생성: [phases/p2-gsjso/scripts/make_clean_labels.py](../../../../phases/p2-gsjso/scripts/make_clean_labels.py).

| QA 지표 | 값 |
|---|---|
| 픽셀 커버리지 (집계) | BG 37.1% / **Roof 40.0% / Wall 22.9%** / Ground **0.0%** |
| roof>1% & wall>1% 프레임 | **936 / 937** |
| 11개 타깃 건물 메시 포함 | **11 / 11** (프레임당 41~386회 관측) |

- 오버레이([clean_labels_qa/overlay_*.png](../../../../results/tum_transfer/clean_labels_qa)): 지붕은 지붕에, 벽은 oblique 시점의 facade에 정합. 등록오차 ~1 m(LoD2 고유 정확도).
- **Ground 0% (기록된 한계):** LoD2엔 건물 사이 terrain이 없고 GroundSurface는 항공 시점에서 자기-가림 → terrain 라벨 부재.
  부수효과: terrain 클래스가 없어 **L_mutual의 알려진 terrain-drift 실패모드는 비활성**(survey §mutual). → 관문 통과(부실 아님).

---

## 3. base config + distortion 결정

base = `tum_vanilla_proper.yaml`(downscale1·30k·densify/prune·`w_nc=0.05`) 위에 의미·prior만 추가. gravity `e_gravity=[0,0,-1]`
([configs/input_and_alignment/tum_gravity.json](../../../../configs/input_and_alignment/tum_gravity.json), EPSG:25832 Z-up). 5구성 동일 base: [configs/tum_mob/](../../../../configs/tum_mob).

- **distortion: OFF로 fallback (기록).** 스케일보정 sweep 결과 **w=100/1.0/0.1 모두 PSNR 붕괴**, **w=0.01도 densification 불안정(N 371k→113k)**.
  TUM 큰 metric depth에서 distortion(~depth²) 폭주, 엔진 동결이라 scene-scale 정규화 불가 → 검증된 base(distortion off) 사용.
- **`structure_voxel_size=2.0`(metric):** G1 grouping 기본 0.05는 unit-scale → 500 m 장면에서 grouping 무력화되므로 metric 값으로.
- **무회귀:** 5구성 30k 학습 안정, PSNR **19.9~20.6** (vanilla 20.34 = 검증된 run_proper 재현, N 1.02~1.19M).

학습 실행: [phases/p2-gsjso/scripts/run_mob_all.sh](../../../../phases/p2-gsjso/scripts/run_mob_all.sh) (train→extract→eval 분리 파이프라인).

---

## 4. 평가 (밀도 보정 + 5-way)

각 구성×건물: TSDF 추출(median depth, opacity>0.5, **min-obs≥3**) → **ALS 밀도로 voxel 다운샘플**(matched) → P0 분류(SMRF+overlay)
→ Roofer → CityJSON → val3dity → RoofSurface 수·plane RMS. 5-way(ALS·sparse·MVS·proposed·reference)는 **동일 harness**로 카운트.
harness 교차검증: MVS를 동일 harness에 통과 → P0 패턴 재현(복구 0/실패, 4906972=3, 4906969 과분할 invalid). ✓

### 4.1 5-way 지붕면 수 (orig 밀도, RoofSurface; ✗=val3dity invalid 또는 MVS missing_lod22)

| 건물 | 축 | **ref** | ALS | MVS(P0) | sparse | vanilla | +sem | +mutual | +structure | +both |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| 42364609 | 복구 | 1 | 1 | ✗ | 0 | 0 | 0 | 0 | 0 | 0 |
| 42364659 | 복구 | 2 | 0 | ✗ | 0 | 0 | **2** | 1 | 1 | 4 |
| 42364663 | 복구 | 1 | 1 | ✗* | 0 | 0 | 0 | 0 | 2 | **1** |
| 4907182 | 복구 | 2 | 5 | ✗ | 0 | 0 | 0 | 0 | 0 | 0 |
| 4907510 | 복구 | 1 | 7 | ✗ | 0 | 0 | 0 | 3 | 3 | 0 |
| 4908050 | 복구 | 1 | 1 | ✗ | 0 | 0 | 0 | 0 | 0 | 0 |
| 4908166 | 복구 | 1 | 1 | ✗ | 0 | 0 | 0 | 0 | 0 | 1 |
| 4908176 | 복구 | 1 | 1 | ✗ | 0 | 0 | 0 | 0 | 0 | 0 |
| 4906969 | 품질 | 3 | 5 | 10✗ | 1 | 2 | 0 | 2 | 4 | 0 |
| 4908023 | 품질 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 2 |
| **4906972** | 품질 | **3** | 3 | 3 | 1 | 17✗ | 12 | 26✗ | **7** | 29✗ |

\* 42364663: P0 canonical은 MVS success(3 planes)였으나 동일 harness 재분류에선 0 — SMRF 재분류 차이(아래 §6 교란).

### 4.2 컴포넌트 기여 — control 4906972 (ref 3면), reference 지붕면 대비 RMS

| 구성 | 지붕면(orig) | val3dity | **RMS→ref (m)** | 해석 |
|---|:--:|:--:|:--:|---|
| vanilla | 17 | invalid | 4.63 | 노이즈 두꺼운 슬랩 |
| **+sem** | 12 | **valid** | **1.18** | 정확도·과분할 크게 개선 |
| +mutual | 26 | invalid | 2.69 | RMS는 개선되나 과분할 악화 |
| **+structure** | **7** | **valid** | **1.14** | **최저 과분할·최저 RMS·valid** |
| +both | 29 | invalid | 3.80 | 시너지 없음(mutual 지배) |
| ALS→Roofer | 3 | valid | (LiDAR 상한) | |

세 품질 건물 RMS→ref(orig, m): 4906972 [4.63→sem1.18/str1.14], 4906969 [0.79→sem0.25/str0.55/both0.48],
4908023 [0.98→sem0.27/str0.42/both0.40, **mutual 12.84 폭발**]. 전체: [results/tum_transfer/mob_analysis/ref_rms.csv](../../../../results/tum_transfer/mob_analysis/ref_rms.csv).
밀도보정(matched) 시 절대 면수는 변하나 **구성 간 순위는 유지**(structure/sem<vanilla<mutual/both). 원본+matched 전체: [eval_results.csv](../../../../results/tum_transfer/mob/eval_results.csv).

### 4.3 복구축 seeding 진단 (복구 실패의 원인)

footprint xy 내 SfM 초기점 / TSDF 표면점 (z-불변): [seeding_diag](../../../../results/tum_transfer/mob_analysis/seeding_diag.json).

| 복구 건물 | SfM(fp) | TSDF vanilla | TSDF both | 재구성? |
|---|--:|--:|--:|---|
| 42364609 | 0 | 0 | 3 | **무씨딩** |
| 42364659 | 127 | 46,406 | 42,337 | 재구성됨 |
| 42364663 | 1,176 | 228,061 | 161,892 | 재구성됨 |
| 4907182 | 58 | 0 | 0 | **무씨딩** |
| 4907510 | 69 | 25,165 | 32,513 | 재구성됨 |
| 4908050 | 59 | 66 | 9 | **무씨딩** |
| 4908166 | 0 | 61 | 327 | 거의 무씨딩 |
| 4908176 | 7 | 5 | 0 | **무씨딩** |

- **5/8동은 프리미티브 자체가 안 생김**(SfM 0~59, TSDF ~0). 무텍스처 → photometric gradient 없음 → SfM 초기점·densification 실패.
  **`L_sem`은 렌더러에서 기하를 detach(geometry-isolation), `L_mutual`/`L_structure`는 기존 프리미티브만 정규화** → 없으면 복구 불가.
  (가우시안 중심 직접 확인: 해당 footprint·높이대에 가우시안 0개.) → **MVS의 무텍스처 약점을 GS-JSO도 씨딩 단계에서 공유.**
- **3/8동(42364659·42364663·4907510)은 재구성됨** → 여기선 **vanilla=0면인데 sem/structure/both가 유효 모델 생성**
  (42364659: vanilla 0 → **+sem 2면 = ref 2면**; 42364663: vanilla 0 → +structure 2 / +both 1=ref). = 의미·구조 prior가 실제로 구조를 살린 부분 신호.

---

## 5. 그림

- [docs/figs/tum_transfer/mob_quality_4906972.png](../../../figs/tum_transfer/mob_quality_4906972.png) — control 4906972 입력 TSDF(5구성, top/side, 높이색). structure의 side-view가 가장 얇음(노이즈↓).
- [docs/figs/tum_transfer/mob_recovery_split.png](../../../figs/tum_transfer/mob_recovery_split.png) — 복구축 씨딩 갈림: 재구성(42364659·42364663) vs 무씨딩(4907182·4908176).

---

## 6. 관찰 (판정 금지)

- **복구(MVS=0 대비 유효+구조 부합):** 8동 중 **어느 구성도 전부 복구 못함**. **5/8은 무씨딩**(근본: 무텍스처에 프리미티브 미생성, 세 손실은 생성 불가).
  **3/8은 재구성되었고 거기서 sem/structure/both가 vanilla 0면을 유효 모델로 살림**(일부는 ref와 일치). → 복구는 "전면 실패"가 아니라 **씨딩 가능 여부로 갈림**.
- **품질(LiDAR로 근접?):** **L_sem·L_structure가 control에서 정확도(RMS 4.6→1.1 m)·과분할(17→7/12)·validity(invalid→valid)를 뚜렷이 개선**.
  **L_mutual·both는 악화**(과분할↑, RMS 국소 폭발, 시너지 없음). 그러나 **어느 구성도 reference(3면)·ALS 수준엔 미달**(RMS 여전히 ~1.1 m, 면수 7~12 vs 3).
- **컴포넌트 귀속:** structure>sem>(vanilla)>mutual≈both 순(품질·정확도). 예전 합성결과(structure 우호·mutual 위험·Both 무시너지)와 **방향 일치**.
- **무회귀:** PSNR 19.9~20.6 (의미·prior 추가로 렌더 품질 회귀 없음).
- **교란(기록):** ① **SMRF가 평탄 무텍스처 지붕을 ground로 흡수** → 일부 "0면"이 "기하 없음"과 모호(ALS 42364659=0도 동일). 본 표는 SMRF 유지·교란 명시(검토자 지시).
  ② **좌표:** GS/OPF=타원체고, GML/ALS=정표고 → **~48 m 지오이드 오프셋**. 지붕면 수·validity는 z-불변이라 무영향; RMS만 z-정렬 후 계산(dz≈40~50 m 회수로 오프셋 확인).

---

## 7. 원인규명 실험 설계 (다음 단계)

복구 한계의 원인 = ① 무텍스처 프리미티브 미씨딩, ② `L_sem` geometry-isolation. 이를 가르는 실험:

| ID | 실험 | 엔진변경 | 가설/예상 | 상태 |
|---|---|:--:|---|---|
| E-R1 | seeding 정량화(SfM·가우시안·TSDF) | 무 | 5/8 무씨딩 확인 | **완료(§4.3)** |
| E-R2 | 추출 완화(min-obs=1·alpha↓) 재추출 | 무 | 무씨딩이면 여전히 ~0(추출 탓 아님 확정) | 권장(가우시안 0개로 사실상 확정) |
| E-R3 | **semantic-driven densification**: 라벨 roof/wall이고 alpha 낮은 영역에 가우시안 생성 | **필요** | 라벨이 기하를 씨딩 → 복구 핵심 레버 | **승인 요청** |
| E-R4 | **L_sem geometry coupling**: render_semantic의 geometry detach 해제(또는 sem-depth 일관성항) | **필요** | 라벨이 기하를 끌어옴(단 기하 오염 위험 — 원래 detach 이유) | **승인 요청** |
| E-R5 | depth 약지도(w_depth>0, MVS depth stage) | 무(데이터) | 무텍스처엔 MVS depth도 비어 5/8 복구엔 무효; 품질 depth는 선명화 가능 | 선택 |
| E-R6 | 후처리: GS-TSDF용 SMRF 튜닝(window↓)·높이기반 분류·Roofer 평면병합 | 무 | 교란(평탄지붕 흡수)·과분할을 후처리로 완화 | 선택 |

> §4 불변규칙상 엔진 동결이므로 **E-R3·E-R4는 김휘영님 승인 후** 별도 브랜치에서. 가장 직접적 레버는 **E-R3(semantic-driven densification)** — "의미가 무텍스처 기하를 만든다"는 P2 핵심 가설을 정면으로 시험.

---

## 8. 재현 (EPSG:25832 · 도커 · 엔진 무변경)

```
# 라벨(관문)
docker compose run --rm -T --user $(id -u):$(id -g) dev python phases/p2-gsjso/scripts/make_clean_labels.py \
  --gml phases/p0-audit/data/raw/lod2/690_5334.gml phases/p0-audit/data/raw/lod2/690_5336.gml \
  --data-root results/tum_transfer/data --out results/tum_transfer/data/semantic --qa results/tum_transfer/clean_labels_qa
# 학습→추출→평가 (분리 파이프라인)
bash phases/p2-gsjso/scripts/run_mob_all.sh
# 분석
docker compose run --rm -T dev python phases/p2-gsjso/scripts/tum_mob_seeding_diag.py
docker run … jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/tum_mob_ref_rms.py
docker run … jointbuildgs-p0-tools:t0 python3 phases/p2-gsjso/scripts/tum_mob_baselines.py …
```
산출(gitignore 스크래치): `results/tum_transfer/mob/{train_*,tsdf_*,eval_results.*}`, `results/tum_transfer/mob_analysis/*`,
`phases/p0-audit/runs/mob_eval/*`. 커밋: 본 문서 + `configs/tum_mob/*`·`configs/input_and_alignment/tum_gravity.json` + `phases/p2-gsjso/scripts/{make_clean_labels,run_mob_all,tum_mob_*,_mob_*}.py`
+ `docs/experiments/p2_mob_past_results.md` + `docs/figs/tum_transfer/mob_*.png`. 엔진 `src/stage2/*` 무변경.
