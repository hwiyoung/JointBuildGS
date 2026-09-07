# P1·P3 기존 자산 수정·보존·보완 검토

- Task: `PHD-GEOGS-P1P2P3-v1`.
- 문서 작성: 2026-09-09. 기존 고정 산출물을 다시 읽고 실제 그림을 표시한 추가 검토다.
- `scientific_verdict: null`.
- 상태: `BOUNDED_ASSET_REVIEW_COMPLETE_DEVELOPMENT_ONLY`.
- 범위: P1/P3의 6조건 final1024 표와 같은 anchor 이후 512 표, 실제 평가 사진, 고정 단면·양방향 거리 지도. 새로운 학습·추출·평가 점수 계산은 하지 않았다.
- 원래 LoD2 입력 GeoGS 자체의 성능과 ALS 파생 표면·깊이·초기화 적용을 구분한다. 같은 ALS 입력과 anchor의 영향은 모든 변경 조건에 남는다.

P1에서는 prior의 높은 불일치 윤곽을 줄이는 제어가 현재 관측면을 정확히 복원하는 제어와 일치하지 않았다. P3에서는 큰 곡면 구조를 유지하고 부족한 측벽을 보완하는 현상이 바닐라부터 관찰되지만, 추가 표면·모서리 변형·다른 영역의 손실이 함께 남는다. 두 지역 모두 더 깨끗한 전체 윤곽, 현재 참조에 가까운 표면, 세부가 보존된 사진 렌더가 같은 방향으로 변하지 않았다.

이 문서는 아래 열거한 **47개 PNG를 직접 표시**한 범위의 관찰과 현재 닫힌 원자료를 결합한다. 모든 사진·모든 공간 위치를 수동 검토했다는 뜻은 아니다. 기존 `P3_REVIEW_ko_v1.md`의 “진행 중”은 그 문서 작성 시점의 상태다. 이번 조회의 summary 영수증은 `TABLES_AND_ACTUAL_VIEWER_DATA_READY`이며 P3 6조건을 포함한다. 기존 문서를 덮어쓰지 않았다.

## 1. 비교의 기준과 읽는 방법

표면 수치는 표면 표본 간격 0.1m, 관측 UAS voxel 0.1m, seed 0의 기존 평가다. F1은 별도 표기가 없으면 0.5m 임계값의 precision/recall 조화평균이며 높은 방향을 참고한다. 표면→UAS와 UAS→삼각형 평균 거리는 낮은 방향을 참고한다. 단일 지표의 방향이 전체 자산 품질의 판정은 아니다.

Raw는 공식 TSDF 추출 직후 메시, post는 같은 메시의 연결 성분 후처리 결과다. Raw/post는 서로 다른 학습 조건이 아니다. final1024는 final끼리만 비교하며 anchor 학습 효과는 같은 512에서 비교한다. 실제 RGB는 Gaussian 모델의 같은 카메라 렌더이고 TSDF 메시를 렌더한 것이 아니다.

P1은 X=[−23,7), Y=[−21,9), Z=[−44.272,−25.962)m, P3는 X=[−60,−20), Y=[−42,12), Z=[−49.223,−16.993)m의 고정 작업좌표 영역이다. P1 단면은 X=−8m/Y=−6m, P3 단면은 X=−40m/Y=−15m, 폭은 모두 0.5m다. 도면은 폭 안의 평가 표본을 투영한 것이며 정확한 mesh-plane 교선은 아니다. 좌표와 높이 차이는 도면에서 읽은 대략값이며 새로운 국소 오차 계측은 아니다.

작업계 EPSG:25832, UAS 헤더 EPSG:32632, 기존 원점 이동과 ALS Z bridge 45.7m를 유지한 기존 결과다. 새 참조 정합이나 datum 보정을 하지 않았다. 여기서 “근접 구조”는 관측 UAS와 가까운 구조이며, 모든 면의 참조 피복·절대 datum·시간적 동일성을 검증한 정답 라벨이 아니다. Prior와 현재 참조의 큰 불일치도 시간 변화, 입력 오류, 변환 오류를 이 그림만으로 구별하지 못한다.

