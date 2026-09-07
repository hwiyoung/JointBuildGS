# Wu–Vallet 2026 원방법 재현 조건과 P3 개발의 구분

> 2026-09-07. 원문·공개 코드 가용성 감사. `scientific_verdict: null`.
> 이번 사용자 지시: Wu–Vallet을 **전체 연구의 주 대조군**으로 두고, GS 없이 본래 갱신 점군을 먼저 재현한다. P3를 첫 개발 지역으로 삼고 P2는 후속 배제 사례로 유지한다.
> 이 문서는 원방법의 구현 조건을 기록한다. 별도 P3 개발 실행은 해당 실행의 설정·receipt로 확인하며, 이 문서 작성만으로 원방법 재현 완료를 뜻하지 않는다.
> 후속 지시 “논문 확인해서 구현 가능할까?”에 따라 **§9의 원문 기반 구성요소 구현**을 추가했다. §1–8의 미실행 표시는 최초 문헌 감사 및 원방법 전체 재현의 상태다.

## 1. 원문에서 확인한 범위

**논문:** Teng Wu, Bruno Vallet, *Image LiDAR based change detection and updating for urban 3D reconstruction*, ISPRS Annals XI-2-2026, 385–392, 2026-07-03. [DOI/공식 초록][W26H] · [공식 전문][W26].

| 원문 위치 | 확인한 입력·계산·산출물 |
|---|---|
| §3.1, Fig.2 | ALS LAS/LAZ의 GPS time으로 scanline을 복원하고, scan-order 공간의 2D Delaunay로 sensor mesh를 만든다. GPS trajectory를 시간 보간해 echo별 optical center를 얻는다. |
| §3.2, §4.2 | 정향된 현재 영상에서 PSMNet disparity, master별 multi-view forward intersection, pixel adjacency mesh를 만든다. 정점은 camera center를 보존한다. 과거 LiDAR 학습라벨의 noisy label을 SGM disparity와 **1 px** 차이로 정제한다. |
| §3.3, Fig.6 | CGAL AABB 기반 교차 검사로 consistent/changed/single을 구분한다. 일치 ALS·ALS-only를 유지하고, old changed를 제거하며 new changed·image-only를 추가한다. |
| §4.1–4.3 | IGN ALS 약10점/m²·영상20cm, GCP 정합. Grenoble 2021→2024, Lyon 2021→2023. 작은 오탐 영역을 크기로 제거하지만 문턱은 미기재. |
| Fig.12·16, §5 | 최종 산출물은 **갱신 점군**이다. 완성 textured mesh·GS는 원산출물이 아니다. 변화 GT 수작업 라벨이 없으며 정량적 갱신 품질 평가는 후속 과제다. |

영상 mesh 오차·가림·식생에서 오탐을 보고하지만, 이것이 P3에서의 실패나 제안법 우위라는 뜻은 아니다. 구조 보존·현재 기하 갱신은 이미 다룬 선행 성과다. 전체 방법 비교는 원산출물과 그 이후 재구성 확장을 모두 포함한다. [원문 §4.3–5][W26]

## 2. 공식 코드와 실행 자원의 현재 상태

논문이 명시한 공식 저장소는 [whuwuteng/ChangeUpdateJN][CODE]다. **2026-09-07 05:44:46 UTC / 14:44:46 KST**, 공개 GitHub REST 요청은 HTTP 404를 반환했다. 웹 직접 요청도 404였으며 저자 공개 repository 목록에도 없었다. 이는 현재 공개 접근 실패를 뜻하며, 저장소가 영구적으로 존재하지 않는다는 판정은 아니다. 논문은 코드 공개를 미래형으로 설명한다.

