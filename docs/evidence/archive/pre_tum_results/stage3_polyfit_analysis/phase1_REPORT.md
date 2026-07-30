# PolyFit Phase 1 — error pattern analysis

**Goal**: 4 가설 (A: implementation / B: input data / C: algorithm fit / D: measurement) 중 dominant 가설을 좁힌다. **새 실행 없음. 기존 자료만 사용.**

자료 출처:
- [results/phase2_ablation_citygml/_gt_polyfit_test/summary.json](../phase2_ablation_citygml/_gt_polyfit_test/summary.json)
- [src/stage3/polyfit_cli.cpp](../../src/stage3/polyfit_cli.cpp)
- [scripts/phase2_synthesis/gt_polyfit_test.py](../../scripts/phase2_synthesis/gt_polyfit_test.py)
- [results/phase2_ablation_citygml/REPORT.md §7](../phase2_ablation_citygml/REPORT.md)
- [results/phase2_ablation_citygml/figures/fig_polyfit_steps_large.png](../phase2_ablation_citygml/figures/fig_polyfit_steps_large.png)

---

## 분석 1 — Per-building cross-tab

`summary.json` 의 `per_building` 9건 직접 추출 (bid 3은 polyfit_fail 별도):

| bid | type | n_planes | n_pts | n_surf | vol | n_errs | error counts |
|---|---|---|---|---|---|---|---|
| 0 | tri-slope | 16 | 214 | 81 | 163.0 | 46 | 303×26, 307×20 |
| 1 | flat | 7 | 80 | **7** | **2876.1** | 7 | 303×5, 307×2 |
| 2 | flat | 8 | 80 | **6** | **50.2** | 5 | 303×2, 307×3 |
| 3 | complex | 66* | — | — | — | — | **polyfit_fail @ Line:55** (input parser) |
| 4 | flat | 6 | 54 | **6** | **1276.8** | 3 | 303×1, 307×2 |
| 5 | hip | 22 | 323 | 117 | 232.2 | 2 | **204×2** (only) |
| 6 | hip | 21 | 284 | 121 | 922.3 | 72 | 303×33, 307×39 |
| 7 | complex | 20 | 302 | 103 | 260.4 | 58 | 303×29, 307×29 |
| 8 | gable | 10 | 120 | 24 | 504.2 | 14 | 303×7, 307×7 |
| 9 | hip | 15 | 216 | 67 | 134.3 | 42 | 303×17, 307×25 |

(*) bid 3: 분석 5에서 추출한 GT-clustered plane 수.

**관찰**:
- **n_surf vs n_planes**: flat은 비율 ≈ 1 (n_planes 그대로 face가 됨). 비-flat은 비율 4-7x (PolyFit MIP가 face arrangement에서 다수 선택). **bid 1: 7→7, bid 2: 8→6, bid 4: 6→6, bid 5: 22→117(5.3x), bid 6: 21→121(5.8x), bid 8: 10→24(2.4x)**.
- **bid 2 vol=50.2 collapse**: 평균 vol(732)의 7%. n_surf(6) ≤ n_planes(8) — face가 부족하게 생성됨. flat 빌딩이 mesh 자체가 작게 만들어짐 (PolyFit MIP가 지지 약한 plane 탈락 처리).
- **bid 5 anomaly**: errors 204×2만, 303/307 0건. 다른 8건과 완전히 다른 오류 패턴 — geometry는 manifold/orient 모두 OK인데 plane 좁은 영역에서 normals deviation.
- **bid 3 polyfit_fail "Line: 55"**: 입력 파일 line 55 파싱 실패. cluster된 66 planes에 대해 N×면적 비례 점 샘플링 결과 첫 부분에서 형식 오류 또는 plane_id out-of-range.

---

## 분석 2 — Error 코드 의미별 분류 (val3dity 2.x reference)

| code | name | 가설 매핑 | 본 데이터 count |
|---|---|---|---|
| 303 | NON_MANIFOLD_CASE | **A** primary, B possible | 120 |
| 307 | ALL_POLYGONS_WRONG_ORIENTATION | **A** (orient propagation 미완) | 127 |
| 204 | NON_PLANAR_POLYGON_NORMALS_DEVIATION | B (input plane 비평면) | 2 |
| polyfit_fail | parser/MIP 실행 실패 | B (입력 형식) 또는 C (복잡도) | 1 |