## 2. P1: 높은 prior 윤곽 감소와 현재 면·유효 구조 손실을 함께 봐야 한다

### 2.1 수정이 필요한 높은 윤곽

**직접 관찰:** X=−8m, Y≈−21…−5m에서 prior와 anchor512는 Z≈−37m의 경사진 윤곽을 유지한다. 같은 위치의 UAS와 MVS는 대체로 Z≈−42m의 낮은 면에 놓인다. 바닐라 final512/1024는 이 높은 면을 변형·분리하지만 넓은 높은 윤곽을 여전히 남긴다. .005의 보호 해제도 이를 해소하지 않는다.

깊이 .0005/0의 네 조건에서는 그 높은 연속 윤곽이 크게 줄고 낮은 참조면 쪽으로 결과가 내려온다. 다만 .0005 native의 Y≈−13…2m는 대략 0.5–1.5m 높게 남고, .0005 release와 D0 release에서는 Y≈0…5m가 다시 위로 올라간다. D0 native raw는 저면의 여러 구간이 끊긴다. 높은 불일치 면의 감소를 현재 평탄면의 정확하고 완전한 회복으로 읽으면 안 된다.

같은 final1024 두 방향 거리 지도에서 기존 중앙/남측의 붉은 범위는 낮은 깊이에서 줄어든다. 동시에 북측과 수목 형태 영역의 UAS→표면 거리는 커진다. 지도가 2m에서 포화하므로 붉은색끼리 정확한 크기 비교는 할 수 없다.

근거: [viewer/P1/prior_mesh.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/prior_mesh.sections.png), [viewer/P1/mvs_points.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/mvs_points.sections.png), [viewer/P1/D005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.final.raw.sections.png), [viewer/P1/D0005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.final.raw.sections.png), [viewer/P1/D0005_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Prelease.final.raw.sections.png).

### 2.2 유지해야 할 구조와 세부의 손실

**직접 관찰:** X=−8m, Y≈6…9m의 높은 면은 prior/anchor/native final이 UAS 윤곽에 가깝게 남기는 부분이다. 낮은 깊이에서는 이 면 주위의 띠가 두꺼워지거나 위·아래로 갈라진다. D0 release는 이 위치에서 Z≈−35…−32m의 추가 높은 띠가 뚜렷하다. Y=−6m, X≈−20…−15m의 수목 형태 비평면 윤곽도 prior·높은 깊이가 남기던 상부 일부를 낮은 깊이에서 잃는다. 수목을 곧바로 건물 구조 유지 성과로 합산하지 않으며, 계절·관측·표면화 한계가 있는 별도 사례로 둔다.

D0 native raw→post에서는 X=−8m, Y≈−17…−12m처럼 raw에 저면 표본이 있던 일부 구간이 사라진다. UAS의 검은 저면은 남아 있으므로 해당 단면 띠에서 예측 표본의 소실을 확인할 수 있다. 폭이 제한된 단면의 소실을 전체 3D 연결성이나 정확한 결손 면적으로 확장하지 않는다. 후처리가 부유물을 줄이면서 UAS에 가까운 부분도 없앨 수 있다는 진단이다.

근거: [viewer/P1/D0_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Pnative.final.raw.sections.png), [viewer/P1/D0_Pnative.final.post.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Pnative.final.post.sections.png), [viewer/P1/D0_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Prelease.final.raw.sections.png).

### 2.3 P1 final1024의 여섯 조건

각 F1 셀은 raw / post다. RGB ROI는 같은 15평가 사진의 고정 prism 투영 사각형에 대한 사진별 비가중 평균이다. ROI에는 가림·배경이 포함될 수 있다. LPIPS는 VGG의 signed11 입력 값만 이 표에 표시하며 native01 원값도 원자료에 남아 있다.

