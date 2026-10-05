# 관측 점수 walkthrough v3.2 예외·검증 기록

scientific_verdict: null. 기존 main_v2 실험 이슈와 별도인 추가 진단의 기록이다.

- 첫6개 위치 계산 attempt_20260911T093434Z_aQDboL을 보존했다. stdout execute.log가 실행 종료 시 계속 기록되므로 최초 출력 hash 목록에 들어간 당시 hash와 최종 log bytes가 달라질 수 있었다. 두 번째 attempt에서는 live stdout log를 봉인 목록에서 제외하고 이 경계를 기록했다. 수치/입력 문제로 해석하지 않는다.
- MVS 결손도 볼 수 있도록 원래6개 위치와 독립적인 격자 strata를 추가하여 새8개 위치 attempt를 생성했다. 첫 결과를 덮어쓰지 않았다.
- 게시 파일 생성의 orchestration JavaScript에서 BASH_SOURCE 변수를 template literal로 해석해 ReferenceError가 한 번 발생했다. 해당 파일 생성/프로젝트 실행 이전에 거부되었다. 쉘 텍스트를 literal 문자열 배열로 전달하여 수정했다.
- 게시기와 producer receipt의 PASS 명칭 차이는 게시 전 검토에서 발견해 정확한 PASS_INTERNAL_FIT_DIAGNOSTIC에 맞췄다. 잘못된 상태를 가진 packet을 게시한 것은 아니다.
- MVS 과거 producer Docker image는 현재 없어 exact binary를 확인하지 못했다. 기록된 COLMAP4.0.4 공식 커널의 정수 ray와 K scaling을 근거로 진단했으며 exact producer와 half-pixel 민감도는 미검증으로 유지했다.
- P1 일부 기준 패치와 이웃 재투영 패치의 모습이 크게 다르다. 결과를 삭제/재선정하지 않고 전체 사진·mask·가시성 unknown으로 보존한다. 입력 카메라 규약 추가 감사와 별도 visibility 검증을 구분한다.
- 첫 packet `packet_photometry_v3_2_20260911T094155_794901Z`의 기계 검사는 4,321개 PASS였으나 모바일 점수표 사진명이 과도하게 줄바꿈되는 육안 문제가 있었다. 표 최소 폭과 사진명 줄바꿈 규칙을 고치고 새 packet을 만들었다. 기존 packet과 `browser_qa/attempt_20260911T094337Z_mQ8HDB`의 NEEDS_MOBILE_SCORE_TABLE_REVISION 기록을 보존했다.
- 두 번째 packet `packet_photometry_v3_2_20260911T094533_720421Z`의 4,409개 검사와 모바일 표는 통과했으나, 확대창이 9×9 패치를 원래 9픽셀 크기로 표시했다. 확대창에 실제 표시 폭을 지정했다. 기존 packet과 `browser_qa/attempt_20260911T094651Z_4Odocj`의 육안 실패 기록을 보존했다.
- 최종 packet `packet_photometry_v3_2_20260911T094838_338420Z`는 `browser_qa/attempt_20260911T095151Z_X0a8kG`에서 4,411개 검사, 500개 화면 상태, 801개 HTTP 자료 해시 확인을 통과했다. 작은 패치 확대와 모바일 표 오른쪽 수치/버튼까지 육안 확인했다. 위 두 화면 문제는 해결됐으며, 해당 검사 중 기존 current.json 해시는 동일했다.
- 추가 카메라 감사 `camera_audit/attempt_20260911T095004Z_Wgh5fA`는 원 COLMAP K/R/t와 입력 카메라의 일치 및 10개 사진의 SfM 2,000관측 재투영을 확인했다. 카메라 규약 오류의 증거는 없었다. 이 결과가 후보 depth 정확성이나 P1의 가림 문제를 해결한 것은 아니며 visibility unknown을 유지한다.
- 사용자 열람에서 패치 선정/크기, 흰색 mask, MVS 결손 때 Prior까지 테두리가 없는 이유, P2 3/6장 지원의 의미가 불명확했다. 수치 오류와 구분한 설명/사용성 문제다. `WALKTHROUGH_READING_ko_v3_2_2.md` 및 새 packet에 실제 source별 표본·좌표·선정 조건·범례를 추가했다. 공통 표본이 없는 비교의 최초 이웃은 어느 한 source라도 RGB 조회 가능한 첫 이웃으로 보여준다. 원 depth·점수·PNG·기존 packet은 보존한다.
