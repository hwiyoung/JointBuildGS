# P2 A/B v2 이슈

`scientific_verdict: null`. v1의 해석 문제는 [별도 정정](CORRECTIONS_ko_v2.md)에 보존한다.

| ID | 문제·원인 | 조치와 상태 |
|---|---|---|
| V2-ROOT-001 | 첫 보존 hash 목록은 Git의 비ASCII 경로 인용을 실제 파일명으로 해석해 일부 파일을 누락했다. directory symlink도 파일처럼 hash하려 했다. | 첫 목록 보존. NUL 경로 구분으로 재계산한 6,116개 파일의 SHA와 directory symlink target 최종 보존 검사 PASS. `ROOT-AUDIT-v1/preservation_receipt.json`에 결속했다. 연구 입력/결과 파일의 수정은 발생하지 않음. |
| V2-SCOPE-001 | B의 초기화를 전부 MVS로 맞추면 과거 prior 기하에서 외관·세부를 회복한다는 중앙 질문이 약해진다. | 학습 전 설계 검토에서 prior ALS 기반 동일 G0의 주 비교로 정정. image-only는 별도 초기화라는 차이를 명시한 추가 기준선으로 분리. |
| V2-OBS-001 | v1은 1,400px undistorted derivative를 사용해 작은 후보의 세부 관측을 제한했다. | 보존된 원RGB와 FULL_OPENCV 모델로 새로운 P2 crop 준비. 원카메라 왜곡을 무시한 확대나 단순 K 배율 적용은 사용하지 않는다. 샘플 영수증에서 실제 크기·가시 범위를 확인한다. |
| V2-SURFACE-001 | 기존 overlay가 RGB screen-only 저역 필터의 alpha로 거의 평행한 ray–plane 교차도 적산했다. 실제 361 ray에서 seed 중심 camera-Z 약180m에 대해 부당한 수천 m 깊이를 확인했고 일부 직접 깊이 미분 분기도 누락됐다. | 원래 12조건과 mask/기하 loss/표면 지표는 연구 성패 해석에서 제외. 독립 plane 합성 adapter의 31개 검산과 CORRECTED 12조건 재실행·산출물 검산 완료. 원 overlay·모든 기존 실행 보존. 유효 여러 면의 기대깊이 혼합과 중심깊이 순서의 한계는 남는다. 세부 원인과 영향은 B 이슈/표면 감사 참조. |
| V2-C-001 | 첫 C exact NN 계산은 단일 CPU에서 동일 초기 표면을 반복 계산했다. 입력 기하 계약 오류도 이후 확인됐다. | 오염된 C-GEOMETRY-v1을 중지(exit137), 완료된 부분 JSON과 실행 소스를 보존했다. 수정 C 12조건의 기하·외관·세부·요약 완료. 동일 XYZ hash cache와 workers4 exact query를 사용했으며, 실제 표본 거리/index bitwise 일치와 빈 입력·중복점 fixture 전체 metric 동일성을 검산했다. |
| V2-VIEWER-001 | 첫 프리뷰 QA는 favicon.ico 404로 최종 오류검사에서 실패했다. | 원 QA를 보존하고 data favicon을 추가했다. 다음 12조건 UI QA의 1040 PASS와 renderer 검산은 구분한다. 최종 수정 데이터 viewer는 1043검사 PASS이며 JS/network 오류0이다. |
| V2-VIEWER-002 | 수정 데이터 viewer의 자동 UI 검산은 통과했지만 390px 육안 검사에서 사선 객체가 잘렸다. 세로 span 고정과 축 정렬 bbox의 최대변만 사용한 것이 원인. | 첫 수정 viewer와 aspect만 고친 v2를 보존. v3는 실제 Gaussian 3σ 정점의 bounding sphere와 화면 양축으로 초기/최종 공통 범위를 맞춘다. QA-CORRECTED-v2의 실제 WebGL 행렬·3σ 전체 정점 검사에서 잘림0 확인. 학습·평가 수치는 변경하지 않았다. |
