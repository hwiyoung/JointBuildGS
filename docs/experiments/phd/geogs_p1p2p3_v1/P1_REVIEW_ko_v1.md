# P1 실제 기하·렌더 검토

`scientific_verdict: null`

상태: **P1 기하 29/29 job 및 지역 영수증 PASS, 렌더 7/7 영수증 PASS, 아래 수동 검토 완료**. 기하 표는 `run_receipt.json: EVALUATED`를 확인한 결과만 포함한다. 지역 `receipt.json`은 `PASS_GEOMETRY_EVALUATION`, 기계 판독 표 822행을 기록한다. 렌더는 공통 anchor와 final 6조건의 `PASS_RENDER_QUALITY_EVALUATION`을 확인한 뒤 읽었다. 다른 지역의 결과로 일반화하지 않는다.

## 1. 입력과 평가 범위

- Task: `PHD-GEOGS-P1P2P3-v1`.
- Task payload root (`$TASK`): `/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1`.
- 후보 봉인 SHA256: `8fc78431dcdfc1bf803c0ac2db4a5bb2cad75c1c163ce2519b571d3710cd011d`.
- Completion amendment SHA256: `3e200db7de4cc171158b08deccffd3869bfd2d30c2a5b89805b86ad1903112c6`; 범위 `PRIMARY18_SUPPLEMENTAL_INCOMPLETE`.
- P1 고정 영역: X `[-23,7)`, Y `[-21,9)`, Z `[-44.272,-25.962)`m. 아래 수치는 기본 표면 표본 간격 0.1m / 참조 voxel 0.1m, 별도 표기가 없는 한 final1024 결과다.
- 고정 단면은 X=-8m 및 Y=-6m, 폭 0.5m이다. 단면은 폭 안의 평가 표본을 투영한 것으로 정확한 mesh-plane 교선이나 이중 표면의 자동 판정이 아니다. 거리 그림의 색은 2m에서 포화된다.
- 작업계 EPSG:25832, UAS 헤더 EPSG:32632, 기존 ALS Z bridge 45.7m와 기존 원점 이동을 유지했다. 새 UAS 정합이나 절대 datum 보정은 하지 않았고 절대 datum 정확도는 검증되지 않았다.
- ROI의 관측 UAS 1,127,634점은 기본 voxel 적용 후 246,125점이다. 0.5m XY 셀의 참조 점 존재는 모든 높이·벽면·가려진 면의 참조 피복을 보증하지 않는다.

입력·제어·임계값을 결과에 맞추어 바꾸지 않았다. 학습 반복 P1/P2 CUDA OOM 실패와 P3 미시도를 그대로 남기므로 같은 조건의 품질 변동은 측정되지 않았다. 아래 대비는 단일 실행의 기술적·서술적 차이다.

## 2. 입력 baseline에서 실제로 보이는 충돌과 근접 영역

| 입력 | 평균 입력→UAS (m) | 평균 UAS→입력 (m) | P / R / F1 @0.5m |
|---|---:|---:|---:|
| ALS 원점군 | 1.0858 | 0.8988 | 0.6471 / 0.6776 / 0.6620 |
| 영상 MVS 원점군 | 0.1411 | 0.3849 | 0.9656 / 0.7793 / 0.8625 |
| ALS 파생 prior mesh | 1.1136 | 0.8460 | 0.6376 / 0.6972 / 0.6661 |

ALS/MVS는 동일 고정-origin voxel 후 **점 간 NN**, prior mesh는 면적 표본→관측 UAS와 **UAS 점→삼각형** 거리다. 같은 estimand로 섞거나 이 표만으로 센서·알고리즘의 우열을 주장하지 않는다. 기본 평가 점 수는 ALS 19,556, MVS 117,690으로, voxel 크기를 같게 했다고 원래 관측 밀도·피복까지 같아지는 것은 아니다. MVS는 기존 all-view 산출물 계보를 유지하며 독립적인 새 취득 실험으로 간주하지 않는다.

