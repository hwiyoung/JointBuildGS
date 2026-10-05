# P2 실제 기하·렌더 검토

`scientific_verdict: null`

P2의 기하 29/29 job과 지역 영수증, 공통 anchor 및 final 6조건의 렌더 7/7 영수증이 닫힌 뒤 검토했다. 기하 영수증은 `EVALUATED` / `PASS_GEOMETRY_EVALUATION`, 렌더는 `PASS_RENDER_QUALITY_EVALUATION`이다. 아래 결과는 P2의 단일 실행 기술 진단이며 다른 지역이나 모집단으로 일반화하지 않는다.

## 1. 입력·비교·평가 범위

- Task: `PHD-GEOGS-P1P2P3-v1`.
- `$TASK`: `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`.
- 후보 봉인 SHA256: `8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d`.
- Completion amendment SHA256: `3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6`; 범위 `PRIMARY18_SUPPLEMENTAL_INCOMPLETE`.
- 평가 영역: X [110,158), Y [86,132), Z [-49.386,-17.679)m. 고정 단면은 X=134m 및 Y=109m, 폭 0.5m이다. 폭 안의 표면 표본을 투영한 그림이며 정확한 mesh-plane 교선이나 이중 표면의 자동 판정은 아니다. 거리 색은 2m에서 포화된다.
- 작업계 EPSG:25832, 원점 이동 [690953,5336071,604], 기존 ALS Z bridge 45.7m를 유지했다. UAS 헤더는 EPSG:32632이며 새 참조 정합이나 절대 datum 보정을 하지 않았다. 절대 datum 정확도는 미검증이다.
- 영역 내 관측 UAS 2,325,976점은 기본 0.1m voxel 후 572,214점이다. 0.5m XY 참조 지지 셀은 8,799개이며 모든 높이·벽·가려진 면의 참조 피복을 보증하지 않는다.
- 기본값은 표면 간격 0.1m / 참조 voxel 0.1m, seed 0이다. 표면 간격만 .05/.1/.2m 또는 참조 voxel만 .05/.1/.2m로 바꾼 총 5설정과 거리 임계값 .1/.2/.25/.5/1/2m를 모두 유지했다. Raw가 주 추출 결과, post가 후처리 보조 결과다.
- 학습 66장 중 57장, 평가 9장이다. DA3 8배치 [8,7,7,7,7,7,7,7]의 사진 이름은 train 57장과 정확히 일치하며 중복·eval 교집합은 0이다. 다만 SfM/pose는 shared full-source이고 이 지역 사진의 과거 개발 이력이 있어 `independent_confirmatory: false`다. 기존 all-view MVS도 입력 문맥 비교이며 이 ALS arm의 초기화가 아니다.

각 지역의 동일 anchor8000에서 final30000까지 refinement 22,000회를 비교했다. 원설정은 iteration 0부터 학습한 실행이고 변경 5조건은 저장한 같은 지역 anchor8000을 복원해 이어 간 실행이다. 이를 여섯 조건 모두 처음부터 독립 학습한 비교로 부르지 않는다. `D005/D0005/D0`는 prior 깊이 가중치 .005/.0005/0, `Pnative/Prelease`는 구조 보호 유지/해제다. 보호 해제는 위치·회전·크기 gradient 감쇠와 clone/split/prune 제한을 함께 변경하므로 두 구성요소의 효과를 따로 분리하지 못한다. 모든 조건에 ALS 파생 prior 초기화와 anchor의 영향이 남아 있어 깊이 0 및 보호 해제 조합도 image-only가 아니다. DA3 adaptive controller의 원 규칙을 유지했지만 실현 가중치 궤적까지 조건 간 같다는 뜻은 아니다.

공식 LoD2 입력 자체의 실험과 **ALS 파생 표면·깊이·보호용 초기화 적용**을 구분한다. 같은 파생 입력을 여섯 조건에 사용했으며 변환 계약·공식 코드 버전·checkpoint 복원 범위는 [실험계획](EXPERIMENT_PLAN_ko_v1.md)에 따른다. 추출은 공식 bounded TSDF 경로와 고정 camera-radius 기반 depth truncation을 유지했다. 512와 1024는 같은 학습 모델에서도 서로 다른 표면을 만들 수 있으므로 해상도 선택을 학습 효과와 섞지 않는다.

## 2. 입력 baseline과 원설정의 회복·손실

