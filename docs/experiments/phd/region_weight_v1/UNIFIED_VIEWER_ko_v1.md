# P1/P2/P3 가중치 실험 완료 및 통합 뷰어

- 확인일: 2026-09-16, Asia/Seoul
- Task: `PHD-P1P2P3-WEIGHT-VIEWER-v1`
- Scientific verdict: `null`
- 실행 범위: 기존 완료 결과의 검사·표시·연결. 새 학습·평가 점수 변경 없음.

## 완료 상태

각 대상의 α=0/1/4 모두 학습 PASS, 최종 checkpoint iteration=30000,
표면 추출 PASS, `PASS_INDIVIDUAL_FINAL_DISPLAY`를 확인했다.
학습·추출 receipt, config와 mask 해시는 publication provenance와 일치한다.

| 대상 | 0 최종 등록 (KST) | 1 최종 등록 (KST) | 4 최종 등록 (KST) |
|---|---|---|---|
| P1 | 09-15 21:58:55 | 09-15 22:02:21 | 09-15 22:51:55 |
| P2 | 09-15 23:52:28 | 09-16 00:41:40 | 09-16 01:30:43 |
| P3 | 09-15 23:45:40 | 09-16 00:28:21 | 09-16 01:11:07 |

위 시각은 학습 종료만의 시각이 아니라 표면·렌더의 최종 등록 시각이다.
9개 조건의 완료는 기하 정확도 향상에 대한 과학적 판정과 별개다.
P2/P3의 새 독립 UAS 정량평가를 완료했다는 의미도 아니다.

## 뷰어

- 서버: `http://127.0.0.1:8910/app/weights.html`
- 기존 브라우저 전달 주소에서는 `/app/weights.html`로 이동한다.
- P1/P2/P3 버튼과 기존 평가 범위/주변 포함 선택을 제공한다.
- α=0/1/4의 최종 raw RGB TSDF512 표면은 동기화된 3D 화면으로 표시한다.
- 촬영 영상 선택이 원사진, native MVS·영역·가중치 그림, 실제 GS RGB/depth를 함께 전환한다.
- 영역도는 전체 영상이며 3D 표시 범위를 바꾸어도 자르지 않는다.
- P2/P3 전체 학습뷰 영역도 링크는 같은 대상·카메라를 선택해 연다.
- 기존 P1, P2/P3 결과 페이지와 수동 영역 페이지에도 통합 뷰어 링크를 추가했다.

## 실험 정책 차이

| 대상 | 실제 수동 마스크 적용 범위 | R1 | 표시 촬영 영상 |
|---|---|---|---|
| P1 | 0100_D만 적용; 다른 97개 depth 기존 감독 유지 | 보정 시험 지면 | 0100_D 학습 / 0099_D 평가 |
| P2 | 전체 57개 학습 depth | 반복 아치 지붕 | 0146_D / 0108_D |
| P3 | 전체 137개 학습 depth | 긴 곡면 지붕·전면 외벽 | 0046_D / 0142_D |

공통: R1=α, R2/R3=1, R4/R5/R6 및 결측=0. 전역 MVS 계수 0.05.
P1 0099_D에는 학습 감독이 없으므로 영역 그림을 대신 제시하지 않고 미적용을 명시한다.
P1은 실제 학습 NPZ의 native/RGB labels와 use/R1 bool 배열의 일치를 검증해 새 그림을 만들었다.
P2/P3는 학습 mask manifest와 기존 영역도 review의 annotation receipt/config 해시를
결박하고, 해당 카메라 NPZ 해시 및 R1–R6 표본 수를 확인했다.

## 재현 및 검증

- 생성: `scripts/phd/region_weight_v1/build_unified_viewer.py`
- 설정: `configs/phd/region_weight_v1/unified_viewer_v1.json`
- Docker 실행: `scripts/phd/region_weight_v1/run_unified_viewer.sh`
- 브라우저: `scripts/phd/region_weight_v1/unified_browser_qa.mjs`
- 외부 출력: resolver `artifacts/manifests/phd_unified_weight_viewer_20260916.yaml`
- 9개 조건의 최종 기록과 101개 표시 asset 크기·SHA256 확인.
- CPU Chromium 검증: 실제 mesh 그리기, 카메라 동기화, 입력/렌더/영역도 동일 카메라,
  평가뷰 마스크 미적용, UI 전환, 모바일 폭, 전체뷰 카메라 직접 연결, 기존 페이지 유지.

첫 브라우저 검증은 186 checks PASS였다. 수동 그림 검토에서 발견된 P1 도면의
행 제목 간격을 수정했다. 최초 표시 자료와 검증은
`weights_v1_layout_review_20260916`에 보존했고 최종 자료를 `weights_v1`에 재생성했다.
원본 학습·추출·영역 마스크는 변경하지 않았다.

최종 재생성 자료에서도 `browser_qa.3eZhRSBV/receipt.json`의
`PASS_UNIFIED_VIEWER_BROWSER`, 186 checks PASS를 확인했다.
실제 화면에서 P1 제목 겹침 해소를 확인했다. P2/P3 기존 도면에 보존된
‘학습 미연결’ 문구는 제작 당시 기록임을 페이지에 명시하고 서버 응답을 확인했다.
최종 앱 파일은 `source/app/`와 `source/app.sha256`에 보관했다.