| 자원 | 상태와 사용 한계 |
|---|---|
| ChangeUpdateJN 공식 코드 | 접근 불가. commit·LICENSE·실제 CLI·의존성 lock·저자 parameter 파일·checkpoint를 확인하지 못했다. `official_code_reproduction = NOT_EXECUTED`. |
| [PSMNet upstream][PSM] | 공개. 확인한 master commit `87ac9093afbf6545c093bd9d26c5ffd66e49a7b8`, MIT. README는 Python3.7, torch1.6+, torchvision0.5와 자체 stereo-pair 추론을 안내한다. |
| upstream 사전학습 모델 | KITTI/SceneFlow용 링크가 있다. **Wu–Vallet 2026 실험의 학습 checkpoint와 동등하지 않다.** upstream 공개만으로 원논문의 dense matching이 재현되지는 않는다. |
| CGAL | 논문은 AABB Tree·edge collapse를 언급하고 참고문헌은 manual6.1을 인용한다. 이것이 실제 빌드 version/commit의 증거는 아니다. |
| 논문의 실험 자료 | 공개 열람한 자료에서 정확 tile·영상/trajectory 파일 목록·정합 변환·학습 표본 membership을 확보하지 못했다. 일반 IGN 데이터 접근과 논문 exact 입력 확보는 구분한다. |

새 Docker 환경의 의존성 선택은 구현 receipt에 기록한다. 이 감사에서는 코드 clone·설치·학습·기하 처리를 실행하지 않았다.

## 3. P3로 옮길 최소 재현 절차

아래는 **원문의 계산을 실행·검증할 수 있게 풀어쓴 구현 계약**이며 저자 공개 CLI가 아니다. 미기재 사항은 §4에 남긴다.

1. **입력 결속.** P3의 ALS 원행·MVS 원행, 원영상·카메라·depth/disparity lineage, 좌표계·시간·이미 적용한 보정을 manifest에 고정한다. 현재 UAS와 LoD2 평가 기하는 입력·정합·문턱 선택에서 제외한다. P3는 개발 prism ID이고 확정 building stable ID가 아니다.
2. **ALS sensor mesh.** 원 LAS의 GPS time과 scan/return 정보를 읽고 flightline 혼합·중복 echo를 확인한다. 별도 trajectory가 있으면 동일 시각/좌표계로 보간한다. scanline/order의 2D 좌표에서 삼각형을 구성하고 원 XYZ·원행·optical center를 연결한다. 시간만 존재한다고 scanline 복원이 자동으로 확정되지는 않는다.
3. **현재 image sensor mesh.** rectified pair와 원카메라의 변환을 보존하고, master별 disparity를 3D로 교차시킨다. 유효 pixel adjacency에서 삼각형을 만들고 master camera center와 원 pixel ID를 연결한다. 복수 master·가림·재투영 실패·중복 표면을 처리하는 규칙도 명시한다.
4. **거리·가시성 분류.** 두 mesh의 가까운 삼각형 관계와 optical-center 기반 교차를 따로 기록한다. 일치/불일치/단독을 결정하기 전의 거리·교차 대상·방향을 보존한다. 구체 predicate·문턱·삼각형 집계는 검산해야 한다. §5의 2023/2026 차이를 반영한다.
5. **영역 정제와 점군 갱신.** 연결영역별 크기와 제거 전후 class를 저장한다. 원 ALS에서 삭제된 원행, 남은 원행, MVS에서 추가된 원행을 분리한다. 최종 점군의 모든 점에 원소스·원행·선택 이유를 유지한다. 이 단계에는 GS가 없다.
6. **검증.** 원입력, 원분류, 정제분류, 갱신 점군을 같은 범위·단면에서 비교한다. 입력 점이 중복되거나 경계에서 소실된 경우와 평가 참조가 없는 경우도 집계한다. 원방법의 출력에 현재 RGB를 입힌 결과는 별도 확장으로 기록한다.

2026 fusion은 수식으로 제시되지 않았다. 구현의 bookkeeping 표현은 `updated = retained_old ∪ admitted_new`로 둘 수 있다. 이는 평균·신뢰도 가중 blending이나 본 연구의 `FUSION` 행동을 뜻하지 않는다. old/new 삼각형 class를 공유 정점과 native point membership에 전달하는 규칙은 별도로 정의해야 한다.

