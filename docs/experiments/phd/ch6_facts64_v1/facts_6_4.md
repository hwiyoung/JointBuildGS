<!-- PHD-CH6-FACTS64-v1 사실표 -->
# 6.4 사실 확인과 6.3 마무리 — 사실표 v1

- 작업: PHD-CH6-FACTS64-v1. 문서 세션의 '6.4 사실 확인과 6.3 마무리 발주문 v1'(사본 `발주문_v1.md`)을 실험 서버의 실행 세션이 실행했다. 2026-10-15 23:40 ~ 10-16 0시대. CPU만 썼고, 돌고 있는 채우기 작업(PHD-MAIN-FILL-v1)은 건드리지 않았다.
- 한 일: 이미 있는 설정, 코드, 실행 기록, 영수증, 보고서를 읽어 사실을 적었다. 학습, MVS, 판정, 지표를 다시 돌리지 않았다. 새로 센 것은 둘이다. 그림 6.1의 자리 표(발주문 2.7이 요청함)와 2.8-4의 대상 건물 벽 점 수(발주문 1절 1번 밖, 그 줄에 밝힘)다.
- 쓴 이: 2.1, 2.6, 3절은 에이전트 A, 2.2와 2.3의 가~라는 에이전트 B, 2.4와 2.5는 에이전트 C, 2.3 마와 2.8은 실행 세션이 썼다. 실행 세션이 '다름'의 근거를 원본에서 다시 확인했고, 세 줄의 상태를 '다름'으로 바꿨다(2.4-5, 2.5-9, 2.5-11; 까닭은 그 줄의 값 칸 끝).
- 사실 180줄: 확인 149, 다름 21, 확인 불가 10.
- 상태: 확인(파일에서 봄), 다름(지금 아는 것과 다름; 맞는 쪽과 근거를 그 줄에 적음), 확인 불가(파일에 없음; 무엇이 없는지와 구하는 법을 그 줄에 적음).
- 경로: 앞에 아무것도 없는 경로는 저장소(`JointBuildGS-exp`, 브랜치 `exp/main-experiment`) 안이다. `main_…/파일.md`처럼 폴더와 문서 이름만 적은 것은 `docs/experiments/phd/` 아래다. 페이로드(`JointBuildGS-artifacts/phase-payloads/` 아래)의 줄임은 P0 = `p0-audit`, PREP = `phd/main_prep_measure_v1/PHD-MAIN-PREP-MEASURE-v1`, DR = `phd/main_prep_discard_rule_v1/PHD-MAIN-PREP-DISCARD-RULE-v1`, S0~S3 = `phd/main_stage0_v1/PHD-MAIN-STAGE0-v1` ~ `phd/main_stage3_v1/PHD-MAIN-STAGE3-v1`, FX = `phd/main_fix_v1/PHD-MAIN-FIX-v1`, SB = `phd/main_baselines_v1/PHD-MAIN-BASELINES-v1`, SL = `phd/main_fill_v1/PHD-MAIN-FILL-v1`, GG = `phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`, MT = `phd/metrics_trial_v1/PHD-MAIN-METRICS-TRIAL-v1`, CH6 = `phd/ch6_support_v1/PHD-CH6-SUPPORT-v1`, F64 = `phd/ch6_facts64_v1/PHD-CH6-FACTS64-v1`(이 작업)이다.
- 지역: B0 = `B0_b10`, B173 주변 = `B173nb_b10`, B173만 = `B173_b0`, R1 = `R1rep_b10`. `<지역>`은 이 넷을 뜻한다. 영상 수 조건: 저자 15·9·3장(A15·A9·A3), 연직 포함 13·8·2장(N13·N8·N2).
- 같은 내용의 json: `facts_6_4.json`(줄마다 번호, 사실, 값, 근거, 확인 방법, 상태, 쓴 이). 근거로 쓴 설정 파일과 보고서의 사본은 전달 묶음의 `evidence/`에 있고, 목록은 `근거_목록.md`다.
- `scientific_verdict: null`. 판독과 권함은 분석자(에이전트)의 것이며 사람 검수 전이다.

## 0. 요약: 지금 아는 것과 다른 것, 확인 불가

### 지금 아는 것과 다른 것

**본 방법과 부록 D (2.1, 3절)**

1. 'LoD2 처음 방향 칸 방식'은 두 사전 정보 모두에 켰다. LoD2에서는 칸 법선이 면 법선과 같아 결과가 같고, 차이는 항공 LiDAR에서만 난다(각도 차 중앙값 3.6~4.1°). (2.1-7)
2. 패치 크기 0.25 m는 설정의 고정값이고 두 사전 정보에 같다. 부록 D의 '항공 LiDAR의 점 간격'은 앞선 작업이 평균 점 간격 약 0.21 m를 올려 0.25 m로 정한 근거를 뜻하며, 이번 네 상자에서 다시 구하지 않았다. (2.1-15, D-7)
3. 수평 이동을 받아들이는 조건이 부록 D보다 많다(네 방위 가운데 셋 이상에 맞춤 화소 5 % 이상, 2,000 화소 이상, 최대 10걸음, 1 cm 미만이면 멈춤, 끝에 학습 영상 전체로 다시 확인). 항공 LiDAR는 벽에도 지붕의 허용 오차를 쓰고, 허용 오차와 정합은 실험 지역이 아니라 탐색 지역에서 구해 상자에 고정했다. (D-3, D-5)

**MVS와 관측 신뢰도 마스크 (2.2)**

4. '동의하는 이웃 시점 2'는 소스 영상이 한 장뿐인 시점에서 1이 된다. 3단계 영상 수 조건에 있다(저자 3장과 연직 포함 2장은 모든 시점, 연직 포함 13장과 8장은 한 시점). 네 실험 지역과, 허용 오차와 정합의 값을 준 탐색 지역(B0, R1, R2)에는 없다. 값을 주지 않은 탐색 지역 R3E와 R4에는 두 시점씩 있다. (2.2-11)
5. 방법론 4.2의 '깊이 차이를 허용할 비율'은 실제 마스크에 없다. COLMAP의 기하 거르기는 동의 시점 수(2)와 재투영 거리(1 화소)만 본다. (2.2-14)
6. 'R1 항공 LiDAR 건물 면 신뢰도 81 %'는 LoD2 건물 면에서 센 값이다(81.31 %). 항공 LiDAR 면에서 센 값은 기록에 없다. (2.2-19)

**허용 오차와 정합 (2.3)**

7. 허용 오차와 정합을 구한 탐색 지역 MVS에 실험 지역 평가 영상 대부분이 들어 있다. B0 35장 가운데 26장, B173 주변 29장 가운데 25장, B173만 20장 가운데 19장, R1 49장 가운데 43장이다. 상자 MVS, 학습 전 판정, 학습에는 평가 영상이 없다. 영향은 새 계산 없이는 알 수 없다. 에이전트 둘이 따로 찾았고 실행 세션이 다시 세었다. (2.3-4, 2.6-14)
8. 6장 보조 보고서 6절 답 4번의 216 m²는 1~4τ의 넓이다. 항공 LiDAR가 1~2τ 어긋난 넓이는 고르는 곳 184 m², 평가 지역 11 m²다. (2.3-25)

**배수를 고른 준비 측정 (2.4)**

9. 6장 보조 작업이 말한 '준비 측정 2.5'는 배수를 고른 측정이 아니다. 배수는 둘째 준비 측정(버리는 기준, 10월 5일)에서 비교했다. (2.4-5)
10. 결과 전에 적어 둔 후보는 열 가지다. 부록 D의 목록에는 비대칭 규칙과 허용 오차 0.5배, 2배가 빠졌다. 2배는 판정이 '여유(모두) 2'와 같아 판정이 다른 후보는 아홉이다. (2.4-10)
11. 항공 LiDAR 2배는 분석자 추천이 아니라 사용자 결정(10월 6일)이다. 분석자는 '전파에만 두는 여유 2'를 권했고, 지지 패치까지 2τ로 올리는 것은 잘못 버림 −59 %와 잘못 지킴 +57 %를 맞바꾸는 일이라 사용자 판단으로 남겼다. LoD2 1배는 추천과 같다. (2.4-19)
12. '넓은 평지붕을 영상이 20~30 cm 낮게'는 첫째 준비 측정이 R4와 R3E 탐색 지역(평가 상자 밖)에서 본 것이다(0.15~0.3 m). R1이 아니고, 둘째 준비 측정은 그 크기를 다시 구하지 않았다. (2.4-23)

**비교 방법 (2.5)**

13. GeoGS의 DA3 묶음 축척 고침은 B173 주변에만 들었다. 가림 검사 고침은 네 지역 모두에 들었다. (2.5-9)
14. GeoGS 항공 LiDAR 판의 '수치표면모델 메시'는 항공 LiDAR 삼각망(분류 2·6 점)의 건물 부분이다. 저장소의 '수치표면모델'은 다른 사전 정보의 이름이다. (2.5-11)
15. MVS 기반 결합의 2 m 규칙은 x·y 축 방향이 아니라 최소 넓이 회전 사각형의 두 변이다. 넓이 4 m² 이상, 높이 차 중앙값 2 m 이상과 함께 본다. (2.5-18)
16. 결합은 'COLMAP MVS 표면'으로 채우지 않는다. 시점마다 변화 칸은 MVS 깊이, 나머지는 정합한 사전 정보의 깊이로 합치고, 이것을 모든 방법과 같은 TSDF로 메시로 만든다. (2.5-20)
17. CDGS의 변형 여덟 판은 어댑터 v3(v2에 시점마다의 크기 맞추기를 건너뛰는 설정 하나를 더한 판)다. v2 그대로 도는 것은 B0 LoD2의 공식 확인 한 판뿐이다. (2.5-24)

**모든 방법에 같은 조건 (2.6)**

18. 평가 영상은 학습에서 빼기만 하는 것이 아니다. 화질(PSNR, SSIM, LPIPS)과 부유 가우시안이 가린 화소의 몫에 쓴다. 기하 지표에는 쓰지 않는다. (2.6-13)

### 확인 불가

1. 부록 B의 본문이 실험 서버에 없다. 그래서 '부록 B와 D에 없는 바꾼 설정'은 부록 D의 목록과만 비교했다. (2.1-16)
2. 이 네 상자의 항공 LiDAR 점 간격은 구한 기록이 없다. 상자마다 분류 2·6 점 수를 평면 넓이로 나누어야 한다. (2.1-15)
3. MVS 명령에 넘긴 다섯 값이 COLMAP 4.0.4의 기본값과 다른지 알 수 없다. 고정 이미지가 이 서버에 없고 도움말 기록도 없다. (2.2-6)
4. 항공 LiDAR 면에서 센 신뢰도 1 몫은 기록이 없다. (2.2-20)
5. 허용 오차를 구할 때 이상치로 지운 몫(3 NMAD 밖)은 실제로 쓴 값에 기록이 없다. 표본 수는 있다. (2.3-11)
6. 배수를 고르는 기준이 결과 전에 적혔는지 알 수 없다. 보고서는 '설정에 미리 적은 기준'이라 하지만 설정 파일에 그 문장이 없고, 그 작업의 발주문도 없다. 후보, 세는 법, 고르는 곳은 결과 전에 적혔다. (2.4-16)
7. 10월 6일 결정에 사용자가 직접 적은 까닭은 없다. 설정과 코드의 문장은 결정 요청의 까닭을 옮긴 것이다. (2.4-20)
8. 사용자가 평가 범위의 수를 보지 않고 골랐는지 알 수 없다. 결정 요청에 상자 넷의 평가 범위 수가 '보고만'으로 함께 실렸다. (2.4-21)
9. '고르게 낮게'의 '고르게'는 두 준비 측정 어디에도 없는 말이다. (2.4-25)
10. CDGS의 결과, 끝까지 돈 설정, 최종 메시는 아직 없다. 채우기 작업이 돌고 있다(10월 16일 0시 무렵 B0 LoD2 두 판이 약 48 %). (2.5-29, 2.6-4)
11. 표정을 제공자의 OPF 원본과 바로 비교하지 않았다. 937장 모델의 표정과 같다는 것까지 확인했다. (2.6-16)

