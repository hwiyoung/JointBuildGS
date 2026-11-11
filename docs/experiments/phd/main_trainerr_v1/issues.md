# PHD-MAIN-TRAINERR-v1 issues

scientific_verdict: null. 문제와 처리, 확인 불가를 시각 순으로 적는다.

- 2026-11-11T18:06:53.026886+09:00: 발표 50쪽 근거 check_cause_range.py가 저장소·원격·산출물·호스트(find /) 어디에도 없다. 3-가 덧붙임의 50쪽 비율은 설정 check3.page50 정의로 다시 센다(원래 코드와 같은지 확인 불가).
- 2026-11-11T18:06:53.026886+09:00: 참값 메시가 없다(GTJUDGE는 참값을 점군 그대로 쓰고 삼각화하지 않음). 보는 영상의 깊이 시험은 참값 점군 z-버퍼(화소별 최소 깊이, 5 cm)로 대신한다(설정 visibility).
- 2026-11-11T18:06:53.026886+09:00: 발주문의 '덧붙임 2 3.4 정확성 규칙' 문구가 GTJUDGE 설정에 없다. 0.1 표의 ③ 값(65.3·77.7)은 덧붙임 11·12의 normal_cylinder_1m 규칙 값이라 그 규칙을 쓰고, 옛 euclidean_1m 규칙 값도 함께 센다.
- 2026-11-11T18:15:59+09:00: 단계 0 첫 실행이 RESCORE geometry.columns의 반환값(owner, hits)을 하나로 받아 멈췄다(값 계산 전). 고쳐 다시 돌렸다(29 s). 첫 실행 때 docker가 아직 없던 r28 마운트 경로를 root 소유 빈 폴더로 만들었고, 지운 뒤 r27을 복사해 r28을 만들었다.
- 2026-11-11T18:15:59+09:00: 점 집합 파일. 두 docker 이미지 모두 parquet 엔진(pyarrow, fastparquet)이 없어 sets/<칸>_<판>_<lost|control>.npz(설정의 열 이름 그대로)와 같은 내용의 .csv.gz로 썼다.
- 2026-11-11T18:15:59+09:00: 작은 예제 첫 시도 10판이 시작 직후(2~14 s) 멈췄다. 상속 속도 렌더러 설치(main_finaltrain_v1/renderer.py)가 설정의 renderer 항목을 읽는데 잠근 설정에 없었다. 잠근 설정은 그대로 두고 common.cfg()가 FINALTRAIN finaltrain_v1.json의 renderer 항목(원래 판·GTJUDGE·TRAINLOG가 쓴 같은 .so, sha 확인)을 덧붙이게 했다. 실패 폴더는 probe_failed_1811/에 두었다.