| 입력 | 평균 입력→UAS (m) | 평균 UAS→입력 (m) | P / R / F1 @0.5m |
|---|---:|---:|---:|
| ALS 점군 | 1.7096 | 1.0911 | .5363 / .5261 / .5312 |
| 영상 MVS 점군 | .1940 | .4262 | .9048 / .8011 / .8498 |
| ALS 파생 prior mesh | 1.9513 | 1.2266 | .4970 / .4961 / .4966 |

ALS/MVS는 동일 고정-origin voxel 후 **점 간 NN**, 삼각형 표면은 **면적 표본→관측 UAS 및 UAS 점→삼각형** 거리다. 서로 다른 추정 대상을 단일 방법 순위로 섞지 않는다. 기본 평가 점 수는 ALS 44,888, MVS 285,341이며 voxel 크기를 같게 했다고 입력 관측 밀도·피복까지 같아지지 않는다. ALS 점군→prior mesh의 수치 차이만으로 입력 변환 손실을 정량 확정할 수도 없다.

고정 단면에서는 ALS/prior가 UAS에 가까운 반복 지붕 일부를 담으면서도 현재 UAS보다 수 m 높은 연속 윤곽을 함께 담는다. MVS는 대체로 현재 낮은 지붕을 따르지만 반복 굴곡의 골을 매끄럽게 잇거나 두껍게 보이는 구간이 있다. Anchor는 prior와 가까운 높은 윤곽, 현재 표면 근처의 윤곽, 아래쪽 추가 윤곽·파편을 함께 보인다.

GeoGS 원설정 final1024 raw의 양방향 평균은 prior의 1.9513/1.2266m에서 .6830/.5868m로 낮아지고 F1@0.5m은 .4966→.6141로 높아진다. 원설정도 큰 기하 불일치를 상당 부분 줄인다는 관찰을 인정한다. 그러나 F1@0.1m은 .3167→.1331, @0.25m은 .4256→.3636으로 낮아진다. 큰 거리의 불일치 감소와 가까운 표면·세부의 회복은 같은 결론이 아니다.

직접 표시한 고정 그림: [ALS](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/als_points.sections.png), [MVS](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/mvs_points.sections.png), [prior](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/prior_mesh.sections.png), [anchor512 raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Pnative.anchor_512.raw.sections.png), [원설정 final1024 raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Pnative.final.raw.sections.png). 각 그림에 같은 관측 UAS가 겹쳐 있다.

## 3. Final1024의 기본 수치와 독립 제어 대비

아래 거리↓, P/R/F1↑는 관측 UAS에 대한 각 지표의 방향이다. 표면 양과 평가 대상이 달라지므로 한 지표만으로 전체 복원 품질 개선을 주장하지 않는다. XY 무표본은 참조 8,799개 셀 중 표면 표본이 없는 셀 수이며 3D 결손·참조 부재의 확정 면적이 아니다.

| 조건 | 표면 | 평균 표면→UAS m | 평균 UAS→삼각형 m | P@.5m | R@.5m | F1@.5m | 면적 m² | XY 무표본 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| D005 Pnative | raw | 0.6830 | 0.5868 | 0.6048 | 0.6237 | 0.6141 | 5695.58 | 42 |
| D005 Pnative | post | 0.4922 | 0.9118 | 0.6510 | 0.5599 | 0.6020 | 4943.09 | 363 |
| D0005 Pnative | raw | 0.6309 | 0.8559 | 0.5862 | 0.4733 | 0.5238 | 4623.55 | 1 |
| D0005 Pnative | post | 0.5454 | 1.0643 | 0.6015 | 0.4597 | 0.5211 | 4426.85 | 6 |
| D0 Pnative | raw | 0.5947 | 0.8350 | 0.6204 | 0.4821 | 0.5426 | 4396.44 | 0 |
| D0 Pnative | post | 0.4951 | 1.0532 | 0.6545 | 0.4734 | 0.5494 | 4097.87 | 11 |
| D005 Prelease | raw | 0.7272 | 0.5915 | 0.5890 | 0.6103 | 0.5994 | 5756.38 | 13 |
| D005 Prelease | post | 0.5251 | 0.8956 | 0.6264 | 0.5619 | 0.5924 | 5125.90 | 75 |
| D0005 Prelease | raw | 0.6550 | 0.8581 | 0.5747 | 0.4707 | 0.5175 | 4670.02 | 1 |
| D0005 Prelease | post | 0.5316 | 1.0774 | 0.6030 | 0.4566 | 0.5197 | 4365.42 | 9 |
| D0 Prelease | raw | 0.6034 | 0.8436 | 0.5749 | 0.4573 | 0.5094 | 4690.62 | 2 |
| D0 Prelease | post | 0.5396 | 1.0562 | 0.5938 | 0.4470 | 0.5100 | 4467.59 | 11 |