## 2.1 본 방법 (일 1)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.1-1 | 바탕 구현: GeoGS 저장소와 커밋 | github.com/zqlin0521/GeoGS, 커밋 db40c95c657ec03ff21c83cb99cf39f4e90247a6 (2026-08-25, 'Add GeoGS training, rendering, and evaluation pipeline'). 포크의 기록 파일에 같은 커밋이 적혀 있다. 학습 이미지 `jointbuildgs:geogs-conf-guided-v1`은 공식 GeoGS 이미지(`geogs-official-db40c95-compat-v1`)에 TensorBoard만 더한 것이다. 그 이미지는 래스터라이저 소스를 고치지 않았고, 저자가 시험한 환경과는 CUDA 컴파일러(12.1, 저자 12.4)와 Matplotlib 판(3.9.2)만 다르다. | GeoGS 사본 `GG/sources/GeoGS` (git log: 커밋 하나, 작업 트리 변경 없음); `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_instrumentation.json:2`; `Dockerfile.geogs-conf-guided-v1:1-3`, `Dockerfile.geogs-compat-v1:1-10`, `Dockerfile.geogs-v1:1-27`; 1단계 GeoGS 영수증 `stage1/R1rep_b10/trust_LoD2/receipt.json` (official_commit) | git log와 git status를 읽기만 하는 꼴로 돌림, 파일 읽기 | 확인 |
| 2.1-2 | 포크가 공개 구현에서 바꾼 파일 | r14와 공개 구현의 차이는 네 파일(`train.py`, `scene/gaussian_model.py`, `scene/dataset_readers.py`, `utils/camera_utils.py`)과 더한 파일(`jbgs_*.py`, 판정 모듈 `src/phd/prior_propagation_v6`)뿐이다. 렌더러(`gaussian_renderer/`)와 학습 인자 파일(`arguments/__init__.py`)은 공개 구현과 같다. | diff -rq 결과(공개 사본 대 r14); `docs/experiments/phd/main_stage0_v1/provenance/build_report_r12.json`, `docs/experiments/phd/main_stage2_v1/provenance/build_report_r13.json`, `docs/experiments/phd/main_fix_v1/provenance/build_report_r14.json`, `docs/experiments/phd/main_stage3_v1/provenance/build_report_r15.json` | 공개 사본과 포크를 diff -rq로 비교, 짓기 기록 읽기 | 확인 |
| 2.1-3 | 1단계 r12와 이후 r14가 같은 결정을 내린다는 기록의 자리 | 두 단계로 확인되어 있다. 첫째, r13 기본값 = r12: 학습 전 계산 여섯 단위에서 배열과 값의 차이 0, 1단계 15,000회 체크포인트의 한 반복 다섯 곳에서 결정 차이 0, 시험 8개 통과. 둘째, r14 = r13: 학습 전 계산 일곱 단위와 체크포인트 여섯 곳에서 배열과 손실 값까지 같음, 시험 11개 통과. r15는 r14에 메모리 부족 기록만 더한 판으로 판정 파일과 가우시안 모델 파일이 r14와 같다. 첫째 비교에는 B173만이 없고, 둘째 비교에 B173만 LoD2가 들어 있다. | `docs/experiments/phd/main_stage2_v1/본실험_2단계_준비보고_v1.md:20-23, 71-101`; `S2/checks/compare_dry.md`, `compare_probe.md`; `docs/experiments/phd/main_fix_v1/본실험_고침_준비보고_v1.md:12, 35-73`; `FX/checks/compare_dry.md`, `compare_probe.md`; `docs/experiments/phd/main_stage3_v1/provenance/build_report_r15.json` (jbgs_judgment_equal_r14, gaussian_model_equal_r14); `tests/phd/test_fork_r13_ablations.py`, `test_fork_r14_memory.py`, `test_fork_r15_oom_record.py` | 보고서와 비교 표, 짓기 기록 읽기 | 확인 |
| 2.1-4 | 반복 수 | 30,000회. 본 방법의 모든 학습 영수증 명령에 `--iterations 30000`이 있다(0~3단계와 고침 작업). | `configs/phd/main_stage0_v1/stage0_v1.json:90`; `configs/phd/main_stage1_v1/train_plan_v1.json:8`; 영수증 예 `S1/stage1/R1rep_b10/prop_LoD2_s0/receipt.json` (command) | 영수증 명령 줄을 모두 읽음 | 확인 |
| 2.1-5 | 영상 크기 | 1024 × 741. 1400 × 1013 왜곡 보정 영상을 이 크기로 줄여 JPEG로 둔 파일을 `-r 1`(크기 그대로)로 읽는다. 네 지역 장면의 영상 1,052장(겹침 포함)이 모두 1024 × 741이다. 이 영상에서는 GeoGS 기본값 `-r -1`도 크기를 바꾸지 않는다(폭 1,600 이하). | `S0/fork_inputs/s61/<지역>/fork_inputs.json` (rule, resolution); `scene_LoD2/jbgs_calibration.json`; 명령의 `-r 1`; `configs/phd/main_prep_measure_v1/prep_v5.json` (render.grid); `GG/sources/GeoGS/utils/camera_utils.py:18-38` | 파일 읽기, JPEG 머리에서 폭과 높이를 셈 | 확인 |
| 2.1-6 | 씨앗 | 0과 1. 지역 × 사전 정보마다 두 번 돌렸다. 씨앗 0은 GeoGS의 safe_state 씨앗 그대로이고, 1은 그 뒤 random, numpy, torch를 1로 다시 놓는다. B173만 LoD2는 씨앗 1이 1단계 r12, 씨앗 0이 고침 작업 r14다. 1단계 r12의 씨앗 0은 GPU 메모리 부족으로 네 번 멈췄다. | `configs/phd/main_stage0_v1/stage0_v1.json:91`; `configs/phd/main_stage1_v1/train_plan_v1.json` (runs); `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:302-309`; 영수증의 `--jbgs_seed`; `FX/runs/B173_b0/prop_LoD2_s0/receipt.json`; `S1/stage1/B173_b0/prop_LoD2_s0*/receipt.json` (OOM 네 번) | 설정, 코드, 영수증 읽기 | 확인 |
| 2.1-7 | 'LoD2 처음 방향 칸 방식'이 무엇인지 | 사전 정보에서 심은 가우시안을 납작한 원판으로 두고, 원판의 법선을 그 점이 처음 놓인 패치 칸의 면 법선(바깥쪽, 위쪽)으로 맞추는 방식이다. 패치가 없는 점은 파일의 법선을 쓰는데, LoD2는 면의 법선이고 항공 LiDAR는 둘레 삼각형의 넓이 가중 평균 법선(꼭짓점 방식)이다. [다른 점] 이 방식은 LoD2만이 아니라 두 사전 정보 모두에 켰다(`--jbgs_prior_normal_mode cell`). LoD2에서는 칸 법선과 면 법선의 각도 차가 0°(최대 약 0.000001°)라 결과가 같고, 차이는 항공 LiDAR에서만 난다(중앙값 3.6~4.1°, 95 % 값 16~20°, 칸이 있는 점은 항공 LiDAR 점의 48~79 %). | `src/phd/prior_propagation_v6/orientation.py:1-18`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:84-87, 266-268, 1176-1232`; `configs/phd/main_stage0_v1/stage0_v1.json:94`; `configs/phd/main_stage1_v1/train_plan_v1.json:8`; 학습 기록 `S1/stage1/<지역>/prop_*_s0/model/monitor/meta.json` (r6.init_filter.orientation) | 코드와 설정 읽기, 학습 기록의 각도 통계 읽기 | 다름 |
| 2.1-8 | GPU 모델과 메모리 | NVIDIA GeForce RTX 3090 두 장, 장마다 24,576 MiB. GPU 하나에 학습 하나씩 두 학습을 함께 돌리고, 후처리는 하나씩 했다. 호스트 메모리는 125 GB이고 다른 서비스가 약 60 GB를 쓴다. | `nvidia-smi --query-gpu=name,memory.total` (10-16 0시 무렵 읽음); `configs/phd/main_stage1_v1/train_plan_v1.json:10`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_보고서_v1.md:590`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:265` | nvidia-smi 읽기, 설정과 보고서 읽기 | 확인 |
| 2.1-9 | 학습 한 번의 시간(지역마다, 벽시계) | 본 방법 16회(네 지역 × 두 사전 정보 × 두 씨앗): 62.6~82.1분. B173 주변 63.6~68.2분, B0 63.6~72.1분, R1 63.1~79.6분, B173만 62.6~82.1분. B0 영상 수 조건(2·3단계, 학습 영상 2~13장): 24.0~53.6분. 벽시계는 docker 실행 전체라 초기화(약 1분), 다시 읽기, 기록 렌더가 들어 있고, 다른 GPU의 학습과 함께 돈 값이다. B173 주변 0단계의 나눔: 학습 고리 51~55분, 다시 읽기 8분(60회), 기록 렌더 1분. | 영수증 `wall_seconds`: `S0/stage0/b{1,2}_{LoD2,ALS}/receipt.json`, `S1/stage1/<지역>/prop_*/receipt.json`, `FX/runs/B173_b0/prop_LoD2_s0/receipt.json`, `S2/runs/B0a15/prop_LoD2_s0/receipt.json`, `S3/runs/B0{a9,a3,n13,n8,n2}/prop_LoD2_s*/receipt.json`; `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md:301-314` | PASS 영수증만 읽어 가장 작은 값과 큰 값을 셈 | 확인 |
| 2.1-10 | GPU 메모리 최대(덧붙임) | 본 방법 16회의 nvidia-smi 최대 12,170~23,352 MiB. B173만 LoD2 씨앗 0은 r12에서 24 GB를 넘겨 멈췄고, 판정 지도를 CPU에 둔 r14로 18,999 MiB에서 끝났다. B0 연직 포함 13장 본 방법은 두 번 멈춘 뒤 래스터라이저 고침(cull3)으로 끝났다. | 영수증 `gpu_memory_used_mib`; `docs/experiments/phd/main_fix_v1/본실험_고침_준비보고_v1.md:35-48`; `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md:10, 410-445` | 영수증과 보고서 읽기 | 확인 |
| 2.1-11 | GeoGS에서 쓰지 않는 것: DA3 단안 깊이 항 | 쓰지 않는다. 명령에 `--da_depth_path /p/fork_none`(빈 폴더)과 `--lambda_da_depth 0.0`이 있다. 판정 모드의 손실은 색 손실, 깊이 왜곡, 법선 일치, λ_MVS × MVS 항, λ_prior × 사전 정보 항뿐이라 GeoGS의 두 깊이 항은 손실에 들어가지 않는다. 학습 기록에 'Depth directory not found: /p/fork_none/raw_depth'가 남아 있다. | `scripts/phd/main_stage0_v1/run_fork_v6.py:46-48`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:225-228, 873-875`; `S1/logs/train_R1rep_b10_prop_LoD2_s0.log:18-23` | 명령, 코드, 학습 기록 읽기 | 확인 |
| 2.1-12 | GeoGS에서 쓰지 않는 것: 처음 점 | 쓰지 않는다. `--lod_init`이 없어 GeoGS의 LoD2 표본(`sparse_lod`) 대신 `sparse/0`을 읽는다. 그 안의 처음 점은 0단계가 만든 것이다: 상자 학습 영상 부분 모델의 3차원 점(상자 범위 안)과, LoD2는 패치 중심 하나씩, 항공 LiDAR는 TIN 꼭짓점. 판정이 충돌인 결측 패치의 점은 심지 않는다. 포크 안의 `data/generate_pcd.py`는 아무도 부르지 않는다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:1413-1416`; `scripts/phd/main_prep_discard_rule_v1/fork_inputs.py:110-170`; `fork_inputs.json` (rule); `docs/experiments/phd/main_fix_v1/본실험_고침_준비보고_v1.md:164`; meta.json (r6.init_filter) | 코드, 입력 기록, 보고서 읽기 | 확인 |
| 2.1-13 | GeoGS에서 쓰지 않는 것: 그 밖(덧붙임) | GeoGS의 두 단계(LoD2 깊이로 8,000회 닻 내리기와 정제 단계의 LoD2 닻), 건물 보호(`--lod2_pcd_path`, `--protect_bldg`, `--freeze_onlybldg`), 동적 깊이 가중(`--dynamic_depth_weight`)도 쓰지 않는다. 명령은 `--stage_switch_iter 0 --lambda_lod_init 0.0 --lambda_lod_anchor 0.0 --lod_depth_path /p/fork_none`이고 저자 깃발 넷은 없다. 보호는 판정 모듈의 보호가 맡고, GeoGS의 frozen_mask 길을 다시 쓴다. | `scripts/phd/main_stage0_v1/run_fork_v6.py:46-48`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:334-335, 1114-1147`; 공개 README의 학습 명령 `GG/sources/GeoGS/README.md` | 명령과 코드 읽기 | 확인 |
| 2.1-14 | 패치 크기(설정 값) | 0.25 m. 학습에 넣은 판정 저장소 여덟 개(네 지역 × 두 사전 정보) 모두 `sp = 0.25`이다. 칸 하나의 넓이는 0.0625 m²다. | `configs/phd/main_prep_measure_v1/prep_v5.json:151`; `S0/fork_inputs/s61/<지역>/store_<사전 정보>.npz` (sp); `src/phd/prior_propagation_v6/locations.py:93-130` | npz 안의 sp.npy를 표준 라이브러리로 읽음 | 확인 |
| 2.1-15 | 패치 크기의 근거(항공 LiDAR 점 간격에서 정했는지) | 본 실험의 설정에는 근거 없이 값만 있다. 근거 규칙은 앞선 작업의 설정에 있다: '드문 쪽 자료의 평균 점 간격을 올림(항공 LiDAR 약 22점/m² → 0.21 m → 0.25 m)'. 값은 지역마다 다시 구하지 않았고 LoD2에도 같은 0.25 m를 쓴다. 이 네 상자의 항공 LiDAR 점 간격을 구한 기록은 없다. 확인하려면 상자마다 항공 LiDAR 2·6 분류 점 수를 평면 넓이로 나누어야 한다(새 계산이라 하지 않음). | `configs/phd/region_unit_v1/run_v1.json:165, 204`; `docs/experiments/phd/mvs_als_surface_patch_v1/SOURCE_DECISION_METHOD_DESIGN_ko_v2.md:1231`; `configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json:63`; `configs/phd/main_prep_measure_v1/prep_v5.json:151` | 설정과 설계 문서에서 찾음 | 다름 |
| 2.1-16 | 부록 B와의 대조 | 부록 B의 본문을 이 저장소와 이웃 저장소에서 찾지 못했다. 그래서 아래 '기본값에서 바꾼 것'은 발주문 3절의 부록 D 목록과만 비교했다. 부록 B가 이미 적은 항목이 섞여 있을 수 있다. | `docs/experiments/phd/ch6_facts64_v1/발주문_v1.md:38, 43, 131`; 저장소 문서 찾기(부록 B 본문 없음) | grep으로 '부록 B' 찾기 | 확인 불가 |
| 2.1-17 | 기본값에서 바꾼 것(부록 D 목록에 없음): 주점 | 공식 읽기 코드는 시야각만 써서 주점을 버린다. 포크는 장면의 `jbgs_calibration.json`으로 주점을 살린다(중심에서 2.4, −4.4 px). 영상은 고치지 않는다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/utils/camera_utils.py:13, 52-56`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_camera_adapter.py:14-50`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:272-273` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-18 | 기본값에서 바꾼 것(부록 D 목록에 없음): 평가 나눔 | 공식은 이름순 8장마다 1장(번호 기준). 포크는 `JBGS_SPLIT_JSON`의 split.json 이름 목록을 쓴다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/scene/dataset_readers.py:374-386` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-19 | 기본값에서 바꾼 것(부록 D 목록에 없음): 입력 영상 | 1400 × 1013 왜곡 보정 영상을 1024 × 741로 줄여 JPEG 95로 저장, `-r 1`. | `S0/fork_inputs/s61/<지역>/fork_inputs.json` (rule) | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-20 | 기본값에서 바꾼 것(부록 D 목록에 없음): 처음 점과 처음 회전 | 처음 점은 0단계의 점(위 표). 사전 정보 출신 가우시안의 처음 회전은 면 법선(칸 방식). 공식은 무작위 회전. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1176-1232`; `src/phd/prior_propagation_v6/orientation.py:1-18` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-21 | 기본값에서 바꾼 것(부록 D 목록에 없음): 심지 않는 점 | 판정이 충돌인 결측 패치의 사전 정보 점은 심지 않는다(init_exclusion). | meta.json (r6.init_filter.rule); `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:62-70` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-22 | 기본값에서 바꾼 것(부록 D 목록에 없음): GeoGS 항을 끈 명령 | `--stage_switch_iter 0 --lambda_lod_init 0.0 --lambda_lod_anchor 0.0 --lambda_da_depth 0.0`, 빈 깊이 폴더, 저자 깃발 넷 없음. | `scripts/phd/main_stage0_v1/run_fork_v6.py:46-48` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-23 | 기본값에서 바꾼 것(부록 D 목록에 없음): 보는지 검사 | 다시 읽기에서 점이 렌더 깊이보다 0.5 m 넘게 뒤에 있으면 가려진 것으로 본다(`--jbgs_e_depth_tol 0.5`). 누적 불투명도 0.05 미만 화소는 가리지 않는다(`--jbgs_e_alpha_min 0.05`). | `configs/phd/main_stage0_v1/stage0_v1.json:93`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:160-170, 245-247` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-24 | 기본값에서 바꾼 것(부록 D 목록에 없음): 다시 읽기 표본 | 패치 칸마다 3 × 3 표본점으로 다시 읽는다(`--jbgs_reread_samples 3`). | `configs/phd/main_stage0_v1/stage0_v1.json:93`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:274` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-25 | 기본값에서 바꾼 것(부록 D 목록에 없음): 깊이 항 나누기 | 두 깊이 항을 그 시점의 화소 수로 나눈다(`--jbgs_depth_norm pixels`). | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:252-253, 1320-1327` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-26 | 기본값에서 바꾼 것(부록 D 목록에 없음): MVS 깊이 항의 꼴 | 관측 신뢰도(0 또는 1)로 가중한 L1이고 허용 구간과 절단이 없다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:361-375, 1320-1333` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-27 | 기본값에서 바꾼 것(부록 D 목록에 없음): 사전 정보 깊이 항의 화소 가중 | 충돌로 판정된 패치의 화소는 0, 그 밖은 1. 패치가 없는 화소는 신뢰도 1이면 자기 표시(항공 LiDAR는 2τ로), 0이면 1. 학습 시작 때 한 번 정한다. | `src/phd/prior_propagation_v6/rule.py:86-93`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1233-1262` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-28 | 기본값에서 바꾼 것(부록 D 목록에 없음): 시점 표시의 동률 | 한 시점에서 일치 화소 수가 충돌 화소 수 이상이면 그 시점은 일치로 센다. | `src/phd/prior_propagation_v6/rule.py:43`; `configs/phd/main_prep_measure_v1/prep_v5.json:156` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-29 | 기본값에서 바꾼 것(부록 D 목록에 없음): 보호의 세부 | 학습률 0.01배는 자리, 회전, 크기의 갱신에만 걸린다(불투명도와 색은 그대로). 보호된 가우시안은 분할, 복제, 제거, 불투명도 다시 놓기에서 빠진다. 충돌 패치 위 가우시안은 보호하지 않는다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1462-1510, 1672-1699`; `src/phd/forks/GeoGS-conf-guided-v1-r14/scene/gaussian_model.py` (density_exempt, reset_opacity) | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-30 | 기본값에서 바꾼 것(부록 D 목록에 없음): 다시 읽는 때 | 1회째와 500의 배수에, 그 반복의 처음(불투명도 다시 놓기 전)에 읽는다. 1회째는 사전 정보 렌더로 가림을 본다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:512-515, 1462-1481`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:815` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-31 | 기본값에서 바꾼 것(부록 D 목록에 없음): 시험·저장 반복 | `--test_iterations 7000 15000 30000`, `--save_iterations 15000 30000` (기본 8,000과 30,000). 기록만 바뀐다. | 영수증 명령; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:1326-1327` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-32 | 기본값에서 바꾼 것(부록 D 목록에 없음): 메모리 설정 | 모든 학습에 `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`(할당기만, 10-06 사용자 결정). | `configs/phd/main_stage1_v1/train_plan_v1.json:8`; 영수증 pytorch_cuda_alloc_conf | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-33 | 기본값에서 바꾼 것(부록 D 목록에 없음): r14의 메모리 고침 | 판정 지도를 CPU 고정 메모리에 두고 읽을 때 GPU로 옮긴다. `--data_device cpu`도 넘기지만 영상에는 효과가 없다. 결정과 값이 r13과 같음을 확인했다. | `docs/experiments/phd/main_fix_v1/본실험_고침_준비보고_v1.md:35-73` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-34 | 기본값에서 바꾼 것(부록 D 목록에 없음): 래스터라이저 고침 | 3단계 B0 연직 포함 13장 본 방법 한 판만 cull3 래스터라이저로 돌았다. 순전파와 반지름은 시험 38장에서 비트까지 같고, 기울기는 상대 1e-7~1e-6 차이다. | `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md:410-445`; `S3/runs/B0n13/prop_LoD2_s0/receipt.json` (image) | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-35 | 기본값에서 바꾼 것(부록 D 목록에 없음): 감시 기록 | 100회마다 기록, 장면 기록 2·5·10·15·20·30천 회, 덤프와 기록 렌더는 30,000회. 학습 계산은 바꾸지 않는다고 기록됨. | `configs/phd/main_stage0_v1/stage0_v1.json` (records); `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md:567` | 명령, 설정, 코드 읽기 | 확인 |
| 2.1-36 | GeoGS 기본값 그대로인 학습 설정(참고) | 30,000회, 자리 학습률 일정(30,000회까지), 색 손실의 SSIM 몫 0.2, 깊이 왜곡 가중 0, 법선 일치 0.05(7,000회 뒤), 밀도 제어 500회 뒤부터 15,000회 전까지 100회마다, 기울기 문턱 0.0002, 불투명도 0.05 미만 제거, 3,000회 뒤 화면 20 px 넘는 것 제거, 불투명도 다시 놓기 3,000회마다, SH 차수 3, 검은 배경. 명령에서 바꾸지 않았다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/arguments/__init__.py:47-130` (공개 구현과 같은 파일); `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:862-863, 1114-1147`; `configs/phd/main_stage0_v1/stage0_v1.json:95` | 코드와 명령 읽기 | 확인 |

## 2.2 MVS와 관측 신뢰도 마스크 (일 2)

### 2.2 가. MVS

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.2-1 | MVS 도구와 이미지 | COLMAP 4.0.4, 이미지 colmap/colmap@sha256:187ca5ec98e5…(GPU). 본 실험이 쓴 MVS 13개(상자 넷, 영상 수 조건 여섯, 탐색 지역 B0·R1·R2 셋)를 포함한 작업 공간 23개의 영수증이 모두 이 이미지이고 종료 코드 0이다. P0의 판 기록이 이 이미지를 4.0.4로 적었다. | `scripts/phd/main_prep_measure_v1/run_colmap.sh:11`; `scripts/phd/main_prep_discard_rule_v1/run_colmap.sh:11`; `scripts/phd/main_stage0_v1/run_colmap.sh:11`; `PREP/mvs/<이름>/colmap_receipt.json:1`; `DR/mvs/<이름>/colmap_receipt.json:1`; `S0/mvs/<이름>/colmap_receipt.json:1`; `P0/runs/t3_mvs_20260611_230138/versions.txt:9,27`; `phases/p0-audit/env/docker-compose.p0.yml:19-21` | 스크립트, 영수증 23개, 판 기록을 읽음 | 확인 |
| 2.2-2 | MVS 명령 | docker run --rm --gpus device=<번호> --network none … colmap patch_match_stereo --workspace_path /ws --workspace_format COLMAP --PatchMatchStereo.geom_consistency true --PatchMatchStereo.max_image_size 1024 --PatchMatchStereo.num_iterations 3 --PatchMatchStereo.filter true --PatchMatchStereo.cache_size 32 --PatchMatchStereo.gpu_index 0. 준비 측정, 버리는 기준, 0단계의 세 스크립트가 작업 폴더와 이름표만 빼고 같다. 스크립트는 937장 공통 MVS의 설정을 따랐다고 적었다. | `scripts/phd/main_prep_measure_v1/run_colmap.sh:4-5,14-19`; `scripts/phd/main_prep_discard_rule_v1/run_colmap.sh:14-19`; `scripts/phd/main_stage0_v1/run_colmap.sh:14-19`; `configs/phd/main_prep_measure_v1/prep_v5.json:87-91`; `scripts/input_and_alignment/tum_transfer/prior_full_stereo.sh:42-48` | 스크립트 읽음 | 확인 |
| 2.2-3 | 소스 영상 고르기 | 모든 영상에 '__auto__, 20'(공유 점이 많은 20장을 자동으로 고름). 작업 공간의 설정 파일은 스크립트가 쓴다. P0의 왜곡 보정 단계가 937장에 쓴 설정 파일도 같은 줄이다. | `scripts/phd/main_prep_measure_v1/colmap_subset.py:79`; `PREP/mvs/box_B0_b10/stereo/patch-match.cfg:1-2`; `P0/data/work/mvs/colmap_dense/stereo/patch-match.cfg:1-2`; `P0/runs/t3_mvs_20260611_230138/logs/colmap_image_undistorter.log:958` | 설정 파일 읽음, 모든 영상 행이 같은지 셈 | 확인 |
| 2.2-4 | 두 단계로 돎 | 광도 단계(기하 일관성 0, 거름 0) 다음에 기하 단계(기하 일관성 1, 거름 1)를 돈다. 두 단계 모두 반복 3회다. 기하 단계의 깊이 지도(.geometric.bin)가 MVS 깊이이자 마스크의 바탕이다. | `PREP/mvs/box_B0_b10/patch_match.log:24-48(광도 단계), 12174-12198(기하 단계)`; `scripts/phd/main_stage1_v1/settings_s1.py:45` | 실행 기록 읽음 | 확인 |
| 2.2-5 | 기하 단계에 기록된 값 전부 | max_image_size 1024, window_radius 5, window_step 1, sigma_spatial 5, sigma_color 0.2, num_samples 15, ncc_sigma 0.6, min_triangulation_angle 1, incident_angle_sigma 0.9, num_iterations 3, geom_consistency 1, geom_consistency_regularizer 0.3, geom_consistency_max_cost 3, filter 1, filter_min_ncc 0.1, filter_min_triangulation_angle 3, filter_min_num_consistent 2(예외는 아래 행), filter_geom_consistency_max_cost 1, write_consistency_graph 0, allow_missing_files 0. depth_min과 depth_max는 시점마다 성긴 점에서 자동으로 정해진다. 깊이 지도를 낸 작업 공간 22개가 모두 같다(버리는 기준 작업의 B0_N2는 두 시점 모두 소스 영상이 없어 깊이 지도 0장). | `PREP/mvs/box_B0_b10/patch_match.log:12174-12198`; `DR/mvs/<탐색 지역>/patch_match.log(같은 블록)`; `S0/mvs/B0_N*/patch_match.log(같은 블록)` | 모든 실행 기록의 옵션 블록을 읽어 값별로 모음 | 확인 |
| 2.2-6 | COLMAP 기본값과 다른 설정 | 명령으로 준 것은 기하 일관성 켬, 최대 크기 1024, 반복 3, 거름 켬, 캐시 32, GPU 0의 여섯이다. 이 가운데 무엇이 이 이미지의 기본값과 다른지는 확인하지 못했다. 저장소 주석 하나가 '반복은 5가 COLMAP 기본, 3은 빠르게'라고 적었을 뿐이다. 명령에 없는 값(바로 위 행의 나머지)은 실행 기록의 값이 곧 이 이미지의 기본값이다(설정 파일 없이 돌림). | `scripts/input_and_alignment/tum_transfer/prior_full_stereo.sh:24-25`; `scripts/phd/main_prep_measure_v1/run_colmap.sh:16-19` | 명령과 실행 기록을 비교. 고정 이미지가 이 서버에 없어(docker image inspect: No such image) 도움말을 볼 수 없었고, 저장된 도움말 출력도 찾지 못함 | 확인 불가 |
| 2.2-7 | 왜곡 보정 방법 | P0에서 937장을 한 번 보정했다: colmap image_undistorter --output_type COLMAP --max_image_size 1400(같은 COLMAP 이미지). 입력 카메라는 표정 묶음(OPF)에서 옮긴 FULL_OPENCV 하나이고, 결과는 PINHOLE 1400×1013 영상이다. 실험 MVS의 작업 공간은 이 보정 영상에 대한 링크와, 학습 영상만 남긴 성긴 모형(표정과 키포인트는 그대로, 남은 영상이 둘 미만인 3차원 점은 뺌)을 쓴다. MVS는 다시 1024×741로 줄여 돈다. | `phases/p0-audit/scripts/03_mvs.sh:25,367-378`; `P0/runs/t3_mvs_20260611_230138/logs/colmap_image_undistorter.log:1`; `P0/data/work/mvs/colmap_camera_model.txt:1`; `scripts/phd/main_prep_measure_v1/colmap_subset.py:1-10,74-79`; `configs/phd/main_prep_measure_v1/prep_v5.json:72-75`; `SB/prep/cdgs/scene_B0_b10_ALS.json:1(box_model: camera model 1, 1400×1013)` | 스크립트와 실행 기록 읽음 | 확인 |
| 2.2-8 | 실험 지역 MVS는 학습 영상만 | 상자 MVS의 영상 목록이 상자 학습 목록과 정확히 같고 평가 영상은 하나도 없다: B0 243장, B173 주변 203장, B173만 140장, R1 338장(이 가운데 333장만 깊이 지도). 학습에 쓴 영상은 243, 203, 140, 333장이다. | `PREP/mvs/box_<지역>/subset.json`; `PREP/step06/box_views.json`; `S0/fork_inputs/s61/<지역>/split.json`; `PREP/mvs/box_<지역>/colmap_receipt.json:1` | 목록 대조(파일 이름 줄기로 맞춤) | 확인 |
| 2.2-9 | R1 상자 MVS에서 깊이 지도가 없는 5장 | COLMAP이 '소스 영상이 없다'며 다섯 장(DJI_20241217093905_0026, 093907_0027, 093911_0029, 094010_0030, 094012_0031)을 건너뛰었다. 준비 측정 문서의 '원본 영상을 찾지 못해'는 COLMAP의 source images(짝이 될 이웃 영상)를 옮긴 말로 보인다. 영상 파일이 없었던 것은 아니다. 학습에서는 이 5장을 뺐다. | `PREP/mvs/box_R1rep_b10/patch_match.log:18-23`; `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md:577`; `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.1.md:36` | 실행 기록 읽음 | 확인 |
| 2.2-10 | 영상 수 조건(3단계)의 MVS 설정 | 같은 스크립트, 같은 이미지, 같은 기록 값이다. 저자 15·9·3장은 준비 측정의 B0_A15·B0_A9·B0_A3 작업 공간, 연직 포함 13·8·2장은 0단계의 B0_N13·B0_N8·B0_N2 작업 공간이다(버리는 기준 작업의 같은 이름 작업 공간이 아님). 각 MVS의 영상 목록은 그 조건의 학습 목록과 같고 평가 영상은 없다. 깊이 지도는 13, 8, 2, 13, 8, 2장으로 학습 영상 모두에 나왔다. | `S2/a15/box/B0_b10/LoD2/summary.json(mvs = /prep/mvs/B0_A15)`; `S3/cond/<조건>/box/B0_b10/LoD2/summary.json(mvs 줄)`; `PREP/mvs/B0_A*/colmap_receipt.json:1`; `S0/mvs/B0_N*/colmap_receipt.json:1`; `S3/fork_inputs/<조건>/split.json`; `S2/fork_inputs/B0a15/split.json` | 요약 파일 읽음, 목록 대조, 실행 기록 비교 | 확인 |
| 2.2-11 | 동의 시점 수의 예외(소스 영상이 한 장인 시점) | 실행 기록을 보면 소스 영상이 1장인 시점은 모두 filter_min_num_consistent가 1로, 2장 이상인 시점은 모두 2로 기록되었다. 곧 그 시점들의 마스크는 '동의 1'이다. 저자 3장: 두 시점 모두. 연직 포함 2장: 두 시점 모두. 연직 포함 13장과 8장: DJI_20241217084247_0007_D 한 시점씩. 네 실험 지역, 탐색 지역 B0·R1·R2, 저자 15장과 9장에는 이런 시점이 없다. 탐색 지역 R3E와 R4에 두 시점씩 있으나 실험 지역 값에는 쓰이지 않았다. | `PREP/mvs/B0_A3/patch_match.log:23,44,73,94`; `S0/mvs/B0_N2/patch_match.log:44,94`; `S0/mvs/B0_N13/patch_match.log:19-23,44,694`; `S0/mvs/B0_N8/patch_match.log:44,444` | 실행 기록 23개(깊이 지도를 낸 22개)에서 시점마다 소스 영상 수와 기록된 동의 시점 수를 짝지어 셈 | 다름 |

### 2.2 나. 마스크 규칙과 세 기준

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.2-12 | 마스크 규칙 | COLMAP 기하 깊이 지도에 값이 있는 화소(유한하고 0보다 큼)가 신뢰도 1, 나머지가 0이다. 거른 깊이 지도를 그대로 썼고 다른 검사는 더하지 않았다. 사전 정보도 쓰지 않는다. 학습 코드는 판정 단계가 내보낸 이 지도(conf)를 그대로 읽는다. '마스크 끄기'는 광도 깊이 지도를 대신 쓴다. 판정 요약의 confidence 값은 geometric이다. | `configs/phd/main_prep_measure_v1/prep_v5.json:76-77`; `scripts/phd/main_stage0_v1/s03_stage1_v6.py:23-24,131-145,375-379,560`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:699-700`; `S0/s61/box/<지역>/<사전 정보>/summary.json('confidence')` | 코드와 설정 읽음 | 확인 |
| 2.2-13 | 기준 1: 동의해야 하는 이웃 시점 수 | 2(filter_min_num_consistent). 명령에 없는 값이라 이 COLMAP 이미지의 기본값이다. 예외는 2-가의 마지막 행(소스 영상이 한 장인 시점은 1). | `PREP/mvs/box_B0_b10/patch_match.log:12194`; `configs/phd/main_prep_measure_v1/prep_v5.json:80`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:227` | 실행 기록과 명령 비교 | 확인 |
| 2.2-14 | 기준 2: 허용 상대 깊이 차 | 없다. COLMAP의 기하 거름은 깊이 비율을 보지 않고, 설정도 'none in COLMAP's filter'로 적었다. 1단계 민감도 비교의 '엄격'(깊이 1 %)만 이 기준을 썼고, 학습에는 쓰지 않았다. 방법 4.2가 이 기준에 값을 두었다면 실험과 다르다. | `configs/phd/main_prep_measure_v1/prep_v5.json:85`; `configs/phd/main_stage1_v1/main_stage1_v1.json:103-105`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:227` | 설정과 보고서 읽음 | 다름 |
| 2.2-15 | 기준 3: 허용 재투영 거리 | 1 화소(filter_geom_consistency_max_cost: 앞으로 투영했다가 되돌아온 거리). 명령에 없는 값이라 기본값이다. | `PREP/mvs/box_B0_b10/patch_match.log:12195`; `configs/phd/main_prep_measure_v1/prep_v5.json:81` | 실행 기록과 명령 비교 | 확인 |
| 2.2-16 | COLMAP 거름이 더 보는 것 | NCC 0.1 이상(filter_min_ncc)과 삼각 각 3° 이상(filter_min_triangulation_angle). 소스 영상은 자동 20장(삼각 각 1° 이상인 영상 가운데 공유 점이 많은 순, min_triangulation_angle 1). 모두 명령에 없는 값이다. | `PREP/mvs/box_B0_b10/patch_match.log:12185,12192-12193`; `configs/phd/main_prep_measure_v1/prep_v5.json:82-84`; `scripts/phd/main_stage1_v1/sens_conf.py:6-8` | 실행 기록과 코드 설명 읽음 | 확인 |
| 2.2-17 | 마스크를 직접 구현해 비교한 기록(1단계 민감도) | 광도 깊이 지도에 같은 기준(동의 2, 1 화소, 비율 없음)을 직접 구현해 돌린 마스크가 COLMAP 마스크와 Jaccard B0 0.847, B173 주변 0.857, B173만 0.804, R1 0.876으로 겹쳤다. 비교용이며 학습에는 COLMAP 마스크를 썼다. | `S1/sens/conf/<지역>.json(totals.jaccard_current_vs_colmap)`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:190-193` | JSON 읽음 | 확인 |

### 2.2 다. 마스크 기록

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.2-18 | 실험 지역별 신뢰도 1 몫(LoD2 건물 면) | 평가 범위 안 LoD2 건물 면(지붕과 벽, 막음 면 제외) 화소 가운데 신뢰도 1의 몫, 학습 영상 전부: B0 88.13 %(지붕 89.89, 벽 86.66, 243장), B173 주변 85.42 %(90.47, 74.47, 203장), B173만 84.59 %(89.11, 78.41, 140장), R1 81.31 %(79.15, 84.07, 333장). | `S1/settings/mask_<지역>.json:12-16`; `scripts/phd/main_stage1_v1/settings_s1.py:8-10,96-136`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:245-252` | JSON과 코드 읽음 | 확인 |
| 2.2-19 | 'R1 항공 LiDAR 건물 면 신뢰도 81 %' | 81 %는 바로 위 행의 R1 값(LoD2 건물 면, 81.31 %)이다. 2단계 설정은 R1 항공 LiDAR '마스크 끄기'의 까닭에 '건물 면 신뢰도가 지역 가운데 가장 낮음(81 %)'이라고만 적었다. 항공 LiDAR 면으로 센 값이 아니다. 마스크 자체는 MVS만으로 정해지므로 두 사전 정보에 같지만, 몫은 세는 면에 따라 달라진다. | `configs/phd/main_stage2_v1/stage2_v1.json:139-153`; `S1/settings/mask_R1rep_b10.json:12-16`; `scripts/phd/main_stage1_v1/settings_s1.py:96-102` | 설정과 코드 읽음 | 다름 |
| 2.2-20 | 실험 지역별 신뢰도 1 몫(항공 LiDAR 면) | 기록이 없다. 구하려면 S0 상자 판정의 항공 LiDAR coverage_views.json에서 building_px와 a1_px를 학습 시점 전부에 더해 나눈다(범위가 평가 범위가 아니라 상자 전체이고, 번호가 있는 지붕형 면만임에 주의). 평가 범위로 맞추려면 settings_s1.py의 mask()를 항공 LiDAR 면으로 다시 돌려야 한다. | `S0/s61/box/<지역>/ALS/coverage_views.json`; `scripts/phd/main_stage1_v1/settings_s1.py:105-136` | 파일을 찾아봄, 계산하지 않음 | 확인 불가 |
| 2.2-21 | 영상 수 조건별 신뢰도 1 몫(B0 대상 건물 + 2 m) | 0단계 표, 학습 영상 전부, LoD2 지붕 / LoD2 벽 / 항공 LiDAR 지붕: 저자 15장 97.42 / 87.71 / 97.29 %, 저자 9장 94.42 / 84.22 / 94.39 %, 저자 3장 40.54 / 51.06 / 39.79 %, 연직 포함 13장 44.38 / 59.55 / 44.08 %, 8장 25.15 / 36.51 / 25.08 %, 2장 13.47 / 29.68 / 12.62 %. 범위는 평가 범위가 아니라 대상 건물 + 2 m다. | `S0/tables/b0_conditions_v2.csv:5-22`; `docs/experiments/phd/main_stage0_v1/본실험준비_0단계_보고서_v1.md:176-202` | CSV 읽음 | 확인 |

