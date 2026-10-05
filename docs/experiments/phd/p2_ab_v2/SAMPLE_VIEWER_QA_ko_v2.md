# P2 v2 Gaussian 뷰어 브라우저 QA

2026-09-07. `scientific_verdict: null`. 화면 동작·실제 매개변수 표시의 기술 검사이며
재구성 성능이나 정확도 검사와 구분한다.

현재 수정 결과 URL은
`http://127.0.0.1:8894/PHD-P2-AB-V2-VIEWER-CORRECTED-v3/viewer/`다.
새 `VIEWER-QA-CORRECTED-v2`에서 **1,043개 브라우저 검사와 기본 모바일
Gaussian 전체 정점 경계 검사**를 통과했다. 아래 기존 결과와 구분하며 자세한
수정 경위·증거는 문서 끝에 기록했다.

**후속 실행 오류 확인:** 아래 12조건 B 결과에서 low-pass alpha의 지지를 실제
기하 교차로 승격하는 renderer overlay 오류가 확인되어, mask·학습·표면 추출을
포함한 해당 실험 결과를 연구 판단에 사용하지 않는다. root/B가 수정·검산·재실행한다.
아래 1,040개 QA 통과는 당시 저장된 매개변수·이미지의 정확한 표시와 UI 동작에 대한
기록으로 보존하며, 입력 실험의 과학적 유효성까지 보장하지 않는다. 수정된 실행은
별도 export와 새 QA가 필요하다. 이 문서의 기존 `최종` 표기는 해당 export의 당시
이름이지 오류 확인 이후의 유효 결과 승인이 아니다.

## 검사 계약

[c_browser_qa.mjs](../../../../scripts/phd/p2_ab_v2/c_browser_qa.mjs)는 Node 기본
모듈로 Chrome DevTools를 사용한다. 사용자 프로필에는 접근하지 않는다. 실제 Chrome
command line의 `--user-data-dir`가 명시한 `/tmp/jbgs-p2-ab-v2-qa.*`와 같아야 실행한다.
프로젝트 수치 처리와 테스트는 Docker이며 이 호스트 Chrome/Node 실행은 브라우저 UI
검사에 한정한다.

- `P2_GAUSSIAN_VIEWER_READY/STATE`, 초기·최종 상태 count와 실제 모든 매개변수의
  shape/유한성, scale 양수, quaternion 유효성, 선형 opacity/RGB 범위를 검사한다.
- WebGL2 실제 draw 호출을 관찰해 Gaussian은 TRIANGLES, 중심점은 POINTS인지 확인한다.
  mesh count만 보거나 점이 보인다는 이유로 Gaussian 검사를 통과시키지 않는다.
  모드 변경 전후 실제 canvas 픽셀도 달라야 한다.
- 초기·최종·target 삼중 영상의 frozen 평가 ID, 평가 역할, 동일 크기, 카메라 K/pose,
  source view manifest hash와 실제 PNG bytes hash를 검사한다.
- 드래그·평면·단면·390 px 모바일·자료 로드·JavaScript와 네트워크 오류를 확인한다.
- 이 브라우저는 저장된 중심·접선 크기·quaternion·RGB·opacity로 3σ 평면 Gaussian
  kernel을 그린다. 중심 깊이 기반 합성이므로 gsplat과 픽셀 단위로 같은 renderer라는
  주장을 하지 않는다. 실제 gsplat 출력은 별도 PNG 삼중 비교에 있다.

## 32-step preflight

URL:
`http://127.0.0.1:8894/PHD-P2-AB-V2-VIEWER-PREFLIGHT-v1/viewer/`.
이 프리뷰는 전경 가림 수정 전 `PREFLIGHT-v2`의 32-step 실행이며 최종 성능 결과가 아니다.

Google Chrome 146.0.7680.80, headless SwiftShader로 실제 페이지를 열었다.
사용 프로필은 `/tmp/jbgs-p2-ab-v2-qa.Fmtl0rl7`, DevTools는 9228이다. root가 소유한
읽기 전용 8894 서버를 사용했고 기존 서버·브라우저 프로필을 중지하거나 변경하지 않았다.