조건별 원자료: `$TASK/evaluation/geometry/P2/<조건>.final.<raw 또는 post>/sample0.1_reference0.1.json`. 결과가 불리한 조건이나 후처리 표면을 제외하지 않았다.

| 변경−기준 | ΔF1@.5m raw | ΔF1@.5m post |
|---|---:|---:|
| D005_Pnative → D0005_Pnative | -0.09034 | -0.08091 |
| D005_Pnative → D0_Pnative | -0.07149 | -0.05262 |
| D005_Prelease → D0005_Prelease | -0.08190 | -0.07276 |
| D005_Prelease → D0_Prelease | -0.09005 | -0.08238 |
| D005_Pnative → D005_Prelease | -0.01467 | -0.00963 |
| D0005_Pnative → D0005_Prelease | -0.00623 | -0.00148 |
| D0_Pnative → D0_Prelease | -0.03324 | -0.03939 |

깊이 가중치를 .005에서 .0005/0으로 낮추면 native와 release 모두 F1@0.5m이 감소한다. Native 고정에서 정방향 평균은 .6830→.6309/.5947m로 낮아지지만 역방향 평균은 .5868→.8559/.8350m로 커진다. 단면의 고립 파편이나 높은 추가 윤곽이 줄어드는 동시에 현재 UAS의 지붕 골·지면에 닿는 표면이 부족해지는 양상이 있다. 깨끗해 보이는 윤곽과 완전한 현재 표면 복원을 구분한다.

보호만 해제한 final1024 raw F1@0.5m은 세 깊이 모두 낮아지며 양방향 평균도 커진다. 다만 .0005의 F1@1m은 .7933→.8050으로 상승하고, 깊이 0의 @2m도 .9169→.9198로 상승한다. 효과가 모든 임계값에서 같은 방향은 아니다. 작은 조건 차이를 반복 변동을 넘어선 확정 인과 효과로 해석하지 않는다.

같은 X=134m 단면에서 .005 release는 Y≈114–129m에 UAS의 약 −27.5m 표면보다 높은 곡면과 중간 윤곽을 남긴다. .0005/0에서는 그 넓은 상부 윤곽이 덜 두드러지지만, Y≈90–112m 반복 지붕의 골이 UAS보다 높고 얕게 이어지는 차이가 남는다. Y=109m의 X≈110–118m 지면은 들떠 있으며, 오른쪽 X≈154–158m에는 약 −40m의 다른 높이 표면이 있어도 약 −43m의 관측 지면에 닿지 않는 구간이 있다. 이는 빈 예측과 다른 형상 불일치다.

Raw→post는 여섯 조건 모두 정방향 평균을 낮추고 P@0.5m을 높이지만, 역방향 평균·p95는 커지고 R@0.5m은 낮아진다. F1 방향은 조건과 임계값에 따라 갈린다. Native의 역방향 p95는 2.0679→4.2143m, 면적은 5695.58→4943.09m²다. 0.5m 이상 관측 UAS에서 떨어진 면적 표본 추정치는 2251.00→1725.03m²지만, 참조 피복이 인증되지 않았으므로 이를 확정된 잘못된 잔존 구조 면적 감소라고 부르지 않는다.

[원설정 거리 지도](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Pnative.final.raw.distance.png), [.0005 native 거리 지도](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D0005_Pnative.final.raw.distance.png), [.005 release 단면](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Prelease.final.raw.sections.png), [.0005 release 단면](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D0005_Prelease.final.raw.sections.png), [D0 release raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D0_Prelease.final.raw.sections.png), [D0 release post](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D0_Prelease.final.post.sections.png)를 같은 범위·폭·축척으로 비교했다. 이 관찰만으로 보호 Gaussian이 이동·삭제됐는지, TSDF depth cutoff가 원인인지, 분리 윤곽이 과거 구조인지 확정하지 않는다.

## 4. 동일 해상도의 anchor→final512

각 셀은 **raw / post**다. Anchor8000과 final30000을 같은 512 추출로 비교했다.