## 2.3 허용 오차와 정합 (일 3)

### 2.3 가. 실제로 쓴 값과 탐색 지역을 고른 규칙 (찾을 것 1)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.3-1 | 학습과 평가에 실제로 쓴 허용 오차와 정합 | 현재 아는 표의 값이 맞다. 0단계 상자 판정 요약의 fixed_from이 버리는 기준 작업의 탐색 지역 실행(s52)을 가리키고, 판정은 그 값을 쓴다. 같은 값이 학습 입력(0단계·2단계·3단계 fork_inputs)과 평가 참 라벨(1단계 v3 box_gt의 labels tau·shift)에 들어 있다. B0: LoD2 지붕 0.1975, 벽 0.5470 m, 이동 없음; 항공 LiDAR 0.1266 m(벽도 지붕 값), 수평 (−0.0482, +0.0431) m. B173 주변·B173만(R2): LoD2 0.1760, 0.2278 m, 이동 없음; 항공 LiDAR 0.1470 m, (−0.0562, +0.0629) m. R1: LoD2 0.6828, 0.7246 m; 항공 LiDAR 0.1034 m, 이동 없음. 6장 보조 작업이 모듈 v6로 다시 돌린 값(CH6 t5)도 비트까지 같다. | `S0/s61/box/<지역>/<사전 정보>/summary.json:8(R1은 14)(fixed_from), tolerance·registration 블록`; `DR/s52/s03/<탐색 지역>/<사전 정보>/summary.json`; `S0/fork_inputs/s61/<지역>/fork_inputs.json`; `S2/fork_inputs/*/fork_inputs.json`; `S3/fork_inputs/*/fork_inputs.json`; `S1/v3/box_gt/<지역>/gt_summary.json(labels.<사전 정보>.tau, shift)`; `CH6/t5/s03/<탐색 지역>/<사전 정보>/summary.json`; `scripts/phd/main_stage1_v1/s04_gt_v7.py:226-235` | JSON 값 비교 | 확인 |
| 2.3-2 | 탐색 지역을 고른 규칙 | '상자를 담은 탐색 지역'의 값으로 고정했다(10월 2일 23:02 사용자 결정): B0 → B0 탐색 지역(1단계 B0 크롭), B173 주변과 B173만 → R2, R1 → R1. 평가 범위는 모두 그 탐색 지역 안에 든다. 상자의 10 m 띠는 조금 넘친다: B173 주변 상자의 v 아래 끝 45.0 m가 R2의 50.0 m보다 5 m 밖이고, B0 상자의 꼭짓점은 B0 탐색 지역 직사각형 밖으로 최대 약 2.9 m 나간다. | `configs/phd/main_prep_measure_v1/prep_v5.json:254-258`; `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md:556-557`; `configs/phd/main_stage0_v1/stage0_v1.json:48`; `docs/experiments/phd/main_prep_discard_rule_v1/버리는기준_보고서_v1.md:337`; `PREP/step06/box_ranges.json(u_m, v_m, eval_u, eval_v, polygon_local)`; `PREP/step01/ranges.json(B0 xy_rect_local, R1·R2 u_m·v_m)` | 설정과 보고서 읽음, 범위 좌표 대조(B0 평가 범위는 u·v를 국지 좌표로 한 번 옮겨 손셈) | 확인 |
| 2.3-3 | 탐색 지역 값을 구한 MVS | 버리는 기준 작업이 탐색 지역마다 그 지역의 학습 영상만으로 다시 만든 MVS다(B0 272장, R2 221장, R1 588장 중 깊이 지도 582장). 설정은 2-가와 같다. 준비 측정의 처음 값(평가 영상이 섞인 937장 MVS로 구한 값)은 쓰지 않았다. | `DR/s52/s03/<탐색 지역>/<사전 정보>/summary.json:6(R1은 13)('mvs')`; `DR/mvs/<탐색 지역>/colmap_receipt.json:1`; `docs/experiments/phd/main_prep_discard_rule_v1/버리는기준_보고서_v1.md:297-300`; `configs/phd/main_prep_discard_rule_v1/discard_v1.json:10,18-23` | 요약과 영수증 읽음 | 확인 |
| 2.3-4 | 탐색 지역 MVS에 든 실험 지역 평가 영상 | 탐색 지역과 상자가 평가 영상을 따로(이름 순 여덟 장에 한 장) 뽑아서, 탐색 지역 MVS에 실험 지역 평가 영상 대부분이 들어 있다: B0 35장 중 26장, B173 주변 29장 중 25장, B173만 20장 중 19장, R1 49장 중 43장. 영상 수 조건의 평가 영상 DJI_20241217101259_0002_D도 B0 탐색 지역 MVS에 들어 있다. 허용 오차와 정합은 이 MVS로 구했으므로 '첫 단계 전체를 평가 영상 없이 했다'고 쓰면 맞지 않다. 상자 MVS 자체에는 평가 영상이 없다. 이 겹침을 적은 보고는 찾지 못했다. | `DR/mvs/<탐색 지역>/subset.json`; `S0/fork_inputs/s61/<지역>/split.json`; `S2/fork_inputs/B0a15/split.json`; `S3/fork_inputs/<조건>/split.json`; `docs/experiments/phd/main_prep_measure_v1/준비측정_결정요청_v1.1.md:148-154` | 목록 대조(파일 이름 줄기로 맞춤); 실행 세션이 네 상자의 겹침을 다시 세어 같음을 확인(파일 이름 줄기로 맞춤) | 다름 |
| 2.3-5 | 상자 자체로 구한 값(기록만, 쓰지 않음) | B0: LoD2 0.168 / 0.488 m, 이동 없음; 항공 LiDAR 0.115 m, (−0.076, +0.020) m. B173 주변: LoD2 0.179 / 0.241 m; 항공 LiDAR 0.129 m, 이동 없음. B173만: LoD2 3.647 / 0.637 m와 연직 −4.231 m, 항공 LiDAR 2.857 m와 연직 −4.618 m(대부분 바뀐 장면이라 무너짐). R1: LoD2 0.560 / 2.463 m; 항공 LiDAR 0.117 m, (+0.007, −0.046) m. 판정은 고정값을 쓰고, 이 값은 비교용으로만 남았다. | `S0/s61/box/<지역>/<사전 정보>/summary.json(fixed.tolerance_box, fixed.registration_box)`; `src/phd/prior_propagation_v6/registration.py:121-132` | JSON 읽음 | 확인 |
| 2.3-6 | 영상 수 조건의 허용 오차와 정합 | 모든 조건이 B0 값(LoD2 0.1975 / 0.5470 m, 이동 없음)이다. 조건 자신의 MVS로 구하지 않았다. | `S3/cond/<조건>/box/B0_b10/LoD2/summary.json(fixed_from = /dr/s52/s03/B0/LoD2)`; `S2/a15/box/B0_b10/LoD2/summary.json`; `configs/phd/main_prep_discard_rule_v1/discard_v1.json:109`; `docs/experiments/phd/main_stage3_v1/본실험_3단계_보고서_v1.md:452` | JSON과 보고서 읽음 | 확인 |
| 2.3-7 | LoD2 이동과 연직 이동 | LoD2는 일곱 탐색 지역 어디서도 옮기지 않았다(B0·R1·R2에서는 첫 수평 걸음이 관문에서 거절됨). B0·R1·R2에서는 두 사전 정보 모두 연직 이동이 없다. 수평 이동 뒤 높이 차 중앙값이 NMAD보다 작았기 때문이다: B0 LoD2 +0.081 ≤ 0.104, 항공 +0.030 ≤ 0.063; R2 LoD2 −0.033 ≤ 0.099, 항공 +0.059 ≤ 0.085; R1 LoD2 +0.112 ≤ 0.353, 항공 +0.034 ≤ 0.045 m. | `DR/s52/s03/<탐색 지역>/<사전 정보>/summary.json(registration.iterations, median_after_horizontal, nmad_after_horizontal, accepted_vertical)`; `docs/experiments/phd/main_prep_discard_rule_v1/버리는기준_보고서_v1.md:308-321,328-333`; `S1/settings/settings.md:1-10` | JSON과 보고서 읽음 | 확인 |
| 2.3-8 | R2 항공 LiDAR 수평 이동이 받아들여진 폭 | 첫 걸음 (−0.056, +0.063) m가 관문 NMAD 0.0846 → 0.0845 m, 전체 건물 면 NMAD 0.0876 → 0.0875 m로 줄어 받아들여졌다. 준비 측정 v1.1에서는 같은 걸음이 0.0881 → 0.0883 m로 늘어 거절되었다. 관문 바로 옆의 결과다. | `DR/s52/s03/R2/ALS/summary.json(registration.iterations, final_check)`; `docs/experiments/phd/main_prep_discard_rule_v1/버리는기준_보고서_v1.md:328-332` | JSON과 보고서 읽음 | 확인 |

