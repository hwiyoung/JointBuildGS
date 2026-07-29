# P0 완전성 재검증 — 점군×Roofer 그리드로 LoD2.2 생성 회복 측정

> 작성 2026-06-22. 관찰만, **판정 금지(사람=김휘영)**. EPSG:25832 · Docker · P0 동일 harness.
> 스크립트: `phases/p2-gsjso/scripts/p0c_*.{json,sh,py}`. 산출: `results/tum_transfer/mob_analysis/p0c_step2/`.

## 목적
P0 W2에서 DIM(영상 MVS)이 LoD2.2를 **생성하지 못한** 64동을, 더 좋은 점군(ACMP plane-prior
PatchMatch MVS)과 Roofer 파라미터를 격자로 바꿔가며 **동일 다운스트림**(SMRF 분류 → Roofer →
val3dity)에 다시 투입해 *생성 회복*을 측정한다. "영상 기반 생성-실패가 어떤 lever로 복구되는가
(점군/Roofer/둘 다), 아니면 진짜 한계인가"를 동별로 가른다.

## 대상 모집단 (Step 1 확정)
생성-실패 64동 = **no_points 46 + missing_lod22 16 + no_planes 2** (전부 ALS는 LoD2.2 생성·성공,
2동만 ALS도 실패 → image-특이 격차). 비교용 control = DIM-success(이미 생성됨; 캐노니컬 재사용).
※ 착수메시지의 "control 93"은 캐노니컬 CSV에서 정확히 재현 안 됨(근접: 89=DIM∩ALS-succ, 100/102=DIM-succ) — 명시.

## 방법 (P0 동일 harness 재사용)
- **점군 levers**: ① DIM(기존, 재사용) ② **ACMP 937뷰**(`acmp_work_full/`, 기존) — GS-local(ellipsoidal)
  → ortho-UTM 변환(+[690953,5336071,**556**]; geoid=48). ground가 ~514(=LoD2 HoeheGrund)에 안착해 datum 정상.
- **분류**: `04_classify`와 **동일 SMRF**(cell1.0/slope0.15/scalar1.25/thr0.5/win18) + **동일 footprint
  overlay**(building=6). ACMP는 풀해상도 712 pt/m²가 SMRF/Roofer에 비현실적으로 조밀·과중 → **0.1 m voxel
  다운샘플 = 159 pt/m²**(여전히 ALS 21·DIM 10–50보다 조밀; "더 조밀한 점군" lever 유지). ⚠️ 다운샘플이 희소
  지붕 점수를 줄여 **no_points 회복은 하한**.
- **Roofer**: 캐노니컬 이미지(`3dgi/roofer@sha256:dd2c…`) + AOI box + 동일 footprint GPKG + `--id-attribute
  building_id`. 파싱·val3dity·`classify_reason`은 `08_roofer_w2.py`를 **그대로 import**(캐노니컬과 동일 판정).
- **셀(점군 × Roofer 파라미터)**:

| cell | 점군 | Roofer 파라미터(epsilon/min_pts/complexity) | 회복 |
|---|---|---|---|
| 1 DIM@canonical | DIM(기존) | default (=캐노니컬 w2_1) | **0/64**(=실패 집합, 정의상) |
| 2 DIM@tuned | DIM(기존) | 0.30 / 15 / 0.888 | **0/64** |
| 3 ACMP@canonical | ACMP | default | **17/64** |
| 4 ACMP@tuned | ACMP | 0.30 / 15 / 0.888 | 17/64 |
| 4 ACMP@loose | ACMP | 0.45 / 10 / 0.65 | 17/64 (일부 다른 동) |
| **4 union(tuned∪loose)** | ACMP | — | **+3 → 20/64** |

## 결과 — 동별 복원성 판정 (관찰)
**20/64 회복**(LoD2.2 생성; 19동 val3dity-valid) · **44/64 미회복**.

| 버킷 | n | 회복 | 미회복(assembly-limited) | 미회복(no-signal) |
|---|---|---|---|---|
| no_points | 46 | **13** | 32 | 1 (`4908160`) |
| missing_lod22 | 16 | **7** | 9 | 0 |
| no_planes | 2 | 0 | 2 | 0 |
| **합** | **64** | **20** | **43** | **1** |

**Lever 귀속(회복된 20동):** cloud(ACMP) 17 + cloud+params 3 = **20**; **Roofer-params 단독 = 0**
(cell2 DIM@tuned가 아무것도 못 살림). → 더 좋은 *영상 MVS 점군*이 결정적 lever이고, Roofer 튜닝은
*어느* ~17동이 살지 재배치할 뿐 수를 늘리지 않음.

**회복 동(20):**
- missing_lod22(7): `42364659 4907168 4907169 4907508 4907510 4908176`(cloud), `4959758`(cloud+params)
- no_points(13): `107802038 108247350 108247351 4907015 4907019 4907032 4907199 4908157 4908161 4908167 4908169`(cloud),
  `42364607 4908054`(cloud+params). ※`4908161`은 LoD2.2 생성되나 val3dity-invalid.

**미회복 43(assembly-limited):** ACMP 점은 **있으나**(일부 수천: `104586480`=56k·`4907182`=13k·`4908050`=15k 등)
Roofer가 solid를 못 만듦 → 점군 부재가 아니라 **조립 한계**(테스트한 파라미터 범위 내). 단, 다운샘플 영향으로
저점수 no_points(probe<30) 일부는 하한일 수 있음.

**진짜 한계(no image MVS signal):** `4908160`(ACMP=0 **그리고** relaxed-OpenMVS=0). 추가로 full-ACMP
probe≤1인 `104583794`·`4908053`도 relaxed=0 → 실질 no-signal ≈ 3동.

## Pass 2 (잔차)
설계상 잔차 = ACMP도 ~0인 동만 새 MVS 변형. 해당 = `4908160`(+probe≤1 2동) → relaxed-OpenMVS(res4→2,
기존)로도 0 → fundamental 확정. 그 외 43동은 점이 있어 cloud lever 무관(=조립 lever 영역).

## 한계·가정 (명시)
1. **다운샘플(0.1 m)** 로 no_points 회복은 **하한** — full-res ACMP면 희소동 일부 추가 회복 가능(요청 시 full-res 확인 가능, SMRF ~35min+).
2. **geoid=48 datum**: 생성률·val3dity·복원판정은 geoid-불변(균일 z 평행이동) — height-vs-ALS만 영향(본 산출엔 미포함).
3. **control-93** 비재현 → DIM-success로 대체 표기.
4. 산출은 수치까지 — **합/불·결론은 사람**.

## 산출물
- `results/tum_transfer/mob_analysis/p0c_step2/eval/p0c_verdict.{csv,json}` (64동 판정표)
- `…/eval/{acmp_canon,acmp_tuned,acmp_loose,dim_tuned}_status.csv` (셀별 199동 status)
- `docs/figs/tum_transfer/p0c_recoverability.png` (버킷별 회복/미회복 막대)
- `…/p0c_step2/acmp_classified.laz` (35.5M, EPSG:25832, ground2/building6)
