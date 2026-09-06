# P2 비교 viewer — 실제 브라우저 검사

Task: `PHD-P2-AB-VIEWER-QA-v1` · `scientific_verdict: null`

**최종 C-v2 viewer 실제 Chrome 검사 PASS.** 29개 arm, 양쪽 WebGL2, DN 11개 평가뷰의 사진·렌더, 전체 유보 표시와 390 px 모바일 배치를 확인했다. 처음 발견된 단위 맞춤 시점과 모바일 배치 문제는 소유 작업자가 수정했고 새 출력에서 재검증했다. 최초 산출물과 최초 screenshot은 보존했다.

## 실행 경계와 서버

- 새 컨테이너: `jbgs-p2-ab-inspector-8893`, ID `67ea41674ae08619237aae6033feb3c54d03a92fd6db9926f27fdef452ea818c`.
- `127.0.0.1:8893 → container 8080`. 기존 8891/8892 등 서버는 중지·변경하지 않았다.
- `jointbuildgs:dev`, user `1000:1000`, root filesystem read-only, `cap-drop ALL`, `no-new-privileges`.
- 새 `phase-payloads/phd/p2_ab_v1` parent만 `/srv:ro`로 mount하여 Python `http.server`로 제공한다. 최종 통합 결과도 같은 parent 아래 URL에서 읽는다.
- 실제 호스트 Chrome `146.0.7680.80`, 새 `/tmp/jbgs-p2-ab-viewer-qa.VvbqPo` 프로필, localhost DevTools 9227. 기존 사용자 프로필을 열지 않았다.
- Headless Chrome의 명시적 SwiftShader WebGL을 사용했다. 이는 브라우저 상호작용 검사이며 수치 프로젝트 도구는 Docker에서 실행한다. 새 호스트 패키지는 설치하지 않았다.

초기 URL: `http://127.0.0.1:8893/PHD-P2-AB-C-A-v1/viewer/`.

재현 드라이버는 [sample_browser_qa.mjs](../../../../scripts/phd/p2_ab_v1/sample_browser_qa.mjs)다. Node 표준 모듈과 Chrome DevTools만 사용한다. CLI는 URL과 **존재하지 않는 새 screenshot 디렉터리**를 받는다.

## 최초 실제 검사

| 검사 | 실제 관측 |
|---|---|
| 데이터 로드 | `P2_INSPECTOR_READY=true`, 552 고정 셀, 7 A arm, 553 unit 선택지 |
| 렌더러 | 두 canvas 모두 WebGL2 `OpenGL ES 3.0 Chromium`, desktop 651×440 px |
| 드래그 | pointer 입력 후 screenshot 내용 변경 확인; 두 panel이 같은 전역 시점을 사용함을 소스에서도 확인 |
| 단위 선택 | unit0/542 선택에 해당 ID·판단·참조 오차 표시 갱신 |
| 시점·참조 | 평면/사선/단면 버튼과 양쪽 UAS checkbox 동작, 오류 없이 화면 갱신 |
| 런타임 오류 | JavaScript exception 0, data/module HTTP 실패 0. 부수 `favicon.ico`만 HTTP404 |
| 문서 링크 | 통합 receipt·risk CSV·후보 metric JSON HTTP200 |
| 단위 맞춤 | **수정 필요**: unit0 사선에서는 원점이 화면 하단·밖으로 빠지고 평면에서는 보임. 공통 Z=-33.5와 단위 span5 고정 때문 |
| 점 크기 | 선택 단위의 `PointsMaterial.size=.06`이 subpixel이라 원점이 매우 희미함 |
| 모바일390 | **수정 필요**: clientWidth390, scrollWidth437. 결과 select가 화면 오른쪽을 넘고 label이 세로로 꺾임 |

초기 harness의 mobile `overflow` 필드는 `innerWidth`와 비교하여 false로 남았다. 실제 mobile auto-fit으로 innerWidth도437로 확장된 경우라 이 필드가 충분하지 않았다. 위 FAIL은 보존된 clientWidth390/scrollWidth437 및 실제 screenshot에서 확인했으며, 후속 harness는 clientWidth 비교로 수정했다.

소스 리뷰에서는 A fixed candidate arm에도 오른쪽 제목이 재구성 표면으로 표시되는 의미상 혼동을 추가로 전달했다. A arm은 고정 후보 지지, B arm은 재구성 초기·최종 산출물로 표시하는 것이 실제 계산과 맞는다.