실제 고정 X=-8m 단면의 Y≈-21…-5m에서 ALS/prior의 경사진 면은 Z≈-37m, 관측 UAS의 평탄면은 Z≈-42m로 약 4–5m 분리된다. MVS는 대체로 아래 UAS 면을 따른다. 반면 Y≈6…9m의 높은 면과 일부 낮은 평탄면에서는 prior도 UAS에 가깝다. 이 구분은 이번 그림에서 관찰한 위치이며, 지역 전체를 ALS 오류 또는 영상 정답으로 지정한 라벨이 아니다. Y=-6m 단면의 수목 형태 비평면 구간은 MVS의 역방향 거리도 커서 정방향 평균만으로 완전성을 주장할 수 없다.

원자료: `$TASK/evaluation/geometry/P1/{als_points,mvs_points,prior_mesh}/sample0.1_reference0.1.json` 및 같은 디렉터리의 `run_receipt.json`. 실제 그림: `$TASK/evaluation/viewer/P1/{als_points,mvs_points,prior_mesh}.{sections,distance}.png`.

## 3. final1024 조건별 기본 수치

아래 Δ 해석에서 거리↓, F1↑가 관측 UAS에 대한 해당 지표의 방향이다. 표면 양 자체가 바뀌므로 거리·면적·완전성을 함께 본다. Raw/post는 같은 학습 결과의 추출·후처리 산출물이므로 별도 학습 반복이 아니다.

| 조건 | 표면 | 평균 표면→UAS (m) | 평균 UAS→삼각형 (m) | F1@0.1m | F1@0.5m | F1@1m | 면적 (m²) |
|---|---|---:|---:|---:|---:|---:|---:|
| D005_Pnative | raw | 1.2583 | 0.5755 | 0.2023 | 0.5279 | 0.6646 | 2901.34 |
| D005_Pnative | post | 1.2373 | 0.7578 | 0.2027 | 0.4971 | 0.6331 | 2608.31 |
| D0005_Pnative | raw | 0.9736 | 0.8952 | 0.0934 | 0.3811 | 0.6275 | 1724.87 |
| D0005_Pnative | post | 0.8437 | 1.0615 | 0.0880 | 0.3520 | 0.6036 | 1530.70 |
| D0_Pnative | raw | 1.1858 | 0.8421 | 0.0984 | 0.3907 | 0.6151 | 1661.89 |
| D0_Pnative | post | 0.8560 | 1.1901 | 0.0953 | 0.3564 | 0.5671 | 1213.52 |
| D005_Prelease | raw | 1.3517 | 0.5693 | 0.1991 | 0.5534 | 0.6932 | 2745.93 |
| D005_Prelease | post | 1.1836 | 0.8308 | 0.1941 | 0.5159 | 0.6556 | 2336.09 |
| D0005_Prelease | raw | 1.0260 | 0.8587 | 0.0849 | 0.3691 | 0.6029 | 1841.52 |
| D0005_Prelease | post | 0.8632 | 1.0591 | 0.0806 | 0.3435 | 0.5720 | 1576.82 |
| D0_Prelease | raw | 1.2189 | 0.8352 | 0.0669 | 0.3559 | 0.5983 | 1864.11 |
| D0_Prelease | post | 1.1108 | 1.1283 | 0.0588 | 0.2979 | 0.5371 | 1535.70 |

원자료는 `$TASK/evaluation/geometry/P1/<조건>.final.<raw 또는 post>/sample0.1_reference0.1.json`이며 각 job의 `run_receipt.json`이 닫힌 뒤 읽었다. 후처리 결과를 최선 실행으로 선택하지 않았다.

## 4. 요인별 현재 관찰

### 깊이 가중치 변경, 보호 native 고정

`.005→.0005`에서는 X=-8m의 과거 상부면이 크게 줄고 낮은 UAS 면 쪽으로 이동한 형상이 나타난다. 그러나 Y≈-13…2m의 넓은 구간은 여전히 약 0.5–1.5m 들떠 있고 북측 높은 면·수목 형태 구간의 대응도 달라진다. `.005→0`에서도 과거 높은 면이 줄지만 들뜸, 원래 근접했던 면의 손실, post의 결손이 남는다. 이 변화는 현재 표면 전체가 정확히 회복됐다는 뜻이 아니다.

