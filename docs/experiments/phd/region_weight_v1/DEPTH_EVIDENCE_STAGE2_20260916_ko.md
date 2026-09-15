# 2단계: P1/P2/P3 입력 관측 근거 지도

- 상태: `PASS_STAGE2_EVIDENCE_MAPS` / `PASS_SAVED_PAIR_REVIEW` / `PASS_STAGE2_BROWSER`.
- 과학적 판정: `scientific_verdict: null`.
- 목적: 자동 가중치를 만들기 전에 관측 가능성·일치·잔차·관측각·가림 후보를 따로 확인한다.
- 추가 학습 0회, GT 사용 없음, 원 입력·마스크·checkpoint 변경 없음.
- 뷰어: <http://localhost:7593/app/depth_evidence.html>, <http://localhost:8910/app/depth_evidence.html>.
- payload: `geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/viewer_rgb_v1/depth_evidence_stage2_v1/attempt.ykHdCXV6`.

## 계산 계약

원 COLMAP 937장 회원 명단, cameras.bin 및 images.bin의 결박 SHA를 확인했다.
지역별 기존 bindings의 K/R/t와 원 카메라가 절대 차이 1e-8 이내로 일치함을 검사했다.
대표 영상의 native depth SHA도 기존 학습 binding과 대조했다.

원본 1024×741 depth에서 4픽셀 간격으로 256×186 표본을 취했다. RGB ray는
K_rgb × inverse(K_native)로 옮겼다. 다른 936개 카메라에 점을 투영한 뒤 화면 안의
유효 native depth를 nearest 조회했다. 자기 영상은 지지 수에서 제외했다.
원래 COLMAP 내부의 선택 영상/비용/필터를 그대로 복구한 것은 아니다.

- 관측 가능: 점이 다른 영상 안에 투영되고 그 픽셀에 유효 depth가 있음. 실제 가시성은 미확정.
- 일치: 다른 영상의 camera-Z 잔차가 0.25m 이내이고 RGB 왕복 투영 오차가 2px 이내.
- 민감도: 0.1/0.25/0.5m를 함께 집계. 모든 조건에 2px gate가 남아 있으므로
  depth 허용 범위를 늘려도 지지 수가 거의 안 늘 수 있다.
- 가림 후보: 다른 영상에서 관측된 depth가 후보 점보다 0.25m 이상 앞에 있음.
  실제 가림/표면 오류의 확정 분류가 아니다.
- 일치 관측 잔차: 위 일치 조건을 통과한 관측의 절대 잔차 중앙값. 조건부 집계이며
  낮은 값만으로 정확도를 인증할 수 없다. 전체 관측 잔차도 별도로 보존했다.
- 관측각: 같은 후보 점을 보는 두 카메라 광선의 각도. 지도는 일치 관측 중 최대값이다.
  큰 각도가 무조건 더 정확함을 의미하지 않는다.

지역 GS train pool은 해당 지역 evaluation 영상을 제외한다. 937장 전체 pool에는
지역 evaluation과 GS 밖 영상이 포함되므로 **참고 진단**이다. 기존 MVS 자체도
전체 계열을 사용했으므로 두 pool 모두 독립 검증 표본으로 주장하지 않는다.

## R1 결과

| 영상 | 유효 표본 | 일치 영상 수 중앙값: 지역 train | 전체937 | train에서 지지 0인 비율 | R1 10% 이상 지지하는 train 영상 수 |
|---|---:|---:|---:|---:|---:|
| P1 0100_D | 3,782 | 1 | 26 | 49.79% | 7 |
| P2 0146_D | 11,065 | 8 | 12 | 0.108% | 12 |
| P2 0108_D | 10,269 | 8 | 13 | 0.068% | 13 |
| P3 0142_D | 2,217 | 17 | 25 | 0.631% | 58 |
| P3 0046_D | 15,982 | 37 | 51 | 0.044% | 51 |

P1은 지역 학습 영상 지지와 전체 MVS 계열 지지가 크게 다르다. GS에서 특정 depth가
주로 사용된다는 사실과 그 depth가 단일 영상으로 만들어졌다는 해석을 구분해야 한다.
이 수치는 실제 loss/gradient 기여나 사진에서 P1 전체가 명확히 보이는 정도를 측정하지 않는다.

P2/P3에는 다수의 일치 관측이 있다. P3의 기존 결과 악화를 단순한 관측 부재로
설명하기는 어렵다. 이 지도만으로 오차가 큰 지점을 자동 분류했다거나 prior보다
MVS가 정확하다고 판단하지 않는다. 기존 GT 오차와 동일 표본에서의 연결도 별도 검증이다.

전체 잔차에는 앞쪽 건물/물체의 가림 후보가 포함되어 수십 m 잔차도 나타났다.
따라서 전체 잔차와 일치한 관측의 조건부 잔차를 모두 표시한다. 첫 raw 지도와 수치를
그대로 보존하고, `review_manifest.json`과 `*_review.png`를 별도 추가했다.

## 화면 및 재현

- `src/apps/geogs_rgb_comparison_v1/depth_evidence.html`: 지역·영상·pool 선택, 10개 지도,
  R1/R2/R3 집계, 허용 오차 민감도, R1 지지 영상 목록, depth 경계 지도, 원 수치 다운로드.
- 기존 `weights.html`에 1단계·2단계 링크 추가.
- 생성: `scripts/phd/prior_weight_followup_v1/run_depth_evidence.sh`.
- 후처리: `review_depth_evidence.py` — 원 pair 잔차에서 지지 수를 재계산해 저장 지도와 대조.
- 각 case의 `pairs.npz`, `maps.npz`, `review_maps.npz`에 표본 좌표/라벨/잔차/각도/집계를 보존.
- 검증: 기존 투영·샘플링·가림 core 단위검사 9개 PASS. 브라우저에서 5영상×2pool,
  모바일 overflow, 기존 결과·1단계·GT 보고서 링크를 7593과 8910에서 검사해 PASS.

## 뷰어 연결 이슈

8910의 원 서버는 정상인데 작업 환경의 7593은 listener가 없어 연결이 거부됐다.
`ensure_viewer_7593.sh`로 동일 자료를 read-only로 제공하는 호환 listener를 추가했다.
기존 서버나 데이터를 교체하지 않았다. 컨테이너 시작 직후 첫 HTTP 요청은 초기화 중
연결 reset이었고 이후 두 포트의 HTTP 및 Chromium 검사를 통과했다.

## Gaussian 질문에 대한 범위 정정

P1 Anchor8k의 Gaussian 1,136,384개가 최종 1,900,424개로 증가했으므로 추가 학습 중
생성은 있었다. 그러나 보정 지면을 표현하는 비보호 집단을 시작 시점의 어느 primitive나
생성 사건과 연결할 영구 ID는 없다. 기존 비보호 집단의 이동/크기/방향 변화와 복제·분할이
가능하며, 같은 투영 영역에 여러 Gaussian이 겹쳐 기여한다. 기존 보호 집단이 남아 있다는
사실이 그 영역을 그 집단만 표현한다는 뜻은 아니다.