| 조건 | F1@.5 raw / post | raw 표면→UAS / UAS→표면 m | ROI PSNR dB | SSIM | LPIPS signed11 |
|---|---:|---:|---:|---:|---:|
| D005_Pnative | .527860 / .497063 | 1.25830 / .57553 | 19.180724 | .698717 | .346019 |
| D0005_Pnative | .381062 / .351950 | .97361 / .89520 | 23.212865 | .797119 | .272007 |
| D0_Pnative | .390698 / .356388 | 1.18579 / .84214 | 23.279582 | .795382 | .274471 |
| D005_Prelease | .553365 / .515935 | 1.35166 / .56933 | 19.123857 | .699633 | .347757 |
| D0005_Prelease | .369149 / .343549 | 1.02599 / .85874 | 23.169763 | .794629 | .274618 |
| D0_Prelease | .355906 / .297863 | 1.21895 / .83523 | 23.293649 | .798173 | .272090 |

Prior mesh의 F1@.5는 .6661, 표면→UAS/UAS→표면은 1.1136/.8460m다. 바닐라도 역방향 평균을 낮추지만 정방향과 엄격한 F1을 함께 개선하지는 않는다. Native .005→.0005는 raw 면적 2901.34→1724.87m², recall@.5 .629412→.347632, UAS→표면 .575526→.895201m다. 면적 감소 전체를 노이즈 제거라 부를 수 없는 이유다.

## 3. P3: 바닐라의 구조 보완을 인정하면서 추가 표면과 경계 손실을 분리한다

### 3.1 유효한 큰 구조의 유지와 부족한 측벽 보완

**직접 관찰:** X=−40m, Y≈−29…5m/Z≈−22…−19m의 큰 곡면 지붕은 prior와 UAS가 가까우며 anchor와 여섯 final1024 raw에서 큰 윤곽이 대체로 유지된다. 이 그림에서 MVS는 지붕을 포함하면서 위·아래로 뻗는 이탈 표본과 두꺼운 가장자리 분포를 보인다.

Y=−15m, X≈−48m의 수직면은 prior mesh/anchor에서 Z≈−23…−41m의 많은 표본이 부족하지만 바닐라 final512/1024에서 연속에 가까운 표본으로 보완된다. 낮은 깊이에서도 이 보완 윤곽은 남는다. 이는 “GeoGS가 유효한 prior를 유지하며 영상으로 보완하는 부분”의 실제 사례다. 다만 벽 전체 두께·모서리 정확도·평가 참조 피복은 별도 문제다.

MVS는 이 ALS arm의 직접 초기화·감독 입력이 아니다. GeoGS가 MVS와 비슷한 오류를 보인다는 이유로 MVS 오류가 직접 유입됐다고 부르지 않는다.

### 3.2 지붕 아래 띠의 감소가 곧 정확한 구조 선택은 아니다

**직접 관찰:** 바닐라와 .005 release는 큰 지붕 아래 Z≈−30…−42m에 긴 띠·파편을 여러 높이로 만든다. 깊이를 낮춘 네 조건에서는 이 띠가 대부분 사라지고 큰 지붕·보완 측벽은 남는다. 따라서 차이는 실제로 있으며 위에서 지붕 외곽만 볼 때보다 단면에서 크다.

그러나 이 내부처럼 보이는 공간에는 관측 UAS가 희소하거나 없다. “관측 참조에서 먼 표면”과 “존재하지 않아야 할 확정된 오류 구조”를 구분한다. 특히 anchor512에도 Z≈−42…−46m에 긴 저면 띠가 이미 있으므로 final 내부 표면 전부를 refinement에서 새로 만든 오류라 설명할 수 없다.

같은512 anchor→native final에서는 긴 저면 띠가 줄고 그보다 위의 파편 분포와 측벽 보완이 나타난다. 이 변화의 생성 원인을 초기화·깊이·Gaussian 가시성·TSDF 중 하나로 확정하지 않는다. Raw→post에서도 다수 띠가 없어지지만 벽에 붙어 있는 돌출은 남는다. 이는 단순 연결 성분 제거로 처리되지 않는 잔여 형상과 제거된 관측 표면을 각각 살펴볼 필요를 뜻한다.

근거: [viewer/P3/D005_Pnative.anchor_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.anchor_512.raw.sections.png), [viewer/P3/D005_Pnative.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.mesh_512.raw.sections.png), [viewer/P3/D005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.final.raw.sections.png), [viewer/P3/D005_Pnative.final.post.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.final.post.sections.png), [viewer/P3/D0005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Pnative.final.raw.sections.png).

