# 앞 작업과 달라진 곳 (설정·실행 명령·메시·채점)

scientific_verdict: null · 2026-11-19 · 앞 작업 = 세 평가 장면의 비교 방법 판(준비.md 2절 표의 판 폴더). 사실만 적는다.

## 1. 발주가 바꾸라고 한 것

| # | 무엇 | 앞 작업 | 이 작업 | 근거 파일 |
|---|---|---|---|---|
| 1 | 영역 | 장면 상자(약 100 m) | TRAINUNIT 넷 판 칸 넷(넓힌 경계 20 %), 칸 파일 그대로 | `configs/phd/main_base151_v1/base151_v1.json` (cells sha256) |
| 2 | 영상 목록 | 장면 학습·시험 목록 | 칸마다 TRAINUNIT 학습 목록(308/471/544/324장)과 시험 목록(41/54/53/38장) | `OUT/scenes/<방법>/cell<k>/split.json` |
| 3 | 사전정보 입력의 범위 | 장면 상자 | 칸 전체. 면 = WD `holdout/internal/prior_tiles`(결정 3) | `inputs_prior.json`, `tables/inputs_sizes.md` |
| 4 | 길쭉함 필터 | 없음 | 모든 학습 방법. 2DGS·GeoGS 짧은 축 ÷ 긴 축, CDGS 둘째 축 ÷ 가장 긴 축, **≤ 0.01**이면 복제·분할에서 뺀다(발주 글은 '< 0.01', TRAINUNIT 코드는 '≤') | `tables/method_filter.md` |
| 5 | GPU 상한 | TRAINUNIT 9 GiB 고정 | 걸기 직전 GPU 1 남은 메모리 − 2 GiB(칸마다 21.47~21.52 GiB) | `OUT/runs/<판>/cell<k>/attempt<a>/gpu_cap.json` |
| 6 | 합치기 | 없음(장면 하나) | 칸마다 학습 뒤 원래 칸 경계 안의 가우시안만 남겨 합침(2DGS 6,069,218개) | `OUT/runs/<판>/merged/` |

## 2. 실행 명령과 환경

| # | 무엇 | 앞 작업 | 이 작업 |
|---|---|---|---|
| 1 | 학습 진입 | `train.py` 직접 | `b151_entry.py`가 필터·기록(1,000회마다)·멈춤 저장을 감싼 뒤 같은 `train.py`를 부른다. 인자는 앞 작업과 같다: 2DGS `--eval -r 1 --data_device cpu`, GeoGS `--lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight -r 1 --iterations 30000 --stage_switch_iter 8000 --lambda_lod_init 0.08 --lambda_lod_anchor 0.005`, CDGS `--depth -r 1 --eval --use_predefined_depth` |
| 2 | 환경 변수 | 2DGS·GeoGS `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`, `JBGS_SPLIT_JSON`; CDGS 넘기지 않음, debug 끔 | 같다. 덧붙인 것: `JBGS_GPU_CAP_GIB`(상한), CDGS `B151_NODEBUG=1`(앞 작업 `jbgs_nodebug.py`와 같은 규칙), `B151_CWD` |
| 3 | 이미지 | `jointbuildgs:2dgs-official-f3e3b9f-v1`, `cdgs-official-db853c1-v1`, GeoGS `geogs-official-db40c95-compat-v1` | 앞 두 이미지와 2DGS의 바탕이 호스트에 없어 저장소 Dockerfile로 다시 지음(`*-b151`). 2DGS 바탕 = `geogs-official-db40c95-compat-v1`, CDGS = 원래 freeze 판으로 pip 고정. 11/19 18시에 이 이미지들이 다시 지워져 같은 방법으로 또 지음(2DGS `b97ade3c0050`, CDGS `cb11b4e1870e`; CDGS 꾸러미 47개 고정 판과 같음). GeoGS 학습 이미지는 같다 |
| 4 | DA3 | 장면 학습 영상, consec12 | 칸 학습 영상, consec12(같은 모형·설정) |
| 5 | LGDM의 MVS | 장면별 MVS(PREP `mvs/box_<장면>`) | WD 캠퍼스 MVS(JC2 본값 판이 쓴 것). 판정은 캠퍼스 학습 영상 819장, 합성은 칸마다 |

## 3. 메시

| # | 무엇 | 앞 작업 | 이 작업 |
|---|---|---|---|
| 1 | 4.1 메시 | RESCORE addendum3 'primary': 방법 자신의 TSDF(0.05 / 0.25 m, 장면 시점) + 정리 | TRAINUNIT-v2 규칙: 합친 모형을 장면 상자로 자르고, RESCORE `render_model.py`로 방법의 렌더러 깊이를 GTJUDGE 장면 시점에서 → 조각 TSDF(0.05 / 0.25 m) → 정리 |
| 2 | 4.2 메시 단위 | 없음 | 칸 × 100 m 구역(원래 칸 경계 안), z = 참값 5 % − 5 m ~ 최대 + 5 m, 시점 = 칸 학습 영상 가운데 단위 상자를 보는 것. 32 단위(`score151.json`) |
| 3 | LGDM 메시 | 패치판(RESCORE `render_patches.py`, GTJUDGE 'fusion') | 깊이를 합친 판(결정 2): 합친 깊이 → 같은 TSDF·정리. 4.1 장면 시점 가운데 캠퍼스 학습 영상이 아닌 것은 합친 깊이가 없어 빈 깊이(수는 렌더 영수증 `views_without_composite`) |
| 4 | 조각 TSDF 검사 | — | e_lat ≥ 0.5 m 단위 하나(c1_6909_53363, 0.5008 m)는 칸이 하나일 때만 검사를 넘김(대리 깊이 화소 0 확인). 한 칸 안 꼭짓점 번호 충돌은 GTJUDGE `recovery_merge.py` 규칙 |
| 5 | 작업 파일 위치 | 결과 폴더(HDD) | 11/19 17:43부터 새 단위의 작업 폴더는 NVMe(사용자 결정), 기록(.json)은 결과 폴더로 되돌림. 값 불변 |

## 4. 채점

| # | 무엇 | 앞 작업(GTJUDGE) | 이 작업 |
|---|---|---|---|
| 1 | 4.1 | GTJUDGE 채점기 | 같다(`add2_scores.metric_rows`, 3.4절 정확성 규칙) |
| 2 | 4.2 참값 행 | 장면 행 | JUDGECHECK-v2 점(세 장면 밖은 0.1 m 솎음), 151동 |
| 3 | 4.2 τ | 장면·종류마다 하나 | 점마다(지역·종류) |
| 4 | 4.2 정확성 표본 칸 | 윤곽 + 2 m 칸 | 짝지은 참값 행이 든 0.5 m 칸 |
| 5 | 4.2 행의 면 | — | 점이 든 칸의 메시(결정 1). 글자 그대로(건물 소속 칸의 메시) 값도 `완전성_문자대로` |
| 6 | 4.2 표본 0개 단위 | — | 남는 삼각형이 0개인 단위는 정확성 표본 0개로 저장(사용자 결정 '표본 없음', 11/20, `b151_score151.py` 132–137·148행). 해당 = CDGS ALS c0_6907_53359 하나. 완전성 행은 그대로 분모에 |

## 5. 없는 것

- 방법 값·규칙의 변경: 없음.
- 칸 나누기 다시 계산: 없음.
