# P1 수동 다중 시점 영역 표시 — 이슈와 한계

- task_id: `PHD-P1-MANUAL-REGIONS-v1`
- scientific_verdict: null

## FIXED-001 — RGB mask의 boolean 자료형 승격

초기 생성 `attempt.uCJGq4`의 후속 배열 검증은 exit 137로 종료됐다. 확인한 구현
문제는 nearest sampling의 `np.where`에서 정수 기본값 0 때문에 boolean 배열이
int64로 승격된 것이다. 저장 값은 0/1로 맞았지만 `~valid`가 논리 부정 대신
음의 정수 인덱스가 되어 검증기가 매우 큰 배열을 만들 수 있었다. OS의 kill 사유는
별도로 확정하지 않았다.

`resample_nearest`에서 outside 값을 원래 배열 dtype으로 변환하고 boolean/uint8
자료형 회귀 테스트를 추가했다. 15개 Docker 테스트가 통과했다. 기존 attempt와
검증 소스는 보존하며, 새 immutable attempt에서 98개 RGB NPZ의 boolean 필드만
수정한다. 모든 필드의 픽셀 값과 모든 그림의 해시 동일성을 검사한다.
최종 `attempt.boolfix.QrP8Ir`는 196개 배열 및 900개 출력 해시 검증을 통과했다.
원래 영역 값이나 표시 그림은 변경하지 않았다.

## KNOWN-001 — 전체 raster 생성과 의미 검수 범위

98개 train 시점 모두에 전체 raster를 만들지만 수동 의미 분할 원영상은 2개다.
나머지는 현재 MVS의 기하적 대응을 검사하여 전파한 초안이며, 모든 픽셀의 의미적
정확도를 사람이 검수한 결과가 아니다. 미분류·대응 미확인 영역은 ID 5로 보존한다.

후속 `VIEW_SUPPORT_AUDIT_ko_v1.md`에서 첫 시점이 R1 native 표본의 77.84%를
차지함을 확인했다. 기존 P1 내부의 동일 기준 지면 표본을 다른 시점들이 지지하는
범위도 제한적이다. 98장 파일 생성과 충분한 다중 시점 감독을 구분한다.

## FIXED-002 — 후속 감사의 환경 확인 명령

지원 범위 감사 결과 생성은 성공했으나 별도 환경/배열 재확인 명령에서 읽기 전용
Docker에 `/tmp` mount를 빠뜨려 Matplotlib import가 종료됐다. 쓰기 가능한 임시
cache mount를 추가한 동일 read-only 검사로 해결했으며 입력과 감사 결과는 변경하지 않았다.

## KNOWN-002 — 다른 시점의 객체와 공통 MVS 오차

대표 시점 사이에 장비/차량 배치가 다르다. source별 제외와 다른 시점의 veto를
적용하지만, 두 대표 영상에서 관찰하지 못한 일시적 객체는 남아 있을 수 있다.
MVS 재투영 일치는 독립 측정이나 confidence calibration이 아니다.

## KNOWN-003 — 새로운 제외 정책과 학습 범위

표시용 배율 0/1/4는 학습 입력에 연결하지 않았다. 제외 마스크가 같은 기준선과
비교해야 α의 효과를 해석할 수 있다. 기존 80×80m 학습 문맥으로 표시를 제한했으며
기존 30×30m 평가 영역을 확장한 결과로 해석하지 않는다.
