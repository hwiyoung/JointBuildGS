# MVS–Existing ALS 3D source-relation 기술 반환 v1

## 결론

전체 공통 공간을 250 m spatial tile로 처리하여 199,813개 3D core를 다섯 관계로 라벨링했다. 이 중 이후 current-view 렌더링 대상으로 넘기는 `SIGNIFICANT_DISCREPANCY`, `MVS_ONLY_SUPPORT`, `PRIOR_ONLY_SUPPORT`는 145,981개다. 이는 **source-difference/support 후보 지도**이며 실제 시계열 변화나 어느 source가 옳은지에 대한 판정이 아니다.

상태는 `COMPLETE_DEVELOPMENT_NON_CONFIRMATORY`, 필수 정성 웹뷰어는 `READY_FOR_QUALITATIVE_WEB_REVIEW`, `scientific_verdict`는 `null`이다.

## 실제 입력과 계보

| Source | Epoch | 실제 입력 | 좌표·정합 계보 |
|---|---:|---|---|
| current-image MVS | 2024-12-17 | `phase-payloads/p2/mvs_native_textured_mesh_preflight_v1/P2-MVS-NATIVE-DENSE-SCENE-RECOVERY-v2/work/mvs/openmvs/dim_dense.ply` | scene-local XYZ + `[690953, 5336071, 604] m`, EPSG:25832 |
| Existing ALS | 2022 | `phase-payloads/p0-audit/data/raw/als/{690_5335,690_5336,691_5335,691_5336}.laz` | provider-declared EPSG:25832, DHHN2016 → current camera ellipsoidal scalar bridge `Z + 45.7 m` |

MVS 원본은 43,926,567점이며 robust 전체 공간 domain 안에는 43,819,444점이 들어왔다. ALS는 네 타일에서 domain 안에 5,019,478점이 들어왔다. Domain은 MVS XY의 `q0.001–q0.999 + 4 m`와 ALS 범위의 교집합이다. 건물 footprint, stable ID, 93동 roster, current UAS LiDAR, LoD2 RoofSurface/Z는 읽지 않았다.

최초 준비 실행은 config에 임시로 옮겨 적은 ALS checksum이 실제 파일과 달라 입력 partition 전에 fail-closed 됐다. `gate_s0_input_manifest_v1.json`과 직접 SHA-256을 대조해 네 파일의 canonical hash로 수정했고, 재실행에서 모두 일치했다. 원시 입력은 수정하지 않았다.

## 방법

- 250 m tile, 5 m halo, 2 m core spacing으로 전체 공간을 처리했다.
- MVS core의 local surface에서 직경 4 m로 normal을 추정하고, normal 방향 직경 2 m·half-length 3 m cylinder에서 두 source의 투영 평균·표준편차·점수를 구했다.
- 양쪽에 최소 4점 support가 있으면 standard local-normal M3C2 signed distance와 local-noise LoD95를 계산한다.
- 한쪽 support가 0이면 core source에 따라 `MVS_ONLY_SUPPORT` 또는 `PRIOR_ONLY_SUPPORT`, 1–3점이면 `NOT_COMPARABLE`로 보수적으로 분리했다.
- primary `SIGNIFICANT_DISCREPANCY`는 `|distance| > LoD95_local`인 high-recall 렌더 후보다. 별도 `robust_significant`는 0.5 m registration envelope를 더한 LoD95도 넘는 경우다. 0.5 m는 C4 acceptance-envelope 민감도이지 추정된 registration covariance가 아니다.
- MVS point covariance와 ALS strip별 acquisition precision이 고정되지 않았으므로 precision-aware M3C2 결과는 생성하지 않고 `pm_valid=0`으로 유지했다.

## 라벨 결과

| ID | 관계 | 개수 | 비율 | 다음 단계 |
|---:|---|---:|---:|---|
| 1 | `COMPATIBLE_WITHIN_LOD` | 19,389 | 9.70% | 기본적으로 렌더 후보에서 제외 |
| 2 | `SIGNIFICANT_DISCREPANCY` | 59,908 | 29.98% | 양 source 충돌 렌더·current-view 판정 |
| 3 | `MVS_ONLY_SUPPORT` | 10,865 | 5.44% | MVS 단독 지지 렌더·current-view 판정 |
| 4 | `PRIOR_ONLY_SUPPORT` | 75,208 | 37.64% | prior 단독 지지 렌더·current-view 판정 |
| 5 | `NOT_COMPARABLE` | 34,443 | 17.24% | normal/support/boundary 원인과 함께 보류 |