### 2.3 나. 표본 수와 걸러 낸 몫 (찾을 것 2)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.3-9 | 허용 오차 표본을 모은 법 | 정합한 사전 정보를 탐색 지역의 학습 시점마다 렌더해, 신뢰도 1이고 건물 면에 맞은 범위 안 화소의 잔차를 면 종류마다 모은다(법선의 연직 성분 절댓값이 0.5 이상이면 지붕형, 아니면 벽형). 시점마다 종류별로 2만 화소가 넘으면 무작위로 2만을 뽑는다. 3 NMAD 밖을 한 번 걸러 내고, 남은 것의 NMAD × 2.5가 허용 오차다. LoD2 벽은 2,000 화소 이상일 때 따로 구하고, 항공 LiDAR 벽은 지붕 값을 그대로 쓴다. | `scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:244-299`; `src/phd/prior_propagation_v6/tolerance.py:1-32`; `configs/phd/main_prep_measure_v1/prep_v5.json:143-148` | 코드와 설정 읽음 | 확인 |
| 2.3-10 | 탐색 지역별 표본 수(실제로 쓴 값) | B0(272 시점): LoD2 지붕 2,560,818, 벽 2,664,723; 항공 LiDAR 지붕 2,483,355, 벽 0(지붕 값). R2(221 시점): LoD2 1,991,449, 2,092,171; 항공 LiDAR 1,954,162, 0. R1(582 시점): LoD2 7,990,474, 8,661,588; 항공 LiDAR 7,489,460, 0. | `DR/s52/s03/<탐색 지역>/<사전 정보>/residual_samples.npz('roof', 'wall' 배열 크기)`; `scripts/phd/main_prep_discard_rule_v1/s03_stage1.py:291-299` | npz 머리만 읽음(컨테이너 하나, 배열 값은 읽지 않음). robust_width는 유한한 값만 세므로 실제 n은 이 크기 이하 | 확인 |
| 2.3-11 | 걸러 낸 몫(3 NMAD 밖) | 실제로 쓴 값에는 기록이 없다. 구하려면 위 파일의 roof·wall 배열에 tolerance.robust_width(k 2.5, clip 3)를 돌려 clipped_share를 읽는다(새 계산이라 하지 않음). 참고로 준비 측정 v1.1(937장 MVS, 쓰지 않은 값)의 지붕 몫은 기록이 있다: B0 LoD2 18.5 %, 항공 9.4 %; R2 LoD2 21.7 %, 항공 19.8 %; R1 LoD2 15.7 %, 항공 15.6 %(표본 수는 B0 2,508,675·2,438,090, R2 1,973,568·1,935,686, R1 7,967,001·7,448,828). 벽의 걸러 낸 몫은 어디에도 없다. | `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md:604-607,618-619`; `src/phd/prior_propagation_v6/tolerance.py:18-32` | 파일을 찾아봄, 계산하지 않음 | 확인 불가 |

### 2.3 다. 기관 정확도와 경고 기록 (찾을 것 3)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.3-12 | 설정에 적힌 기관 정확도 | 항공 LiDAR 지붕 0.12 m, 벽 없음; LoD2 지붕 1.0 m, 벽 없음. 준비 측정 설정 v1~v5가 모두 같은 줄에 적었다. | `configs/phd/main_prep_measure_v1/prep_v5.json:107-116(0.12는 109줄)`; `configs/phd/main_prep_measure_v1/prep_v1.json~prep_v4.json:109` | 설정 읽음 | 확인 |
| 2.3-13 | 기관 정확도의 쓰임 | 기록하고 비교만 한다. 허용 오차의 하한으로 쓰지 않는다(처음 판의 max(k·s, 기준) 규칙은 없앴다). 허용 오차가 기준보다 크면 경고 'tolerance exceeds the agency spec'를 남긴다. 판정과 지표에는 쓰이지 않는다. | `src/phd/prior_propagation_v6/tolerance.py:7-11,35-51`; `configs/phd/main_prep_measure_v1/prep_v5.json:147`; `docs/experiments/phd/main_fill_v1/본실험_채우기_결정반영_v1.md:63` | 코드와 문서 읽음 | 확인 |
| 2.3-14 | 0.12 m의 출처 | main 브랜치의 앞 실험 설정이 'TUM2TWIN 기재 바이에른 ALS 수직 정확도 0.12 m'로, LoD2 1 m는 '발주서 3절'로 적었다. r10 설정도 같은 출처를 적었다. 판정 요약의 출처 표기는 'agency spec (configs prep_v2 = v1)'이다. 6장 보조 작업은 기관 값 약 0.10 m, TUM2TWIN 본문 0.12 m, 같은 논문 표 2는 0.21 m로 정리했다. | `main 브랜치 configs/phd/stage1_conf_tol_conflict_v1/experiment.json:49-50(이 작업 폴더에는 없음, git show로 읽음)`; `configs/phd/stage2_r10_two_fixes_three_checks_v1/r10.json:76-90`; `docs/experiments/phd/ch6_support_v1/6장_3절_사실_v1.md:13,39`; `S0/s61/box/<지역>/ALS/summary.json(tolerance.roof.spec_source)` | 설정과 문서 읽음 | 확인 |
| 2.3-15 | 경고 기록(실제로 쓴 값) | 항공 LiDAR 지붕: B0 0.1266 > 0.12, R2 0.1470 > 0.12 → 경고가 있다. R1 0.1034 ≤ 0.12 → 경고 없음. LoD2 지붕은 모두 1.0 m 아래라 경고 없음. 벽은 기준이 없어 경고가 없다(항공 LiDAR 벽이 지붕 값 0.1266·0.1470을 쓰더라도). | `S0/s61/box/B0_b10/ALS/summary.json:105`; `S0/s61/box/B173nb_b10/ALS/summary.json:106`; `S0/s61/box/B173_b0/ALS/summary.json:95`; `DR/s52/s03/B0/ALS/summary.json:8`; `DR/s52/s03/R2/ALS/summary.json:8`; `DR/s52/s03/R1/ALS/summary.json:15` | JSON 읽음 | 확인 |
| 2.3-16 | 경고 기록(상자 자체 값, 비교용) | B173 주변 항공 0.129 m, B173만 LoD2 3.647 m, B173만 항공 2.857 m에 경고가 있다. 쓰지 않은 값이다. | `S0/s61/box/B173nb_b10/ALS/summary.json:17`; `S0/s61/box/B173_b0/LoD2/summary.json:17`; `S0/s61/box/B173_b0/ALS/summary.json:17` | JSON 읽음 | 확인 |
| 2.3-17 | 논문에 0.10 m로 쓸 때와 0.12가 적힌 곳 | 파일의 경고는 0.12 m 기준으로 붙었다. 0.10 m와 비교하면 R1 항공 0.1034도 넘는다(값 대조). 기준은 판정과 지표에 쓰이지 않으므로 결과는 같다. 0.12가 적힌 곳: 준비 측정 설정 v1~v5의 109줄, 모든 판정 요약의 항공 LiDAR tolerance.roof.spec, 준비 측정 보고서 v1·v1.1의 4.2절 표와 본문, r10 설정, main 브랜치 앞 실험 설정, 6장 보조 문서들. | `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.md:593-612`; `docs/experiments/phd/main_prep_measure_v1/준비측정_보고서_v1.1.md:605-624`; `docs/experiments/phd/main_fill_v1/본실험_채우기_결정반영_v1.md:63`; `docs/experiments/phd/ch6_support_v1/6장보조_보고서_v1.md:72,315`; `docs/experiments/phd/ch6_support_v1/문서세션_전달_v1.md:79`; `docs/experiments/phd/ch6_support_v1/실험세션_전달_v1.md:60` | 문서 검색 | 확인 |

### 2.3 라. 비교 방법이 받은 사전 정보의 정합 (찾을 것 4)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.3-18 | GeoGS(LoD2) | LoD2 면 = 상자 메시(s02_box lod2_mesh.npz) + 0단계 상자 실행의 LoD2 이동(모든 지역 0). 기록된 registration_shift는 [0, 0, 0]이다. 고친 GeoGS도 1단계 장면의 lod2.obj를 그대로 쓴다. 본 방법과 같다. | `scripts/phd/main_stage1_v1/geogs_prep.py:12-14,123-133`; `S1/geogs/<지역>/prep.json:11`; `scripts/phd/main_fix_v1/geogs_scene_fix.py:5` | 코드와 기록 읽음 | 확인 |
| 2.3-19 | GeoGS 항공 LiDAR | 건물 부분 = als_mesh.npz의 건물 삼각형 + 0단계 상자 실행의 항공 LiDAR 이동(B0 (−0.048, +0.043, 0), B173 두 곳 (−0.056, +0.063, 0), R1 0). 1단계의 정합한 사본(defs prior_ALS.npz)과 비교한 기록이 네 지역 모두 '이동 같음, 꼭짓점 최대 차 0.0 m'다. 본 방법과 같다. | `docs/experiments/phd/main_baselines_v1/본실험_비교방법_발주문_v1.1.md:261`; `docs/experiments/phd/main_baselines_v1/본실험_비교방법_준비보고_v1.md:17`; `scripts/phd/main_baselines_v1/geogs_als/als_inputs.py:8-11,103-106,134-143`; `SB/prep/geogs_als/<지역>_inputs.json:25,51-56` | 문서, 코드, 점검 기록 읽음 | 확인 |
| 2.3-20 | MVS 기반 결합(Zhou 외 2020 재현) | 사전 정보 깊이 = 0단계 판정이 내보낸 정합한 사전 정보 렌더(S0 export의 prior 지도). 사전 정보 메시 = s02_box 메시 + 0단계 상자 실행의 이동. B0 두 사전 정보에서 다시 렌더한 깊이와 내보낸 지도의 차는 시점별 중앙값이 최대 3.8×10⁻⁶ m다. 본 방법과 같다. | `scripts/phd/main_baselines_v1/mvsfuse/mf_common.py:4-11,168-169,189-206`; `SB/prep/mvsfuse/conv_check_B0_b10_ALS.json:483-492`; `SB/prep/mvsfuse/conv_check_B0_b10_LoD2.json(summary)` | 코드 읽음(네 지역 같은 함수), 수치 점검 기록은 B0만 있음 | 확인 |
| 2.3-21 | CDGS | 사전 정보 깊이 = 0단계 판정이 내보낸 정합한 사전 정보 렌더다(비교 방법 작업과 채우기 작업 모두). 본 방법과 같은 이동이다. CDGS 자신의 시점별 깊이 맞춤(축척과 이동)은 정합과 다른 것이다: 비교 방법 작업은 공식 맞춤을 돌렸고(학습하지 않음), 채우기 작업은 맞춤을 건너뛴다(축척 1, 이동 0, 10월 15일 사용자 결정). | `scripts/phd/main_baselines_v1/cdgs/cdgs_scenes.py:17,213-214`; `SB/prep/cdgs/scene_<단위>.json:1(prior_depth.dir)`; `configs/phd/main_fill_v1/fill_v1.json:1919,2060,2106` | 코드와 설정 읽음 | 확인 |
| 2.3-22 | 학습 없는 사전 정보 `samepath_<사전 정보>` | 1단계 defs의 `prior_<사전 정보>.npz`(= s02_box 메시 + 0단계 상자 실행의 이동)를 학습 시점마다 광선으로 렌더해 같은 TSDF로 메시를 만든다. 본 방법과 같은 이동이다. | `scripts/phd/main_stage1_v1/defs_s1.py:79-86,164`; `scripts/phd/main_stage1_v1/gpu_s1.py:4-5,134-145` | 코드 읽음 | 확인 |
| 2.3-23 | (참고) 본 방법 판정을 바꿔 끼운 결합 | 포크 r14의 학습 전 판정 출력을 읽으므로 본 방법의 입력과 같은 이동이다. | `SB/prep/judgefuse/judgment_source.json:1` | 기록 읽음 | 확인 |

### 2.3 마. 항공 LiDAR가 τ의 1~2배 어긋난 넓이 (찾을 것 5)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.3-24 | 184 m²와 11 m²가 센 것 | 항공 LiDAR가 τ의 1~2배 어긋난 넓이다. 영상이 맞고 측정된 패치(지지 패치, 영역 코드 11)만 셌고, 결측 패치(코드 13)와 비가시 패치(코드 14)는 넣지 않았다. 184 m²는 고르는 곳의 값이고(1~1.5τ 150 m², 1.5~2τ 34 m²), 11 m²는 평가 지역 셋의 값이다(8 m², 3 m²). 고르는 곳은 탐색 지역 일곱 곳에서 실험 지역의 평가 범위를 뺀 곳이며, 겹친 곳은 한 번만 센다. 두 값을 더한 값은 어느 기록에도 없다 | `CH6/t5/judge/bins.md:7-8`; `scripts/phd/ch6_support_v1/t5_bins.py:28`(코드 2와 11의 패치만); `scripts/phd/ch6_support_v1/ch6_common.py:86-99`(항목 정의: 코드 11이고 1~4τ면 '조금 틀린 곳'); `scripts/phd/ch6_support_v1/t5_judge.py:130-138`(고르는 곳은 평가 범위 밖, 겹친 곳은 한 번) | 코드의 항목 정의와 구간 넓이를 대조 | 확인 |
| 2.3-25 | 보조 보고서 6절 답 4번의 216 m² | 같은 지지 패치의 1~4τ 넓이다. 고르는 곳에서 150 + 34 + 21 + 11 = 216 m²이고, 주 표의 '사전 정보가 조금 틀린 곳(1~4τ)' 칸의 값이다. 답 4번은 이 값을 '1~2τ를 설계대로 지킨다'는 문장에 붙여 1~2τ의 넓이처럼 읽힌다. 1~2τ의 넓이는 184 m²(고르는 곳)와 11 m²(평가 지역)가 맞다. 같은 문장의 '놓음 8~53 %'는 1~2τ 구간의 고르는 곳 8 %·22 %와 평가 지역 39 %·53 %를 함께 적은 범위다 | `ch6_support_v1/6장보조_보고서_v1.md:199`(답 4번), `:222`(주 표); `ch6_support_v1/tables/t5_tables.md:25`; `CH6/t5/judge/bins.md:7` | 구간 넓이를 더해 주 표의 값과 맞춤 | 다름 (보고서 문장이 틀렸다. 채우기 결정 반영 덧붙임 4절과 실험 세션 전달 글 4절 5번은 이미 184 m²로 적었다) |

## 2.4 충돌 문턱 배수의 준비 측정 (일 4)