결과는 **70개 검사 통과, 비핵심 favicon 404로 전체 상태 PARTIAL**이다. 실제 초기·최종
45,986개 Gaussian의 크기·방향·색·불투명도와 mesh draw, 중심점 전환의 픽셀 변화,
11개 평가뷰의 삼중 영상, 드래그·단면·모바일은 통과했다. 실제 JavaScript 예외는 없었다.
`/favicon.ico`의 404를 숨기지 않고 실패 기록에 남겼다. owning root가 source HTML에
data favicon을 추가했으며 기존 프리뷰는 그대로 보존한다. 최종 export에서 재검사한다.

초기 background Chrome 시작은 9228이 열려 있지 않아 연결에 실패했다. 빈 `browser/`
디렉터리와 시작 기록은 보존했다. 별도 foreground 실행과 새 프로필로 복구했다.
원인을 브라우저 GPU 실패나 사용자 세션 문제로 확정하지 않는다.

외부 산출물 root:
`phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-VIEWER-QA-PREFLIGHT-v1/`.

| 산출물 | 내용 |
|---|---|
| `technical_receipt.json` | 70개 통과/1개 favicon 오류, 프로필·PID·소스 해시·화면 해시 |
| `source_c_browser_qa.mjs` | 당시 실행 소스; 후속 강화된 QA source와 구분 |
| `browser_recovery_v1/FAILED.json` | 숨기지 않은 전체 실패와 통과 체크·이벤트 |
| `browser_recovery_v1/desktop_gaussian_initial_final.png` | 실제 Gaussian 초기·최종 표시 |
| `browser_recovery_v1/desktop_centers.png` | 점 표현과의 분리 비교 |
| `browser_recovery_v1/native_view_triplet.png` | 같은 평가 카메라 사진·초기·최종 gsplat |
| `browser_recovery_v1/mobile_390.png` | 모바일 표시 |

최종 실행을 위한 QA source에는 추가로 PNG 자체의 SHA256와 finite K/pose 검사를
강화했다. 위 70개 preflight 통과에 아직 실행하지 않은 추가 검사를 소급 포함하지 않는다.

## 최종 12개 조건 검사

최종 URL:
`http://127.0.0.1:8894/PHD-P2-AB-V2-VIEWER-v1/viewer/`.
새 출력 `phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-VIEWER-QA-v1/`에서
**1,040개 검사 모두 통과**했다. `browser_qa.json`의 상태는
`PASS_BROWSER_PARAMETER_INSPECTION_AND_INTERACTION_ONLY`다.

12개 조건의 초기·최종 전체 parameter JSON, 실제 TRIANGLES/POINTS draw와 픽셀 변화,
각 조건의 11개 평가 카메라 삼중 영상 396개 PNG bytes SHA, finite K/pose·크기·역할·ID,
드래그·단면·평면·390 px 모바일을 검사했다. JavaScript 오류와 실패한 네트워크 요청은
모두 0이며 favicon 문제도 해결됐다. 같은 11개 평가뷰를 12번 비교한 것이므로 132개의
독립 시점으로 세지 않는다.

저장된 Gaussian 수는 일반 prior 조건 45,986개, 표현 세분 조건 183,944개,
image-only 조건 266,361개였다. 초기·최종 count를 각 실제 state와 대조했다.
`thinned=false`는 뷰어가 저장된 state를 추가 축소하지 않았다는 뜻이며, B 초기화가
native 전체 원점을 항상 그대로 사용했다는 별도 주장이 아니다.

두 WebGL2 renderer는 실제로
`ANGLE / Vulkan 1.3.0 / SwiftShader Device (Subzero)`를 보고했다. 대표 최종
스크린샷을 직접 열어 Gaussian의 색·크기·방향과 실제 gsplat 삼중 영상 표시도 확인했다.

