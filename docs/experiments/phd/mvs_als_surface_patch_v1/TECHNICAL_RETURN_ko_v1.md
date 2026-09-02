# MVS–Existing ALS 국소 연결 surface patch 기술 반환 v1

## 결론

동결된 M3C2 5관계지도 199,813개 core를 다시 계산하거나 덮어쓰지 않고, 동일
source surface 안에서만 연결하는 guarded-Kruskal patch 계층을 추가했다. 선택된
`base` 프로파일은 45,129개 patch를 만들었고, 이 중 core 4개 이상이며 candidate-safe
관계 purity를 통과한 stable patch는 4,858개·72,785 core(전체의 36.43%)다.

결과는 **판단 단위로는 유효하지만 최종 렌더 geometry로 바로 쓰기에는 아직
파편적**이다. 전체 patch의 중앙값은 1 core인 반면 stable patch의 중앙값은 11
core다. 52,179 core(26.11%)는 작은 연결섬, 6,853 core(3.43%)는 혼합관계로
fail-closed됐고, 64,965 core(32.51%)는 normal·class 5·높은 surface variation
때문에 연결 교량에서 제외됐다. 관계가 섞인 9,884 core(4.95%)도 후보 증거가
`compatible`로 평활화되지 않도록 fail-closed했다. 작은 patch나 부적격 core는
삭제하지 않았다.

따라서 이 결과의 역할은 M3C2 core별 salt-and-pepper를 source 판정용 국소 표면
단위로 집계하는 것이다. patch bbox나 색칠된 core를 면으로 채워 최종 렌더링하거나,
patch dominant label을 source truth로 읽어서는 안 된다. 원 source point/Gaussian을
patch로 역매핑하는 별도 resolver와 current-view visibility 검사가 필요하다.

