# PHD-MAIN-WIDEN0-v2 자료 안내

전체 범위의 측정과 시험 자리 목록을 만드는 작업이다. 학습은 실행하지 않는다. `scientific_verdict: null`.

- 발주와 τ 결정: [발주문](발주문_v2.md), `configs/phd/main_widen0_v2/widen0_v2.json`. LoD2 τ는 사용자 답변으로 지붕·벽 모두 0.20 m이며, 과거 τ·결과는 그대로 보존한다.
- 최초 입력·범위 보고: [중간 보고](중간보고_v1.md). 최초 PARTIAL 기록과 MVS 이후 보완을 구별한다.
- 진행 및 실패 기록: [progress.md](progress.md), [issues.md](issues.md).
- 최종 보고: [본실험 넓히기 0단계 보고 v2](본실험_넓히기0단계_보고_v2.md). 표는 `tables/`, 그림은 `figures/`에 있다.

## 저장 경로와 실행 환경

외부 작업 경로는 `JointBuildGS-artifacts/phase-payloads/phd/main_widen0_v2/PHD-MAIN-WIDEN0-v2/`다. 컨테이너에서는 이 경로를 `/out`, 이 문서 폴더를 `/docs`, 설정 폴더를 `/cfg`로 사용한다. 저장소 `/repo`와 전체 외부 자료 `/art`는 읽기 전용이다.

CPU 실행기는 `scripts/phd/main_widen0_v2/run_cpu.sh <로그 이름> <스크립트.py>`이며 `jointbuildgs:dev` 이미지, nice 19, 컨테이너 전체 32 GiB 한도를 사용한다. 이미지의 실제 ID·각 실행의 코드 SHA-256·설정 SHA-256은 실행 영수증에 남긴다. MVS는 별도 `run_mvs.sh`와 고정 COLMAP 이미지로 실행했다.

## 이 실행의 자료 흐름

| 처리 | 스크립트 | 기록 |
|---|---|---|
| 입력·범위·건물/영상 나눔 | preflight, scope_split, image_inventory, colmap_subset | 입력 표, 잠금 해시, `/out/inputs`, `/out/building_split.json`, `/out/image_split.json` |
| 원자료 구역화와 사전 정보 | tile_points, prior_tiles, gt_points, tile_views | 원본 점·면 출처, 구역별 중간 자료 |
| MVS | run_mvs.sh, mvs_outputs | `/out/mvs/full/colmap_receipt.json`, 깊이별 해시 |
| 깊이 점 복원 | mvs_points | `/out/holdout/internal/points`, 점 준비 영수증 |
| 정합·측정 | register_geometry, measure_all, u_worker, export_values | 구역별 정합·실행 영수증, 나눔별 패치값 |
| 표·그림·과거 비교 | run_reports | 표, 그림, 사진, 수치 검사 영수증 |
| 그림 검토 뒤 표시 보완·사진 검증 | finish_reports, validate_photo_crops | 빈 분포 축 보완 전후 수치 동일성, 원본 해상도·화소 비교 |
| 전달 묶음 | package | 파일별 SHA256SUMS, ZIP 안 파일 해시 검사, `/out/handover_manifest.json` |

`after_mvs.py`의 첫 실행은 원본 추가 패치의 0 법선 검사에서 중단됐다. `resume_measurements.py`로 정합부터 재개했고 완료된 MVS와 점 자료는 다시 만들지 않았다. 첫 실패의 정확한 단계 경과 시간은 저장되지 않았다. 실패 종료 코드·로그와 재개 시간은 보존했다.

`u_core.py`는 앞 UNCERT 수치 코어와 같은 바이트다. 원본 작은 면의 추가 패치는 삭제하거나 법선을 채우지 않는다. 이번 출력은 `source_extra`, `normal_defined`로 그 상태를 기록한다. 사진의 표시용 사각형은 수치 패치 면적을 대체하지 않는다.

## 나눔과 전달

정하는 곳의 패치값은 `/out/patch_values/`에 있다. 확인용 값·칸·자리 목록과 봉인 ZIP은 `/out/holdout/` 안에만 있다. 공개 표는 확인용의 허용된 수·넓이·참값 비율과 파일 해시만 싣는다.

light ZIP에는 문서·표·그림·설정·스크립트가, full ZIP에는 이에 더해 정하는 곳의 패치값이 들어간다. 두 ZIP 모두 확인용 자료를 제외한다. 그림 확인 기록과 수치 검사 PASS가 있어야 묶음 생성기가 실행된다.

대표 자리는 세 칸에서 각각 20곳을 선정했다. 실제 원본 사진은 54곳이며, 나머지 6곳은 전체 덩어리·여백의 연직 영상 투영 조건을 만족하는 영상을 확인하지 못했다. 선정 목록은 바꾸지 않았고 모음 그림과 보고서에 확인 불가를 표시했다.

최종 점검은 [보내기 전 점검](보내기전_점검.md)에 있다. 외부 작업 폴더의 `PHD-MAIN-WIDEN0-v2_handover_light.zip`과 `PHD-MAIN-WIDEN0-v2_handover.zip`이 전달 파일이며, 최종 해시·크기·내부 파일 검증 결과는 같은 폴더의 `handover_manifest.json`·`SHA256SUMS`에서 확인한다.