Raw F1@0.5m은 `.5279→.3811/.3907`, UAS→삼각형 평균은 `.5755→.8952/.8421m`이다. 정방향 평균은 `.0005`에서 낮아지지만 역방향과 가까운 임계값의 F1은 나빠진다. 큰 거리의 잔존 면이 줄어드는 것과 가까운 표면·피복을 잃는 것이 동시에 관찰된다.

### 보호 native→release, 깊이 고정

`.005`에서 raw F1@0.5m은 `.5279→.5534`이지만 정방향 평균은 `1.2583→1.3517m`이다. 단면의 높은 잔존 면은 계속 보이므로 구조 보호 해제만으로 그 면이 해결됐다고 해석할 수 없다. `.0005`에서 raw F1@0.5m은 `.3811→.3691`, 역방향 평균은 `.8952→.8587m`로 역시 방향이 갈린다. 작은 차이의 반복 변동 대비 크기는 현재 측정되지 않았다.

깊이 0에서 보호 해제의 raw F1@0.5m 변화는 `.3907→.3559`, post는 `.3564→.2979`이다. D0 release의 X=-8m 단면에서 Y≈6…9m의 추가 높은 표본 띠와 북측 큰 거리 영역이 보인다. 이 조건도 높은 과거 면의 일부 감소를 현재 표면 전체의 회복으로 해석할 수 없다.

| 대비: 변경−기준 | ΔF1@0.5m raw | ΔF1@0.5m post |
|---|---:|---:|
| 깊이 .005→.0005, native 고정 | -0.14680 | -0.14511 |
| 깊이 .005→0, native 고정 | -0.13716 | -0.14067 |
| 깊이 .005→.0005, release 고정 | -0.18422 | -0.17239 |
| 깊이 .005→0, release 고정 | -0.19746 | -0.21807 |
| native→release, 깊이 .005 | +0.02551 | +0.01887 |
| native→release, 깊이 .0005 | -0.01191 | -0.00840 |
| native→release, 깊이 0 | -0.03479 | -0.05852 |

차이의 차이 `(release−native)_낮은깊이 − (release−native)_.005`는 F1@0.5m에서 .0005의 raw/post `-0.03742/-0.02727`, 0의 `-0.06030/-0.07740`이다. 이는 효과가 단순히 일정하게 더해지지 않는다는 서술적 대비다. 통계적 상호작용 검정이나 반복 변동을 넘어서는 인과 추정은 아니다. 이후 정식 factor exporter의 원자료와 동일한 차감 순서로 대조할 수 있다.

보호 해제는 gradient 감쇠와 clone/split/prune 제한을 함께 바꾼다. 두 구성요소의 단독 효과를 분리하지 못한다. DA3 adaptive controller는 같은 원 규칙을 유지하더라도 실제 loss 이력에 따라 실현 가중치 궤적이 달라질 수 있다. 따라서 이 대비는 고정 DA3 궤적 아래의 순수 직접 효과가 아니다. 모든 조건에 prior 초기화와 같은 지역 anchor의 영향이 남으므로 깊이 0 및 release 조합도 image-only가 아니다.

### Raw→post와 면적 추정치

Native raw의 높은 고립 단면 표본 일부는 post에서 사라지지만 recall@0.5m도 `.6294→.5437`로 줄고 역방향 평균은 `.5755→.7578m`로 커진다. Native의 표면 면적은 `2901.34→2608.31m²`, 0.5m 이상 관측 UAS에서 떨어진 면적 표본 추정치는 `1582.61→1414.20m²`다. 후자는 확정된 잘못된 잔존 구조 면적이 아니다. 참조 피복 차이와 표면 총량 감소를 함께 해석해야 한다.

특히 D0 native post는 XY 참조 셀 중 표본이 없는 셀이 745개(raw 71개)다. 이 수치는 표면 표본의 XY support 진단이며 실제 건물 결손 면적이나 전부 참조가 있는 3D 표면이라는 뜻은 아니다.

위 위치를 직접 비교하는 고정 단면: [prior](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/prior_mesh.sections.png), [MVS](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/mvs_points.sections.png), [원설정 raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.final.raw.sections.png), [깊이 .0005 native raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.final.raw.sections.png), [깊이 0 release raw](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Prelease.final.raw.sections.png). 각 그림에 같은 관측 UAS 표본이 겹쳐 있다. [원설정 거리 지도](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.final.raw.distance.png)와 [약한 깊이 거리 지도](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.final.raw.distance.png)는 같은 두 방향·범위에서 비교한다.

