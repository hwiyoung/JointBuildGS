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
- 02:56 사-2(9,589 s)·사-3(8,899 s) 학습 끝, COMPLETED.
- 02:59–10:58 후처리 tile 넷이 cgroup 상한(60 GiB)에 걸려 멈춤 → 사-3 내림, 사-2 이어 하기(issues.md).
- 11:16 사-2 후처리 끝. 11:17–11:53 사-3 후처리 다시 실행 끝.
- 11:55–12:15 사 값 다시 계산(기록 판 메시 경로 대체 `mdir`), `사_요약.md`, `보고.md`(3,719자).

## 10절 점검

- [x] 첫 계산 전에 설정을 잠갔다(addendum4.json 00:14, addendum4_sa3.json, addendum4_b.json).
- [x] 자리마다 대조를 함께 냈다(가·나·다·라 표의 '대조' 줄, 사-2 모서리 옆벽·길 쪽 긴 벽).
- [x] 일 가 2.1의 줄 번호를 적고 그 파일을 묶음에 넣었다(`ga_code_check.csv`, 묶음 가의 `code/`).
- [x] 사건 수의 합을 자리마다 적었다(`ga_balance2_*`, 가우시안별 차례 셈: 모든 자리·창 잔차 0. 첫 셈 `ga_balance_*`는 겹친 사건을 두 번 세거나 빠뜨려 버림).
- [x] 모든 케이스(15)에 그림 넷과 요약 그림을 냈다. 단위·방향(카메라 쪽 화살표)·범례가 있고 내부 이름이 없다.
- [x] 높이 구간, 학습 판, 판정을 값마다 적었다.
- [x] 새 판(r31·r32)의 스위치를 모두 끈 단위 점검 결과를 적었다(사_요약.md).
- [x] 정량(표)과 정성(그림)을 함께 냈다.
- [x] `addendum4/`와 새 판 폴더 밖에 쓰지 않았다. 예외: payload `addendum4/` 아래 작업 결과, NVMe 작업 폴더(임시).
- 21:40–22:30 다시 확인 뒤 고침: 기록 판 메시 여덟 개 다시 채점(`tlre_*`), 사-2·사-3 값 다시 계산, 사건 수 맞추기 가우시안별 차례 셈(`ga_balance2_*`, 잔차 0), 일 라 이력 두 장면 추가(B0·B173 × 항공 LiDAR), 요약·보고 고침(issues.md).
- 22:20 사용자 결정("Start all now"): 추가 기록 판 다섯. 설정 `addendum4_c.json` 잠금(sha256 7c88cb04…, r31, 방법 설정 그대로). 22:24 sb4 B173 × LoD2(GPU 0), 22:26 sb1 B0 × LoD2 6,000(GPU 1) 시작. 대기열: sb2 → sb3 → sb5. 후처리 구동기 `a4_sb_post.py` 다섯(GPU 단계는 그 GPU에 학습이 없을 때만, 메시 작업자 하나씩).
