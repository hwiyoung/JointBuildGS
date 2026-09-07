# 실제 결과 바로 보기

`PHD-GEOGS-P1P2P3-v1` · `scientific_verdict: null`

2026-09-08 22:15 KST 사용자의 “이제 그냥 결과를 뷰어에서 보여줘” 요청에 따라, 최종 분석을 기다리지 않고 닫힌 실제 결과를 기존 viewer에 연결했다.

[이 컴퓨터에서 실제 결과 열기](http://127.0.0.1:8902/app/index.html?manifest=/task/evaluation/viewer/manifest_preview_v1.json&color=height)

1. 상단에서 P1/P2/P3와 변경 조건을 선택한다.
2. 처음 열리는 같은512·높이 색상 비교는 prior / 영상 MVS / anchor / GeoGS 원설정 / 변경 / UAS를 같은 카메라로 보여준다. 예를 들어 `D0005_Pnative`는 깊이 가중치 약화, `D005_Prelease`는 원래 깊이 가중치를 유지한 보호 해제다.
3. 마우스로 회전, 휠로 확대, Shift+드래그 또는 오른쪽 드래그로 이동한다. 여섯 패널의 시점이 같이 바뀐다.
4. 최종1024, raw/post, 표면 점/실제 삼각면, 참조 거리 색상을 선택할 수 있다. Anchor1024는 확인된 자원 부족이며 같은512에서 anchor 비교가 가능하다.
5. 아래에서 고정 단면·거리 지도 및 실제 사진/GeoGS 렌더/RGB 오차 그림을 선택한다.

이 주소는 기존 `127.0.0.1:8902` 서비스이며 LAN 주소가 아니다. Preview는 생성 시점의 정적 목록이다. P1/P2는 각각32개 후보 상태와210/126개 실제 렌더 비교 항목을 포함한다. P3는 당시24개 후보 상태와0개 완료 렌더 평가 항목을 포함하며, 아직 등록되지 않은 비교는 대기로 표시한다. 모든 주18개 학습·필수 표면·저장 RGB는 이미 완료됐지만 P3 평가/표시 목록·렌더 점수의 완성이 진행 중이라는 차이를 유지한다.

기존 최종 평가 launcher는 계속 실행 중이다. 최종 평가 산출물 `evaluation/viewer/manifest.json`과 사례 포함 `manifest_v2.json`은 이 preview와 다른 파일이다. Preview를 최종 사례/전체 browser QA의 완료 증거로 바꾸지 않는다. 전체 분석 문서는 여전히 작성 중이다.

## 생성 근거

- Manifest: `evaluation/viewer/manifest_preview_v1.json`
- Manifest SHA256: `5eab711b7ef371726d45d3d5837aba5a2363e0b201ffb69f05f6f4c896f83a18`
- Script: `scripts/phd/geogs_p1p2p3_v1/viewer/build_available_preview.py`
- Config: `configs/phd/geogs_p1p2p3_v1/viewer_preview_v1.json`
- Docker image: `jointbuildgs:geogs-official-db40c95-compat-v1` / `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`
- 실제 실행: CPU1/RAM2GiB, 네트워크 없음. `PYTHONPATH=/code/evaluation`, `LD_PRELOAD=/opt/geogs/lib/libstdc++.so.6`에서 `python /code/viewer/build_available_preview.py --task /task --config /config.json`.
- `/task`는 기존 외부 task, `/code`는 해당 workstream scripts 읽기 전용, `/config.json`은 위 config 읽기 전용 mount였다. 실행 exit0, 출력 상태 `ACTUAL_AVAILABLE_PREVIEW_READY`.

P1/P2는 완료된 `viewer_index.json`을 사용하고 P3는 `EVALUATED`가 닫힌 job만 표시했다. P3 참조 표시가 아직 생성되기 전이므로, 닫힌 prior 평가의 `reference_points` 배열에서 기존 표시 exporter로 `reference_preview_v1.json`을 만들었다. 원 UAS를 다시 열거나 점수를 계산하지 않았다. 기존과 같은 .1m 표시 voxel·최대20만점 규칙을 적용하며 이 표시 자료를 평가 입력으로 사용하지 않는다. Source NPZ의 경로·SHA와 script/config/candidate seal SHA는 preview manifest에 기록했다.

기존 입력·메시·평가·서비스·live launcher를 덮어쓰지 않았다. 실제 HTTP200을 확인했다. 첫 preview smoke는 `viewer_qa_preview_v1/attempt.20260908T131645Z.s2Wrg7`에서34검사·3지역 스크린샷으로 PASS했다. 3지역×6패널의 실제 픽셀, P1 native512 메시74,254삼각형의 draw, 실제 사진·렌더 갤러리4200×1043 표시를 확인했다. 전체 조건 matrix나 최종 과학 검증은 아니다.

스크린샷 수동 확인에서 UAS 등록 기본색이 배경과 비슷한 점을 발견했다. 앱 초기화에 선택적 `color=height/source/distance` URL 인자를 추가했으며, 인자 없는 기존 기본값과 데이터는 유지한다. 최종 제공 링크는 공통 높이 색상으로 시작한다. 원래 `viewer.js`는 첫 smoke의 snapshot에 보존되어 있다. 두 번째 smoke는 이 시작 색상의 실제 표시를 검증한다.

높이 색상 URL의 실제 검증은 `viewer_qa_preview_v1/attempt.20260908T132127Z.qXBi7Q`에서34검사·18.85초·스크린샷3개로 PASS했다. 세 지역의 `QA state.mode`와18패널 색상 모드가 모두 height이며, UAS 형상이 보이는 실제 화면을 수동 확인했다. P1 메시74,254삼각형 및 실제 사진/렌더 갤러리 로드도 확인했다. 기존 smoke source/wrapper는 유지하고 새 실제 명령의 URL 인자만 바꿨으며19개 출력 파일 해시를 검증했다. 두 attempt의 원 영수증과 스크린샷을 모두 보존한다.