| 조건 | F1@.1m | F1@.25m | F1@.5m | F1@1m | 평균 표면→UAS m | 평균 UAS→삼각형 m |
|---|---:|---:|---:|---:|---:|---:|
| D005_Pnative.anchor_512 | 0.1692 / 0.1702 | 0.3303 / 0.3188 | 0.4651 / 0.4376 | 0.6188 / 0.5701 | 1.4961 / 1.4622 | 0.7187 / 1.2689 |
| D005_Pnative.mesh_512 | 0.0910 / 0.0915 | 0.2732 / 0.2723 | 0.5346 / 0.5327 | 0.7993 / 0.7970 | 0.6511 / 0.5867 | 0.7372 / 0.8901 |
| D0005_Pnative.mesh_512 | 0.0494 / 0.0489 | 0.2016 / 0.2007 | 0.4598 / 0.4584 | 0.7325 / 0.7302 | 0.5834 / 0.5805 | 1.1211 / 1.1947 |
| D0_Pnative.mesh_512 | 0.0514 / 0.0512 | 0.2120 / 0.2120 | 0.4719 / 0.4718 | 0.7350 / 0.7345 | 0.5840 / 0.5695 | 1.0974 / 1.1802 |
| D005_Prelease.mesh_512 | 0.0851 / 0.0846 | 0.2575 / 0.2539 | 0.5091 / 0.5018 | 0.7855 / 0.7769 | 0.6701 / 0.6255 | 0.7747 / 0.9579 |
| D0005_Prelease.mesh_512 | 0.0512 / 0.0510 | 0.1925 / 0.1917 | 0.4562 / 0.4552 | 0.7307 / 0.7291 | 0.5963 / 0.5917 | 1.1227 / 1.1928 |
| D0_Prelease.mesh_512 | 0.0530 / 0.0528 | 0.1978 / 0.1974 | 0.4548 / 0.4539 | 0.7341 / 0.7295 | 0.5968 / 0.5873 | 1.1025 / 1.1922 |

기본값에서 원설정 raw의 anchor→final은 정방향 평균 1.4961→.6511m로 좋아지지만 역방향 평균은 .7187→.7372m로 소폭 커진다. Anchor512를 final1024와 직접 비교하면 역방향 .5868m를 사용하게 되어 이 방향을 반대로 설명할 수 있으므로 분리했다.

5개 표본/참조 설정 모두에서 모든 final raw의 F1@.1/.25m은 anchor보다 낮고 @1/2m은 높다. @.5m에서는 원설정 native/release와 D0 native raw가 anchor보다 높지만, .0005 release와 D0 release는 낮다. .0005 native raw의 기본 변화는 −.00533이며 참조 voxel .2m에서만 +.000057로 부호가 바뀐다. 이 미세한 부호 변화는 참조 표본화 민감도이지 학습 반복의 효과나 유의성 증거가 아니다. Post의 @.5m은 여섯 조건과 5설정 모두 같은 post anchor보다 높다.

512에서도 .005 release의 높은 곡면과 .0005/0의 지붕 골·들뜬 지면 차이가 남는다. 원설정 native는 X=134m의 Y≈125–129m 국소 높은 윤곽을 보이고, .005 release에서는 Y≈114–129m의 더 넓은 곡면이 보인다. 후처리가 파편을 없애도 이런 연속 윤곽·높이 차이가 전부 사라지지는 않는다.

원자료: `$TASK/evaluation/geometry/P2/D005_Pnative.anchor_512.<raw 또는 post>/sample*.json` 및 `<조건>.mesh_512.<raw 또는 post>/sample*.json`. [512 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Pnative.mesh_512.raw.sections.png), [512 release](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D005_Prelease.mesh_512.raw.sections.png), [512 .0005 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P2/D0005_Pnative.mesh_512.raw.sections.png)는 실제 표시한 같은 단면이다.

## 5. 임계값·표본화 민감도

아래는 기본값의 6개 임계값 F1이다. 점 baseline과 삼각형 표면의 거리 정의가 다르다는 제약을 함께 유지한다. 모든 post와 나머지 표본 설정의 6임계값 P/R/F1도 원자료에 보존되어 있다.

