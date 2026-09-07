# P1/P2 동일 조건 비교 결과

`PHD-GEOGS-MVS-PGSR-MATCHED-v1` · 2026-09-15 · `scientific_verdict: null`

**표시 차이가 거칠음을 과장했지만, 실제 출력의 문제도 남는다.** 동일한 raw RGB
TSDF512와 같은 촬영 시점으로 비교하니 MVS 교체는 두 영역의 기하 지표를 개선했다.
PGSR 추가 효과는 그보다 작고, P2에서는 완전성 증가와 정확도 손실이 함께 나타났다.
이는 prior 0.005·보호 유지의 두 개발 사례에 대한 관측이다.

[동일 조건 3열 뷰어](http://127.0.0.1:8910/app/matched.html) ·
[봉인 입력·방법](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/plan.json)

## 실제 비교 조건

P1/P2의 DA3, MVS-only, MVS+PGSR를 prior 0.005, native 보호, 같은 Anchor8k에서
30,000 iteration까지 학습한 결과로 비교했다. 기존 DA3 raw512는 봉인 원본을
재사용하고 신규 네 조건은 동결된 동일 renderer로 추출했다. 실제 voxel/sdf/depth
truncation과 num_cluster가 영역별로 정확히 일치했다. 표면 정리·평활화·opacity
필터는 하지 않았다. 기존 학습 결과에는 쓰지 않고 새 extraction copy를 사용했다.

같은 시점 RGB/depth는 P1 evaluation index 0·12, P2 0·1이다. 고정 ROI의 투영 면적이
큰 두 시점을 신규 표면과 UAS를 보기 전에 선택했다. 같은 crop, 원사진과 실제
렌더, 공통 depth 색 범위를 사용했다. P1 reference 246,125점과 P2 572,214점은
기존 0.1m voxel 규칙으로 선택한 동일 원본 ID이며 각 조건의 대응을 검증했다.

## 기하: 정확도와 완전성

고정 거리 기준 0.5m. Precision은 표면 표본 중 관측 UAS와 가까운 비율, recall은
관측 UAS 중 예측 삼각형 표면과 가까운 비율이다. UAS 미관측 부분 자체가 오차의
참값인 것은 아니며, 이 표는 관측 reference에 대한 개발 진단이다.

| 영역 | 조건 | Precision | Recall | F1 | 표면→UAS 평균 m | UAS→표면 평균 m |
|---|---|---:|---:|---:|---:|---:|
| P1 | DA3 | 42.46% | 60.62% | 0.4994 | 1.2446 | 0.5958 |
| P1 | MVS-only | 52.45% | 70.63% | 0.6020 | 1.1433 | 0.4541 |
| P1 | MVS+PGSR | 54.85% | 74.25% | 0.6309 | 1.0894 | 0.4099 |
| P2 | DA3 | 54.90% | 52.09% | 0.5346 | 0.6511 | 0.7372 |
| P2 | MVS-only | 62.99% | 72.41% | 0.6737 | 0.6294 | 0.4110 |
| P2 | MVS+PGSR | 61.88% | 77.92% | 0.6898 | 0.6614 | 0.3500 |

DA3→MVS의 F1 변화는 P1 +0.1026, P2 +0.1391이다. MVS→MVS+PGSR는 각각 +0.0289,
+0.0161이다. P2의 PGSR 추가는 recall +5.52%p와 precision −1.11%p를 함께 가져왔고,
표면→UAS 평균 거리는 0.6294m에서 0.6614m로 증가했다. F1만으로 모든 출력이
깔끔해졌다고 말할 수 없다. 같은 P2 비교에서 1m·2m F1은 오히려 각각
0.8321→0.8294, 0.9612→0.9530으로 감소했다. 모든 기존 threshold를 CSV에 보존했다.

[P1 전체 거리 표](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/regions/P1/metrics.csv) ·
[P2 전체 거리 표](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/regions/P2/metrics.csv)

## 같은 관측점의 회복과 훼손

0.5m 밖→안은 회복, 안→밖은 훼손이다. 새로운 표면을 더 많이 생성하여 recall을
올린 것과 기존의 잘 맞던 부분을 유지한 것을 구분한다.

| 영역 | 변화 | 회복 점 | 훼손 점 | 순증가 |
|---|---|---:|---:|---:|
| P1 | DA3→MVS | 41,864 | 17,239 | 24,625 |
| P1 | MVS→MVS+PGSR | 17,406 | 8,497 | 8,909 |
| P2 | DA3→MVS | 170,298 | 54,051 | 116,247 |
| P2 | MVS→MVS+PGSR | 49,559 | 17,998 | 31,561 |

## 화면에서 확인한 잔여 문제

- **P1:** MVS 두 조건은 고정 단면에서 현재 바닥 높이의 표면을 DA3보다 많이
  복원한다. 동시에 기존 지붕 높이의 상부 잔여층도 남는다. 따라서 지붕을 전부
  바닥으로 옮겨 단일 표면으로 정리한 결과는 아니다. 같은 index 0의 실제 RGB에서
  MVS+PGSR에 큰 푸른색 번짐도 보인다. 이는 중심점 뷰어가 만든 점이 아니다.
- **P2:** MVS 계열은 관측 지붕·벽에 가까운 면을 더 복원하지만 지붕 아래의 별도
  층이 남는다. PGSR 조건의 고정 X=134m 단면에는 관측 지붕보다 위쪽의 추가 조각도
  나타난다. 이 관측은 위 precision/거리의 손실과 양립한다. 특정 loss 항이 원인인지는
  이번 세 조건 비교만으로 분리하지 못한다.

[P1 동일 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/regions/P1/sections.png) ·
[P2 동일 단면](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_mvs_pgsr_v1/PHD-GEOGS-MVS-PGSR-v1/matched_comparison_v1/attempt.uWs3ytqy/regions/P2/sections.png)

“기하 loss가 적용되지 않아서”라는 설명은 현재 로그와 맞지 않는다. 기록된
loss/gradient는 유한했고 PGSR의 multi-view 유효 표본도 존재했다. 반대로 수치가
유한하다는 사실이 이중층이나 부유 표면의 제거를 보장하지도 않는다. PGSR 이식은
기존 normal 항을 대체하는 expected-depth 기반 세 항이며 전체 PGSR renderer를
재현한 것은 아니다. MVS 생성 영상의 평가 독립성도 미확인이다.

## 실행 증거와 범위

새 네 extraction과 영역별 평가·publish는
`matched_comparison_v1/attempt.uWs3ytqy`에서 PASS했다. 기존 P3 학습은 종료하거나
중지하지 않았고 dispatcher만 추출 동안 대기 후 재개했다. 전체 12개 학습·최종
후처리 큐는 별도로 진행한다. 이번 부분 비교를 전체 matrix 완료로 집계하지 않는다.

해시 열거 문제로 GPU 시작 전에 종료된 두 attempt도 보존했다. 정확한 원인과 수정은
ISSUES의 MGP-012에 기록했다. 브라우저 기술 검증과 보조 연결성 진단은 각자의
새 receipt로 별도 기록하며, 과학적 판정은 null을 유지한다.

실제 브라우저 검증은 137개 검사 PASS, 오류 0개다. 여섯 mesh의 실제 buffer SHA,
동기 카메라, 네 촬영 뷰의 RGB/depth 28개, 데스크톱·모바일 PNG 11개를 확인했다.
증거는 `matched_comparison_v1/browser_qa/attempt.20260915T021452Z.9Hvyqn5b/receipt.json`이다.
단, 공통 depth 전체 범위에 큰 값이 포함되어 색 대비가 낮다(P1 첫 뷰 10.58–494.11m,
P2 첫 뷰 45.52–2342.00m). 세부 기하는 3D 표면·고정 단면·수치와 함께 읽어야 한다.
이 depth 색상 대비 한계는 렌더 depth나 표면 점수를 바꾸지 않는다.

추가 연결성 진단은 표시용 복제 정점 대신 원본 native edge ID와 ROI 내 양수 edge
길이로 연결을 정의하고 정확한 clipping 면적을 합산했다. P1의 component 수는
DA3/MVS/PGSR 738/794/953, 최대 면적 비율은 91.85/93.08/90.94%다. P2는
822/1,034/921개, 80.82/85.03/85.99%다. 따라서 PGSR의 단절 변화 방향도 영역마다
다르며 component 수만으로 오차를 판정할 수 없다. CPU 2개·8GiB, GPU/GT 접근 없이
9.996초에 완료했다. 최초 ROI schema 실패와 수정 후 fixture 9개 PASS는
`component_diagnostic`에 보존했다.
