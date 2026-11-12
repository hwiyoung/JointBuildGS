# PHD-MAIN-JUDGECHECK-v2 문제와 정의 보충

- 2026-11-12T13:21:31+09:00: [정의 보충] '탐색 지역의 MVS'. 탐색 지역 일곱의 MVS(DISCARD mvs/<지역>)는 탐색 지역 밖 61동에 없고, 사진 점·시선 검사·고리 셈에 쓸 점·깊이도 그 MVS로는 만들어져 있지 않다. 그래서 전 건물에 같은 MVS인 WIDEN0-v2 캠퍼스 MVS(학습 819장)를 쓴다. 실험 지역 밖 건물에 이 MVS를 쓴 가장 가까운 앞 작업은 JUDGECHECK-v1이다. 확인(stage0/mvs_identity.json): 세 실험 지역 MVS(STAGE0 s61 export, 243/203/333장)는 WIDEN0와도 DISCARD와도 다른 실행이다(같은 영상 깊이가 같은 화소 0.01~0.18 %, 차이 중앙값 1.6~2.8 cm). 발주 3.3대로 본값 판은 WIDEN0 MVS, 세 지역의 지금 판은 JUDGEAPPLY/FINALTRAIN 파일.
- 2026-11-12T13:21:31+09:00: [정의 보충] 정합. WIDEN0-v2는 구역(100 m)마다 따로 정합해 패치 중심과 ALS 점을 옮겨 두었다(예: LoD2 6907_53359 1.136/−0.272 m, ALS 6911_53361 z −3.758 m). 발주(실험과 같은 정합)대로 이 이동은 쓰지 않고 raw_centre + 탐색 지역의 ALS 이동(DISCARD s52/s03 summary.json), LoD2 0을 쓴다. 탐색 지역 밖 61동은 이동 값이 없어 0으로 둔다.
- 2026-11-12T13:21:31+09:00: [정의 보충] 고리 R1.5 재사용. WIDEN0 u_mvs·als_u는 중심이 이 작업과 같은 패치(2,987,138개)만 다시 쓰고 나머지는 같은 커널로 새로 셈한다. WIDEN0 u_worker의 시드 패치 번호는 patch_id 숫자가 아니라 patch_geometry 파일 안의 차례였다(처음 시험에서 다르게 나와 찾음). 고친 뒤 재현 표본은 float32로 같다.
- 2026-11-12T13:21:31+09:00: [정의 보충] 시선 검사 입력의 u·σ_p 채우기(TARGET target_rules.uncertainties: 묶음 중앙값으로 채움)의 묶음은 JUDGECHECK-v1의 단위(건물)와 맞춰 건물:지붕/벽으로 한다.
