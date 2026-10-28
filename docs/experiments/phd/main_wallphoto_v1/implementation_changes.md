# 코드와 설정 기록

원본: scripts/phd/main_photocheck_v1, configs/phd/main_photocheck_v1/photocheck_v1.json.

- common.py: 시험 건물 일곱 이름을 사용한다. 공개 표·그림·묶음 사이에 작업 전용 잠금을 두고 JSON 저장을 임시 파일 뒤 원자 교체로 바꾸어 정시 묶음이 쓰는 중인 파일을 읽지 않게 한다.
- prepare.py, curves.py, features.py: 설정 파일 이름만 wallphoto_v1.json으로 바꾼다. prepare.py의 freeze/main은 호출하지 않고 group 함수만 쓴다.
- cameras.py, verify_core.py, verify_image_score.py: 원본 바이트 그대로 복사했다.
- group, 카메라 투영·선택, compute, derive: 설정 파일 이름을 제외한 구문 트리 일치 검사 통과. NCC 쌍별 식과 OpenCV 투영 대조 통과.
- 벽 처리: 새 wall_prepare.py와 wall_measure.py가 LoD2 kind=2만 고른다. 법선·접선·패치 식별자는 원본 값을 사용한다. 벽을 위해 연직 수식을 고친 줄은 없다.
- 새 wall_report.py, wall_figures.py는 완료된 사진 판단에만 참값을 연결한다. 참값 점검은 확대 결정에 들어가지 않는다.
- 줄인 경우 패치 판단 -1을 보존하며, 모름 2·3·4와 구분한다. 15개 후보 순서는 그대로다.
- 실행 조정: CPU 8개, 프로세스 12 GiB, 사진 임시 보관 2 GiB, 점 묶음 4096. 원래 32 GiB 상한 안에서 자원 경쟁을 줄이는 실행 조건이며 수식·사진·판단 설정은 바뀌지 않았다. kernel compute의 기본값을 수정하지 않고 호출 인자로 묶음 수만 준다.
- 자원 입장: MESHPATCH 양쪽 패치 표 완료 전에는 가용 메모리 68 GiB 이상을 60초 유지해야 한다. 양쪽 status가 table_complete이면 28 GiB 이상을 적용해 나머지 작업에 16 GiB를 남긴다. 과학적 PASS 여부로 실행 권한을 정하지 않는다.
- 확인용 벽의 점 묶기는 별도 holdout 경로에 저장하고 수만 시간 어림에 포함한다. 공개 묶음에는 점·판단을 넣지 않는다.
- 검증용 이전 벽 결과 24,041점은 validation 폴더에만 두고 새 시험의 숫자와 전달 묶음에서 제외한다.

설정 잠금 원본 SHA-256은 wallphoto_v1.lock.json에 있으며, 운영 제한은 runtime_profile.json에 분리했다. 변경 줄 전체는 source_changes.diff에 있다.

scientific_verdict: null