## 4. 원문만으로 동결할 수 없는 값과 동작

| 항목 | 누락과 구현 시 기록할 내용 |
|---|---|
| scanline 복원 | 시간 간격/방향 전환 기준, 여러 return의 처리, flightline 경계. 임의 규칙을 저자 기본값으로 쓰지 않는다. |
| 삼각형 구성 | 깊이 단차·긴 edge·degenerate face의 제외, 결손을 잇는 범위, 여러 sensor mesh의 중복 처리. |
| 영상 전처리 | exact stereo pair/master 목록, rectification/crop/해상도, PSMNet checkpoint·학습 일정·분할·disparity 범위, multi-view fusion 검정값. |
| mesh 단순화 | 실제 사용 여부·비율·정점 optical center/membership 갱신. |
| consistency | 거리 metric·문턱, overlap 정의, 양방향 집계와 경계 처리. |
| 교차 검사 | ray/segment/tetrahedron predicate, test 위치·집계, 수치 epsilon·self-hit·coplanar·가림 처리. CGAL 라이브러리 이름만으로 이 값들이 정해지지 않는다. |
| 작은 영역 제거 | 크기의 단위가 face 수/점 수/면적인지, 연결성 및 문턱의 정확값, 제거된 class의 복귀 규칙. |
| 최종 갱신 | mixed-class 정점 처리, 중복점 제거, 기존/신규 경계의 tie-break. |

이 값은 개발 config와 민감도 비교로 구체화할 수 있다. 다만 그렇게 완성한 결과의 provenance는 `paper_based_reimplementation_with_declared_choices`이며 공식 코드의 동일 결과를 확인했다는 뜻은 아니다. 실제로 사용한 자료·geometry가 원 sensor mesh를 대체했다면 아래의 component/adaptation으로 더 제한한다.

## 5. 2023 방법과의 혼용 방지

[Wu, Vallet & Demonceaux 2023, §III-B][W23]는 triangle와 viewpoint가 만드는 **빈 tetrahedron**의 교차를 설명한다. 작은 삼각형은 개별 ray 사이로 빠질 수 있다고 지적한다. 따라서 centroid ray 몇 개의 hit 결과를 그 volumetric predicate와 동일하다고 볼 수 없다. 2026은 2023을 인용하면서 AABB ray tracing이라고 설명하지만 구체 predicate/샘플링은 공개 코드로 확인하지 못했다.

두 논문의 갱신 규칙도 동일하지 않다. 2023의 asymmetric conflict에서는 과거 빈공간에 나타난 새 표면 자체가 과거 표면의 소실을 입증하지 않는다. 반면 2026 §3.3·Fig.6은 새 건물 아래의 이전 ground 영역③을 changed로 제거한다. **2023의 single 판정을 그대로 옮겨 2026이라고 명명하지 않는다.**

2023의 time-series sustainability, QPBO mesh mosaic, seam stitching을 2026의 원실행에 추가하지 않는다. 그런 결합은 별도 비교법이다. 2026의 기본 결과는 단순 점군 갱신이다.

## 6. 지금 가능한 실행의 재현 수준

| 수준 | 충족 조건 | 표시 |
|---|---|---|
| 저자 실행 재현 | 공식 code/checkpoint·exact data/config를 확보하고 native 갱신 점군까지 실행 | 현재 미실행·자원 미확보 |
| 원문 기반 전체 구현 | 원 sensor mesh·sensor center·원 matching 절차를 구성하고 미기재 선택을 명시 | 가능한 후속 목표. 이 감사에서는 구현하지 않음 |
| 변화·갱신 구성요소 재현 | 동일 sensor mesh/centers에 change/update를 적용하되 기존 current MVS로 dense matching을 대체 | 입력 대체를 명시. end-to-end 재현과 분리 |
| P3 개발 adaptation | XYZ를 XY/height mesh로 대체하거나, ALS trajectory 대신 가정 viewpoint·현재 camera projection을 사용 | **Wu–Vallet 원방법 재현으로 부르지 않음.** 실제 계산과 표현 차이를 기록 |