- 이 절의 줄임: '보고서' = `main_prep_discard_rule_v1/버리는기준_보고서_v1.md`(둘째 준비 측정), '결정요청' = `main_prep_discard_rule_v1/버리는기준_결정요청_v1.md`. '지지 패치' = 영상이 확인한 패치, '결측 패치' = 찍혔지만 영상이 확인하지 못한 패치, '잘못 버림' = 맞는 사전 정보를 버림, '잘못 지킴' = 틀린 사전 정보를 지킴.

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.4-1 | 배율을 비교한 보고서와 날짜 | 둘째 준비 측정 '옛 자료를 버리는 기준'(`PHD-MAIN-PREP-DISCARD-RULE-v1`) 보고서 v1, 2026-10-05 00:3x~07:10 | `main_prep_discard_rule_v1/버리는기준_보고서_v1.md`:1-5, 544-547 | 문서 읽음 | 확인 |
| 2.4-2 | 분석자가 고른 절 | 보고서 1.4절(분석자 추천)과 7.2절 1번, 결정 요청 2절 '가'와 5절 초안 | 같은 보고서:115-135, 529-533; `버리는기준_결정요청_v1.md`:102-127, 224 | 문서 읽음 | 확인 |
| 2.4-3 | 최종 결정을 내린 곳 | 사용자 결정 2026-10-06. 0단계 설정 `stage0_v1.json`의 'user_decisions_1006'(10-06 13:39 저장, 0단계 첫 계산 전), 0단계 결정 요청 3절 '이미 정한 것', 0단계 보고서 2.1절, 공용 모듈 v6 `rules.py`의 `DEFAULT_BY_PRIOR`와 그 주석 | `configs/phd/main_stage0_v1/stage0_v1.json`:12-15, 28-33; `main_stage0_v1/0단계_결정요청_v1.md`:29, 153; `main_stage0_v1/본실험준비_0단계_보고서_v1.md`:7, 43; `src/phd/prior_propagation_v6/rules.py`:107-112 | 설정·문서·코드 대조 | 확인 |
| 2.4-4 | 후보가 처음 나온 곳 | 첫째 준비 측정(`PHD-MAIN-PREP-MEASURE-v1`, 10-02~03, 보고서 v1.1은 10-04)의 결정 요청이 τ 민감도(0.5배·2배), 충돌 전파의 여유(중앙값 ≥ kτ), 비대칭 규칙을 선택지로 내고 짧은 사전 측정을 권했다. 사용자가 10-05에 '이 순서로 비교'로 정했다 | `main_prep_measure_v1/준비측정_결정요청_v1.1.md`:160-190; `discard_v1.json`:7-11 | 문서 읽음 | 확인 |
| 2.4-5 | 6장 보조 작업이 말한 '준비 측정 2.5' | 첫째 준비 측정 보고서 v1.1의 2.5절(경우 7 대부분이 변한 장면, 경우 9 정합 차이)이다. 배율과는 다른 측정이다 발주문 2.4의 '같은 보고서로 보인다'와 다르다: 배수를 고른 것은 둘째 준비 측정(버리는 기준, 10월 5일)이고, 6장 보조 작업이 가리킨 '준비 측정 2.5'는 첫째 준비 측정(10월 2~4일)의 2.5절 '전제가 어긋날 때'다(실행 세션이 두 문서의 절 제목으로 확인). | `ch6_support_v1/실험검토기록_일곱항목_v1.md`:82-83; `준비측정_보고서_v1.1.md`:404-470 | 문서 대조 | 다름 (배수를 고른 측정과 다른 보고서) |
| 2.4-6 | 고르는 데 쓴 곳 | '고르는 곳' = 탐색 지역 일곱(R1, R2, R3E, R4, R5, SW, B0 크롭)에서 실험 지역 상자 넷(B0, B173과 이웃, B173만, R1 부채꼴)의 평가 범위를 뺀 곳. 겹치는 곳은 B0, R1, R2, R3E, R4, R5, SW 차례로 한 번만 셈. R3은 R3E 안이라 따로 만들지 않음 | 보고서:32-33; `configs/phd/main_prep_discard_rule_v1/discard_v1.json`:19-20, 95-98; `scripts/phd/main_prep_discard_rule_v1/rules_eval.py`:138-156 | 스크립트 줄 확인 | 확인 |
| 2.4-7 | 평가 범위를 뺐는지 | 뺐다. 패치 가운데(정합 이동 반영)가 상자 넷의 평가 범위 사각형 안이면 뺐다. 다만 상자의 맥락 띠(B0·B173과 이웃·R1 부채꼴 상자의 10 m)는 빼지 않아 고르는 곳에 남았다 | `rules_eval.py`:143-152 | 코드 읽음 | 확인 (띠는 남음) |
| 2.4-8 | 고르는 곳의 자료 | 학습 영상만으로 다시 만든 MVS(8장마다 1장인 평가 영상 뺌, COLMAP 4.0.4, 준비 측정과 같은 설정, 10-05 01:32~05:08), 새로 구한 허용 오차 τ와 정합, 학습 없는 첫째 단계 14건, 참값 v5 규칙(드론 LiDAR 2024-12-17; B0는 GeoGS 저자 참값에 드론 LiDAR 보충), 평가 제외 칸은 준비 측정 v1.1 파일 그대로 | `discard_v1.json`:18-25, 70-76; 보고서:297-302 | 문서 읽음 | 확인 |
| 2.4-9 | 센 부분 | 범위 안, 평가 제외 칸 밖, 참 라벨(일치·충돌)이 있는 패치. 지붕과 벽(항공 LiDAR는 벽 패치가 없음), 지지 패치와 결측 패치를 따로 셈. 비가시 패치는 어느 규칙에서도 같아 따로 둠. 패치 수: LoD2 지붕 지지 388,332(참 충돌 98,347)·결측 7,943(1,657), LoD2 벽 지지 223,425(29,880)·결측 9,307(829), 항공 LiDAR 지붕 지지 318,469(10,613)·결측 6,787(398) | 보고서:76, 93; `discard_v1.json`:86-94; `DR/rules/counts.json`의 selection_aggregate | 컨테이너에서 `counts.json`을 읽어 보고서 표와 대조 | 확인 |
| 2.4-10 | 후보 (부록 D와 비교) | 결과 전 설정의 후보 열 가지: 지금 규칙(1τ), 여유 규칙(모두) k = 1.5·2·3, 여유 규칙(전파만) k = 1.5·2·3, 비대칭 규칙, 허용 오차 0.5배·2배. 허용 오차 2배는 판정이 여유(모두) 2와 같다고 설정에 미리 적음(판정이 다른 후보는 아홉). 부록 D의 '1, 1.5, 2, 3배와 전파에만 둔 여유'에는 비대칭 규칙과 허용 오차 0.5배·2배가 빠졌고, 전파만 여유가 k 세 값이었다는 것이 드러나지 않는다 | `discard_v1.json`:77-85, 117; `rules.py`(v6):20-26; 보고서:35-45 | 설정·코드 대조 | 다름 (빠진 후보) |
| 2.4-11 | '전파에만 둔 여유'의 꼴과 값 | 지지 패치의 표(일치·충돌)는 τ 그대로 둔다. 결측 패치에 판정을 빌려 줄 때, 충돌 표인 지지 패치는 그 패치의 신뢰도 1 화소(지지 시점 모두를 모음)의 잔차 크기 중앙값이 kτ를 넘을 때만 충돌 증거로 센다. 아니면 모은 수(5개까지)에는 넣되 어느 쪽 증거로도 세지 않는다. k = 1.5, 2, 3. 상태, 같은 면 1 m 안 지지 패치 5개까지 모으기, 3분의 2 다수, 손실의 허용 구간은 어느 규칙에서도 그대로 | `discard_v1.json`:80, 84; `rules.py`(v6):1-15, 50-71 | 코드 읽음 | 확인 |
| 2.4-12 | '여유 규칙(모두)'의 꼴 | 화소의 표시 문턱을 kτ로 올린다(τ < 잔차 ≤ kτ는 일치). 지지 패치의 표와 전파가 모두 이 표시를 쓴다 | `discard_v1.json`:79; `rules.py`(v6):8, 23 | 코드 읽음 | 확인 |
| 2.4-13 | 비교한 값 | 학습 전 판정의 잘못 버림(버렸는데 참 일치)과 잘못 지킴(지켰는데 참 충돌), 그리고 맞게 버림·맞게 지킴, 잘못 지킴의 크기 나눔(참값과 사전 정보의 차 ÷ τ: 1~2, 2~4, 4 넘음), 심지 않을 점의 수. '버림' = 충돌 표의 지지 패치, 또는 충돌로 판정된 결측 패치 | `discard_v1.json`:86-94; `rules_eval.py`:88-119 | 코드 읽음 | 확인 |
| 2.4-14 | 참값을 썼는지 | 썼다. 패치마다 참값(드론 LiDAR)과 사전 정보의 차 중앙값이 기준 τ 이하면 참 일치, 넘으면 참 충돌이다. 기준 τ는 새로 구한 τ이고 규칙의 배율과 무관하다 | `discard_v1.json`:75; 보고서:31 | 문서 읽음 | 확인 |
| 2.4-15 | 결과 표 | 아래 '표 4-가'. 보고서 1.2절 표와 `counts.json`의 수가 모두 같다 | 보고서:57-97; `DR/rules/counts.json` | 컨테이너에서 대조 | 확인 |
| 2.4-16 | 고르는 기준 | 보고서와 결정 요청: '잘못 버림이 크게 줄면서 잘못 지킴은 거의 늘지 않는' 규칙과 k. 두 문서 모두 '설정에 미리 적은 기준'이라 하지만 설정 두 파일에 이 기준 문장이 없다. 그 작업의 발주문은 저장소와 작업 폴더에 없다 | 보고서:117; 결정요청:120; `discard_v1.json` 전체, `sites_v1.json` 전체 | 설정 파일 전체를 낱말로 찾음 | 확인 불가 (결과 전에 적혔는지) |
| 2.4-17 | 후보·세는 법·고르는 곳이 결과 전인지 | 결과 전이다. 설정 파일 시각 10-05 01:41:23(보고서가 적은 시각과 같음). 설정 안 '작성' 칸은 '01:5x', 진행 기록은 '02:0x'로 셋이 다르지만 모두 첫 결과 전. 첫 결과: 새 MVS의 첫째 단계 05:10:43(R4 LoD2), 규칙 열 가지 첫 셈 05:59:11 끝(79초; 06:38 다시 셈, `counts.json` 해시 같음). 지금 설정 파일의 sha256 앞자리(08a85ceb6e27, ef8c3ad069a0)가 진행 기록·영수증과 같다 | 보고서:12-15; `DR/logs/progress.md`:11, 21, 25; `DR/receipt_task.json`:80-83, 1134-1140, 1561-1566; `DR/s52/s03/R4/LoD2/summary.json` 파일 시각 | 파일 시각과 sha256 대조 | 확인 (시각 기록 셋이 다름) |
| 2.4-18 | 분석자 추천 | 항공 LiDAR = 여유 규칙(전파만) k = 2. 결측 패치의 잘못 버림 1,541 → 515(−67 %), 잘못 지킴 316 → 330(+14개). k = 3도 거의 같아 작은 2를 고름. 이득의 대부분은 R1 반투명 지붕 홀(1,128 → 305). 항공 LiDAR 지지 패치는 '기준을 채우는 규칙이 없다'며 여유(모두) 2(잘못 버림 37,244 → 15,291, −59 %; 잘못 지킴 3,992 → 6,250, +57 %)를 맞바꿈의 판단으로 사용자에게 남김. LoD2 = 지금 규칙(여유(모두)는 잘못 버림 하나를 줄일 때 잘못 지킴이 1.6~2.8개 늚). 비대칭과 허용 오차 0.5배는 권하지 않음 | 보고서:115-135; 결정요청:102-127, 224 | 문서 읽음 | 확인 |
| 2.4-19 | 최종 '항공 LiDAR 2배'의 뜻 | 여유 규칙(모두) 2: 지지 패치의 표와 전파 모두 2τ에서 충돌 표시. 분석자가 권한 '전파만 2'가 아니다. 수치표면모델에도 같은 규칙. 손실의 허용 구간은 τ, 참 라벨은 기준 τ 그대로. LoD2는 지금 규칙(1τ) | `stage0_v1.json`:13, 28-33; `rules.py`(v6):107-112 | 설정·코드 대조 | 다름 (분석자 추천과 다름) |
| 2.4-20 | 결정의 문장 근거 | 0단계 설정: 'LoD2 = current (conflict beyond 1 tau); airborne LiDAR and DSM = margin_all_2 (conflict only beyond 2 tau, measured and unmeasured patches alike)'. `rules.py` 주석의 까닭(LoD2는 일반화된 옛 모델이라 버림이 대부분 맞았고, 항공 LiDAR와 수치표면모델은 정확한 옛 표면이라 버림이 대부분 MVS 오류에서 왔다)은 결정 요청 2절 '가'의 '왜'와 같은 내용이다. 사용자가 직접 적은 까닭은 없다 | `stage0_v1.json`:12-13; `rules.py`(v6):108-111; 결정요청:105-108 | 문서 대조 | 확인 불가 (사용자 자신의 까닭) |
| 2.4-21 | 사용자가 본 수에 평가 범위가 들었는지 | 결정 요청 1.3절에 상자 넷 평가 범위의 수가 '보고만'으로 함께 실렸다(항공 LiDAR 여유(모두) 2에서 잘못 버림 B0 802 → 431, B173과 이웃 1,873 → 695, B173만 1,510 → 831, R1 부채꼴 8,148 → 5,644; 잘못 지킴 +30~87). 분석자의 비교는 고르는 곳만 썼다. 사용자가 이 수를 썼는지는 기록이 없다 | 결정요청:76-81; 보고서:235-259 | 문서 읽음 | 확인 불가 |
| 2.4-22 | 결정 뒤 같은 규칙의 효과 (참고) | 0단계(공용 모듈 v6, 패치 저장소 고침 뒤) 평가 범위: 항공 LiDAR 잘못 버림 B0 825 → 423, B173과 이웃 1,849 → 684, B173만 1,462 → 805, R1 부채꼴 8,148 → 5,644; 잘못 지킴 +25~+87 | `0단계_결정요청_v1.md`:32; `본실험준비_0단계_보고서_v1.md`:109 | 문서 읽음 | 확인 |
| 2.4-23 | '넓은 평지붕을 영상이 20~30 cm 낮게' 처음 나온 곳 | 첫째 준비 측정 보고서 v1.1의 1.4절 1번(100행 '넓은 평지붕의 20~30 cm 어긋남')과 2.3절 경우 2의 셋째 결과(287행 'R4·R3E 넓은 평지붕: MVS가 참값보다 0.15~0.3 m 낮다', 300행 R4 그림 '20~30 cm 낮다(τ 0.17 m)'). v1에도 같은 문장(99, 285, 298행). 2.2절은 '사전 정보의 오류'라 이 문장이 없다 | `main_prep_measure_v1/준비측정_보고서_v1.1.md`:100, 249, 283-300 | 문서 읽음 | 다름 (절 번호: 2.3절) |
| 2.4-24 | 둘째 준비 측정에서 다시 확인했는지 | 크기를 다시 구하지 않았다. R4 평지붕과 R3E 평지붕을 '지켜야 맞는 곳'의 대표 자리로 썼고, 설정의 출처 칸에 첫째 측정의 'MVS 0.2-0.3 m low on a wide flat roof'를 옮겨 적었다. 새 MVS로 그린 R4 LoD2 그림의 읽기는 'LoD2, 참값, MVS가 거의 같은 높이'다. 결정 요청 2절 '가'는 '넓은 평지붕의 어긋남'을 까닭으로만 들었다 | `configs/phd/main_prep_discard_rule_v1/sites_v1.json`:32-39; 보고서:201-207; 결정요청:108 | 문서 읽음 | 확인 |
| 2.4-25 | '고르게'인지 | 두 준비 측정 어디에도 '고르게'라는 말이 없다. 첫째 측정 2.1절은 넓은 평지붕·박공 지붕의 흔한 덩어리를 'MVS가 넓은 지붕에서 τ(0.16~0.22 m)를 조금 넘게 흔들린 것'으로 적었다 | `준비측정_보고서_v1.1.md`:137 | 문서 읽음 | 확인 불가 |
| 2.4-26 | 그 자리 | R4·R3E 탐색 지역(평가 상자 밖). R1 상자에는 그런 평지붕이 없다고 채우기 준비 보고가 적었다(R1에서 같은 꼴을 찾으면 LoD2 61 m², 전제 위배 0) | `main_fill_v1/본실험_채우기_준비보고_v1.md`:92-95; `SL/progress.md`:16 | 문서 읽음 | 확인 (R1이라 쓰면 다름) |

**표 4-가. 고르는 곳의 두 잘못 (잘못 버림 / 잘못 지킴, 패치 수)**

| 규칙 | LoD2 지붕 지지 | LoD2 지붕 결측 | LoD2 벽 지지 | LoD2 벽 결측 | 항공 LiDAR 지붕 지지 | 항공 LiDAR 지붕 결측 |
|---|---|---|---|---|---|---|
| 지금 규칙 (1τ) | 23,116 / 22,993 | 945 / 565 | 14,528 / 9,518 | 1,329 / 507 | 37,244 / 3,992 | 1,541 / 316 |
| 여유(모두) 1.5 | 10,892 / 46,095 | 624 / 715 | 8,919 / 18,294 | 905 / 662 | 22,092 / 5,482 | 1,085 / 324 |
| 여유(모두) 2 (= 허용 오차 2배) | 7,529 / 59,329 | 557 / 819 | 6,137 / 24,459 | 610 / 728 | 15,291 / 6,250 | 720 / 329 |
| 여유(모두) 3 | 5,170 / 73,690 | 424 / 1,186 | 3,890 / 27,448 | 434 / 773 | 9,982 / 7,132 | 421 / 342 |
| 여유(전파만) 1.5 | 지금 규칙과 같음 | 509 / 774 | 지금 규칙과 같음 | 792 / 651 | 지금 규칙과 같음 | 699 / 326 |
| 여유(전파만) 2 | 지금 규칙과 같음 | 474 / 908 | 지금 규칙과 같음 | 552 / 724 | 지금 규칙과 같음 | 515 / 330 |
| 여유(전파만) 3 | 지금 규칙과 같음 | 425 / 1,164 | 지금 규칙과 같음 | 394 / 772 | 지금 규칙과 같음 | 409 / 339 |
| 비대칭 | 지금 규칙과 같음 | 0 / 1,657 | 지금 규칙과 같음 | 0 / 829 | 지금 규칙과 같음 | 0 / 398 |
| 허용 오차 0.5배 | 87,277 / 7,043 | 1,770 / 470 | 39,611 / 4,868 | 2,631 / 364 | 108,995 / 1,876 | 2,818 / 289 |

- 읽는 법: 최종 선택은 LoD2 = 첫 줄, 항공 LiDAR = 셋째 줄(여유(모두) 2)이다. 분석자 추천은 항공 LiDAR 결측 = 여유(전파만) 2였다.
- 근거: `버리는기준_보고서_v1.md`:57-97, `DR/rules/counts.json`(selection_aggregate, 컨테이너에서 읽어 모두 같음).

## 2.5 비교 방법 (일 5)

- 이 절의 줄임: '보고서' = `main_baselines_v1/본실험_비교방법_보고서_v1.md`, '발주문 v1.1' = `main_baselines_v1/본실험_비교방법_발주문_v1.1.md`, '준비보고' = `main_baselines_v1/본실험_비교방법_준비보고_v1.md`, '채우기 발주문' = `main_fill_v1/본실험_채우기_발주문_v1.md`.

### 2.5 가. 2차원 가우시안 스플래팅

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.5-1 | 저장소와 커밋 | 공식 구현 `github.com/hbb1/2d-gaussian-splatting`, f3e3b9fa67bbd1c75e05167ff37391d8dab2a678(2026-08-25). 하위 모듈 diff-surfel-rasterization e0ed020, simple-knn f155ec0. 이미지 `jointbuildgs:2dgs-official-f3e3b9f-v1`(GeoGS 공식 이미지 바탕이라 Python 3.10, PyTorch 2.1.2; README는 3.8, 2.0.0) | `configs/phd/main_baselines_v1/baselines_v1.json`:1617-1618; `Dockerfile.2dgs-official-v1`:1-26; `SB/sources/2d-gaussian-splatting`의 git 원격과 HEAD | git 기록 확인 | 확인 |
| 2.5-2 | 반복과 학습 값 | 30,000회. 학습 값은 모두 공식 기본값: 법선 일관성 0.05(7,000회부터), 왜곡 0, depth_ratio 0, 밀도 제어 500~15,000회. 넘긴 인자는 `-r 1`, `--eval`, `--data_device cpu`뿐 | `SB/prep/twodgs/defaults.json`:1-57; `main_baselines_v1/본실험_비교방법_보고서_v1.md`:797 | 기록 읽음 | 확인 |
| 2.5-3 | 씨앗 | 공식 고정 씨앗 하나(train.py 272행 `safe_state` → 씨앗 0) | `SB/sources/2d-gaussian-splatting/train.py`:272; 같은 곳 `utils/general_utils.py`:130-132 | 원본 코드 확인 | 확인 |
| 2.5-4 | 기본값에서 바꾼 것과 까닭 | 학습 값은 바꾸지 않았다. 어댑터 셋: 주점(공식 읽기 코드는 주점을 버림; 이 카메라의 주점은 중심에서 2.4·−4.4 px), 평가 나눔(`split.json`), 기록 한 줄. 할당기 설정 `expandable_segments`(메모리만). 왜곡 0을 둔 까닭: 공식 기본값이 0이고 공식 평가 스크립트도 왜곡 없이 학습함(TnT 스크립트는 화면에 100·10을 찍지만 실제로 실행하는 줄에는 넣지 않음; Mip-NeRF 360 스크립트는 기본값) | `baselines_v1.json`의 components.twodgs.source; `main_baselines_v1/본실험_비교방법_발주문_v1.1.md`:340-345; `main_stage1_v1/본실험_1단계_준비보고_v1.md`:266-272; `SB/sources/2d-gaussian-splatting/scripts/tnt_eval.py`:20-30, `scripts/m360_eval.py`:36-40 | 원본 스크립트 읽음 | 확인 |
| 2.5-5 | 사전 정보와 횟수 | 사전 정보 없음(처음 점은 영상 점만). 지역마다 한 번(B0, B173 주변, R1, B173만; B173만은 보고만 하는 지역). 결과 하나를 LoD2·항공 LiDAR 두 표에 씀. B173만은 첫 시도가 14,150회에서 GPU 메모리 부족으로 멈추고 같은 설정의 둘째 시도로 끝남 | 보고서:523-534, 858; `baselines_v1.json`:29-38 | 문서 읽음 | 확인 |
| 2.5-6 | 메시 | 공통 후처리: 포크 렌더러로 학습 시점(1024×741)의 알파로 나눈 기댓값 깊이, 상자 가림, TSDF 0.05 m·잘림 0.25 m·깊이 한도 300 m. 공식 렌더러와 깊이가 비트까지 같음을 확인 | 보고서:796, 814-819; `main_baselines_v1/본실험_비교방법_준비보고_v1.md`:14 | 문서 읽음 | 확인 |

