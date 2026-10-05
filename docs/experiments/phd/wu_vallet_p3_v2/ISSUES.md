# Wu–Vallet P3 v2 이슈 기록

2026-09-07 · `scientific_verdict: null`.

| 항목 | 문제·원인 | 조치·현재 상태 |
|---|---|---|
| WV2-I01 | 기존 설명이 scan/order 미구현과 필수 입력 부재를 혼동 | 실제 P3 GPS 전량 확인·scan 복원·추정궤적·점군 갱신까지 실행. 설명 정정 |
| WV2-I02 | 신규 acquisition/trajectory 결과 폴더의 Docker 생성 소유권 때문에 호스트 로그 저장 Permission denied | 해당 새 결과만 Docker에서 기록하거나 소유권 정리. 각 additional_validation/validation_receipt에 실제 실패·조치 보존. 과학 계산 실패 아님 |
| WV2-I03 | 실행 전 통합검토에서 trajectory 파일명 불일치와 context 일부 미지원이면 양방향 전체를 막는 조건 발견 | 파일명 결속, partial NaN 원점은 해당 광선만 생략하는 API·14개 ray 단위검증 적용 후 본실행. 미지원336context점은 모두 고립점이어서 실제면/광선 손실0 |
| WV2-I04 | 첫 실제 브라우저 QA에서 headless Chrome의 WebGL context lost | 새 전용프로필/명시적 SwiftShader로 재검증. 실패receipt와 이후 실행 분리. 기존서비스/브라우저 건드리지 않음 |
| WV2-I05 | 최초 viewer가 전체 평가JSON을 펼쳐 표시하여 문서가 지나치게 길어짐 | 별도 viewer-r2에서 정량표·원그림으로 표시. 첫 viewer/QA 보존, 이번 작업 소유8898만 exact ID/mount 확인 후 교체 |
| WV2-I06 | P3 ALS5,124점은 현재 sensor mesh의 어느면에도 속하지 않음 | unassessed 보존·회계 분리. 판단 성공·현재성 확인으로 주장하지 않음 |
| WV2-I07 | 갱신에 추가한 영상점 중 원래 큰 참조 편차가 있는 점이 존재 | 원점/원pixel/XYZ/crop 회계 독립검산14개PASS. 불일치신규점 채택 효과와 영상매칭대체를 별도 연구문제로 기록 |

원 실측 센서 궤적과 저자 PSMNet/공개코드 동등성, 유한 광선과 volumetric predicate 차이, 거리/영역/return층 집계 선택, datum/epoch·정합 연결은 여전히 재현 및 해석의 제한이다. 이번 성공 상태는 명시한 입력·선택에서의 원문 기반 점군 갱신 실행이다.