ALS trajectory가 없으면 원 ALS visibility를 재현할 수 없다. 현재 camera ray만으로 가능한 검사는 현재 관측의 빈공간에 놓인 과거 표면을 찾는 일부 방향이다. 새 건물/이전 ground 처리까지 원 sensor-viewpoint 비교와 같다고 확대하지 않는다. native XYZ만 남은 경우 pixel/scan-order 인접성도 복원되었다고 가정하지 않는다.

P3의 기존 NCC/roughness 결과는 ALS 활용 가능성을 확인할 **후보 선정 근거**다. ALS의 현재 적합성·절대 정확성 판정은 아니다. MVS 결손에 남긴 ALS는 현재성 미확인일 수 있다. 별도 개발실험이 그곳을 보존하더라도 평가 전용 참조·허용 현재 관측으로 검증하기 전에는 현재 복구 성공이라고 쓰지 않는다.

## 7. 전체 연구·A/B 비교에 연결

**필요성 → 이미 해결한 부분:** 과거 기하를 버리지 않고 변경 부위에 새 기하를 넣는 갱신은 주 대조군의 기존 성과다. 우리의 연구 필요성을 갱신 기능의 부재로 쓰지 않는다.

**남는 검증 질문 → 수정 후보:** P3에서는 양쪽 실제 기하오차와 현재 사용 가능성, 판단 후 구조 유지·현재 외관·관측 가능한 세부를 확인한다. 미기재 원방법 parameter 때문에 생긴 차이와 새 판단/재구성 효과를 분리한다.

**A:** 같은 입력에서 원 분류·점군 선택의 차이를 기록한다. `consistent/changed/single`을 `IMAGE/PRIOR/FUSION/ABSTAIN`으로 변환하는 adapter가 있으면 그 규칙과 잃는 정보를 명시한다. 변화 없음은 자동적인 절대 정확성 보장이 아니다.

**B:** 원 갱신 점군, 동일 점군의 공통 텍스처/GS 확장, 새 재구성의 결과를 구분한다. 원 점군에 렌더 출력이 없다는 이유로 렌더 점수를 0 처리하지 않는다. 같은 실제 인계를 고정한 B 비교와 A까지 바꾸는 전체 비교를 함께 둔다.

**기대 효과 → 실행 결과:** 결손 보완·구조 유지·현재 텍스처/세부·양호 영역 열화를 같은 고정 지지에서 보고한다. 출처 지도·단면·실제 렌더·양방향 기하거리/완전도는 provenance와 분모를 함께 가진다. 개발 adaptation의 성공도 주 대조군 대비 우위를 확정하지 않는다.

## 8. 접근 기록과 원문 provenance

- 공식 PDF: `https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf`.
- 웹 PDF 추출은 39MB 크기 제한으로 실패했다. 공식 호스트를 `curl`로 읽어 `pdftotext -layout`으로 전문을 확인했다. 검토 중 [ResearchGate의 동일 논문 전문][RG]도 보조 확인했으며 기술 내용의 출처는 저자 논문이다.
- 로컬 임시 원문: `/tmp/jbgs_wu_vallet_2026_20260907.pdf`; **39,061,976 bytes**, SHA256 `c57f088755b21fb437f14e103d5222dc228eecf6306addaa8f2f92cc20f51f86`. 이번 다운로드를 직접 해시했고 기존 P2 감사의 기록과 일치했다. `/tmp`는 durable artifact 저장소가 아니다.
- 추출 전문 `/tmp/jbgs_wu_vallet_2026_20260907.txt`, 직접 확인한 PDF p.388/Fig.6 이미지 `/tmp/jbgs_wu_vallet_2026_fig6_20260907.png`. 이들은 원문 읽기용 임시 파일이며 실험 산출물이 아니다.
- HTTP 404 응답: `/tmp/jbgs_wu_vallet_2026_code_api_20260907.json`; SHA256 `a298fd3d1a255b0eb21a952212460852e05ba9721d3445fb42d7ad054d88f94a`; 요청 `https://api.github.com/repos/whuwuteng/ChangeUpdateJN`; 관측 시각은 §2.
- 기존 [P2 A v2 문헌 감사](../p2_ab_v2/A_LITERATURE_AND_DESIGN_ko_v2.md)의 원문 접근 기록도 확인했다. 기존 연구 문서·payload·실험 결과를 수정하거나 새 결과로 재명명하지 않았다.