### 2.5 나. GeoGS

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.5-7 | 저장소와 커밋, 학습에 썼는지 | `github.com/zqlin0521/GeoGS`, db40c95c657ec03ff21c83cb99cf39f4e90247a6(2026-08-25). 이 커밋으로 학습했다. 학습 원본 `GeoGS-official-adapters-v1-fix1` = 이 커밋 + 어댑터 둘(주점, 평가 나눔) + 가림 검사 두 줄(바뀐 파일은 `data/generate_pcd.py` 하나). 이미지 `jointbuildgs:geogs-official-db40c95-compat-v1`(matplotlib 3.9.2, libstdc++ 미리 읽기) | `GG/sources/GeoGS/.git/config`(원격)와 HEAD; `configs/phd/main_stage1_v1/train_plan_v1.json`:17; `main_fix_v1/본실험_고침_보고서_v1.md`:44; `main_fix_v1/provenance/source_manifest_fix1.json`:1-10; `Dockerfile.geogs-v1`:5; `Dockerfile.geogs-compat-v1`:1-10 | git 원격·HEAD 확인, 문서 대조 | 확인 |
| 2.5-8 | 반복과 저자 깃발 | 30,000회. `--eval --lod_init --freeze_onlybldg --protect_bldg --dynamic_depth_weight -r 1`, `--stage_switch_iter 8000 --lambda_lod_init 0.08 --lambda_lod_anchor 0.005`(셋은 공식 기본값과 같은 값을 앞 작업처럼 넘김), 씨앗 0(`safe_state`), `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. 깃발 다섯은 README의 명령과 같다 | `SB/prep/geogs_als/commands.json`:1-125; `scripts/phd/main_stage1_v1/run_geogs.py`:13-17, 47-50; `FX/geogs/source/GeoGS-official-adapters-v1-fix1/train.py`:1266-1269, `README.md`:95-113 | 명령 기록과 원본 기본값 대조 | 확인 |
| 2.5-9 | 고친 판의 두 고침 | (가) 처음 점의 가림 검사가 예외로 막혀 모든 점을 '보임'으로 남기던 것을 고침(메시를 돌려줌, 첫 교차만), rtree를 전처리 이미지에 더함. 네 지역 모두에 해당. 빠진 점 0.1~24.8 %. (나) DA3 묶음 축척: B173 주변만 12장 묶음으로 다시 맞춤(묶음 축척 0.130~1.213 → 0.975~1.074). B0, R1, B173만은 1단계의 8장 묶음 깊이 그대로 발주문의 '고친 판(가림 검사, DA3 깊이 묶음의 축척)'은 두 고침이 모든 지역에 든 것처럼 읽힌다. 가림 검사 고침은 네 지역 모두, DA3 묶음 축척 고침은 B173 주변뿐이다. | `main_fix_v1/본실험_고침_준비보고_v1.md`:17-31, 93-118, 142-160, 170 | 문서 읽음 | 다름 (DA3 묶음 축척 고침은 B173 주변만) |
| 2.5-10 | DA3 단안 깊이 | 쓴다(`--da_depth_path`, `--dynamic_depth_weight`). 저자 절차는 장면 영상 전체를 한 번에 넣지만, 24 GB GPU에 들지 않아 이름 차례 8장 묶음으로 공식 스크립트를 돌렸다(사용자 결정 10-07). 항공 LiDAR 실행도 고친 판의 같은 DA3 파일을 씀(하드 링크) | `main_stage1_v1/본실험_1단계_준비보고_v1.md`:266-277; `main_stage1_v1/본실험_1단계_보고서_v1.md`:528-531; `SB/prep/geogs_als/commands.json`:22; 발주문 v1.1:277 | 문서 읽음 | 확인 |
| 2.5-11 | 항공 LiDAR로 옮긴 법 | LoD2 메시 자리에 항공 LiDAR TIN(2022-02 분류 2·6 점을 평면에서 Delaunay로 이은 삼각망)의 건물 부분을 넣었다. 건물 부분 = 건물 꼭짓점(등급 6)이 하나 이상인 면(v1, 사용자 결정 10-15로 지붕 끝과 땅 사이 구멍을 닫음; 발주의 '둘 이상' 규칙은 v0으로 보관) + 본 방법과 같은 정합 이동. 지면 면은 넣지 않음. `--z_offset 0`. GeoGS가 받는 세 입력(처음 점 `sparse_lod/0`, 렌더 깊이 `lod2_prior`, 건물 점 구름 `lod2_pcd.ply`)을 GeoGS의 이름 그대로 이 건물 부분에서 만듦. 처음 점(표본 10만, 2~15장에 보임, 고친 가림 검사), '건물' 점 구름(100만 점, 0.2 m), 학습 명령은 LoD2 판과 같음. 표의 지붕·벽은 법선 연직 성분 0.5로 나눔. 그 밖의 LoD2 전제는 찾지 못함 발주문의 '수치표면모델 메시'는 이 삼각망을 가리킨다. 저장소에서 '수치표면모델'(DSM)은 다른 사전 정보 종류의 이름이라, 글에서는 '항공 LiDAR 삼각망'이 맞다. | `SB/prep/geogs_als/lod2_places.json`(전체); `SB/prep/geogs_als/commands.json`:16-30; 발주문 v1.1:257-280; `baselines_v1_amendments.json`:14-20 | 기록 읽음 | 다름 (말: '수치표면모델 메시'가 아니라 항공 LiDAR 삼각망) |
| 2.5-12 | 학습 시간과 자원 | 항공 LiDAR 52.2~98.0분, GPU 최대 9.7~19.9 GiB, 컨테이너 `--memory 46g`(자원 한도만, 계산은 같음). LoD2 판(고침 작업의 결과를 옮김) 52.6~195.6분 | 보고서:535-542, 798, 877 | 문서 읽음 | 확인 |

### 2.5 다. MVS 기반 결합 (Zhou 외 2020의 재현)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.5-13 | 공개 구현 | 없다. 10-14(발주)와 10-15(준비)에 찾았다: GitHub(API 저장소 검색 셋, 관련 0건), Zenodo(API, 정확한 제목 0건), 4TU.ResearchData(웹 검색 0건). 논문은 C++, OpenCV, GDAL, libLAS로 짰다고만 적고 공개한다는 문장이 없다(원고 19쪽 380-383줄) | `SB/prep/mvsfuse/paper_check.md`:38-40; 발주문 v1.1:294; 준비보고:53 | 기록 읽음 | 확인 |
| 2.5-14 | 원문 | Zhou, Lindenbergh, Gorte, Zlatanova (2020), ISPRS J. 162, 200-213의 저자 승인 원고(TU Delft 저장소). 발주 표의 '원 논문' 칸 열한 개가 원문과 맞음 | `SB/prep/mvsfuse/paper_check.md`:1-26 | 기록 읽음 | 확인 |
| 2.5-15 | 색 문턱의 값과 정한 법 | 대응 화소 RGB 차(0~255)의 제곱평균제곱근 > 25. 원 논문의 '20~30, 여러 자료에서 잘 맞음'(원고 27쪽 535-537줄)의 가운데 값으로 발주(10-14)가 결과 전에 정함. 이 자료로 맞추지 않았다. 20과 30은 참고 넓이와 놓침·잘못 잡음에만 | 발주문 v1.1:369; `scripts/phd/main_baselines_v1/mvsfuse/mf_common.py`:67; `baselines_v1.json`:156 | 문서·코드 확인 | 확인 |
| 2.5-16 | 색 차 참고값과 그 자료 | 준비에서 참고로만 구함. 실험 지역 넷 × 사전 정보 둘의 학습 영상에서 MVS 깊이가 사전 정보와 τ 안인 판정 화소의 색 차: 중앙값 8.4~14.6, 95분위 39~65, 25를 넘는 몫 13~29 % | `SB/prep/mvsfuse/colourref_*.json`(여덟); 준비보고:55 | 여덟 파일의 값을 모아 봄 | 확인 |
| 2.5-17 | 판정까지의 단계 | 학습 영상마다 짝 하나(같은 비행, 시선 차 20° 안, 겹침 60 %에 가장 가까움; 짝 없는 영상 3~6장은 판정에 안 씀). 사전 정보 면의 점을 짝 영상에 투영한 자리 ±2화소에서 3×3 회색 NCC가 가장 큰 화소를 대응으로 삼고, 짝에서 가려진 점은 판정 안 함. 가파른 사전 정보 화소(법선 연직 성분 < 0.5: LoD2 벽, 항공 LiDAR 가파른 면)는 판정 안 함. 짝마다 2 m 높이 변화의 기복 변위 0.7배 크기로 열기. 0.25 m 평면 칸에서 짝 있는 시점의 절반 넘게 변화이고 시점 둘 이상이면 변화 칸. 철거 규칙: 건물마다 둘레 지면 높이로 대응을 찾아 95 % 이상이 문턱 아래면 건물 전체를 변화로(이번에 더해진 넓이는 모든 단위 0) | `mf_common.py`:54-83; 보고서:576-583, 776-790 | 코드 읽음 | 확인 |
| 2.5-18 | 2 m 규칙의 실제 꼴 | 넓히기 뒤의 크기 거르기. 8방향으로 이어진 변화 칸 덩어리마다 최소 넓이 회전 사각형의 두 변 ≥ 2 m, 넓이 ≥ 4 m², 덩어리 칸의 높이 차(MVS − 사전 정보) 중앙값 ≥ 2 m여야 남음. 칸의 반 넘게 MVS가 없으면 높이를 보지 않고 남기는 예외가 있으나 여덟 단위 모두 0개였다. 넓히기 중에는 1 m²(16칸) 미만 새 조각을 지움. 축 방향 x·y가 아니라 회전 사각형의 두 변이다(사용자 결정 10-15, 원 논문의 '2 × 2 m²'가 축에 매이지 않아서) | `mf_common.py`:31-53, 90-94; `SB/prep/mvsfuse/decisions_1015.json`; `main_baselines_v1/tables/fusion_records.json`의 size_filter | 코드와 기록 확인 | 다름 (축 방향 x·y가 아님) |
| 2.5-19 | 넓히기 규칙 | 변화 칸 둘레 1 m 안의 칸을 본다. 칸의 높이 차(가파르지 않은 사전 정보 화소, 모든 학습 시점의 (MVS 깊이 − 사전 정보 깊이) × 광선 z 성분) 중앙값의 크기가 2 m를 넘으면 변화 칸 → 1 m² 미만 새 조각 지움 → 새 변화 둘레 2 m로 되풀이. 본 칸은 다시 보지 않고, 더할 것이 없으면 멈춤. 1.5 m는 참고 넓이만 | `mf_common.py`:84-89; `baselines_v1.json`:161; `baselines_v1_amendments.json`:7-13 | 코드 읽음 | 확인 |
| 2.5-20 | 합친 표면을 메시로 만든 법 | 학습 시점마다 깊이 지도를 합친다. 변화 칸 화소 = COLMAP 기하 깊이(관측 신뢰도 1, 0단계 내보내기; 없으면 비움), 나머지 사전 정보 화소 = 정합한 사전 정보의 렌더 깊이, 사전 정보가 없는 화소 = MVS 깊이. 이것을 모든 방법과 같은 TSDF(학습 시점, 0.05 m, 잘림 0.25 m, 깊이 한도 300 m, 상자 가림)에 넣어 한 표면으로 만듦. 1단계 `samepath`와 같은 길. COLMAP의 메시나 점 구름 표면을 쓰지 않음 | `mf_common.py`:1-13, 95-99; 발주문 v1.1:335, 375; 보고서:789, 796 | 코드·문서 확인 | 다름 ('COLMAP MVS 표면'이 아니라 MVS 깊이 지도) |
| 2.5-21 | 원 논문과 다른 점 전체 | ① 사전 정보로 이끄는 정합과 둘째 정합 대신 이 실험의 COLMAP MVS 깊이; 스테레오 한 쌍(거의 연직의 앞뒤 연속 영상) 대신 학습 영상마다 짝 하나 ② 대응: 투영점 둘레 5×5에서 max(0, NCC), 매끄러움 항·MRF·3×3 중앙값 거르기 없음 ③ 색 문턱 25 ④ 침식 대신 열기(0.7배) ⑤ 여러 시점을 0.25 m 칸에 모음 ⑥ 크기: 회전 사각형 2 m·4 m²·높이 중앙값 2 m ⑦ 가파른 화소(벽)는 판정과 높이 차에서 뺌 ⑧ 철거의 '모두'를 95 %로 ⑨ 넓히기: 영상만 정합 대신 MVS 높이 차 2 m ⑩ 갱신: 점 바꾸기 대신 깊이 합치기와 같은 TSDF ⑪ NDVI와 도로·강 마스크 안 함(근적외 영상, 지형도 없음; 평가 범위 밖 변화 넓이를 적음) ⑫ 둘째 정합의 부분 변화 다시 확인 없음 | 보고서:776-790; `SB/prep/mvsfuse/paper_check.md`:28-36; `decisions_1015.json`; `baselines_v1_amendments.json`:7-13 | 문서 대조 | 확인 |
| 2.5-22 | 변화로 판정된 넓이 몫 (평가 범위 패치 넓이 대비) | B0 LoD2 1.2 % (61.4 / 5,132.3 m²), B0 항공 LiDAR 0.1 % (2.0 / 1,592.9), B173 주변 LoD2 56.1 % (4,960.8 / 8,845.9), B173 주변 항공 LiDAR 53.5 % (1,222.0 / 2,285.9), R1 LoD2 34.4 % (1,697.9 / 4,940.9), R1 항공 LiDAR 5.4 % (87.4 / 1,610.5). B173만(보고만): LoD2 68.3 % (4,866.1 / 7,129.1), 항공 LiDAR 70.6 % (1,220.5 / 1,729.6) | 보고서:576-583; `main_baselines_v1/tables/fusion_records.md`:4, 12-19, 47-50 | 표 읽음 | 확인 |

### 2.5 라. CDGS

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.5-23 | 저장소, 커밋, 이미지 | `github.com/zqlin0521/cdgs-release`, db853c11f185a5a6cf6fe40e26cc106d209fa012(2025-09-23). 이미지 `jointbuildgs:cdgs-official-db853c1-v1`(CUDA 11.8, Python 3.8, PyTorch 2.0.1, opencv 4.12 고정, scipy·imageio 더함) | `main_baselines_v1/provenance/cdgs/changes.json`:1-10; `main_fill_v1/provenance/changes.json`:1-6; `Dockerfile.cdgs-official-v1`:1-33; `SB/sources/cdgs-release`의 git | git 확인 | 확인 |
| 2.5-24 | 판 | 변형 여덟(`cdgsnofit_<사전 정보>_s0`) = 어댑터 v3 = v2 + 크기 맞추기를 건너뛰는 설정 하나(축척 1, 이동 0; 정렬 손실과 시점 가중 0.6 × exp(−150 × 손실)은 그대로). 공식 확인 한 판(B0 LoD2, `cdgs_LoD2_s0`) = 어댑터 v2 그대로. v2 = v1(주점, 사전 정보가 닿지 않은 화소 빼기, 기록, 인자 형 고침) + 정렬 대상을 그 시점이 본 SfM 점으로 + 정렬 단위를 원 저자 자료(TT 중앙값 2.646)에 맞춤 | `main_fill_v1/provenance/changes.json`(전체); `main_baselines_v1/provenance/cdgs/changes.json`; `main_fill_v1/본실험_채우기_발주문_v1.md`:203-214 | 기록 읽음 | 다름 (변형은 어댑터 v3) |
| 2.5-25 | 반복, 명령, 기본값 | 30,000회(공식 기본값). `train.py -s … -m … --depth -r 1 --eval --use_predefined_depth --predefined_depth_path <사전 정보 렌더 깊이, 미터>`. 밀도 제어 100~15,000회, `--depth`에서는 불투명도 다시 놓기 없음, 가우시안 150만 개를 넘으면 밀도 제어 멈춤. 할당기 설정 없음(torch 2.0.1이 받지 않음). `--data_device cpu`는 공식 코드 오류라 기본값(GPU). `PipelineParams.debug` = 켬(공식 기본값) 그대로 | 채우기 발주문:136, 276-277; `SL/prep/cdgs/commands.json`:1-30, 96-109 | 기록 읽음 | 확인 |
| 2.5-26 | 씨앗 | 고정 씨앗 없음(공식 train.py 339행의 `safe_state`가 주석 처리됨). 비교 방법 발주 6.4절의 '공식 코드의 고정 씨앗'은 틀린 문장이었고, 준비 보고가 바로잡음 | `SB/sources/cdgs-release/train.py`:339; 준비보고:194; 발주문 v1.1:357 | 원본 코드 확인 | 확인 |
| 2.5-27 | 비교 방법 작업에서의 결과 | 학습하지 않음. 학습 전 두 규칙(축척 0.9~1.1 밖 시점이 4분의 1 넘으면 지역 멈춤, 깊이 가중 중앙값 0.006 미만이면 단위 멈춤)에 걸림. B0 LoD2만 두 규칙을 통과했으나 같은 지역 항공 LiDAR가 걸려 함께 멈춤 | 보고서:692-716; `baselines_v1_amendments.json`:35-41 | 문서 읽음 | 확인 |
| 2.5-28 | 채우기 작업의 점검 | 같은 감독 확인(B0 LoD2 152장, 차 최대 1.55e-6 < 1e-5) 통과. 깊이 가중 점검(깊이가 있는 시점만으로 세게 바꿈) 여덟 단위 통과(중앙값 0.351~0.581) | `main_fill_v1/본실험_채우기_준비보고_v1.md`:12-14, 25-50 | 문서 읽음 | 확인 |
| 2.5-29 | 채우기 작업이 끝났는지 | 끝나지 않음. 대기열 10-15 21:57 시작. 10-16 00시 무렵 B0 LoD2 두 판(공식 확인, 변형)이 각각 14,460회·14,520회(48 %), 초당 약 1.1회, 남은 어림 3시간 45분. 나머지 변형 일곱 판은 기다림. 모든 표의 CDGS 칸은 '아직'. 23:03에 `debug` 끄기를 사용자에게 여쭈었고 23:51까지 답 기록이 없음 | `SL/progress.md`:40-41, 48, 58; `SL/logs/train_B0_b10_cdgs_LoD2_s0.log`, `SL/logs/train_B0_b10_cdgsnofit_LoD2_s0.log` 끝줄 | 진행 기록과 로그 끝을 읽음(파일은 건드리지 않음) | 확인 불가 (결과와 끝까지 돈 설정) |

### 2.5 마. 학습 전 사전 정보 (기준)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.5-30 | 결과 이름 | `samepath_<사전 정보>`(1단계) | `baselines_v1.json`:118-152; `main_stage1_v1/본실험_1단계_장면보기_보고_v1.md`:36 | 문서 읽음 | 확인 |
| 2.5-31 | 표면을 만든 법 | 정합한 사전 정보 메시를 학습 시점마다 광선 투사해 깊이 지도를 만들고, 0단계 상자 가림과 같은 TSDF(0.05 m, 잘림 0.25 m, 깊이 한도 300 m)로 메시를 만듦. LoD2는 덮개 면을 뺀 면(이동 0), 항공 LiDAR는 지면과 건물을 모두 담은 TIN 전체에 정합 이동을 더함 | `scripts/phd/main_stage1_v1/gpu_s1.py`:4-5, 134-177; `scripts/phd/main_stage1_v1/defs_s1.py`:79-86 | 코드 읽음 | 확인 |
| 2.5-32 | 같은 TSDF인지 | 같다. 결합과 판정만 바꾼 변형도 '1단계 samepath와 같은 길'로 깊이를 같은 TSDF에 넣었다 | 발주문 v1.1:331-335; 보고서:796 | 문서 확인 | 확인 |

## 2.6 모든 방법에 같은 조건 (일 6)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.6-1 | 메시 생성: 본 방법 | TSDF 복셀 0.05 m, 절단 거리 0.25 m, 깊이 한도 300 m. 학습 시점 전부에서 렌더한 기댓값 깊이(알파로 나눈 값)를 상자 가림 뒤 합치고, 다듬지 않는다. 0~3단계와 고침 작업의 본 방법 결과 기록이 모두 같은 값이고, 시점 수는 학습 영상 수와 같다. | `scripts/phd/main_stage1_v1/gpu_s1.py:181-247` (226행 extract_mesh_bounded); `configs/phd/main_stage0_v1/stage0_v1.json:115`; 결과마다 `post/post.json` (tsdf) | 코드 읽기. 0~3단계, 고침, 비교 방법, 채우기 작업의 결과 기록 117개(post.json, samepath.json)와 지표 시험 작업의 2개를 모두 읽어 비교: 모두 0.05, 0.25, 300이고 시점 수는 그 조건의 학습 영상 수 | 확인 |
| 2.6-2 | 메시 생성: 2차원 가우시안 스플래팅 | 같다. 공식 2DGS(커밋 f3e3b9f)로 학습한 결과를 포크 렌더러로 같은 카메라에서 렌더해 같은 TSDF로 합쳤다. 네 지역 기록 모두 0.05, 0.25, 300과 시점 243, 140, 203, 333. 준비 단계에서 공식 렌더러와 포크 렌더러의 깊이가 비트까지 같음을 확인했다. | `scripts/phd/main_baselines_v1/gpu_bl.py:1-13`; `SB/runs/<지역>/imgonly_2dgs_s0/post/post.json`; `docs/experiments/phd/main_baselines_v1/본실험_비교방법_보고서_v1.md:796, 814-816` | 코드, 기록, 보고서 읽기 | 확인 |
| 2.6-3 | 메시 생성: GeoGS | 같다. 고친 GeoGS LoD2(`trust_LoD2_fix1`), GeoGS 항공 LiDAR(`geogs_ALS_fix1`), 1단계 GeoGS(`trust_LoD2`) 모두 포크 렌더러로 같은 카메라에서 렌더해 같은 TSDF로 합쳤다. GeoGS 공식 `render.py`의 메시(깊이 한도 = 장면 반지름의 두 배, 복셀 = 한도/1024, 덩어리 50개만 남김)는 쓰지 않았다. | `FX/runs/<지역>/trust_LoD2_fix1/post/post.json`; `SB/runs/<지역>/geogs_ALS_fix1/post/post.json`; `S1/stage1/<지역>/trust_LoD2/post/post.json`; `GG/sources/GeoGS/render.py:128-139` | 기록과 공개 코드 읽기 | 확인 |
| 2.6-4 | 메시 생성: CDGS | 같은 길로 만들게 짜여 있다: 학습 시점 전부를 CDGS 렌더러로 렌더한 알파로 나눈 기댓값 깊이를 같은 카메라, 같은 상자, TSDF 0.05/0.25/300으로 합친다. 최종 결과는 아직 없다. 채우기 작업에서 학습 중이다(10-15 23:03 기록, 한 판 약 6시간). 준비 시험에서는 호스트 메모리 한도 32 GB 때문에 TSDF를 학습 시점 4장으로 줄여 연결만 확인했다. | `scripts/phd/main_fill_v1/cdgs/cdgs_post.py:1-24`; `scripts/phd/main_fill_v1/gpu_fl.py:61`; `SL/prep/cdgs/smoke_chain.json`; `SL/progress.md` (10-15 21:56, 23:03 줄) | 코드와 진행 기록 읽기 | 확인 불가 |
| 2.6-5 | 메시 생성: MVS 기반 결합 | 같다. 학습 시점마다 변화 칸은 MVS 깊이, 그 밖은 사전 정보 렌더 깊이로 만든 깊이 지도를 같은 카메라, 같은 상자 가림, TSDF 0.05/0.25/300으로 합치고 다듬지 않는다. 여덟 단위 모두 시점 수가 학습 영상 수와 같고 깊이가 없는 시점은 0이다. 짝 영상도 학습 영상에서만 고른다. | `scripts/phd/main_baselines_v1/gpu_bl.py:39-87`; `SB/runs/<지역>/mvsfuse_<사전 정보>/post/post.json`; `configs/phd/main_baselines_v1/baselines_v1.json` (mvsfuse_rules.update); `scripts/phd/main_baselines_v1/mvsfuse/pairs.py:1-5, 24-42` | 코드와 기록 읽기 | 확인 |
| 2.6-6 | 메시 생성: 학습 전 사전 정보(`samepath_<사전 정보>`) | 같다. 정합한 사전 정보 면을 학습 시점마다 광선으로 비춰 얻은 깊이를 같은 상자 가림, TSDF 0.05/0.25/300으로 합쳤다. B0, B173만, R1은 1단계 `gpu_s1.samepath`, B173 주변은 지표 시험 작업의 같은 코드(`gpu_mt.samepath`, 상자는 0단계 후처리의 것)로 만들었다. 시점 수는 학습 영상 수와 같다. | `scripts/phd/main_stage1_v1/gpu_s1.py:134-178`; `scripts/phd/metrics_trial_v1/gpu_mt.py:47, 119-161`; `S1/stage1/<지역>/samepath_<사전 정보>/samepath.json`; `MT/gpu/samepath_<사전 정보>/samepath.json`; `scripts/phd/main_stage1_v1/metrics_s1.py:43-45` | 코드와 기록 읽기 | 확인 |
| 2.6-7 | 같은 상자 가림 | 같다. 지역마다 상자 하나(범위 사각형 + 2 m, 높이는 상자 참값의 5 % 값 − 5 m부터 최대 + 5 m까지)를 모든 결과 기록이 같은 값으로 쓴다 (B0 24개, B173 주변 23개, B173만 15개, R1 25개 기록에서 상자 값이 하나). | `scripts/phd/main_stage1_v1/gpu_s1.py:45-52, 98-104`; post.json (box) | post.json의 box를 지역마다 모아 서로 다른 값의 수를 셈 | 확인 |
| 2.6-8 | 메시 다듬기 없음 | 확인했다. TSDF에서 나온 메시를 그대로 저장한다. 덩어리 거르기나 매끄럽게 하기가 없고, 깊이 지도로 합치는 길도 'no cleaning'으로 적혀 있다. | `scripts/phd/main_stage1_v1/gpu_s1.py:226-229`; `src/phd/forks/GeoGS-conf-guided-v1-r14/utils/mesh_utils.py:141-182`; `scripts/phd/main_baselines_v1/gpu_bl.py:8-10, 75-78` | 코드 읽기 | 확인 |
| 2.6-9 | 같은 학습 시점 목록 | 같다. 모든 후처리 실행기가 `JBGS_SPLIT_JSON`으로 같은 split.json을 넘긴다. 기록의 시점 수가 학습 영상 수(243, 140, 203, 333)와 같고, 평가 영상 목록이 남은 결과는 모두 split.json의 평가 목록과 같다. CDGS는 최종 결과가 없어 기록으로는 확인하지 못했다. | `scripts/phd/main_stage1_v1/run_gpu.sh:18`; `scripts/phd/main_baselines_v1/run_gpu_bl.sh:15, 20`; `scripts/phd/metrics_trial_v1/run_gpu.sh:22`; `scripts/phd/main_stage0_v1/run_fork_v6.py:42`; post.json (tsdf.views, eval_views) | post.json의 시점 수와 평가 목록을 split.json과 비교 | 확인 |
| 2.6-10 | 가상 시점 메시(덧붙임) | 보지 못한 벽을 세는 데는 다른 메시를 쓴다: 학습 시점과 가상 시점 16개, 상자 안 가우시안만, TSDF 복셀 0.10 m, 절단 0.5 m, 한도 300 m. 채우기 작업이 같은 설정을 모든 방법에 쓴다. 지금 아는 것에는 이 두 번째 설정이 없다. | `scripts/phd/main_stage1_v1/gpu_s1.py:316-345` (342행); `scripts/phd/main_fill_v1/virtual/vv_common.py:12`; `scripts/phd/main_fill_v1/virtual/vv_defs.py:73` | 코드 읽기 | 확인 |
| 2.6-11 | 평가 영상 나눔 규칙 | 상자의 후보 영상을 이름순으로 놓고 자리 번호를 8로 나눈 나머지가 0인 영상을 평가로 둔다(8장에 1장). 나눔은 깊이 지도가 없는 학습 영상을 빼기 전에 정해서, R1은 후보 387장 가운데 49장이 평가, 학습은 333장이다(5장 빠짐). 평가 영상 수: B0 35, B173 주변 29, B173만 20, R1 49. | `configs/phd/main_prep_measure_v1/prep_v5.json:60`; `S0/fork_inputs/s61/<지역>/split.json`, `fork_inputs.json` (dropped_training_views) | 설정과 나눔 파일 읽기 | 확인 |
| 2.6-12 | 모든 방법이 같은 나눔인지 | 같다. 본 방법, GeoGS, 2DGS는 `JBGS_SPLIT_JSON` 어댑터로 split.json을 읽는다. CDGS는 split.json을 이름순 번호로 바꾼 `split_index.json`을 읽는다(되돌려 같음 확인). MVS 기반 결합과 학습 전 사전 정보는 포크 장면의 학습 카메라를 쓴다. GeoGS 공식 규칙을 그대로 쓰면 R1에서 평가가 48장이 되어 달라지므로 어댑터를 썼다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/scene/dataset_readers.py:374-386`; `docs/experiments/phd/main_baselines_v1/provenance/twodgs/adapters_v1.diff:4-6, 37-46`; `scripts/phd/main_baselines_v1/cdgs/cdgs_scenes.py:15, 194`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:273`; `docs/experiments/phd/main_baselines_v1/본실험_비교방법_보고서_v1.md:814` | 코드와 보고서 읽기 | 확인 |
| 2.6-13 | 평가 영상을 지표에 쓰는지 | 학습, 상자 MVS, 학습 전 판정에서는 빠진다. 지표에서는 화질(PSNR, SSIM, LPIPS-VGG)과 부유 가우시안이 가린 화소의 몫에 쓴다. 기하 지표는 학습 시점으로 만든 메시와 참값으로 구한다. 평가 시점의 렌더 깊이 점(eval_points)은 만들지만 1단계 이후 지표에는 쓰지 않는다. | `scripts/phd/main_stage1_v1/gpu_s1.py:196-211, 251-300`; `scripts/phd/main_stage1_v1/metrics_s1.py:234-246, 281-287`; `scripts/phd/main_stage1_v1/tables_s1.py:208` | 후처리와 지표 코드 읽기 | 다름 |
| 2.6-14 | 평가 영상과 탐색 지역 MVS(새로 찾음) | 상자의 평가 영상 대부분이, 허용 오차와 정합을 구한 탐색 지역 MVS의 학습 목록에 들어 있다: B0 26/35, B173 주변 25/29, B173만 19/20, R1 43/49. 탐색 지역은 자기 후보 목록으로 따로 8장에 1장을 나누기 때문이다. 그 값은 상자에 고정해 썼다. 영향을 알려면 이 영상을 뺀 탐색 지역 MVS로 허용 오차와 정합을 다시 구해야 한다(새 계산이라 하지 않음). | `DR/mvs_lists/{B0,R1,R2}.json`; `S0/fork_inputs/s61/<지역>/split.json`; `docs/experiments/phd/main_prep_discard_rule_v1/버리는기준_보고서_v1.md:297-337`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:243` | 두 이름 목록의 겹침을 셈(파일 읽기); 실행 세션이 네 상자의 겹침을 다시 세어 같음을 확인(파일 이름 줄기로 맞춤) | 다름 |
| 2.6-15 | 모든 방법이 같은 표정 파일을 썼는지 | 같다. 본 방법(LoD2, 항공 LiDAR 장면), GeoGS(1단계, 고침, 항공 LiDAR), 2DGS 장면의 `images.bin`이 지역마다 바이트까지 같다(sha256). CDGS 장면은 2차원 관측을 더한 다른 파일이지만 영상 이름과 회전·이동 값이 모두 같다(최대 차 0). MVS 기반 결합과 학습 전 사전 정보는 포크 장면의 카메라를 쓴다. 카메라 파일과 주점 보정 파일도 지역마다 같다. | `S0/fork_inputs/s61/<지역>/scene_<사전 정보>/sparse/0/images.bin`; `S1/geogs/<지역>/scene/sparse/0/images.bin`; `FX/geogs/<지역>/scene_fix1/sparse/0/images.bin`; `SB/scenes/{twodgs,geogs_als,cdgs}/...`; `SL/scenes/cdgs/...`; `docs/experiments/phd/main_baselines_v1/본실험_비교방법_보고서_v1.md:814` | sha256 비교, COLMAP 바이너리를 표준 라이브러리로 읽어 값 비교 | 확인 |
| 2.6-16 | 자료집의 표정을 그대로 쓰는지 | 포크 장면의 표정은 937장 COLMAP 모델(P0 `colmap_dense/sparse`)의 회전·이동과 같다(네 지역 장면 1,052장 모두 차 0). 그 모델은 제공자 OPF의 보정과 자세를 COLMAP 형식으로 옮기고(P0 T2, 다시 추정한 기록 없음) PINHOLE 1400 × 1013으로 왜곡을 보정한 것이다. 상자 MVS도 이 모델의 자세를 쓴다. OPF 원본과 바로 비교하려면 좌표 이동(EPSG:25832 − (690953, 5336071, 604) m)을 되돌린 카메라 중심 비교가 필요해 하지 않았다. | `scripts/phd/main_prep_discard_rule_v1/fork_inputs.py:57-62, 110, 168`; `scripts/phd/main_prep_discard_rule_v1/common.py:27, 152-160`; `configs/phd/main_prep_measure_v1/prep_v5.json:90`; `docs/evidence/p0-audit/w1-input-diagnostics/reports/opf2colmap_summary.md`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:224-225` | 두 COLMAP 바이너리의 값 비교, 기록 읽기 | 확인 |
| 2.6-17 | 3단계 영상 수 조건의 나눔(덧붙임) | B0 영상 수 조건은 따로 나눈다: 저자 15장과 연직 포함 13장은 학습 13 + 평가 2(0002, 0016), 9장·8장·3장·2장은 평가 0002 하나. 같은 조건 안의 방법들(본 방법, 영상만, 고친 GeoGS)은 같은 나눔이다. | `S3/runs/B0*/<결과>/post/post.json` (eval_views); `configs/phd/main_prep_measure_v1/prep_v5.json:63-69` | 기록 읽기 | 확인 |

## 2.8 B0 대상 건물의 벽 참값 (일 8)

- 발주문 2.8의 4번(GeoGS 저자가 B0 참값을 만든 방식)은 발주문대로 기다리지 않았다. 실험 서버에는 GeoGS 논문 PDF가 없다.

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| 2.8-1 | 벽 참값을 정한 자료 | GeoGS 예제 장면의 정리본(`r1_b1_sub002_transformed.ply`, 4,709,500점)을 주 참값으로 썼다. 정리본 라벨이 없는 패치(점 5개 미만)만 드론 LiDAR(TUM2TWIN의 연직 촬영 ULS, 2024-12-17)의 점으로 채웠다. 정리본은 작성자 좌표에 [2, −29, 0] m를 더해 공통 틀에 놓고, 높이에 정리본 맞춤 −0.0746 m와 1단계 공통 이동 +0.0095 m를 더했다. 기록에는 정리본이 '대상 건물만 담는다'고 적혀 있다. 1단계 뒤의 모든 평가가 이 참값 폴더의 라벨을 읽는다 | `scripts/phd/main_stage1_v1/s04_gt_v7.py:331-348`(335행 파일, 343행 좌표 맞춤, 344행 기록, 347~348행 두 라벨). 라벨을 읽는 규칙 `scripts/phd/main_stage0_v1/regions_v1.py:45-55`, `scripts/phd/main_stage1_v1/sens_count.py:25-33`, `scripts/phd/main_stage1_v1/s1_common.py:76-100`. 기록 `S1/v3/box_gt/B0_b10/gt_summary.json`의 `gt_primary`, `labels_uls_supplement`. 같은 규칙의 앞 판 `scripts/phd/main_prep_discard_rule_v1/s04_gt.py:311-327`, `scripts/phd/main_stage0_v1/s04_gt_v6.py:335, 343`. 같은 폴더를 읽는 곳: `scripts/phd/main_stage2_v1/a15_defs.py:70`, `scripts/phd/main_stage3_v1/prep_s3.py:84`, `scripts/phd/main_baselines_v1/judgefuse/judgefuse.py:476`, `scripts/phd/main_fill_v1/obs_masked/om.py:33` | 코드와 기록 파일을 대조 | 확인 |
| 2.8-2 | 단일 반사 규칙을 B0 건물에 적용했는가 | 정리본에는 적용하지 않았다. 정리본에는 반사 횟수가 없어 적용할 수 없었고, 벽 참값은 '수직면 위의 점'만으로 골랐다(`vg = vertical_points(Xg)`). 정리본 라벨이 없는 패치를 채운 드론 LiDAR 점에는 다른 지역과 같이 '수직면 위 단일 반사 점'을 썼다(`vu = vertical_points(X) & ~multi`; `multi`는 반사 수가 2 이상인 점). 수직면 점은 0.5 m 복셀에 점이 5개 이상이고 분산이 가장 작은 방향의 연직 성분 절댓값이 0.5보다 작은 점이다. 벽 패치의 값은 벽 법선 방향으로 투영해 면 안, 면에서 2 m 안에 든 점의 법선 거리 중앙값이며, 점이 5개 이상일 때만 낸다. 설정 문장에도 '정리본에는 반사 횟수가 없어 수직면만'이라고 적혀 있다 | `scripts/phd/main_stage1_v1/s04_gt_v7.py:107-125`(`vertical_points`), `:272-295`(벽 투영), `:311`(5점 이상), `:345`; `scripts/phd/main_stage0_v1/common.py:229-238`(`multi` = `number_of_returns > 1`); `configs/phd/main_prep_measure_v1/prep_v5.json:166`(`ground_truth.patch_value`) | 코드와 설정을 대조 | 확인 |
| 2.8-3 | B0 상자의 벽 참값 점 수 (기록에 있는 값) | 상자 B0_b10 전체: 정리본 4,709,500점 가운데 수직면 점의 몫 0.582. 드론 LiDAR 26,994,350점 가운데 수직면 단일 반사 점의 몫 0.066. 상자의 LoD2 벽 패치 76,534개 가운데 정리본이 라벨을 낸 패치 35,070개(45.8 %), 드론 LiDAR가 라벨을 낸 패치 16,219개(21.2 %). 건물 하나의 값은 기록에 없다 | `S1/v3/box_gt/B0_b10/gt_summary.json`의 `gt_primary.points`, `vertical_surface_points`, `uls_points`, `labels.wall`, `labels_uls_supplement.wall` | 기록 파일을 읽음 | 확인 |
| 2.8-4 | 대상 건물 벽의 점 수 (새로 센 값) | 대상 건물의 LoD2 벽 패치는 45,997개(2,874.8 m²)이고 모두 평가 범위 안에 있다. 그 벽에 투영된 점은 정리본의 수직면 점 2,548,190개, 드론 LiDAR의 수직면 단일 반사 점 254,479개다. 드론 LiDAR가 정리본의 약 10분의 1이다. 라벨을 낸 패치는 정리본 34,271개, 드론 LiDAR 10,032개다(둘 다 낸 패치 5,341개). 평가가 쓴 라벨은 정리본 34,271개와 드론 LiDAR 4,691개로 38,962개(벽 패치의 84.7 %)이고, 평가 제외 칸을 빼면 36,680개(정리본 32,491개, 드론 LiDAR 4,189개)다. 쓴 라벨에 든 점은 정리본 2,541,377개, 드론 LiDAR 89,094개다 | 기존 소유 기록 `S1/v3/box_gt/B0_b10/gt_owner_LoD2.npz`, `gt_owner_uls_LoD2.npz`(점마다 맡은 패치)와 라벨 `labels_LoD2.npz`, `labels_uls_LoD2.npz`. 스크립트 `scripts/phd/ch6_facts64_v1/t8_b0_walls.py`, 결과 `F64/t8/b0_walls.json` | 건물의 벽 패치를 LoD2 면 목록으로 고르고 소유 기록의 점을 셈(CPU, 1분 안). 판정, 참값, 라벨은 새로 만들지 않음 | 확인. 단, 발주 1절 1번('새로 셈해야만 답할 수 있으면 하지 않는다') 밖에서 센 값이다. 쓰지 않기로 하면 바로 위 줄의 상자 값만 쓴다 |

## 3. 부록 D의 값과 코드 (발주 3절)

| 번호 | 사실 | 값 | 근거 | 확인 방법 | 상태 |
|---|---|---|---|---|---|
| D-1 | 관측 신뢰도의 기준(6장에서 정함) | 코드는 COLMAP 기하 깊이 지도에 유효한 깊이가 있으면 1, 없으면 0으로 둔다(사전 정보는 쓰지 않음). 그 거르기 값: 동의 시점 2, 재투영 1 px, NCC 0.1, 삼각측량각 3°, 깊이 비율 기준 없음. 부록 D와 어긋나지 않는다. | `configs/phd/main_prep_measure_v1/prep_v5.json:76-91`; `scripts/phd/main_stage0_v1/s03_stage1_v6.py:20-23` | 설정과 코드 읽기 | 확인 |
| D-2 | 수직 편향을 되돌리는 조건 | 같다. 수평 이동 뒤 다시 렌더한 높이 차의 중앙값의 절댓값이 NMAD보다 크면 그 중앙값만큼 옮긴다. 쓰는 화소는 지붕꼴 신뢰도 1 건물 면, 학습 영상 최대 40장, 시점마다 최대 2만 화소다. | `src/phd/prior_propagation_v6/registration.py:101-106`; `scripts/phd/main_stage0_v1/s03_stage1_v6.py:184-206` | 코드 읽기 | 확인 |
| D-3 | 수평 이동을 받아들이는 조건 | 핵심은 같다(NMAD가 줄 때만 한 걸음씩 받고, 줄지 않으면 멈춤). 코드에는 조건이 더 있다: 네 방위 가운데 세 곳 이상에 맞춤 화소가 5 % 이상이고 2,000 화소 이상일 때만 수평을 구함, 걸음은 최대 10번, 걸음이 1 cm 미만이면 멈춤, 맞춤 화소는 경사 5~60°와 중앙값에서 NMAD 세 배 안, 끝에 모든 학습 영상의 건물 면 NMAD가 정합 전보다 작을 때만 수평 이동을 남김. | `src/phd/prior_propagation_v6/registration.py:39-42, 74-98, 116-118`; `configs/phd/main_prep_measure_v1/prep_v5.json:119-141`; `scripts/phd/main_stage0_v1/s03_stage1_v6.py:270-292` | 코드와 설정 읽기 | 다름 |
| D-4 | 이상치 걸러내기 | 같다. 허용 오차는 중앙값에서 NMAD 세 배 밖을 한 번 지운 뒤 구한다. 정합의 맞춤은 걸음마다 세 배 밖을 다시 지운다. | `src/phd/prior_propagation_v6/tolerance.py:18-32`; `src/phd/prior_propagation_v6/registration.py:86-89` | 코드 읽기 | 확인 |
| D-5 | 허용 오차 | 2.5 × 다시 구한 NMAD를 지붕꼴(\|n_z\| ≥ 0.5)과 벽꼴에 하나씩 구한다는 점은 같다. 다른 점: 항공 LiDAR는 TIN에 벽면이 없어 벽에 지붕 값을 쓴다(값이 하나). LoD2 벽 화소가 2,000 미만이어도 지붕 값을 쓴다. 표본은 시점마다 종류마다 최대 2만 화소다. 값은 실험 지역이 아니라 탐색 지역(B0←B0, B173 둘←R2, R1←R1)에서 구해 상자에 고정했다. | `src/phd/prior_propagation_v6/tolerance.py:1-51`; `scripts/phd/main_stage0_v1/s03_stage1_v6.py:255-304`; `configs/phd/main_prep_measure_v1/prep_v5.json:143-148`; `docs/experiments/phd/main_stage1_v1/본실험_1단계_준비보고_v1.md:243` | 코드와 설정 읽기 | 다름 |
| D-6 | 충돌 문턱의 배수 | 같다(LoD2 1, 항공 LiDAR 2, 규칙 auto). 배수는 투표, 전파, 패치 없는 화소의 표시에만 쓰고, 사전 정보 깊이 항의 허용 구간은 두 사전 정보 모두 1τ다. | `src/phd/prior_propagation_v6/rules.py:1-27, 107-128`; `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:55-63, 1243-1256` | 코드 읽기 | 확인 |
| D-7 | 패치의 크기 | 코드는 0.25 m 고정값이고 두 사전 정보에 같다. '항공 LiDAR의 점 간격'은 앞선 작업에서 평균 점 간격 약 0.21 m를 올려 0.25 m로 정한 근거를 뜻한다. '항공 LiDAR 평균 점 간격(약 0.21 m)을 올린 0.25 m'로 적는 것이 코드와 맞다. | `configs/phd/main_prep_measure_v1/prep_v5.json:151`; `configs/phd/region_unit_v1/run_v1.json:165, 204`; 저장소 sp 값 | 설정, 저장소 읽기 | 다름 |
| D-8 | 지지의 기준 | 같다. 본 시점에서 패치 화소의 절반 이상이 신뢰도 1이면 받치는 시점이고, 받치는 시점이 본 시점의 절반 이상이면 지지 패치다(둘 다 '이상'). 본 시점은 사전 정보 렌더에서 그 패치 화소가 하나라도 보이는 시점이다. | `src/phd/prior_propagation_v6/rule.py:6-9, 38-47` | 코드 읽기 | 확인 |
| D-9 | 다수결의 동률 | 같다. 충돌 시점 수가 일치 시점 수보다 클 때만 충돌이고 같으면 일치다. 한 시점 안의 표시도 동률이면 일치다. | `src/phd/prior_propagation_v6/rule.py:43, 48-49` | 코드 읽기 | 확인 |
| D-10 | 전파 | 같다(3분의 2, 5곳, 1 m). 실제 동작: 같은 면 위 칸 길 거리로 가장 가까운 지지 패치 5곳을 1 m 안에서 모으고, 그 가운데 4곳 이상(5 × 2/3 = 3.33)이 같은 판정이면 그 판정, 아니면 섞임, 5곳이 안 되면 근거 부족이다. 즉 '3분의 2'는 '가까운 5곳 가운데 4곳'이다. | `src/phd/prior_propagation_v6/rule.py:55-67`; `src/phd/prior_propagation_v6/locations.py:241-296`; `configs/phd/main_stage0_v1/stage0_v1.json:93` | 코드와 설정 읽기 | 확인 |
| D-11 | 가우시안 신뢰도의 문턱 | 같다. 0.5(`--jbgs_e_threshold 0.5`). 신뢰도 = 받치는 시점 수 / 본 시점 수이고, 문턱 미만이 보호 후보다. | `configs/phd/main_stage0_v1/stage0_v1.json:93`; `src/phd/prior_propagation_v6/rule.py:96-104`; 영수증 명령 | 설정, 코드, 명령 읽기 | 확인 |
| D-12 | 다시 읽는 주기 | 같다. 500회(1회째와 500의 배수, 반복의 처음). | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:512-515`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:815`; 영수증 `--jbgs_e_interval 500` | 코드와 명령 읽기 | 확인 |
| D-13 | 두 깊이 항의 가중 | 같다. λ_MVS 0.05, λ_prior 0.05. | `configs/phd/main_stage0_v1/stage0_v1.json:93`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:873-875`; 영수증 명령 | 설정, 코드, 명령 읽기 | 확인 |
| D-14 | 사전 정보 깊이 항의 구간 | 같다. \|r\| ≤ τ이면 0, τ < \|r\| ≤ 4τ이면 \|r\| − τ, 4τ 밖은 3τ로 묶여 기울기가 0이다. τ는 화소마다 깊이 단위로 바꾼 값을 쓴다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:334-338, 410-426, 1334-1346` | 코드 읽기 | 확인 |
| D-15 | 보호의 학습률 배율 | 같다(0.01). 다만 자리, 회전, 크기의 갱신에만 걸리고 불투명도와 색에는 걸리지 않는다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1672-1693`; meta.json lock_mechanism | 코드와 학습 기록 읽기 | 확인 |
| D-16 | 보호가 풀리는 거리 | 같다(허용 오차의 네 배). τ는 그 가우시안이 처음 놓인 면 종류(지붕꼴, 벽꼴)의 값이고, 거리는 지붕에서 연직, 벽에서 법선 방향으로 구한다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1445-1459, 1503-1505` | 코드 읽기 | 확인 |
| D-17 | 불투명도의 하한 | 같다(0.5). 보호를 정하는 순간과 매 걸음 뒤에 건다. | `src/phd/forks/GeoGS-conf-guided-v1-r14/jbgs_judgment.py:1370-1376, 1690-1693` | 코드 읽기 | 확인 |
| D-18 | 정칙화 항 | 같다. 깊이 왜곡 가중 0(GeoGS 기본값), 법선 일치 0.05를 7,000회 뒤부터. | `src/phd/forks/GeoGS-conf-guided-v1-r14/arguments/__init__.py:121-123`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:862-863` | 코드 읽기 | 확인 |
| D-19 | 밀도 제어 | 같다. 500회 뒤부터 15,000회 전까지 100회마다(GeoGS 기본값). 기울기 문턱 0.0002, 불투명도 0.05 미만 제거, 3,000회 뒤 화면 20 px 넘는 것 제거, 불투명도 다시 놓기 3,000회마다(보호 대상은 뺌). | `src/phd/forks/GeoGS-conf-guided-v1-r14/arguments/__init__.py:124-130`; `src/phd/forks/GeoGS-conf-guided-v1-r14/train.py:1114-1147` | 코드 읽기 | 확인 |

