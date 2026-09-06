# P2 연속 원점·원본 영상 공통 입력 감사

2026-09-07. `PHD-P2-AB-V2-COMMON-v1` 및 독립 재검사
`PHD-P2-AB-V2-COMMON-AUDIT-v1`. 비확증 개발, `scientific_verdict: null`.

P2 전체 원점과 원본 영상에서 직접 만든 crop을 새로 동결했다. 기존 v1의 작은
후보를 그대로 재사용하며 재구성의 세부 자유도를 닫는 제약을 제거하기 위한 입력이다.
이는 어떤 prior의 현재 사용 가능성이나 재구성 방법의 효과를 승인하는 결과가 아니다.

## 1. 확인한 원인과 조치

| 항목 | 실제 확인 | 새 공통 입력 |
|---|---|---|
| 원본 RGB | 추출 원본 `Images/`에 5280×3956 JPG 보존; 66개 모두 Gate S0 member SHA256 일치 | 원본을 직접 읽어 왜곡 제거와 crop 수행 |
| v1 RGB | `colmap_dense/images/`는 1400×1013, focal 약 922 px | 원본 focal 약 3717 px 유지; 저해상도 JPG 확대 없음 |
| 카메라 | 원본 FULL_OPENCV 937개와 dense PINHOLE 937개의 image ID·이름·회전·이동이 모두 정확히 동일 | 자세 고정, 원본 FULL_OPENCV→PINHOLE 직접 remap |
| v1 추가 축소 | B 저장 학습뷰의 crop 축척 중앙 1.0, 최소 약 0.395 | 공통 PNG는 resize 없음; B가 추가 축소하면 별도 기록 |
| 실제 투영 배율 | 새 focal / v1 B 저장 학습뷰 focal 중앙 약 4.03, 최대 약 10.21 | 2 m 후보와 시점에 따른 투영 축소는 여전히 존재 |
| 깊이·법선 | geometric map 실제 헤더는 모두 1024×741; normal은 3채널 | 원자료 경로·해시·해상도를 별도 제공. 고해상도 깊이로 재명명하지 않음 |

원본 RGB의 해상도 손실은 확인된 원인이다. 작은 후보 범위와 비스듬한 시점도
투영 면적을 제한한다. 이 감사만으로 영상 잔차나 최적화 거부의 원인을 모두
해상도로 확정하지 않는다. 원본 왜곡 제거도 원 JPG의 재표본화이며 새로운 관측을
만들지 않는다. 원래 촬영에 없는 세부, 가려진 면, 공동 카메라 오차는 복구하지 않는다.

## 2. 공통 계약

컨테이너 root:
`/artifacts/JointBuildGS/phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-COMMON-v1/`.
호스트는 저장소 형제 `../JointBuildGS-artifacts` 아래 동일 상대경로다.

| 파일 | 계약 |
|---|---|
| `sample_manifest.json` | 입력·출력 해시, 카메라·원자료 계보, 환경, 기존 gravity, frame, 분모 |
| `native_geometry.npz` | 전체 native MVS 330,679점, ALS 45,986점; 기존 `units.npz`와 바이트 동일 |
| `units.json` | 552개 2 m XY 단위 ID. v1의 pilot 표시가 역사 메타데이터로 남지만 새 manifest의 `pilot_unit_indices=null`; B의 선택 제한으로 사용하지 않음 |
| `views.json` | 기존 역할·ID와 새 PNG path, K/R/t, 크기, 원본 해시, crop 좌표, mask 및 기존 geometric map |
| `images/<image_id>.png` | 원본에서 직접 만든 PINHOLE crop. 66개 합계 164.228391 MP, 크기 중앙 1028×618, 축별 최대 3540×3868 px |
| `valid/<image_id>.png` | 원본의 bilinear 표본 범위가 유효하면 255, 아니면 0. 이번 66 crop은 모두 100% 유효 |
| `projection_audit.json` | 원본 해시·937 자세 검사, 각 소스 투영 범위, 0.1 m 축 변위의 픽셀 크기, remap 검산 |
| `frame_audit.json` | v1에서 검증한 좌표·수직 보정·gravity 계보를 그대로 보존 |
| `source_snapshot/` | 실제 실행 source와 config |

`native_geometry.npz`의 소스별 키는 `mvs_*`, `als_*`이며 `xyz`, `tile_rows`,
`patch_id`, `unit_index`, `normals`, `patch_type`, `original_row`,
`original_file_index`를 제공한다. 원행 ID 쌍은 모든 점에서 유일하다. MVS의
native patch ID는 908개, ALS는 292개이며 이 수는 저장된 ID 종류 수다.
모든 ID가 평면·현재성·면 지지에 적격이라는 뜻이 아니다. 지상·지붕·다층 원점을
같은 높이로 합치지 않고 소스별 native Z와 patch 소속을 보존한다.

