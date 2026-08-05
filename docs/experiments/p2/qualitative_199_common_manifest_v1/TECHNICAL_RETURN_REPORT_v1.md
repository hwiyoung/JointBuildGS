# 199동 6행 공통 camera/view/crop manifest v1 기술 Return

- task: `P2-QUALITATIVE-199-COMMON-MANIFEST-v1`
- decision: `DEC-P1-018`
- artifact: `artifact://JointBuildGS/phase-payloads/p2/qualitative_199_common_manifest_v1/P2-QUALITATIVE-199-COMMON-MANIFEST-v1`
- technical state: `COMPLETE_WITH_RETAINED_DIAGNOSTIC_MISSINGNESS`
- scientific_verdict: `null`

## 동결된 dense 계보

새 6행 결과에서 MVS 관련 4·5·6행은 복구 실행에서 함께 나온 다음 pair만 공유한다.

- row 4 dense PLY: SHA-256
  `fc2561ab3e41adaa64a5cbc1f7a13c5f887999d2d81f94d4dca082c2c43c02ce`,
  finite point `43,926,567`
- row 5 MVS Roofer: row 4 exact PLY의 새 class-2/6 derivative에서 다시 생성해야 한다.
- row 6 native textured mesh: SHA-256
  `bc533e1eb642513c080742d11ac7e58d828718b87132ba95b7e95ddcd2659c31`인
  paired MVS scene에서 생성해야 한다.

과거 C2 dense PLY, 그 PLY의 Roofer 결과·metric, display-only textured Roofer는
이 manifest의 새 6행 결과 source가 아니다. 원본은 삭제하지 않고 역사적 산출물로
보존한다.

## 199동 공통 manifest 결과

- 199동을 모두 유지했다.
- 건물마다 `TOP`, `OBLIQUE_1`, `OBLIQUE_2`, `PRINCIPAL_SECTION` 역할에 서로 다른
  current-image camera 4개를 선택하여 총 796개 camera/view row를 만들었다.
- camera와 crop 선택에는 건물 identity/display bbox와 새 current-image MVS dense
  support만 사용했다.
- LoD2 roof boundary는 camera와 crop을 고정한 뒤 투영 진단만 계산했으며,
  `used_for_camera_or_crop_selection=false`를 796개 row 모두에서 검증했다.
- source camera, image/pose, exact-937 crosswalk, scene frame, U_target metric roster,
  LoD2 reference, recovered dense PLY/MVS와 recovery receipt를 hash로 결합했다.

## 보존된 missingness와 진단

건물 주변 viewport에서 새 dense 점을 20개 이상 찾은 건물은 171동이다. 다음 28동은
그보다 적어서 카메라 선택용 Z prism에 새 dense 전체의 중앙 높이
`574.1877632141113 m`를 사용했다. 이 fallback도 동일한 새 dense source에서 나온 값이며,
건물을 삭제하거나 결과가 있는 것처럼 바꾸지 않았다.

`DEBY_LOD2_104583794`, `DEBY_LOD2_107802038`, `DEBY_LOD2_107807336`,
`DEBY_LOD2_42364607`, `DEBY_LOD2_4907000`, `DEBY_LOD2_4907011`,
`DEBY_LOD2_4907012`, `DEBY_LOD2_4907013`, `DEBY_LOD2_4907014`,
`DEBY_LOD2_4907015`, `DEBY_LOD2_4907029`, `DEBY_LOD2_4907030`,
`DEBY_LOD2_4907031`, `DEBY_LOD2_4907032`, `DEBY_LOD2_4907033`,
`DEBY_LOD2_4907035`, `DEBY_LOD2_4907036`, `DEBY_LOD2_4907156`,
`DEBY_LOD2_4908044`, `DEBY_LOD2_4908045`, `DEBY_LOD2_4908051`,
`DEBY_LOD2_4908052`, `DEBY_LOD2_4908053`, `DEBY_LOD2_4908054`,
`DEBY_LOD2_4908059`, `DEBY_LOD2_4908157`, `DEBY_LOD2_4908159`,
`DEBY_LOD2_8573617`.

사후 LoD2 roof-boundary 투영은 790개 row가 full, 2개가 partial, 4개가 not
projectable이었다. 비-full 6개 row는 다음과 같이 그대로 남겼다.

- `DEBY_LOD2_4907021 / OBLIQUE_1`: `ROOF_BOUNDARY_NOT_PROJECTABLE`
- `DEBY_LOD2_4907022 / OBLIQUE_2`: `PARTIAL_ROOF_BOUNDARY_PROJECTABLE`
- `DEBY_LOD2_4908164 / TOP`: `ROOF_BOUNDARY_NOT_PROJECTABLE`
- `DEBY_LOD2_4908164 / OBLIQUE_1`: `ROOF_BOUNDARY_NOT_PROJECTABLE`
- `DEBY_LOD2_4908164 / PRINCIPAL_SECTION`: `ROOF_BOUNDARY_NOT_PROJECTABLE`
- `DEBY_LOD2_4959460 / TOP`: `PARTIAL_ROOF_BOUNDARY_PROJECTABLE`

## 검증과 다음 경계

컨테이너 `jointbuildgs:dev`에서 계약 단위 테스트 3개를 통과했다. 생성 후 199동,
796개 view row, 건물별 4개 고유 camera, `scientific_verdict=null`, LoD2 비선택성,
runtime artifact manifest의 6개 record hash를 독립 재검증했고 실패는 0개였다.

이 task는 manifest만 생성했다. raw-image 첫 행 렌더링, outcome-free 3--5동 검토,
Roofer 재생성, native mesh 생성, 3D inspector와 최종 PNG/PDF/HTML은 실행하지 않았다.
다음 단계는 사람 승인 전까지 `next_stage_authorized=false`다.
