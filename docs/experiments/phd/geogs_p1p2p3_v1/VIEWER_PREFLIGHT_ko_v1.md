# GeoGS 세 지역 정성 뷰어 사전 점검

`scientific_verdict: null`

이 기록은 **PREFLIGHT_INPUT_DISPLAY_ONLY**이다. P1/P2/P3의 실제 ALS 변환
표면 입력을 브라우저에 표시하고 조작을 검증했다. GeoGS 학습 결과, UAS
참조 비교, 정량·정성 결과 분석을 대신하지 않는다. 이 사전 자료 생성에는
세 지역의 봉인된 ALS surface PLY만 읽기 전용으로 마운트했으며 UAS를
마운트하거나 읽지 않았다. 입력 봉인 이후 `inputs/`의 바이트를 바꾸지 않았다.

## 실제 표시와 접근

- 앱: `src/apps/geogs_p1p2p3_v1/`.
- 실행·QA: `scripts/phd/geogs_p1p2p3_v1/viewer/`.
- 외부 task root: `phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`.
- 실제 사전 표시 자료: 위 task의 `viewer_preflight/manifest.json`,
  `receipt.json`, 원본 config/script/실행 command 사본과 세 지역 JSON.
- 주소: <http://127.0.0.1:8902/app/index.html?manifest=/task/viewer_preflight/manifest.json>.
- 새 컨테이너: `jbgs-geogs-p1p2p3-viewer-8902`, loopback 8902,
  read-only root와 read-only app/Three/task/서버 script 마운트.
- 실제 결과용 주소는 `?manifest=/task/evaluation/viewer/manifest.json`이다.
  실제 결과 manifest가 준비되기 전에는 사전 점검 주소를 사용한다.

동일 prism 안에서 실제 삼각형에 연결된 ALS mesh vertex를 선택했다.
P1 18,948점, P2 40,034점, P3 47,638점이며 세 지역 모두 사전 표시 상한
50,000점 이하여서 추가 축소하지 않았다. 이는 Gaussian 초기화 점이나
Gaussian 중심이 아니다. 원 ALS의 mesh 변환 누락은 별도 surface receipt에
기록되며 이 화면에서 감추거나 채우지 않는다. 나머지 다섯 패널은 사전
점검에서 제외된 실제 산출물 대기 상태다.

## 브라우저 검증

`evaluation/browser_qa/input_preflight_v6/browser_qa.json`:
`PASS_ACTUAL_AVAILABLE_ARTIFACTS_DISPLAYED`, 40/40 checks, 9 screenshots.
P1 source screenshot을 직접 열어 실제 ALS 표면과 한국어 표시도 확인했다.

- P1/P2/P3 실제 geometry WebGL rasterization.
- 6개 패널 camera position/target/metric meters-per-pixel 일치.
- 지역 선택과 등록된 사전 조건 선택, source/distance 색상 전환.
- 시점 preset, pointer 회전, wheel 확대, 오른쪽 drag 이동의 전체 동기화.
- 브라우저 예외·실패 HTTP 요청 없음.
- 실제 원본 P1 surface PLY 다운로드 경로 HTTP 200 확인.

사용 환경은 `jointbuildgs:geogs-viewer-browser-v2`, image ID
`sha256:5043f84d76db9d54e64fcf457125aad90ac5423fded88eca6cf487d2b4713a9e`이다.
Chromium 152.0.7977.82와 Noto CJK, 컨테이너가 직접 시작한 free-display Xvfb,
ANGLE GL/Mesa software renderer를 사용한다. GPU 장치와 기존 host X에는
접근하지 않는다. `--ignore-gpu-blocklist`는 이 격리된 소프트웨어 표시
검증을 위한 명시적 옵션이며 학습/렌더러 변경이 아니다. 실행 image ID,
browser version/arguments, 실제 표시 상태와 screenshot SHA는 receipt에 있다.

실패 시도 `input_preflight_v1`–`v5`는 삭제하지 않았다. 순서대로 readonly
기본 config의 Chromium crashpad 실패, Alpine SwiftShader/Vulkan xcb 확장
부재, ANGLE GL의 X display 부재, 임의 :99와 기존 abstract display 충돌,
자동 배정 display 이후 Chromium software GL blocklist가 확인됐다. 마지막
시도는 private tmpfs XDG 경로, Xvfb의 `-displayfd` 자동 배정,
명시적 software GL/blocklist 옵션으로 해결했다. 기존 display/서비스는
종료·재시작하지 않았다.

## 실제 결과 연결 후 남은 검증

raw/post TSDF selector는 anchor/native/changed 세 패널의 `.raw`/`.post`
candidate suffix를 함께 바꾼다. prior selector는 `prior_mesh`와 `als_points`를
구분한다. 이 둘은 실제 해당 candidate가 있어야 전체 의미를 검증할 수
있으므로 사전 입력 표시 PASS를 결과 검증 PASS로 옮기지 않는다.

최종 export 이후 조건별 실제 GeoGS 표면, UAS 거리, 0.5 m 동일 단면,
실제 평가 사진/렌더/오차 그림, 사례 선택 기록과 full-source/receipt 링크를
연결해 새로운 QA run ID로 다시 실행한다. 거리 색상은 모든 패널에서
0–2 m 고정이며 초과는 포화, 거리 부재는 회색이다. 표시 표본은
`DISPLAY_ONLY`; 별도 정량 평가의 원자료를 대신하지 않는다.

사전 브라우저 PASS 이후 추가한 UI는 Docker JavaScript 구문 검사를 통과했다.
render condition/domain/image 필터는 선택한 한 장만 로드하며 목록 전체를
이미지로 생성하지 않는다. 실제 `region.cases`의 center/extent/조건을
여섯 패널에 함께 적용한다. 이 추가 UI의 실제 cases, 최종 raw/post 및
원 ALS 전환은 최종 export를 받은 뒤 별도 브라우저 QA로 검증해야 한다.
`reconstruction_failure`는 `reference_unavailable`과 별도 상태로 표시한다.

## resource_v3 UI 적용 뒤 실제 입력 재점검

새 `resource_v3_input_preflight_v1` 실행에서127개 브라우저 검사가 통과했고 exception/failed request는0이었다. 실제 ALS raster는 P1 18,948점, P2 40,034점, P3 47,638점으로 표시됐다. 동기 회전·확대·이동과 source/distance/top 제어를 확인했다. 기존 입력 manifest에는 `resolution_modes`가 없어 새1024/512 선택기는 숨김·비활성이었다. 따라서 실제 결과의 해상도 전환을 검증한 것은 아니다. 이 manifest의 MVS/anchor/GeoGS/UAS는 계속 pending이다.

증거는 외부 task의 `evaluation/browser_qa/resource_v3_input_preflight_v1/`에 있다. `browser_qa.json` SHA256은 `388d04a6f9f4b209725777cc48d0b7f2b3a941ac4798be0272fcc885b8e96759`이며 스크린샷9장·Chrome log·실행 소스 사본을 함께 보존했다. 담당 agent는 P2_source.png, root는 P3_source.png를 직접 열어 실제 ALS와 미완료 패널을 확인했다. 브라우저는 기존 private software renderer image를 사용했고 서비스·UI 코드는 변경하지 않았다.

현재 viewer 포트는 `127.0.0.1:8902`에만 연결돼 있다. 이 로컬 접속 검증을 LAN 공개·외부 접속 확인으로 표현하지 않는다. 최종 실제 결과 manifest의 검증은 여전히 별도 필수 작업이다.