## 9. 후속 구현 — 명시적 sensor 입력의 sampled-ray 구성요소

사용자의 후속 지시에 따라 [ray_update.py](../../../../src/phd/wu_vallet_p3_v1/ray_update.py)를 추가했다. 입력은 `SensorMesh(vertices, triangles, optical_origins, native_rows)` 두 개다. **삼각형 topology와 정점별 optical origin은 필수이며 XYZ로 추측하지 않는다.** `RayUpdateConfig(distance_tolerance_m=...)`의 거리값도 명시적으로 전달한다.

구현은 triangle AABB BVH의 nearest segment hit, KD-tree 후보의 실제 point-to-triangle 거리, 양방향 교차 검사, Fig.6의 삭제·추가를 수행한다. source 자체가 가리는 광선은 빈공간 주장에 사용하지 않는다. 삼각형의 vertex/centroid 샘플을 검사하며 `consistent > changed > single`의 우선순위를 face·vertex에 적용한다. 이 유한 샘플, 집계 규칙과 작은 영역 필터 생략은 모두 반환 provenance에 기록한다. 원래 두 시점 sensor mesh·PSMNet 전체 pipeline 재현은 여전히 미완료다.

**구성요소 검증:** Docker에서 [단위검증](../../../../tests/phd/test_wu_vallet_ray_update.py) **9개 PASS**를 확인했다. 일치 표면 보존, 소실 지붕 교체, Fig.6 신축 정책, 단독 피복, 광선 endpoint, source self-occlusion, 면까지의 거리, 필수 센서 입력, 원입력 보존을 검사했다. 이는 수치적 동작 검증이며 실제 P3 성능·ALS 현재 적합성·원저자 결과 일치를 뜻하지 않는다.

**재현 가능한 합성 실행:** [설정](../../../../configs/phd/wu_vallet_p3_v1/ray_fixture_v1.json)과 [driver](../../../../scripts/phd/wu_vallet_p3_v1/run_ray_fixture.py)는 unchanged/demolition/construction/single/mixed 다섯 합성 장면을 고정한다. Docker 실행 예시는 다음과 같다.

```bash
python scripts/phd/wu_vallet_p3_v1/run_ray_fixture.py \
  --config configs/phd/wu_vallet_p3_v1/ray_fixture_v1.json \
  --output /output/run
```

각 장면은 원입력·topology·origins·class·교차·최종 점군과 원행을 담은 NPZ, `updated_points.ply`, 정량 accounting JSON을 만든다. 전체에는 출처/단면 그림과 config·source·출력 hash/commit/version receipt를 남긴다. 기존 출력 폴더를 덮어쓰지 않는다. 합성 좌표는 `SYNTHETIC_LOCAL_CARTESIAN`이고 실제 EPSG:25832의 P3 실험과 구분한다. GS는 수행하지 않는다. 실제 실행 성공 여부와 외부 payload 경로는 별도 receipt가 기준이다.