## 5. 같은 해상도의 anchor→final512

같은 512 추출 해상도의 anchor 및 final 14개 raw/post job, 각 5개 표본/참조 설정 JSON과 단면·거리 그림을 완료 후 확인했다. Final1024와 anchor512를 그대로 빼서 학습 효과로 쓰지 않는다. 각 셀은 **raw / post**다.

| 조건 | F1@0.1m | F1@0.25m | F1@0.5m | F1@1m | 평균 표면→UAS (m) | 평균 UAS→삼각형 (m) |
|---|---:|---:|---:|---:|---:|---:|
| anchor8000 | .3201 / .3208 | .5060 / .5037 | .6408 / .6362 | .7448 / .7389 | .9504 / .9553 | .7596 / .8726 |
| D005 native | .1484 / .1481 | .3362 / .3323 | .4994 / .4903 | .6647 / .6424 | 1.2446 / 1.2514 | .5958 / .7320 |
| D0005 native | .0855 / .0831 | .2059 / .1982 | .3759 / .3607 | .6323 / .6192 | .8465 / .8276 | .9730 / 1.0247 |
| D0 native | .0973 / .0956 | .2299 / .2219 | .3935 / .3729 | .6255 / .5980 | .9382 / .9226 | .8785 / 1.0141 |
| D005 release | .1539 / .1530 | .3488 / .3414 | .5188 / .5008 | .6788 / .6556 | 1.2430 / 1.2419 | .5820 / .7305 |
| D0005 release | .0996 / .0970 | .2392 / .2309 | .3834 / .3719 | .6275 / .6116 | .8417 / .8260 | .9115 / .9935 |
| D0 release | .0748 / .0737 | .1930 / .1852 | .3411 / .3239 | .6098 / .5901 | 1.1414 / 1.1207 | .9255 / .9975 |

0.1/0.25/0.5/1m의 F1은 모든 refinement 조건에서 같은 raw/post anchor보다 낮다. 원설정에서도 정방향 평균 악화와 역방향 평균 개선이 동시에 발생한다. Native/release의 높은 면 잔존, 낮은 깊이의 들뜬 저면과 다른 영역의 손실은 1024에서 본 교환관계와 맞는다. 그러나 보호 효과의 작은 수치는 추출 해상도에 따라 달라진다. 예를 들어 .0005 보호 해제의 raw F1@0.5m은 512에서 `+0.00748`, 1024에서 `-0.01191`이다. 해상도를 유리하게 골라 단일 개선 주장에 쓰지 않는다.

512의 5개 표본/참조 설정 모두에서 raw F1@0.5m은 anchor보다 낮다. Anchor 범위는 `.6287–.6409`, 모든 final 범위의 최대는 `.5189`이다. 반대로 2m raw F1은 anchor `.8369`보다 모든 final(`.8457–.9326`)이 높다. 이 범위는 표본·참조 민감도이며 반복 변동이나 신뢰구간이 아니다.

원자료: `$TASK/evaluation/geometry/P1/D005_Pnative.anchor_512.<raw 또는 post>/sample*.json` 및 `<조건>.mesh_512.<raw 또는 post>/sample*.json`. 그림은 `$TASK/evaluation/viewer/P1/<동일 candidate>.sections.png`와 `.distance.png`.

## 6. final1024 민감도

Native의 F1@2m은 prior `.7856`에서 raw `.8342`로 높아지지만 F1@0.5m은 `.6661→.5279`로 낮아져 임계값에 따라 결론이 달라진다. 아래 범위는 각각 나머지 설정을 0.1m로 고정하고 표면 간격 또는 참조 voxel만 .05/.1/.2m로 바꾼 등록 결과의 F1@0.5m이다.

