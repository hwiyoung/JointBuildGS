# C3 roof evidence 5항목 기술 진단 — promoted summary

## 상태

- 기술 상태: `300-CLOSED_LOCAL_TECHNICAL_DIAGNOSTIC`
- 실행 권한: 사용자의 직접 지시에 따른 single Experiment Host local execution
- two-host handoff event: 아님
- 대상: `C3_1_SEM`, `C3_2_SEM_DEPTH`의 seed0와 대표 3건물
- `official_G3_G4_PASS_usable: null`
- `scientific_verdict: null`

전체 한글 보고서는 외부 artifact의 `reports/technical_report_ko_v1.md`, portable report는 `reports/report.html`에 있다. Git-owned resolver는 `artifacts/manifests/p2_c3_tsdf_roof_diagnostic_report_recovery_v2.json`이다.

## 먼저 구분할 세 가지

1. **Semantic context**는 기존 v13 rendered-depth fused 3D points의 전체 semantic 표현이다. Roof는 강조하고 wall·terrain은 흐리게 표시해 주변 구조와 outlier를 보는 용도다.
2. **Roof consensus**는 이번 진단에서 동일 24-view plan으로 렌더한 depth 중 semantic roof이며, 유효 alpha/depth와 최소 2개 distinct-view support를 통과한 점이다. 이번 Poisson과 TSDF의 동일 입력이다.
3. **Inherited Roofer input**은 TSDF 샘플이 아니다. 기존 v13 `rendered_depth_fused_surface_points_v1.ply` 중 semantic class 1이면서 exact GT footprint 내부인 점을 0.2m voxel로 만든 class-6 points다. C2 terrain을 공유하며 이번 진단에서는 Roofer를 재실행하지 않았다.

따라서 semantic context, roof consensus, inherited Roofer input은 서로 다른 계층이다. 특히 TSDF와 inherited Roofer를 직접적인 input-output 관계로 읽으면 안 된다.

## 5항목 결론

### 1. 동일 입력 Poisson–TSDF

TSDF는 동일 depth와 camera ray의 0.45m truncation band 안에서 관측 표면 가까이에 머물렀다. Poisson은 공백을 연결했지만 weak-evidence 건물에서 관측점과 멀리 떨어진 면을 만들었다. 108580336의 evidence-distance p95는 다음과 같다.

| 조건 | Poisson p95 | TSDF p95 | Roof coverage |
|---|---:|---:|---:|
| C3-1 | 32.651m | 0.301m | 1.23% |
| C3-2 | 27.325m | 0.304m | 1.50% |

TSDF가 비어 보이는 것은 이 사례에서 결함을 감춘 결과가 아니라 관측된 roof support 자체가 희박하다는 표시다.

### 2. Semantic 표시 개선

3개 case sheet는 전체 semantic context와 실제 Poisson/TSDF 입력인 roof-only consensus를 별도 행으로 표시한다. Wall/terrain은 mesh 입력이 아니며 흐린 context로만 남겼다.

### 3. 4906975 plane 진단

| 조건 | Class-6 points | Roofer 면 | weak 면(support<100) | residual median / p95 |
|---|---:|---:|---:|---:|
| C3-1 | 35,404 | 25 | 8 | 0.878 / 3.511m |
| C3-2 | 4,342 | 1 | 0 | 0.499 / 3.436m |

C3-1은 TSDF p95 0.342m로 C3-2의 0.366m보다 geometry evidence fidelity가 약간 낫다. C3-2 Roofer의 1면은 더 정확하다는 증거가 아니라 과소분할 가능성을 포함한 강한 단순화다. 두 seed0 control의 실질적 조작 차이는 `load_depth: false→true`, `w_depth: 0→0.03`이므로 이 pair의 직접 원인은 depth loss지만, 반복 seed가 없어 일반적인 인과효과로 확대하지 않는다.

### 4. 4907177 현재 존재 여부

2024 RGB에는 해당 위치의 지붕이 존재한다. Footprint 내부 current points도 C1 16,892점, C2 1,162점이며 median Z는 581.399m와 581.613m다. +45.7m datum의 LoD2 roof 상단 580.88m와 0.52–0.73m 차이다.

반면 기존 prepared local ground는 C1 580.519m, C2 581.193m로, +45.7m datum의 LoD2 GroundSurface 약 559.97m보다 20.55–21.22m 높다. 연속된 지붕 바깥 ring을 local ground로 오인해 `ground+2.5m` 필터가 실제 roof points를 제거한 것이 직접적인 기술 실패 후보다. 이 상태를 철거 또는 current evidence absence로 보고하면 안 된다.

### 5. 108580336 mesh 신뢰도

C3-2는 consensus points 1,191개로 C3-1의 833개보다 많고, TSDF largest component fraction도 0.666 대 0.378로 상대적으로 낫다. 그러나 roof coverage가 1.5% 미만이므로 둘 다 건물 전체 roof mesh로 신뢰할 수 없다.

Inherited Roofer의 겉보기 외곽이 깔끔한 이유는 exact GT footprint가 외곽을 제공하기 때문이다. C3-1 Roofer residual median/p95는 15.395/41.448m다. C3-2는 median 0.355m이나 p95 8.080m이고, 약 4,795m² 면의 support density가 0.127점/m²다. 깔끔한 silhouette는 충분한 roof recovery 증거가 아니다.

## Wall outlier

108580336 wall Gaussian의 in-plane scale p95/max는 C3-1 4.32/44.34m, C3-2 3.53/35.52m다. 큰 elongated Gaussian과 semantic leakage가 전체 semantic 그림을 지배한다. Roof 판단은 roof-only consensus 행에서 해야 한다.

## 실행 및 해석 경계

- GS training: 0
- Roofer invocation: 0
- G2 invocation: 0
- official metric recomputation: 0
- C4/C5 access: 0
- 초기 lineage checkpoint render extraction: 2
- recovery checkpoint render extraction: 0

이 결과는 3건물·seed0의 기술 진단이며 GT-footprint oracle Roofer를 상속한다. `scientific_verdict: null`은 C3-1/C3-2의 최종 과학적 우열, 모집단 일반화, G3/G4/PASS_usable 판정을 하지 않았다는 뜻이다.

Portable HTML은 validation과 package verification을 통과했다. 설치된 Chromium headless-shell이 없어 per-report browser QA는 `structural_only`이며, 3개 case sheet는 원본 해상도로 별도 직접 검토했다.