## 부록 가. 그림 6.1 고침 (일 7, 판 v3)

낸 것: `figures/fig6_1_regions.png`(300 dpi), `figures/fig6_1_regions.pdf`, 스크립트 `scripts/phd/ch6_facts64_v1/t7_fig61.py`(6장 보조 작업의 `t3_fig61.py` v2를 고친 판), 자리 표 `tables/fig6_1_sites.csv`, `tables/fig6_1_sites_stats.json`, `tables/fig6_1_undecidable_faces.csv`. 판정과 영역 파일은 새로 만들지 않고 1단계 영역 v3를 그대로 읽었다. 이 판이 6장 보조 작업 폴더의 v2(`ch6_support_v1/figures/`)를 대신한다.

1. B0, B173 주변, R1 세 칸에 평가 범위 안의 '맞는 자료를 판단할 수 없는 곳' 패치(코드 3 전제 위배; 충돌 문턱 LoD2 1τ, 항공 LiDAR 2τ)를 두 사전 정보를 합쳐 빗금으로 칠했다. B173만 칸은 장면 전체 빗금 그대로다.
2. R1의 '판단 불가 / 반투명 지붕' 이름표와 평가 범위 밖의 점선 윤곽을 뺐다. B173 주변의 '판단 불가 / 유리 채광창'은 두었다. B0와 R1에는 이 패치가 가장 크게 뭉친 곳(1 m 안에서 이어진 가장 큰 무리)에 '판단 불가'만 달았다. 가장 넓은 면이 그 칸 전체의 34 %(B0)와 25 %(R1)라 한 면의 이름을 붙이지 않았다.
3. B0 칸 왼쪽의 '사전 정보 틀림 / 정면·지붕 가장자리' 이름표를 칸 안으로 옮겼다. 축척 막대의 글자를 막대 오른쪽에 두어 모든 칸에서 평가 범위 테두리와 겹치지 않게 했고, 북쪽 화살표도 그에 맞춰 옮겼다.
4. 범례와 그 밖의 자리 규칙은 그대로다.
5. 자리 표에 칸마다 이 경우의 넓이와 가장 넓게 모인 면 셋을 더했다. 항공 LiDAR 패치는 평면에서 0.5 m 안의 가장 가까운 LoD2 패치의 면으로 셌다(6장 보조 작업 자리 표의 규칙).