| 최종 산출물 | 내용 |
|---|---|
| `browser_qa.json` | 12조건·1,040검사·11시점 반복의 전체 결과와 해시 |
| `run_configuration.json`, `source_c_browser_qa.mjs` | 실제 실행 URL/프로필/포트와 소스 동결 |
| `desktop_gaussian_initial_final.png` | 기본 구조 제한 조건의 초기·최종 실제 kernel 표시 |
| `desktop_centers.png` | 같은 데이터의 점 표현 |
| `desktop_dragged.png`, `desktop_top.png`, `desktop_section.png` | 실제 조작 결과 |
| `native_view_triplet.png` | 동일 카메라의 target·초기·최종 출력 |
| `mobile_390.png` | 최종 모바일 레이아웃 |
| `browser_cleanup_receipt.json` | 소유 Chrome 종료, 9228 닫힘, root의 8894 viewer HTTP 200 유지 |

실행 source SHA256은
`41787b65d8c945828835302c2ab520ba68dcd194e5df5a1ecc510a2b36d684d2`다.
작업 Chrome PID 2915445는 정확한 실행 파일과 작업 프로필을 재확인해 종료했다.
처음 null 구분 argv 검사가 Chrome의 공백으로 합친 process title 때문에 안전하게
거절되어 아무 signal도 보내지 않은 사실과, 이후 정확한 token 재검사 후 종료한
기록도 cleanup receipt에 남겼다. 사용자 프로필·기존 서비스는 변경하지 않았다.

이 통과는 저장된 Gaussian과 이미지의 표시·연결·조작에 대한 것이다. source 현재성,
표면 정확도, 구조 보존, 세부 복원의 성공 또는 gsplat과 브라우저의 픽셀 동등성을
검증했다고 해석하지 않는다. 재구성 성능은 B/C의 별도 실험 결과를 따른다.

## 수정 실행용 QA 준비

후속 읽기 검토에서 사진 triple의 단순 존재 검사만으로는 누락된 평가 시점을
거절하지 못하는 점을 확인했다. QA source는 각 arm에서 고정된 11개 평가 ID의
정확한 집합과 중복 부재를 검사하도록 강화했다. arm ID 중복 검사도 추가했으며,
수정 최종 12조건 실행에는 CLI 마지막 인수 `12`로 전체 조건 수도 고정한다.
새 source SHA256은
`fdcc69cedb0a4a8f8c7d80f440c7f5c321c22c1ab33d8f6e367f4644746062df`이며,
Node 구문 검사를 통과했다. 수정된 실제 결과에 대한 새 브라우저 QA는 대기 중이다.

## 수정된 12조건 최종 QA

수정 B의 세 실행 root만 담은 `VIEWER-CORRECTED-v1`에서 12조건·1,042개
자동 검사는 통과했으나, 육안으로 390 px 모델 잘림을 발견했다. 당시 camera는
수직 span만 고정했다. 기본 사선에서 초기/최종 중심의 수평 범위가 약
[-31.62,31.63]/[-31.74,31.70] m인 데 비해 화면은 ±26.07 m여서 각각
2,079/2,092개 중심이 화면 밖이었다. 이 사실은 `QA-CORRECTED-v1`의
`manual_screen_review.json`에 별도로 남겼다. 레이아웃 overflow 통과가 모델
전체 표시 통과를 뜻하지 않는 사례다.

root는 가로세로 비율만 보정한 `VIEWER-CORRECTED-v2`도 보존하고, 실제
Gaussian 3σ triangle 정점의 bounding sphere로 초기·최종 공통 범위를 맞추는
`VIEWER-CORRECTED-v3`를 새로 만들었다. 중간 v2의 전체 브라우저 검사를
반복했다고 주장하지 않는다. 수정 B state/PNG는 같고 브라우저 화면 맞춤만 바뀌었다.

최종 검사 URL:
`http://127.0.0.1:8894/PHD-P2-AB-V2-VIEWER-CORRECTED-v3/viewer/`.
최종 QA 출력 root:
`phase-payloads/phd/p2_ab_v2/PHD-P2-AB-V2-VIEWER-QA-CORRECTED-v2/`.

- **1,043개 검사 모두 통과.** 정확한 12조건과 각 조건의 중복 없는 11개 frozen
  평가 ID, 전체 초기·최종 저장 매개변수와 실제 mesh/point draw 및 픽셀 변화를 확인했다.
- 카메라 K/pose·역할·영상 크기·view manifest와 PNG bytes SHA를 대조했다.
  132개 triple은 동일한 11시점을 12조건에 반복한 것이며, 396개 PNG를 확인했다.
