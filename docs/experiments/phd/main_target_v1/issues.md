# PHD-MAIN-TARGET-v1 문제 기록

- r0 STOP_STAGE0_UNAVAILABLE_AREA: 10/31 사용자 결정으로 평가 범위만 분모에 넣고 같은 단위·면 종류 중앙값을 대체해 해소. 원본 결측은 그대로이며 대체 넓이를 별도 기록했다. 법선 결측은 유지한다.
- r0 STOP_STAGE0_UNCERTAINTY_JOIN: B173 자체 학습 영상 140장의 MVS와 원본 ALS로 고리 1.5 m 값을 새로 계산해 해소. 주변 값 전용 없음. 추가 두 판 단계 0 통과.
- SIGMA_PROVENANCE: 사용자가 10/26 방법 세션의 참값 없는 추정 과정과 참값 17.1 cm 점검 용도를 제공했다. 원 추정 독립 재현은 하지 않았다.
- ALS_BAND_STATUS1: 저장 띠 패치가 UNCERT 점군의 crop 범위 밖까지 이어지는 범위 불일치가 빈 원통 대부분을 설명한다. 원본 crop/패치 변경 없음; 사용자 결정에 따라 비중단 기록.
- PHOTO_CURVE_UNMATCHED: 실험 ALS 격자·정합과 전체 지역 사진 패치가 대부분 정확히 일치하지 않는다. 해당 사진 판단은 모름으로 고정. 인접 패치나 정합 제거 후 사진 곡선을 옮겨 쓰지 않았다.
- B173_ENV_LXML: 첫 준비 실행에서 GeoGS 이미지의 lxml 부재로 오류. 데이터 계산 전에 발생했으며 dev/GeoGS 역할 분리로 해결.
- B173_ZERO_NORMAL_WARNING: 원본 UNCERT 코드의 0 법선 정규화 경고를 보존. 대상 패치는 셀 수 없음으로 유지.
- REPORT_ARRAY_KEY: 최초 T2 그림 작성에서 NPZ 필드명을 잘못 읽어 실패. 저장된 abs_d/area 필드로 고쳤으며 수치 계산 변경 없음.
- 단계 0 독립 검사 PASS. 학습은 아직 시작하지 않았다. scientific_verdict: null.