`robust_significant`는 5,315개로 전체 core의 2.66%, primary discrepancy의 8.87%다. 이것은 렌더 우선순위 보조 flag이며 나머지 discrepancy를 기각하는 판정이 아니다.

## exact downstream schema

`relation_map.npy`와 `render_queue.npy`의 한 row는 다음 필드를 갖는다.

```text
x,y,z,nx,ny,nz,
relation_class,core_source,reason,n_mvs,n_als,
m3c2_signed_m,lod95_local_m,lod95_reg_upper_m,significance_ratio,
sigma_mvs_m,sigma_als_m,robust_significant,pm_valid,
normal_point_count,surface_variation
```

- `x,y,z`: current MVS/pose와 같은 scene-local XYZ, metre. EPSG:25832 표시나 GIS 변환 시 config의 world shift `[690953, 5336071, 604] m`를 더한다. ALS Z에는 partition 전에 `+45.7 m` bridge가 적용되어 이 local frame으로 들어온다.
- `core_source`: `0=MVS`, `1=ALS reciprocal`
- `relation_class`: 위 1–5 enum
- `reason`: `OK`, `NORMAL_INSUFFICIENT`, `OWN_SUPPORT_INSUFFICIENT`, `OTHER_SUPPORT_SPARSE`, `SOURCE_BOUNDARY`의 numeric enum
- `m3c2_signed_m`: deterministic local normal에서 `ALS projection mean - MVS projection mean`으로 정의한 signed distance
- `render_queue.npy`: class 2/3/4만 포함하며 schema는 동일

## 실행량과 검증

실제 점이 있는 tile은 9개였다. 대표 tile은 약 9.8초, 최대 밀도 tile은 59.9초·peak RSS 약 1.44 GiB였고, 64개 tile receipt의 누적 runtime은 169.1초였다. merge는 12.7초였다.

Docker unit test 6개와 산출물 validator를 통과했다. Validator는 output hash, class count, required fields, render-queue allowlist, precision leakage, binary PLY header/body, `scientific_verdict: null`, prohibited-input 비접근을 각각 `PASS`로 확인했다.

## 산출물과 다음 gate

Canonical external root:

```text
$JBGS_ARTIFACT_ROOT/phase-payloads/phd/mvs_als_source_relation_v1/
  PHD-MVS-ALS-SOURCE-RELATION-v1/
```

주요 파일은 `relation_map.npy/.ply`, `render_queue.npy/.ply`, `relation_elements.csv.gz`, `relation_map_preview.png`, `technical_return.json`, `validation_receipt.json`이다. 정확한 SHA-256은 `artifacts/manifests/phd/mvs_als_source_relation_v1/technical_result_manifest_v1.json`에 고정했다.

### 필수 정성 웹뷰어

Docker viewer URL은 `http://127.0.0.1:8891/`이며 container 이름은 `jbgs-mvs-als-relation-viewer-8891`이다. 재시작은 `scripts/phd/mvs_als_source_relation_viewer_v1/serve.sh`로 수행한다.

뷰어는 다음 세 레이어를 동일한 scene-local 3D 공간에서 동시에 표시한다.

- 1 m deterministic display voxel의 current-image MVS 460,443점
- 같은 display voxel의 registered Existing ALS 683,124점
- 원 계산 해상도를 유지한 199,813개 relation core와 다섯 class

MVS와 ALS는 source별 색상·visibility·opacity·point size를 독립 조절할 수 있다. relation core는 class별 filter, `2/3/4` 렌더 큐 preset, `robust 2` preset, label/M3C2 signed distance/significance ratio 색상 모드를 제공한다. active tile로 이동할 수 있고, core를 클릭하면 signed distance, local/registration-upper LoD95, support 수, source, reason, local/world 좌표를 확인할 수 있다.

1 m voxel은 브라우저 전시 전용이며 method input, M3C2 parameter, 라벨, validation score로 되먹임되지 않는다. asset hash·stride·class count·offline dependency 검증과 HTTP 200, headless Chrome DOM `ready · 199,813 relation cores`, WebGL screenshot smoke를 통과했다. 정확한 viewer lineage와 receipt SHA-256은 `artifacts/manifests/phd/mvs_als_source_relation_viewer_v1/technical_result_manifest_v1.json`에 고정했다.

다음 단계는 class 2/3/4를 current multi-view로 투영해 image evidence로 `IMAGE/PRIOR/FUSION/ABSTAIN` source 판단을 하는 것이다. current UAS LiDAR는 이 지도 생성이나 parameter 선택에는 소급 사용하지 않고, 별도 score-only validation 계약이 승인될 때만 평가한다. 93동은 그 이후 downstream 평가 subset으로만 교차 집계한다.