### 3.3 남는 경계 변형·결손과 참조가 있는 영역의 손실

X=−40m, Y≈1…5m의 지붕 끝은 모든 final에서 UAS의 원 윤곽 아래로 접혀 돌아가는 띠를 보인다. Y≈−35…−32m의 지붕·벽 사이 연결도 둥글고 두껍다. Y=−15m, X≈−35…−31m/Z≈−23…−30m에서는 낮은 깊이일수록 원 곡면보다 안쪽으로 내려오는 부분과 돌출이 보인다. X≈−22…−23m의 높은 수직면은 관측 UAS가 있음에도 모든 비교 조건에서 대부분 예측 표본이 부족하다.

이들은 큰 지붕 윤곽이 유지된다는 관찰과 동시에 남는 세부·완전성 문제다. 낮은 깊이에서 수목 형태 주변 영역의 UAS→표면 거리도 커지는 것이 거리 지도에 보인다. 참조가 관측된 영역의 소실과 지붕 내부처럼 참조가 부족한 영역의 판단 불가를 합치지 않는다.

### 3.4 P3 final1024의 여섯 조건

RGB ROI는 같은 20평가 사진의 평균이다. Raw/post 표면과 Gaussian RGB를 서로 다른 출력 품질로 유지한다.

| 조건 | F1@.5 raw / post | raw 표면→UAS / UAS→표면 m | ROI PSNR dB | SSIM | LPIPS signed11 |
|---|---:|---:|---:|---:|---:|
| D005_Pnative | .634312 / .656942 | .80068 / .70941 | 21.266417 | .702616 | .361015 |
| D0005_Pnative | .649268 / .637696 | .41826 / .79715 | 22.749474 | .747919 | .334995 |
| D0_Pnative | .645013 / .636642 | .47364 / .76961 | 22.820679 | .749753 | .333772 |
| D005_Prelease | .622467 / .646174 | .84184 / .68847 | 21.769524 | .718406 | .349597 |
| D0005_Prelease | .646882 / .640590 | .47713 / .74271 | 22.876416 | .750962 | .335296 |
| D0_Prelease | .624826 / .611271 | .47840 / .74540 | 22.782506 | .750772 | .334870 |

Prior mesh의 F1@.5는 .83939, 표면→UAS/UAS→표면은 .15079/.63594m다. 이 값이 높다는 이유로 prior가 벽 결손 없이 완전하다고 말하지 않는다. 바닐라는 부족한 벽을 보완하면서 많은 추가 표면도 만든다.

Native .005→.0005의 raw F1@.5는 상승하지만 raw precision .631418→.731881, recall .637233→.583413으로 방향이 갈린다. 같은 대비의 raw F1@.1은 .22527→.19512, @.25는 .46436→.43326이며 post F1@.5도 감소한다. 특정 임계값·raw만 선택하면 성공처럼 보이는 반면 가까운 기하·완전성·post 결과는 다른 답을 준다.

## 4. 같은512에서 본 anchor 이후 변화

이 표는 anchor8000과 final30000을 같은 512 추출로 비교한 기존 CSV다. 각 셀은 F1@.5의 raw / post이며, final1024 표와 직접 차감하지 않는다.

| 상태/조건 | P1 | P3 |
|---|---:|---:|
| 공통 anchor8000 | .640809 / .636191 | .701764 / .682765 |
| D005_Pnative final30000 | .499435 / .490344 | .588058 / .601022 |
| D0005_Pnative final30000 | .375917 / .360673 | .625704 / .621941 |
| D0_Pnative final30000 | .393542 / .372941 | .636363 / .631315 |
| D005_Prelease final30000 | .518792 / .500807 | .568260 / .588570 |
| D0005_Prelease final30000 | .383399 / .371943 | .634125 / .630639 |
| D0_Prelease final30000 | .341080 / .323924 | .632738 / .629489 |

P1 anchor→native raw는 UAS→표면 평균 .759603→.595780m로 낮아지지만 표면→UAS .95043→1.24459m, F1@.5 .640809→.499435다. P3는 UAS→표면 .759690→1.000428m, F1@.5 .701764→.588058이다. 한편 같은 상태의 실제 Gaussian ROI 평균 PSNR은 P1 14.584458→19.180724dB, P3 15.366711→21.266417dB로 높아진다.