| 조건 | 표면 간격 민감도 raw / post | 참조 voxel 민감도 raw / post |
|---|---|---|
| D005 native | .5260–.5279 / .4959–.4972 | .5167–.5279 / .4868–.4971 |
| D0005 native | .3808–.3812 / .3520–.3534 | .3775–.3911 / .3520–.3587 |
| D0 native | .3906–.3916 / .3554–.3564 | .3796–.4135 / .3403–.3886 |
| D005 release | .5516–.5534 / .5153–.5160 | .5482–.5534 / .5048–.5167 |
| D0005 release | .3679–.3693 / .3431–.3435 | .3609–.3782 / .3329–.3587 |
| D0 release | .3559–.3563 / .2974–.2987 | .3515–.3605 / .2875–.3118 |

## 7. 독립 평가 영상 15장의 실제 렌더

고정 113장 중 학습 98장과 분리한 평가 15장을 사용했다. 아래는 각 영상 지표의 산술평균이며, 원 평가 코드의 `summarize.optical_summary`로 닫힌 영수증을 읽어 확인했다. 모든 7개 실행×두 domain에서 15/15장이 평가됐고, 실패·참조/카메라 domain 부재·지표 결측·무한대는 모두 0이다. Full frame의 총 평가 화소는 실행마다 21,273,000, ROI는 1,721,921로 같다. 화소 수로 영상별 평균을 다시 가중하지 않았다.

ROI는 같은 고정 3D prism의 영상 투영 사각형이며, 가림·배경을 포함할 수 있다. Full frame은 P1의 30×30m 영역 밖 학습 문맥도 포함한다. 두 domain을 섞어 평균하지 않는다. 이 렌더는 공식 Gaussian 모델의 저장 RGB이며 TSDF raw/post mesh를 다시 렌더한 결과가 아니다. `anchor_512` 이름의 512는 표면 추출 조건이지 RGB 평가 해상도가 아니다.

| 실행 | Domain | PSNR (dB) ↑ | SSIM ↑ | LPIPS VGG native 0…1 ↓ | LPIPS VGG signed −1…1 ↓ |
|---|---|---:|---:|---:|---:|
| anchor8000 | full | 16.6712 | .4907 | .5804 | .6310 |
| anchor8000 | ROI | 14.5845 | .3933 | .5614 | .5937 |
| D005 native | full | 21.0251 | .6951 | .3977 | .4456 |
| D005 native | ROI | 19.1807 | .6987 | .3096 | .3460 |
| D0005 native | full | 21.5508 | .7044 | .3919 | .4401 |
| D0005 native | ROI | 23.2129 | .7971 | .2351 | .2720 |
| D0 native | full | 21.6196 | .7050 | .3925 | .4408 |
| D0 native | ROI | 23.2796 | .7954 | .2360 | .2745 |
| D005 release | full | 21.0303 | .6960 | .3972 | .4444 |
| D005 release | ROI | 19.1239 | .6996 | .3122 | .3478 |
| D0005 release | full | 21.6235 | .7048 | .3926 | .4414 |
| D0005 release | ROI | 23.1698 | .7946 | .2360 | .2746 |
| D0 release | full | 21.6395 | .7048 | .3922 | .4398 |
| D0 release | ROI | 23.2936 | .7982 | .2359 | .2721 |

Native 보호 고정의 깊이 `.005→.0005`는 평균 ROI PSNR `+4.0321dB`, SSIM `+.0984`, LPIPS native01 `−.0746`으로 개선된다. 그러나 final1024 raw F1@0.5m은 `.5279→.3811`이고 가까운 표면·피복 손실도 보였다. 영상 평균 개선을 현재 3D 표면의 동반 회복으로 해석하지 않는다. `.005→0`도 같은 평균 렌더 방향이지만 `.0005`와 0의 작은 차이로 우열·최선 조건을 정하지 않는다.

같은 15장에 대해 평가 index·사진 이름/ID·camera ID·사진 SHA·ROI 좌표·화소 수를 맞춘 paired 비교도 확인했다. `.005→.0005`의 개선/악화 사진 수는 full frame에서 PSNR `12/3`, SSIM `11/4`, LPIPS01 `12/3`, LPIPS11 `12/3`; ROI에서는 각각 `13/2`, `11/4`, `12/3`, `11/4`다. 동률은 없다. 개선 사진 수를 독립 표본 수나 유의성 검정으로 해석하지 않는다.

