# P1/P2 동일 표현 비교

`PHD-GEOGS-MVS-PGSR-MATCHED-v1` · `scientific_verdict: null`

2026-09-15 사용자는 “몇개 케이스라도 같은 조건으로 비교해보자. Mvs+pgsr
문제인지 뷰어 표시 방식 문제인지 봐야하잖아”라고 요청했다. 이는 완료된
checkpoint의 제한된 렌더링·추출·비교 실행 범위다. 새 학습 조건은 추가하지 않는다.

## 비교를 고정하는 기준

- P1/P2 × DA3 / MVS-only / MVS+PGSR, prior 0.005, native 보호, 최종 30,000 iteration.
- 기존 DA3는 봉인된 raw RGB TSDF512를 재사용한다. 신규 네 조건은 같은 원본
  `render.py`, 같은 입력 장면, 동일 mesh resolution 512와 num_cluster 50으로
  렌더링·추출한다. 실제 voxel/sdf/depth truncation을 기존 조건과 정확히 대조한다.
- 원본 표면을 smoothing, 임의 연결, opacity threshold 등으로 정리하지 않는다.
  후처리 표면은 생성되더라도 이번 주 비교에는 raw만 사용한다.
- 실제 RGB/depth 비교는 기존 evaluation camera 중 고정 ROI 투영 면적이 큰 두
  시점을 영역별로 선택한다. 동률은 원래 정렬 index를 따른다. 이 선택은 신규
  표면이나 UAS reference를 읽기 전에 봉인한다. 조건마다 같은 pose·crop과 depth
  색 범위를 사용한다. 기존 RGB 재사용은 final Gaussian PLY SHA도 확인한다.
- 기하 점수는 기존 0.1m 표면 샘플·원점 고정 UAS voxel, 고정 거리 threshold를
  그대로 사용한다. Precision/recall과 동일 reference ID의 회복/훼손을 함께 기록한다.
  UAS는 CPU 평가 단계에만 연결한다. MVS 생성 이웃 lineage의 독립성은 미확인이다.

## 표시 방식과 학습 차이를 구분한 선행 관측

원래 7열 뷰어는 DA3를 RGB mesh로, 추출 전 MVS 조건을 Gaussian 중심점으로
표시했다. 중심점은 Gaussian opacity·scale·rotation을 적용하지 않는 2px 점이므로
실제 Gaussian 렌더링과 다르다. 기본 MVS+PGSR .005에서 표시한 ROI 점 중 alpha
0.01 미만은 P1 65.01%, P2 43.93%였다. 이것만으로 실제 표면의 품질은 판정할 수 없다.

추가로 final PLY 전체를 Docker CPU로 확인한 결과는 다음과 같다. 위 ROI 통계와
모집단이 다르므로 수치를 혼용하지 않는다.

| 영역·조건 | 전체 Gaussian | opacity 중앙값 | alpha < 0.01 |
|---|---:|---:|---:|
| P1 DA3 | 6,033,926 | 0.00531 | 55.1% |
| P1 MVS | 2,026,814 | 0.36863 | 21.5% |
| P1 MVS+PGSR | 2,282,750 | 0.27071 | 24.7% |
| P2 DA3 | 4,093,957 | 0.11596 | 28.2% |
| P2 MVS | 3,504,253 | 0.25113 | 21.3% |
| P2 MVS+PGSR | 4,543,530 | 0.11218 | 26.8% |

신규 네 run의 loss/gradient 기록은 각 221개 모두 유한했다. MVS+PGSR의 multi-view
유효 표본 중앙값은 P1 2,071, P2 2,141이고 NCC는 1,811, 1,815였다. 이 기록에서는
loss가 전반적으로 무효화되거나 전체 Gaussian이 소실된 상태를 관측하지 않았다.
국소 기하의 개선·악화는 별도 문제다.

세 조건의 영상 membership 및 입력 SHA, 220개 공통 기록 시점의 camera 순서가
일치했다. P1은 같은 c08a39aa… Anchor8k, P2는 91bc9ad7… Anchor8k다. 보호 Gaussian
수도 P1 236,015, P2 114,521로 유지됐다. DA3→MVS에는 depth target과 residual 기반
동적 가중치 변화가, MVS→MVS+PGSR에는 기존 normal 항을 PGSR 세 항으로 대체한
변화가 있다. 이 두 비교를 분리한다.

## 실행·산출물

설정은 `configs/phd/geogs_mvs_pgsr_v1/matched_comparison_v1.json`, 재현 driver는
`scripts/phd/geogs_mvs_pgsr_v1/matched_compare.py`와 `run_matched_compare.sh`다.
새 산출물은 기존 task의 `matched_comparison_v1/attempt.*/` 아래 보존한다.
전체 12개 최종 보고서의 결과 경로와 분리하여 부분 비교를 전체 완료로 집계하지 않는다.

기존 P3 학습 프로세스는 계속 실행한다. GPU 0이 비면 큐의 부모 supervisor만 잠시
정지하여 다음 batch와의 경합을 막고, 새 네 조건의 표면을 순차 추출한다. 기존
학습에 종료·중지 신호를 보내지 않는다. 부모 재개는 trap 및 별도 systemd
ExecStopPost guard로 보장하며 PID와 시작 시각을 확인한다. GPU 추출이 끝나면
부모를 재개하고 새 비교의 CPU 평가·표시 생성을 수행한다.

완료 여부는 각 extraction receipt, 영역별 동일 조건 평가 receipt, 최종 publish
receipt와 실제 browser 확인으로 판단한다. 이 문서와 코드 준비 자체는 비교 결과가 아니다.

비교 페이지: [동일 조건 P1/P2 비교](http://127.0.0.1:8910/app/matched.html).
