# 동등조건 v5 이슈 기록

- **WV5-001 / 교정 실행 완료:** v4 주표에 P1/P2의 추가 관측지원 시점과 P3의 기존 hash-first 시점이 섞였다. 세 구역 전체 영상에 같은 선택 규칙과 같은 updater를 적용해 새 실행했다. 선택은 P1=90, P2=296, P3=134다. v4는 변경하지 않았다.
- **WV5-002 / 독립 검증 PASS:** v2의 작은 변화영역 재유입 버그는 v3에서 이미 교정됐다. v5 핵심 검사 59개와 평가·동등조건 검사 18개를 통과했다. 세 구역 실행 소스와 검사한 소스의 해시가 일치한다. 이번 감사에서 추가로 입증된 알고리즘 버그는 없으며 v5의 point-selection 의미는 바꾸지 않았다. raw evidence API만 노출해 이전 잘못된 최종 mask를 잘못 소비하는 경로를 차단했다.
- **WV5-003 / 지속되는 재현 범위:** 동등조건 실험과 저자 원방법의 완전 재현은 구분한다. PSMNet/COLMAP, 추정/실측 궤적과 미공개 predicate/정제 세부 차이는 과학적 결론의 범위에 반영한다.
- **WV5-004 / 평가 해석:** 모든 구역 UAS를 평가에 사용한다. 후보 생성·판정에는 사용하지 않는다. 이미 평가를 본 개발 구역이므로 독립 blind 검증이 아니다. CRS·datum/epoch·정합 오차를 새로 보정하지 않은 참조 거리다.
- **WV5-005 / 교정·재검증 완료:** P3 legacy 궤적 NPZ의 무손실 변환 검증에서 문자열 배열에 숫자용 `equal_nan` 검사를 적용해 TypeError가 발생했다. 변환 배열과 실패 로그는 보존했고, 별도 dtype-aware 검증에서 10개 배열의 dtype/shape/byte 일치를 확인했다. 재실행용 수정은 `adapter_recovery.py`로 분리해 세 지역 입력 생성 코드의 바이트 일치를 유지했다. 원 궤적 값이나 후보 정책은 바꾸지 않았다.
- **WV5-006 / 외부 wrapper 예외, 출력 검증 완료:** P3 입력의 Docker 처리가 완료된 시점에 실행 중이던 Bash launcher를 편집해 외부 shell이 EOF parse error/exit2를 반환했다. 완료한 Docker 출력과 고정 source는 보존하고 `PHD-WU-VALLET-P3-INPUT-v5/launcher_completion_note.json`에 예외를 기록했다. 이후 독립 평가 gate가 세 입력의 모든 출력·source·선택 규칙과 후보를 재검증해 통과했다. 이 예외를 알고리즘 실행 실패나 성공 exit0로 바꿔 기록하지 않는다. 이후 갱신·평가는 별도 `exec python3` launcher로 실행하고 실행 중에는 편집하지 않았다.
- **WV5-007 / 설명 정정:** core audit receipt의 2026 저자 predicate를 exact triangle-volume로 단정한 설명은 `AUTHOR_PREDICATE_CLARIFICATION.json`으로 정정했다. 2023의 tetrahedron formulation과 우리 sampled ray가 다르다는 사실, 2026 저자 predicate 세부가 미확보라는 사실을 구분한다. 원 receipt는 보존했다.