범위는 기존 scene-local prism `x[110,158), y[86,132), z[-49.386,-17.679)`다.
source-only 투영의 양의 깊이 점 전체 bbox에 24 px를 더하고 원본 크기의 PINHOLE
canvas로 자른다. crop의 빈 공간도 남으므로 bbox 자체가 관측된 표면 mask는 아니다.
새 crop·표면·뷰 선정에 UAS나 LoD2를 읽지 않았다.

기존 22 decision / 33 train / 11 appearance_eval ID 역할을 유지한다. 전체 66개가
역사적으로 개발에 쓰였고 MVS는 모든 역할을 포함하는 exact937에 의존한다. 역할은
이번 최적화의 분리일 뿐 독립 확증 관측이 아니다.

## 3. 카메라와 map 사용 규칙

새 RGB PNG는 PINHOLE이며 `views.json`의 `K`가 **새 crop 좌표**다. 원본의
FULL_OPENCV 왜곡 계수를 새 PNG에 다시 적용하지 않는다. `R,t`는 기존과 동일하다.
추가 crop 또는 resize를 할 경우 principal point와 두 행의 축척을 함께 변환한다.

기존 depth/normal은 **새 RGB와 좌표가 다르다**. 기존 RGB는 1400×1013이고
실제 map은 1024×741이므로, `low_resolution_derivative.K`의 첫 행에 `1024/1400`,
둘째 행에 `741/1013`을 적용한 map K를 사용한다. 새 crop K를 그대로 복사하면
틀린 투영이다. 해당 map의 검증된 관례를 따르는 보간과 결측 mask도 필요하다.
COLMAP normal은 camera frame이다. world frame 변환은
`src/stage2/dataloader.py`의 기존 변환 관례와 일치시킨다.

map의 geometry는 원래 해상도로 남는다. RGB 해상도 회복이 MVS depth/normal의
해상도를 높이거나 후보 MVS에 대한 독립 감독을 만드는 것은 아니다. A가 기각한
MVS를 해당 영역의 honest prior 재구성 감독으로 되돌려 쓰는 승인도 아니다.

## 4. 좌표·참조 경계

원점은 기존 scene-local 수치 그대로다. world shift `[690953,5336071,604] m`,
프로젝트 수평 표기는 EPSG:25832다. camera/MVS 원 출처의 EPSG:32632, UAS 원 VLR의
EPSG:32632, ALS provider의 EPSG:25832/DHHN2016와 동결 수치 연결 관계는
복사한 `frame_audit.json`을 따른다. source datum/epoch의 미보정 불확실성과 작은
수치 투영 차이를 혼동하지 않는다. 새 정합·수평 변환·참조 적합은 하지 않았다.
ALS에는 기존 partition의 `raw Z +45.7 −604`가 이미 반영돼 있어 추가 보정은 0이다.

gravity는 기존 Gate S0의 terrain MVS 추정 checkpoint를 인용한다. 이번 recovered
MVS로 다시 추정한 값이라고 주장하지 않으며 hardcode로 새 축을 정하지 않았다.
UAS/LoD2는 기존 별도 evaluation payload에 남아 있고 이 builder/auditor는 읽지 않는다.

## 5. 실행·재검사·보존

- producer: [sample_build.py](../../../../scripts/phd/p2_ab_v2/sample_build.py),
  [sample_native_v1.json](../../../../configs/phd/p2_ab_v2/sample_native_v1.json).
- independent recheck: [sample_audit.py](../../../../scripts/phd/p2_ab_v2/sample_audit.py),
  [sample_audit_v1.json](../../../../configs/phd/p2_ab_v2/sample_audit_v1.json).
- Docker `jointbuildgs:dev`, image ID
  `sha256:251f83c17879a83b0c3dda5b9d71cbf45ca72cc0fdcbc89994194dc3edb86774`,
  UID/GID 1000, network none, repository read-only, NumPy/OpenCV container execution.
- `python -m scripts.phd.p2_ab_v2.sample_build --config configs/phd/p2_ab_v2/sample_native_v1.json`
  와 같은 방식으로 auditor를 실행했다. 모든 환경·config·source 해시는 receipt에 있다.
- 모든 동결 입력·출력 SHA를 다시 검사했다. 원본 66 JPG, native payload, 역할,
  출력 66 PNG와 binary mask, 유일한 원행 ID가 통과했다. remap을 별도 rational
  point projection과 비교한 최대 절대 오차는 `0.0002440223 px`였다.
- 재검사 receipt:
  `phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-COMMON-AUDIT-v1/audit_receipt.json`.
- 기존 출력·source·원본 JPG를 수정하지 않았다. 새 output directory가 이미 있으면
  실행은 실패하며 덮어쓰지 않는다. 이번 producer와 auditor 실행은 정상 종료했다.

이 결과는 연속 입력과 실제 원본 영상의 가용성을 확인한다. 세부 기하·외관의 개선,
구조 보존, 오채택·유보와 지지되지 않은 영역 확장 여부는 A/B/C에서 별도로 검증한다.