따라서 refinement가 실행되지 않은 것이 아니다. 외관·측벽 보완·추가 표면 변화가 있으며, 그 개선이 특정 표면 지표의 개선과 일치하지 않는다. Anchor가 모든 최종 품질에서 낫다는 반대 결론도 성립하지 않는다. Anchor에는 남겨둔 높은 불일치 면, 벽 결손, 렌더 결손이 있다.

## 5. 실제 사진에서 보이는 세부·외관의 차이

수동 사례는 기존 검토에서 정한 첫째/가운데/마지막 순서 P1 index0/7/14, P3 index0/10/19를 유지했다. 좋은 점수의 사진으로 교체하지 않았다. P3 index0은 과거에도 보았던 이미지이므로 blind 선택이라 하지 않는다. 아래 서술은 이번에 원 사진·동일 카메라 렌더·고정 스케일 RGB 오차 montage를 직접 다시 표시한 결과다.

| 지역/사진 | 직접 관찰 | 보존해야 할 해석 |
|---|---|---|
| P1 index0, DJI_20241217084551_0099_D.JPG | .005 native도 장비·포장·수목을 흐리지만 .0005 native에서는 포장 줄눈과 작은 장비 형상, 수목·곡면 가장자리 세부가 더 뭉개진다. | 저면의 3D 불일치 감소와 영상의 세부 보존은 같은 결과가 아니다. |
| P1 index7, DJI_20241217100259_0004_D.JPG | Anchor의 검은 결손·번짐이 native final에서 줄고 지붕 반복 선이 나타난다. .0005 native는 지붕 하단 검은 찢김을 줄이지만 평행선과 배경 수목을 더 흐리게 한다. | 한 이미지에서도 큰 결손 감소와 세부 손실이 공존한다. |
| P1 index14, DJI_20241217103107_0010_D.JPG | Native/약한 깊이 모두 전경 금속 지붕 선이 있으나 약한 깊이에서 배경의 포장·기둥·작은 물체가 더 약해진다. | 전경의 유지로 배경 세부 소실을 가리지 않는다. |
| P3 index0, DJI_20241217084553_0100_D.JPG | Native의 포장·장비가 이미 흐리며 약한 깊이와 D0 release는 포장·수목·작은 물체를 더 크게 평활화한다. 큰 금속 지붕 외곽은 비슷하다. | 상단 높이 색상 뷰어에서 보이지 않는 외관 차이가 있다. |
| P3 index10, DJI_20241217095757_0003_D.JPG | Anchor의 흐리고 찢긴 외벽이 native final에서 반복 수평선·전경 지붕으로 뚜렷해진다. Native/약한 깊이/.005 release의 전체 모습 차이는 작지만 외벽 하단과 얇은 선의 번짐이 남는다. | 바닐라의 큰 회복을 인정한다. 작은 제어 차이의 우열은 사진 하나로 정하지 않는다. |
| P3 index19, DJI_20241217103545_0062_D.JPG | Native도 외벽 수평선과 수목이 흐리다. 약한 깊이는 수목 가지·하부 외벽·포장을 더 강하게 뭉개며 큰 지붕 외곽과 밝은 띠는 유사하다. | 동일한 큰 외곽 안에 의미 있는 세부 손실이 숨을 수 있다. |

D005_Pnative→D0005_Pnative의 같은 사진 ROI 실제 값:

| 사진 | PSNR dB, 기준→변경 | SSIM, 기준→변경 | LPIPS signed11, 기준→변경 |
|---|---:|---:|---:|
| P1 index0 | 22.558470→21.642330 | .563506→.454901 | .476186→.625434 |
| P1 index7 | 23.184326→25.633707 | .722578→.768324 | .376971→.390108 |
| P1 index14 | 21.871723→21.921356 | .782361→.764392 | .243997→.278386 |
| P3 index0 | 21.573837→21.566605 | .456135→.426281 | .564727→.615939 |
| P3 index10 | 22.803288→22.741278 | .809023→.804479 | .208803→.213873 |
| P3 index19 | 20.992661→20.373161 | .609109→.523224 | .412827→.480939 |

