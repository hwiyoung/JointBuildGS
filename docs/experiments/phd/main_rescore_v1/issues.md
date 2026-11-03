# PHD-MAIN-RESCORE-v1 예외

- stage1 첫 실행은 읽기 전용 /repo 아래의 허용 스크립트 사본을 만들려다 차단됨. 계산 시작 전 실패. 호스트에서 허용 경로에 사본을 만들고 컨테이너에서는 읽기만 하도록 수정.
- stage0 Git diff 일반 검사는 생성 CSV의 CRLF를 공백으로 보고했다. 기존 CSV bytes는 유지하고 이후 검사에는 cr-at-eol을 적용한다.

- FIRST_MERGE_RECEIPT: streamed_tsdf.merge는 merged.ply 저장 후 mean_share_of_pixels_in_box 보조 항목 부재로 실패. 저장 파일과 타일 삼각형 합계를 대조해 복구. 원래 병합 피크 메모리 및 내부 정점 진단은 확인 불가로 유지한다. 원본 코드/타일은 변경하지 않음.
- FIRST_CLEANUP: 원본 Open3D의 83,029,035 삼각형 정리 호출이 완료 영수증 없이 종료됨. 후속 estimate는 final.json 부재로 실패. 종료 원인은 확인 불가(32 GiB 상한은 유지). 동일 공유변 연결 성분, 50번째 크기 문턱 및 동률, 최소 50 삼각형, 퇴화 삼각형 제거, 평가 범위 규칙을 bounded_cleanup.py/cleanup.cpp로 구현해 계속한다.

- 2026-11-04 01:59 KST: LoD2 장면 τ 선택 오류. 가장 가까운 사전 정보 패치 종류를 쓴 탓에 B173 주변 참값 3,881,308점 중 319,497점의 τ가 참값의 지붕·벽 종류와 달랐다. 4.3에 따라 장면 참값은 기존 vert_gt_points, 결과는 최근접 참값 면의 종류, 영역 참값은 기존 rows.kind로 τ를 적용한다. 기둥 소속과 거리 계산은 그대로다. ALS는 한 종류의 τ여서 영향 없음. 완료된 LoD2는 저장된 거리·결과 좌표로 재집계하며 수정 전 표와 τ 배열을 보존한다. scientific_verdict: null.

- CDGS 대형 병합 메모리: 원시 삼각형 1억 개 초과로 기존 일괄 병합이 32 GiB를 넘을 가능성. 실제 OOM으로 보고하지 않음. 디스크 배열/동일 순서 병합으로 예방하고 두 사례 바이트 일치 검증. 기존 실행 셸만 타일 완료 시 교체; scientific_verdict: null.

- B173 단계 게시: 추가 점검 해당 판이 없는 LoD2 빈 Markdown 표가 EOF 빈 줄 검사를 실패함. 빈 결과 표기 수정 후 게시 재개. 수치·메시·그림 재계산 없음.

- 2026-11-04 04:47 KST: B0 freeze_views가 원래 unseen.npz 부재로 실패. 원본 stage1 gpu_s1.py:307-314와 fill virtual/vv_defs.py:47-54에서 B0/R1은 가상 시점 대상이 아님을 확인. 발주 1.3·1.5·4.1에 따라 새 시점을 만들거나 학습 시점 메시를 최종 값으로 대체하지 않음. 미실행 freeze_views/run_site/target_quality/publish_tables/report/finalize를 수정하고 unavailable_virtual을 추가: 입력 채점·목표·기존 학습 메시를 계속하며 의존 최종 값은 확인 불가로 기록. B173 완료 결과는 재계산하지 않음.
