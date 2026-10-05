# 동일 P2 샘플과 자료 역할 — 개발 검증 v1

Task: `PHD-P2-AB-COMMON-v2` · 상태: `PASS_DEVELOPMENT_INPUT_AND_ROLE_CONTRACT` · `scientific_verdict: null`

기존 P2 prism 전체의 원점 소속과 새 A/B 공통 64단위를 고정했다. 현재 UAS는 별도 평가 파일로 만들었다. 이 결과는 입력·역할 검증이며 후보의 현재 사용 가능성 또는 재구성 성공을 판정하지 않는다.

| 항목 | 실제 고정·검증 결과 |
|---|---|
| 동일 지역 | tile `x004_y004`, scene-local `x[110,158), y[86,132), z[-49.386,-17.679)` |
| 좌표 원점 | `[690953,5336071,604] m`; EPSG:25832는 프로젝트 작업 계약 명칭이며 아래 실제 원자료 좌표 구분을 함께 적용 |
| 전체 단위 | 2 m XY 격자 552개; 빈 단위도 유지, 지붕·벽·지면 의미 라벨 없음 |
| MVS | native 330,679점, 550단위 피복, 2단위 결손; planar patch 소속 293,020점 |
| Existing ALS | native 45,986점, 552단위 피복; planar patch 소속 38,439점 |
| 원자료 소속 | 타일 전체 XYZ를 exact 원 MVS PLY와 4개 ALS LAZ에서 입력 순서대로 재생하여 완전 일치. 원 파일 인덱스·원행·타일행을 모두 기록 |
| 새 공통 pilot | 양쪽 중 한 소스라도 30점 이상인 단위를 정렬하고 균등 정수 인덱스로 최대 64개 고정. 새 사진 측정·참조 오차를 보지 않고 선택 |
| pilot 실제 상태 | 양쪽 존재 63, MVS 자연 결손 1: `P2_X078_Y056` / unit 542 / ALS 160점 |
| 사진 역할 | frozen 66개를 image ID 문자열의 SHA256 순위로 decision 22 / train 33 / appearance_eval 11 분리. 사진·카메라·exact-937 crosswalk 해시 재검증 |
| 현재 UAS 참조 | 원자료 177,981,904점 중 XY prism 2,327,262점; Z 밖 1,286점 제외; 최종 2,325,976점. 전체 552단위에 점 지지 존재 |
| UAS 분류 | 포함점 모두 raw class 0. 이를 지붕·지면 분류로 사용하지 않음 |
| GroundSurface XY | 기존 공통 footprint와 교차한 stable ID는 `DEBY_LOD2_4959326`, `DEBY_LOD2_4959460`; XY와 ID만 읽음 |

이 64단위는 과거 높이 진단의 prior 64그룹과 다르다. 점 소속을 2 m 셀로 묶어도 여러 높이·방향의 patch를 평균하지 않는다. `sources[source].patches`와 원점의 patch ID를 유지한다. A/B는 부적격 단위를 다른 좋은 단위로 대체하지 않고 이 64분모에 제외·유보·미산출 이유를 남긴다. 명목 격자 면적은 확인된 현재 표면 면적이 아니다. UAS 점이 있다는 사실도 모든 방향의 면 피복이나 참조 정확도 보증이 아니다.

## 입력 인터페이스

컨테이너 root는 `/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v1/PHD-P2-AB-COMMON-v2`다. 호스트는 같은 상대 경로를 `../JointBuildGS-artifacts` 아래에서 찾는다.

| 경로 | 내용·역할 |
|---|---|
| `common/sample_manifest.json` | domain/frame/전체 입력 해시/raw lineage/분모 |
| `common/units.json` | `units`, `pilot_unit_indices`, `pilot_unit_ids`; 각 단위 bbox·소스 점수·patch별 층 정보 |
| `common/units.npz` | `mvs_xyz`, `mvs_tile_rows`, `mvs_patch_id`, `mvs_unit_index`, `mvs_normals`, `mvs_patch_type`, `mvs_original_row`, `mvs_original_file_index`; ALS는 동일 키의 `als_` 접두어 |
| `common/views.json` | `views[]`: `image_id`, `camera_id`, `role`, `name`, `path`, `sha256`, `K`, `R`, `t`, `width`, `height` |
| `common/frame_audit.json` | 실제 원자료 CRS, 현재 비교 좌표·수직 보정, 기존 gravity의 분리 계보 |
| `common/sample_audit_receipt.json` | 입력·역할 검증, 코드·설정·이미지 해시와 실제 검사 결과 |
| `evaluation_v2/evaluation_reference.npz` | root 평가 전용: `uas_xyz`, `uas_original_rows`, `uas_classification`, `uas_unit_index` |
| `evaluation_v2/reference_manifest.json` | 평가전용 파일·VLR·좌표·단위별 점수·참조 정확도 미정 상태 |
| `evaluation_v2/shared_groundsurface_xy.geojson` | 기존 공통 통제 XY/ID와 교차 관계; RoofSurface·Z 읽지 않음 |

