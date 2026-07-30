# T4 — 기존 arm A 지붕 opacity 궤적

- 대상: `DEBY_LOD2_42364609`, 기존 arm A r1
- 역할: 기록 부록, 판정 미사용
- 계산 wall time: `2.02 s` (`30 min` 상한 이내)
- 그림: [arm_A_roof_opacity_trajectory.png](arm_A_roof_opacity_trajectory.png)
- 정량 원본: [arm_A_roof_opacity_trajectory.csv](arm_A_roof_opacity_trajectory.csv)

| iteration | roof proxy N | opacity median | opacity > 0.5 | cumulative prune candidates | protected | pruned |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 330 | 0.250000 | 0 | 0 | 0 | 0 |
| 5,000 | 7,408 | 0.002937 | 0 | 806,220 | 806,220 | 0 |
| 10,000 | 12,003 | 0.002696 | 0 | 4,242,838 | 4,242,838 | 0 |
| 15,000 | 14,970 | 0.002656 | 0 | 10,589,306 | 10,589,306 | 0 |
| 20,000 | 14,965 | 0.002655 | 0 | 10,589,306 | 10,589,306 | 0 |
| 25,000 | 14,964 | 0.002655 | 0 | 10,589,306 | 10,589,306 | 0 |
| 30,000 | 14,966 | 0.002655 | 0 | 10,589,306 | 10,589,306 | 0 |

고정 geometry proxy는 초기 class 6의 XY bounding box 안이면서 초기 class 2
최대 canonical Z보다 높은 Gaussian이다. checkpoint가 class 2/6 lineage를
구분해 보존하지 않으므로, 이 값은 exact class 6 lineage가 아닌 geometry proxy다.