근거 payload: `phase-payloads/phd/p2_ab_v1/PHD-P2-AB-VIEWER-QA-v1/baseline/`의 `browser_qa.json`, `desktop_before.png`, `desktop_dragged.png`, `unit0_oblique.png`, `unit0_top.png`, `unit542_oblique.png`, `unit542_section_with_reference.png`, `mobile_390.png`. 서버 실제 설정은 같은 QA root의 `server_inspect.json`에 있다. 후속 검사는 새 하위 디렉터리에 기록하며 이 최초 증거를 덮어쓰지 않는다.

## 수정 소스의 분리 preview 검사

원본 소유 작업자가 실제 단위 Z 범위에 따른 맞춤 시점, 선택점 2.8 px, 모바일 label/select 폭 제한, A/B 제목 구분 및 개발 범위 밖 안내를 수정했다. 이전 C-A/C-v1 출력은 덮어쓰지 않고 QA `preview_case_v1/viewer`에 C-v1 표시 자료와 수정 소스를 복사했다. 이 preview의 수치 자료는 C-v1에 속하며 최종 통합 산출물로 재명명하지 않는다.

실제 Chrome 재검사에서 다음을 확인했다.

- 단위0·542의 사선 화면에 실제 native 점군이 들어오며 점을 식별할 수 있다.
- 390 px에서 `scrollWidth=clientWidth=390`, overflow=false다.
- 27개 arm 모두 오류 없이 전환되며 A/B 제목이 실제 역할에 맞게 바뀐다.
- B의 target·initial·final 384×220 사진 3개가 실제 decode된다.
- 양쪽 WebGL2, 드래그, 단위 선택·단면·참조 checkbox가 동작한다. 새 network 실패와 JavaScript exception은 없다.

`fixed_preview/browser_qa.json`의 Log에는 앞선 baseline favicon404가 Chrome의 저장 로그로 한 번 전달되었다. timestamp와 networkFailures=[]로 과거 이벤트임을 구별했다. 최종 URL 검사는 Log.clear와 console reset 후 새로 수행한다.

수정 확인 캡처는 QA root `fixed_preview/unit0_oblique.png`, `fixed_preview/unit542_oblique.png`, `fixed_preview/mobile_390.png`, `fixed_preview/first_b_arm_desktop.png`다.

## 최종 C-v2 실제 검사 — PASS

최종 URL은 [P2 판단·재구성 비교](http://127.0.0.1:8893/PHD-P2-AB-C-v2/viewer/)다. 최종 데이터·HTML·JS를 그대로 검사했으며 preview 자료를 대신 사용하지 않았다.

| 최종 검사 | 확인 결과 |
|---|---|
| 전체 arm | 29/29 전환: A7 + B20 + DN1 + 전체 유보1 |
| 렌더·조작 | WebGL2 2개, 실제 드래그 화면 변화, unit0/542, 평면·사선·단면·UAS on/off PASS |
| 이미지 | B arm 첫 평가사진의 모든 표시 이미지 decode PASS; DN 평가뷰11개의 target·초기·최종 이미지 모두 decode PASS |
| 전체 유보 | `ABSTAIN_NO_GEOMETRY`, `reference_units=64`; UAS off의 우측은 빈 기하, UAS on은 평가 참조만 표시 |
| 모바일 | clientWidth390 = scrollWidth390, overflow=false |
| 오류 | Log 초기화 후 JavaScript/runtime/console 오류0, network 실패0 |
| 문서 URL | 최종 receipt·risk CSV·candidate metric JSON 모두 HTTP200 |

대표 캡처는 QA root `final_combined/first_b_arm_desktop.png`, `final_combined/dn_images.png`, `final_combined/all_abstain_without_reference.png`, `final_combined/mobile_390.png`다. 모든 결과와 소스·스크린샷 해시는 [QA manifest](../../../../artifacts/manifests/phd/p2_ab_v1/sample_viewer_qa_v1.json)에 고정했다.

검사 종료 후 이번에 만든 Chrome 주 프로세스 PID1027157만 종료했고 DevTools9227 닫힘을 확인했다. read-only 8893 viewer 서버는 실행 상태로 남겼다. Chrome 자체의 background GCM deprecated-endpoint·adapter stderr는 페이지/CDP 오류와 구분했다. 이 UI 검사는 수치 정확도·과학적 성능 검증을 대체하지 않는다.