보호 해제의 평균 ROI PSNR 변화는 깊이 .005에서 `−.0569dB`, .0005에서 `−.0431dB`, 0에서 `+.0141dB`다. SSIM·LPIPS까지 일관된 단일 개선은 아니다. 반복 변동이 없어 이런 작은 값의 재현성을 판단할 수 없다. Anchor→native refinement에서는 두 domain의 네 지표 모두 평균이 좋아지지만 같은 512 표면의 가까운 임계값 F1은 낮아졌으므로 외관과 추출 표면의 효과를 분리한다.

Anchor→native의 경우 두 domain 모두 **15장 각각의 네 렌더 지표가 개선**됐다. 따라서 이 대비의 외관 향상은 사진 평균에만 한정된 현상이 아니지만, 모든 국소 세부나 3D 표면이 좋아졌다는 판정은 아니다. 보호 대비의 ROI 개선/악화 사진 수는 아래와 같이 지표와 깊이에 따라 엇갈린다.

| native→release의 깊이 | PSNR 개선/악화 | SSIM 개선/악화 | LPIPS01 개선/악화 | LPIPS11 개선/악화 |
|---|---:|---:|---:|---:|
| .005 | 8/7 | 7/8 | 6/9 | 8/7 |
| .0005 | 6/9 | 7/8 | 10/5 | 9/6 |
| 0 | 8/7 | 10/5 | 6/9 | 9/6 |

예를 들어 .0005의 LPIPS01은 10장에서 개선되지만 평균은 `.23508→.23595`로 악화된다. 개선·악화의 크기가 다르므로 다수 사진의 방향과 평균 방향도 서로 대신할 수 없다.

원자료: `$TASK/evaluation/renders/P1/<조건>/final/receipt.json` 및 `$TASK/evaluation/renders/P1/D005_Pnative/anchor_512/receipt.json`. 각 영수증의 `rows`가 사진 이름·SHA, 평가 index, domain, ROI, 네 지표와 실제 montage 경로를 담는다.

### 같은 실제 사진의 수동 확인

자동 대표 사례 선정과 별개로 고정 평가 순서의 **첫째/가운데/마지막 index 0/7/14**를 골랐다. 효과 크기를 보고 고른 시점이 아니다. 같은 세 시점에서 공통 anchor와 6조건의 ROI montage 21장을 실제 표시했고, index 0/7의 native/약한 깊이 native full-frame montage 4장도 확인했다. 이 3장만으로 15장 전체의 세부 품질을 대표한다고 주장하지 않는다.

| Index | 실제 평가 사진 | 관찰 |
|---|---|---|
| 0 | `DJI_20241217084551_0099_D.JPG` (image_id 90) | 높은 깊이 native/release는 바닥 줄눈 일부와 수목·곡면 지붕의 선을 유지하지만 장비와 일부 표면은 흐리고 찢긴다. 낮은 깊이 네 조건은 바닥 줄눈·장비·수목·곡면 지붕의 세부를 더 크게 뭉갠다. 평균 렌더 개선의 예외를 보존한다. |
| 7 | `DJI_20241217100259_0004_D.JPG` (image_id 571) | Anchor의 검은 결손과 심한 번짐은 final에서 줄었다. 낮은 깊이는 높은 깊이 native의 지붕 하단 검은 찢김을 줄이면서도 지붕의 평행선과 배경 수목 세부를 흐린다. 한 시점 안에도 개선·손실이 함께 있다. |
| 14 | `DJI_20241217103107_0010_D.JPG` (image_id 870) | 모든 final에서 전경 금속 지붕의 반복 선과 큰 외곽은 anchor보다 뚜렷하다. 낮은 깊이에서는 배경 기둥·포장·작은 물체가 사라지거나 흐리게 남는다. 전경의 외관 유지와 배경 세부 손실을 구분한다. |

Index 0의 ROI `[567,108,1220,760]`(425,756화소)는 아래처럼 네 지표 모두 악화된다. 사진 SHA256은 `a973b430489c227dfa9b3084e0ec99db88c5906add644d8bd8d86c0e3e2cbcb4`다.

