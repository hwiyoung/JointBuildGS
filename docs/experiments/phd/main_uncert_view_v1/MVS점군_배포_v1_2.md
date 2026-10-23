# MVS 점군 표시 v1.2 배포 확인

기존 [웹주소](http://192.168.10.203:8912/)를 v1.2로 전환했다. 연구실 네트워크 또는 VPN에서 새로고침하면 기본 MVS 불확실도·실제 오차 지도가 실제 MVS 점군에 표시된다. 상단 ‘표시 형상’으로 기존 공통 사전 면/패치 보기와 전환할 수 있다. 형상과 색의 의미를 각 지도 위에 표시한다.

색은 연결 패치의 기존 통계다. 원본 MVS XYZ의 표시 표본에 색을 입혔으며, 개별 점의 불확실도·오차를 새로 추정하지 않았다. 차트의 원본 표본, 계산 방법, 수치 정밀도를 유지했다. [방법·제약·화면](MVS점군_표시_v1_2.md)

- [캡처·보고서 묶음 — 7,980,640 bytes, 약 8 MB](http://192.168.10.203:8912/downloads/PHD-MAIN-UNCERT-VIEW-v1.2_report_and_screens.zip)
- [전체 결과 묶음 — 395,317,778 bytes, 약 395 MB](http://192.168.10.203:8912/downloads/PHD-MAIN-UNCERT-VIEW-v1.2_results.zip)

두 묶음 모두 기존 캡처 37장과 이번 캡처 15장, 총 52장을 포함한다. 전체 묶음에는 웹 화면과 자료도 포함한다. ZIP은 배포 전 검증 시점의 기록이며, 실제 주소 배포·저장 완료 검증은 이 문서와 아래 별도 receipt에 기록했다. 이전 v1.1 묶음은 그대로 보존했다.

## 확인 결과

- 여섯 경우의 미리보기 360개 검사 통과: 고정 참조와 구간 통계 일치, MVS 판 전환, 실제 점 선택, 3D 보기, 기존 보기 전환, 필터, 좁은 화면.
- 실제 LAN 주소 화면 검사 65개, 네트워크 없는 오프라인 화면 검사 65개 통과.
- 실제 LAN 주소에서 Linux Chromium 152의 두 ZIP 다운로드가 `completed`로 끝났으며 저장 파일의 크기와 SHA-256이 모두 일치했다.
- 기존 v1.1 ZIP·설정 및 원래 `data/`, `sections/`, `faces/` 자료를 동결 ZIP과 대조했다. 상세 파일 목록과 서비스 정보는 [배포 기록](tables_v1_2/deployment.json)에 있다.
- v1.1 서비스 컨테이너는 `jbgs-main-uncert-view-8912-v11-downloads` 이름으로 중지하여 보존했다. 현재 서비스는 `jbgs-main-uncert-view-8912`이다.

Codex 앱 안의 다운로드가 끝에서 멈췄던 문제는 앱 자체에서 재검증하지 못했다. 서버의 전송·별도 Chromium 저장 성공을 Codex 앱 저장 성공으로 간주하지 않는다. 사용자는 외부 Chrome/Edge에서 위 링크를 직접 열어 받을 수 있다. Windows Chrome/Edge 자체의 실행 검증은 수행하지 않았다.

[실제 화면 검사](tables_v1_2/browser_live.json) · [오프라인 검사](tables_v1_2/browser_offline.json) · [다운로드 완료 기록](tables_v1_2/download_browser_live.json) · [다운로드 크기·해시](tables_v1_2/downloads.json)

scientific_verdict: null