| 칸 | LoD2 | 항공 LiDAR | 합 | 가장 넓게 모인 면 셋 (두 사전 정보의 합) |
|---|---|---|---|---|
| B0 | 210.7 m² | 42.7 m² | 253.4 m² | 4959323 벽 86.6 m², 4959323 지붕 64.1 m², 4959323 지붕 44.5 m² |
| B173 주변 | 139.4 m² | 51.8 m² | 191.2 m² | 4959460 지붕 19.8 m², 4959326 지붕 16.6 m², 4959326 벽 14.6 m² |
| B173만 | 188.9 m² | 71.2 m² | 260.1 m² | 4959326 벽 79.4 m², 4959326 지붕 19.3 m², 4959326 지붕 16.2 m² (그림은 장면 전체 빗금) |
| R1 | 402.7 m² | 163.4 m² | 566.1 m² | 4906975 지붕 143.8 m², 4906975 벽 125.6 m², 4906968 벽 51.4 m² |

- 이 넓이는 발주문 2.7에 적힌 넓은 범위 검증의 값(B0 211·43 m², B173 주변 139·52 m², R1 403·163 m², B173만 189·71 m²)과 같다.
- 면 이름의 숫자는 LoD2 건물 번호(`DEBY_LOD2_` 뒤)다. 면마다의 전체 목록은 `tables/fig6_1_undecidable_faces.csv`다.

## 부록 나. 본 방법의 학습 시간 (에이전트 A, 영수증의 `wall_seconds`)

| 지역 | LoD2 씨앗 0 | LoD2 씨앗 1 | 항공 LiDAR 씨앗 0 | 항공 LiDAR 씨앗 1 | GPU 최대(nvidia-smi, MiB) |
|---|---|---|---|---|---|
| B173 주변 (0단계, r12) | 63.6분 | 67.7분 | 65.6분 | 68.2분 | 15,106~19,029 |
| B0 (1단계, r12) | 65.6분 | 69.1분 | 63.6분 | 72.1분 | 15,542~18,356 |
| R1 (1단계, r12) | 67.6분 | 63.1분 | 79.6분 | 67.1분 | 18,236~23,352 |
| B173만 (1단계 r12, LoD2 씨앗 0만 고침 작업 r14) | 74.6분 | 64.6분 | 82.1분 | 62.6분 | 12,170~18,999 |

| B0 영상 수 조건(본 방법 LoD2) | 저자 15장 | 저자 9장 | 저자 3장 | 연직 포함 13장 | 연직 포함 8장 | 연직 포함 2장 |
|---|---|---|---|---|---|---|
| 벽시계 | 30.5분 (r13) | 26.0분 | 25.0분 (씨앗 0, 1) | 53.6분 (cull3, 셋째 시도) | 32.5분 | 24.0분 |

## 부록 다. 실행 기록

- 10-15 23:40 시작. 23:42에 에이전트 셋을 같이 띄웠다(A: 일 1, 일 6, 부록 D / B: 일 2, 일 3의 1~4번 / C: 일 4, 일 5). 셋은 00:11(C), 00:20(B), 00:22(A)에 끝났다.
- 실행 세션이 그동안 한 일: 일 7 그림(`t7_fig61.py --stats` 9초, 그림 23초, 23:44~23:46), 일 8 점 셈(`t8_b0_walls.py`, 1분 안, 23:47~23:58에 세 번: 처음, 색인 확인을 더함, 제외 칸 규칙을 평가 코드와 맞춤), 일 3의 5번(기록 읽기).
- 검토: 에이전트의 '다름'을 모두 원본 줄에서 다시 확인했다(0단계 설정의 결정 문장, 공용 모듈의 규칙 표, 후보 설정, 분석자 추천 절, 첫째 준비 측정의 평지붕 문장, 결합 코드의 크기 거르기와 깊이 합치기, 영수증의 처음 방향 칸 방식, 마스크 셈의 면, 실행 기록의 동의 시점 1, 패치 크기 규칙). 평가 영상 겹침은 네 상자 모두 다시 세었다.
- 바로잡은 것: 실행 세션의 첫 겹침 셈은 0이 나왔다. 목록 한쪽의 이름에 `.JPG`가 붙어 있었기 때문이고, 이름 줄기로 맞추어 다시 세니 에이전트 둘의 값과 같았다.
- 에이전트가 쓴 명령: 파일 읽기, GPU 이름과 메모리 읽기(nvidia-smi, A), npz 머리만 읽기(B, 컨테이너), 큰 json 읽기(C, 컨테이너). 호스트 python3 표준 라이브러리로 읽기만 한 곳이 있다(A, C). 결과는 각자 `F64/agents/<A|B|C>/`에만 썼다.
- 묶기: `scripts/phd/ch6_facts64_v1/assemble_facts.py`가 네 초안의 표를 발주문 차례로 옮기고, 경로 표기를 맞추고, 번호를 달고, 실행 세션이 바꾼 상태 셋을 넣었다. 요약의 줄 번호가 실제 줄을 가리키는지, 다름과 확인 불가인 줄이 모두 요약에 있는지를 스크립트가 확인한다.
- 학습, MVS, 판정, 지표는 다시 돌리지 않았다. GPU 계산은 없다.