| 입력/조건 raw | .1m | .2m | .25m | .5m | 1m | 2m |
|---|---:|---:|---:|---:|---:|---:|
| als_points | 0.1527 | 0.3924 | 0.4340 | 0.5312 | 0.6019 | 0.6839 |
| mvs_points | 0.4162 | 0.6468 | 0.7029 | 0.8498 | 0.9391 | 0.9724 |
| prior_mesh | 0.3167 | 0.3987 | 0.4256 | 0.4966 | 0.5599 | 0.6356 |
| D005_Pnative.final.raw | 0.1331 | 0.2929 | 0.3636 | 0.6141 | 0.8438 | 0.9434 |
| D0005_Pnative.final.raw | 0.0655 | 0.1779 | 0.2537 | 0.5238 | 0.7933 | 0.9140 |
| D0_Pnative.final.raw | 0.0678 | 0.1849 | 0.2599 | 0.5426 | 0.8063 | 0.9169 |
| D005_Prelease.final.raw | 0.1066 | 0.2615 | 0.3373 | 0.5994 | 0.8357 | 0.9425 |
| D0005_Prelease.final.raw | 0.0584 | 0.1562 | 0.2233 | 0.5175 | 0.8050 | 0.9128 |
| D0_Prelease.final.raw | 0.0710 | 0.1864 | 0.2561 | 0.5094 | 0.7984 | 0.9198 |

| final1024 조건 | 표면 간격 민감도 F1@.5m raw / post | 참조 voxel 민감도 F1@.5m raw / post |
|---|---|---|
| D005_Pnative | 0.6140–0.6156 / 0.6019–0.6022 | 0.5943–0.6287 / 0.5781–0.6226 |
| D0005_Pnative | 0.5237–0.5242 / 0.5210–0.5219 | 0.5094–0.5491 / 0.5051–0.5479 |
| D0_Pnative | 0.5426–0.5430 / 0.5494–0.5498 | 0.5273–0.5713 / 0.5323–0.5808 |
| D005_Prelease | 0.5994–0.5998 / 0.5923–0.5935 | 0.5803–0.6132 / 0.5698–0.6110 |
| D0005_Prelease | 0.5174–0.5175 / 0.5190–0.5202 | 0.5037–0.5414 / 0.5040–0.5464 |
| D0_Prelease | 0.5090–0.5094 / 0.5098–0.5107 | 0.4960–0.5334 / 0.4951–0.5364 |

표면 간격 변화보다 참조 voxel 변화에 따른 범위가 크다. 이 범위는 동일 모델·추출 표면의 평가 표본화 민감도이며 학습 반복 변동, 신뢰구간, 새로운 최적 설정이 아니다. P2의 137개 metric JSON(삼각형 27 job×5설정 + 점군 2 job×1설정)이 822개 임계값 행을 구성한다.


## 6. 학습과 분리한 9사진의 실제 렌더

공통 anchor 및 final 6조건, 두 domain 각각 9장으로 126행의 504개 지표가 모두 유한하다. 누락·계산 실패·무한 PSNR은 0이며 모든 행이 `ASSESSED`다. 이 상태는 평가 계산의 완료를 뜻하며 아래의 실제 렌더 실패를 숨기지 않는다. 사진 index/name/image ID/camera ID/photo SHA와 domain별 bbox·화소 수가 일치하는 paired 비교다.

아래 평균은 domain별 9사진의 **비가중 산술평균**이다. 검은 예측 화소나 불리한 사진도 포함하며 full과 ROI를 합치지 않았다. 공식 Gaussian 모델의 저장 RGB를 원 사진과 비교했고, TSDF raw/post mesh를 다시 렌더한 결과가 아니다. `anchor_512`의 512는 표면 추출 해상도이며 RGB 평가 해상도가 아니다. ROI는 고정 3D prism의 투영 사각형이므로 배경·가림이 포함될 수 있고 표적만의 가시성 마스크가 아니다.

| 실행 | Domain | PSNR dB ↑ | SSIM ↑ | LPIPS VGG native01 ↓ | LPIPS VGG signed11 ↓ |
|---|---|---:|---:|---:|---:|
| anchor8000 | full | 15.022 | .4365 | .5787 | .6305 |
| anchor8000 | ROI | 13.739 | .3084 | .6047 | .6363 |
| D005 native | full | 19.374 | .6390 | .4086 | .4534 |
| D005 native | ROI | 16.440 | .4466 | .4933 | .5252 |
| D0005 native | full | 20.448 | .6609 | .4016 | .4493 |
| D0005 native | ROI | 21.902 | .7099 | .2906 | .3258 |
| D0 native | full | 20.335 | .6519 | .4023 | .4483 |
| D0 native | ROI | 21.895 | .7028 | .2956 | .3323 |
| D005 release | full | 19.219 | .6360 | .4064 | .4525 |
| D005 release | ROI | 16.548 | .4473 | .4889 | .5204 |
| D0005 release | full | 20.274 | .6567 | .4016 | .4492 |
| D0005 release | ROI | 21.853 | .7074 | .2945 | .3327 |
| D0 release | full | 20.430 | .6585 | .3994 | .4469 |
| D0 release | ROI | 22.003 | .7069 | .2880 | .3261 |

