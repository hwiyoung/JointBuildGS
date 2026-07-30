# 42364609 A′ r1 readout 복구 관찰 보고

- 기술 상태: `COMPLETE`
- 실행 범위: `DEBY_LOD2_42364609 / Aprime / r1` 한 job
- 새 학습: `0`
- 다른 대기 job 실행: `0`
- 실행 HEAD: `38de83882c1dacb5491ea22050c453b594b345a9`
- 성공 readout: recovery `attempt_005`
- 과학 판정: 기록하지 않음

## 단계별 측정

| 단계 | 상태·측정 |
|---|---|
| 캐시 preflight | UID 1000, RTX 3090, `MAX_JOBS=2`, 기존 gsplat extension 재사용, 캐시 트리 전후 동일, `PermissionError` 0건 |
| TSDF/MC | raw 10,268 vertices / 17,773 triangles; filtered 9,931 vertices / 17,442 triangles; 61 components 중 58 제거 |
| 표면 샘플 | class 6 1,450점, 0.1 m 요청 간격, 표면적 14.499830 m² |
| Roofer 입력 | 총 9,094점 = class 6 1,450 + 원본 ALS class 2 7,644 |
| primary 조립 | LoD2 geometry 있음, LoD1 fallback 없음, CityJSON 생성, val3dity valid |
| primary 채점 | plane P/R/F1 = 1/1/1; roof RMS 0.132732 m; Hausdorff 0.259492 m; completeness 0.999715; face ratio 1; XY overlap 1 |
| P0 Ref-L 기록값 대비 | P0 RMS 0.090516 m; RMS delta +0.042216 m; completeness delta +0.000012621 |
| legacy alpha 비교 | 3,060점 전부 class 2, footprint 안 class 6=0; `NOT_ASSEMBLED`; Roofer 0회; 판정 비사용 |

## 예외 보존

- recovery attempt 004는 47개 파일·4,246,166 bytes·tree SHA `1be09fe5...d358` 상태로 고정했다.
- attempt 004에서는 두 score까지 생성된 뒤 `primary/engine/scores.csv.lock` 0-byte 파일을 artifact ledger가 거부해 finalize가 중단됐다. 권한 오류가 아니다.
- attempt 005에서는 scorer 종료 후 해당 동기화 파일의 비점유를 확인하고 recovery 격리 경로로 이동했다. 과학 산출물 이동 수는 0이다.
- attempt 005에는 실패 영수증이 없으며 job complete와 recovery complete 영수증이 발행됐다.

## 주요 산출물

- 완료 영수증: `completed.json` — SHA `9a2bfa64...ed8c6`
- TSDF 영수증: `readout/.../attempt_005/tsdf/tsdf_receipt.json`
- CityJSON: `readout/.../attempt_005/primary/engine/by_building/DEBY_LOD2_42364609/cityjson/seed_p0prime.city.json` — SHA `fd6f9c19...b1970`
- 상세 기계 판독 보고: `recovery_report.json`

## 이번에 실행하지 않은 20 jobs

`A′ r1의 다른 8동 + A′ r2의 9동 전부 + arm B r1의 3동 = 20 jobs`이다. 이 recovery에서 시작된 수는 0이다.