상태는 `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, `scientific_verdict: null`이다.

## 방법과 안전 경계

- 입력은 frozen `relation_map.npy`와 그 technical return뿐이며 SHA-256을 먼저
  확인했다. M3C2는 재실행하지 않았다.
- `core_source=0/1`을 분리해 MVS와 Existing ALS를 한 patch로 합치지 않았다.
- class 5는 연결 bridge로 사용하지 않았다.
- `surface_variation > 0.15` 또는 비유한 core는 base profile에서 bridge로 사용하지
  않았다.
- 국소 edge는 3.5 m 거리, 15° sign-invariant normal 차이, 0.35 m symmetric
  point-to-plane gap을 모두 통과해야 한다.
- edge를 정렬한 뒤 합칠 때마다 합친 전체 patch의 반경 8 m, plane RMSE 0.25 m,
  최대 잔차 0.60 m, local-to-global normal 20°를 다시 검사해 chaining을 막았다.
- 작은 patch, 혼합관계 patch, 부적격 core는 `NOT_COMPARABLE`로 남겼다.
- raw class 2/3/4는 dominant 후보로 유지되거나 class 5로 유보되며, patch 다수결로
  class 1 `COMPATIBLE`이 되는 경로를 금지했다.
- patch UID는 profile과 정렬된 source/XYZ/normal member key의 SHA-256에서 만들어
  재현 가능한 계보를 제공한다.

current UAS LiDAR, LoD2 Ground/Roof/Z, stable building ID, 93동 roster는 읽지 않았다.
source authority, temporal change, `IMAGE/PRIOR/FUSION/ABSTAIN`, Gaussian weight는
산출하지 않았다.

## 전후 파편화 비교

같은 base bridge graph에서 class 1–4를 원시 관계 라벨별로 나누면 connected
component가 76,335개다. source-surface 연결 후 patch는 45,129개로 31,206개
(40.88%) 줄었다. 다만 이 수치는 단순히 적을수록 좋은 score가 아니다. 관계 경계를
넘어 같은 표면을 묶는 대신 global plane/radius guard가 과병합을 막은 결과다.

| 항목 | 결과 |
|---|---:|
| 전체 relation core | 199,813 |
| bridge 적격 core | 134,848 (67.49%) |
| 전체 patch | 45,129 |
| stable patch | 4,858 |
| stable core | 72,785 (36.43%) |
| small-island core | 52,179 (26.11%) |
| mixed-relation core | 9,884 (4.95%) |
| bridge-unassigned core | 64,965 (32.51%) |
| class 5 bridge | 0 |
| mixed-source patch | 0 |
| candidate core 보존 | 100% |
| candidate→compatible 평활화 | 0 |

stable patch의 연결성과 평면성은 다음과 같다.

| 항목 | p10 | median | p90 | max |
|---|---:|---:|---:|---:|
| core 수 | 4 | 11 | 31 | 67 |
| 반경 (m) | 1.829 | 4.765 | 7.706 | 7.999 |
| plane RMSE (m) | 0.014 | 0.066 | 0.157 | 0.250 |
| plane p95 절대잔차 (m) | 0.022 | 0.108 | 0.287 | 0.548 |
| normal p95 (deg) | 5.859 | 12.743 | 17.230 | 19.934 |

원시 5관계 preview와 patch-aggregated 관계, patch UID를 나란히 그린
`surface_patch_before_after.png`를 생성했다. 여기서 회색 증가분은 삭제가 아니라
small/mixed/unassigned의 fail-closed 표시다.

## 민감도와 현재 판단

profile은 reference 결과를 보고 고른 것이 아니라 중간값인 `base`를 사전에
선택했다. fine/base/coarse의 연결성–평면성 trade-off는 다음과 같다.

| profile | stable core 비율 | stable patch median core | stable plane RMSE median/p90 (m) | stable normal p95 median (deg) |
|---|---:|---:|---:|---:|
| fine | 25.40% | 10 | 0.036 / 0.087 | 7.588 |
| base | 36.43% | 11 | 0.066 / 0.157 | 12.743 |
| coarse | 44.62% | 10 | 0.105 / 0.252 | 17.702 |

coarse는 더 많은 core를 stable로 만들지만 평면잔차와 normal 분산이 커진다. fine은
더 평면적이지만 unassigned가 45.03%로 증가한다. 이 결과만으로 어느 profile이
과학적으로 최적이라고 결론내릴 수 없다. 현재 base는 웹 정성검토와 current-view
렌더링을 위한 개발 기준일 뿐이다.

## 검증과 산출물

Docker unit test 6개와 실제 산출물 validator를 통과했다. Validator는 upstream
hash, 199,813행 1:1 보존, raw relation 계보, patch ID/UID 무결성, class 5 bridge 0,
mixed source-family patch 0, candidate core 100% 보존, candidate→compatible 0,
ambiguous fail-closed, output
hash, prohibited-input 비접근, `scientific_verdict: null`을 확인했다.

Canonical external root:

```text
$JBGS_ARTIFACT_ROOT/phase-payloads/phd/mvs_als_surface_patch_v1/
  PHD-MVS-ALS-SURFACE-PATCH-v1/
```

주요 산출물은 `patch_membership.npy`, `surface_patch_summary.npy/.csv.gz`,
`surface_patch_adjacency.npy`, `surface_patch_map.ply`,
`surface_patch_before_after.png`, `technical_return.json`,
`validation_receipt.json`이다. 정확한 SHA-256은
`artifacts/manifests/phd/mvs_als_surface_patch_v1/technical_result_manifest_v1.json`에
기록했다.

별도 patch 웹뷰어는 `http://127.0.0.1:8892/`에서 실행 중이다. raw 5관계,
patch-aggregated 관계, patch UID, source family, patch status를 전환하고 core를
선택해 전체 patch member와 품질 통계를 확인할 수 있다. 기존 raw relation viewer
`http://127.0.0.1:8891/`와 그 산출물은 변경하지 않았다.

frozen current camera의 exact MVS/ALS 독립 렌더와 patch overlay도 별도 task에서
완료했다. 결과와 표현 편향 평가는
`docs/experiments/phd/mvs_als_current_view_render_v1/TECHNICAL_RETURN_ko_v1.md`에
기록한다.