P3 위 세 사진은 모두 세 지표에서 낮은 깊이의 악화 방향이지만, 20사진 전체의 ROI 평균은 개선 방향이다. 세 사진을 전체 대표 성능으로 바꾸지 않는다. 기존 paired 표에서 P3 .005→.0005 ROI PSNR/SSIM의 개선 사진 수는 각각 9/20이다. 사진 평균, 사진별 성패, 국소 세부는 서로 대신할 수 없다.

바로 열어볼 실제 이미지: [renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png), [renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png), [renders/P3/D005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png), [renders/P3/D0005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D0005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png).

## 6. 관찰에서 이어지는 우선 진단과 연구 질문

이 순서는 후속 진단의 우선순위이며 새로운 알고리즘의 우위·필수성에 대한 과학적 판정이 아니다. 참조를 다음 학습 판단 입력으로 사용하라는 뜻도 아니다.

| 우선순위 | 관찰된 현상 | 현재 분리되지 않은 원인 | 다음에 답할 질문 |
|---|---|---|---|
| 1 | P1 높은 prior 윤곽을 줄였지만 낮은 면이 들뜨고 기존 근접 면·세부를 잃음 | prior 감독, 보호, 실현 DA3 궤적, 현재 RGB의 모호성이 함께 작용 | 영상의 국소 관측 지지에 따라 수정해야 할 범위와 보존할 범위를 제어하면 전역 완화의 손실을 줄이는가? |
| 1 | P3 바닐라가 곡면 유지·벽 보완을 이미 수행함 | ALS→mesh에서 잃은 벽과 실제 prior 취득 결손의 기여 | 어떤 보완은 기본 최적화로 충분하며, 어느 경계·가림 조건에 추가 제어가 필요한가? |
| 1 | 실제 렌더 향상과 TSDF 기하 악화가 갈림 | Gaussian 깊이 일관성, 가시성, 추출 격자·깊이 절단·후처리의 기여 | 같은 모델의 다중 시점 깊이와 동일 추출 도메인을 검토하면 학습 오류와 추출 오류를 분리할 수 있는가? |
| 2 | P3 내부처럼 보이는 띠는 줄지만 내부 참조가 부족함 | 관측 부재와 잘못된 추가 표면의 식별 한계 | 보이는 면과 보이지 않는 면의 판단 가능성을 어떻게 표시하고, 평가 전용 참조 없이 무근거 삭제를 통제할 것인가? |
| 2 | Raw→post에서 고립 표본과 참조에 가까운 표본이 함께 사라짐 | 연결 성분 크기가 유효성·현재성의 대리 지표가 되지 못함 | 추출·후처리가 세부·완전성 손실을 만들 때 이를 어떤 별도 출력 계약·측정으로 통제할 것인가? |
| 2 | .005 보호 해제의 외관 차이는 작고 다른 지표 방향은 엇갈림 | 반복 변동 미측정, 여러 보호 기제가 함께 변경됨 | 같은 anchor 원설정 반복과 보호 구성요소 분리 후에도 차이가 유지되는가? |

반복 재판단이 필요한지는 이 표에서 결정되지 않는다. 그 추가 효과는 동일한 판단을 한 번 적용한 조건과 같은 자원·입력·평가 범위에서 따로 비교할 질문이다. “변화가 있으면 Gaussian 소스를 바꿔야 한다” 또한 이 결과가 입증한 결론이 아니다. 바닐라가 수정·보완하는 범위, 제어 완화로 달라지는 범위, 서로 모순되는 출력 품질을 먼저 기술한다.

## 7. 증거·재현과 이번 검토의 한계

이번 수치 조회는 실행 중인 `jbgs-geogs-p1p2p3-viewer-8902` 컨테이너의 Python 표준 라이브러리 `csv.DictReader`로 기존 `/task/evaluation/summary/` CSV를 읽었다. 컨테이너 이미지 ID는 `sha256:c5445549fe7f6995e0478ab9b07565da09947c1f1d54e274802dca50aa1e7f8e`, 문서 조회 시 작업 저장소 HEAD는 `72f45bcf861c5fe6e0c70e28e0686a72e9424b17`이다. 이 HEAD는 학습 코드 버전이라는 뜻이 아니다. 원 실행 버전과 조건은 기존 실행 영수증에 따른다.