Native 보호 고정의 .005→.0005는 ROI 평균에서 PSNR +5.462163dB, SSIM +.263274, LPIPS01 −.202660, LPIPS11 −.199382다. .005→0도 +5.455062dB / +.256136 / −.197647 / −.192886다. 두 대비의 PSNR은 9사진 모두에서 올라가지만 개별 사진의 구조·지각 지표나 세부까지 좋아진 것은 아니다. 기하의 final1024 raw F1@0.5m 감소(.6141→.5238/.5426)와도 구분한다.

아래는 반올림 전 값에서의 사진 수 **개선/악화**다. 동률은 모두 0이며, 이는 정확히 같은 부동소수 값이 없다는 뜻이지 통계적 유의성이나 측정 잡음 범위를 넘었다는 뜻은 아니다.

| 대비 | Domain | PSNR | SSIM | LPIPS01 | LPIPS11 |
|---|---|---:|---:|---:|---:|
| native .005→.0005 | full | 9/0 | 9/0 | 7/2 | 5/4 |
| native .005→.0005 | ROI | 9/0 | 8/1 | 7/2 | 6/3 |
| native .005→0 | full | 9/0 | 7/2 | 7/2 | 7/2 |
| native .005→0 | ROI | 9/0 | 7/2 | 7/2 | 7/2 |
| .005 native→release | full | 4/5 | 4/5 | 5/4 | 5/4 |
| .005 native→release | ROI | 4/5 | 4/5 | 6/3 | 5/4 |
| .0005 native→release | full | 3/6 | 3/6 | 5/4 | 5/4 |
| .0005 native→release | ROI | 3/6 | 6/3 | 5/4 | 3/6 |
| 0 native→release | full | 6/3 | 5/4 | 5/4 | 4/5 |
| 0 native→release | ROI | 7/2 | 7/2 | 6/3 | 6/3 |
| anchor→native final | full | 9/0 | 8/1 | 9/0 | 9/0 |
| anchor→native final | ROI | 8/1 | 8/1 | 9/0 | 9/0 |

보호 해제의 ROI 평균 PSNR/SSIM/LPIPS01/LPIPS11 변화는 깊이 .005에서 +.107670 / +.000611 / −.004385 / −.004756, .0005에서 −.048818 / −.002504 / +.003840 / +.006893, 0에서 +.107471 / +.004077 / −.007625 / −.006148이다. 작은 평균 효과의 방향과 사진별 개선 수가 일치하지 않을 수 있으며 같은 조건 학습 반복의 품질 변동은 미측정이다.

원설정 anchor→final도 ROI 평균 +2.701070dB / +.138253 / −.111395 / −.111111로 개선한다. 원설정이 이미 회복하는 부분을 인정하면서도 아래 index8의 악화를 함께 남긴다.

## 7. 같은 실제 사진의 개선·악화·실패

점수를 읽기 전에 고정 평가 순서의 **첫째/가운데/마지막 index 0/4/8**을 수동 검토 시점으로 정했다. 공식 자동 대표 사례 선정과 별개이며 효과 크기로 바꾸지 않았다. 세 시점×7실행의 ROI montage 21장과 native/.0005 native의 index4/8 full-frame montage 4장을 직접 표시했다. 원 사진도 사전에 split SHA와 대조했다.

| Index | 실제 평가 사진 / image ID | 고정 ROI bbox [x0,y0,x1,y1) | 화소 |
|---:|---|---|---:|
| 0 | DJI_20241217084503_0075_D.JPG / 66 | [719,0,1400,623) | 424263 |
| 4 | DJI_20241217094953_0023_D.JPG / 404 | [734,135,936,256) | 24442 |
| 8 | DJI_20241217101359_0032_D.JPG / 656 | [1060,210,1400,542) | 112880 |

Camera ID는 모두 1, 사진은 1400×1013이다. 사진 SHA256은 순서대로 `e5f918528a2f1218aacf5b507f8035c91e22b05407892720fd2c1900d179dd74`, `18231b9ff668bada57bbe3cd421aa8346d17674395a7ed3cf6f2ce4bb7b56b0e`, `fd34ddc0b9491c949670586e746700a5f71bb5b7cc2d46b2bac6dc7a6061ac43`다.