| 동일 첫 사진 ROI | D005 native | D0005 native | 변경−기준 |
|---|---:|---:|---:|
| PSNR (dB) ↑ | 22.55847 | 21.64233 | −.91614 |
| SSIM ↑ | .563506 | .454901 | −.108606 |
| LPIPS native01 ↓ | .432815 | .571642 | +.138827 |
| LPIPS signed11 ↓ | .476186 | .625434 | +.149248 |

같은 사진의 full-frame PSNR은 반대로 `19.95315→20.66846dB`로 높아지지만 SSIM은 `−.03858`, LPIPS01은 `+.05177`, LPIPS11은 `+.05668`로 악화된다. ROI/full-frame, 사진별/전체 평균, 화소 오차/세부 지표를 함께 확인해야 하는 실제 반례다.

Montage의 왼쪽은 실제 평가 사진, 가운데는 같은 카메라의 저장 RGB, 오른쪽은 고정 0…255 범위의 평균 절대 RGB 오차다. Full-frame의 청록 사각형은 같은 ROI다. 원본 PNG를 열어 같은 배율에서 확인한다. 우측의 어두운 오차만으로 세부 보존을 판정하지 않는다.

직접 확인 경로:

- [첫 사진, 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [첫 사진, 깊이 .0005 native](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [첫 사진, 깊이 .005 release](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Prelease/final/montages/00000_fixed_prism_projected_bbox.png)
- [가운데 사진, anchor](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/anchor_512/montages/00007_fixed_prism_projected_bbox.png)
- [가운데 사진, 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00007_fixed_prism_projected_bbox.png)
- [마지막 사진, 원설정](../../../../../JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00014_fixed_prism_projected_bbox.png)

다른 조건도 같은 디렉터리 규칙의 `montages/00000`, `00007`, `00014`와 `_fixed_prism_projected_bbox.png` 또는 `_full_frame.png`로 비교할 수 있다. 최종 지역 viewer 및 자동 대표 사례의 생성·검증은 전체 평가 이후 별도 단계이며, 이 문서는 그 완료를 대신하지 않는다.

## 8. 해석과 후속 질문의 경계

현재 관찰은 특정 prior 충돌 면을 제약 완화로 움직일 수 있음과, 다른 면·피복·정밀도를 함께 잃을 수 있음을 보여준다. 원설정도 anchor 이후 외관을 개선하고 역방향 거리를 낮추는 부분이 있으며, GeoGS가 아무 수정도 못 한다는 주장은 성립하지 않는다. 반면 P1에서 가까운 임계값의 추출 표면 품질과 일부 영상 세부까지 함께 개선됐다는 결과도 아니다. 과거 ALS에서 파생한 초기화·보호 기하, 원 adaptive 제어와 공식 추출·후처리의 영향을 함께 가진 이번 실행이다. 원래 LoD2 입력의 모든 GeoGS 성능을 대표하지 않는다.

구체적으로는 남쪽 높은 충돌 면의 감소가 관찰된 개선, 높은 깊이 조건의 일부 영상 줄눈 및 final 금속 지붕 선이 상대적으로 남는 현상이 유지, 낮은 깊이에서 북측·수목 형태 구간과 첫 평가 사진 세부의 손실이 악화 사례다. 관측이 부족한 3D 면, 단면만으로 연결 여부가 불명인 표면, 반복 변동보다 작은지 알 수 없는 차이는 판단 불가로 남긴다. 확정된 참조 부재와 복원 실패를 서로 대체하지 않는다.

후속 검증 질문은 (1) 현재 면의 회복과 기존 근접 면·영상 세부 보존을 동시에 만족시키는 국소 제어가 가능한가, (2) 렌더 개선과 TSDF 표면 악화가 갈리는 위치에서 학습 상태와 추출 경로의 기여를 분리할 수 있는가, (3) 동일한 판단을 한 번 적용한 조건보다 반복 재판단이 추가로 개선하는가이다. 이번 전역 요인 제어 결과만으로 새로운 판단 알고리즘의 필요 조건이나 반복 재판단의 추가 효과가 입증된 것은 아니다. 결과를 보고 기존 설정을 수정하거나 최선 실행을 재선택하지 않았다.
