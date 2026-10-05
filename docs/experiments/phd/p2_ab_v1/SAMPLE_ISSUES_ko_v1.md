# 공통 P2 샘플 이슈 기록

`scientific_verdict: null`. 기존 산출물은 보존했다.

| ID | 문제 → 원인 | 조치 → 해결 여부 | 남은 한계 |
|---|---|---|---|
| SAMPLE-I01 | common v1 마지막 commit 기록 실패 → Docker root와 repo uid의 git dubious ownership | 명령 한 번에만 exact repo `safe.directory` 지정, 새 common v2 전체 생성·검증 PASS. partial v1와 `FAILED.json` 보존 | v1은 최종 manifest가 없어 후속 입력으로 사용하지 않음 |
| SAMPLE-I02 | evaluation v1 raw header에서 중단 → `laspy.parse_crs()`가 설치되지 않은 optional pyproj를 요구 | raw GeoTIFF VLR·WKT를 직접 기록, 새 `evaluation_v2`에서 원점 177,981,904개 streaming 완료. 최초 STARTED와 FAILED 보존 | UAS source EPSG32632와 project 작업명25832를 구분, vertical VLR·실제 정확도 미확정 |
| SAMPLE-I03 | 동일 데이터의 과거 다양한 frame 명칭 → source/native frame와 registry 작업명 혼용 가능 | `frame_audit.json`에 camera/MVS/UAS32632, ALS25832, 이미 적용한 +45.7, local shift, 고정 투영 연산과 gravity를 계보별 기록 | datum·epoch와 registration metric uncertainty 미교정; 내부 오차는 기존 georef bridge 조건부 |
| SAMPLE-I04 | 점 지지·관측 재사용을 넓은 성공/독립검증으로 해석할 위험 | 전체552/새pilot64/과거64그룹 구분, 원층 소속 보존, frozen66을 22/33/11로 역할 분리 | 전체66 및 exact937 MVS는 개발 재사용; 공통 격자 면적은 검정된 표면 면적 아님 |
| SAMPLE-CHECK01 | 이미 존재하는 common v2 재실행 차단 확인 | `FileExistsError` 종료1, 새 입력 읽기·출력 쓰기 이전 중단 → 기대 동작 PASS | 재현 시 별도 새 namespace config가 필요 |

파일 소유자 보정 중 첫 host `FAILED.json` 작성은 root-owned 새 출력에 대한 `Permission denied`로 실패했다. 동일 파일을 Docker에서 새로 작성하고 이번에 만든 sample namespace 두 개만 uid/gid 1000으로 복원했다. 기존 payload의 권한은 변경하지 않았다.