- **Index0의 유지·악화:** Anchor의 크게 번지고 늘어진 지붕·벽 외곽은 모든 final에서 더 분명해지고 곡면 지붕의 반복선도 보인다. 그러나 .005 native/release가 남긴 노란 차량의 외곽, 설비·지면·수목의 세부는 낮은 깊이 네 조건에서 더 뭉개진다. 낮은 깊이에서도 지붕 반복선은 남으므로 사진 전체가 같은 정도로 악화됐다고 표현하지 않는다. 모든 final에 긴 선 형태의 번짐과 흐린 설비가 남는다.
- **Index4의 개선:** 202×121 ROI의 어두운 지붕·밝은 벽은 anchor와 .005 native/release에서 크게 찢기고 검은 결손을 보인다. 낮은 깊이 네 조건은 지붕·벽 외곽과 주요 반복선을 훨씬 잘 재현한다. 작은 설비와 배경 세부는 여전히 흐리다. ROI 개선은 full frame 평균보다 크게 나타나며, 영상의 외곽 회복을 3D 기하의 동반 회복으로 바꾸지 않는다.
- **Index8의 실패·판단 한계:** 모든 final에서 전경 건물·지붕이 크게 찢기거나 뭉개지고 검은 결손이 남는다. .005의 일부 고주파 조각도 실제 형태와 맞지 않으며 낮은 깊이가 이 시점을 해결하지 못했다. Full frame에서도 큰 왜곡이 보인다. Bbox는 전경·배경·가림을 포함하므로 이 시점의 부실한 렌더를 P2 전체 표면 추출의 전역 실패나 참조 부재로 바꾸지 않는다. 불리한 시점을 삭제하지 않았다.

| 실제 ROI | 조건 | PSNR dB | SSIM | LPIPS01 | LPIPS11 |
|---|---|---:|---:|---:|---:|
| index0 | D005 native | 23.450 | .7391 | .2791 | .3122 |
| index0 | D0005 native | 23.922 | .7256 | .3165 | .3552 |
| index4 | D005 native | 12.101 | .2334 | .6114 | .6313 |
| index4 | D0005 native | 22.822 | .7638 | .1976 | .2223 |
| index8 | D005 native | 9.256 | .1160 | .6632 | .6928 |
| index8 | D0005 native | 10.249 | .1861 | .6613 | .6928 |

Index0은 PSNR이 조금 올라가도 SSIM과 두 LPIPS가 모두 나빠지는 사례다. Index8의 모든 final ROI PSNR은 9.256–10.395dB, SSIM은 .1160–.2013에 머문다. Anchor→native에서도 이 시점의 ROI PSNR은 10.543→9.256, SSIM은 .1829→.1160으로 악화한다. 표에서 같아 보이는 index8 LPIPS11은 실제로 .6928036213→.6928197145로 아주 조금 악화하며, 미세 차이에 의미를 부여하거나 동률로 재분류하지 않았다.

실제 비교 파일: [index0 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png) / [.0005 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png), [index4 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D005_Pnative/final/montages/00004_fixed_prism_projected_bbox.png) / [.0005 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D0005_Pnative/final/montages/00004_fixed_prism_projected_bbox.png), [index8 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D005_Pnative/final/montages/00008_fixed_prism_projected_bbox.png) / [.0005 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D0005_Pnative/final/montages/00008_fixed_prism_projected_bbox.png). 각 montage는 **실제 사진 / 저장 RGB 렌더 / 고정 0…255 평균 절대 RGB 오차** 순서다. [Index4 full frame](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D005_Pnative/final/montages/00004_full_frame.png)과 [index8 full frame](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P2/D005_Pnative/final/montages/00008_full_frame.png)의 청록색 사각형으로 ROI 위치를 확인할 수 있다.

## 8. 원인 해석의 경계와 후속 질문

이번 관찰의 연결은 다음과 같다.

