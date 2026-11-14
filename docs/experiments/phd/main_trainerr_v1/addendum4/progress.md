# PHD-MAIN-TRAINERR-v1 덧붙임 4 진행 기록

scientific_verdict: null. 발주문 `덧붙임4_발주문.md`. 설정 `configs/phd/main_trainerr_v1/addendum4.json`(잠금 2026-11-15 00:14, sha256 354d85c8…), 사-1 기록 설정 `addendum4_trainlog_sa1.json`(같은 잠금), 사-3 입력 규칙 `addendum4_sa3.json`(잠금 00:18, ebf2e247…), 자리·값 세부 `addendum4_b.json`(잠금 00:24, 7b8a8c5e…). 실행기 `scripts/phd/main_trainerr_v1/addendum4/a4_launch.py`(로그·tmp = payload addendum4/).

- 00:12 r31 = r30 커밋 파일 118개 바이트 사본(sha256 ALL_EQUAL) + `jbgs_a4.py` + `train.py` 네 곳 + `jbgs_trainlog.py` 두 줄. 바꾼 줄 `r31_changed_lines.diff`.
- 00:14 설정 잠금 → 사-1 시작(GPU 0).
- 00:15–00:16 r31 단위 점검 PASS: 결정 재생 r30 = r31(여섯 부분 바이트 같음), 함수 점검(기본값에서 멈춤 없음·지도 그대로), 바뀐 파일 = train.py·jbgs_trainlog.py·새 jbgs_a4.py(`payload addendum4/verification/`).
- 00:17 사-2 시작(GPU 1). 가림 무게 0 화소 4,753,239 / 목표 화소 138,095,510(3.4 %).
- 00:18–00:20 사-3 입력 만들기(78 s; `a4_sa3_build.py`, FINALTRAIN 함수 그대로).
- 00:21 r32(= r31 + 손실 둘째 항 스위치) 단위 점검 PASS: 재생 r31 = r32, 손실 식 점검, 바뀐 파일 = jbgs_a4.py·jbgs_target.py. 바꾼 줄 `r32_changed_lines.diff`.
- 00:23 일 가 2.1 코드 확인표 `tables/ga_code_check.csv`.
- 00:25–00:32 일 가 사건·수 맞추기·기울기(`a4_ga.py`). 수 맞추기 첫 셈은 자식이 물려받은 목표를 보지 않아 잔차가 컸다 → 자식은 물려받은 목표가 자리 안일 때만 '생김'으로 세도록 고쳐 다시 셈.
- 00:28 사-1 끝(810 s), 사-3 시작(GPU 0).
- 00:29–00:35 일 나 가림·색 무게(`a4_na.py`), 재구현 점검(CUDA와 누적 불투명도 차 ≤ 6.5e-5).
- 00:40 묶음 가·나(`delivery/PHD-MAIN-TRAINERR-v1_덧붙임4가_1115-0040.zip`, `…나_1115-0040.zip`), 커밋 fa8c44c7 푸시.
- 00:41–00:46 일 마(`a4_ma.py`, 두 장면 84 s·40 s). 첫 실행은 목표 파일 열 이름(region) 누락으로 실패 → 고쳐 다시.
- 00:43 GPU 이미지에 shapely가 없어 자리 점을 CPU에서 한 번 셈해 `payload addendum4/places/`에 담는 `place_points_cached`를 더함.
- 00:44–00:51 일 다 잘 보이는 벽 다섯 모델(`a4_da.py wall`, 43~137 s), 벽 앞·뜬 면·바닥 위 가우시안 계보(`front`), 가장자리 띠 가림(`edge`).
- 00:48–01:00 일 라 그리기(`a4_ra.py draw`, 장면당 2.5~7분, GPU 0), 고친 자리 대표 둘 고르기(`fixed_cases`).
- 00:53–01:00 일 바 그림 틀(`a4_ba.py`) 시험(R1 바닥 띠, 462 s) → 단면 창을 반폭 3~8 m로 좁히고 여백을 잘라 모든 케이스 두 줄로 실행.
- 00:55 일 다 'wrong' 대기 줄이 pgrep 자기 일치로 멈춤 → 직접 시작. (정리하려던 pkill이 지금 셸까지 끊어 다시 띄움.)
- 01:02 남쪽 끝 벽 '벽 뒤' 점에 거리 하한이 없어 건물 반대쪽까지 902,000점이 들어감 → addendum1 영역(벽에서 −5~+2 m)으로 고쳐 다시 셈. 앞 결과는 `wrong_south_unbounded_superseded.npz`로 남김.
- 01:03 사-2·사-3 후처리 구동기(`a4_sa_post.py`: ply → 메시 7,000·10,000·15,000·30,000 → 값) 대기 시작. NVMe 작업 폴더 `/home/innopam/jbgs_nvme_work/trainerr_a4`.