| 원자료 | 이번 조회 SHA256 | 사용 필터/필드 |
|---|---|---|
| [summary/geometry_primary_1024.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/geometry_primary_1024.csv) | `528cb46deceefa9a9dbadc7915700f58059f91c3005932fd72a607761aefc023` | region P1/P3, sensitivity sample0.1_reference0.1, threshold_m 0.5, candidate final raw/post; f1, precision, recall, p2ref_mean_m, ref2candidate_mean_m, surface_area_m2 |
| [summary/geometry_anchor_refinement_512.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/geometry_anchor_refinement_512.csv) | `42a0576a20a25a57dcd59161de5d3b5df8a9fdbef3380115f165b8cd67b0b48a` | 같은 지역/표본/임계값, candidate anchor_512/mesh_512 raw/post |
| [summary/render_summary.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/render_summary.csv) | `2fbac52479548f0a25185301f1ab7786053c7fe8bd780bfb63df2790f46489bb` | stage final/anchor_512, domain fixed_prism_projected_bbox; psnr_native_db, ssim_native, lpips_vgg_signed_11 |
| [summary/render_all_images.csv](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/summary/render_all_images.csv) | 기존 실행 영수증 계보 유지 | 같은 domain/condition, evaluation_index P1 0/7/14, P3 0/10/19; name, photo/render SHA, 지표와 montage 경로 |

조회 중 최초 개별 사진 필터에서 존재하지 않는 `index` 대신 실제 열 `evaluation_index`를 사용하도록 바로잡았다. 첫 조회는 행을 반환하지 않았고 입력·결과를 변경하지 않았다. 그 빈 결과를 누락·실패로 집계하지 않았으며 수정한 조회의 실제 행을 표에 사용했다.

고정 제어의 전체 실행 차이를 기술한다. 원 DA3 adaptive 규칙은 같지만 실현 loss·가중치 궤적이 같지 않을 수 있다. 보호 해제는 gradient 감쇠와 clone/split/prune 제한을 함께 바꿨으므로 각각의 단독 효과가 아니다. 모든 변경은 ALS 초기화와 공통 anchor의 영향을 유지하며 image-only가 아니다. 보조 반복은 P1/P2 실패·P3 미시작으로 품질 변동을 측정하지 못했다. 작은 차이가 반복 변동을 넘는지 판단할 수 없다.

UAS와 기존 모든 평가 전용 참조는 이 문서에서 분석에만 사용했다. 재학습·정합 보정·파라미터 재선택을 하지 않았다. MVS·ALS 점 NN과 메시 표면 거리는 추정 대상이 달라 단일 순위로 합치지 않는다. 확정된 시간 변화/노이즈 면적/건물 보존 성공률을 새로 만들지 않았다. 아래 직접 표시 목록 외의 시점·표면을 전수 수동 검토했다고 주장하지 않는다.

## 8. 이번에 직접 표시한 47개 PNG

원 그림을 변경하거나 새 과학 그림을 합성하지 않았다. 각 링크는 실제 표시한 기존 파일이다. 단면 27개, 거리 지도 4개, 실제 RGB 비교 montage 16개다. 작성 후 동일 Docker 컨테이너에서 목록의 파일 존재를 다시 확인했다: 47개/고유 47개/누락 0개.

### P1 단면 13개

- [viewer/P1/prior_mesh.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/prior_mesh.sections.png)
- [viewer/P1/mvs_points.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/mvs_points.sections.png)
- [viewer/P1/D005_Pnative.anchor_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.anchor_512.raw.sections.png)
- [viewer/P1/D005_Pnative.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.mesh_512.raw.sections.png)
- [viewer/P1/D0005_Pnative.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.mesh_512.raw.sections.png)
- [viewer/P1/D0_Prelease.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Prelease.mesh_512.raw.sections.png)
- [viewer/P1/D005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.final.raw.sections.png)
- [viewer/P1/D0005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.final.raw.sections.png)
- [viewer/P1/D0_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Pnative.final.raw.sections.png)
- [viewer/P1/D005_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Prelease.final.raw.sections.png)
- [viewer/P1/D0005_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Prelease.final.raw.sections.png)
- [viewer/P1/D0_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Prelease.final.raw.sections.png)
- [viewer/P1/D0_Pnative.final.post.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0_Pnative.final.post.sections.png)


