# 제한·예외·해석 정정

2026-09-10 · `task_id: PHD-GEOGS-CAUSAL-FOLLOWUP-v1` · `scientific_verdict: null`

## 실행 예외와 해결

- 최초 깊이 조회 Docker 실행은 이미지 기본 작업 경로와 권한 문제로 시작 단계에서 exit 125였다. `-w /tmp`로 수정해 읽기 전용 입력 조회를 완료했다. 실패 실행에서 새 학습·추론·렌더 또는 원자료 수정은 없었다.
- `completed_prefix8000_v1`는 SfM 무-anchor 계보여서 prior anchor로 사용할 수 없음을 확인했다. 최종 감사는 `extraction_resource_v3/primary/*/D005_Pnative/auxiliary/anchor_512/model/train/ours_8000`를 사용한다.
- 최초 깊이 조회 후 prior Open3D ray는 u+0.5,v+0.5, GS는 정수 u,v인 규약 차이를 확인했다. world endpoint 계산을 보완한 별도 v2를 저장했다. 초기 자료는 보존하며 최종 본문·표는 v2를 인용한다. camera-Z 배열 조회값은 변경되지 않았다.

## 해석 제한

- 그림은 사후 선택한 폭 0.5m XY 띠 안의 기존 표본이다. 동일 조건의 모든 표본과 Y bin을 보존했다. 정확한 메쉬–평면 교선, 대응점 오차, 연속 topology 증명, 건물 전체 지표가 아니다.
- anchor와 .005는 여러 높이의 표면이 섞인다. 낮은 점이 존재한다는 이유만으로 올바른 골이 복원됐다고 판단하지 않는다. anchor에 이미 형상 차이가 있어 “DA3 refinement에서 처음 손실”이라는 설명은 지지되지 않는다.
- 깊이 probe는 화면 안에 투영되는 후보 중 하향 시선 성분 순으로 정한 3개씩이다. 투영 가능성과 직접 가시성은 다르다. P1의 두 후보에서 확인한 전경 지붕 가림을 DA3의 큰 깊이 오류로 세지 않는다. 전체 train 관측 충분성은 미평가다.
- 원 train JPG와 저장 gt PNG의 픽셀 일치를 확인해 사진–TIFF 대응을 검증했다. 그러나 current UAS 목표점의 정확한 first-hit 가시성을 새 raycast로 검증하지 않았다. 골 경계의 반 픽셀 차이와 5×5 내 다중 표면은 남는 불확실성이다.
- 실제 GS TIFF는 alpha로 정규화한 expected depth다. 이를 Gaussian 위치나 첫 표면 깊이, TSDF mesh Z와 동일시하지 않는다. opacity·복수 층의 영향은 국소 추적 전까지 원인 후보다.
- 입력과 기록된 전역 제어가 같다는 확인은 DA3/geometry/RGB 각각의 국소 gradient 기여율을 분리하지 않는다. reference는 평가·진단에만 사용했으며 mask 생성이나 학습에 사용하지 않았다.
- 기존 CRS·shift 계보를 따랐고 새 정합은 하지 않았다. 원자료에 기록된 수직 기준의 절대 검증 한계를 해소한 결과가 아니다.

## 완료한 기술 확인과 범위

| 분석 | 기존 입력 보존 확인 | 완료 상태 |
|---|---|---|
| 골 표본 그림 | 8개 원파일 SHA 전후 일치·동일 참조 ID | PASS_CACHED_SAMPLE_DIAGNOSTIC |
| 큰 변화 비교 | 12개 원파일 SHA 전후 일치·지역별 동일 참조 ID | PASS_CACHED_CHANGE_CONTRAST |
| 기존 학습 제어 | 봉인 summary·trace·receipt 9개 전후 일치 | PASS_SAVED_CONTROL_AUDIT |
| 저장 입력 깊이 v2 | 125개 입력 SHA 전후 일치·54행 보존 | PASS_SAVED_INPUT_DEPTH_TRACE |

각 행은 별도 분석의 입력 수이며 중복 없는 전체 파일 수의 합계가 아니다. 신규 분석 파일은 별도 경로에 작성했다. 기존 코드·학습·산출물·서비스를 변경하지 않았다. 새 학습·장면 렌더·추론·메쉬 추출·정합·새 거리 질의는 0회다. 마스크 방법 실험과 학위 기여 확정은 이번 완료 범위에 포함되지 않는다.

최종 Docker 정적 확인에서 최종 receipt 4개의 현재 script/config SHA 및 기록된 출력 SHA, Python 4개 구문, 문서 상대 링크 39개를 검증했다 (`PASS_NEW_ARTIFACT_QA`). Git diff 공백 검사도 통과했다. 이 확인은 서술의 인과적 확정이나 과학적 성능 판정이 아니다.
