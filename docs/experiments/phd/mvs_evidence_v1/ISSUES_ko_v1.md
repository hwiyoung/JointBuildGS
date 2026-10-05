# Prior–MVS 관측 진단 이슈

`PHD-MVS-EVIDENCE-v1` · `scientific_verdict: null`

- MVS 이웃 depth에 대한 검사는 MVS-conditioned이며 독립 visibility truth가 아니다.
- 기존 MVS의 실제 생성 이웃 및 평가영상 독립성은 복구되지 않았다.
- Prior 반픽셀 ray와 MVS native 해상도를 각각 보정한다. 경계의 보간 차이 자체는
  정합오차·기하 변화와 구분해야 한다.
- 비용곡선은 source normal 평면 가설과 고정 탐색 범위에 조건부이다. 표면 경계,
  가림, 잘못된 normal에서 높은 비용/모호성은 원인 판정이 아니다.
- 최초 수치 테스트에서 odd-size nearest mapping의 마지막 RGB 픽셀을 범위 밖으로
  예상한 fixture가 실패했다. native K로 직접 검산하니 유효 픽셀이 맞아 기대값을
  수정했으며, core 샘플러 변경 없이 9개 Docker 검사가 통과했다.
- 최초 CPU 시도 `attempt_20260914T144506Z_dtLFFa`는 source raw patch에 일부 결손이
  있어도 normal 평면 가설이 그 위치를 채울 수 있는 비용곡선 지원 문제를 검토에서
  발견해 중단했다. 이 시도의 출력은 미완료·대체됨으로 보존한다. 새 시도는 두 source
  raw patch가 모두 완전할 때만 비용곡선 support를 허용한다. 기존 GPU 실험은 그대로다.
- 비용 최저점이 내부와 오른쪽 탐색 끝에서 동률인 경우 첫 argmin만 보면 경계 도달을
  놓쳤다. 양 끝의 실제 비용을 최저 비용과 비교하도록 수정하고 회귀 검사를 추가했다.
  낮은 비용 구간 자체가 경계에 닿는지도 별도 원자료에 기록한다.
- 최초 실제 브라우저 검증은 화면 밖의 lazy-load 사례 이미지를 스크롤 없이 기다려
  timeout됐다. 당시 script/runtime/network 오류는 0개였다. QA에서 실제 검사할 이미지를
  실제 스크롤로 로드한 뒤 판정하도록 고쳤다. `qa_v2/receipt.json`은 476개 검사,
  207개 지도 상태, 36개 사례에서 PASS이며 오류 요청·응답·runtime·console 오류는
  모두 0개다. 첫 QA 실패 기록은 보존한다.
- 첫 검토 UI의 공통 설명은 모든 지도에 '격자점만'이라고 써 전체 raster 깊이차와
  혼동될 수 있었다. `review_v2`에서 full raster/16px 관측/48px 비용곡선을 구분하고
  '가시성' 필드도 source 내부 깊이 일치·모델 뒤쪽 후보로 구체화했다. 수치는 그대로다.
- 최종 수치 검사는 결손 원패치와 탐색 끝 동률 회귀 검사를 포함해 13개 모두 통과했다.
- 모바일 `mobile_delivery/v1`의 깊이 colorbar 숫자를 공백 문자열로 배치해 실제
  색척도 위치와 맞지 않았다. `v2`는 0/75/150m를 시작/중앙/끝 좌표로 명시했고,
  직접 시각 검토했다. v1·원 수치·원 마스크는 보존했으며 전달 대상은 v2다.
