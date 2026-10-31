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
- MAP_CAMERA_SCHEMA: 최초 지도 작성의 height/width 필드 오류를 기존 카메라의 H/W로 수정. 지도가 저장되기 전 발생했으며 목표·카메라 수치 변경 없음.
- MAP_SITE_NAME: B0 지도 완료 뒤 잘못 입력한 R1_b10에서 파일을 찾지 못해 종료. 정확한 고정 단위 R1rep_b10으로 실행했고 완료된 B0 지도는 재계산하지 않음.
- REPRESENTATIVE_JSON: 첫 대표 자리 잠금 시 numpy.float32 직렬화 오류. JSON 기본 수로 변환해 같은 선택 규칙과 값으로 저장. 어떤 렌더나 학습 결과도 보기 전 잠금 완료.
- DIAGNOSTIC_LAUNCH: 진단 실행기의 mount mode 변수와 작업 mode 변수 이름 충돌로 gpu_ro.py를 찾지 못함. 컨테이너에서 계산 전 종료. 이름 충돌을 고치고 최초 오류 명령/로그/영수증을 diagnose_commands/B173nb_b10_ALS_launch_error에 보존.
- INITIAL_RENDER_DEPTH_GATE: 발주문 3.5의 초기 깊이 절대 오차 중앙값 0.05 m 기준 미충족. B173 주변 ALS 39.562180 m, LoD2 17.064514 m(전체 학습 영상 목표 화소). 사전 패치 화소만도 각각 4.569275 m, 2.516720 m. 7,000회 점검과 본 학습은 미실행.
- BASELINE_SPARSE_BACKGROUND: 기존 영상 씨앗은 MVS 작업공간의 sparse SfM 점이다. B173 주변에 크기 42.538944 m의 배경 원반이 있고, 대표 영상에서 한 원반만으로 목표 화소 전체를 약 11.33 m 깊이로 덮음. 배경을 제외한 진단 렌더와 합성 평면 검사로 좌표 변환 오류와 구분했다. 그 진단을 초기화 변경이나 통과로 사용하지 않았다.
- ALS_ZERO_SEED_PATCHES: 기존 패치별 씨앗 수를 유지했으므로 기존 씨앗이 없는 유효 ALS 목표 패치에도 새 씨앗을 추가하지 않았다. 단위별 수는 stage1_seeds 표에 기록.
- TRAINING_NOT_VALIDATED: r19의 묶기·상속 단위 검사와 초기 렌더만 수행. 최적화·7,000회 건강·30,000회·최종 메시·채점 검증은 미실행. 사용자 초기화/기준 변경 결정 전 현재 중단을 유지.
- SOURCE_FORMAT: r19에 복사한 기존 파일의 줄 끝 공백은 원본 바이트 보존을 위해 유지했다. 증거용 unified diff의 빈 문맥 행도 유지한다. 새 단계 1 CSV는 LF로 저장했다. 새 작성 코드·설정·보고서의 별도 공백 검사는 통과했다.
