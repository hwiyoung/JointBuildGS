# Issues — source candidate v1

`scientific_verdict: null`

| ID | 문제 | 처리/상태 |
|---|---|---|
| SC-001 | 제공 정합·pose 불확실성 미보정 | 고정값 및 후보 변위 검사로 범위 제한; 원인/절대 정확도 주장 금지 |
| SC-002 | 같은 RGB로 생성된 MVS의 관측 의존성 | 개발 검증으로 명시; 독립 관측이라고 부르지 않음 |
| SC-003 | local plane과 native points의 표현 차이 | native membership·적합 잔차·무효 후보 포함, native 결과와 plane diagnostic 분리 |
| SC-004 | 전체 장면 가림·free-space 미확인 | source별 자기 가림 모델과 관측 부족 명시, 현재성 확정·삭제 권한 없음 |
| SC-005 | 초기 조사에서 존재하지 않는 예전 config/run.sh 경로 검색 | 현 파일 목록으로 수정; 처리 실행이나 산출물 변경 없이 해소 |
| SC-006 | UAS 평가 로더가 `xyz`를 기대했으나 동결 파일의 정확한 키는 `uas_xyz`여서 평가 첫 시도 중단 | 전체 method seal 이후 Docker에서 스키마 확인. 로더·명시적 스키마 테스트 수정. 실패 로그·소스·빈 출력은 `failed_attempts/`로 보존하고 평가만 재실행; 후보·관측·판단 및 임계값은 변경하지 않음 |
| SC-007 | 실패 평가를 보존하는 host rename이 Docker root 소유의 빈 `run/evaluation` 디렉터리 권한 때문에 중단 | 런처가 해당 task 출력만 마운트한 Docker에서 atomic rename 수행하도록 수정. 첫 보존 디렉터리의 로그·소스와 빈 복사본도 유지; 다른 실험 출력 권한은 변경하지 않음 |
| SC-008 | 관측 없는 사례의 빈 profile legend에 Matplotlib 경고 발생 | 그림 17종 PNG/PDF와 manifest 정상 생성. 해당 패널에 데이터가 없음을 유지; 경고 로그 보존. 수치·그림 생성 실패가 아님 |
| SC-009 | 전체 1,317셀 중 42셀만 선택; P1/P3의 큰 이격 prior 선택 근거 부족 | 결과와 실패를 모두 보고. 27개 사전 고정 민감도에서도 P1 0 / P2 33–42 / P3 1–3 선택. 후보 표현·관측 대응 단위 개선이 후속 과제 |