**Total errors 250건의 가설 매핑**:
- A 직접 지지: 120 + 127 = **247 (98.8%)**
- B 직접 지지: 2 + (1 if polyfit_fail = parser) = **3 (1.2%)**
- C 직접 지지: (1 if polyfit_fail = complexity) = 0-1
- D 직접 지지: **0** (val3dity ≠ quality 검증 metric, 본 분석 범위 밖)

**307의 본질**: `orient_to_bound_a_volume`은 `is_closed(model)`이 true일 때만 실행됨 ([src/stage3/polyfit_cli.cpp:79-87](../../src/stage3/polyfit_cli.cpp#L79)). REPORT.md:348의 "stitch_borders 가 float-precision 한계로 close 못함" 진술이 정확하면, mesh가 closed 안 됨 → orient 단계 skip → 307 자동 발생. 즉 **303 → 307은 cascade**: 303 fix하면 307은 자동 사라질 가능성.

---

## 분석 3 — Type별 패턴

| type | bid | val3dity | 주 errors | 의미 |
|---|---|---|---|---|
| flat | 1, 2, 4 | 0/3 | 303 + 307 (모두) | flat은 가장 단순한 case인데도 fail → A 강력 시사 |
| tri-slope | 0 | 0/1 | 303 + 307 | A 일관 |
| complex | 3, 7 | 0/2 | bid 3=parser fail, bid 7=303+307 | C 부분(bid 3) + A(bid 7) 혼재 |
| hip | 5, 6, 9 | 0/3 | bid 5=204만, bid 6/9=303+307 | bid 5는 다른 모드 (B), 나머지는 A |
| gable | 8 | 0/1 | 303 + 307 | A 일관 |

**핵심 패턴**: 
- **flat 3/3 fail with 303+307**: flat은 prism이라 hip-skeleton 같은 복잡한 알고리즘 없이도 처리 가능 → 알고리즘 적합성(C)이 아니라 **공통 post-processing 결함(A)** 시사. 결정적.
- **bid 5 hip만 다름**: 22 planes / 117 faces인데 errors 204×2만 → mesh manifold/orient는 OK. **부분 A 설계가 일부 case에서 작동했다**는 증거 (운/configuration 의존).
- **bid 3 complex polyfit_fail**: 다른 모드. parser 또는 MIP 자체 실행 실패. C 또는 B.

---

## 분석 4 — 시도 vs 미시도 영역

### 이미 시도된 fix (코드 직접 인용)

| 단계 | 위치 | 효과 |
|---|---|---|
| `stitch_borders(model)` | [polyfit_cli.cpp:77](../../src/stage3/polyfit_cli.cpp#L77) | float-precision 한계로 closed mesh 보장 못함 (REPORT §7) |
| `is_closed(model)` 체크 | [polyfit_cli.cpp:79](../../src/stage3/polyfit_cli.cpp#L79) | 결과: false (대부분의 building) |
| `orient_to_bound_a_volume(model)` (closed시) | [polyfit_cli.cpp:86](../../src/stage3/polyfit_cli.cpp#L86) | is_closed=false라 거의 실행 안 됨 → 307 cascade |
| Python quantize-dedup (1mm) | [gt_polyfit_test.py:162-174](../../scripts/phase2_synthesis/gt_polyfit_test.py#L162) | vertex 좌표만 dedup, edge sharing은 재구성 안 함 |
| signed-volume → 음수면 winding 일괄 반전 | [gt_polyfit_test.py:191-204](../../scripts/phase2_synthesis/gt_polyfit_test.py#L191) | 일괄 반전 → 일부 face가 inward인 경우 해결 못 함 |

### 미시도 fix (CGAL 표준 watertight repair recipe)

| 단계 | CGAL function | 본 코드/데이터 검증 |
|---|---|---|
| polygon soup 구성 | `polygon_mesh_to_polygon_soup` | grep 0 hit |
| duplicate vertex merge | `merge_duplicate_points_in_polygon_soup` | grep 0 hit |
| degenerate face 제거 | `repair_polygon_soup` | grep 0 hit |
| 일관 orientation | `orient_polygon_soup` | grep 0 hit |
| polygon mesh 재구성 | `polygon_soup_to_polygon_mesh` | grep 0 hit |
| custom BFS orientation | (Python 또는 C++) | grep 0 hit |

표준 repair 5단계 recipe 자체가 **한 번도 실행되지 않음**.

### 시도/미시도 영역과 error의 연결

- 303 (NON_MANIFOLD): `repair_polygon_soup` + `merge_duplicate_points_in_polygon_soup`이 정확히 이걸 다룬다. 미시도.
- 307 (WRONG_ORIENTATION): `orient_polygon_soup`이 polygon-level에서 해결 (closed 여부 무관). 미시도.

→ **error 247건의 영역은 미시도 fix의 직접 표적**. A 가설 강력 지지.

---

## 분석 5 — Cluster_planes 입력 영향

[gt_polyfit_test.py:34-62](../../scripts/phase2_synthesis/gt_polyfit_test.py#L34) — `cluster_planes(faces, cos_tol=0.98, dist_tol=0.2)`:
- cos_tol=0.98 → 약 11.5° 이내 normal 합치기
- dist_tol=0.2m → 0.2m 이내 평행 plane 합치기

**bids 0-9 GT face → clustered plane ratio**:

| bid | type | GT faces | clustered planes | ratio | sem(R/W/G) |
|---|---|---|---|---|---|
| 0 | tri-slope | 21 | 16 | 1.31 | 3/17/1 |
| 1 | flat | 8 | 7 | 1.14 | 1/6/1 |
| 2 | flat | 8 | 8 | 1.00 | 1/6/1 |
| 3 | complex | **127** | **66** | 1.92 | 25/101/1 |
| 4 | flat | 6 | 6 | 1.00 | 1/4/1 |
| 5 | hip | 32 | 22 | 1.45 | 4/27/1 |
| 6 | hip | 28 | 21 | 1.33 | 4/23/1 |
| 7 | complex | 30 | 20 | 1.50 | 5/24/1 |
| 8 | gable | 12 | 10 | 1.20 | 2/9/1 |
| 9 | hip | 21 | 15 | 1.40 | 4/16/1 |

- bid 1, 2, 4 (flat): ratio 1.0-1.14 — coplanar 합쳐도 plane 거의 그대로. 입력 손실 미미.
- bid 3 complex: 127 → 66 planes (1.92x). 가장 큰 합. 그리고 polyfit_fail. **입력 plane 수 과다 + 알고리즘 부담**.
- 나머지: 1.2-1.5x 합. 통상 수준 (대각선 face 1쌍이 1 plane이 되는 등).

**dist_tol=0.2m 위험**: 두 평행 벽이 0.2m 이하로 가까우면 합쳐짐. 도시 환경에서 실측 데이터로는 위험할 수 있지만, 본 GT는 3D BAG의 LOD2 모델이라 두께 0인 wall (single plane). 합쳐질 위험 거의 없음.

**cos_tol=0.98 위험**: 11° 차이 plane 합쳐짐. tri-slope나 hip의 인접 slope이 11° 이내면 위험. 현실적으로 hip 4개 slope은 90° 간격이라 안전. 다만 tri-slope의 일부 face가 합쳐질 가능성 있음 (B0 GT 21 → 16, ~24% 손실).

**B 가설 영향 평가**: 입력 cluster 자체는 GT face의 1.0-1.5x 압축 (bid 3 제외). flat은 거의 무손실인데도 fail → B가 dominant 원인 아님. bid 3 polyfit_fail은 B 또는 C로 갈 수 있음.

---

## 분석 6 — Figure 검토

[fig_polyfit_steps_large.png](../phase2_ablation_citygml/figures/fig_polyfit_steps_large.png) — 4 buildings × 4 steps panel:

**Row 1 (flat, 8 faces)**:
- Step 1 (GT): 깔끔한 박스 solid (회색 + 일부 빨강 표시).
- Step 2 (Clustered input, 7 planes / 80 pts): 점이 매우 sparse. plane당 평균 11점.
- Step 3 (PolyFit, 7 faces / 17 verts): mesh 형태가 보이지만 일부 face 빠짐.
- Step 4 (CityJSON INVALID, 5 bad faces): 빨간 face 5개 — top/일부 wall이 invalid 표시. **mesh 거의 닫혀 있는데 face-level 문제**.

**Row 2 (hip, 32 faces → 22 planes)**:
- Step 2: 점 더 dense (323 pts).
- Step 3 (PolyFit, 117 faces / 198 verts): **wireframe 형태로 매우 fragment됨**. 117 face가 대부분 서로 분리된 작은 polygon. 명확한 solid 형태 없음.
- Step 4 (CityJSON INVALID, 2 bad faces): 표시조차 어려운 분해 상태.

**Row 3 (complex, 35 faces — bid 7로 추정)**:
- Step 1 (GT): L-shape 형태 (회색).
- Step 3: **PolyFit FAILED**.
- Step 4: no CityJSON.

**Row 4 (complex, 127 faces — bid 3)**:
- Step 1 (GT): 거대한 복합 building.
- Step 3: **PolyFit FAILED**.
- Step 4: no CityJSON.

**시각적 결론**:
- **flat**: PolyFit MIP는 정확한 face 수 (7) 산출. 그러나 face-level 문제 (5 bad)로 INVALID. → A 가설 강력 (post-processing/face validation 단계).
- **hip**: MIP가 117 faces 산출 (22 plane × 5x). 명확한 solid 안 됨. 단순 stitch로는 해결 어려운 구조 → A primary, C 보조 (MIP 자체가 over-segment 경향).
- **complex (large)**: 알고리즘 자체 실행 실패. C 또는 B.
- **REPORT.md:351 ("Step 3 mesh 는 watertight 안 닫힘") 정확**: figure에서 Step 3가 명백히 깨짐 (특히 hip).

---

## 가설 판정 표

| 가설 | 지지 증거 | 반증 증거 | 가능성 |
|---|---|---|---|
| **A** (implementation: post-processing 미완) | • 247/250 errors (303+307) = 98.8%<br>• flat 3/3 fail with 303+307 (단순 case도 fail)<br>• 미시도 fix (`repair_polygon_soup`, `orient_polygon_soup`)가 정확히 303·307 표적<br>• cascade 구조: 303 fix → 307 자동 해소<br>• REPORT §7 자체가 "1-2h Python BFS 또는 polygon_soup 접근" 인정 | • 미시도 fix가 실제로 통과시킬지는 미검증 (해 봐야 확실) | **HIGH** |
| **B** (input data: cluster_planes 누락/병합) | • bid 3 complex 66 planes → polyfit_fail (입력 형식 또는 plane 과다)<br>• 204 errors 2건은 plane 불일치 시사 | • cluster ratio 1.0-1.5x (압축률 낮음, flat은 무손실)<br>• flat 무손실인데도 303+307 → B로 설명 안 됨<br>• 247/250 errors는 cluster 손실로 설명 불가 | **LOW-MEDIUM** |
| **C** (algorithm fit: PolyFit 가정 부적합) | • bid 3 polyfit_fail (66 plane 복잡도 한계 가능)<br>• hip 빌딩에서 n_surf 5x (MIP 자체 over-segment)<br>• REPORT §7 "candidate face arrangement"가 폭발 가능 | • flat에서는 MIP가 정확히 face 수 산출 (n_surf=n_planes)<br>• bid 5 hip는 manifold OK (errors 204×2만) — 같은 type 안에서도 MIP가 잘 풀리는 case 존재 | **LOW-MEDIUM** |
| **D** (measurement: val3dity ≠ quality) | • height/coverage/vol_ratio 측정 0건 — quality는 사실상 모름<br>• PolyFit MIP가 기하적 *근사*만 제공 | • 본 분석은 val3dity stage *이전* failure를 다룸. D는 val3dity *통과 후* 의 quality 문제를 가리키므로 본 데이터로 평가 불가 | **UNFALSIFIABLE** (본 데이터에서) |

---

## Dominant 가설: **A (HIGH)**

**근거 요약**:
1. **수치적 비대칭**: error 247/250 (98.8%)이 A 표적 영역에 직접 귀속.
2. **Type 균질성**: 가장 단순한 flat (prism) 3/3 모두 동일 패턴 (303+307)으로 fail. C/B로는 flat 실패 설명 불가.
3. **시도 영역 vs error 영역 mismatch**: 시도된 fix (stitch_borders 단일 단계 + Python quantize)와 미시도 fix (`repair_polygon_soup` + `orient_polygon_soup` 5단계 recipe) 사이에 정확히 *현재 error의 표적*이 위치.
4. **REPORT §7 자체 인정**: "Python BFS orientation propagation 또는 polygon_soup 접근 필요" — 저자가 미시도임을 명시.

**보조 (A를 부분적으로 보충)**:
- **C (LOW-MEDIUM)**: bid 3 complex의 66 planes는 PolyFit MIP의 복잡도 한계와 가까울 수 있음. polyfit_fail의 진짜 원인은 input parser vs MIP 분리 필요.
- **B (LOW-MEDIUM)**: 2 errors (bid 5 204) + bid 3 polyfit_fail 후보. 작은 영향이나 존재.

**D (UNFALSIFIABLE)**: 본 분석은 val3dity stage 이전 failure에 갇혀 있음. 가설 D를 평가하려면 val3dity 통과한 mesh의 GT 비교 필요 — 현 시점 0건이라 평가 불가.

---

## Phase 2 후속 실험 방향 (추정 input)

**A dominant 시 우선순위 (수립)**:

### Step P2-A1: untried CGAL repair 5-단계 recipe 적용
[polyfit_cli.cpp](../../src/stage3/polyfit_cli.cpp)에 추가:
```cpp
namespace PMP = CGAL::Polygon_mesh_processing;

// PolyFit output → polygon soup
std::vector<Point> points;
std::vector<std::vector<std::size_t>> polygons;
PMP::polygon_mesh_to_polygon_soup(model, points, polygons);

// Repair pipeline
PMP::merge_duplicate_points_in_polygon_soup(points, polygons);
PMP::repair_polygon_soup(points, polygons);  // 중복/degenerate 제거
PMP::orient_polygon_soup(points, polygons);  // consistent CCW outward

// Rebuild mesh
Surface_mesh repaired;
PMP::polygon_soup_to_polygon_mesh(points, polygons, repaired);

// Then existing close+orient
PMP::stitch_borders(repaired);
if (CGAL::is_closed(repaired)) {
    PMP::orient_to_bound_a_volume(repaired);
}
```
이 recipe가 정확히 303 (manifold)+307 (orientation) 표적. 실패 시 A→A2 (custom BFS) 또는 A 가설 약화.

### Step P2-A2: error code별 cleanup 검증
- 9 buildings * (before/after) val3dity → 303+307 감소율 측정.
- 만약 A2 후에도 303 잔존: A 약화, C 의심.
- 만약 307 잔존: orient_polygon_soup이 작동 안 함 → 더 깊은 manifold 결함.

### Step P2-A3 (병행 가능): bid 3 polyfit_fail 분리 진단
- "Line: 55"의 의미: input.txt 55번 줄 파싱 vs PolyFit 내부 line.
- input file 직접 검사 (재실행 없이 cluster_planes 출력 dump).
- B(parser format) vs C(plane 수 과다)로 좁힘.

**B 보조 검증** (low priority):
- 204 errors 2건이 어느 plane에서 발생한 face인지 (bid 5 cluster 결과 점검).

**D 검증** (가장 후): A2 통과 후 height/coverage/vol_ratio 측정 → 진짜 quality 평가.

---

## Self-verification

- 6개 분석 (1 cross-tab, 2 error 매핑, 3 type pattern, 4 시도/미시도, 5 cluster ratio, 6 figure) 모두 표 형태 출력: ✓
- 가설 A/B/C/D 각각 지지/반증/가능성 명시: ✓
- Dominant 가설 결정: **A (HIGH)** + 보조 B/C(LOW-MEDIUM), D(UNFALSIFIABLE): ✓
- Phase 2 후속 방향: 미시도 CGAL repair recipe (P2-A1) 우선, bid 3 분리(P2-A3), D 후순위: ✓
- 가설 4개 중 어느 하나도 dominant 아니면 그렇게 보고하기로 함 — 본 분석은 A가 명확히 dominant라 단일 가설 결정.