### P3 단면 14개

- [viewer/P3/prior_mesh.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/prior_mesh.sections.png)
- [viewer/P3/mvs_points.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/mvs_points.sections.png)
- [viewer/P3/D005_Pnative.anchor_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.anchor_512.raw.sections.png)
- [viewer/P3/D005_Pnative.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.mesh_512.raw.sections.png)
- [viewer/P3/D0005_Pnative.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Pnative.mesh_512.raw.sections.png)
- [viewer/P3/D0_Prelease.mesh_512.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0_Prelease.mesh_512.raw.sections.png)
- [viewer/P3/D005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.final.raw.sections.png)
- [viewer/P3/D0005_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Pnative.final.raw.sections.png)
- [viewer/P3/D0_Pnative.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0_Pnative.final.raw.sections.png)
- [viewer/P3/D005_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Prelease.final.raw.sections.png)
- [viewer/P3/D0005_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Prelease.final.raw.sections.png)
- [viewer/P3/D0_Prelease.final.raw.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0_Prelease.final.raw.sections.png)
- [viewer/P3/D005_Pnative.final.post.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.final.post.sections.png)
- [viewer/P3/D0005_Pnative.final.post.sections.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Pnative.final.post.sections.png)


### P1·P3 양방향 거리 지도 4개

- [viewer/P1/D005_Pnative.final.raw.distance.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D005_Pnative.final.raw.distance.png)
- [viewer/P1/D0005_Pnative.final.raw.distance.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P1/D0005_Pnative.final.raw.distance.png)
- [viewer/P3/D005_Pnative.final.raw.distance.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D005_Pnative.final.raw.distance.png)
- [viewer/P3/D0005_Pnative.final.raw.distance.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/viewer/P3/D0005_Pnative.final.raw.distance.png)


### P1 실제 사진 montage 7개

- [renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [renders/P1/D005_Pnative/anchor_512/montages/00007_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/anchor_512/montages/00007_fixed_prism_projected_bbox.png)
- [renders/P1/D005_Pnative/final/montages/00007_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00007_fixed_prism_projected_bbox.png)
- [renders/P1/D0005_Pnative/final/montages/00007_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00007_fixed_prism_projected_bbox.png)
- [renders/P1/D005_Pnative/final/montages/00014_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D005_Pnative/final/montages/00014_fixed_prism_projected_bbox.png)
- [renders/P1/D0005_Pnative/final/montages/00014_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P1/D0005_Pnative/final/montages/00014_fixed_prism_projected_bbox.png)


### P3 실제 사진 montage 9개

- [renders/P3/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [renders/P3/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D0005_Pnative/final/montages/00000_fixed_prism_projected_bbox.png)
- [renders/P3/D005_Pnative/anchor_512/montages/00010_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/anchor_512/montages/00010_fixed_prism_projected_bbox.png)
- [renders/P3/D005_Pnative/final/montages/00010_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/final/montages/00010_fixed_prism_projected_bbox.png)
- [renders/P3/D0005_Pnative/final/montages/00010_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D0005_Pnative/final/montages/00010_fixed_prism_projected_bbox.png)
- [renders/P3/D005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png)
- [renders/P3/D0005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D0005_Pnative/final/montages/00019_fixed_prism_projected_bbox.png)
- [renders/P3/D005_Prelease/final/montages/00010_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D005_Prelease/final/montages/00010_fixed_prism_projected_bbox.png)
- [renders/P3/D0_Prelease/final/montages/00000_fixed_prism_projected_bbox.png](/media/innopam/InnoPAM-8TB/hwiyoung/code/JointBuildGS-artifacts/phase-payloads/phd/geogs_p1p2p3_v1/PHD-GEOGS-P1P2P3-v1/evaluation/renders/P3/D0_Prelease/final/montages/00000_fixed_prism_projected_bbox.png)