**합성 실행 결과:** Docker에서 다섯 장면의 고정 accounting 검사 **5/5 PASS**를 확인했다. 최종 점 수는 위 장면 순서로 4/4/4/8/20개이며, mixed scene은 기존 점8개와 신규 점12개를 보존한다. 이는 설정에 명시한 도형/정책의 실제 실행 결과다. 실제 P3의 점군 갱신 성능으로 해석하지 않는다.

원문 PDF·전문·Fig.6·HTTP 응답의 장기 참조는 새 외부 디렉터리 `phase-payloads/phd/wu_vallet_p3_v1/literature_20260907/`와 그 manifest로 승격했다. §8의 `/tmp` 경로는 수집 당시 위치다.

## 10. 후속 구현 — 센서 기하를 보존하는 mesh 전처리

[sensor_mesh.py](../../../../src/phd/wu_vallet_p3_v1/sensor_mesh.py)는 두 개의 명시적 입력 adapter를 제공한다. [별도 검증](../../../../tests/phd/test_wu_vallet_sensor_mesh.py)은 좌표 변환·원소속·결손·센서 시간 처리를 다룬다.

**검증 결과:** Docker에서 센서 mesh 검증 **11개 PASS**를 확인했다. ray-update 9개와 합하면 단위검증 20개다. 합성 camera/trajectory의 수치적 처리 검증이며 실제 센서 metadata가 확보되었다는 뜻은 아니다.

| adapter | 입력·보존 항목 | 구현의 경계 |
|---|---|---|
| `image_depth_to_sensor_mesh` | camera-Z depth(m), depth 픽셀좌표의 K, `Xcam=R·Xworld+t`의 R/t. 정점마다 원 flat pixel ID·u/v·camera center `−Rᵀt`를 보존 | 고정 NW–SE 대각선의 pixel adjacency. finite positive depth만 사용하고 명시한 edge 길이·depth jump로 face를 제외. 결손을 넘어 Delaunay로 연결하지 않음 |
| `als_acquisition_to_sensor_mesh` | 원 XYZ, 명시적 scan ID·beam order·GPS time, optical-center trajectory의 시간/좌표 | `(beam_order, scan_id)` 공간 Delaunay. trajectory support 밖이면 실패하고 보간구간의 optical center만 사용. 중복 echo의 자동 선택·GPS antenna→sensor center 추정·scanline 복원은 하지 않음 |

영상 adapter의 `ImageMeshConfig(max_edge_length_m, max_depth_jump_m, ...)`와 ALS adapter의 scan/beam/time/edge gap은 명시적 개발 설정이다. 저자 기본 문턱으로 표시하지 않는다. 유효 depth이지만 face를 만들지 못한 pixel도 별도 분모에 남기고, 기본적으로 isolated vertex는 mesh에서 제외한다. 원 depth raster 자체를 덮어쓰지 않는다.

기존 COLMAP 등 depth를 제공하면 **원 matching 단계가 대체된 image sensor-mesh 구성요소 실행**이다. 실제 P3의 영상 depth mesh가 만들어져도 과거 ALS sensor trajectory가 없는 상태에서 양방향 원방법 전체 재현으로 승격되지 않는다. 두 adapter는 좌표계 정합·시간기준·센서 metadata의 실제 정확성이나 후보의 현재 적합성을 인증하지 않는다.

[W26H]: https://doi.org/10.5194/isprs-annals-XI-2-2026-385-2026
[W26]: https://isprs-annals.copernicus.org/articles/XI-2-2026/385/2026/isprs-annals-XI-2-2026-385-2026.pdf
[W23]: https://arxiv.org/html/2303.07182v1#S3.SS2
[CODE]: https://github.com/whuwuteng/ChangeUpdateJN
[PSM]: https://github.com/JiaRenChang/PSMNet/tree/87ac9093afbf6545c093bd9d26c5ffd66e49a7b8
[RG]: https://www.researchgate.net/publication/408463381_Image_LiDAR_based_change_detection_and_updating_for_urban_3D_reconstruction
