# 비정형 마스크 계산 실행 기록

`PHD-IRREGULAR-SOURCE-MASKS-v1` · 2026-09-15 · `scientific_verdict: null`

2026-09-15 01:42:34 UTC에 새 CPU 백그라운드 계산을 시작했다. 이 기록은
실행 시작 기록이며 전체 마스크 완성 또는 영역 정확도 입증을 뜻하지 않는다.

- 실행: `attempt_20260915T014234Z_NtoOoy`
- 외부 경로: `../JointBuildGS-artifacts/phase-payloads/phd/irregular_source_masks_v1/PHD-IRREGULAR-SOURCE-MASKS-v1/attempt_20260915T014234Z_NtoOoy`
- service: `jbgs-irregular-masks-attempt_20260915t014234z_ntoooy.service`
- 계산 컨테이너: `jbgs-irregular-attempt_20260915t014234z_ntoooy`
- 자원 상한: CPU 4개, RAM 16GiB, GPU 없음
- 웹: <http://127.0.0.1:8911/report/>

동결한 source snapshot의 10개 수치·판정 테스트가 통과한 뒤 실제 입력 계산에
진입했다. `numerical_validation.json`과 `.log`에 결과를 남겼다. 원픽셀 판정의
사각형 전파 없음, 소스 교환 대칭성, 결측·깊이 검색 간격·동률 처리, 반대 관측
집계와 기존 비용 계산의 수치 일치를 검사했다. 이 검사는 실제 마스크 정확도의
평가가 아니다.

9개 원영상은 각 1400×1013 픽셀이다. 전체 깊이차를 계산하고, 기존 고정 지역의
XY 투영 범위에 들어오는 불일치 픽셀 각각을 검사한다. 첫 P1 영상은 해당 후보
8,478픽셀을 모두 관측 검사했고, 148픽셀에서 깊이 비용곡선을 검사했다.
그 영상의 최종 MVS/Prior 지지 후보는 모두 0이며 8,478픽셀은 유보다.
이를 변화 없음 또는 정확한 유보라고 주장하지 않는다.

진행 상황은 `status.txt`, `run.log`, service 및 컨테이너 상태를 함께 확인한다.
`evidence/data.json`과 영상별 `camera.json`은 계산 중 현재 자료를 표시한다.
모든 카메라 완료 및 최종 입력 재해시 후 `evidence/receipt.json`이 생성된다.
완료 전 픽셀은 `UNASSESSED`, 두 깊이 모두 결측이면 `NO_SOURCE_XY_ROI_UNKNOWN`으로
표시한다. 표본 단위 디버그 저장 배열의 미검사 0은 `photo_examined=false`와 함께
읽어야 하며, 실제 검사에서 지지 0개인 것과 구분한다.

기존 GeoGS MVS/PGSR 학습과 13패치 소스 교체 실험은 변경하지 않았다. 새 계산은
마스크 추출만 수행하며 Gaussian 연결·수정은 수행하지 않는다. 이후 이를 GS에
적용한 비교는 해당 마스크 계보를 명시해야 한다.

소스/config 원본과 SHA 목록, 기준 Git commit, 입력·출력 해시는 attempt에 남긴다.
실행은 사용자 systemd 서비스이며 linger가 활성화되어 있다. 화면의 15초 갱신은
저장된 진행 상황을 읽는 기능이고 대화 알림을 예약한 것이 아니다.

## 최초 데스크탑 검토 시점

P1의 세 영상 계산이 완료됐으며 각각 8,478 / 23,956 / 37,718개 불일치 픽셀이
모두 유보됐다. 최종 MVS/Prior 지지 후보는 0이다. P2는 계산 중, P3는 대기 상태였다.
이 스냅샷 이후 진행은 live 상태 파일을 기준으로 한다.

`qa_mask_preview/receipt.json`은 당시 이용 가능한 자료에 대한 실제 Chromium
검사 `PASS_ACTUAL_BROWSER_PARTIAL_DATA`를 기록했다. 700개 검사, 154개 화면 상태,
9개 브라우저/API 픽셀 조회를 확인했다. `qa_retry_browser_only/numeric_api_validation.json`
은 완료된 P1 영상 두 개의 ROI 표본 6개에 대해 NPZ의 원 수치와 API 응답의 일치를
검사했다. 이는 표시·수치 전달 검증이며 마스크 선택 정확도 검증이 아니다.
초기 QA 도구 실패와 복구는 [이슈 기록](ISSUES_ko_v1.md)에 보존했다.