`source_original_file_index`는 `sample_manifest.source_lineage[source].raw_files`의 인덱스다. NPZ의 XYZ는 모두 동일 scene-local 좌표다. `role=decision`만 A의 새 판단 관측에, `train`만 B의 적합에, `appearance_eval`만 별도 외관 진단에 사용한다. 평가 UAS는 후보 생성·정합·판단·문턱 조정·재구성 입력에서 제외한다.

66뷰는 모두 과거 개발에 사용되었다. 또한 MVS 후보와 카메라는 전체 exact-937을 공유한다. 이번 역할 분리는 새 반복에서의 정보 흐름을 제한하며 독립 확증·일반화 자료를 만들지 않는다.

## 좌표·수직 보정과 gravity

원 UAS LAS VLR는 `EPSG:32632`를 명시한다. 기존 source ancestry도 camera/MVS scene source를 `EPSG:32632`로 기록한다. 따라서 native MVS와 UAS의 같은 수치 scene-local 좌표에서의 상대 오차는 기존 georeferencing 계약에 조건부인 개발 진단으로 읽을 수 있다. 서로 다른 EPSG 이름만으로 이 내부 비교 전체를 무효로 하지는 않는다.

Existing ALS는 공급자 선언 `EPSG:25832 / DHHN2016`이고, partition 생성 시 **Z +45.7 m를 적용한 뒤 world shift를 이미 뺐다.** 이번 샘플은 추가 보정을 0으로 고정했다. UAS는 raw XYZ에서 world shift만 빼고 +45.7 m를 적용하지 않았다. UAS header의 vertical CRS는 확정되어 있지 않으며, ellipsoidal이라는 표현은 후속 프로젝트의 동일 취득·카메라 frame 사용 계약에서 온다. 절대 datum·epoch·측량 오차가 보정되었다고 주장하지 않는다.

기존 Gate S0에는 WGS84 UTM32 역변환 → GRS80 UTM32 정변환의 고정 투영 연산이 있다. 역사 PROJ 교차검사의 최대 구현 잔차는 0.000231 m이며, 이번 P2 네 모서리에서 같은 구현의 수치 변위는 최대 0.000167465 m다. **투영 연산의 수치 차이와 실제 datum/epoch 불확실성은 다른 항목**이다. 이번 candidate·UAS 배열에는 이 변환이나 평가 참조 기반 정합을 추가 적용하지 않았다. 실제 참조 정확도와 datum/epoch 오차는 `null`이다.

기존 terrain MVS normals 8,013개에서 한 번 추정한 gravity `[0.0022003022295437485,-0.0038866451918428023,-0.9999900262798882]`를 정확 checkpoint와 해시로 연결했다. `hardcoded_gravity=false`다. 이 checkpoint의 역사 dense 입력은 43,942,554점으로 현재 recovered MVS 43,926,567점과 다르므로 이번 원점에서 재추정한 값으로 부르지 않는다. Scene Z 방향의 높이 민감도 시험도 중력 추정 자체와 구분한다.

정본 연결은 [공통 manifest](../../../../artifacts/manifests/phd/p2_ab_v1/sample_common_manifest_v2.json), [frame audit](../../../../artifacts/manifests/phd/p2_ab_v1/sample_frame_audit_v1.json), [검증 receipt](../../../../artifacts/manifests/phd/p2_ab_v1/sample_audit_receipt_v1.json)에 있다.

## 실행과 보존

구현은 [sample_build.py](../../../../scripts/phd/p2_ab_v1/sample_build.py), [sample_audit.py](../../../../scripts/phd/p2_ab_v1/sample_audit.py)다. `jointbuildgs:dev` image ID `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`의 Python 3.11/NumPy/laspy로 실행했다. 공통 준비와 참조 준비는 CPU 작업이며 B용 GPU 1은 준비 시점 RTX 3090 24 GB, 사용량 91 MiB였다.

새 빈 namespace에 동일 저장소·artifact mount를 제공한 Docker에서 실행 순서는 다음과 같다. 이미 사용한 namespace에는 `exist_ok=False`로 중단한다. 실제 재실행 방지 검사는 `FileExistsError`, 종료 1을 반환했으며 기존 payload는 보존되었다.

```bash
python -m scripts.phd.p2_ab_v1.sample_build common --config configs/phd/p2_ab_v1/sample_recovery_v2.json
python -m scripts.phd.p2_ab_v1.sample_build evaluation --config configs/phd/p2_ab_v1/sample_evaluation_recovery_v3.json
python -m scripts.phd.p2_ab_v1.sample_audit
```

첫 common v1의 Docker git ownership 실패와 첫 evaluation의 optional pyproj parse 실패는 [이슈 기록](SAMPLE_ISSUES_ko_v1.md)에 남겼다. 각각 partial namespace를 보존한 새 출력에서 해결했다. 기존 과학 payload·기존 개발 결과·작업 트리 수정 사항은 변경·stage·commit하지 않았다. 새 sample 두 namespace의 파일 소유자만 원 사용자 uid/gid 1000으로 복원했다.