- JavaScript/페이지 로그 오류와 네트워크 실패는 0이다. 드래그·단면·평면 및
  390 px 모바일 레이아웃 검사를 통과했다.
- 실제 WebGL에 업로드된 projection/modelView matrices를 관찰하고 기본
  structured_detail의 초기·최종 전체 45,986개 중심이 화면 안에 있음을 계산했다.
  이어 [sample_browser_framing_audit.mjs](../../../../scripts/phd/p2_ab_v2/sample_browser_framing_audit.mjs)로
  각 단계의 모든 3σ quad 고유 꼭짓점 183,944개까지 대조해 화면 밖이 **0개**였다.
  초기 NDC 범위는 x[-0.8573,0.8405], y[-0.7814,0.7021],
  최종은 x[-0.8674,0.8422], y[-0.7873,0.7074]였다.
- 기본 desktop/mobile 스크린샷을 직접 열어 여백과 전체 모델 표시를 확인했다.
  추가 경계 검사는 기본 조건의 기본 사선/390 px 범위이며 모든 사용자 zoom과
  모든 가능한 조작에서 항상 물체가 들어온다는 주장은 아니다.

최종 브라우저 QA source SHA256:
`240fd1e832861ec4317ea8d00a3fc1e23ee89cd5f32042c8bd9936b35317f415`.
최종 viewer `app.js` SHA256:
`eea6a71820c24a88aa4cc47efdb3f00f690d0bb68792e5a11ee437959154fb76`.

| 최종 QA 산출물 | 내용 |
|---|---|
| `browser_qa.json` | 12조건·1,043개 검사, 카메라/PNG, 실제 WebGL 행렬 |
| `gaussian_full_fit_audit.json` | 기본 모바일의 초기·최종 모든 3σ quad 경계 및 입력/소스 SHA |
| `manual_screen_review.json` | 직접 확인한 최종 화면과 이전 잘림 수정의 범위 |
| `run_configuration.json`, `source_c_browser_qa.mjs` | URL·프로필·expected12와 실행 소스 |
| `source_sample_browser_framing_audit.mjs` | 독립 화면 경계 계산 소스 |
| `desktop_gaussian_initial_final.png` | 여백을 포함한 전체 초기·최종 Gaussian |
| `desktop_centers.png`, `desktop_dragged.png`, `desktop_top.png`, `desktop_section.png` | 실제 모드·회전·단면 |
| `native_view_triplet.png` | 동일 평가 카메라 target·초기·최종 gsplat |
| `mobile_390.png` | 모델 전체가 들어오는 수정 모바일 화면 |
| `browser_launch_receipt.json`, `browser_cleanup_receipt.json` | 작업 Chrome 정체성, 종료와 서버 보존 |

대표 desktop 스크린샷 SHA256은
`1ceef282c02ea9ae4c7b128cd88fb909997841d150c29d6e3f2f317596f64d96`,
모바일은 `9510135abedeaf4ae1d4ce6024541ce4b1fc60cbbbf0e550883d1bdc08f8b67f`다.

작업 프로필 `/tmp/jbgs-p2-ab-v2-qa.XRwNUbka`, Chrome PID 3202545를 두 수정
QA에만 사용했다. 두 실제 WebGL renderer는 SwiftShader를 보고했다. Chrome
배경 로그에는 descriptor lookup/GCM deprecated endpoint와 별도 NVIDIA adapter
초기화 메시지도 있었으므로 전체 Chrome 프로세스가 GPU를 전혀 쓰지 않았다고
주장하지 않는다. 페이지 오류와 WebGL renderer의 관찰은 구분한다.

완료 후 정확한 실행 파일·프로필을 다시 확인해 소유 PID만 SIGTERM으로 정상 종료했다.
프로세스 소멸, DevTools 9228 닫힘, root의 8894 최종 viewer HTTP 200 유지까지
확인했다. 사용자 프로필과 기존 서비스·이미지·실험 산출물을 변경하지 않았다.

이 최종 통과도 저장된 수정 결과의 표시·파일 연결·조작 검증이다. B adapter의
기하·미분 검산이나 C의 참조 기반 성능 비교를 대신하지 않으며 scientific verdict는 null이다.