1. **관찰:** 원설정도 큰 prior 불일치를 줄이고 일부 현재 영상의 외관을 회복한다. 깊이 약화는 별도 높은 윤곽과 일부 렌더 찢김을 줄이지만 지붕 골·지면 높이의 불일치, 다른 사진의 세부 손실, index8 실패를 남긴다.
2. **구현·입력 영향:** ALS 표면화 및 고정 좌표계, prior 초기화·anchor, 공식 학습의 DA3 적응 제어, 512/1024 추출, TSDF 통합·depth cutoff 및 post를 모두 포함한 결과다. 이 중 하나를 표면 그림만으로 원인 확정하지 않는다. 보호 해제도 gradient와 densification 보호의 묶음 대비다.
3. **원방법과의 관계:** GeoGS가 오류·부분 결손 prior를 다루는 원문 실험과 이번 ALS 변형의 오차 종류·시간차·피복이 같다고 가정하지 않는다. 원설정의 회복을 인정하면서도 이 조건에서의 미해결 현상을 남긴다. ALS 변형의 결과를 공식 LoD2 입력에 대한 포괄적 실패나 우리 방법의 우위로 바꾸지 않는다.
4. **수정 필요성의 범위:** 이 P2 결과는 큰 오류 완화·가까운 기하·영상 세부·관측된 표면의 유지 사이 교환관계를 추가로 검증할 근거다. 아직 새로운 판단 알고리즘이나 반복 재판단의 필요성·우위를 증명하지 않는다.
5. **후속 검증 질문:** 어떤 입력/관측 구간에서 높은 윤곽을 줄이면서 지붕 골·지면·원래 좋은 세부를 유지할 수 있는지, 실현 DA3 가중치와 추출 조건이 차이에 얼마나 관여하는지, 같은 조건 반복의 변동을 넘는지 분리해 검증해야 한다. 반복 재판단을 나중에 도입한다면 동일 판단을 한 번 적용한 조건과의 추가 대비가 필요하다.

고정 단면에서 UAS와 가까운 구간·떨어진 구간을 관찰했지만 지역 전체를 영상 또는 ALS의 정답 영역으로 새 라벨링하지 않았다. 단면의 관측 부족·참조 부재를 방법 실패로 바꾸거나, MVS에 점이 없다는 사실만으로 영상 관측이 없다고 판단하지 않는다. 자동 지역군·대표 사례 분석과 이 수동 고정 단면/사진 검토의 선택 근거도 구분한다.

보조 `native_repeat_1`은 P1/P2의 CUDA OOM 학습 실패와 P3의 미시도를 그대로 유지한다. P2 보조 실패의 driver 비용 20.131426초는 성공한 주 실행과 별개이며 품질 지표는 null이다. 보조 품질 미측정을 기하 추출 실패나 참조 부재로 채우지 않는다. 같은 조건의 완성된 반복 쌍이 없으므로 품질 변동·확증 추론은 미측정이다.

## 9. 근거와 검토 범위

- [기하 원자료 822행 CSV](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/geometry/P2/geometry_metrics.csv), [기하 지역 영수증](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/geometry/P2/receipt.json). 지역 영수증 SHA256: `8f928c1c8a400f22f5b0c8c0ab1efd0ab0c72348800a409d6a97fc2544b26f02`.
- 기하의 29개 닫힌 job / 137개 metric JSON을 Docker CPU1/RAM512MiB에서 읽고 137 metric와 29 job 영수증의 읽기 전후 bytes 동일을 확인했다. 기본 수치·민감도·조건 차이는 이 원자료에서 계산했다. 단면·거리 그림 58장은 분담하여 실제 표시했다. Gaussian 중심점을 최종 표면으로 사용하지 않았다.
- 렌더 원자료는 `$TASK/evaluation/renders/P2/<조건>/final/receipt.json` 및 `D005_Pnative/anchor_512/receipt.json`의 사진별 `rows`다. 7개 영수증을 CPU1/RAM2GiB 이내의 별도 읽기 전용 검토로 대응 관계·유한 값·평균·paired 차이·읽기 전후 SHA/크기 동일을 확인했다.
- 입력 split은 `$TASK/inputs/P2/scene/split_manifest_da3_v2.json`, SHA256 `3a40213d46ee611b56f28910081c74517c26a9ed1b320899ebf692146744cd16`이다. DA3 train-only 이름 집합과 사전 선택 사진 3장의 SHA를 확인했다.
- P2 기하 stage는 2026-09-08 21:25 KST, 렌더 stage는 21:27 KST에 PASS가 확인됐고, 이 문서는 그 뒤 닫힌 결과의 수동 검토를 기록한다. 이 문서의 파일 링크 25개 존재 및 실제 그림 표시 확인은 통합 viewer 전체의 browser QA 또는 전체 프로젝트 보존 검사와 별개다. 이후 전 지역 분석·viewer 및 보존 결과는 소유 문서에서 별도로 연결한다.
- 본 검토에서는 기존 입력·결과·설정·서비스를 변경하지 않고 이 문서만 추가했다. 새 학습, 아카이브 이동, 정합 보정, 평가 설정 선택을 하지 않았다. `scientific_verdict: null`을 유지한다.
