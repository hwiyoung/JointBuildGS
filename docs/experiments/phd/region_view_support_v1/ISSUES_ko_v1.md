# 이슈 — R1–R5 영상 지원 감사

- `scientific_verdict: null`
- RV-001 / INPUT_LIMIT: 개략 사각형을 원 MVS 객체축 기준 수치 영역 v1로 옮김. 생성 이미지 자체는 지리참조 자료가 아님.
- RV-002 / INTERPRETATION: 유효 감독 계수량 및 MVS끼리의 지원 일치는 실제 loss/gradient 또는 정확도 평가가 아님.
- RV-003 / DEVELOPMENT_LINEAGE: 기존 MVS의 평가 영상 참여와 영역 간 공유가 있으므로 독립 검증 또는 일반화 결과가 아님.
- RV-004 / FIXED: 첫 시도 `attempt_20260915T130749Z_VUSB9Q`는 P1 진단 NPZ 경로에서 `result/`를 빠뜨려 카메라 순회 전에 실패했다. 실패 traceback/코드 snapshot을 보존했다. 실제 NPZ 위치를 확인해 수정하고 파일 존재 검사 및 해당 입력의 `--mount` 사용으로 재발을 방지했다. 잘못된 Docker `-v`가 만든 빈 디렉터리는 비어 있음을 요구하는 `rmdir`로 제거했다. 기존 파일은 변경하지 않았다.
- RV-005 / CONFIRMED_SELECTION_EFFECT: 기존 P1의 113개 전체 카메라 membership은 `all_corners_inside`를 전체937에 재적용한 결과와 완전히 같다. 08:45 비행의 0098_D/0101_D는 모서리 7/8개만 포함해 탈락했지만 기존 보정 지면 23,118표본 전체를 depth≤0.5m 및 roundtrip≤2px로 지원한다. 0099_D는 기존113에 포함되나 평가용이라 기존 학습98에는 없다. 따라서 기존98의 지면 지원 부족을 전체937의 관측 부재로 확대할 수 없다. 이번 새 후보 선정은 부분 관측을 허용하며, 영역 크기와 선정 규칙을 함께 바꾼 개발 감사다.
